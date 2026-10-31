"""
Testes FIN-SALDO-PRECEDENCIA-AJUSTE-01 — precedencia do ajuste de saldo real (migration 20261206090000), em cluster local
descartavel, com o contrato FICTICIO equivalente ao real (tests/test_supabase_tr_projetada.py) e o ajuste de 05/10/2026
(R$ 269.524,62, referencia 31, parcela-base 30), como na producao:
- A: pagar a parcela 30 (valor real, diferenca classificada) nao troca o saldo real pelo estimado; contador e proxima;
- B: parcela anterior a base (historica, paga em Despesas, estornada) nao altera o saldo real;
- C: parcela posterior a base evolui pela cadeia que parte do saldo real (sem congelar);
- D: sem ajuste, o saldo segue a cadeia como antes;
- amortizacao ancorada na base parte do saldo real; anterior a ela, recusada; TR real cadastrada depois continua igual;
- parcela-base registrada com o ajuste, deduzida para ajuste ja existente (ou a migration para); reversao.
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_financiamentos_motor import FIXO, com_tr, falha, fin_id, novo
from tests.test_supabase_recorrencia import (  # noqa: F401  (fixture de modulo reaproveitada)
    ID,
    PG_BIN,
    atribuir,
    cluster,
    copiar,
    sql,
)
from tests.test_supabase_tr_projetada import SALDO_CAIXA, ajustar, contrato_como_producao, parcelas, projetadas

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
SUPABASE = Path(__file__).resolve().parent.parent / 'supabase'
MIGRATION = SUPABASE / 'migrations' / '20261206090000_financeiro_precedencia_ajuste_saldo.sql'
REVERSAO = SUPABASE / 'reversao' / '20261206090000_precedencia_ajuste_saldo_anterior.sql'
VALOR_REAL_30 = Decimal('2990.90')


def executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))  # como a fixture (LF)
    finally:
        conn.close()


def contrato(dsn):
    return sql(dsn, 'select * from public.financiamento where id = %s', (fin_id(dsn),))[0]


def saldo(dsn):
    return contrato(dsn)['saldo_devedor_atual']


def conta_da(dsn, numero):
    return sql(dsn, """select c.* from public.conta c join public.financiamento_parcela p on p.id = c.financiamento_parcela_id
                        where p.financiamento_id = %s and p.numero_parcela = %s""", (fin_id(dsn), numero))[0]


def banco(dsn):
    return sql(dsn, "select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")[0]['id']


def pagar(dsn, numero, valor=None, data='2026-10-05'):
    c = conta_da(dsn, numero)
    dados = {'conta_bancaria_id': banco(dsn), 'data_pagamento': data, 'valor_pago': str(valor or c['valor']),
             'valor_devido': str(c['valor'])}
    if valor is not None and Decimal(valor) != c['valor']:
        dados.update(tipo_ajuste='AJUSTE', justificativa='Valor real cobrado pela CAIXA (saldo real ajustado)')
    return rpc(dsn, 'pagar_despesa', PESSOAL, c['id'], dados, str(uuid.uuid4()))


def estornar(dsn, numero, pagamento):
    return rpc(dsn, 'estornar_pagamento_despesa', PESSOAL, conta_da(dsn, numero)['id'], pagamento['movimento_id'],
               {'motivo': 'teste', 'data_estorno': '2026-10-06'}, str(uuid.uuid4()))


def tela(dsn):
    t = rpc(dsn, 'financiamento_tela', PESSOAL, fin_id(dsn))
    return {'saldo': Decimal(str(t['saldo_devedor_atual'])), 'pagas': sum(1 for p in t['parcelas'] if p['status'] == 'pago'),
            'total': len(t['parcelas']), 'proxima': next(p['numero_parcela'] for p in t['parcelas'] if p['status'] != 'pago')}


def como_producao(cluster, ate=29):  # noqa: F811
    """Contrato real ficticio, ajuste de 05/10/2026 (referencia 31) e parcelas 1..ate quitadas antes do sistema."""
    dsn = contrato_como_producao(cluster)
    ajustar(dsn)
    novo(dsn, 'registrar_parcelas_historicas', PESSOAL, fin_id(dsn), {'ate_parcela': ate})
    return dsn


def base_registrada(dsn):
    return [(r['numero_parcela'], r['numero_parcela_base']) for r in sql(dsn, """
        select a.numero_parcela, b.numero_parcela_base from public.financiamento_ajuste_saldo a
          join financeiro.ajuste_saldo_base b on b.ajuste_id = a.id where a.financiamento_id = %s order by a.id""", (fin_id(dsn),))]


def test_cenario_a_parcela_30_paga_mantem_saldo_real(cluster):  # noqa: F811
    dsn = como_producao(cluster)
    assert base_registrada(dsn) == [(31, 30)]
    assert tela(dsn) == {'saldo': SALDO_CAIXA, 'pagas': 29, 'total': 420, 'proxima': 30}
    antes = parcelas(dsn)
    movimentos = sql(dsn, 'select count(*) n from public.movimento_financeiro')[0]['n']

    pg = pagar(dsn, 30, VALOR_REAL_30)

    # Pagamento normal: parcela, valor, diferenca, despesa e movimento.
    p30 = parcelas(dsn)[30]
    assert (p30['status'], p30['valor_pago'], p30['dif_apurada']) == ('pago', VALOR_REAL_30, antes[30]['valor_previsto_total'] - VALOR_REAL_30)
    c30 = conta_da(dsn, 30)
    assert (c30['status_pagamento'], c30['valor'], str(c30['data_pagamento'])) == ('Pago', VALOR_REAL_30, '2026-10-05')
    assert sql(dsn, 'select count(*) n from public.movimento_financeiro')[0]['n'] == movimentos + 1
    assert sql(dsn, 'select valor from public.movimento_financeiro where id = %s', (pg['movimento_id'],))[0]['valor'] == VALOR_REAL_30
    # Saldo real preservado, nao o estimado da parcela 30 (na producao, R$ 464.285,71); contador e proxima; sem novo ajuste.
    assert antes[30]['saldo_devedor_apos_pagamento'] > 400000
    assert tela(dsn) == {'saldo': SALDO_CAIXA, 'pagas': 30, 'total': 420, 'proxima': 31}
    f = contrato(dsn)
    assert (f['numero_parcela_base'], str(f['data_base']), f['prazo_remanescente_meses']) == (30, '2026-10-05', 390)
    assert sql(dsn, 'select count(*) n from public.financiamento_ajuste_saldo')[0]['n'] == 1
    # Parcelas futuras (ja recalculadas pelo ajuste) e a TR projetada intactas.
    depois = parcelas(dsn)
    assert all(depois[n] == antes[n] for n in range(31, 421))
    assert projetadas(dsn) == list(range(31, 421))


def test_cenario_b_parcela_anterior_a_base_nao_altera_saldo_real(cluster):  # noqa: F811
    dsn = como_producao(cluster, ate=24)  # historicas 1..24 depois do ajuste: saldo real intacto
    assert saldo(dsn) == SALDO_CAIXA
    pg30 = pagar(dsn, 30, VALOR_REAL_30)
    assert saldo(dsn) == SALDO_CAIXA
    pg25 = pagar(dsn, 25, data='2026-10-10')  # parcela historica paga depois, em Despesas
    assert parcelas(dsn)[25]['status'] == 'pago' and saldo(dsn) == SALDO_CAIXA
    novo(dsn, 'registrar_parcelas_historicas', PESSOAL, fin_id(dsn), {'ate_parcela': 29})  # 26..29
    assert saldo(dsn) == SALDO_CAIXA
    assert tela(dsn) == {'saldo': SALDO_CAIXA, 'pagas': 30, 'total': 420, 'proxima': 31}
    # Estornos (a mais recente primeiro): continua o saldo real, nunca o estimado.
    estornar(dsn, 30, pg30)
    assert parcelas(dsn)[30]['status'] == 'pendente' and saldo(dsn) == SALDO_CAIXA
    assert falha(dsn, 'estornar_pagamento_despesa', PESSOAL, conta_da(dsn, 25)['id'], pg25['movimento_id'],
                 {'motivo': 'teste', 'data_estorno': '2026-10-11'}, str(uuid.uuid4()))[2] == 'PARCELA_POSTERIOR_PAGA'


def test_cenario_c_parcela_posterior_evolui_a_partir_do_saldo_real(cluster):  # noqa: F811
    dsn = como_producao(cluster)
    pagar(dsn, 30, VALOR_REAL_30)
    p31 = parcelas(dsn)[31]
    pg31 = pagar(dsn, 31, data='2026-11-05')
    # Evolucao normal pela cadeia SAC/TR que parte do saldo real: nao fica congelado em R$ 269.524,62.
    assert saldo(dsn) == p31['saldo_devedor_apos_pagamento'] == Decimal('269267.97')
    tr = Decimal('0.001616')
    assert abs(SALDO_CAIXA * (1 + tr) - p31['valor_amortizacao'] - saldo(dsn)) <= Decimal('0.01')
    assert tela(dsn) == {'saldo': Decimal('269267.97'), 'pagas': 31, 'total': 420, 'proxima': 32}
    pg32 = pagar(dsn, 32, data='2026-12-05')
    assert saldo(dsn) == parcelas(dsn)[32]['saldo_devedor_apos_pagamento'] < Decimal('269267.97')
    # Estorno da 32: volta a cadeia da 31; nada volta ao estimado.
    estornar(dsn, 32, pg32)
    assert saldo(dsn) == Decimal('269267.97')
    estornar(dsn, 31, pg31)
    assert saldo(dsn) == SALDO_CAIXA


def test_cenario_d_sem_ajuste_saldo_pela_cadeia_como_antes(cluster):  # noqa: F811
    dsn = contrato_como_producao(cluster)
    novo(dsn, 'registrar_parcelas_historicas', PESSOAL, fin_id(dsn), {'ate_parcela': 29})
    p = parcelas(dsn)
    assert saldo(dsn) == p[29]['saldo_devedor_apos_pagamento']
    pg = pagar(dsn, 30)
    assert saldo(dsn) == p[30]['saldo_devedor_apos_pagamento'] > 400000
    estornar(dsn, 30, pg)
    assert saldo(dsn) == p[29]['saldo_devedor_apos_pagamento']
    # O texto novo e o de 20261123 dao o mesmo saldo sem ajuste (a reversao devolve o texto de 20261123).
    novo_saldo = sql(dsn, 'select financeiro.saldo_devedor_pelas_parcelas(%s) s', (fin_id(dsn),))[0]['s']
    executar(dsn, REVERSAO)
    assert sql(dsn, 'select financeiro.saldo_devedor_pelas_parcelas(%s) s', (fin_id(dsn),))[0]['s'] == novo_saldo


def test_amortizacao_parte_do_saldo_real_e_anterior_a_base_recusada(cluster):  # noqa: F811
    dsn = como_producao(cluster)
    antes = parcelas(dsn)
    erro = falha(dsn, 'registrar_amortizacao_extra', PESSOAL, fin_id(dsn), {'data': '2026-10-01', 'valor': 1000, 'tipo': 'reduzir_parcela'},
                 str(uuid.uuid4()))
    assert erro[2] == 'AJUSTE_POSTERIOR' and parcelas(dsn) == antes and saldo(dsn) == SALDO_CAIXA
    # Ancorada na base (primeira recalculada = 31): parte do saldo real, nao do estimado da 30.
    novo(dsn, 'registrar_amortizacao_extra', PESSOAL, fin_id(dsn), {'data': '2026-10-20', 'valor': 10000, 'tipo': 'reduzir_parcela'})
    restante = SALDO_CAIXA - 10000
    assert saldo(dsn) == restante
    p = parcelas(dsn)
    assert p[30] == antes[30] and p[420]['saldo_devedor_apos_pagamento'] == 0
    assert abs(p[31]['valor_amortizacao'] - (restante / 390 * Decimal('1.001616')).quantize(Decimal('0.01'))) <= Decimal('0.01')
    # Pagar a 30 depois: saldo real menos a amortizacao posterior a ele; a 31 segue a cadeia nova.
    pagar(dsn, 30, VALOR_REAL_30)
    assert saldo(dsn) == restante
    pagar(dsn, 31, data='2026-11-05')
    assert saldo(dsn) == parcelas(dsn)[31]['saldo_devedor_apos_pagamento']


def test_tr_real_cadastrada_depois_mantem_saldo_e_recalcula_projetadas(cluster):  # noqa: F811
    dsn = como_producao(cluster)
    pagar(dsn, 30, VALOR_REAL_30)
    antes = parcelas(dsn)
    assert rpc(dsn, 'criar_tr', {'competencia': '2026-11', 'valor_percentual': '0,16224'}, str(uuid.uuid4()))['data']
    depois = parcelas(dsn)
    assert projetadas(dsn) == list(range(32, 421))
    assert depois[31]['saldo_devedor_apos_pagamento'] != antes[31]['saldo_devedor_apos_pagamento'] and depois[30] == antes[30]
    assert saldo(dsn) == SALDO_CAIXA


def test_base_do_ajuste_com_referencia_paga_e_ajuste_mais_recente(cluster):  # noqa: F811
    dsn = como_producao(cluster)
    pagar(dsn, 30, VALOR_REAL_30)
    # Referencia ja paga: o saldo real e depois dela (base = referencia); recalcula da 31.
    novo(dsn, 'ajustar_saldo_devedor', PESSOAL, fin_id(dsn), {'numero_parcela': 30, 'saldo_devedor_real': '269000.00',
                                                             'data_referencia': '2026-10-05'})
    assert base_registrada(dsn) == [(31, 30), (30, 30)]
    assert saldo(dsn) == Decimal('269000.00')
    novo(dsn, 'registrar_parcelas_historicas', PESSOAL, fin_id(dsn), {'ate_parcela': 29})  # nada a registrar: segue o real
    assert saldo(dsn) == Decimal('269000.00')
    pagar(dsn, 31, data='2026-11-05')
    assert saldo(dsn) == parcelas(dsn)[31]['saldo_devedor_apos_pagamento'] < Decimal('269000.00')


def test_migration_deduz_a_base_dos_ajustes_existentes_ou_para(cluster):  # noqa: F811
    dsn = contrato_como_producao(cluster)
    executar(dsn, REVERSAO)
    ajustar(dsn)  # pelo texto anterior: sem parcela-base registrada
    assert sql(dsn, "select to_regclass('financeiro.ajuste_saldo_base') t")[0]['t'] is None
    executar(dsn, MIGRATION)
    assert base_registrada(dsn) == [(31, 30)]
    # Ajuste nao identificavel (sem recalculo e ja superado por outro): a migration para e nada fica.
    executar(dsn, REVERSAO)
    sql(dsn, 'update public.financiamento_ajuste_saldo set parcelas_recalculadas = 0')
    novo(dsn, 'ajustar_saldo_devedor', PESSOAL, fin_id(dsn), {'numero_parcela': 31, 'saldo_devedor_real': '269000.00',
                                                             'data_referencia': '2026-10-05'})
    with pytest.raises(psycopg2.Error, match='nao identificavel'):
        executar(dsn, MIGRATION)
    assert sql(dsn, "select to_regclass('financeiro.ajuste_saldo_base') t")[0]['t'] is None


def test_reversao_devolve_o_texto_anterior_e_volta(cluster):  # noqa: F811
    dsn = copiar(cluster)
    catalogo = ("select p.oid::regprocedure::text s, md5(p.prosrc) c, coalesce(p.proacl::text, '') a from pg_proc p "
                "join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro'")
    com = {r['s']: r for r in sql(dsn, catalogo)}
    executar(dsn, REVERSAO)
    sem = {r['s']: r for r in sql(dsn, catalogo)}
    assert set(com) - set(sem) == {'financeiro.fin_ajuste_vigente(integer)'} and set(sem) < set(com)
    trocadas = {s for s in sem if sem[s] != com[s]}
    assert trocadas == {'financeiro.saldo_devedor_pelas_parcelas(integer)',
                        'financeiro.ajustar_saldo_devedor(integer,integer,jsonb,uuid)',
                        'financeiro.registrar_amortizacao_extra(integer,integer,jsonb,uuid)'}
    assert all(sem[s]['a'] == com[s]['a'] for s in trocadas)  # mesmos privilegios
    origem = (SUPABASE / 'migrations' / '20261123090000_financeiro_financiamentos_motor.sql').read_text(encoding='utf-8')
    for s in trocadas:
        corpo = sql(dsn, 'select prosrc from pg_proc where oid = %s::regprocedure', (s,))[0]['prosrc']
        assert corpo.replace('\r\n', '\n') in origem
    assert sql(dsn, "select to_regclass('financeiro.ajuste_saldo_base') t")[0]['t'] is None
    executar(dsn, MIGRATION)
    assert {r['s']: r for r in sql(dsn, catalogo)} == com
    r = sql(dsn, "select c.relrowsecurity rls, c.relforcerowsecurity forcado, "
                 "has_table_privilege('authenticated', c.oid, 'select') sel, has_table_privilege('anon', c.oid, 'select') anon "
                 "from pg_class c where c.oid = 'financeiro.ajuste_saldo_base'::regclass")[0]
    assert r == {'rls': True, 'forcado': True, 'sel': False, 'anon': False}
    assert sql(dsn, "select has_function_privilege('authenticated', 'financeiro.fin_ajuste_vigente(integer)', 'execute') x")[0]['x'] is False
