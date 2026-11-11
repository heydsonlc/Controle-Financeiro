"""
Testes FIN-CARTOES-EXECUTADO-01 (migration 20261225090000), em cluster local descartavel com o cenario FICTICIO do
FIN-RECORRENCIA-1 (Cartao Teste 910, Pessoal; Categoria do Cartao 961 com limite de R$ 500). Recorrencias em 05/2029.

- executado consolidado = compras + parcelas + recorrencias fixas (previstas ou cobradas) - creditos; o orcamento da
  Categoria do Cartao nao e executado; a recorrencia nao cobrada fica fora;
- previsto da fatura aberta = executado + o que falta dos limites (a fixa prevista nao e somada duas vezes);
- Despesas, faturas do mes e Dashboard (faturas em aberto e contas a vencer) com o mesmo valor (previsto_fatura);
- importacao com valor diferente substitui a previsao (uma vez), com o previsto preservado;
- pagamento: o executado consolidado e o valor sugerido (com a parte prevista informada); o banco pode cobrar menos
  (fixa prevista nao cobrada) sem marca automatica, sem movimento ou lancamento extra; a cobranca que chega depois pede
  revisao; marca de nao cobrada gravada antes da migration continua valendo e o estorno a desfaz;
- faturas futuras; seguranca; reversao e reaplicacao sem mudar dados.
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartao_despesas_fixas import (  # noqa: F401  (fixture e ajudantes reaproveitados)
    MES,
    PESSOAL,
    analisar,
    assinaturas,
    banco,
    importar,
    linha,
    md5_compras,
    ocorrencia,
    recorrencia,
)
from tests.test_supabase_cartao_previsto_executado import (
    D, JUNHO, conta_bancaria, dados_pagamento, estornar_pelo_app, fixa, lista, pagar_pelo_app, procurar,
)
from tests.test_supabase_cartoes import CARTAO, comprar, fatura, tabela
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, USUARIO_B, chamar, cluster, sql  # noqa: F401
from tests.test_supabase_recorrencia_cartao import falha, gerar_mes, rpc

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

RAIZ = Path(__file__).resolve().parent.parent
MIGRATION = RAIZ / 'supabase/migrations/20261225090000_financeiro_cartoes_executado.sql'
REVERSAO = RAIZ / 'supabase/reversao/20261225090000_cartoes_executado_anterior.sql'
FIXAS = D('329.60')  # Netflix 59,90 + Apple One 59,90 + ChatGPT 99,90 + Claude 109,90 (o Visa de 12/2026)


def previsto_fatura(dsn, mes=MES):
    return D(sql(dsn, 'select financeiro.previsto_fatura(%s) v', (fatura(dsn, CARTAO, mes)['id'],))[0]['v'])


def painel(dsn, mes='2029-05'):
    return D(procurar(rpc(dsn, 'dashboard_resumo_tela', PESSOAL, mes), 'faturas_em_aberto')['valor'])


# ---------------------------------------------------------------------------------------------------------------------
# Regra do executado consolidado
# ---------------------------------------------------------------------------------------------------------------------

def test_so_despesas_fixas_previstas_como_o_visa_de_dezembro(banco):
    assinaturas(banco)
    # executado = as 4 fixas; previsto = executado + o limite inteiro da categoria (orcamento nao e executado)
    assert lista(banco) == (FIXAS + D('500.00'), FIXAS + D('500.00'), FIXAS)
    r = rpc(banco, 'fatura_por_categoria', PESSOAL, CARTAO, MES)
    assert (D(r['total_fatura']), D(r['total_despesas_fixas']), D(r['total_compras_parceladas'])) == (FIXAS, FIXAS, D('0'))
    limite = next(x for x in tabela(banco, 'limites_do_cartao', PESSOAL, CARTAO, MES) if x['id'] == 981)
    assert (limite['gasto_atual'], limite['disponivel']) == (0, 500)  # as fixas nao consomem a Categoria do Cartao


def test_parcelas_compras_e_fixas_somam_uma_vez(banco):
    assinaturas(banco)
    comprar(banco, descricao='Notebook', valor='300.00', total_parcelas=3)   # parcela de 100 em 05/2029
    comprar(banco, descricao='Revista', valor='40.00', total_parcelas=1)     # Categoria do Cartao 961
    executado = FIXAS + D('100.00') + D('40.00')
    assert lista(banco) == (executado + D('460.00'), executado + D('460.00'), executado)
    assert previsto_fatura(banco) == lista(banco)[0]
    assert lista(banco, JUNHO)[2] == FIXAS + D('100.00')  # fatura futura: fixas previstas e a parcela de junho


def test_despesas_faturas_do_mes_e_dashboard_com_o_mesmo_valor(banco):
    assinaturas(banco)
    comprar(banco, descricao='Revista', valor='40.00', total_parcelas=1)
    valor = lista(banco)[0]
    cartao = next(x for x in tabela(banco, 'faturas_do_mes', PESSOAL, MES) if x['cartao_id'] == CARTAO)
    assert D(cartao['valor_previsto']) == valor == previsto_fatura(banco) == painel(banco)
    # contas a vencer: a fatura entra pelo mesmo valor (vencimento trazido para dentro dos proximos 7 dias)
    hoje = sql(banco, "select (now() at time zone 'America/Sao_Paulo')::date d")[0]['d']
    sql(banco, 'update public.conta set data_vencimento = %s where id = %s', (hoje, fatura(banco, CARTAO, MES)['id']))
    itens = procurar(rpc(banco, 'dashboard_resumo_tela', PESSOAL, '2029-05'), 'proximos_vencimentos')
    linha_fatura = next(x for x in itens if x['tipo'] == 'fatura')
    assert D(linha_fatura['valor']) == valor


def test_cobranca_com_valor_diferente_substitui_a_previsao(banco):
    ids = assinaturas(banco)
    antes = sql(banco, 'select count(*) n from public.lancamento_agregado')[0]['n']
    importar(banco, linha(1, 'NETFLIX.COM', '44.90', categoria=None))
    assert sql(banco, 'select count(*) n from public.lancamento_agregado')[0]['n'] == antes  # nenhum lancamento novo
    f = fixa(banco, ids['Netflix'])
    assert (f['situacao_ocorrencia'], D(f['valor_executado']), D(f['valor_previsto'])) == ('CONFIRMADA', D('44.90'), D('59.90'))
    assert lista(banco)[2] == FIXAS - D('59.90') + D('44.90')
    assert painel(banco) == lista(banco)[0]


def test_recorrencia_nao_cobrada_fica_fora(banco):
    ids = assinaturas(banco)
    l = ocorrencia(banco, ids['Claude'])
    # marca gravada antes desta migration (o pagamento antigo marcava): continua fora do executado
    sql(banco, """insert into financeiro.ocorrencia_recorrencia_cartao (perfil_financeiro_id, lancamento_id, item_despesa_id,
                  cartao_id, competencia, valor_previsto, valor_executado, origem, lancamento_antes)
                  values (%s, %s, %s, %s, %s, %s, 0, 'NAO_COBRADA', '{}'::jsonb)""",
        (PESSOAL, l['id'], ids['Claude'], CARTAO, MES, l['valor']))
    assert fixa(banco, ids['Claude'])['situacao_ocorrencia'] == 'NAO_COBRADA'
    assert lista(banco)[2] == FIXAS - D('109.90')


# ---------------------------------------------------------------------------------------------------------------------
# Pagamento: compromisso consolidado x cobranca efetiva
# ---------------------------------------------------------------------------------------------------------------------

def test_valor_sugerido_identifica_a_parte_prevista(banco):
    assinaturas(banco)
    comprar(banco, descricao='Revista', valor='40.00', total_parcelas=1)
    d = dados_pagamento(banco)
    assert (D(d['fatura']['valor_executado']), D(d['fatura']['previsto_sem_cobranca']), d['pode_pagar']) == \
        (FIXAS + D('40.00'), FIXAS, True)


def test_fixa_prevista_ainda_nao_cobrada_pelo_banco(banco):
    """Claude prevista nao veio na fatura do banco: paga-se o cobrado com a diferenca justificada; o consolidado continua,
    nada e marcado como nao cobrado, nenhum movimento, compra ou competencia muda; Dashboard sem duplicidade."""
    ids = assinaturas(banco)
    importar(banco, linha(1, 'NETFLIX.COM', '59.90', categoria=None), linha(2, 'APPLE ONE', '59.90', categoria=None),
             linha(3, 'CHATGPT', '99.90', categoria=None))
    assert {fixa(banco, ids[n])['situacao_ocorrencia'] for n in ('Netflix', 'Apple One', 'ChatGPT')} == {'CONFIRMADA'}
    consolidado = lista(banco)[2]
    assert consolidado == FIXAS  # 3 cobradas + Claude prevista
    f_id = fatura(banco, CARTAO, MES)['id']
    compras_antes = md5_compras(banco)
    movs = sql(banco, 'select count(*) n from public.movimento_financeiro')[0]['n']
    cobrado = FIXAS - D('109.90')
    p = rpc(banco, 'pagar_fatura', PESSOAL, f_id, {
        'conta_bancaria_id': conta_bancaria(banco), 'data_pagamento': '2029-05-31', 'valor_pago': f'{cobrado}',
        'valor_executado': f'{consolidado}', 'tipo_ajuste': 'AJUSTE', 'justificativa': 'Claude nao veio nesta fatura'}, str(uuid.uuid4()))
    assert (D(p['valor_pago']), D(p['valor_executado']), D(p['diferenca'])) == (cobrado, consolidado, D('-109.90'))
    assert sql(banco, 'select count(*) n from public.movimento_financeiro')[0]['n'] == movs + 1
    assert md5_compras(banco) == compras_antes
    assert fixa(banco, ids['Claude'])['situacao_ocorrencia'] == 'PAGA'
    assert not sql(banco, "select 1 from financeiro.ocorrencia_recorrencia_cartao where origem = 'NAO_COBRADA'")
    assert lista(banco) == (consolidado, consolidado + D('500.00'), consolidado)
    assert painel(banco) == D('0.00')  # paga: nada em aberto
    assert lista(banco, JUNHO)[2] == FIXAS  # junho: as 4 previstas, nada em dobro
    # a cobranca da Claude que chega depois pede revisao (nao entra sozinha na proxima fatura)
    r = analisar(banco, linha(4, 'CLAUDE', '109.90', categoria=None))[0]
    assert r['status'] == 'revisar' and r['realiza_lancamento_id'] is None


def test_estorno_desfaz_marca_gravada_antes_da_migration(banco):
    ids = assinaturas(banco)
    p = pagar_pelo_app(banco)
    l = ocorrencia(banco, ids['Claude'])
    sql(banco, """insert into financeiro.ocorrencia_recorrencia_cartao (perfil_financeiro_id, lancamento_id, item_despesa_id,
                  cartao_id, competencia, valor_previsto, valor_executado, origem, lancamento_antes, pagamento_id)
                  values (%s, %s, %s, %s, %s, %s, 0, 'NAO_COBRADA', '{}'::jsonb, %s)""",
        (PESSOAL, l['id'], ids['Claude'], CARTAO, MES, l['valor'], p['pagamento_id']))
    assert fixa(banco, ids['Claude'])['situacao_ocorrencia'] == 'NAO_COBRADA'
    estornar_pelo_app(banco, p['movimento_id'])
    assert fixa(banco, ids['Claude'])['situacao_ocorrencia'] == 'PREVISTA'
    assert lista(banco)[2] == FIXAS


# ---------------------------------------------------------------------------------------------------------------------
# Seguranca e reversao
# ---------------------------------------------------------------------------------------------------------------------

def test_previsto_fatura_e_interna(banco):
    f = sql(banco, """select prosecdef d, proconfig c, has_function_privilege('anon', p.oid, 'execute') a,
                             has_function_privilege('authenticated', p.oid, 'execute') u
                        from pg_proc p where p.oid = 'financeiro.previsto_fatura(integer)'::regprocedure""")[0]
    assert (f['d'], f['c'], f['a'], f['u']) == (True, ['search_path=""'], False, False)
    assert falha(banco, 'previsto_fatura', fatura(banco, CARTAO, MES)['id'] if fatura(banco, CARTAO, MES) else 1)[0] == '42501'


def _executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_reversao_e_reaplicacao_sem_alterar_dados(banco):
    assinaturas(banco)
    comprar(banco, descricao='Revista', valor='40.00', total_parcelas=1)
    dados = (md5_compras(banco), sql(banco, "select md5(string_agg(c::text, '|' order by c.id)) h from public.conta c")[0]['h'])
    _executar(banco, REVERSAO)
    assert lista(banco)[2] == D('40.00')  # regra anterior: a fixa prevista fora do executado
    assert not sql(banco, "select 1 from pg_proc where proname = 'previsto_fatura'")
    _executar(banco, MIGRATION)
    assert lista(banco)[2] == FIXAS + D('40.00')
    assert (md5_compras(banco), sql(banco, "select md5(string_agg(c::text, '|' order by c.id)) h from public.conta c")[0]['h']) == dados
