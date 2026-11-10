"""
Testes FIN-MVP-LANCAMENTOS-03, parte B (P14): a previa das parcelas no Novo Lancamento usa previa_compra, que planeja pelo
mesmo plano_compra que criar_compra grava. Aqui a prova de que a previa e exatamente o que fica gravado (numero, total,
competencia da fatura, valor e soma), em cluster local descartavel com dados ficticios (Cartao Teste 910, Pessoal). Sem
migration: nenhuma funcao do banco muda nesta parte.

Casos: a vista, 2 parcelas, 3 com centavos (R$ 100,00), 12, virada de ano, fatura paga no meio (a parcela vai para a
proxima aberta), sugestao de fatura pelo fechamento, mudanca de data, de cartao e de quantidade, e previa sem gravar.
"""
import uuid
from decimal import Decimal

import pytest

from tests.test_supabase_cartoes import ASSINATURAS, CARTAO, COMPRA, banco, fatura, pagar, rpc  # noqa: F401
from tests.test_supabase_recorrencia import ID, PG_BIN, cluster, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']


def previa(dsn, **campos):
    return rpc(dsn, 'previa_compra', PESSOAL, {**COMPRA, **campos})


def criar(dsn, **campos):
    return rpc(dsn, 'criar_compra', PESSOAL, {**COMPRA, **campos}, str(uuid.uuid4()))


def gravadas(dsn, descricao):
    return sql(dsn, 'select numero_parcela, total_parcelas, mes_fatura, valor from public.lancamento_agregado '
                    'where descricao = %s order by numero_parcela', (descricao,))


def da_previa(p):
    return [(x['numero'], x['total'], str(x['mes_fatura']), Decimal(str(x['valor']))) for x in p['parcelas']]


def do_banco(linhas):
    return [(x['numero_parcela'], x['total_parcelas'], str(x['mes_fatura']), x['valor']) for x in linhas]


def contagem(dsn):
    return sql(dsn, 'select count(*) n from public.lancamento_agregado')[0]['n']


@pytest.mark.parametrize('parcelas, valor, mes', [
    (1, '89.90', '2029-05-01'),     # a vista
    (2, '250.00', '2029-05-01'),
    (3, '100.00', '2029-05-01'),    # centavos
    (12, '1000.00', '2029-05-01'),  # doze
    (4, '500.00', '2029-11-01')])   # virada de ano
def test_previa_e_exatamente_o_que_fica_gravado(banco, parcelas, valor, mes):  # noqa: F811
    nome = f'Compra {parcelas}x {valor}'
    antes = contagem(banco)
    p = previa(banco, descricao=nome, total_parcelas=parcelas, valor=valor, mes_fatura=mes)
    assert contagem(banco) == antes  # a previa nao grava
    assert len(p['parcelas']) == parcelas and Decimal(str(p['soma'])) == Decimal(valor)
    criar(banco, descricao=nome, total_parcelas=parcelas, valor=valor, mes_fatura=mes)
    assert do_banco(gravadas(banco, nome)) == da_previa(p)


def test_centavos_seguem_a_regra_do_banco(banco):  # noqa: F811
    p = previa(banco, total_parcelas=3, valor='100.00')
    valores = [Decimal(str(x['valor'])) for x in p['parcelas']]
    assert sum(valores) == Decimal('100.00') and sorted(valores, reverse=True) == [Decimal('33.34'), Decimal('33.33'), Decimal('33.33')]
    assert [str(x['mes_fatura']) for x in p['parcelas']] == ['2029-05-01', '2029-06-01', '2029-07-01']


def test_virada_de_ano_nas_competencias(banco):  # noqa: F811
    p = previa(banco, total_parcelas=4, valor='500.00', mes_fatura='2029-11-01')
    assert [str(x['mes_fatura']) for x in p['parcelas']] == ['2029-11-01', '2029-12-01', '2030-01-01', '2030-02-01']


def test_fatura_paga_no_meio_vai_para_a_proxima_e_a_previa_mostra(banco):  # noqa: F811
    criar(banco, descricao='Abre faturas', total_parcelas=3, valor='30.00')
    pagar(banco, CARTAO, '2029-06-01')
    p = previa(banco, descricao='Depois da paga', total_parcelas=3, valor='90.00')
    assert [str(x['mes_fatura']) for x in p['parcelas']] == ['2029-05-01', '2029-07-01', '2029-08-01']
    assert [x['redirecionada'] for x in p['parcelas']] == [False, True, True]
    criar(banco, descricao='Depois da paga', total_parcelas=3, valor='90.00')
    assert do_banco(gravadas(banco, 'Depois da paga')) == da_previa(p)


def cartao_configurado(dsn, nome='Visa P14'):
    cartao = rpc(dsn, 'criar_cartao', PESSOAL, {'nome': nome, 'dia_fechamento': 3, 'dia_vencimento': 10}, str(uuid.uuid4()))['cartao_id']
    sql(dsn, 'update public.config_agregador set fechamento_confirmado = true where item_despesa_id = %s', (cartao,))
    return cartao


def test_sugestao_de_fatura_pelo_fechamento(banco):  # noqa: F811
    cartao = cartao_configurado(banco)
    antes, depois = (previa(banco, cartao_id=cartao, data_compra=d, mes_fatura='2029-05-01', total_parcelas=2) for d in ('2029-05-02', '2029-05-04'))
    assert (antes['sugestao']['situacao'], depois['sugestao']['situacao']) == ('SUGERIDA', 'SUGERIDA')
    assert antes['sugestao']['competencia'] != depois['sugestao']['competencia']  # depois do fechamento, a fatura seguinte
    # a previa usa a fatura escolhida no formulario (a sugestao so orienta a escolha, como ao gravar)
    assert str(antes['parcelas'][0]['mes_fatura']) == str(depois['parcelas'][0]['mes_fatura']) == '2029-05-01'


def test_mudar_quantidade_data_e_cartao_muda_a_previa_sem_gravar(banco):  # noqa: F811
    antes = contagem(banco)
    duas, seis = previa(banco, total_parcelas=2), previa(banco, total_parcelas=6)
    assert (len(duas['parcelas']), len(seis['parcelas'])) == (2, 6)
    outra_data = previa(banco, total_parcelas=2, data_compra='2029-05-20')
    assert [x['data_compra'] for x in outra_data['parcelas']][0] == '2029-05-20'
    assert contagem(banco) == antes
    criar(banco, descricao='Abre a fatura do 910', total_parcelas=1)
    outro = cartao_configurado(banco, 'Master P14')
    no_910, no_outro = previa(banco, total_parcelas=2), previa(banco, total_parcelas=2, cartao_id=outro)
    assert no_910['parcelas'][0]['fatura_id'] is not None and no_outro['parcelas'][0]['fatura_id'] is None  # faturas de cada cartao
    with pytest.raises(psycopg2.Error) as e:
        previa(banco, total_parcelas=2, cartao_id=911)  # Cartao Sem Config: a tela mostra o motivo
    assert 'vencimento' in str(e.value)
    assert contagem(banco) == antes + 1
