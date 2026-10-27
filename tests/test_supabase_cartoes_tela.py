"""
Testes FIN-FIDELIDADE-CARTOES-1 — funcoes da tela original de Cartoes (migration 20261104090000).

Cenario FICTICIO do FIN-RECORRENCIA-1 (tests/supabase_local.py), copia por teste: Cartao Teste (910, Pessoal),
limites 981 (Streaming CC 961, R$ 500, ativo), 982 (Outros CC 962, R$ 300, inativo) e 983 (Legado CC 963, sem
perfil); categoria de despesa 952 -> 961; Cartao B (930, Perfil B). Chamadas como o navegador (authenticated).
"""
import uuid
from decimal import Decimal

import pytest

from tests.test_supabase_cartoes import (
    ASSINATURAS,
    CARTAO,
    CARTAO_B,
    MORADIA,
    comprar,
    edicao,
    fatura,
    pagar,
    parcelas,
    rpc,
    tabela,
)
from tests.test_supabase_recorrencia import (
    atribuir,
    ID,
    PG_BIN,
    USUARIO_A,
    USUARIO_B,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
DA_TELA = [
    'financeiro.cartoes_da_tela(integer)', 'financeiro.categorias_cartao_do_perfil(integer)',
    'financeiro.limites_do_cartao(integer, integer, date)', 'financeiro.fatura_por_categoria(integer, integer, date)',
    'financeiro.lancamentos_fatura_por_categoria(integer, integer, date, text)',
    'financeiro.vincular_limite_cartao(integer, integer, jsonb)',
    'financeiro.atualizar_limite_cartao(integer, integer, integer, jsonb)',
    'financeiro.desativar_limite_cartao(integer, integer, integer)',
    'financeiro.editar_lancamento_cartao(integer, integer, text, jsonb)',
    'financeiro.parcelamento_da_compra(integer, integer)',
    'financeiro.editar_parcelas_futuras(integer, integer, text, jsonb)',
    'financeiro.cancelar_parcelas_futuras(integer, integer, text)',
    'financeiro.criar_cartao(integer, jsonb, uuid)', 'financeiro.editar_cartao(integer, integer, text, jsonb)',
]
INTERNAS = [
    'financeiro.ler_dados_cartao(jsonb, boolean)', 'financeiro.gasto_categoria_fatura(integer, integer, integer, date)',
    'financeiro.status_consumo(numeric, numeric)', 'financeiro.ler_limite_mensal(text)',
    'financeiro.travar_limite_cartao(integer, integer, integer)', 'financeiro.situacao_parcela(integer, date)',
    'financeiro.parcela_futura_editavel(integer, date)', 'financeiro.base_do_parcelamento(integer, integer)',
    'financeiro.travar_parcelas_futuras(integer, integer, text)',
]


@pytest.fixture
def banco(cluster):  # noqa: F811
    dsn = copiar(cluster)
    # FIN-ESCRITOR-UNICO-FINAL-1: as escritas do novo aplicativo exigem o perfil atribuido a ele.
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    return dsn


def falha(dsn, funcao, *args, usuario=USUARIO_A):
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, funcao, *args, usuario=usuario)
    return erro.value.pgcode, erro.value.diag.message_primary


def limites(dsn, mes='2029-05-01', cartao=CARTAO, perfil=PESSOAL, usuario=USUARIO_A):
    return {x['id']: x for x in tabela(dsn, 'limites_do_cartao', perfil, cartao, mes, usuario=usuario)}


def resumo(dsn, mes='2029-05-01', cartao=CARTAO, perfil=PESSOAL, usuario=USUARIO_A):
    return rpc(dsn, 'fatura_por_categoria', perfil, cartao, mes, usuario=usuario)


def lancamentos(dsn, filtro='todos', mes='2029-05-01', cartao=CARTAO, perfil=PESSOAL, usuario=USUARIO_A):
    return rpc(dsn, 'lancamentos_fatura_por_categoria', perfil, cartao, mes, filtro, usuario=usuario)['lancamentos']


def a_vista(dsn, **campos):
    return comprar(dsn, total_parcelas=1, **campos)['lancamentos'][0]


def parcelamento(dsn, lancamento_id, usuario=USUARIO_A):
    return rpc(dsn, 'parcelamento_da_compra', PESSOAL, lancamento_id, usuario=usuario)


def editar_lancamento(dsn, lancamento_id, dados, versao=None, usuario=USUARIO_A):
    versao = versao or edicao(dsn, lancamento_id)['versao']
    return rpc(dsn, 'editar_lancamento_cartao', PESSOAL, lancamento_id, versao, dados, usuario=usuario)


def executado(dsn, mes):
    f = fatura(dsn, CARTAO, mes)
    return f['valor_executado'] if f else None


@pytest.mark.parametrize('funcao', DA_TELA)
def test_funcoes_da_tela_seguras(banco, funcao):
    r = sql(banco, f"""select p.prosecdef as definer, coalesce(array_to_string(p.proconfig, ','), '') as config,
                              has_function_privilege('anon', '{funcao}', 'EXECUTE') as anon,
                              has_function_privilege('authenticated', '{funcao}', 'EXECUTE') as autenticado
                         from pg_proc p where p.oid = '{funcao}'::regprocedure""")[0]
    assert r['definer'] is True and 'search_path=""' in r['config']
    assert r['anon'] is False and r['autenticado'] is True


@pytest.mark.parametrize('funcao', INTERNAS)
def test_funcoes_internas_fora_do_navegador(banco, funcao):
    r = sql(banco, f"""select has_function_privilege('anon', '{funcao}', 'EXECUTE') as anon,
                              has_function_privilege('authenticated', '{funcao}', 'EXECUTE') as autenticado""")[0]
    assert r == {'anon': False, 'autenticado': False}


# ---------------------------------------------------------------------------
# Cartao: emissor e "possui codigo"; numero, validade e CVV continuam recusados
# ---------------------------------------------------------------------------

def test_emissor_e_possui_codigo_no_cadastro_e_na_edicao(banco):
    r = rpc(banco, 'criar_cartao', PESSOAL, {'nome': 'Visa Tela', 'descricao': 'Banco Ficticio S.A.', 'dia_fechamento': 3,
                                             'dia_vencimento': 10, 'tem_codigo': False}, str(uuid.uuid4()))
    cartao = next(c for c in tabela(banco, 'cartoes_da_tela', PESSOAL) if c['id'] == r['cartao_id'])
    assert (cartao['descricao'], cartao['tem_codigo'], cartao['final_numero']) == ('Banco Ficticio S.A.', False, None)
    assert cartao['versao'] == next(c['versao'] for c in tabela(banco, 'cartoes_do_perfil', PESSOAL) if c['id'] == r['cartao_id'])
    rpc(banco, 'editar_cartao', PESSOAL, r['cartao_id'], cartao['versao'], {'descricao': 'Outro Emissor', 'tem_codigo': True})
    cartao = next(c for c in tabela(banco, 'cartoes_da_tela', PESSOAL) if c['id'] == r['cartao_id'])
    assert (cartao['descricao'], cartao['tem_codigo'], cartao['nome']) == ('Outro Emissor', True, 'Visa Tela')
    cfg = sql(banco, 'select * from public.config_agregador where item_despesa_id = %s', (r['cartao_id'],))[0]
    assert (cfg['numero_cartao'], cfg['codigo_seguranca'], cfg['data_validade']) == (None, None, None)


@pytest.mark.parametrize('campo', ['numero_cartao', 'codigo_seguranca', 'data_validade'])
def test_dados_sensiveis_recusados_tambem_na_edicao(banco, campo):
    versao = next(c['versao'] for c in tabela(banco, 'cartoes_da_tela', PESSOAL) if c['id'] == CARTAO)
    codigo, mensagem = falha(banco, 'editar_cartao', PESSOAL, CARTAO, versao, {campo: '123'})
    assert codigo == '22023' and 'codigo de seguranca' in mensagem


def test_cartoes_da_tela_isolado(banco):
    assert {c['id'] for c in tabela(banco, 'cartoes_da_tela', ID['PERFIL_B'], usuario=USUARIO_B)} == {CARTAO_B}
    assert falha(banco, 'cartoes_da_tela', ID['PERFIL_B'])[0] == '42501'


# ---------------------------------------------------------------------------
# Categorias do Cartao e limites
# ---------------------------------------------------------------------------

def test_categorias_do_cartao_do_perfil_com_legado(banco):
    nomes = [c['nome'] for c in tabela(banco, 'categorias_cartao_do_perfil', PESSOAL)]
    assert {'Streaming CC', 'Outros CC', 'Legado CC'} <= set(nomes)  # NULL conta como Pessoal (condicao_perfil)
    assert not {'Streaming CC', 'Outros CC', 'Legado CC'} & {
        c['nome'] for c in tabela(banco, 'categorias_cartao_do_perfil', ID['PERFIL_B'], usuario=USUARIO_B)}


def test_limites_com_gasto_do_mes_como_o_flask(banco):
    comprar(banco)  # 100,00 em 3x a partir de 05/2029, categoria 952 -> 961
    lim = limites(banco)
    assert set(lim) == {981, 982}  # 983 e de perfil NULL: o Flask lista so os do perfil
    assert (lim[981]['gasto_atual'], lim[981]['disponivel'], lim[981]['percentual_utilizado']) == (33.34, 466.66, 6.67)
    assert (lim[982]['ativo'], lim[982]['gasto_atual']) == (False, 0)
    assert limites(banco, '2029-08-01')[981]['gasto_atual'] == 0


def test_vincular_reativa_o_existente_e_cria_o_novo(banco):
    r = rpc(banco, 'vincular_limite_cartao', PESSOAL, CARTAO, {'categoria_cartao_id': 962, 'limite_mensal': '250.50'})
    assert r == {'limite_id': 982, 'criado': False}
    assert (limites(banco)[982]['ativo'], limites(banco)[982]['limite_mensal']) == (True, 250.5)
    nova = sql(banco, "insert into public.categoria_cartao (nome, ativo, perfil_financeiro_id) values ('Mercado CC', true, %s) "
                      "returning id", (PESSOAL,))[0]['id']
    r = rpc(banco, 'vincular_limite_cartao', PESSOAL, CARTAO, {'categoria_cartao_id': nova, 'limite_mensal': ''})
    assert r['criado'] is True and limites(banco)[r['limite_id']]['limite_mensal'] == 0
    assert sql(banco, 'select perfil_financeiro_id from public.cartao_categoria_limite where id = %s',
               (r['limite_id'],))[0]['perfil_financeiro_id'] == PESSOAL


@pytest.mark.parametrize('dados, codigo', [
    ({'categoria_cartao_id': 962, 'limite_mensal': '-1'}, '22023'),
    ({'categoria_cartao_id': 962, 'limite_mensal': '1.234'}, '22023'),
    ({'categoria_cartao_id': 'x'}, '22023'),
    ({'categoria_cartao_id': 999999}, '22023'),
    ({'categoria_cartao_id': 963, 'limite_mensal': '10'}, '22023'),  # vinculo legado sem perfil: nao e sobrescrito
])
def test_vinculo_invalido_recusado(banco, dados, codigo):
    antes = sql(banco, 'select md5(string_agg(t::text, \'|\' order by id)) as h from public.cartao_categoria_limite t')
    assert falha(banco, 'vincular_limite_cartao', PESSOAL, CARTAO, dados)[0] == codigo
    assert sql(banco, 'select md5(string_agg(t::text, \'|\' order by id)) as h from public.cartao_categoria_limite t') == antes


def test_atualizar_e_desativar_limite(banco):
    rpc(banco, 'atualizar_limite_cartao', PESSOAL, CARTAO, 981, {'limite_mensal': '650'})
    assert (limites(banco)[981]['limite_mensal'], limites(banco)[981]['ativo']) == (650, True)
    rpc(banco, 'desativar_limite_cartao', PESSOAL, CARTAO, 981)
    assert limites(banco)[981]['ativo'] is False
    rpc(banco, 'atualizar_limite_cartao', PESSOAL, CARTAO, 981, {'ativo': True})
    assert (limites(banco)[981]['ativo'], limites(banco)[981]['limite_mensal']) == (True, 650)
    sql(banco, 'update public.categoria_cartao set ativo = false where id = 962')
    assert 'inativa' in falha(banco, 'atualizar_limite_cartao', PESSOAL, CARTAO, 982, {'ativo': True})[1]


@pytest.mark.parametrize('usuario, perfil, cartao, limite, codigo', [
    (USUARIO_B, PESSOAL, CARTAO, 981, '42501'),           # outro usuario
    (USUARIO_A, ID['PERFIL_B'], CARTAO_B, 981, '42501'),  # perfil sem acesso
    (USUARIO_A, PESSOAL, CARTAO_B, 981, '42501'),         # cartao de outro perfil
    (USUARIO_A, PESSOAL, CARTAO, 983, '42501'),           # vinculo sem perfil (nao e do perfil)
    (None, PESSOAL, CARTAO, 981, '42501'),                # anonimo
])
def test_limites_isolados(banco, usuario, perfil, cartao, limite, codigo):
    pg = falha(banco, 'desativar_limite_cartao', perfil, cartao, limite, usuario=usuario)[0]
    assert pg == codigo
    assert limites(banco)[981]['ativo'] is True


def test_leitor_nao_altera_limites(banco):
    empresa = ID['EMPRESA']
    cartao = sql(banco, "select id from public.item_despesa where tipo = 'Agregador' and perfil_financeiro_id = %s limit 1",
                 (empresa,))
    alvo = cartao[0]['id'] if cartao else CARTAO
    assert falha(banco, 'vincular_limite_cartao', empresa, alvo, {'categoria_cartao_id': 962})[0] == '42501'


# ---------------------------------------------------------------------------
# Fatura por Categoria do Cartao
# ---------------------------------------------------------------------------

def test_fatura_por_categoria_como_o_flask(banco):
    comprar(banco)                                                       # 33,34 classificado (961)
    a_vista(banco, descricao='Mercado', valor='40.00', categoria_id=MORADIA)  # sem Categoria do Cartao
    sql(banco, "insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, categoria_id, categoria_cartao_id, "
               "descricao, valor, data_compra, mes_fatura, numero_parcela, total_parcelas) "
               "values (%s, %s, %s, 962, 'Sem limite', 10.00, '2029-05-02', '2029-05-01', 1, 1)", (PESSOAL, CARTAO, MORADIA))
    r = resumo(banco)
    assert (r['total_fatura'], r['total_com_categoria'], r['total_sem_categoria_cartao']) == (83.34, 43.34, 40.0)
    # Limite total: so os ativos do perfil (981); disponivel e percentual so com as categorias vinculadas.
    assert (r['limite_total'], r['disponivel_total'], r['percentual_total'], r['status_total']) == (500, 466.66, 6.67, 'Normal')
    grupos = {g['tipo_grupo']: g for g in r['categorias']}
    assert [g['tipo_grupo'] for g in r['categorias']] == ['categoria_cartao', 'categoria_sem_limite', 'sem_categoria']
    assert (grupos['categoria_cartao']['categoria_cartao_nome'], grupos['categoria_cartao']['gasto_atual'],
            grupos['categoria_cartao']['disponivel'], grupos['categoria_cartao']['status']) == ('Streaming CC', 33.34, 466.66, 'Normal')
    assert (grupos['categoria_sem_limite']['categoria_cartao_id'], grupos['categoria_sem_limite']['disponivel'],
            grupos['categoria_sem_limite']['status'], grupos['categoria_sem_limite']['avisos']) == \
        (962, None, 'Revisar', ['Categoria sem limite neste cartao.'])
    assert (grupos['sem_categoria']['categoria_cartao_nome'], grupos['sem_categoria']['gasto_atual'],
            grupos['sem_categoria']['quantidade_lancamentos']) == ('Sem Categoria do Cartao', 40.0, 1)


@pytest.mark.parametrize('gasto, limite, status', [('0', '0', 'Normal'), ('1', '0', 'Estourado'), ('80', '100', 'Normal'),
                                                   ('80.01', '100', 'Atencao'), ('100', '100', 'Atencao'),
                                                   ('100.01', '100', 'Estourado')])
def test_status_do_consumo_como_o_flask(banco, gasto, limite, status):
    assert sql(banco, 'select financeiro.status_consumo(%s::numeric, %s::numeric) as s', (gasto, limite))[0]['s'] == status


def test_fatura_vazia_e_mes_sem_compras(banco):
    r = resumo(banco, '2031-01-01')
    assert (r['total_fatura'], r['categorias'][0]['tipo_grupo'], len(r['categorias'])) == (0, 'categoria_cartao', 1)
    assert r['situacao_fatura'] == 'SEM_FATURA'


def test_lancamentos_por_filtro_e_bloqueio(banco):
    comprar(banco)
    a_vista(banco, descricao='Mercado', valor='40.00', categoria_id=MORADIA)
    todos = lancamentos(banco)
    assert [(x['descricao'], x['status_classificacao']) for x in todos] == \
        [('Notebook', 'classificado'), ('Mercado', 'sem_categoria_cartao')]
    assert [x['descricao'] for x in lancamentos(banco, 'sem_categoria')] == ['Mercado']
    assert [x['descricao'] for x in lancamentos(banco, '961')] == ['Notebook']
    assert todos[0]['parcela_atual'] == 1 and todos[0]['parcelas_total'] == 3 and todos[0]['compra_id']
    assert all(x['pode_editar'] for x in todos)
    pagar(banco, CARTAO, '2029-05-01')
    assert [(x['pode_editar'], x['bloqueio']) for x in lancamentos(banco)][0] == (False, 'Fatura paga: correcao so por estorno')
    assert falha(banco, 'lancamentos_fatura_por_categoria', PESSOAL, CARTAO, '2029-05-01', '1; drop')[0] == '22023'


# ---------------------------------------------------------------------------
# Edicao de um lancamento
# ---------------------------------------------------------------------------

def test_edicao_da_compra_a_vista_recalcula_a_fatura(banco):
    lid = a_vista(banco, descricao='Mercado', valor='40.00', categoria_id=MORADIA)
    assert executado(banco, '2029-05-01') == Decimal('40.00')
    editar_lancamento(banco, lid, {'descricao': 'Mercado central', 'valor': 55.5, 'data_compra': '2029-05-12',
                                   'categoria_id': ASSINATURAS, 'numero_parcela': 1, 'total_parcelas': 1})
    l = sql(banco, 'select * from public.lancamento_agregado where id = %s', (lid,))[0]
    assert (l['descricao'], l['descricao_exibida'], l['valor'], str(l['data_compra']), l['categoria_cartao_id']) == \
        ('Mercado central', 'Mercado central', Decimal('55.50'), '2029-05-12', 961)
    assert executado(banco, '2029-05-01') == Decimal('55.50')


def test_edicao_de_uma_parcela_so_muda_ela(banco):
    r = comprar(banco)
    p1, p2, p3 = r['lancamentos']
    editar_lancamento(banco, p2, {'valor': '40.00', 'descricao': 'Notebook (ajuste)'})
    linhas = parcelas(banco, r['compra_id'])
    assert [(x['valor'], x['descricao']) for x in linhas] == [
        (Decimal('33.34'), 'Notebook'), (Decimal('40.00'), 'Notebook (ajuste)'), (Decimal('33.33'), 'Notebook')]
    assert executado(banco, '2029-06-01') == Decimal('40.00')


@pytest.mark.parametrize('dados, trecho', [
    ({'numero_parcela': 2}, 'Parcela e total'),
    ({'total_parcelas': 5}, 'Parcela e total'),
    ({'data_compra': '2029-05-20'}, 'data da compra'),
    ({'valor': 0}, 'Valor'),
    ({'descricao': ''}, 'Descricao'),
    ({'categoria_id': 999999}, 'Categoria'),
])
def test_edicao_de_parcela_recusa_o_que_desmonta_o_parcelamento(banco, dados, trecho):
    r = comprar(banco)
    antes = parcelas(banco, r['compra_id'])
    codigo, mensagem = falha(banco, 'editar_lancamento_cartao', PESSOAL, r['lancamentos'][0],
                             edicao(banco, r['lancamentos'][0])['versao'], dados)
    assert codigo == '22023' and trecho in mensagem
    assert parcelas(banco, r['compra_id']) == antes


def test_edicao_em_fatura_paga_ou_com_versao_velha_recusada(banco):
    r = comprar(banco)
    versao = edicao(banco, r['lancamentos'][1])['versao']
    pagar(banco, CARTAO, '2029-06-01')
    codigo, mensagem = falha(banco, 'editar_lancamento_cartao', PESSOAL, r['lancamentos'][1], versao, {'valor': '1.00'})
    assert (codigo, 'Fatura paga' in mensagem) == ('P0001', True)
    editar_lancamento(banco, r['lancamentos'][0], {'valor': '30.00'})  # a de maio continua aberta
    codigo, mensagem = falha(banco, 'editar_lancamento_cartao', PESSOAL, r['lancamentos'][0], versao, {'valor': '2.00'})
    assert (codigo, 'alterada por outra operacao' in mensagem) == ('P0001', True)


def test_leitor_e_outro_perfil_nao_editam_lancamento(banco):
    r = comprar(banco)
    versao = edicao(banco, r['lancamentos'][0])['versao']
    assert falha(banco, 'editar_lancamento_cartao', PESSOAL, r['lancamentos'][0], versao, {'valor': '1'},
                 usuario=USUARIO_B)[0] == '42501'
    assert falha(banco, 'editar_lancamento_cartao', ID['EMPRESA'], r['lancamentos'][0], versao, {'valor': '1'})[0] == '42501'


# ---------------------------------------------------------------------------
# Parcelamento: consulta, parcelas futuras e cancelamento
# ---------------------------------------------------------------------------

def compra_4x(dsn):
    return comprar(dsn, valor='100.00', total_parcelas=4)  # 25,00 x 4: 05, 06, 07 e 08/2029


def test_consulta_do_parcelamento_como_o_flask(banco):
    r = compra_4x(banco)
    pagar(banco, CARTAO, '2029-06-01')
    base = parcelamento(banco, r['lancamentos'][0])
    assert (base['base']['parcela_atual'], base['base']['total_parcelas'], base['base']['primeira_competencia'],
            base['base']['ultima_competencia'], base['base']['futuras_editaveis'], base['base']['futuras_bloqueadas']) == \
        (1, 4, '2029-05', '2029-08', 2, 1)
    assert [(p['parcela'], p['status'], p['editavel']) for p in base['parcelas']] == [
        ('1/4', 'atual', False), ('2/4', 'paga', False), ('3/4', 'futura', True), ('4/4', 'futura', True)]
    assert base['pode_gerir'] is True and base['versao'] == edicao(banco, r['lancamentos'][0])['versao']
    terceira = parcelamento(banco, r['lancamentos'][2])  # base na 3a: 1a passada, 2a paga, 4a futura
    assert [p['status'] for p in terceira['parcelas']] == ['passada', 'paga', 'atual', 'futura']
    lid = a_vista(banco, descricao='Mercado', valor='40.00', categoria_id=MORADIA)
    assert falha(banco, 'parcelamento_da_compra', PESSOAL, lid)[1] == 'Lancamento nao pertence a parcelamento'


def test_editar_parcelas_futuras_so_as_futuras_abertas(banco):
    r = compra_4x(banco)
    pagar(banco, CARTAO, '2029-06-01')
    versao = parcelamento(banco, r['lancamentos'][0])['versao']
    res = rpc(banco, 'editar_parcelas_futuras', PESSOAL, r['lancamentos'][0], versao,
              {'descricao': 'Notebook novo', 'valor': '30.00', 'categoria_id': str(MORADIA)})
    assert res == {'atualizadas': 2, 'faturas_afetadas': ['2029-07', '2029-08']}
    linhas = parcelas(banco, r['compra_id'])
    assert [(x['numero_parcela'], x['valor'], x['descricao'], x['categoria_id']) for x in linhas] == [
        (1, Decimal('25.00'), 'Notebook', ASSINATURAS), (2, Decimal('25.00'), 'Notebook', ASSINATURAS),
        (3, Decimal('30.00'), 'Notebook novo', MORADIA), (4, Decimal('30.00'), 'Notebook novo', MORADIA)]
    assert [x['categoria_cartao_id'] for x in linhas] == [961, 961, None, None]
    assert executado(banco, '2029-07-01') == Decimal('30.00') and executado(banco, '2029-06-01') == Decimal('25.00')
    # Campos vazios nao mudam nada; a versao antiga e recusada.
    assert falha(banco, 'editar_parcelas_futuras', PESSOAL, r['lancamentos'][0], versao, {'valor': '1'})[0] == 'P0001'
    versao = parcelamento(banco, r['lancamentos'][0])['versao']
    rpc(banco, 'editar_parcelas_futuras', PESSOAL, r['lancamentos'][0], versao, {'descricao': '', 'valor': '', 'categoria_id': ''})
    assert parcelas(banco, r['compra_id']) == linhas


def test_ultima_parcela_nao_tem_futuras(banco):
    r = compra_4x(banco)
    ultima = r['lancamentos'][3]
    res = rpc(banco, 'editar_parcelas_futuras', PESSOAL, ultima, parcelamento(banco, ultima)['versao'], {'valor': '9'})
    assert res == {'atualizadas': 0, 'faturas_afetadas': []}
    res = rpc(banco, 'cancelar_parcelas_futuras', PESSOAL, ultima, parcelamento(banco, ultima)['versao'])
    assert res == {'canceladas': 0, 'faturas_afetadas': []}
    assert len(parcelas(banco, r['compra_id'])) == 4


def test_cancelar_parcelas_futuras_preserva_historico_e_recalcula(banco):
    r = compra_4x(banco)
    pagar(banco, CARTAO, '2029-06-01')
    fechada = fatura(banco, CARTAO, '2029-08-01')['id']
    sql(banco, "update public.conta set status_fatura = 'FECHADA' where id = %s", (fechada,))  # 4a em fatura consolidada
    pago_antes = fatura(banco, CARTAO, '2029-06-01')
    res = rpc(banco, 'cancelar_parcelas_futuras', PESSOAL, r['lancamentos'][0], parcelamento(banco, r['lancamentos'][0])['versao'])
    assert res == {'canceladas': 1, 'faturas_afetadas': ['2029-07']}
    assert [x['numero_parcela'] for x in parcelas(banco, r['compra_id'])] == [1, 2, 4]
    assert executado(banco, '2029-07-01') == Decimal('0')
    assert fatura(banco, CARTAO, '2029-06-01') == pago_antes  # fatura paga intacta


def test_parcelamento_isolado_e_leitor(banco):
    r = compra_4x(banco)
    versao = parcelamento(banco, r['lancamentos'][0])['versao']
    assert falha(banco, 'parcelamento_da_compra', PESSOAL, r['lancamentos'][0], usuario=USUARIO_B)[0] == '42501'
    assert falha(banco, 'parcelamento_da_compra', ID['PERFIL_B'], r['lancamentos'][0], usuario=USUARIO_B)[0] == '42501'
    for funcao, extra in (('editar_parcelas_futuras', ({'valor': '1'},)), ('cancelar_parcelas_futuras', ())):
        assert falha(banco, funcao, PESSOAL, r['lancamentos'][0], versao, *extra, usuario=USUARIO_B)[0] == '42501'
        assert falha(banco, funcao, ID['EMPRESA'], r['lancamentos'][0], versao, *extra)[0] == '42501'
    assert len(parcelas(banco, r['compra_id'])) == 4


def test_recorrencia_do_cartao_nao_e_editada_nem_cancelada_aqui(banco):
    r = compra_4x(banco)
    sql(banco, 'update public.lancamento_agregado set is_recorrente = true where id = %s', (r['lancamentos'][2],))
    base = parcelamento(banco, r['lancamentos'][0])
    assert [p['editavel'] for p in base['parcelas']] == [False, True, False, True]
    res = rpc(banco, 'cancelar_parcelas_futuras', PESSOAL, r['lancamentos'][0], base['versao'])
    assert res['canceladas'] == 2 and [x['numero_parcela'] for x in parcelas(banco, r['compra_id'])] == [1, 3]


def test_nada_parcial_quando_falha(banco):
    r = compra_4x(banco)
    antes = parcelas(banco, r['compra_id'])
    faturas_antes = sql(banco, 'select * from public.conta where is_fatura_cartao order by id')
    falha(banco, 'editar_parcelas_futuras', PESSOAL, r['lancamentos'][0], parcelamento(banco, r['lancamentos'][0])['versao'],
          {'descricao': 'ok', 'valor': '1.001'})
    assert parcelas(banco, r['compra_id']) == antes
    assert sql(banco, 'select * from public.conta where is_fatura_cartao order by id') == faturas_antes
