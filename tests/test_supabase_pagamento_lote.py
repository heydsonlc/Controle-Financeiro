"""
Testes FIN-DESPESAS-PAGAMENTO-LOTE-01 (P20, migration 20261218090000) — pagamento em lote das ocorrencias pendentes de uma
recorrencia semanal, com a conta bancaria escolhida, em cluster PostgreSQL local descartavel e com dados ficticios.

Cenario como o real: duas recorrencias semanais "Diarista" (terca e sexta), Pix e sem conta bancaria, agrupadas pela tela;
algumas ocorrencias pagas uma a uma e as demais no lote. Cada ocorrencia e paga pelo pagamento individual, todas na mesma
transacao e com a mesma conta: ou todas, ou nenhuma. O lote que a tela mostrou e conferido com o de agora.
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_categorias_recorrencias import banco, contas, erro, nova_recorrencia  # noqa: F401
from tests.test_supabase_despesas import _paralelo
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, USUARIO_B, chamar, cluster, gerar_confirmado, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
MES = '2027-02-01'  # 4 tercas e 4 sextas, como 11/2026 no caso real
RAIZ = Path(__file__).resolve().parent.parent


def conta_bancaria(dsn, nome='Conta Pessoal (A)'):
    return sql(dsn, 'select id from public.conta_bancaria where nome = %s', (nome,))[0]['id']


def cenario(dsn):
    """Duas recorrencias "Diarista" de R$ 200 (terca e sexta), Pix e sem conta; as contas de 02/2027 geradas."""
    itens = [nova_recorrencia(dsn, 'Diarista', 'semanal_1_2', '2027-02-02', valor='200.00'),
             nova_recorrencia(dsn, 'Diarista', 'semanal_1_5', '2027-02-05', valor='200.00')]
    sql(dsn, "update public.item_despesa set meio_pagamento = 'pix' where id = any(%s)", (itens,))
    gerar_confirmado(dsn, mes=MES)
    return itens


def do_mes(dsn, itens):
    return sql(dsn, "select id, descricao, valor, status_pagamento, conta_bancaria_id from public.conta "
                    "where item_despesa_id = any(%s) and mes_referencia = %s order by id", (itens, MES))


def pagar_uma(dsn, conta, banco_id):
    return rpc(dsn, 'pagar_despesa', PESSOAL, conta['id'], {'conta_bancaria_id': banco_id, 'data_pagamento': '2027-02-03',
                                                           'valor_pago': str(conta['valor']), 'valor_devido': str(conta['valor'])},
               str(uuid.uuid4()))


def lote(dsn, pendentes, banco_id, chave=None, usuario=USUARIO_A, perfil=PESSOAL, **extra):
    dados = {'itens': [{'conta_id': c['id'], 'valor_devido': f"{Decimal(str(c['valor'])):.2f}"} for c in pendentes],
             'conta_bancaria_id': banco_id, 'data_pagamento': '2027-02-27', **extra}
    return rpc(dsn, 'pagar_despesas_lote', perfil, dados, chave or str(uuid.uuid4()), usuario=usuario)


def movimentos(dsn, banco_id=None):
    if banco_id is None:
        return sql(dsn, 'select count(*) n, coalesce(sum(valor), 0) v from public.movimento_financeiro')[0]
    return sql(dsn, 'select count(*) n, coalesce(sum(valor), 0) v from public.movimento_financeiro where conta_bancaria_id = %s', (banco_id,))[0]


def saldo(dsn, banco_id):
    return sql(dsn, 'select saldo_atual s from public.conta_bancaria where id = %s', (banco_id,))[0]['s']


def md5(dsn, tabela, where='true', args=None):
    return sql(dsn, f"select md5(coalesce(string_agg(t::text, '|' order by t.id), '')) h from {tabela} t where {where}", args)[0]['h']


def preparar(dsn, pagas=2):
    itens = cenario(dsn)
    banco_id = conta_bancaria(dsn)
    todas = do_mes(dsn, itens)
    for c in todas[-pagas:] if pagas else []:
        pagar_uma(dsn, c, banco_id)
    pendentes = [c for c in do_mes(dsn, itens) if c['status_pagamento'] != 'Pago']
    return itens, banco_id, todas, pendentes


# =====================================================================================================================
# 8, 9, 10, 11, 19. Pagamento das pendentes
# =====================================================================================================================

def test_lote_paga_as_pendentes_na_conta_escolhida_e_preserva_as_ja_pagas(banco):
    itens, banco_id, todas, pendentes = preparar(banco)
    assert len(todas) == 8 and len(pendentes) == 6  # como o caso real: 8 ocorrencias, 2 pagas uma a uma
    recorrencias =md5(banco, 'public.item_despesa', 'id = any(%s)', (itens,))
    n_contas = sql(banco, 'select count(*) n from public.conta')[0]['n']
    mov, s0 = movimentos(banco, banco_id), saldo(banco, banco_id)

    r = lote(banco, pendentes, banco_id)
    assert (r['pagas'], Decimal(str(r['valor_total'])), r['conta_bancaria_id']) == (6, Decimal('1200.00'), banco_id)
    assert sorted(o['conta_id'] for o in r['ocorrencias']) == sorted(c['id'] for c in pendentes)
    depois = do_mes(banco, itens)
    assert all(c['status_pagamento'] == 'Pago' and c['conta_bancaria_id'] == banco_id for c in depois)
    novos = movimentos(banco, banco_id)
    assert (novos['n'] - mov['n'], Decimal(str(novos['v'])) - Decimal(str(mov['v']))) == (6, Decimal('1200.00'))
    assert saldo(banco, banco_id) == s0 - Decimal('1200.00')
    # a recorrencia nao muda (Pix, sem conta) e nenhuma despesa e criada; as pagas antes: test_pagas_antes_ficam_intactas
    assert md5(banco, 'public.item_despesa', 'id = any(%s)', (itens,)) == recorrencias
    assert sql(banco, "select meio_pagamento m, conta_bancaria_id c from public.item_despesa where id = %s", (itens[0],))[0] == {'m': 'pix', 'c': None}
    assert sql(banco, 'select count(*) n from public.conta')[0]['n'] == n_contas
    # cada ocorrencia com um debito e um registro de pagamento
    assert sql(banco, 'select count(*) n from public.movimento_financeiro where conta_id = any(%s)', ([c['id'] for c in pendentes],))[0]['n'] == 6
    assert sql(banco, 'select count(*) n from financeiro.pagamento_fatura where fatura_id = any(%s)', ([c['id'] for c in pendentes],))[0]['n'] == 6


def test_pagas_antes_ficam_intactas(banco):
    itens, banco_id, todas, pendentes = preparar(banco)
    ids_pagas = [c['id'] for c in todas[-2:]]
    antes = md5(banco, 'public.conta', 'id = any(%s)', (ids_pagas,))
    movs_antes = md5(banco, 'public.movimento_financeiro', 'conta_id = any(%s)', (ids_pagas,))
    lote(banco, pendentes, banco_id)
    assert md5(banco, 'public.conta', 'id = any(%s)', (ids_pagas,)) == antes
    assert md5(banco, 'public.movimento_financeiro', 'conta_id = any(%s)', (ids_pagas,)) == movs_antes


def test_pagamento_individual_continua_funcionando(banco):
    itens, banco_id, todas, pendentes = preparar(banco, pagas=0)
    r = pagar_uma(banco, pendentes[0], banco_id)
    assert r['movimento_id'] and do_mes(banco, itens)[0]['status_pagamento'] == 'Pago'


# =====================================================================================================================
# 12, 13, 14. Conta invalida: nada e pago
# =====================================================================================================================

@pytest.mark.parametrize('caso,trecho', [('inativa', 'inativa'), ('outro_perfil', 'nao encontrada neste perfil'),
                                         ('sem_conta', 'Selecione a conta bancária')])
def test_conta_invalida_e_recusada_sem_pagar_nada(banco, caso, trecho):
    itens, banco_id, todas, pendentes = preparar(banco)
    alvo = {'inativa': banco_id, 'outro_perfil': conta_bancaria(banco, 'Conta Perfil B'), 'sem_conta': None}[caso]
    if caso == 'inativa':
        sql(banco, "update public.conta_bancaria set status = 'INATIVO' where id = %s", (banco_id,))
    contas_antes, mov = md5(banco, 'public.conta'), movimentos(banco)
    assert trecho in str(erro(lote, banco, pendentes, alvo))
    assert (md5(banco, 'public.conta'), movimentos(banco)) == (contas_antes, mov)


# =====================================================================================================================
# 15, 16. Repeticao e confirmacoes simultaneas
# =====================================================================================================================

def test_repetir_a_mesma_confirmacao_nao_gera_novos_movimentos(banco):
    itens, banco_id, todas, pendentes = preparar(banco)
    chave = str(uuid.uuid4())
    r1 = lote(banco, pendentes, banco_id, chave=chave)
    mov = movimentos(banco)
    r2 = lote(banco, pendentes, banco_id, chave=chave)
    assert r2['repetida'] is True and r2['pagas'] == r1['pagas'] == 6
    assert movimentos(banco) == mov


def test_duas_confirmacoes_simultaneas_pagam_uma_vez(banco):
    itens, banco_id, todas, pendentes = preparar(banco)
    mov = movimentos(banco)
    resultados = _paralelo([lambda: lote(banco, pendentes, banco_id) for _ in range(2)])
    assert sorted(r[0] for r in resultados) == ['erro', 'ok']
    novos = movimentos(banco)
    assert (novos['n'] - mov['n'], Decimal(str(novos['v'])) - Decimal(str(mov['v']))) == (6, Decimal('1200.00'))
    assert sql(banco, 'select count(*) n from public.movimento_financeiro where conta_id = any(%s)', ([c['id'] for c in pendentes],))[0]['n'] == 6


# =====================================================================================================================
# 17, 18. Falha numa ocorrencia e lote desatualizado: nada e pago, com o motivo
# =====================================================================================================================

def test_valor_alterado_numa_ocorrencia_recusa_o_lote_inteiro_com_o_motivo(banco):
    itens, banco_id, todas, pendentes = preparar(banco)
    sql(banco, "update public.conta set valor = 210 where id = %s", (pendentes[2]['id'],))  # mudou depois de a tela abrir
    contas_antes, mov = md5(banco, 'public.conta'), movimentos(banco)
    e = erro(lote, banco, pendentes, banco_id)
    texto = e.diag.message_primary
    assert texto.startswith('Nenhuma ocorrência foi paga.') and pendentes[2]['descricao'] in texto and 'R$ 210,00' in texto
    assert e.diag.message_hint == 'VALOR_MUDOU'
    assert (md5(banco, 'public.conta'), movimentos(banco)) == (contas_antes, mov)


def test_ocorrencia_paga_depois_da_abertura_torna_o_lote_desatualizado(banco):
    itens, banco_id, todas, pendentes = preparar(banco)
    pagar_uma(banco, pendentes[0], banco_id)  # paga em outra aba com o modal aberto
    mov = movimentos(banco)
    e = erro(lote, banco, pendentes, banco_id)
    assert e.diag.message_hint == 'LOTE_DESATUALIZADO' and 'agora são 5' in e.diag.message_primary
    assert movimentos(banco) == mov


def test_lote_que_deixa_ocorrencia_pendente_de_fora_e_desatualizado(banco):
    itens, banco_id, todas, pendentes = preparar(banco)
    mov = movimentos(banco)
    e = erro(lote, banco, pendentes[:-1], banco_id)
    assert e.diag.message_hint == 'LOTE_DESATUALIZADO'
    assert movimentos(banco) == mov


def test_ocorrencia_repetida_ou_de_outro_perfil_e_recusada(banco):
    itens, banco_id, todas, pendentes = preparar(banco)
    assert 'repetida' in str(erro(lote, banco, pendentes + [pendentes[0]], banco_id))
    criada = rpc(banco, 'criar_despesa', ID['PERFIL_B'], {'nome': 'Despesa B', 'valor': '200.00', 'categoria_id': 951,
                                                          'data_vencimento': '2027-02-10'}, str(uuid.uuid4()), usuario=USUARIO_B)
    alheia = [{'id': criada['conta_id'], 'valor': Decimal('200.00')}]
    assert 'nao encontrada neste perfil' in str(erro(lote, banco, pendentes + alheia, banco_id)).replace('ã', 'a')


def test_competencias_diferentes_no_mesmo_lote_sao_recusadas(banco):
    itens = cenario(banco)
    banco_id = conta_bancaria(banco)
    marco = sql(banco, "select id, valor from public.conta where item_despesa_id = any(%s) and mes_referencia = '2027-03-01' order by id limit 1", (itens,))
    pendentes = [c for c in do_mes(banco, itens) if c['status_pagamento'] != 'Pago']
    assert 'uma competência' in str(erro(lote, banco, pendentes + marco, banco_id))


def test_lista_vazia_e_dados_invalidos(banco):
    itens, banco_id, todas, pendentes = preparar(banco)
    assert 'Nenhuma ocorrência pendente' in str(erro(lote, banco, [], banco_id))
    with pytest.raises(psycopg2.Error, match='inválidos'):
        rpc(banco, 'pagar_despesas_lote', PESSOAL, {'itens': [{'conta_id': 'x', 'valor_devido': '200.00'}], 'conta_bancaria_id': banco_id,
                                                    'data_pagamento': '2027-02-27'}, str(uuid.uuid4()))


# =====================================================================================================================
# Outros meios, permissoes e reversao
# =====================================================================================================================

def test_recorrencia_em_debito_automatico_e_boleto_tambem_paga_em_lote(banco):
    item = nova_recorrencia(banco, 'Aula', 'semanal_1_3', '2027-02-03', valor='80.00')
    sql(banco, "update public.item_despesa set meio_pagamento = 'boleto' where id = %s", (item,))
    gerar_confirmado(banco, mes=MES)
    banco_id = conta_bancaria(banco)
    pendentes = [c for c in do_mes(banco, [item]) if c['status_pagamento'] != 'Pago']
    r = lote(banco, pendentes, banco_id)
    assert r['pagas'] == len(pendentes) and len(pendentes) >= 4


def test_permissoes(banco):
    r = sql(banco, "select has_function_privilege('authenticated', 'financeiro.pagar_despesas_lote(integer, jsonb, uuid)', 'execute') a, "
                   "has_function_privilege('anon', 'financeiro.pagar_despesas_lote(integer, jsonb, uuid)', 'execute') n")[0]
    assert (r['a'], r['n']) == (True, False)
    itens, banco_id, todas, pendentes = preparar(banco)
    assert 'nao autorizado' in str(erro(lote, banco, pendentes, banco_id, usuario=USUARIO_B))


def test_reversao_remove_a_funcao_sem_mudar_os_pagamentos(banco):
    itens, banco_id, todas, pendentes = preparar(banco)
    lote(banco, pendentes, banco_id)
    antes = (md5(banco, 'public.conta'), md5(banco, 'public.movimento_financeiro'))
    conn = psycopg2.connect(banco)
    try:
        with conn, conn.cursor() as cur:
            cur.execute((RAIZ / 'supabase/reversao/20261218090000_pagamento_lote_anterior.sql').read_text(encoding='utf-8'))
            cur.execute("select count(*) from pg_proc where proname = 'pagar_despesas_lote'")
            assert cur.fetchone()[0] == 0
        assert (md5(banco, 'public.conta'), md5(banco, 'public.movimento_financeiro')) == antes
        with conn, conn.cursor() as cur:
            cur.execute((RAIZ / 'supabase/migrations/20261218090000_financeiro_pagamento_lote.sql').read_text(encoding='utf-8'))
            cur.execute("select count(*) from pg_proc where proname = 'pagar_despesas_lote'")
            assert cur.fetchone()[0] == 1
    finally:
        conn.close()
