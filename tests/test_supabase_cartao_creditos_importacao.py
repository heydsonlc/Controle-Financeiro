"""
Testes FIN-CARTAO-CREDITOS-01 (P18), em cluster local descartavel com o cenario FICTICIO de FIN-CARTAO-NUBANK-CREDITOS-01
(Cartao Teste 910, 05/2029). Sem migration: conferem o contrato do banco de que a tela depende. A natureza da linha vem
do arquivo (tipo_movimento); o valor chega sempre positivo; a analise e a confirmacao separam credito de debito:
- compra, credito, IOF devolvido, estorno integral e parcial, credito e debito de mesmo valor;
- reimportacao de credito e de compra; importacao conjunta; totais da fatura.
A mesma linha sem o tipo e tratada como compra ja lancada: e o que a tela provocava ao omitir o campo.
"""
from decimal import Decimal

import pytest

from tests.test_supabase_cartao_despesas_fixas import MES, PESSOAL, banco, md5_compras  # noqa: F401
from tests.test_supabase_cartao_nubank_creditos import D, a_pagar, compra, creditos, importar, linha, md5, previa
from tests.test_supabase_cartoes import CARTAO
from tests.test_supabase_recorrencia import PG_BIN, cluster  # noqa: F401
from tests.test_supabase_recorrencia_cartao import falha

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')


def credito_positivo(n, descricao, valor, **extra):
    """Como o PDF ou a coluna Credito da Caixa enviam: valor positivo, a natureza vem no tipo (nao no sinal)."""
    return {**linha(n, descricao, valor, categoria=None), 'tipo_movimento': 'credito', **extra}


def classes(resposta):
    return [(l['tipo_movimento'], l['classificacao_importacao'], l['status']) for l in resposta['linhas']]


def test_compra_comum(banco):
    r = previa(banco, linha(1, 'Padaria', '8.00'))
    assert classes(r) == [('debito', 'COMPRA', 'valido')]
    assert importar(banco, linha(1, 'Padaria', '8.00'))['inseridos'] == 1
    assert (a_pagar(banco), creditos(banco)) == (D('8.00'), [])


def test_credito_com_valor_positivo_preserva_a_natureza(banco):
    """Nao depende do sinal: a natureza informada pelo arquivo basta, e nada entra como compra."""
    compras = compra(banco, 'Mercado', '100.00')
    antes = md5_compras(banco)
    ajuste = credito_positivo(1, 'Credito de ajuste', '30.00')
    assert classes(previa(banco, ajuste)) == [('credito', 'CREDITO', 'valido')]
    res = importar(banco, ajuste)
    assert (res['inseridos'], res['creditos'], D(res['total_creditos'])) == (0, 1, D('30.00'))
    assert md5_compras(banco) == antes and compras
    assert a_pagar(banco) == D('70.00')


def test_devolucao_de_iof_com_a_compra_de_mesmo_valor_lancada(banco):
    """Mesmo valor, data e cartao da cobranca de IOF: com o tipo, e credito; sem ele, parece a compra ja lancada."""
    compra(banco, 'Nuvem', '28.47')
    iof = compra(banco, 'IOF de "Nuvem"', '0.99')
    volta = linha(1, 'IOF de volta de Nuvem', '-0.99')
    r = previa(banco, volta)['linhas'][0]
    assert (r['classificacao_importacao'], r['status'], r['conciliacao']) == ('CREDITO', 'valido', None)
    assert (r['credito']['natureza'], r['credito']['compra']['id']) == ('IOF_DEVOLVIDO', iof)

    sem_tipo = {k: v for k, v in volta.items() if k != 'tipo_movimento'}
    errada = previa(banco, sem_tipo)['linhas'][0]
    assert (errada['tipo_movimento'], errada['status'], errada['conciliacao']['lancamento_id']) == ('debito', 'conciliado', iof)

    importar(banco, volta)
    assert a_pagar(banco) == D('28.47')
    assert [(c['natureza'], D(c['valor']), c['lancamento_id']) for c in creditos(banco)] == [('IOF_DEVOLVIDO', D('0.99'), iof)]


def test_estorno_integral(banco):
    loja = compra(banco, 'Loja Som', '64.90')
    compra(banco, 'Mercado', '10.00')
    integral = linha(1, 'Estorno de "Loja Som" (Som)', '-64.90')
    r = previa(banco, integral)['linhas'][0]
    assert (r['classificacao_importacao'], r['credito']['compra']['id'], r['credito']['parcial']) == ('CREDITO', loja, False)
    importar(banco, integral)
    assert a_pagar(banco) == D('10.00')


def test_estorno_parcial(banco):
    loja = compra(banco, 'Loja Som', '100.00')
    parcial = linha(1, 'Estorno de "Loja Som" (Som)', '-25.50')
    r = previa(banco, parcial)['linhas'][0]
    assert (r['credito']['compra']['id'], r['credito']['parcial']) == (loja, True)
    importar(banco, parcial)
    assert a_pagar(banco) == D('74.50')


def test_credito_e_debito_de_mesmo_valor_data_e_competencia(banco):
    """Mesma descricao, valor e data: naturezas diferentes nunca sao duplicidade uma da outra."""
    debito = linha(1, 'Loja Igual', '50.00')
    credito = linha(2, 'Loja Igual', '-50.00')
    r = previa(banco, debito, credito)
    assert classes(r) == [('debito', 'COMPRA', 'valido'), ('credito', 'CREDITO', 'valido')]
    assert [l['duplicidade'] for l in r['linhas']] == [None, None]
    res = importar(banco, debito, credito)
    assert (res['inseridos'], res['creditos'], res['duplicados']) == (1, 1, 0)
    assert a_pagar(banco) == D('0.00')


def test_credito_de_mesmo_valor_de_compra_ja_lancada_nao_e_duplicidade(banco):
    compra(banco, 'Loja Igual', '50.00')
    r = previa(banco, linha(1, 'Loja Igual', '-50.00'))
    assert classes(r) == [('credito', 'CREDITO', 'valido')]
    assert r['linhas'][0]['conciliacao'] is None


def test_reimportacao_de_credito_nao_abate_de_novo(banco):
    compra(banco, 'Mercado', '100.00')
    ajuste = linha(1, 'Credito de ajuste', '-3.00')
    importar(banco, ajuste)
    antes = (md5(banco, 'financeiro.credito_fatura'), a_pagar(banco))
    assert classes(previa(banco, ajuste)) == [('credito', 'JA_EXISTENTE', 'duplicado')]
    assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, [ajuste], '00000000-0000-4000-8000-000000000018')[1] \
        == 'Nenhuma linha para importar'
    assert (md5(banco, 'financeiro.credito_fatura'), a_pagar(banco)) == antes


def test_reimportacao_de_compra_nao_grava_de_novo(banco):
    padaria = linha(1, 'Padaria', '8.00')
    importar(banco, padaria)
    antes = (md5_compras(banco), a_pagar(banco))
    assert classes(previa(banco, padaria)) == [('debito', 'JA_EXISTENTE', 'duplicado')]
    assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, [padaria], '00000000-0000-4000-8000-000000000019')[1] \
        == 'Nenhuma linha para importar'
    assert (md5_compras(banco), a_pagar(banco)) == antes


def test_importacao_conjunta_preserva_os_totais(banco):
    compra(banco, 'Nuvem', '28.47')
    compra(banco, 'IOF de "Nuvem"', '0.99')
    compra(banco, 'Loja Som', '799.90')
    arquivo = [linha(1, 'Padaria', '8.00'), linha(2, 'IOF de volta de Nuvem', '-0.99'),
               linha(3, 'Estorno de "Loja Som" (Som)', '-50.22'), linha(4, 'Credito de ajuste', '-3.00'),
               linha(5, 'Pagamento recebido', '-900.00', data='2029-04-30'), linha(6, 'Farmacia', '30.00')]
    v = previa(banco, *arquivo)['validacoes']
    assert (Decimal(v['total_importavel']), v['creditos_a_abater'], D(v['total_creditos_a_abater'])) == (D('38.00'), 3, D('54.21'))
    res = importar(banco, *arquivo)
    assert (res['inseridos'], res['creditos'], D(res['total_creditos'])) == (2, 3, D('54.21'))
    # compras: 829,36 + 38,00; creditos: 54,21. O pagamento recebido fica fora.
    assert a_pagar(banco) == D('813.15')
    # a segunda passada nao muda nada
    antes = (md5_compras(banco), md5(banco, 'financeiro.credito_fatura'), a_pagar(banco))
    assert all(l['status'] in ('duplicado', 'ignorado') for l in previa(banco, *arquivo)['linhas'])
    assert (md5_compras(banco), md5(banco, 'financeiro.credito_fatura'), a_pagar(banco)) == antes


# Pendencias que dependem de migration (nao autorizada neste contrato): xfail estrito, para acusar quando forem corrigidas.
@pytest.mark.xfail(strict=True, reason='pagamento_fatura e testado antes do estorno em analisar_importacao_cartao')
def test_estorno_com_pagamento_no_texto_continua_credito(banco):
    r = previa(banco, linha(1, 'Estorno de "Pagamento Facil Loja"', '-20.00'))
    assert classes(r) == [('credito', 'CREDITO', 'valido')]


@pytest.mark.xfail(strict=True, reason='a chave do credito usa o texto e a trava OUTRA_FONTE so olha compras novas')
def test_mesmo_credito_por_outro_tipo_de_arquivo_nao_abate_duas_vezes(banco):
    compra(banco, 'Mercado', '100.00')
    importar(banco, {**linha(1, 'Estorno de "Loja" (Som)', '-20.00'), 'origem_importacao': 'csv'})
    try:
        importar(banco, {**linha(1, 'Estorno de Loja', '-20.00'), 'origem_importacao': 'pdf'})
    except psycopg2.Error:
        pass
    assert a_pagar(banco) == D('80.00')
