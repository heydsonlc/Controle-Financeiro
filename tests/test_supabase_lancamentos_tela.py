"""
Testes FIN-FIDELIDADE-MOVIMENTACOES-1 — leituras da tela original de Lancamentos (migration 20261109090000, secao 6).

Cenario FICTICIO do FIN-RECORRENCIA-1 (tests/supabase_local.py), copia por teste: Cartao Teste (910, Pessoal), Cartao B
(930, Perfil B). Receitas ficticias inseridas aqui. Formatos do Flask: LancamentoAgregado.to_dict, listar_despesas,
ReceitaRealizada / ReceitaOrcamento / ItemReceita.to_dict. So leitura: nada e gravado pelas funcoes.
"""
import uuid

import pytest

from tests.test_supabase_cartoes import CARTAO, CARTAO_B, COMPRA, rpc
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL, PERFIL_B = ID['PESSOAL'], ID['PERFIL_B']
FUNCOES = ['financeiro.compras_do_cartao_tela(integer, integer)', 'financeiro.despesas_diretas_tela(integer)',
           'financeiro.receitas_lancamentos_tela(integer, date, integer)']


@pytest.fixture
def banco(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    return dsn


def falha(dsn, funcao, *args, usuario=USUARIO_A):
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, funcao, *args, usuario=usuario)
    return erro.value.pgcode, erro.value.diag.message_primary


def contagens(dsn):
    return sql(dsn, """select (select count(*) from public.conta) c, (select count(*) from public.lancamento_agregado) l,
                              (select count(*) from public.receita_realizada) r, (select count(*) from public.movimento_financeiro) m""")[0]


def test_privilegios(banco):
    for funcao in FUNCOES:
        r = sql(banco, "select has_function_privilege('authenticated', %s, 'execute') as a, "
                       "has_function_privilege('anon', %s, 'execute') as n", (funcao, funcao))[0]
        assert (r['a'], r['n']) == (True, False), funcao


def test_compras_do_cartao_todos_os_meses_no_formato_do_flask(banco):
    rpc(banco, 'criar_compra', PESSOAL, COMPRA, str(uuid.uuid4()))
    rpc(banco, 'criar_compra', PESSOAL, {**COMPRA, 'descricao': 'Fone', 'total_parcelas': 1, 'data_compra': '2029-07-02',
                                         'mes_fatura': '2029-07-01'}, str(uuid.uuid4()))
    antes = contagens(banco)
    compras = rpc(banco, 'compras_do_cartao_tela', PESSOAL, CARTAO)
    assert contagens(banco) == antes
    novas = [c for c in compras if c['descricao'] in ('Notebook', 'Fone')]
    # Da mais recente a mais antiga pela data da compra (cada parcela tem a data do seu mes, como no Flask).
    assert [(c['descricao'], c['numero_parcela'], c['mes_fatura']) for c in novas] == [
        ('Notebook', 3, '2029-07-01'), ('Fone', 1, '2029-07-01'), ('Notebook', 2, '2029-06-01'), ('Notebook', 1, '2029-05-01')]
    assert set(novas[0]) == {'id', 'perfil_financeiro_id', 'item_agregado_id', 'categoria_cartao_id', 'descricao', 'valor',
                             'data_compra', 'mes_fatura', 'numero_parcela', 'total_parcelas', 'observacoes', 'is_recorrente',
                             'item_despesa_id', 'categoria_cartao'}
    datas = [c['data_compra'] for c in compras]
    assert datas == sorted(datas, reverse=True)
    # Isolamento: cartao de outro perfil e outro titular.
    assert falha(banco, 'compras_do_cartao_tela', PESSOAL, CARTAO_B)[1] == 'Cartao nao encontrado neste perfil'
    assert falha(banco, 'compras_do_cartao_tela', PESSOAL, CARTAO, usuario=USUARIO_B)[0] == '42501'


def test_despesas_diretas_todos_os_meses_sem_faturas(banco):
    criada = rpc(banco, 'criar_despesa', PESSOAL, {'nome': 'Padaria (lanc)', 'valor': '12.50', 'descricao': 'pao',
                                                   'categoria_id': 951, 'data_vencimento': '2030-02-03',
                                                   'debito_automatico': False, 'conta_bancaria_id': None}, str(uuid.uuid4()))
    lista = rpc(banco, 'despesas_diretas_tela', PESSOAL)
    esperadas = sql(banco, """select count(*) n from public.conta c where not coalesce(c.is_fatura_cartao, false)
                               and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, %s)""", (PESSOAL,))[0]['n']
    assert len(lista) == esperadas and not any(d['is_fatura_cartao'] for d in lista)
    d = next(x for x in lista if x['id'] == criada['conta_id'])
    assert (d['nome'], d['descricao'], d['tipo'], d['valor'], d['mes_competencia'], d['pago'], d['categoria_id']) == \
        ('Padaria (lanc)', 'pao', 'Simples', 12.5, '2030-02', False, 951)
    assert d['categoria']['id'] == 951
    vencimentos = [x['data_vencimento'] for x in lista]
    assert vencimentos == sorted(vencimentos, reverse=True)
    assert all(x['id'] != criada['conta_id'] for x in rpc(banco, 'despesas_diretas_tela', PERFIL_B, usuario=USUARIO_B))
    assert falha(banco, 'despesas_diretas_tela', PESSOAL, usuario=USUARIO_B)[0] == '42501'


def test_receitas_realizadas_previsoes_e_fontes(banco):
    def inserir(perfil, nome):
        item = sql(banco, "insert into public.item_receita (perfil_financeiro_id, nome, tipo, descricao, ativo, recorrente, "
                          "dia_previsto_pagamento) values (%s, %s, 'SALARIO', '', true, true, 5) returning id", (perfil, nome))[0]['id']
        sql(banco, "insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, valor_esperado, "
                   "periodicidade) values (%s, %s, '2031-03-01', 3000, 'MENSAL_FIXA'), (%s, %s, '2032-01-01', 3000, 'MENSAL_FIXA')",
            (perfil, item, perfil, item))
        sql(banco, "insert into public.receita_realizada (perfil_financeiro_id, item_receita_id, data_recebimento, valor_recebido, "
                   "mes_referencia) values (%s, %s, '2031-03-05', 3000, '2031-03-01')", (perfil, item))
        sql(banco, "insert into public.receita_realizada (perfil_financeiro_id, data_recebimento, valor_recebido, mes_referencia, "
                   "descricao) values (%s, '2031-04-10', 150, '2031-04-01', 'Venda avulsa')", (perfil,))
        return item
    item = inserir(PESSOAL, 'Salario (lanc)')
    inserir(PERFIL_B, 'Salario B (lanc)')
    tudo = rpc(banco, 'receitas_lancamentos_tela', PESSOAL, None, 2031)
    minhas = [r for r in tudo['realizadas'] if r['data_recebimento'] in ('2031-03-05', '2031-04-10')]
    assert [(r['valor_recebido'], r['orcamento_id'], r['item_receita_id'] == item) for r in minhas] == [(150, None, False), (3000, None, True)]
    assert minhas[1]['item_receita'] == {'id': item, 'nome': 'Salario (lanc)', 'tipo': 'SALARIO'}
    assert minhas[0]['item_receita'] is None and minhas[0]['estornada'] is False
    # Filtro do mes (ano_mes) e do ano (orcamentos).
    marco = rpc(banco, 'receitas_lancamentos_tela', PESSOAL, '2031-03-01', None)
    assert [r['data_recebimento'] for r in marco['realizadas']] == ['2031-03-05'] and marco['orcamentos'] == []
    assert [(o['mes_referencia'], o['valor_esperado']) for o in tudo['orcamentos'] if o['item_receita_id'] == item] == [('2031-03-01', 3000)]
    assert any(i['id'] == item and i['dia_previsto_pagamento'] == 5 for i in tudo['itens'])
    # Isolamento.
    assert all(i['nome'] != 'Salario B (lanc)' for i in tudo['itens'])
    assert falha(banco, 'receitas_lancamentos_tela', PESSOAL, None, 2031, usuario=USUARIO_B)[0] == '42501'
