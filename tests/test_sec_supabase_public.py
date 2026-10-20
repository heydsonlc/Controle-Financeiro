"""
Testes SEC-SUPABASE-PUBLIC-1 — protecao das tabelas legadas do schema public.

Num cluster PostgreSQL descartavel que reproduz o Supabase (shim + papel que
imita o `postgres` da plataforma: sem superuser, BYPASSRLS e default privileges
que concedem tudo a anon/authenticated), roda a cadeia REAL de migrations Alembic:
  1. ate 5c91e95eb05d -> prova que o problema existe (anon le e grava);
  2. ate o head (c4f7a2d91b3e) -> prova que foi corrigido e que o Flask segue funcionando.
Alembic e o smoke do Flask rodam em subprocesso (isola logging e config).
Nunca toca no banco local de desenvolvimento nem no Supabase remoto.
"""
import importlib.util
import json
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.supabase_local import (
    USUARIO_A,
    ClusterLocal,
    PostgrestLocal,
    assinar_jwt,
    claims_usuario,
    encontrar_pg_bin,
    encontrar_postgrest,
)

psycopg2 = pytest.importorskip('psycopg2')

ROOT = Path(__file__).resolve().parent.parent
REVISAO_ANTERIOR = '5c91e95eb05d'
REVISAO_PROTECAO = 'c4f7a2d91b3e'
PG_BIN = encontrar_pg_bin()
POSTGREST_BIN = encontrar_postgrest()
SEGREDO_JWT = secrets.token_urlsafe(48)
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

_SCRIPT_ALEMBIC = """
import sys
from backend.app import create_app
from flask_migrate import upgrade
app = create_app('local')
with app.app_context():
    upgrade(directory='migrations', revision=sys.argv[1])
print('ALEMBIC_OK', sys.argv[1])
"""

_SCRIPT_SMOKE_FLASK = """
import json
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    u = Usuario(email='flask.smoke@teste.local', nome='Smoke', ativo=True)
    u.definir_senha('Senha-ficticia-smoke-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
r_login = c.post('/login', data={'email': 'flask.smoke@teste.local', 'senha': 'Senha-ficticia-smoke-2026'})
r_lista = c.get('/api/categorias')
r_cria = c.post('/api/categorias', json={'nome': 'Categoria smoke SEC', 'cor': '#123456'})
r_lista2 = c.get('/api/categorias')
nomes = [x.get('nome') for x in (r_lista2.get_json() or {}).get('data', [])]
print('SMOKE ' + json.dumps({'login': r_login.status_code, 'lista': r_lista.status_code,
      'cria': r_cria.status_code, 'criada_visivel': 'Categoria smoke SEC' in nomes}))
"""


def _rodar(script, cluster, papel, *args):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': cluster.dsn(papel)}
    env.pop('FLASK_ENV', None)
    resultado = subprocess.run([sys.executable, '-c', script, *args], cwd=ROOT, env=env,
                               capture_output=True, text=True, timeout=300)
    assert resultado.returncode == 0, resultado.stderr[-1500:]
    return resultado.stdout


def _carregar_migration():
    caminho = next((ROOT / 'migrations' / 'versions').glob(f'{REVISAO_PROTECAO}_*.py'))
    spec = importlib.util.spec_from_file_location('migration_sec_public', caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _rest(base, caminho, metodo='GET', token=None, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(base + caminho, method=metodo, data=dados)
    req.add_header('Accept-Profile' if metodo == 'GET' else 'Content-Profile', 'public')
    if dados is not None:
        req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _privilegios_api(conn):
    with conn.cursor() as cur:
        cur.execute("""
            select count(*) filter (where has_table_privilege(r.rolname, c.oid, 'SELECT,INSERT,UPDATE,DELETE')),
                   count(*) filter (where c.relrowsecurity)
              from pg_class c join pg_namespace n on n.oid = c.relnamespace
              cross join (values ('anon'), ('authenticated')) as r(rolname)
             where n.nspname = 'public' and c.relkind = 'r'
        """)
        return cur.fetchone()


@pytest.fixture(scope='module')
def ambiente(tmp_path_factory):
    """Cluster no estado anterior (5c91), metricas 'antes', e depois o head."""
    tmp = tmp_path_factory.mktemp('sec_public')
    with ClusterLocal(PG_BIN, tmp) as cluster:
        cluster.aplicar_shim()
        papel = cluster.criar_papel_estilo_supabase()
        _rodar(_SCRIPT_ALEMBIC, cluster, papel, REVISAO_ANTERIOR)

        antes = {}
        conn = cluster.conectar()
        try:
            antes['privilegios_api'], antes['tabelas_com_rls'] = _privilegios_api(conn)
            with conn.cursor() as cur:
                cur.execute("select count(*) from pg_tables where schemaname = 'public'")
                antes['tabelas'] = cur.fetchone()[0]
        finally:
            conn.close()

        postgrest = None
        if POSTGREST_BIN:
            # Como no Supabase hoje: o public exposto na Data API.
            postgrest = PostgrestLocal(POSTGREST_BIN, cluster, SEGREDO_JWT, tmp, schemas='public').__enter__()
            antes['rest_anon_get_usuario'] = _rest(postgrest.url, '/usuario?select=id&limit=0')
            antes['rest_anon_patch_usuario'] = _rest(postgrest.url, '/usuario?id=eq.-1', 'PATCH', corpo={'nome': 'x'})
        try:
            _rodar(_SCRIPT_ALEMBIC, cluster, papel, 'head')
            yield {'cluster': cluster, 'papel': papel, 'antes': antes, 'postgrest': postgrest}
        finally:
            if postgrest:
                postgrest.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# O problema existia (reproduz o Supabase antes da correcao)
# ---------------------------------------------------------------------------

def test_antes_da_migration_anon_tinha_acesso_total(ambiente):
    antes = ambiente['antes']
    assert antes['tabelas'] >= 50
    assert antes['tabelas_com_rls'] == 0
    # 2 papeis x todas as tabelas com SELECT/INSERT/UPDATE/DELETE.
    assert antes['privilegios_api'] == 2 * antes['tabelas']


def test_antes_da_migration_rest_anonimo_lia_e_gravava(ambiente):
    if not ambiente['postgrest']:
        pytest.skip('POSTGREST_BIN nao definido')
    assert ambiente['antes']['rest_anon_get_usuario'] == 200
    assert ambiente['antes']['rest_anon_patch_usuario'] in (200, 204)


# ---------------------------------------------------------------------------
# Depois da migration
# ---------------------------------------------------------------------------

def test_todas_as_tabelas_com_rls_e_sem_force(ambiente):
    conn = ambiente['cluster'].conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("""select count(*), count(*) filter (where c.relrowsecurity), count(*) filter (where c.relforcerowsecurity)
                             from pg_class c join pg_namespace n on n.oid = c.relnamespace
                            where n.nspname = 'public' and c.relkind = 'r'""")
            total, com_rls, com_force = cur.fetchone()
    finally:
        conn.close()
    assert com_rls == total and total >= 50
    assert com_force == 0, 'FORCE nao deve ser aplicado'


def test_anon_e_authenticated_sem_nenhum_privilegio_em_tabelas(ambiente):
    conn = ambiente['cluster'].conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("""select count(*) from information_schema.role_table_grants
                            where table_schema = 'public' and grantee in ('anon', 'authenticated')""")
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_anon_e_authenticated_sem_privilegio_em_sequencias(ambiente):
    conn = ambiente['cluster'].conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("""select count(*), count(*) filter (where has_sequence_privilege('anon', c.oid, 'USAGE,SELECT,UPDATE')
                                                         or has_sequence_privilege('authenticated', c.oid, 'USAGE,SELECT,UPDATE'))
                             from pg_class c join pg_namespace n on n.oid = c.relnamespace
                            where n.nspname = 'public' and c.relkind = 'S'""")
            total, expostas = cur.fetchone()
    finally:
        conn.close()
    assert total > 0 and expostas == 0


def test_tabela_criada_depois_nao_nasce_exposta(ambiente):
    cluster, papel = ambiente['cluster'], ambiente['papel']
    conn = cluster.conectar(papel)
    try:
        with conn.cursor() as cur:
            cur.execute('create table public.tabela_futura_sec (id serial primary key)')
            cur.execute("select has_table_privilege('anon', 'public.tabela_futura_sec', 'SELECT'), "
                        "has_table_privilege('authenticated', 'public.tabela_futura_sec', 'INSERT'), "
                        "has_sequence_privilege('anon', 'public.tabela_futura_sec_id_seq', 'USAGE')")
            assert cur.fetchone() == (False, False, False)
            cur.execute('drop table public.tabela_futura_sec')
    finally:
        conn.close()


def test_dono_continua_com_crud_completo(ambiente):
    conn = ambiente['cluster'].conectar(ambiente['papel'])
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute('select count(*) from public.usuario')
            cur.execute("insert into public.categoria (nome, cor, ativo, sistemica, bloquear_edicao, bloquear_exclusao) "
                        "values ('Teste dono SEC', '#000000', true, false, false, false) returning id")
            novo = cur.fetchone()[0]
            cur.execute("update public.categoria set descricao = 'x' where id = %s", (novo,))
            assert cur.rowcount == 1
            cur.execute('delete from public.categoria where id = %s', (novo,))
            assert cur.rowcount == 1
    finally:
        conn.rollback()
        conn.close()


def test_flask_real_funciona_apos_migration(ambiente):
    saida = _rodar(_SCRIPT_SMOKE_FLASK, ambiente['cluster'], ambiente['papel'])
    resultado = json.loads(saida.strip().splitlines()[-1].removeprefix('SMOKE '))
    assert resultado['login'] == 302
    assert resultado['lista'] == 200
    assert resultado['cria'] in (200, 201)
    assert resultado['criada_visivel'] is True


def test_papeis_da_api_bloqueados_no_banco(ambiente):
    conn = ambiente['cluster'].conectar()
    conn.autocommit = False
    try:
        for papel in ('anon', 'authenticated'):
            with conn.cursor() as cur:
                cur.execute(f'set local role {papel}')
                with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                    cur.execute('select id from public.usuario limit 1')
            conn.rollback()
    finally:
        conn.close()


def test_rest_anonimo_e_autenticado_bloqueados(ambiente):
    postgrest = ambiente['postgrest']
    if not postgrest:
        pytest.skip('POSTGREST_BIN nao definido')
    token = assinar_jwt(claims_usuario(USUARIO_A), SEGREDO_JWT)
    assert _rest(postgrest.url, '/usuario?select=id&limit=0') in (401, 403)
    assert _rest(postgrest.url, '/usuario?id=eq.-1', 'PATCH', corpo={'nome': 'x'}) in (401, 403)
    assert _rest(postgrest.url, '/usuario?id=eq.-1', 'DELETE') in (401, 403)
    assert _rest(postgrest.url, '/config_agregador?select=id&limit=0', token=token) in (401, 403)
    assert _rest(postgrest.url, '/categoria', 'POST', token=token, corpo={'nome': 'x'}) in (401, 403)


def test_migration_e_idempotente(ambiente):
    from sqlalchemy import create_engine
    migration = _carregar_migration()
    engine = create_engine(ambiente['cluster'].dsn(ambiente['papel']))
    try:
        with engine.begin() as conn:
            resumo = migration.aplicar_protecao(conn)
    finally:
        engine.dispose()
    assert resumo['aplicado'] is True
    assert resumo['habilitadas'] == []
    assert len(resumo['ja_tinham']) >= 50


def test_tabela_de_outro_dono_nao_recebe_rls(ambiente):
    from sqlalchemy import create_engine
    cluster = ambiente['cluster']
    conn = cluster.conectar()
    try:
        with conn.cursor() as cur:
            cur.execute('create table public.tabela_de_outro_dono (id int)')
    finally:
        conn.close()
    engine = create_engine(cluster.dsn(ambiente['papel']))
    try:
        with engine.begin() as c:
            resumo = _carregar_migration().aplicar_protecao(c)
    finally:
        engine.dispose()
    assert 'tabela_de_outro_dono' in resumo['ignoradas']
    conn = cluster.conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("select relrowsecurity from pg_class where oid = 'public.tabela_de_outro_dono'::regclass")
            assert cur.fetchone()[0] is False
            cur.execute('drop table public.tabela_de_outro_dono')
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fora do Supabase a migration nao faz nada (banco local de desenvolvimento)
# ---------------------------------------------------------------------------

def test_noop_em_sqlite():
    from sqlalchemy import create_engine
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        assert _carregar_migration().aplicar_protecao(conn)['aplicado'] is False


def test_noop_em_postgres_sem_papeis_do_supabase(tmp_path):
    from sqlalchemy import create_engine
    with ClusterLocal(PG_BIN, tmp_path) as cluster:
        conn = cluster.conectar()
        try:
            with conn.cursor() as cur:
                cur.execute('create table public.local_dev (id int)')
        finally:
            conn.close()
        engine = create_engine(cluster.dsn())
        try:
            with engine.begin() as c:
                resumo = _carregar_migration().aplicar_protecao(c)
        finally:
            engine.dispose()
        assert resumo == {'aplicado': False, 'motivo': 'sem papeis da Data API (nao e Supabase)'}
        conn = cluster.conectar()
        try:
            with conn.cursor() as cur:
                cur.execute("select relrowsecurity from pg_class where oid = 'public.local_dev'::regclass")
                assert cur.fetchone()[0] is False
        finally:
            conn.close()
