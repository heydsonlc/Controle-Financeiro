"""
Testes PERFIS-1 — identidade (Auth) <-> perfil financeiro <-> dados.

Cluster PostgreSQL descartavel com as tabelas do Flask (protegidas como no
staging), as migrations de supabase/ e dados FICTICIOS (tests/supabase_local.py):
- A: Pessoal (TITULAR), Empresa (LEITOR), um perfil inativo;
- B: Perfil B.
Camada de banco: como o PostgREST faz (SET ROLE + claims). Camada REST: /rpc com JWT.
"""
import json
import secrets
import urllib.error
import urllib.request

import pytest

from tests.supabase_local import (
    CONTAS_ESPERADAS,
    PERFIS,
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
POSTGREST_BIN = encontrar_postgrest()
SEGREDO_JWT = secrets.token_urlsafe(48)
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

ID = {chave: perfil['id'] for chave, perfil in PERFIS.items()}


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    with ClusterLocal(PG_BIN, tmp_path_factory.mktemp('perfis')) as c:
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
    cur = conn.cursor()
    cur.execute('set local role %s' % role)
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims or {'role': role}),))
    return cur


def _perfis(cur):
    cur.execute('select nome from financeiro.meus_perfis()')
    return [linha[0] for linha in cur.fetchall()]


def _contas(cur, perfil_id):
    cur.execute('select nome from financeiro.contas_bancarias_do_perfil(%s)', (perfil_id,))
    return sorted(linha[0] for linha in cur.fetchall())


# ---------------------------------------------------------------------------
# Estrutura
# ---------------------------------------------------------------------------

def test_perfil_acesso_com_rls_forcada_e_somente_leitura(conn):
    cur = conn.cursor()
    cur.execute("select relrowsecurity, relforcerowsecurity from pg_class where oid = 'financeiro.perfil_acesso'::regclass")
    assert cur.fetchone() == (True, True)
    cur.execute("""select grantee, privilege_type from information_schema.role_table_grants
                    where table_schema = 'financeiro' and table_name = 'perfil_acesso'
                      and grantee in ('anon', 'authenticated', 'PUBLIC')""")
    assert cur.fetchall() == [('authenticated', 'SELECT')]


@pytest.mark.parametrize('funcao', [
    'financeiro.meus_perfis()',
    'financeiro.pode_acessar_perfil(integer)',
    'financeiro.contas_bancarias_do_perfil(integer)',
])
def test_funcoes_seguras(conn, funcao):
    cur = conn.cursor()
    cur.execute(f"""select p.prosecdef, coalesce(array_to_string(p.proconfig, ','), ''),
                           has_function_privilege('anon', '{funcao}', 'EXECUTE'),
                           has_function_privilege('authenticated', '{funcao}', 'EXECUTE')
                      from pg_proc p where p.oid = '{funcao}'::regprocedure""")
    definer, config, anon, autenticado = cur.fetchone()
    assert definer is True
    assert 'search_path=""' in config
    assert anon is False and autenticado is True


def test_nada_foi_vinculado_automaticamente(conn):
    cur = conn.cursor()
    cur.execute('select count(*) from financeiro.perfil_acesso')
    assert cur.fetchone()[0] == 4  # exatamente os vinculos semeados


# ---------------------------------------------------------------------------
# Sem login
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('sql', [
    'select * from financeiro.meus_perfis()',
    f"select * from financeiro.contas_bancarias_do_perfil({PERFIS['PESSOAL']['id']})",
    'select * from financeiro.perfil_acesso',
])
def test_anon_nao_acessa_perfis(conn, sql):
    cur = _como(conn, 'anon')
    with pytest.raises(errors.InsufficientPrivilege):
        cur.execute(sql)


# ---------------------------------------------------------------------------
# Perfis autorizados
# ---------------------------------------------------------------------------

def test_usuario_a_ve_seus_perfis_ativos(conn):
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_A))
    assert _perfis(cur) == ['Pessoal', 'Empresa']  # padrao primeiro; inativo fora


def test_usuario_b_ve_somente_o_proprio(conn):
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_B))
    assert _perfis(cur) == ['Perfil B']


def test_usuario_sem_vinculo_nao_ve_perfil(conn):
    cur = _como(conn, 'authenticated', claims_usuario({'id': '00000000-0000-4000-8000-000000000000', 'email': 'x'}))
    assert _perfis(cur) == []


def test_vinculos_visiveis_somente_os_proprios(conn):
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_A))
    cur.execute('select distinct user_id::text from financeiro.perfil_acesso')
    assert cur.fetchall() == [(USUARIO_A['id'],)]


@pytest.mark.parametrize('chave,esperado', [
    ('PESSOAL', True), ('EMPRESA', True), ('PERFIL_B', False), ('INATIVO_A', False),
])
def test_pode_acessar_perfil_do_usuario_a(conn, chave, esperado):
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_A))
    cur.execute('select financeiro.pode_acessar_perfil(%s)', (ID[chave],))
    assert cur.fetchone()[0] is esperado


@pytest.mark.parametrize('valor', [None, 999999, -1])
def test_pode_acessar_perfil_inexistente_ou_nulo(conn, valor):
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_A))
    cur.execute('select financeiro.pode_acessar_perfil(%s)', (valor,))
    assert cur.fetchone()[0] is False


# ---------------------------------------------------------------------------
# Isolamento entre perfis (dados legados via fachada)
# ---------------------------------------------------------------------------

def test_a_alterna_entre_os_proprios_perfis(conn):
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_A))
    assert _contas(cur, ID['PESSOAL']) == CONTAS_ESPERADAS['PESSOAL']  # inclui legado sem perfil
    assert _contas(cur, ID['EMPRESA']) == CONTAS_ESPERADAS['EMPRESA']


def test_b_ve_somente_as_contas_do_proprio_perfil(conn):
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_B))
    assert _contas(cur, ID['PERFIL_B']) == CONTAS_ESPERADAS['PERFIL_B']


@pytest.mark.parametrize('usuario,chave', [
    (USUARIO_A, 'PERFIL_B'),   # perfil de outro usuario
    (USUARIO_A, 'INATIVO_A'),  # perfil proprio, mas inativo
    (USUARIO_B, 'PESSOAL'),    # B tentando o Pessoal (e o legado sem perfil)
    (USUARIO_B, 'EMPRESA'),
])
def test_identificador_de_perfil_indevido_e_recusado(conn, usuario, chave):
    cur = _como(conn, 'authenticated', claims_usuario(usuario))
    with pytest.raises(errors.InsufficientPrivilege):
        _contas(cur, ID[chave])


def test_tabelas_legadas_seguem_inacessiveis_diretamente(conn):
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_A))
    for tabela in ('public.conta_bancaria', 'public.perfil_financeiro'):
        with pytest.raises(errors.InsufficientPrivilege):
            cur.execute(f'select * from {tabela}')
        conn.rollback()
        cur = _como(conn, 'authenticated', claims_usuario(USUARIO_A))


@pytest.mark.parametrize('sql', [
    "insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id) values ('{a}', {b})",
    "update financeiro.perfil_acesso set perfil_financeiro_id = {b} where user_id = '{a}'",
    "delete from financeiro.perfil_acesso where user_id = '{a}'",
])
def test_usuario_nao_concede_acesso_a_si_mesmo(conn, sql):
    cur = _como(conn, 'authenticated', claims_usuario(USUARIO_A))
    with pytest.raises(errors.InsufficientPrivilege):
        cur.execute(sql.format(a=USUARIO_A['id'], b=ID['PERFIL_B']))


# ---------------------------------------------------------------------------
# Camada REST (PostgREST, como o supabase-js chama as funcoes)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def rest(cluster, tmp_path_factory):
    if POSTGREST_BIN is None:
        pytest.skip('POSTGREST_BIN nao definido')
    with PostgrestLocal(POSTGREST_BIN, cluster, SEGREDO_JWT, tmp_path_factory.mktemp('postgrest_perfis')) as p:
        yield p


def _rpc(rest, funcao, corpo=None, usuario=None):
    req = urllib.request.Request(f'{rest.url}/rpc/{funcao}', method='POST', data=json.dumps(corpo or {}).encode())
    req.add_header('Content-Type', 'application/json')
    req.add_header('Content-Profile', 'financeiro')
    if usuario:
        req.add_header('Authorization', f'Bearer {assinar_jwt(claims_usuario(usuario), SEGREDO_JWT)}')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b'null')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'null')


def test_rest_anonimo_nao_lista_perfis(rest):
    status, corpo = _rpc(rest, 'meus_perfis')
    assert status in (401, 403) and not isinstance(corpo, list)


def test_rest_meus_perfis_por_usuario(rest):
    assert [p['nome'] for p in _rpc(rest, 'meus_perfis', usuario=USUARIO_A)[1]] == ['Pessoal', 'Empresa']
    assert [p['nome'] for p in _rpc(rest, 'meus_perfis', usuario=USUARIO_B)[1]] == ['Perfil B']


def test_rest_contas_do_perfil_autorizado(rest):
    status, corpo = _rpc(rest, 'contas_bancarias_do_perfil', {'p_perfil_id': ID['EMPRESA']}, USUARIO_A)
    assert status == 200 and [c['nome'] for c in corpo] == CONTAS_ESPERADAS['EMPRESA']
    assert set(corpo[0]) == {'id', 'nome', 'instituicao', 'tipo', 'cor', 'status'}  # sem agencia/numero/saldo


def test_rest_perfil_de_outro_usuario_recusado(rest):
    status, corpo = _rpc(rest, 'contas_bancarias_do_perfil', {'p_perfil_id': ID['PERFIL_B']}, USUARIO_A)
    assert status == 403
    assert not isinstance(corpo, list)


def test_rest_tabelas_legadas_e_vinculos_sem_escrita(rest):
    token = assinar_jwt(claims_usuario(USUARIO_A), SEGREDO_JWT)
    req = urllib.request.Request(f'{rest.url}/perfil_acesso', method='POST',
                                 data=json.dumps({'user_id': USUARIO_A['id'], 'perfil_financeiro_id': ID['PERFIL_B']}).encode())
    for nome, valor in (('Content-Type', 'application/json'), ('Content-Profile', 'financeiro'),
                        ('Authorization', f'Bearer {token}')):
        req.add_header(nome, valor)
    try:
        status = urllib.request.urlopen(req, timeout=10).status
    except urllib.error.HTTPError as exc:
        status = exc.code
    assert status in (401, 403)
