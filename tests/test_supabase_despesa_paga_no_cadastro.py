"""
Testes FIN-MVP-CADASTRO-UNIFICADO-02 (migration 20261230090000) — despesa direta cadastrada e paga na mesma operacao,
em cluster PostgreSQL local descartavel e com dados ficticios.

criar_despesa_paga chama, na mesma transacao, o cadastro oficial e o pagamento oficial (o do botao Pagar): o resultado
tem de ser o mesmo de cadastrar e depois pagar; se o pagamento for recusado, a despesa tambem nao e gravada; repetir a
chamada nao duplica despesa nem pagamento.
"""
import uuid
from decimal import Decimal

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_categorias_recorrencias import CATEGORIA, banco, erro  # noqa: F401
from tests.test_supabase_despesas import _paralelo
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, USUARIO_B, cluster, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
NOME = 'Farmacia paga no cadastro'


def conta_bancaria(dsn, nome='Conta Pessoal (A)'):
    """A conta do cenario, ja com o saldo calculado (um primeiro pagamento, de outra despesa, faz o banco calcula-lo)."""
    banco_id = sql(dsn, 'select id from public.conta_bancaria where nome = %s', (nome,))[0]['id']
    if sql(dsn, 'select saldo_atual s from public.conta_bancaria where id = %s', (banco_id,))[0]['s'] is None:
        rpc(dsn, 'criar_despesa_paga', PESSOAL, dados(nome='Despesa anterior', valor='1.00'),
            {'conta_bancaria_id': banco_id, 'data_pagamento': '2027-03-01'}, str(uuid.uuid4()))
    return banco_id


def dados(**extra):
    return {'nome': NOME, 'valor': '87.40', 'categoria_id': CATEGORIA, 'data_vencimento': '2027-03-10', 'descricao': 'pix', **extra}


def paga(dsn, banco_id, chave=None, usuario=USUARIO_A, perfil=PESSOAL, pagamento=None, **extra):
    return rpc(dsn, 'criar_despesa_paga', perfil, dados(**extra),
               {'conta_bancaria_id': banco_id, 'data_pagamento': '2027-03-10'} if pagamento is None else pagamento,
               chave or str(uuid.uuid4()), usuario=usuario)


def retrato(dsn):
    """Tudo o que a operacao pode tocar: nada disto pode mudar quando ela e recusada."""
    return sql(dsn, """select (select count(*) from public.item_despesa) itens, (select count(*) from public.conta) contas,
        (select count(*) from public.movimento_financeiro) movimentos, (select count(*) from financeiro.pagamento_fatura) pagamentos,
        (select count(*) from financeiro.operacao_despesa) operacoes,
        (select md5(string_agg(id || ':' || saldo_atual, '|' order by id)) from public.conta_bancaria) saldos""")[0]


def saldo(dsn, banco_id):
    return sql(dsn, 'select saldo_atual s from public.conta_bancaria where id = %s', (banco_id,))[0]['s']


def da_despesa(dsn):
    return sql(dsn, "select c.id, c.valor, c.status_pagamento, c.data_pagamento::text data_pagamento, c.conta_bancaria_id, c.mes_referencia::text mes "
                    "from public.conta c where c.descricao = %s order by c.id", (NOME,))


# =====================================================================================================================
# 1. Uma operacao: despesa, pagamento, movimento e saldo
# =====================================================================================================================

def test_cadastra_e_paga_com_movimento_saldo_e_registro_de_pagamento(banco):
    banco_id = conta_bancaria(banco)
    antes, s0 = retrato(banco), saldo(banco, banco_id)
    r = paga(banco, banco_id)
    assert r['paga'] is True and r['repetida'] is False and r['recorrente'] is False
    assert r['competencia'] == '2027-03-01'
    pg = r['pagamento']
    assert (Decimal(str(pg['valor_pago'])), Decimal(str(pg['valor_devido'])), pg['conta_bancaria_id'], pg['data_pagamento']) == (
        Decimal('87.40'), Decimal('87.40'), banco_id, '2027-03-10')
    assert Decimal(str(pg['saldo_conta'])) == s0 - Decimal('87.40') == saldo(banco, banco_id)
    linhas = da_despesa(banco)
    assert len(linhas) == 1
    assert linhas[0] == {'id': r['conta_id'], 'valor': Decimal('87.40'), 'status_pagamento': 'Pago', 'data_pagamento': '2027-03-10',
                         'conta_bancaria_id': banco_id, 'mes': '2027-03-01'}
    mov = sql(banco, 'select tipo, valor, conta_bancaria_id, conta_id, origem, data_movimento::text d from public.movimento_financeiro where id = %s',
              (pg['movimento_id'],))[0]
    assert mov == {'tipo': 'DEBITO', 'valor': Decimal('87.40'), 'conta_bancaria_id': banco_id, 'conta_id': r['conta_id'], 'origem': 'DESPESA',
                   'd': '2027-03-10'}
    assert sql(banco, 'select count(*) n from financeiro.pagamento_fatura where fatura_id = %s and movimento_id = %s',
               (r['conta_id'], pg['movimento_id']))[0]['n'] == 1
    depois = retrato(banco)
    assert (depois['itens'] - antes['itens'], depois['contas'] - antes['contas'], depois['movimentos'] - antes['movimentos'],
            depois['pagamentos'] - antes['pagamentos'], depois['operacoes'] - antes['operacoes']) == (1, 1, 1, 1, 2)


def test_resultado_igual_ao_de_cadastrar_e_depois_pagar(banco):
    """A mesma operacao financeira do botao Pagar: a despesa paga no cadastro e a paga depois ficam identicas."""
    banco_id = conta_bancaria(banco)
    a = paga(banco, banco_id)
    b = rpc(banco, 'criar_despesa', PESSOAL, dados(), str(uuid.uuid4()))
    rpc(banco, 'pagar_despesa', PESSOAL, b['conta_id'], {'conta_bancaria_id': banco_id, 'data_pagamento': '2027-03-10',
                                                        'valor_pago': '87.40', 'valor_devido': '87.40'}, str(uuid.uuid4()))
    campos = ("valor, status_pagamento, data_pagamento, conta_bancaria_id, mes_referencia, data_vencimento, descricao, observacoes, "
              "debito_automatico, numero_parcela, total_parcelas, is_fatura_cartao, status_fatura")
    assert (sql(banco, f'select {campos} from public.conta where id = %s', (a['conta_id'],))
            == sql(banco, f'select {campos} from public.conta where id = %s', (b['conta_id'],)))
    mov = 'select tipo, valor, conta_bancaria_id, origem, ajustavel, data_movimento, descricao from public.movimento_financeiro where conta_id = %s'
    assert sql(banco, mov, (a['conta_id'],)) == sql(banco, mov, (b['conta_id'],))
    pag = 'select origem, valor_executado, tipo_ajuste, justificativa from financeiro.pagamento_fatura where fatura_id = %s'
    assert sql(banco, pag, (a['conta_id'],)) == sql(banco, pag, (b['conta_id'],))
    # o estorno e o de sempre: a despesa paga no cadastro volta a pendente e o saldo e devolvido
    s = saldo(banco, banco_id)
    dp = rpc(banco, 'dados_pagamento_despesa', PESSOAL, a['conta_id'])
    rpc(banco, 'estornar_pagamento_despesa', PESSOAL, a['conta_id'], a['pagamento']['movimento_id'],
        {'motivo': 'teste de estorno', 'data_estorno': '2027-03-11'}, str(uuid.uuid4()))
    assert dp['despesa']['paga'] is True
    assert sql(banco, 'select status_pagamento s from public.conta where id = %s', (a['conta_id'],))[0]['s'] == 'Pendente'
    assert saldo(banco, banco_id) == s + Decimal('87.40')


# =====================================================================================================================
# 2. Tudo ou nada
# =====================================================================================================================

@pytest.mark.parametrize('pagamento, trecho', [
    ({'conta_bancaria_id': 999999, 'data_pagamento': '2027-03-10'}, ''),            # conta inexistente
    ({'conta_bancaria_id': None, 'data_pagamento': '2027-03-10'}, 'conta bancaria'),
    ({'data_pagamento': '2027-03-10'}, 'conta bancaria'),
    ({'conta_bancaria_id': 'x', 'data_pagamento': '2027-03-10'}, ''),
    ('CONTA', 'data do pagamento'),                                                # sem data (conta valida)
    ('DATA_RUIM', ''),
    ('OUTRO_PERFIL', ''),                                                          # conta bancaria de outro perfil
])
def test_pagamento_recusado_nao_deixa_despesa_nem_movimento(banco, pagamento, trecho):
    banco_id = conta_bancaria(banco)
    if pagamento == 'CONTA':
        pagamento = {'conta_bancaria_id': banco_id}
    elif pagamento == 'DATA_RUIM':
        pagamento = {'conta_bancaria_id': banco_id, 'data_pagamento': '2027-02-31'}
    elif pagamento == 'OUTRO_PERFIL':
        outra = sql(banco, 'select id from public.conta_bancaria where perfil_financeiro_id <> %s order by id limit 1', (PESSOAL,))
        if not outra:
            pytest.skip('cenario sem conta bancaria de outro perfil')
        pagamento = {'conta_bancaria_id': outra[0]['id'], 'data_pagamento': '2027-03-10'}
    antes = retrato(banco)
    e = erro(paga, banco, banco_id, pagamento=pagamento)
    assert trecho in (e.diag.message_primary or '').lower()
    assert retrato(banco) == antes
    assert da_despesa(banco) == []


def test_dados_da_despesa_invalidos_nao_gravam_nada(banco):
    banco_id = conta_bancaria(banco)
    antes = retrato(banco)
    for extra in ({'valor': '0'}, {'nome': ''}, {'categoria_id': 999999}, {'data_vencimento': None}):
        erro(paga, banco, banco_id, **extra)
    assert 'so para despesa direta' in erro(paga, banco, banco_id, recorrente=True, tipo_recorrencia='mensal').diag.message_primary
    assert retrato(banco) == antes


def test_sem_permissao_no_perfil_nada_e_gravado(banco):
    banco_id = conta_bancaria(banco)
    antes = retrato(banco)
    assert erro(paga, banco, banco_id, usuario=USUARIO_B).pgcode == '42501'
    assert retrato(banco) == antes


# =====================================================================================================================
# 3. Sem duplicar
# =====================================================================================================================

def test_repetir_a_mesma_chave_devolve_o_mesmo_resultado(banco):
    banco_id = conta_bancaria(banco)
    chave = str(uuid.uuid4())
    a = paga(banco, banco_id, chave=chave)
    depois, s = retrato(banco), saldo(banco, banco_id)
    b = paga(banco, banco_id, chave=chave)
    assert b['repetida'] is True
    assert {k: v for k, v in b.items() if k != 'repetida'} == {k: v for k, v in a.items() if k != 'repetida'}
    assert retrato(banco) == depois and saldo(banco, banco_id) == s
    assert len(da_despesa(banco)) == 1
    # a chave nao serve a outro usuario
    assert erro(paga, banco, banco_id, chave=chave, usuario=USUARIO_B).pgcode in ('42501', '22023')


def test_tres_envios_simultaneos_uma_despesa_e_um_pagamento(banco):
    banco_id = conta_bancaria(banco)
    chave, s0 = str(uuid.uuid4()), saldo(banco, banco_id)
    resultados = _paralelo([lambda: paga(banco, banco_id, chave=chave) for _ in range(3)])
    assert [r[0] for r in resultados] == ['ok'] * 3
    assert len({r[1]['conta_id'] for r in resultados}) == 1 and len({r[1]['pagamento']['movimento_id'] for r in resultados}) == 1
    assert len(da_despesa(banco)) == 1
    assert sql(banco, 'select count(*) n from public.movimento_financeiro where conta_id = %s', (resultados[0][1]['conta_id'],))[0]['n'] == 1
    assert saldo(banco, banco_id) == s0 - Decimal('87.40')


def test_chave_de_um_cadastro_pendente_nao_paga_a_despesa_que_ja_existia(banco):
    banco_id = conta_bancaria(banco)
    chave = str(uuid.uuid4())
    pendente = rpc(banco, 'criar_despesa', PESSOAL, dados(), chave)
    antes = retrato(banco)
    assert 'Chave da operacao ja usada' in erro(paga, banco, banco_id, chave=chave).diag.message_primary
    assert retrato(banco) == antes
    assert sql(banco, 'select status_pagamento s from public.conta where id = %s', (pendente['conta_id'],))[0]['s'] == 'Pendente'


# =====================================================================================================================
# 4. Permissoes da funcao e o cadastro pendente de sempre
# =====================================================================================================================

def test_funcao_so_para_usuario_autenticado_e_cadastro_pendente_inalterado(banco):
    acl = sql(banco, """select has_function_privilege('anon', p.oid, 'execute') anon, has_function_privilege('authenticated', p.oid, 'execute') aut,
                               p.prosecdef definer from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                         where n.nspname = 'financeiro' and p.proname = 'criar_despesa_paga'""")
    assert acl == [{'anon': False, 'aut': True, 'definer': True}]
    r = rpc(banco, 'criar_despesa', PESSOAL, dados(), str(uuid.uuid4()))
    assert sql(banco, 'select status_pagamento s, data_pagamento d from public.conta where id = %s', (r['conta_id'],))[0] == {'s': 'Pendente', 'd': None}
    assert sql(banco, 'select count(*) n from public.movimento_financeiro where conta_id = %s', (r['conta_id'],))[0]['n'] == 0
