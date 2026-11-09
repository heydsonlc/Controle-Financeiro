"""
Testes FIN-DESPESAS-PAGAMENTO-LOTE-02 (P21, migration 20261219090000) — o pagamento em lote confere a identidade do lote que
a tela mostrou e o usuario confirmou, em cluster PostgreSQL local descartavel e com dados ficticios.

Cenario como o real: duas recorrencias semanais "Diarista" (terca e sexta, R$ 200) e uma "Psicologa" (terca, R$ 250) em
02/2027. A tela abria o modal de uma recorrencia pelo botao da outra; o banco aceitava, porque as ocorrencias enviadas eram
todas as pendentes de uma recorrencia. Agora o pedido traz o nome, a competencia, as recorrencias, a quantidade e o total
mostrados, e o banco recusa (LOTE_IDENTIDADE) o que nao for exatamente esse lote, sem gravar nada.
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_categorias_recorrencias import banco, erro, nova_recorrencia  # noqa: F401
from tests.test_supabase_pagamento_lote import MES, PESSOAL, do_mes, gravado, identidade, lote, movimentos, preparar, saldo
from tests.test_supabase_recorrencia import PG_BIN, cluster, gerar_confirmado, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

RAIZ = Path(__file__).resolve().parent.parent


def com_psicologa(dsn):
    """Diarista (6 pendentes, 2 pagas uma a uma) e Psicologa (4 pendentes de R$ 250) em 02/2027."""
    psicologa = nova_recorrencia(dsn, 'Psicologa', 'semanal_1_2', '2027-02-02', valor='250.00')
    sql(dsn, "update public.item_despesa set meio_pagamento = 'pix' where id = %s", (psicologa,))
    itens, banco_id, todas, pendentes = preparar(dsn)  # gera o mes das tres recorrencias
    psi = [c for c in do_mes(dsn, [psicologa]) if c['status_pagamento'] != 'Pago']
    assert (len(pendentes), len(psi)) == (6, 4)
    return itens, psicologa, banco_id, pendentes, psi


def recusa(dsn, pendentes, banco_id, ident):
    antes = gravado(dsn)
    e = erro(lote, dsn, pendentes, banco_id, lote=ident)
    assert gravado(dsn) == antes  # nada pago, nenhum movimento, nenhuma operacao registrada
    return e


# =====================================================================================================================
# Identidade divergente: recusada sem pagar nada
# =====================================================================================================================

@pytest.mark.parametrize('caso', ['nome_da_outra', 'recorrencia_da_outra', 'recorrencias_a_mais', 'competencia', 'quantidade', 'total'])
def test_identidade_que_nao_corresponde_as_ocorrencias_e_recusada(banco, caso):
    itens, psicologa, banco_id, diarista, psi = com_psicologa(banco)
    alvo = psi if caso == 'nome_da_outra' else diarista
    ident = identidade(banco, alvo)
    if caso == 'nome_da_outra':  # o modal mostrou Diarista, mas foram enviadas as ocorrencias da Psicologa
        ident['descricao'] = 'Diarista'
    elif caso == 'recorrencia_da_outra':
        ident['recorrencias'] = [psicologa]
    elif caso == 'recorrencias_a_mais':
        ident['recorrencias'] = sorted(itens + [psicologa])
    elif caso == 'competencia':
        ident['competencia'] = '2027-03'
    elif caso == 'quantidade':
        ident['quantidade'] = len(alvo) - 1
    else:
        ident['valor_total'] = '1000.00'
    e = recusa(banco, alvo, banco_id, ident)
    assert e.diag.message_hint == 'LOTE_IDENTIDADE' and 'Nada foi pago' in e.diag.message_primary


def test_ocorrencias_das_duas_recorrencias_no_mesmo_lote_sao_recusadas(banco):
    itens, psicologa, banco_id, diarista, psi = com_psicologa(banco)
    for ident in (identidade(banco, diarista), identidade(banco, psi)):
        ident.update(quantidade=10, valor_total='2200.00')
        assert recusa(banco, diarista + psi, banco_id, ident).diag.message_hint == 'LOTE_IDENTIDADE'


@pytest.mark.parametrize('ident', [None, {}, {'descricao': 'Diarista', 'competencia': '2027-02', 'recorrencias': ['x'], 'quantidade': 6, 'valor_total': '1200.00'},
                                   {'descricao': 'Diarista', 'competencia': '02/2027', 'recorrencias': [1], 'quantidade': 6, 'valor_total': '1200.00'},
                                   {'descricao': ' ', 'competencia': '2027-02', 'recorrencias': [1], 'quantidade': 6, 'valor_total': '1200.00'},
                                   {'descricao': 'Diarista', 'competencia': '2027-02', 'recorrencias': [], 'quantidade': 6, 'valor_total': '1200.00'},
                                   {'descricao': 'Diarista', 'competencia': '2027-02', 'recorrencias': 7, 'quantidade': 6, 'valor_total': '1200.00'}])
def test_pedido_sem_identidade_valida_e_recusado(banco, ident):
    """A tela antiga (publicada com a P20) nao envia a identidade: o pedido dela e recusado."""
    itens, banco_id, todas, pendentes = preparar(banco)
    e = recusa(banco, pendentes, banco_id, ident)
    assert e.diag.message_hint == 'LOTE_IDENTIDADE' and 'não identifica o lote' in e.diag.message_primary


# =====================================================================================================================
# Identidade certa: paga so a recorrencia mostrada
# =====================================================================================================================

def test_lote_certo_paga_so_a_recorrencia_mostrada(banco):
    itens, psicologa, banco_id, diarista, psi = com_psicologa(banco)
    s0, mov0 = saldo(banco, banco_id), movimentos(banco, banco_id)
    r = lote(banco, diarista, banco_id)
    assert (r['pagas'], Decimal(str(r['valor_total']))) == (6, Decimal('1200.00'))
    assert all(c['status_pagamento'] == 'Pago' for c in do_mes(banco, itens))
    assert all(c['status_pagamento'] != 'Pago' for c in do_mes(banco, [psicologa]))
    assert sql(banco, 'select count(*) n from public.movimento_financeiro where conta_id = any(%s)', ([c['id'] for c in psi],))[0]['n'] == 0
    r = lote(banco, psi, banco_id)
    assert (r['pagas'], Decimal(str(r['valor_total']))) == (4, Decimal('1000.00'))
    assert sorted(o['conta_id'] for o in r['ocorrencias']) == sorted(c['id'] for c in psi)
    assert saldo(banco, banco_id) == s0 - Decimal('2200.00')
    assert movimentos(banco, banco_id)['n'] - mov0['n'] == 10


def test_escritor_unico_continua_antes_da_identidade(banco):
    itens, banco_id, todas, pendentes = preparar(banco)
    antes = gravado(banco)
    sql(banco, "update financeiro.gerador_recorrencia set gerador = 'FLASK' where perfil_financeiro_id = %s", (PESSOAL,))
    assert erro(lote, banco, pendentes, banco_id, lote=None).diag.message_hint == 'SISTEMA_FLASK'
    assert gravado(banco) == antes


# =====================================================================================================================
# Permissoes e reversao
# =====================================================================================================================

def test_funcao_mantem_permissoes_e_seguranca(banco):
    r = sql(banco, "select has_function_privilege('authenticated', 'financeiro.pagar_despesas_lote(integer, jsonb, uuid)', 'execute') a, "
                   "has_function_privilege('anon', 'financeiro.pagar_despesas_lote(integer, jsonb, uuid)', 'execute') n, "
                   "p.prosecdef d, p.proconfig c from pg_proc p where p.proname = 'pagar_despesas_lote'")
    assert len(r) == 1 and (r[0]['a'], r[0]['n'], r[0]['d'], r[0]['c']) == (True, False, True, ['search_path=""'])


def test_reversao_volta_ao_corpo_anterior_sem_mudar_dados(banco):
    itens, banco_id, todas, pendentes = preparar(banco)
    antes = gravado(banco)
    conn = psycopg2.connect(banco)
    try:
        with conn, conn.cursor() as cur:
            cur.execute((RAIZ / 'supabase/reversao/20261219090000_pagamento_lote_identidade_anterior.sql').read_text(encoding='utf-8'))
            cur.execute("select count(*), bool_or(prosrc like '%LOTE_IDENTIDADE%') from pg_proc where proname = 'pagar_despesas_lote'")
            assert cur.fetchone() == (1, False)
        assert gravado(banco) == antes
        r = lote(banco, pendentes, banco_id, lote=None)  # o corpo anterior ignora a identidade
        assert r['pagas'] == 6
        with conn, conn.cursor() as cur:
            cur.execute((RAIZ / 'supabase/migrations/20261219090000_financeiro_pagamento_lote_identidade.sql').read_text(encoding='utf-8'))
            cur.execute("select count(*), bool_or(prosrc like '%LOTE_IDENTIDADE%') from pg_proc where proname = 'pagar_despesas_lote'")
            assert cur.fetchone() == (1, True)
    finally:
        conn.close()
    novo = nova_recorrencia(banco, 'Aula', 'semanal_1_3', '2027-02-03', valor='80.00')
    gerar_confirmado(banco, mes=MES)
    aula = [c for c in do_mes(banco, [novo]) if c['status_pagamento'] != 'Pago']
    assert erro(lote, banco, aula, banco_id, lote=None).diag.message_hint == 'LOTE_IDENTIDADE'
    assert lote(banco, aula, banco_id, chave=str(uuid.uuid4()))['pagas'] == len(aula)
