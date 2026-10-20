"""
Testes CF-SUPABASE-REFACTOR-1 — controle de acesso das categorias na nova arquitetura.

Rodam num cluster PostgreSQL descartavel (tests/supabase_local.py), nunca no banco
local de desenvolvimento nem no Supabase remoto. Pulam se nao houver binarios do
PostgreSQL. A parte REST pula se POSTGREST_BIN nao estiver definido.

Camada de banco: reproduz o que o PostgREST do Supabase faz a cada requisicao
(SET LOCAL ROLE + request.jwt.claims) e prova o comportamento das policies.
Camada REST: JWTs reais (HS256) contra o PostgREST, como o supabase-js faria.
"""
import json
import secrets
import time
import urllib.error
import urllib.request

import pytest

from tests.supabase_local import (
    CATEGORIAS_A,
    CATEGORIAS_B,
    USUARIO_A,
    USUARIO_B,
    ClusterLocal,
    PostgrestLocal,
    assinar_jwt,
    claims_usuario,
    encontrar_pg_bin,
    encontrar_postgrest,
)

psycopg2 = pytest.importorskip('psycopg2')
from psycopg2 import errors  # noqa: E402

PG_BIN = encontrar_pg_bin()
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    with ClusterLocal(PG_BIN, tmp_path_factory.mktemp('supabase_mvp')) as c:
        c.preparar()
        yield c


@pytest.fixture()
def conn(cluster):
    c = cluster.conectar()
    c.autocommit = False
    yield c
    c.rollback()
    c.close()


def _como(conn, role, claims=None):
    """Mesmo que o PostgREST faz por requisicao: troca de role + claims do JWT."""
    cur = conn.cursor()
    cur.execute('set local role %s' % role)
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims or {'role': role}),))
    return cur


def _nomes(cur):
    cur.execute('select nome from financeiro.categorias order by nome')
    return [linha[0] for linha in cur.fetchall()]


# ---------------------------------------------------------------------------
# Estrutura de seguranca da migration
# ---------------------------------------------------------------------------

def test_rls_habilitada_e_forcada(conn):
    cur = conn.cursor()
    cur.execute("select relrowsecurity, relforcerowsecurity from pg_class where oid = 'financeiro.categorias'::regclass")
    assert cur.fetchone() == (True, True)


def test_unica_policy_e_de_leitura_para_authenticated(conn):
    cur = conn.cursor()
    cur.execute("select policyname, cmd, roles from pg_policies where schemaname = 'financeiro' and tablename = 'categorias'")
    politicas = cur.fetchall()
    assert len(politicas) == 1
    nome, comando, roles = politicas[0]
    assert comando == 'SELECT'
    roles = roles if isinstance(roles, list) else str(roles).strip('{}').split(',')
    assert set(roles) == {'authenticated'}


def test_privilegios_de_tabela(conn):
    cur = conn.cursor()
    cur.execute("""
        select grantee, privilege_type from information_schema.role_table_grants
        where table_schema = 'financeiro' and table_name = 'categorias'
          and grantee in ('anon', 'authenticated', 'PUBLIC')
    """)
    assert sorted(cur.fetchall()) == [('authenticated', 'SELECT')]


def test_anon_sem_acesso_ao_schema(conn):
    cur = conn.cursor()
    cur.execute("select has_schema_privilege('anon', 'financeiro', 'USAGE'), has_schema_privilege('authenticated', 'financeiro', 'USAGE')")
    assert cur.fetchone() == (False, True)


def test_schema_financeiro_nao_herda_grants_padrao_do_public(conn):
    """No Supabase o public concede ALL a anon em tabelas novas; o schema novo nao."""
    cur = conn.cursor()
    cur.execute('create table financeiro.tabela_futura_teste (id int)')
    cur.execute("select has_table_privilege('anon', 'financeiro.tabela_futura_teste', 'SELECT'), "
                "has_table_privilege('authenticated', 'financeiro.tabela_futura_teste', 'SELECT')")
    assert cur.fetchone() == (False, False)


# ---------------------------------------------------------------------------
# Comportamento por papel (camada de banco)
# ---------------------------------------------------------------------------

def test_anon_nao_le_categorias(conn):
    cur = _como(conn, 'anon')
    with pytest.raises(errors.InsufficientPrivilege):
        cur.execute('select * from financeiro.categorias')


def test_authenticated_sem_sub_nao_ve_nada(conn):
    cur = _como(conn, 'authenticated', {'role': 'authenticated'})
    assert _nomes(cur) == []


def test_usuario_a_ve_somente_as_proprias(conn):
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_A))
    assert _nomes(cur) == sorted(CATEGORIAS_A)


def test_usuario_b_ve_somente_as_proprias(conn):
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_B))
    assert _nomes(cur) == sorted(CATEGORIAS_B)


def test_usuario_a_nao_le_categoria_de_b_nem_filtrando_por_id(conn):
    cur = conn.cursor()
    cur.execute('select id from financeiro.categorias where user_id = %s limit 1', (USUARIO_B['id'],))
    id_de_b = cur.fetchone()[0]
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_A))
    cur.execute('select count(*) from financeiro.categorias where id = %s', (id_de_b,))
    assert cur.fetchone()[0] == 0


def test_sub_inexistente_nao_ve_nada(conn):
    claims = claims_usuario({'id': '00000000-0000-4000-8000-000000000000', 'email': 'x@teste.local'})
    cur = _como(conn, 'authenticated', claims)
    assert _nomes(cur) == []


@pytest.mark.parametrize('comando', [
    "insert into financeiro.categorias (user_id, nome) values ('{a}', 'Nova')",
    "update financeiro.categorias set nome = 'Alterada' where user_id = '{a}'",
    "delete from financeiro.categorias where user_id = '{a}'",
])
def test_authenticated_nao_escreve_nem_nas_proprias(conn, comando):
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_A))
    with pytest.raises(errors.InsufficientPrivilege):
        cur.execute(comando.format(a=USUARIO_A['id']))


@pytest.mark.parametrize('comando', [
    "insert into financeiro.categorias (user_id, nome) values ('{a}', 'Nova')",
    "delete from financeiro.categorias",
])
def test_anon_nao_escreve(conn, comando):
    cur = _como(conn, 'anon')
    with pytest.raises(errors.InsufficientPrivilege):
        cur.execute(comando.format(a=USUARIO_A['id']))


# ---------------------------------------------------------------------------
# Camada REST (PostgREST, a mesma usada pela Data API do Supabase)
# ---------------------------------------------------------------------------

POSTGREST_BIN = encontrar_postgrest()
SEGREDO_JWT = secrets.token_urlsafe(48)


@pytest.fixture(scope='module')
def rest(cluster, tmp_path_factory):
    if POSTGREST_BIN is None:
        pytest.skip('POSTGREST_BIN nao definido')
    with PostgrestLocal(POSTGREST_BIN, cluster, SEGREDO_JWT, tmp_path_factory.mktemp('postgrest')) as p:
        yield p


def _req(rest, metodo='GET', caminho='/categorias?select=nome&order=nome', token=None, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(rest.url + caminho, method=metodo, data=dados)
    req.add_header('Accept-Profile', 'financeiro')
    req.add_header('Content-Profile', 'financeiro')
    if dados is not None:
        req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b'null')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'null')


def test_rest_sem_token_nao_le(rest):
    status, corpo = _req(rest)
    assert status in (401, 403)
    assert not isinstance(corpo, list)


def test_rest_usuario_a_recebe_somente_as_proprias(rest):
    status, corpo = _req(rest, token=assinar_jwt(claims_usuario(USUARIO_A), SEGREDO_JWT))
    assert status == 200
    assert [c['nome'] for c in corpo] == sorted(CATEGORIAS_A)


def test_rest_usuario_b_recebe_somente_as_proprias(rest):
    status, corpo = _req(rest, token=assinar_jwt(claims_usuario(USUARIO_B), SEGREDO_JWT))
    assert status == 200
    assert [c['nome'] for c in corpo] == sorted(CATEGORIAS_B)


def test_rest_filtro_por_user_id_alheio_nao_vaza(rest):
    token = assinar_jwt(claims_usuario(USUARIO_A), SEGREDO_JWT)
    status, corpo = _req(rest, caminho=f'/categorias?user_id=eq.{USUARIO_B["id"]}', token=token)
    assert status == 200 and corpo == []


def test_rest_token_assinado_com_outro_segredo_e_recusado(rest):
    token = assinar_jwt(claims_usuario(USUARIO_A), 'segredo-de-atacante-' + secrets.token_hex(16))
    status, corpo = _req(rest, token=token)
    assert status == 401
    assert not isinstance(corpo, list)


def test_rest_token_expirado_e_recusado(rest):
    claims = claims_usuario(USUARIO_A)
    claims['exp'] = int(time.time()) - 60
    status, _ = _req(rest, token=assinar_jwt(claims, SEGREDO_JWT))
    assert status == 401


def test_rest_token_com_role_service_role_forjado_e_recusado(rest):
    claims = claims_usuario(USUARIO_A)
    claims['role'] = 'service_role'
    status, _ = _req(rest, token=assinar_jwt(claims, 'segredo-de-atacante-' + secrets.token_hex(16)))
    assert status == 401


@pytest.mark.parametrize('metodo,caminho,corpo', [
    ('POST', '/categorias', {'nome': 'Injetada'}),
    ('PATCH', '/categorias?nome=eq.Moradia%20(A)', {'nome': 'Alterada'}),
    ('DELETE', '/categorias?nome=eq.Moradia%20(A)', None),
])
def test_rest_usuario_autenticado_nao_escreve(rest, cluster, metodo, caminho, corpo):
    token = assinar_jwt(claims_usuario(USUARIO_A), SEGREDO_JWT)
    status, _ = _req(rest, metodo=metodo, caminho=caminho, token=token, corpo=corpo)
    assert status in (401, 403)
    conn = cluster.conectar()
    try:
        with conn.cursor() as cur:
            cur.execute('select count(*) from financeiro.categorias where user_id = %s', (USUARIO_A['id'],))
            assert cur.fetchone()[0] == len(CATEGORIAS_A)
            cur.execute("select count(*) from financeiro.categorias where nome in ('Injetada', 'Alterada')")
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()
