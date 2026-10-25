"""
Testes FIN-MIGRACAO-FIDELIDADE-FASE-1 — gestao de perfis financeiros (Configuracoes do novo aplicativo).

Cluster PostgreSQL descartavel com dados FICTICIOS (tests/supabase_local.py):
- A: Pessoal (TITULAR, gere, padrao), Empresa (LEITOR), "Perfil inativo (A)" (TITULAR, gere);
- B: Perfil B (TITULAR, gere).
Cada teste roda numa transacao desfeita ao final. Camada de banco como o PostgREST (SET ROLE + claims);
camada REST por /rpc com JWT.
"""
import json
import secrets
import urllib.error
import urllib.request
import uuid

import pytest

from tests.supabase_local import (
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
PUBLICAS = ['financeiro.perfis_para_configuracao()', 'financeiro.criar_perfil(jsonb)',
            'financeiro.atualizar_perfil(integer, jsonb)', 'financeiro.inativar_perfil(integer)',
            'financeiro.reativar_perfil(integer)', 'financeiro.definir_perfil_padrao(integer)']
INTERNAS = ['financeiro.gere_perfil(integer)', 'financeiro.perfil_em_json(integer)',
            'financeiro.normalizar_dados_perfil(jsonb, text)', 'financeiro.aplicar_perfil_padrao(integer)']


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    with ClusterLocal(PG_BIN, tmp_path_factory.mktemp('perfis_gestao')) as c:
        c.preparar()
        yield c


@pytest.fixture()
def conn(cluster):
    c = cluster.conectar()
    c.autocommit = False
    yield c
    c.rollback()
    c.close()


def _como(conn, usuario):
    cur = conn.cursor()
    cur.execute('reset role')
    if usuario == 'anon':
        cur.execute('set local role anon')
        cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({'role': 'anon'}),))
    else:
        cur.execute('set local role authenticated')
        cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims_usuario(usuario)),))
    return cur


def _chamar(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def _falha(cur, sql, params=()):
    """Executa esperando erro, sem perder a transacao do teste. Devolve (sqlstate, mensagem)."""
    cur.execute('savepoint tentativa')
    try:
        cur.execute(sql, params)
    except psycopg2.Error as exc:
        cur.execute('rollback to savepoint tentativa')
        return exc.pgcode, exc.diag.message_primary
    raise AssertionError(f'deveria falhar: {sql}')


def _criar(cur, dados):
    return _chamar(cur, 'select financeiro.criar_perfil(%s::jsonb)', (json.dumps(dados),))


def _linha(conn, perfil_id):
    cur = conn.cursor()
    cur.execute('reset role')
    cur.execute('select nome, tipo, documento, avatar, cor, ativo, padrao from public.perfil_financeiro where id = %s',
                (perfil_id,))
    return cur.fetchone()


# ---------------------------------------------------------------------------
# Estrutura e permissoes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('funcao', PUBLICAS)
def test_funcoes_publicas_seguras(conn, funcao):
    cur = conn.cursor()
    cur.execute(f"""select p.prosecdef, coalesce(array_to_string(p.proconfig, ','), ''),
                           has_function_privilege('anon', '{funcao}', 'EXECUTE'),
                           has_function_privilege('authenticated', '{funcao}', 'EXECUTE')
                      from pg_proc p where p.oid = '{funcao}'::regprocedure""")
    definer, config, anon, autenticado = cur.fetchone()
    assert definer is True and 'search_path=""' in config
    assert anon is False and autenticado is True


@pytest.mark.parametrize('funcao', INTERNAS)
def test_funcoes_internas_sem_execute(conn, funcao):
    cur = conn.cursor()
    cur.execute(f"""select has_function_privilege('anon', '{funcao}', 'EXECUTE'),
                           has_function_privilege('authenticated', '{funcao}', 'EXECUTE'),
                           coalesce(array_to_string(p.proconfig, ','), '')
                      from pg_proc p where p.oid = '{funcao}'::regprocedure""")
    anon, autenticado, config = cur.fetchone()
    assert anon is False and autenticado is False and 'search_path=""' in config


def test_nenhuma_tabela_nova(conn):
    cur = conn.cursor()
    cur.execute("select count(*) from information_schema.tables where table_schema = 'financeiro' and table_name like '%perfil%'")
    assert cur.fetchone()[0] == 1  # so perfil_acesso


@pytest.mark.parametrize('sql', [
    'select * from financeiro.perfis_para_configuracao()',
    """select financeiro.criar_perfil('{"nome": "Intruso"}'::jsonb)""",
    f"""select financeiro.atualizar_perfil({ID['PESSOAL']}, '{{"tipo": "OUTRO"}}'::jsonb)""",
    f"select financeiro.inativar_perfil({ID['PESSOAL']})",
    f"select financeiro.reativar_perfil({ID['INATIVO_A']})",
    f"select financeiro.definir_perfil_padrao({ID['EMPRESA']})",
])
def test_anon_nao_gere_perfis(conn, sql):
    cur = _como(conn, 'anon')
    with pytest.raises(errors.InsufficientPrivilege):
        cur.execute(sql)


# ---------------------------------------------------------------------------
# Leitura para Configuracoes
# ---------------------------------------------------------------------------

def test_configuracao_lista_os_proprios_inclusive_inativos(conn):
    cur = _como(conn, USUARIO_A)
    cur.execute('select nome, ativo, papel, pode_gerir from financeiro.perfis_para_configuracao()')
    assert cur.fetchall() == [('Empresa', True, 'LEITOR', False), ('Pessoal', True, 'TITULAR', True),
                              ('Perfil inativo (A)', False, 'TITULAR', True)]
    cur = _como(conn, USUARIO_B)
    cur.execute('select nome from financeiro.perfis_para_configuracao()')
    assert cur.fetchall() == [('Perfil B',)]


# ---------------------------------------------------------------------------
# Criar
# ---------------------------------------------------------------------------

def test_criar_perfil_com_regras_do_flask_e_vinculo_so_do_criador(conn):
    cur = _como(conn, USUARIO_A)
    perfil = _criar(cur, {'nome': '  Trabalho Teste  ', 'tipo': 'empresa', 'documento': ' 12.345.678/0001-90 ',
                          'avatar': '', 'cor': '0f766e'})
    assert perfil['nome'] == 'Trabalho Teste' and perfil['tipo'] == 'EMPRESA'
    assert perfil['documento'] == '12.345.678/0001-90' and perfil['avatar'] == 'TT' and perfil['cor'] == '#0f766e'
    assert perfil['ativo'] is True and perfil['padrao'] is False
    cur.execute('select nome from financeiro.meus_perfis()')
    assert ('Trabalho Teste',) in cur.fetchall()
    cur.execute('select papel, pode_gerir from financeiro.perfil_acesso where perfil_financeiro_id = %s', (perfil['id'],))
    assert cur.fetchall() == [('TITULAR', True)]  # so o criador; RLS mostra so os proprios
    cur.execute('reset role')
    cur.execute('select count(*) from financeiro.perfil_acesso where perfil_financeiro_id = %s', (perfil['id'],))
    assert cur.fetchone()[0] == 1
    cur = _como(conn, USUARIO_B)
    cur.execute('select count(*) from financeiro.meus_perfis() where id = %s', (perfil['id'],))
    assert cur.fetchone()[0] == 0
    assert _falha(cur, 'select financeiro.atualizar_perfil(%s, %s::jsonb)',
                  (perfil['id'], '{"nome": "Tomado"}'))[0] == '42501'


def test_criar_normaliza_tipo_cor_e_apelido(conn):
    cur = _como(conn, USUARIO_A)
    perfil = _criar(cur, {'nome': 'Associacao', 'tipo': 'xyz', 'cor': '#zzzzzz'})
    assert (perfil['tipo'], perfil['cor'], perfil['avatar']) == ('OUTRO', '#2563eb', 'ASS')
    perfil = _criar(cur, {'nome': 'Outro Perfil', 'tipo': 'PESSOAL', 'avatar': 'meu apelido'})
    assert perfil['avatar'] == 'MA'


@pytest.mark.parametrize('dados, mensagem', [
    ({'nome': '   '}, 'Nome do perfil financeiro e obrigatorio'),
    ({'nome': 'x' * 121}, 'Nome do perfil financeiro deve ter ate 120 caracteres'),
    ({'nome': 'Empresa'}, 'Ja existe perfil financeiro com este nome'),
    ({'nome': 'Perfil B'}, 'Ja existe perfil financeiro com este nome'),
    ({'nome': 'Pessoal'}, 'O nome Pessoal e reservado ao perfil que guarda os registros sem perfil'),
])
def test_criar_recusa_nome_invalido(conn, dados, mensagem):
    cur = _como(conn, USUARIO_A)
    assert _falha(cur, 'select financeiro.criar_perfil(%s::jsonb)', (json.dumps(dados),))[1] == mensagem


def test_perfil_novo_nao_ve_registros_sem_perfil(conn):
    cur = _como(conn, USUARIO_A)
    perfil = _criar(cur, {'nome': 'Novo sem legado', 'tipo': 'PESSOAL'})
    cur.execute('select count(*) from financeiro.contas_bancarias_do_perfil(%s)', (perfil['id'],))
    assert cur.fetchone()[0] == 0  # a "Carteira legado sem perfil" continua so no Pessoal


def test_criar_como_padrao_transfere_o_padrao_do_proprio_usuario(conn):
    cur = _como(conn, USUARIO_A)
    perfil = _criar(cur, {'nome': 'Novo padrao', 'tipo': 'PESSOAL', 'padrao': True})
    assert perfil['padrao'] is True
    assert _linha(conn, ID['PESSOAL'])[6] is False


def test_padrao_de_outro_titular_nunca_e_alterado(conn):
    cur = _como(conn, USUARIO_B)
    estado, mensagem = _falha(cur, 'select financeiro.criar_perfil(%s::jsonb)',
                              (json.dumps({'nome': 'B quer padrao', 'padrao': True}),))
    assert (estado, mensagem) == ('42501', 'O perfil padrao atual e gerido por outro titular')
    assert _linha(conn, ID['PESSOAL'])[6] is True
    cur = conn.cursor()
    cur.execute("select count(*) from public.perfil_financeiro where nome = 'B quer padrao'")
    assert cur.fetchone()[0] == 0  # tudo desfeito
    cur = _como(conn, USUARIO_B)
    assert _falha(cur, 'select financeiro.definir_perfil_padrao(%s)', (ID['PERFIL_B'],))[0] == '42501'


# ---------------------------------------------------------------------------
# Editar
# ---------------------------------------------------------------------------

def test_editar_atualiza_so_as_chaves_enviadas(conn):
    cur = _como(conn, USUARIO_A)
    perfil = _chamar(cur, 'select financeiro.atualizar_perfil(%s, %s::jsonb)',
                     (ID['PESSOAL'], json.dumps({'documento': '123.456.789-00', 'cor': '#111827', 'avatar': 'eu'})))
    assert perfil['nome'] == 'Pessoal' and perfil['tipo'] == 'PESSOAL'
    assert (perfil['documento'], perfil['cor'], perfil['avatar']) == ('123.456.789-00', '#111827', 'EU')
    perfil = _chamar(cur, 'select financeiro.atualizar_perfil(%s, %s::jsonb)',
                     (ID['PESSOAL'], json.dumps({'nome': 'Pessoal', 'documento': ''})))
    assert perfil['documento'] is None and perfil['cor'] == '#111827'


def test_editar_nome_e_tipo_de_perfil_gerido(conn):
    cur = _como(conn, USUARIO_A)
    perfil = _chamar(cur, 'select financeiro.atualizar_perfil(%s, %s::jsonb)',
                     (ID['INATIVO_A'], json.dumps({'nome': 'Consultoria', 'tipo': 'EMPRESA'})))
    assert (perfil['nome'], perfil['tipo'], perfil['ativo']) == ('Consultoria', 'EMPRESA', False)


@pytest.mark.parametrize('perfil, dados, mensagem', [
    ('PESSOAL', {'nome': 'Minhas contas'}, 'O perfil Pessoal nao pode ser renomeado: ele guarda os registros sem perfil'),
    ('INATIVO_A', {'nome': 'Pessoal'}, 'O nome Pessoal e reservado ao perfil que guarda os registros sem perfil'),
    ('INATIVO_A', {'nome': 'Perfil B'}, 'Ja existe perfil financeiro com este nome'),
    ('INATIVO_A', {'nome': ''}, 'Nome do perfil financeiro e obrigatorio'),
])
def test_editar_recusa_nome_invalido(conn, perfil, dados, mensagem):
    cur = _como(conn, USUARIO_A)
    assert _falha(cur, 'select financeiro.atualizar_perfil(%s, %s::jsonb)', (ID[perfil], json.dumps(dados)))[1] == mensagem


@pytest.mark.parametrize('usuario, perfil', [(USUARIO_A, 'EMPRESA'), (USUARIO_A, 'PERFIL_B'),
                                             (USUARIO_B, 'PESSOAL'), (USUARIO_B, 'INATIVO_A')])
def test_sem_gestao_nada_e_alterado(conn, usuario, perfil):
    antes = _linha(conn, ID[perfil])
    cur = _como(conn, usuario)
    for sql, params in (('select financeiro.atualizar_perfil(%s, %s::jsonb)', (ID[perfil], '{"tipo": "OUTRO"}')),
                        ('select financeiro.inativar_perfil(%s)', (ID[perfil],)),
                        ('select financeiro.reativar_perfil(%s)', (ID[perfil],)),
                        ('select financeiro.definir_perfil_padrao(%s)', (ID[perfil],))):
        assert _falha(cur, sql, params) == ('42501', 'Perfil financeiro nao autorizado')
    assert _linha(conn, ID[perfil]) == antes


# ---------------------------------------------------------------------------
# Ativar, inativar e padrao
# ---------------------------------------------------------------------------

def test_nao_inativa_o_unico_perfil_ativo(conn):
    cur = _como(conn, USUARIO_B)
    assert _falha(cur, 'select financeiro.inativar_perfil(%s)', (ID['PERFIL_B'],))[1] == \
        'Nao e possivel inativar o unico perfil ativo'


def test_inativar_padrao_exige_outro_perfil_gerido(conn):
    cur = _como(conn, USUARIO_A)  # Empresa esta ativa, mas A so le: nao pode virar padrao
    assert _falha(cur, 'select financeiro.inativar_perfil(%s)', (ID['PESSOAL'],))[1] == \
        'Defina outro perfil padrao antes de inativar este'
    novo = _criar(cur, {'nome': 'Reserva', 'tipo': 'PESSOAL'})
    perfil = _chamar(cur, 'select financeiro.inativar_perfil(%s)', (ID['PESSOAL'],))
    assert (perfil['ativo'], perfil['padrao']) == (False, False)
    assert _linha(conn, novo['id'])[5:] == (True, True)
    cur = _como(conn, USUARIO_A)
    cur.execute('select nome from financeiro.meus_perfis()')
    assert cur.fetchall() == [('Reserva',), ('Empresa',)]  # inativo sai do seletor


def test_reativar_e_padrao(conn):
    cur = _como(conn, USUARIO_A)
    perfil = _chamar(cur, 'select financeiro.reativar_perfil(%s)', (ID['INATIVO_A'],))
    assert (perfil['ativo'], perfil['padrao']) == (True, False)  # ja ha padrao ativo
    perfil = _chamar(cur, 'select financeiro.definir_perfil_padrao(%s)', (ID['INATIVO_A'],))
    assert perfil['padrao'] is True and _linha(conn, ID['PESSOAL'])[6] is False
    cur = conn.cursor()
    cur.execute('reset role')
    cur.execute('select count(*) from public.perfil_financeiro where padrao')
    assert cur.fetchone()[0] == 1


def test_reativar_sem_padrao_ativo_vira_padrao(conn):
    cur = conn.cursor()
    cur.execute('update public.perfil_financeiro set padrao = false')
    cur = _como(conn, USUARIO_A)
    assert _chamar(cur, 'select financeiro.reativar_perfil(%s)', (ID['INATIVO_A'],))['padrao'] is True


def test_padrao_so_em_perfil_ativo(conn):
    cur = _como(conn, USUARIO_A)
    assert _falha(cur, 'select financeiro.definir_perfil_padrao(%s)', (ID['INATIVO_A'],))[1] == \
        'Perfil financeiro ativo nao encontrado'


def test_operacoes_de_a_nao_mudam_o_perfil_de_b(conn):
    antes = _linha(conn, ID['PERFIL_B'])
    cur = _como(conn, USUARIO_A)
    novo = _criar(cur, {'nome': 'Fluxo completo', 'tipo': 'EMPRESA', 'padrao': True})
    _chamar(cur, 'select financeiro.atualizar_perfil(%s, %s::jsonb)', (novo['id'], '{"cor": "#be123c"}'))
    _chamar(cur, 'select financeiro.definir_perfil_padrao(%s)', (ID['PESSOAL'],))
    _chamar(cur, 'select financeiro.inativar_perfil(%s)', (novo['id'],))
    _chamar(cur, 'select financeiro.reativar_perfil(%s)', (novo['id'],))
    assert _linha(conn, ID['PERFIL_B']) == antes


# ---------------------------------------------------------------------------
# FIN-MIGRACAO-FIDELIDADE-FASE-1-REAL: gerador de recorrencias do perfil novo
# ---------------------------------------------------------------------------

def _geradores(conn):
    cur = conn.cursor()
    cur.execute('reset role')
    cur.execute('select perfil_financeiro_id, gerador, alterado_por, motivo from financeiro.gerador_recorrencia order by 1')
    return cur.fetchall()


def test_perfil_novo_nasce_no_novo_aplicativo_e_os_existentes_nao_mudam(conn):
    antes = _geradores(conn)
    cur = _como(conn, USUARIO_A)
    perfil = _criar(cur, {'nome': 'Novo no app', 'tipo': 'EMPRESA'})
    depois = _geradores(conn)
    assert [g for g in depois if g[0] != perfil['id']] == antes  # perfis existentes intactos
    assert [g[:2] for g in depois if g[0] == perfil['id']] == [(perfil['id'], 'NOVO')]
    cur = conn.cursor()
    cur.execute('select financeiro.gerador_do_perfil(%s)', (perfil['id'],))
    assert cur.fetchone()[0] == 'NOVO'
    cur.execute('select gerador_anterior, gerador_novo, alterado_por, motivo from financeiro.gerador_recorrencia_historico '
                'where perfil_financeiro_id = %s', (perfil['id'],))
    assert cur.fetchall() == [(None, 'NOVO', f"criar_perfil (usuario {USUARIO_A['id']})", 'Perfil criado pelo novo aplicativo')]
    cur = _como(conn, USUARIO_A)  # o criador administra o perfil novo
    cur.execute('select financeiro.pode_gerir_perfil(%s)', (perfil['id'],))
    assert cur.fetchone()[0] is True


def test_falha_na_atribuicao_desfaz_a_criacao_do_perfil(conn):
    cur = conn.cursor()
    cur.execute("""create function pg_temp.falhar() returns trigger language plpgsql as $$
                   begin raise exception 'falha simulada na atribuicao'; end $$""")
    cur.execute('create trigger falha_simulada before insert on financeiro.gerador_recorrencia '
                'for each row execute function pg_temp.falhar()')
    cur = _como(conn, USUARIO_A)
    assert _falha(cur, 'select financeiro.criar_perfil(%s::jsonb)', (json.dumps({'nome': 'Sem atribuicao'}),))[1] == \
        'falha simulada na atribuicao'
    cur = conn.cursor()
    cur.execute('reset role')
    cur.execute("select count(*) from public.perfil_financeiro where nome = 'Sem atribuicao'")
    assert cur.fetchone()[0] == 0
    cur.execute("""select count(*) from financeiro.perfil_acesso a
                    where not exists (select 1 from public.perfil_financeiro p where p.id = a.perfil_financeiro_id)""")
    assert cur.fetchone()[0] == 0


def test_geracao_de_recorrencias_funciona_no_perfil_novo(conn):
    cur = conn.cursor()
    cur.execute('select min(id) from public.categoria where ativo')
    categoria = cur.fetchone()[0]
    cur = _como(conn, USUARIO_A)
    perfil = _criar(cur, {'nome': 'Gera no app', 'tipo': 'PESSOAL'})
    cur.execute('select financeiro.criar_despesa(%s, %s::jsonb, %s)',
                (perfil['id'], json.dumps({'nome': 'Assinatura (e2e)', 'valor': '49.90', 'categoria_id': categoria,
                                           'data_vencimento': '2029-05-10', 'recorrente': True}), str(uuid.uuid4())))
    cur.execute('select financeiro.previa_geracao(%s, %s)', (perfil['id'], '2029-06-01'))
    previa = cur.fetchone()[0]
    assert previa['pode_gerar'] is True and previa['a_gerar'] >= 1
    cur.execute('select financeiro.gerar_mes(%s, %s, %s, %s::jsonb)', (perfil['id'], '2029-06-01', previa['a_gerar'], '[]'))
    cur.execute("select count(*) from financeiro.contas_do_mes(%s, %s) where nome like 'Assinatura (e2e)%%'",
                (perfil['id'], '2029-06-01'))
    assert cur.fetchone()[0] == 1
    cur = _como(conn, USUARIO_B)  # outro usuario nao ve o perfil novo
    assert _falha(cur, 'select * from financeiro.contas_do_mes(%s, %s)', (perfil['id'], '2029-06-01'))[0] == '42501'


# ---------------------------------------------------------------------------
# Camada REST (como o supabase-js chama)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def rest(cluster, tmp_path_factory):
    if POSTGREST_BIN is None:
        pytest.skip('POSTGREST_BIN nao definido')
    with PostgrestLocal(POSTGREST_BIN, cluster, SEGREDO_JWT, tmp_path_factory.mktemp('postgrest_perfis_gestao')) as p:
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


def test_rest_gestao_de_perfis(rest, cluster):
    assert _rpc(rest, 'perfis_para_configuracao')[0] in (401, 403)
    assert _rpc(rest, 'criar_perfil', {'p_dados': {'nome': 'Anonimo'}})[0] in (401, 403)
    status, corpo = _rpc(rest, 'perfis_para_configuracao', usuario=USUARIO_B)
    assert status == 200 and [p['nome'] for p in corpo] == ['Perfil B']
    status, corpo = _rpc(rest, 'atualizar_perfil', {'p_perfil_id': ID['PESSOAL'], 'p_dados': {'tipo': 'OUTRO'}}, USUARIO_B)
    assert status == 403 and corpo['message'] == 'Perfil financeiro nao autorizado'
    status, corpo = _rpc(rest, 'criar_perfil', {'p_dados': {'nome': 'Rest temporario', 'tipo': 'EMPRESA'}}, USUARIO_B)
    try:
        assert status == 200 and corpo['nome'] == 'Rest temporario' and corpo['padrao'] is False
        status, duplicado = _rpc(rest, 'criar_perfil', {'p_dados': {'nome': 'Rest temporario'}}, USUARIO_B)
        assert status == 409 and duplicado['message'] == 'Ja existe perfil financeiro com este nome'
    finally:  # o cluster e do modulo: remove o perfil criado por este teste
        conn = cluster.conectar()
        try:
            with conn.cursor() as cur:
                cur.execute("delete from public.perfil_financeiro where nome = 'Rest temporario'")
            conn.commit()
        finally:
            conn.close()
