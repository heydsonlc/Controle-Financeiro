"""
Testes FIN-RECEITAS-SALDO-01 (migration 20261224090000), em cluster PostgreSQL local descartavel e com dados ficticios.

1. Valor-base de fonte recorrente: a previa lista o que muda e o que fica; a atualizacao (com a confirmacao da previa)
   muda so as previsoes geradas automaticamente e ainda pendentes, a partir da competencia escolhida; preserva as
   recebidas, as parciais e as alteradas manualmente (valor, data, zerada, criada/anotada pelo usuario); registra em
   operacao_receita; nenhum recebimento, movimento ou saldo muda.
2. Total de receitas do mes (receitas_totais_do_mes) e Dashboard pela mesma regra: estorno nao conta, parcial conta o
   previsto, recebido acima do previsto conta o recebido, recebimento sem previsao conta uma vez, consorcio e previsto.
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_receitas import (  # noqa: F401
    ID, MES, PG_BIN, USUARIO_A, USUARIO_B, banco, chamar, cluster, conta_bancaria, criar, edicao, editar, excluir, rpc, sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
D = Decimal
RAIZ = Path(__file__).resolve().parent.parent
MIGRATION = RAIZ / 'supabase/migrations/20261224090000_financeiro_receitas_saldo.sql'
REVERSAO = RAIZ / 'supabase/reversao/20261224090000_receitas_saldo_anterior.sql'


def erro(funcao, *args, **kw):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args, **kw)
    return e.value


def versao_fonte(dsn, item):
    return sql(dsn, 'select financeiro.versao_fonte(%s) as v', (item,))[0]['v']


def previsoes(dsn, item):
    return {str(p['mes_referencia'])[:7]: p for p in sql(dsn, 'select * from public.receita_orcamento where item_receita_id = %s '
                                                               'order by mes_referencia', (item,))}


def receber(dsn, orc, valor, falta):
    return rpc(dsn, 'receber_receita', PESSOAL, orc, {'conta_bancaria_id': conta_bancaria(dsn, 'Conta Pessoal (A)'),
                                                      'data_recebimento': '2027-01-05', 'valor_recebido': valor, 'falta': falta},
               str(uuid.uuid4()))


def previa(dsn, item, a_partir=None, usuario=USUARIO_A):
    return rpc(dsn, 'previa_atualizacao_previsoes', PESSOAL, item, a_partir, usuario=usuario)


def atualizar(dsn, item, a_partir, esperadas, versao=None, chave=None, usuario=USUARIO_A):
    return rpc(dsn, 'atualizar_previsoes_fonte', PESSOAL, item, versao or versao_fonte(dsn, item), a_partir, esperadas,
               chave or str(uuid.uuid4()), usuario=usuario)


def dinheiro(dsn):
    return {t: sql(dsn, f"select md5(coalesce(string_agg(t::text, '|' order by t.id), '')) h from public.{t} t")[0]['h']
            for t in ('receita_realizada', 'movimento_financeiro', 'conta_bancaria')}


def cenario(dsn):
    """Fonte recorrente de R$ 1.000 (01 a 12/2027), como o Salario: 01 recebida, 02 parcial, 04 com valor manual,
    05 com data propria, 06 removida (zerada) e 08 anotada pelo usuario; depois o valor-base passa a R$ 1.200."""
    item = criar(dsn, {'nome': 'Subsidio X', 'tipo': 'SALARIO_FIXO', 'valor': '1000.00', 'competencia': '2027-01-01',
                       'dia_previsto': 5, 'observacoes': 'Gerado automaticamente - Subsidio X', 'recorrente': True})['item_receita_id']
    p = previsoes(dsn, item)
    receber(dsn, p['2027-01']['id'], '1000.00', '1000.00')
    receber(dsn, p['2027-02']['id'], '400.00', '1000.00')
    editar(dsn, p['2027-04']['id'], {'valor': '950.00'})
    editar(dsn, p['2027-05']['id'], {'data_prevista': '2027-05-20'})
    excluir(dsn, p['2027-06']['id'])
    editar(dsn, p['2027-08']['id'], {'observacoes': 'Ferias: valor a confirmar'})
    rpc(dsn, 'redefinir_fonte_receita', PESSOAL, item, versao_fonte(dsn, item), {'valor_base_mensal': '1200.00', 'recorrente': True})
    return item


# =====================================================================================================================
# 1. Atualizacao das previsoes pelo valor-base
# =====================================================================================================================

def test_redefinir_valor_base_continua_sem_mudar_as_gravadas(banco):
    dsn, _ = banco
    item = cenario(dsn)
    assert {m: p['valor_esperado'] for m, p in previsoes(dsn, item).items()}['2027-03'] == D('1000.00')


def test_previa_lista_as_que_mudam_e_as_preservadas_com_o_motivo(banco):
    dsn, _ = banco
    item = cenario(dsn)
    r = previa(dsn, item, '2027-01-01')
    assert r['pode_atualizar'] is True and D(str(r['valor_base'])) == D('1200.00')
    assert [x['competencia'][:7] for x in r['afetadas']] == ['2027-03', '2027-07', '2027-09', '2027-10', '2027-11', '2027-12']
    assert r['quantidade'] == 6 and D(str(r['diferenca_total'])) == D('1200.00')
    assert {x['competencia'][:7]: x['motivo'] for x in r['preservadas']} == {
        '2027-01': 'Recebida (ha recebimento nesta competencia)', '2027-02': 'Parcialmente recebida',
        '2027-04': 'Valor alterado manualmente', '2027-05': 'Data prevista definida manualmente',
        '2027-06': 'Zerada ou removida manualmente', '2027-08': 'Criada ou anotada manualmente'}
    # a competencia inicial limita o alcance
    assert [x['competencia'][:7] for x in previa(dsn, item, '2027-10-01')['afetadas']] == ['2027-10', '2027-11', '2027-12']


def test_atualizacao_muda_so_as_elegiveis_e_registra_a_auditoria(banco):
    dsn, _ = banco
    item = cenario(dsn)
    antes, din = previsoes(dsn, item), dinheiro(dsn)
    r = atualizar(dsn, item, '2027-03-01', 6)
    assert r['atualizadas'] == 6
    depois = previsoes(dsn, item)
    for m in ('2027-03', '2027-07', '2027-09', '2027-10', '2027-11', '2027-12'):
        assert depois[m]['valor_esperado'] == D('1200.00')
    for m in ('2027-01', '2027-02', '2027-04', '2027-05', '2027-06', '2027-08'):
        assert depois[m] == antes[m]  # preservadas, inteiras
    assert dinheiro(dsn) == din  # nenhum recebimento, movimento ou saldo
    aud = sql(dsn, "select perfil_financeiro_id p, resultado r from financeiro.operacao_receita where operacao = 'atualizar_previsoes_fonte'")
    assert len(aud) == 1 and aud[0]['p'] == PESSOAL
    assert [(a['competencia'][:7], D(str(a['antes'])), D(str(a['depois']))) for a in aud[0]['r']['alteracoes']][0] == \
        ('2027-03', D('1000.00'), D('1200.00'))
    assert [x['competencia'][:7] for x in aud[0]['r']['preservadas']] == ['2027-04', '2027-05', '2027-06', '2027-08']


def test_repetir_a_chave_nao_muda_de_novo_e_previa_velha_e_recusada(banco):
    dsn, _ = banco
    item = cenario(dsn)
    chave = str(uuid.uuid4())
    primeiro = atualizar(dsn, item, '2027-03-01', 6, chave=chave)
    segundo = atualizar(dsn, item, '2027-03-01', 6, chave=chave)
    assert segundo['repetida'] is True and segundo['atualizadas'] == primeiro['atualizadas']
    assert sql(dsn, "select count(*) n from financeiro.operacao_receita where operacao = 'atualizar_previsoes_fonte'")[0]['n'] == 1
    # depois de atualizadas, uma nova previa nao tem nada a mudar; a quantidade velha e recusada sem alterar nada
    assert previa(dsn, item, '2027-03-01')['quantidade'] == 0
    antes = previsoes(dsn, item)
    assert 'mudaram desde a previa' in str(erro(atualizar, dsn, item, '2027-03-01', 6))
    assert previsoes(dsn, item) == antes


def test_versao_da_fonte_desatualizada_e_recusada(banco):
    dsn, _ = banco
    item = cenario(dsn)
    e = erro(atualizar, dsn, item, '2027-03-01', 6, versao='antiga')
    assert 'alterad' in str(e).lower()
    assert previsoes(dsn, item)['2027-03']['valor_esperado'] == D('1000.00')


def test_recebimento_depois_da_previa_nao_e_reescrito(banco):
    dsn, _ = banco
    item = cenario(dsn)
    p = previsoes(dsn, item)
    receber(dsn, p['2027-03']['id'], '1000.00', '1000.00')  # recebida depois da previa
    assert 'mudaram desde a previa' in str(erro(atualizar, dsn, item, '2027-03-01', 6))
    r = atualizar(dsn, item, '2027-03-01', 5)
    assert r['atualizadas'] == 5 and previsoes(dsn, item)['2027-03']['valor_esperado'] == D('1000.00')


def test_editar_valor_marca_manual_e_so_data_nao(banco):
    dsn, _ = banco
    item = cenario(dsn)
    p = previsoes(dsn, item)
    assert p['2027-04']['valor_manual'] is True
    assert p['2027-05']['valor_manual'] is False and p['2027-05']['data_prevista'] is not None
    editar(dsn, p['2027-07']['id'], {'valor': '1000.00'})  # mesmo valor: nao marca
    assert previsoes(dsn, item)['2027-07']['valor_manual'] is False


def test_fonte_de_consorcio_nao_atualiza(banco):
    dsn, ids = banco
    r = previa(dsn, ids['consorcio'])
    assert r['pode_atualizar'] is False and r['quantidade'] == 0
    assert erro(atualizar, dsn, ids['consorcio'], '2027-03-01', 0)


def test_outro_perfil_e_permissoes(banco):
    dsn, _ = banco
    item = cenario(dsn)
    assert erro(previa, dsn, item, None, usuario=USUARIO_B)
    assert erro(atualizar, dsn, item, '2027-03-01', 6, usuario=USUARIO_B)
    assert previsoes(dsn, item)['2027-03']['valor_esperado'] == D('1000.00')
    linhas = sql(dsn, """select p.proname f, has_function_privilege('authenticated', p.oid, 'execute') a,
                                has_function_privilege('anon', p.oid, 'execute') n, p.prosecdef d,
                                coalesce(array_to_string(p.proconfig, ','), '') = 'search_path=""' s
                           from pg_proc p join pg_namespace s on s.oid = p.pronamespace
                          where s.nspname = 'financeiro' and p.proname in ('previsoes_para_atualizar', 'previa_atualizacao_previsoes',
                                'atualizar_previsoes_fonte', 'receitas_totais_do_mes') order by 1""")
    assert {x['f']: (x['a'], x['n']) for x in linhas} == {
        'atualizar_previsoes_fonte': (True, False), 'previa_atualizacao_previsoes': (True, False),
        'previsoes_para_atualizar': (False, False), 'receitas_totais_do_mes': (True, False)}
    assert all(x['d'] and x['s'] for x in linhas)


# =====================================================================================================================
# 2. Total de receitas do mes: uma regra para Despesas, Receitas e Dashboard
# =====================================================================================================================

def totais(dsn, mes=MES):
    return rpc(dsn, 'receitas_totais_do_mes', PESSOAL, mes)


def test_total_do_mes_estorno_parcial_consorcio_e_pontual(banco):
    dsn, _ = banco
    # cenario de test_supabase_receitas: Salario 5.000 com 3.000 recebidos (parcial), Aluguel 1.200 recebido, Bonus 500
    # estornado (sem previsao), consorcio 40.000 previsto, venda 800 sem previsao, Aulas 600 previstas
    t = totais(dsn)
    assert D(str(t['previstas'])) == D('47600.00')   # 5.000 + 1.200 + 40.000 + 800 + 600 (estorno fora; parcial pelo previsto)
    assert D(str(t['recebidas'])) == D('5000.00')    # 3.000 + 1.200 + 800 (sem estorno e sem a previsao de consorcio)
    assert D(str(t['estornadas'])) == D('500.00')


def test_recebido_acima_do_previsto_conta_o_recebido(banco):
    dsn, ids = banco
    sql(dsn, 'update public.receita_realizada set valor_recebido = 1500 where item_receita_id = %s', (ids['aluguel'],))
    assert D(str(totais(dsn)['previstas'])) == D('47900.00')  # aluguel: 1.500 em vez de 1.200


def test_dashboard_usa_a_mesma_regra(banco):
    dsn, _ = banco
    painel = rpc(dsn, 'dashboard_resumo_tela', PESSOAL, MES[:7])['fluxo_caixa']['resumo']
    t = totais(dsn)
    assert D(str(painel['receitas_previstas'])) == D(str(t['previstas']))
    assert D(str(painel['receitas_recebidas'])) == D(str(t['recebidas']))


# =====================================================================================================================
# Reversao
# =====================================================================================================================

def _executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_reversao_recusa_com_valor_manual_e_reaplica(banco):
    dsn, _ = banco
    item = cenario(dsn)
    assert 'valor alterado manualmente' in str(erro(_executar, dsn, REVERSAO))
    sql(dsn, 'update public.receita_orcamento set valor_manual = false')  # so no cluster descartavel
    _executar(dsn, REVERSAO)
    assert not sql(dsn, "select 1 from information_schema.columns where table_name = 'receita_orcamento' and column_name = 'valor_manual'")
    assert not sql(dsn, "select 1 from pg_proc where proname = 'receitas_totais_do_mes'")
    _executar(dsn, MIGRATION)
    assert previa(dsn, item, '2027-03-01')['quantidade'] == 7  # a 04 perdeu a marca no cluster: volta a ser elegivel
