"""
Testes FIN-AJUSTE-FINANCIAMENTO-REAL-01 — TR projetada no motor SAC/TR (migration 20261204090000), em cluster local
descartavel, com contrato FICTICIO equivalente ao real (FIXO de tests/test_supabase_financiamentos_motor.py) e a TR
publicada so ate 2026-10, como na producao:
- TR publicada prevalece; depois da ultima publicada, a ultima (projetada, so em memoria: nada vai para Indexadores);
  sem TR entre publicadas continua recusado;
- ajuste de saldo real a partir da parcela 31 (saldo CAIXA de 05/10/2026) recalcula 31..420 com TR projetada, marca as
  parcelas, mantem 1..30 e as despesas delas, atualiza a despesa de novembro no lugar (sem duplicar);
- TR real cadastrada (ou importada) depois: as projetadas sao recalculadas e ficam iguais ao ajuste feito ja com a TR;
- perfil no Flask ou parcela protegida na faixa: nada e recalculado;
- simulacao de quitacao com TR projetada avisa a origem; a reversao volta a recusar.
"""
import uuid
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_financiamentos_motor import FIXO, com_tr, fin_id, novo
from tests.test_supabase_recorrencia import (  # noqa: F401  (fixture de modulo reaproveitada)
    ID,
    PG_BIN,
    USUARIO_A,
    atribuir,
    cluster,
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
TR_PRODUCAO = {'2026-07': '0.00172900', '2026-08': '0.00169300', '2026-09': '0.00169000', '2026-10': '0.00161600'}
SALDO_CAIXA = Decimal('269524.62')
# Taxa nominal do contrato real (9,3764% a.a.; a CAIXA informa 9,38% com relacionamento, arredondada).
CONTRATO = {**FIXO, 'taxa_juros_nominal_anual': 9.3764}
AJUSTE = {'numero_parcela': 31, 'saldo_devedor_real': str(SALDO_CAIXA), 'data_referencia': '2026-10-05',
          'observacao': 'Saldo devedor teorico CAIXA em 05/10/2026, apos a parcela 30'}
CAMPOS = ('valor_amortizacao', 'valor_juros', 'valor_seguro', 'valor_taxa_adm', 'valor_atualizacao_monetaria',
          'valor_previsto_total', 'saldo_devedor_apos_pagamento', 'status')


def centavos(v):
    return Decimal(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def contrato_como_producao(cluster, tr_extra=None):  # noqa: F811
    """Contrato de 420 parcelas gerado com TR completa; depois a TR fica como na producao (ate 2026-10)."""
    dsn = com_tr(copiar(cluster))
    atribuir(dsn, 'PESSOAL')
    novo(dsn, 'criar_financiamento', PESSOAL, CONTRATO)
    sql(dsn, "delete from public.indice_tr_mensal where competencia > '2026-10'")
    for comp, valor in {**TR_PRODUCAO, **(tr_extra or {})}.items():
        sql(dsn, 'delete from public.indice_tr_mensal where competencia = %s', (comp,))
        sql(dsn, "insert into public.indice_tr_mensal (ano, mes, competencia, valor_decimal, fonte) values (%s, %s, %s, %s, 'BACEN')",
            (int(comp[:4]), int(comp[5:]), comp, valor))
    return dsn


def parcelas(dsn):
    return {p['numero_parcela']: p for p in sql(dsn, 'select * from public.financiamento_parcela where financiamento_id = %s',
                                                 (fin_id(dsn),))}


def contas(dsn):
    return {c['numero_parcela']: c for c in sql(dsn, """select c.*, p.numero_parcela from public.conta c
                                                       join public.financiamento_parcela p on p.id = c.financiamento_parcela_id
                                                      where p.financiamento_id = %s""", (fin_id(dsn),))}


def projetadas(dsn):
    return sorted(r['numero_parcela'] for r in sql(dsn, """select p.numero_parcela from financeiro.parcela_tr_projetada t
                                                          join public.financiamento_parcela p on p.id = t.parcela_id
                                                         where t.financiamento_id = %s""", (fin_id(dsn),)))


def ajustar(dsn, dados=AJUSTE):
    return novo(dsn, 'ajustar_saldo_devedor', PESSOAL, fin_id(dsn), dados)


def test_tr_publicada_prevalece_futura_projetada_e_lacuna_recusada(cluster):  # noqa: F811
    dsn = contrato_como_producao(cluster)
    real = sql(dsn, "select financeiro.fin_tr_info('2026-10-05') as v")[0]['v']
    assert real == {'valor': 0.001616, 'projetada': False, 'origem': '2026-10'}
    futura = sql(dsn, "select financeiro.fin_tr_info('2031-03-05') as v")[0]['v']
    assert futura == {'valor': 0.001616, 'projetada': True, 'origem': '2026-10'}
    assert float(sql(dsn, "select financeiro.fin_tr('2031-03-05') as v")[0]['v']) == 0.001616
    assert sql(dsn, "select count(*) as n from public.indice_tr_mensal where competencia > '2026-10'")[0]['n'] == 0
    sql(dsn, "delete from public.indice_tr_mensal where competencia = '2026-08'")  # lacuna entre publicadas
    with pytest.raises(psycopg2.Error, match='Nao ha TR cadastrada para a competencia 2026-08'):
        sql(dsn, "select financeiro.fin_tr_info('2026-08-05')")
    sql(dsn, 'delete from public.indice_tr_mensal')
    with pytest.raises(psycopg2.Error, match='Nao ha TR cadastrada'):
        sql(dsn, "select financeiro.fin_tr('2031-03-05')")


def test_ajuste_de_saldo_real_com_tr_projetada(cluster):  # noqa: F811
    dsn = contrato_como_producao(cluster)
    antes_p, antes_c = parcelas(dsn), contas(dsn)
    r = ajustar(dsn)
    assert r['parcelas_recalculadas'] == 390
    depois_p, depois_c = parcelas(dsn), contas(dsn)

    # Parcela 31 pela cadeia SAC/TR, com a TR projetada (a de 2026-10).
    tr = Decimal('0.001616')
    taxa = Decimal('9.3764') / 100 / 12
    corrigido = SALDO_CAIXA * (1 + tr)
    p31 = depois_p[31]
    assert p31['valor_amortizacao'] == centavos(SALDO_CAIXA / 390 * (1 + tr)) == Decimal('692.21')
    assert p31['valor_juros'] == centavos(corrigido * taxa)
    assert p31['valor_seguro'] == Decimal('163.51')  # vigencia fixa de 2026-01 do contrato ficticio
    assert p31['valor_taxa_adm'] == Decimal('25.00')
    # Calibracao com a CAIXA (05/11/2026): amortizacao + juros 2.801,62.
    assert abs(p31['valor_amortizacao'] + p31['valor_juros'] - Decimal('2801.62')) <= Decimal('0.10')

    # 1..30 intactas (valores, status e despesas); 31..420 recalculadas e marcadas; nada duplicado.
    assert all({k: depois_p[n][k] for k in CAMPOS} == {k: antes_p[n][k] for k in CAMPOS} for n in range(1, 31))
    assert all(depois_c[n] == antes_c[n] for n in range(1, 31))
    assert projetadas(dsn) == list(range(31, 421))
    assert len(depois_c) == len(antes_c) == 420
    assert depois_c[31]['id'] == antes_c[31]['id'] and depois_c[31]['valor'] == p31['valor_previsto_total']
    assert sql(dsn, """select count(*) as n from public.conta c join public.financiamento_parcela p on p.id = c.financiamento_parcela_id
                        where p.financiamento_id = %s and c.mes_referencia = '2026-11-01'""", (fin_id(dsn),))[0]['n'] == 1
    f = sql(dsn, 'select * from public.financiamento where id = %s', (fin_id(dsn),))[0]
    assert (f['saldo_devedor_atual'], f['prazo_remanescente_meses'], f['numero_parcela_base'], str(f['data_base'])) == \
        (SALDO_CAIXA, 390, 30, '2026-10-05')
    assert depois_p[420]['saldo_devedor_apos_pagamento'] == 0
    # Nada foi para Indexadores.
    assert sql(dsn, "select count(*) as n from public.indice_tr_mensal where competencia > '2026-10'")[0]['n'] == 0

    # A tela recebe a marca so nas parcelas projetadas.
    tela = rpc(dsn, 'financiamento_tela', PESSOAL, fin_id(dsn))
    marcadas = [p['numero_parcela'] for p in tela['parcelas'] if p.get('tr_projetada')]
    assert marcadas == list(range(31, 421))
    assert 'tr_projetada' not in tela['parcelas'][29]


def test_tr_real_cadastrada_recalcula_igual_ao_ajuste_ja_com_a_tr(cluster):  # noqa: F811
    com_tr_depois = contrato_como_producao(cluster)
    ajustar(com_tr_depois)
    chave = str(uuid.uuid4())
    rpc(com_tr_depois, 'criar_tr', {'competencia': '2026-11', 'valor_percentual': '0,16224'}, chave)

    com_tr_antes = contrato_como_producao(cluster, {'2026-11': '0.00162240'})
    ajustar(com_tr_antes)

    a, b = parcelas(com_tr_depois), parcelas(com_tr_antes)
    assert all({k: a[n][k] for k in CAMPOS} == {k: b[n][k] for k in CAMPOS} for n in range(1, 421))
    ca, cb = contas(com_tr_depois), contas(com_tr_antes)
    assert all(ca[n]['valor'] == cb[n]['valor'] for n in range(1, 421))
    assert projetadas(com_tr_depois) == projetadas(com_tr_antes) == list(range(32, 421))
    p31 = a[31]
    assert (p31['valor_amortizacao'], p31['valor_juros']) == (Decimal('692.21'), Decimal('2109.39'))

    # Importacao: o mesmo, a partir da primeira competencia importada.
    importado = contrato_como_producao(cluster)
    ajustar(importado)
    rpc(importado, 'importar_tr', {'texto': '2026-11;0,16224\n2026-12;0,15', 'fonte': 'BACEN'}, str(uuid.uuid4()))
    referencia = contrato_como_producao(cluster, {'2026-11': '0.00162240', '2026-12': '0.00150000'})
    ajustar(referencia)
    a, b = parcelas(importado), parcelas(referencia)
    assert all({k: a[n][k] for k in CAMPOS} == {k: b[n][k] for k in CAMPOS} for n in range(1, 421))
    assert projetadas(importado) == list(range(33, 421))


def test_reprojecao_respeita_escritor_e_parcela_protegida(cluster):  # noqa: F811
    flask = contrato_como_producao(cluster)
    ajustar(flask)
    antes = parcelas(flask)
    atribuir(flask, 'PESSOAL', 'FLASK')  # o Flask volta a escrever o perfil: o novo aplicativo nao recalcula
    rpc(flask, 'criar_tr', {'competencia': '2026-11', 'valor_percentual': '0,16224'}, str(uuid.uuid4()))
    assert parcelas(flask) == antes and projetadas(flask) == list(range(31, 421))

    protegida = contrato_como_producao(cluster)
    ajustar(protegida)
    banco = sql(protegida, "select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")[0]['id']
    c33 = contas(protegida)[33]
    rpc(protegida, 'pagar_despesa', PESSOAL, c33['id'], {'conta_bancaria_id': banco, 'data_pagamento': '2026-10-20',
                                                         'valor_pago': str(c33['valor']), 'valor_devido': str(c33['valor'])},
        str(uuid.uuid4()))
    antes = parcelas(protegida)
    rpc(protegida, 'criar_tr', {'competencia': '2026-11', 'valor_percentual': '0,16224'}, str(uuid.uuid4()))
    assert {n: {k: p[k] for k in CAMPOS} for n, p in parcelas(protegida).items()} == \
        {n: {k: p[k] for k in CAMPOS} for n, p in antes.items()}  # parcela 33 paga na faixa: fica como estava


def test_simulacao_de_quitacao_avisa_tr_projetada(cluster):  # noqa: F811
    dsn = contrato_como_producao(cluster)
    ajustar(dsn)
    r = rpc(dsn, 'simular_quitacao', PESSOAL, fin_id(dsn), {'data_quitacao': '2099-01-10'})
    assert r['data']['tr_aplicada'] == 0.001616
    assert any('(projetada: TR de 2026-10, a última publicada)' in o for o in r['data']['observacoes'])
    r = rpc(dsn, 'simular_quitacao', PESSOAL, fin_id(dsn), {'data_quitacao': '2026-10-10'})
    assert not any('projetada' in o for o in r['data']['observacoes'])


def test_reversao_volta_a_recusar_tr_futura(cluster):  # noqa: F811
    dsn = contrato_como_producao(cluster)
    ajustar(dsn)
    conn = psycopg2.connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute((Path(__file__).resolve().parent.parent / 'supabase' / 'reversao' / '20261204090000_tr_projetada_anterior.sql')
                    .read_bytes().decode('utf-8'))
    conn.close()
    with pytest.raises(psycopg2.Error, match='Nao ha TR cadastrada para a competencia 2031-03'):
        sql(dsn, "select financeiro.fin_tr('2031-03-05')")
    assert sql(dsn, "select to_regclass('financeiro.parcela_tr_projetada') as t")[0]['t'] is None
    assert parcelas(dsn)[31]['valor_amortizacao'] == Decimal('692.21')  # o que foi calculado fica
    assert rpc(dsn, 'criar_tr', {'competencia': '2026-11', 'valor_percentual': '0,16224'}, str(uuid.uuid4()))['data']
