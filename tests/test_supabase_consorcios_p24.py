"""
Testes P24 (FIN-CONSORCIOS-INTEGRACAO-01, retificacao e adendo 02; migration 20261227090000), em cluster local
descartavel com dados FICTICIOS. Consorcio em MOEDA: natureza, formula (premio = parcela da posicao de contemplacao x
numero de parcelas) e geracao das parcelas como antes.

A. contemplacao: a receita prevista do contrato e realizada (conta, data, credito), uma vez, com auditoria;
B. edicao de parcela pendente (esta / esta e as futuras), protegendo paga, com movimento e historica;
C. cadastro retroativo: contrato integral (1/10..10/10, premio integral) com as N primeiras parcelas pagas no historico,
   sem movimento bancario, reversiveis pelo mecanismo de regularizacao historica.
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_B, atribuir, cluster, copiar, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
D = Decimal
RAIZ = Path(__file__).resolve().parent.parent
MIGRATION = RAIZ / 'supabase/migrations/20261227090000_financeiro_consorcios_p24.sql'
REVERSAO = RAIZ / 'supabase/reversao/20261227090000_consorcios_p24_anterior.sql'


@pytest.fixture
def banco(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    return dsn


def erro(funcao, *args, **kw):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args, **kw)
    return e.value


def conta_pessoal(dsn):
    return sql(dsn, "select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")[0]['id']


def categoria(dsn):
    return sql(dsn, 'select id from public.categoria order by id limit 1')[0]['id']


def mes(dsn, deslocamento):
    """Primeiro dia do mes corrente (horario de Brasilia) + deslocamento em meses, como YYYY-MM."""
    return sql(dsn, "select to_char(date_trunc('month', financeiro.hoje_brasilia()) + make_interval(months => %s), 'YYYY-MM') m",
               (deslocamento,))[0]['m']


def criar(dsn, nome, **campos):
    dados = {'nome': nome, 'valor_inicial': 500, 'categoria_id': categoria(dsn), 'numero_parcelas': 10,
             'tipo_reajuste': 'fixo', 'valor_reajuste': 10, **campos}
    return rpc(dsn, 'criar_consorcio', PESSOAL, dados, str(uuid.uuid4()))


def parcelas(dsn, nome):
    return sql(dsn, "select c.id, c.numero_parcela n, c.total_parcelas t, c.descricao, c.valor, c.status_pagamento s, c.data_pagamento dp, "
                    "c.data_vencimento dv, to_char(c.mes_referencia, 'YYYY-MM') m from public.conta c join public.item_despesa d "
                    "on d.id = c.item_despesa_id where d.tipo = 'Consorcio' and d.nome like %s order by c.numero_parcela", (nome + ' - Parcela %',))


def contrato(dsn, nome):
    return sql(dsn, 'select * from public.contrato_consorcio where nome = %s', (nome,))[0]


def receita_contemplacao(dsn, contrato_id):
    return sql(dsn, 'select * from public.receita_realizada where observacoes like %s', (f'%consorcio_id={contrato_id}%',))


def dinheiro(dsn):
    return sql(dsn, "select (select count(*) from public.movimento_financeiro) movs, "
                    "(select md5(string_agg(t::text, '|' order by id)) from public.conta_bancaria t) bancos")[0]


def versao(dsn, conta):
    return sql(dsn, 'select financeiro.versao_despesa(%s) v', (conta,))[0]['v']


# =====================================================================================================================
# C. Cadastro retroativo e premio integral
# =====================================================================================================================

def test_contrato_novo_com_dez_prestacoes(banco):
    r = criar(banco, 'Consorcio Novo P24', mes_inicio=mes(banco, 1), mes_contemplacao=mes(banco, 8))
    p = parcelas(banco, 'Consorcio Novo P24')
    assert [(x['n'], x['t']) for x in p] == [(i, 10) for i in range(1, 11)]
    assert [x['descricao'] for x in p][:2] == ['Consorcio Novo P24 - Parcela 1/10', 'Consorcio Novo P24 - Parcela 2/10']
    assert [x['valor'] for x in p] == [D(500 + 10 * i) for i in range(10)]
    assert all(x['s'] == 'Pendente' for x in p)
    # premio = parcela da posicao 8 (570) x 10
    assert contrato(banco, 'Consorcio Novo P24')['valor_premio'] == D('5700.00') and r['parcelas_anteriores'] is None


def test_contrato_retroativo_quatro_pagas_seis_restantes(banco):
    antes = dinheiro(banco)
    r = criar(banco, 'Consorcio Diego Ficticio', mes_inicio=mes(banco, -4), mes_contemplacao=mes(banco, 3),
              parcelas_pagas_anteriores=4)
    p = parcelas(banco, 'Consorcio Diego Ficticio')
    # contrato integral: 1/10 a 10/10; a do mes corrente e a 5/10 (antes, cadastrada so como 1/6)
    assert [(x['n'], x['t']) for x in p] == [(i, 10) for i in range(1, 11)]
    assert p[4]['m'] == mes(banco, 0) and p[4]['descricao'].endswith('Parcela 5/10')
    # as 4 historicas: pagas no vencimento, sem movimento; as 6 restantes pendentes
    assert [(x['s'], x['dp'] == x['dv']) for x in p[:4]] == [('Pago', True)] * 4
    assert all(x['s'] == 'Pendente' and x['dp'] is None for x in p[4:])
    assert dinheiro(banco) == antes  # nenhum debito ficticio, saldos iguais
    hist = sql(banco, 'select lote, conta_id, tipo, valor from financeiro.regularizacao_historica where conta_id = any(%s) order by conta_id',
               ([x['id'] for x in p[:4]],))
    assert len(hist) == 4 and len({h['lote'] for h in hist}) == 1 and {h['tipo'] for h in hist} == {'DESPESA'}
    assert r['parcelas_anteriores']['quantidade'] == 4 and D(str(r['parcelas_anteriores']['valor'])) == D('2060.00')  # 500+510+520+530
    # premio integral: posicao 8 (570) x 10 = 5.700 (com 6 parcelas, 570 x 6 = 3.420)
    c = contrato(banco, 'Consorcio Diego Ficticio')
    assert (c['numero_parcelas'], c['valor_premio']) == (10, D('5700.00'))
    rec = receita_contemplacao(banco, c['id'])
    assert len(rec) == 1 and rec[0]['valor_recebido'] == D('5700.00') and rec[0]['conta_bancaria_id'] is None
    assert str(rec[0]['mes_referencia'])[:7] == mes(banco, 3)


def test_retroativo_com_valores_diferentes_por_reajuste_percentual(banco):
    criar(banco, 'Consorcio Percentual P24', valor_inicial=400, tipo_reajuste='percentual', valor_reajuste=5,
          mes_inicio=mes(banco, -2), mes_contemplacao=mes(banco, 1), parcelas_pagas_anteriores=2)
    p = parcelas(banco, 'Consorcio Percentual P24')
    assert [x['valor'] for x in p[:4]] == [D('400.00'), D('420.00'), D('440.00'), D('460.00')]
    assert contrato(banco, 'Consorcio Percentual P24')['valor_premio'] == D('4600.00')  # posicao 4 (460) x 10


@pytest.mark.parametrize('pagas, deslocamento, trecho', [
    (10, -10, 'menos que o total'),
    (5, -4, 'anteriores ao mes corrente'),
    ('x', -4, 'numero inteiro'),
])
def test_retroativo_invalido_nao_grava(banco, pagas, deslocamento, trecho):
    e = erro(criar, banco, 'Consorcio Invalido P24', mes_inicio=mes(banco, deslocamento), parcelas_pagas_anteriores=pagas)
    assert trecho in str(e)
    assert not sql(banco, "select 1 from public.contrato_consorcio where nome = 'Consorcio Invalido P24'")
    assert not parcelas(banco, 'Consorcio Invalido P24')


def test_historico_reversivel_pelo_mecanismo_existente(banco):
    r = criar(banco, 'Consorcio Reverte P24', mes_inicio=mes(banco, -3), parcelas_pagas_anteriores=3)
    rpc(banco, 'reverter_regularizacao_historica', PESSOAL, r['parcelas_anteriores']['lote'], str(uuid.uuid4()))
    assert [x['s'] for x in parcelas(banco, 'Consorcio Reverte P24')[:3]] == ['Pendente'] * 3


def test_regenerar_preserva_as_historicas(banco):
    criar(banco, 'Consorcio Regenera P24', mes_inicio=mes(banco, -4), parcelas_pagas_anteriores=4)
    c = contrato(banco, 'Consorcio Regenera P24')
    rpc(banco, 'editar_consorcio', PESSOAL, c['id'], {'valor_inicial': 600})
    rpc(banco, 'regenerar_parcelas_consorcio', PESSOAL, c['id'], {'categoria_id': categoria(banco)})
    p = parcelas(banco, 'Consorcio Regenera P24')
    assert [x['valor'] for x in p[:4]] == [D('500.00'), D('510.00'), D('520.00'), D('530.00')]  # historicas intactas
    assert p[4]['valor'] == D('640.00') and len(p) == 10                                          # 600 + 4 x 10


# =====================================================================================================================
# A. Contemplacao
# =====================================================================================================================

def realizar(dsn, receita, chave=None, **dados):
    return rpc(dsn, 'realizar_contemplacao_consorcio', PESSOAL, receita,
               {'conta_bancaria_id': conta_pessoal(dsn), 'data_recebimento': '2027-03-10', **dados}, chave or str(uuid.uuid4()))


def test_realizar_contemplacao_cria_o_credito_uma_vez(banco):
    criar(banco, 'Consorcio Contempla P24', mes_inicio=mes(banco, 0), mes_contemplacao=mes(banco, 2))
    c = contrato(banco, 'Consorcio Contempla P24')
    rec = receita_contemplacao(banco, c['id'])[0]
    saldo = sql(banco, 'select financeiro.saldo_da_conta(%s) s', (conta_pessoal(banco),))[0]['s']
    chave = str(uuid.uuid4())
    r = realizar(banco, rec['id'], chave=chave)
    assert D(str(r['valor_recebido'])) == c['valor_premio'] == D('5200.00')  # posicao 3 (520) x 10
    depois = receita_contemplacao(banco, c['id'])[0]
    assert (depois['id'], depois['conta_bancaria_id'], str(depois['data_recebimento'])) == (rec['id'], conta_pessoal(banco), '2027-03-10')
    mov = sql(banco, 'select tipo, valor, origem from public.movimento_financeiro where receita_realizada_id = %s', (rec['id'],))
    assert mov == [{'tipo': 'CREDITO', 'valor': D('5200.00'), 'origem': 'RECEITA'}]
    assert sql(banco, 'select financeiro.saldo_da_conta(%s) s', (conta_pessoal(banco),))[0]['s'] == saldo + D('5200.00')
    # repetir com a mesma chave devolve o mesmo; outra chave e recusada (ja realizada); nenhuma receita nova
    assert realizar(banco, rec['id'], chave=chave)['repetida'] is True
    assert 'ja foi realizada' in str(erro(realizar, banco, rec['id']))
    assert len(receita_contemplacao(banco, c['id'])) == 1
    assert sql(banco, "select count(*) n from financeiro.operacao_receita where operacao = 'realizar_contemplacao_consorcio'")[0]['n'] == 1
    # editar o contrato depois nao reescreve a contemplacao realizada (regra existente)
    rpc(banco, 'editar_consorcio', PESSOAL, c['id'], {'valor_inicial': 700})
    assert receita_contemplacao(banco, c['id'])[0]['valor_recebido'] == D('5200.00')


def test_valor_diferente_exige_justificativa(banco):
    criar(banco, 'Consorcio Valor P24', mes_inicio=mes(banco, 0), mes_contemplacao=mes(banco, 1))
    rec = receita_contemplacao(banco, contrato(banco, 'Consorcio Valor P24')['id'])[0]
    assert 'justificativa' in str(erro(realizar, banco, rec['id'], valor_recebido='5000.00'))
    realizar(banco, rec['id'], valor_recebido='5000.00', justificativa='Lance com desconto')
    depois = sql(banco, 'select valor_recebido, observacoes from public.receita_realizada where id = %s', (rec['id'],))[0]
    assert depois['valor_recebido'] == D('5000.00') and 'Lance com desconto' in depois['observacoes']
    assert 'consorcio_id=' in depois['observacoes']


def test_so_contemplacao_e_so_do_perfil(banco):
    criar(banco, 'Consorcio Perfil P24', mes_inicio=mes(banco, 0), mes_contemplacao=mes(banco, 1))
    rec = receita_contemplacao(banco, contrato(banco, 'Consorcio Perfil P24')['id'])[0]
    comum = sql(banco, "select id from public.receita_realizada where coalesce(observacoes, '') !~ 'consorcio_id=' order by id limit 1")
    if comum:
        assert erro(realizar, banco, comum[0]['id']).diag.message_hint in ('NAO_E_CONTEMPLACAO', None)
    e = erro(rpc, banco, 'realizar_contemplacao_consorcio', PESSOAL, rec['id'], {'conta_bancaria_id': conta_pessoal(banco)},
             str(uuid.uuid4()), usuario=USUARIO_B)
    assert e.pgcode == '42501'
    assert receita_contemplacao(banco, contrato(banco, 'Consorcio Perfil P24')['id'])[0]['conta_bancaria_id'] is None


def test_receitas_do_mes_mostra_prevista_e_depois_recebida(banco):
    criar(banco, 'Consorcio Tela P24', mes_inicio=mes(banco, 0), mes_contemplacao=mes(banco, 1))
    c = contrato(banco, 'Consorcio Tela P24')
    rec = receita_contemplacao(banco, c['id'])[0]

    def situacao():
        linhas = rpc(banco, 'receitas_totais_do_mes', PESSOAL, mes(banco, 1) + '-01')
        return linhas
    antes = situacao()
    realizar(banco, rec['id'])
    depois = situacao()
    assert D(str(antes['previstas'])) == D(str(depois['previstas']))          # previsto uma vez, antes e depois
    assert D(str(depois['recebidas'])) - D(str(antes['recebidas'])) == c['valor_premio']


# =====================================================================================================================
# B. Edicao de parcelas
# =====================================================================================================================

def editar(dsn, conta, escopo, **dados):
    return rpc(dsn, 'editar_parcela_consorcio', PESSOAL, conta, versao(dsn, conta), dados, escopo)


def test_editar_esta_parcela(banco):
    criar(banco, 'Consorcio Edita P24', mes_inicio=mes(banco, 1))
    p = parcelas(banco, 'Consorcio Edita P24')
    r = editar(banco, p[2]['id'], 'unica', valor='555.55', data_vencimento=str(p[2]['dv'].replace(day=10)))
    assert r['atualizadas'] == 1
    depois = parcelas(banco, 'Consorcio Edita P24')
    assert (depois[2]['valor'], depois[2]['dv'].day) == (D('555.55'), 10)
    assert [x['valor'] for i, x in enumerate(depois) if i != 2] == [x['valor'] for i, x in enumerate(p) if i != 2]
    assert depois[2]['descricao'] == p[2]['descricao']  # numeracao preservada


def test_editar_esta_e_as_futuras_preserva_paga_e_anteriores(banco):
    criar(banco, 'Consorcio Futuras P24', mes_inicio=mes(banco, -2), parcelas_pagas_anteriores=2)
    p = parcelas(banco, 'Consorcio Futuras P24')
    banco_id = conta_pessoal(banco)
    rpc(banco, 'pagar_despesa', PESSOAL, p[5]['id'], {'conta_bancaria_id': banco_id, 'data_pagamento': '2027-01-05',
                                                      'valor_pago': str(p[5]['valor']), 'valor_devido': str(p[5]['valor'])}, str(uuid.uuid4()))
    r = editar(banco, p[3]['id'], 'futuras', valor='600.00')
    depois = parcelas(banco, 'Consorcio Futuras P24')
    assert [x['valor'] for x in depois[:3]] == [x['valor'] for x in p[:3]]       # anteriores (2 historicas + a 3a) intactas
    assert depois[5]['valor'] == p[5]['valor'] and depois[5]['s'] == 'Pago'       # paga intacta
    assert all(x['valor'] == D('600.00') for i, x in enumerate(depois) if i >= 3 and i != 5)
    assert r['atualizadas'] == 6 and [x['parcela'] for x in r['preservadas']] == [6]


def test_parcela_paga_historica_ou_versao_velha_e_recusada(banco):
    criar(banco, 'Consorcio Bloqueio P24', mes_inicio=mes(banco, -1), parcelas_pagas_anteriores=1)
    p = parcelas(banco, 'Consorcio Bloqueio P24')
    assert 'Despesa paga' in str(erro(editar, banco, p[0]['id'], 'unica', valor='1.00'))
    e = erro(rpc, banco, 'editar_parcela_consorcio', PESSOAL, p[1]['id'], 'antiga', {'valor': '1.00'}, 'unica')
    assert 'alterada por outra operacao' in str(e)
    assert 'Escolha' in str(erro(editar, banco, p[1]['id'], 'todas', valor='1.00'))
    assert parcelas(banco, 'Consorcio Bloqueio P24') == p


def test_editar_nao_toca_outro_contrato(banco):
    criar(banco, 'Consorcio Um P24', mes_inicio=mes(banco, 1))
    criar(banco, 'Consorcio Dois P24', mes_inicio=mes(banco, 1))
    outro = parcelas(banco, 'Consorcio Dois P24')
    editar(banco, parcelas(banco, 'Consorcio Um P24')[0]['id'], 'futuras', valor='999.00')
    assert parcelas(banco, 'Consorcio Dois P24') == outro


# =====================================================================================================================
# Seguranca e reversao
# =====================================================================================================================

def test_permissoes(banco):
    linhas = sql(banco, """select p.proname f, has_function_privilege('authenticated', p.oid, 'execute') a,
                                  has_function_privilege('anon', p.oid, 'execute') n
                             from pg_proc p join pg_namespace s on s.oid = p.pronamespace
                            where s.nspname = 'financeiro' and p.proname in ('realizar_contemplacao_consorcio', 'editar_parcela_consorcio',
                                  'registrar_parcelas_anteriores_consorcio', 'consorcio_parcelas_anteriores') order by 1""")
    assert {x['f']: (x['a'], x['n']) for x in linhas} == {
        'consorcio_parcelas_anteriores': (False, False), 'editar_parcela_consorcio': (True, False),
        'realizar_contemplacao_consorcio': (True, False), 'registrar_parcelas_anteriores_consorcio': (False, False)}


def _executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_reversao_e_reaplicacao(banco):
    criar(banco, 'Consorcio Antes P24', mes_inicio=mes(banco, -2), parcelas_pagas_anteriores=2)
    _executar(banco, REVERSAO)
    assert not sql(banco, "select 1 from pg_proc where proname = 'realizar_contemplacao_consorcio'")
    assert 'parcelas_pagas_anteriores' not in sql(banco, "select prosrc from pg_proc where proname = 'criar_consorcio'")[0]['prosrc']
    assert [x['s'] for x in parcelas(banco, 'Consorcio Antes P24')[:2]] == ['Pago', 'Pago']  # dados ficam
    _executar(banco, MIGRATION)
    criar(banco, 'Consorcio Depois P24', mes_inicio=mes(banco, -1), parcelas_pagas_anteriores=1)
    assert parcelas(banco, 'Consorcio Depois P24')[0]['s'] == 'Pago'
