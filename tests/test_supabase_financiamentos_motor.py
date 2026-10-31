"""
Testes FIN-FINANCIAMENTOS-MOTOR-1 — motor SAC/TR da Caixa no novo aplicativo (migration 20261123090000).

Fidelidade: o PROPRIO Flask cria e amortiza o mesmo contrato FICTICIO numa copia do cluster (perfil no Flask) e o novo
aplicativo faz o mesmo noutra (perfil atribuido a ele); contrato, 420 parcelas, despesas, vigencias e faixas MIP sao
comparados campo a campo, ao centavo. Calibracao: as tolerancias de tests/test_financiamento_calibracao_caixa_tr.py
(valores cobrados pela Caixa) valem para o motor novo. Cenario obrigatorio: 420 parcelas, 22 historicas pagas sem
movimento, 398 pendentes, seguro fixo por vigencia, taxa administrativa e uma amortizacao extraordinaria; as sete
provas de preservacao. Tambem: correcoes em relacao ao Flask, escritor unico, quem so le, isolamento, idempotencia.
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from dateutil.relativedelta import relativedelta

from tests.test_financiamento_calibracao_caixa_tr import (
    EVOLUCAO_REAL,
    SALDO_DEVEDOR_TEO_PDF_2026_05,
    TR_MENSAL,
    VALORES_REAIS_2025,
    _payload_motor_caixa_tr,
)
from tests.test_supabase_cartoes import rpc
from tests.test_supabase_receitas_categorias_tela import flask
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL, EMPRESA = ID['PESSOAL'], ID['EMPRESA']
NOME = 'Financiamento Caixa SAC/TR (ficticio)'
NOME_DFI = 'Financiamento CAIXA calibracao TR'

# Equivalente ficticio do contrato real: valores, datas, taxa e TR dos testes de calibracao; seguro FIXO por vigencia
# (o modo do contrato real) com os valores cobrados em 2025/2026.
FIXO = {
    'nome': NOME, 'produto': 'SFH', 'sistema_amortizacao': 'SAC', 'indexador_saldo': 'TR', 'valor_financiado': 500000,
    'prazo_total_meses': 420, 'taxa_juros_nominal_anual': 9.38, 'data_contrato': '2024-05-05',
    'data_primeira_parcela': '2024-05-05', 'seguro_modo': 'fixo', 'taxa_administracao_fixa': 25,
    'vigencias_seguro': [{'competencia_inicio': '2024-05', 'valor_mensal': 182.06},
                         {'competencia_inicio': '2025-03', 'valor_mensal': 248.07},
                         {'competencia_inicio': '2025-08', 'valor_mensal': 163.43},
                         {'competencia_inicio': '2026-01', 'valor_mensal': 163.51, 'observacoes': 'reajuste'}],
}
AMORTIZACAO = {'data': '2025-07-06', 'valor': 216670.0, 'tipo': 'reduzir_parcela', 'observacoes': 'Amortizacao calibrada'}

FORA = {'id', 'criado_em', 'atualizado_em', 'item_despesa_id', 'financiamento_id', 'conta_id', 'financiamento_parcela_id',
        'origem_id', 'parcela_id', 'registrado_em', 'registrado_por', 'parcela_referencia_id'}


def com_tr(dsn, sem=None):
    valores = dict(TR_MENSAL)
    competencia = date(2026, 7, 1)
    while competencia <= date(2060, 12, 1):
        valores.setdefault(f'{competencia:%Y-%m}', Decimal('0'))
        competencia += relativedelta(months=1)
    valores.pop(sem, None)
    comps = sorted(valores)
    sql(dsn, "delete from public.indice_tr_mensal")
    sql(dsn, """insert into public.indice_tr_mensal (ano, mes, competencia, valor_decimal, fonte)
                select split_part(c, '-', 1)::int, split_part(c, '-', 2)::int, c, v, 'BACEN'
                  from unnest(%s::text[], %s::numeric[]) as x(c, v)""", (comps, [valores[c] for c in comps]))
    return dsn


def limpo(linhas):
    return [{k: v for k, v in linha.items() if k not in FORA} for linha in linhas]


def estado(dsn, nome=NOME):
    f = sql(dsn, 'select * from public.financiamento where nome = %s', (nome,))
    fid = f[0]['id'] if f else -1
    return {
        'financiamento': limpo(f),
        'parcelas': limpo(sql(dsn, 'select * from public.financiamento_parcela where financiamento_id = %s order by numero_parcela', (fid,))),
        'contas': limpo(sql(dsn, """select c.* from public.conta c join public.financiamento_parcela p on p.id = c.financiamento_parcela_id
                                    where p.financiamento_id = %s order by p.numero_parcela""", (fid,))),
        'item': limpo(sql(dsn, 'select d.* from public.item_despesa d join public.financiamento f on f.item_despesa_id = d.id where f.id = %s', (fid,))),
        'vigencias': limpo(sql(dsn, 'select * from public.financiamento_seguro_vigencia where financiamento_id = %s order by competencia_inicio, id', (fid,))),
        'faixas': limpo(sql(dsn, 'select * from public.financiamento_seguro_faixa_mip where financiamento_id = %s order by idade_inicio', (fid,))),
        'amortizacoes': limpo(sql(dsn, 'select * from public.financiamento_amortizacao_extra where financiamento_id = %s order by id', (fid,))),
        'ajustes': limpo(sql(dsn, 'select * from public.financiamento_ajuste_saldo where financiamento_id = %s order by id', (fid,))),
    }


def diferencas(a, b, limite=8):
    saida = []
    for secao in a:
        if len(a[secao]) != len(b[secao]):
            saida.append((secao, 'linhas', len(a[secao]), len(b[secao])))
            continue
        for i, (x, y) in enumerate(zip(a[secao], b[secao])):
            for k in x:
                if x[k] != y.get(k):
                    saida.append((secao, i + 1, k, x[k], y.get(k)))
    return saida[:limite]


def fin_id(dsn, nome=NOME):
    return sql(dsn, 'select id from public.financiamento where nome = %s', (nome,))[0]['id']


def falha(dsn, funcao, *args, usuario=None):
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, funcao, *args, **({'usuario': usuario} if usuario else {}))
    return erro.value.pgcode, erro.value.diag.message_primary, erro.value.diag.message_hint


def novo(dsn, funcao, *args, chave=None):
    return rpc(dsn, funcao, *args, chave or str(uuid.uuid4()))


def historicas_flask(dsn, ate, nome=NOME):
    """Estado das parcelas quitadas antes do sistema no Flask (como no gastos.db): parcela e despesa pagas, sem movimento."""
    fid = fin_id(dsn, nome)
    sql(dsn, """update public.financiamento_parcela set status = 'pago', valor_pago = valor_previsto_total, dif_apurada = 0
                 where financiamento_id = %s and numero_parcela <= %s and status = 'pendente'""", (fid, ate))
    sql(dsn, """update public.conta c set status_pagamento = 'Pago', data_pagamento = c.data_vencimento
                  from public.financiamento_parcela p where c.financiamento_parcela_id = p.id and p.financiamento_id = %s
                   and p.numero_parcela <= %s""", (fid, ate))
    sql(dsn, """update public.financiamento set saldo_devedor_atual = (select saldo_devedor_apos_pagamento from public.financiamento_parcela
                 where financiamento_id = %s and numero_parcela = %s) where id = %s""", (fid, ate, fid))


def movimentos(dsn, fid):
    return sql(dsn, """select count(*) n from public.movimento_financeiro m join public.conta c on c.id = m.conta_id
                        join public.financiamento_parcela p on p.id = c.financiamento_parcela_id where p.financiamento_id = %s""",
               (fid,))[0]['n']


def por_competencia(dsn, nome):
    return {f"{p['data_vencimento']:%Y-%m}": p for p in sql(dsn, """select p.* from public.financiamento_parcela p
             join public.financiamento f on f.id = p.financiamento_id where f.nome = %s order by p.numero_parcela""", (nome,))}


@pytest.fixture(scope='module')
def fidelidade(cluster):  # noqa: F811
    """Mesmo roteiro no Flask (copia A) e no novo aplicativo (copia B): cadastro, 15 historicas, amortizacao, ate 22."""
    antigo, novo_ = com_tr(copiar(cluster)), com_tr(copiar(cluster))
    r = flask(antigo, [('perfil', PESSOAL), ('fin', 'post', '/api/financiamentos', FIXO)])
    assert r['fin'][0] == 201, r['fin']
    atribuir(novo_, 'PESSOAL')
    criado = novo(novo_, 'criar_financiamento', PESSOAL, FIXO)
    etapas = {'cadastro': (estado(antigo), estado(novo_))}
    historicas_flask(antigo, 15)
    novo(novo_, 'registrar_parcelas_historicas', PESSOAL, criado['data']['id'], {'ate_parcela': 15})
    etapas['historicas'] = (estado(antigo), estado(novo_))
    fid = fin_id(antigo)
    r = flask(antigo, [('perfil', PESSOAL), ('amort', 'post', f'/api/financiamentos/{fid}/amortizacao-extra', AMORTIZACAO)])
    assert r['amort'][0] == 201, r['amort']
    novo(novo_, 'registrar_amortizacao_extra', PESSOAL, criado['data']['id'], AMORTIZACAO)
    etapas['amortizacao'] = (estado(antigo), estado(novo_))
    return {'antigo': antigo, 'novo': novo_, 'etapas': etapas, 'criado': criado}


def test_cadastro_sac_tr_igual_ao_flask(fidelidade):
    antigo, novo_ = fidelidade['etapas']['cadastro']
    assert len(novo_['parcelas']) == 420 and len(novo_['contas']) == 420
    assert diferencas(antigo, novo_) == []
    assert fidelidade['criado']['parcelas_geradas'] == 420 and fidelidade['criado']['data']['parcelas_pagas'] == 0


def test_historicas_igual_ao_estado_do_flask_sem_movimento(fidelidade):
    antigo, novo_ = fidelidade['etapas']['historicas']
    assert diferencas(antigo, novo_) == []
    dsn = fidelidade['novo']
    assert movimentos(dsn, fin_id(dsn)) == 0
    assert sql(dsn, 'select count(*) n from financeiro.parcela_historica')[0]['n'] == 15


def test_amortizacao_reduzir_parcela_igual_ao_flask(fidelidade):
    antigo, novo_ = fidelidade['etapas']['amortizacao']
    assert diferencas(antigo, novo_) == []
    p = novo_['parcelas']
    assert p[14]['status'] == 'pago' and p[15]['status'] == 'pendente'
    assert p[15]['valor_amortizacao'] < Decimal('700')  # prestacao reduzida depois da amortizacao


def test_calibracao_caixa_preservada_no_motor_novo(cluster):  # noqa: F811
    """As tolerancias contra os valores cobrados pela Caixa (DFI + MIP) valem para o motor novo."""
    dsn = com_tr(copiar(cluster))
    atribuir(dsn, 'PESSOAL')
    criado = novo(dsn, 'criar_financiamento', PESSOAL, _payload_motor_caixa_tr())
    novo(dsn, 'registrar_parcelas_historicas', PESSOAL, criado['data']['id'], {'ate_parcela': 15})
    novo(dsn, 'registrar_amortizacao_extra', PESSOAL, criado['data']['id'], {**AMORTIZACAO, 'valor': 216670.0})
    parcelas = por_competencia(dsn, NOME_DFI)
    for comp, real in VALORES_REAIS_2025.items():
        s = parcelas[comp]
        pre = comp <= '2025-07'
        assert abs(s['valor_amortizacao'] - real['amortizacao']) <= Decimal('5.00'), comp
        assert abs(s['valor_juros'] - real['juros']) <= Decimal('15.00' if pre else '5.00'), comp
        assert abs(s['valor_seguro'] - real['seguro']) <= Decimal('5.00'), comp
        assert abs(s['valor_previsto_total'] - real['total']) <= Decimal('25.00' if pre else '15.00'), comp
    assert abs(parcelas['2026-05']['saldo_devedor_apos_pagamento'] - SALDO_DEVEDOR_TEO_PDF_2026_05) <= Decimal('100.00')
    assert abs(parcelas['2026-06']['valor_previsto_total'] - EVOLUCAO_REAL['2026-06']['total']) <= Decimal('15.00')


def test_cadastro_dfi_mip_igual_ao_flask(cluster):  # noqa: F811
    antigo, novo_ = com_tr(copiar(cluster)), com_tr(copiar(cluster))
    payload = _payload_motor_caixa_tr(prazo=60)
    r = flask(antigo, [('perfil', PESSOAL), ('fin', 'post', '/api/financiamentos', payload)])
    assert r['fin'][0] == 201, r['fin']
    atribuir(novo_, 'PESSOAL')
    novo(novo_, 'criar_financiamento', PESSOAL, payload)
    assert diferencas(estado(antigo, NOME_DFI), estado(novo_, NOME_DFI)) == []
    assert len(estado(novo_, NOME_DFI)['faixas']) == 8


@pytest.fixture(scope='module')
def cenario(fidelidade):
    """Cenario obrigatorio no novo aplicativo: 22 historicas (15 + amortizacao + 7), 398 pendentes."""
    dsn, fid = fidelidade['novo'], fidelidade['criado']['data']['id']
    novo(dsn, 'registrar_parcelas_historicas', PESSOAL, fid, {'ate_parcela': 22})
    historicas_flask(fidelidade['antigo'], 22)
    return dsn, fid


def _historico(dsn, fid):
    return {'parcelas': sql(dsn, 'select * from public.financiamento_parcela where financiamento_id = %s and numero_parcela <= 22 '
                                 'order by numero_parcela', (fid,)),
            'contas': sql(dsn, """select c.* from public.conta c join public.financiamento_parcela p on p.id = c.financiamento_parcela_id
                                  where p.financiamento_id = %s and p.numero_parcela <= 22 order by p.numero_parcela""", (fid,)),
            'amortizacoes': sql(dsn, 'select * from public.financiamento_amortizacao_extra where financiamento_id = %s order by id', (fid,))}


def test_cenario_420_parcelas_22_historicas(cenario):
    dsn, fid = cenario
    s = sql(dsn, """select count(*) filter (where status = 'pago') pagas, count(*) filter (where status = 'pendente') pendentes,
                           count(*) total, count(distinct numero_parcela) numeros from public.financiamento_parcela
                     where financiamento_id = %s""", (fid,))[0]
    assert (s['pagas'], s['pendentes'], s['total'], s['numeros']) == (22, 398, 420, 420)
    assert movimentos(dsn, fid) == 0
    h = _historico(dsn, fid)
    assert all(c['status_pagamento'] == 'Pago' and c['data_pagamento'] == c['data_vencimento'] for c in h['contas'])
    assert sql(dsn, 'select saldo_devedor_atual from public.financiamento where id = %s', (fid,))[0]['saldo_devedor_atual'] == \
        h['parcelas'][21]['saldo_devedor_apos_pagamento']


def test_segunda_amortizacao_preserva_historico_igual_ao_flask(cenario, fidelidade):
    """As sete provas: historicas intactas, nenhum movimento artificial, nenhuma despesa historica recriada, amortizacao
    anterior preservada, continuidade do saldo, so as futuras elegiveis recalculadas, sem duplicidade. E igual ao Flask."""
    dsn, fid = cenario
    antes = _historico(dsn, fid)
    contas_antes = {c['id'] for c in sql(dsn, 'select c.id from public.conta c join public.financiamento_parcela p '
                                              'on p.id = c.financiamento_parcela_id where p.financiamento_id = %s', (fid,))}
    futuras_antes = sql(dsn, 'select numero_parcela, valor_previsto_total from public.financiamento_parcela '
                             'where financiamento_id = %s and numero_parcela > 22 order by numero_parcela', (fid,))
    dados = {'data': '2026-03-01', 'valor': 20000, 'tipo': 'reduzir_parcela', 'observacoes': 'segunda'}
    chave = str(uuid.uuid4())
    r1 = novo(dsn, 'registrar_amortizacao_extra', PESSOAL, fid, dados, chave=chave)
    r2 = novo(dsn, 'registrar_amortizacao_extra', PESSOAL, fid, dados, chave=chave)
    assert r2['repetida'] is True and r1['parcelas_recalculadas'] == 398
    depois = _historico(dsn, fid)
    assert depois['parcelas'] == antes['parcelas'] and depois['contas'] == antes['contas']    # 1 e 3
    assert movimentos(dsn, fid) == 0                                                            # 2
    assert depois['amortizacoes'][0] == antes['amortizacoes'][0] and len(depois['amortizacoes']) == 2  # 4
    p23 = sql(dsn, 'select * from public.financiamento_parcela where financiamento_id = %s and numero_parcela = 23', (fid,))[0]
    base = antes['parcelas'][21]['saldo_devedor_apos_pagamento'] - 20000
    tr = TR_MENSAL['2026-03']
    assert abs(p23['saldo_devedor_apos_pagamento'] + p23['valor_amortizacao'] - base * (1 + tr)) <= Decimal('0.01')  # 5
    futuras = sql(dsn, 'select numero_parcela, valor_previsto_total from public.financiamento_parcela '
                       'where financiamento_id = %s and numero_parcela > 22 order by numero_parcela', (fid,))
    assert all(a['valor_previsto_total'] > b['valor_previsto_total'] for a, b in zip(futuras_antes[:300], futuras[:300]))  # 6
    contas_depois = {c['id'] for c in sql(dsn, 'select c.id from public.conta c join public.financiamento_parcela p '
                                               'on p.id = c.financiamento_parcela_id where p.financiamento_id = %s', (fid,))}
    assert contas_depois == contas_antes and len(contas_depois) == 420                          # 7
    # Fidelidade: o Flask, no mesmo estado, chega as mesmas parcelas.
    antigo = fidelidade['antigo']
    r = flask(antigo, [('perfil', PESSOAL), ('a', 'post', f'/api/financiamentos/{fin_id(antigo)}/amortizacao-extra', dados)])
    assert r['a'][0] == 201, r['a']
    assert diferencas(estado(antigo), estado(dsn)) == []


def test_regeneracao_e_reregistro_nao_alteram_historico(cenario):
    dsn, fid = cenario
    antes = _historico(dsn, fid)
    assert falha(dsn, 'regenerar_parcelas_financiamento', PESSOAL, fid)[2] == 'COM_EXECUCAO'
    assert novo(dsn, 'registrar_parcelas_historicas', PESSOAL, fid, {'ate_parcela': 22})['registradas'] == 0
    assert _historico(dsn, fid) == antes
    assert falha(dsn, 'registrar_parcelas_historicas', PESSOAL, fid, {'ate_parcela': 400}, str(uuid.uuid4()))[2] == 'PARCELA_FUTURA'


def test_registro_historico_e_permanente_e_coerente_no_banco(cenario):
    """Conferencia final: mesmo fora das funcoes (administrador, SQL direto), o registro das 22 historicas nao muda, nao
    sai e nao aceita linha incoerente; RLS forcado e sem acesso direto do navegador."""
    dsn, fid = cenario
    assert sql(dsn, 'select count(*) n from financeiro.parcela_historica where financiamento_id = %s', (fid,))[0]['n'] == 22
    antes = sql(dsn, 'select * from financeiro.parcela_historica order by parcela_id')
    for comando in ('update financeiro.parcela_historica set conta_id = null',
                    'delete from financeiro.parcela_historica', 'truncate financeiro.parcela_historica'):
        with pytest.raises(psycopg2.Error, match='permanente'):
            sql(dsn, comando)
    pendente = sql(dsn, "select id from public.financiamento_parcela where financiamento_id = %s and numero_parcela = 23", (fid,))[0]['id']
    with pytest.raises(psycopg2.Error, match='incoerente'):  # parcela pendente
        sql(dsn, 'insert into financeiro.parcela_historica (parcela_id, financiamento_id, perfil_financeiro_id, registrado_por) '
                 "values (%s, %s, %s, '00000000-0000-0000-0000-000000000000')", (pendente, fid, PESSOAL))
    assert sql(dsn, 'select * from financeiro.parcela_historica order by parcela_id') == antes
    # Sob os privilegios das funcoes do banco (SECURITY DEFINER, executadas como o dono): o gatilho vale do mesmo jeito.
    sql(dsn, """create function public.tentar_reabrir_historica() returns void language plpgsql security definer
                  set search_path = '' as $$ begin update financeiro.parcela_historica set conta_id = null; end $$;
                  grant execute on function public.tentar_reabrir_historica() to authenticated""")
    try:
        with pytest.raises(psycopg2.Error, match='permanente'):
            chamar(dsn, USUARIO_A, 'select public.tentar_reabrir_historica()')
    finally:
        sql(dsn, 'drop function public.tentar_reabrir_historica()')
    assert sql(dsn, 'select * from financeiro.parcela_historica order by parcela_id') == antes
    r = sql(dsn, "select c.relrowsecurity rls, c.relforcerowsecurity forcado, "
                 "has_table_privilege('authenticated', c.oid, 'select') sel, has_table_privilege('anon', c.oid, 'select') anon "
                 "from pg_class c where c.oid = 'financeiro.parcela_historica'::regclass")[0]
    assert r == {'rls': True, 'forcado': True, 'sel': False, 'anon': False}


def test_pagamento_e_estorno_em_despesas_protegem_parcela(cluster):  # noqa: F811
    """Integracao com FIN-CONTRATOS-2: parcela paga com debito fica intacta; com movimento estornado bloqueia o motor."""
    dsn = com_tr(copiar(cluster))
    atribuir(dsn, 'PESSOAL')
    fid = novo(dsn, 'criar_financiamento', PESSOAL, FIXO)['data']['id']
    novo(dsn, 'registrar_parcelas_historicas', PESSOAL, fid, {'ate_parcela': 2})
    banco = sql(dsn, "select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")[0]['id']
    c3 = sql(dsn, 'select c.id, c.valor from public.conta c join public.financiamento_parcela p on p.id = c.financiamento_parcela_id '
                  'where p.financiamento_id = %s and p.numero_parcela = 3', (fid,))[0]
    pg = rpc(dsn, 'pagar_despesa', PESSOAL, c3['id'], {'conta_bancaria_id': banco, 'data_pagamento': '2024-07-05',
                                                        'valor_pago': str(c3['valor']), 'valor_devido': str(c3['valor'])},
             str(uuid.uuid4()))
    p3 = sql(dsn, 'select * from public.financiamento_parcela where financiamento_id = %s and numero_parcela = 3', (fid,))[0]
    c3_pago = sql(dsn, 'select * from public.conta where id = %s', (c3['id'],))[0]
    novo(dsn, 'registrar_amortizacao_extra', PESSOAL, fid, {'data': '2024-07-20', 'valor': 10000, 'tipo': 'reduzir_parcela'})
    assert sql(dsn, 'select * from public.financiamento_parcela where id = %s', (p3['id'],))[0] == p3   # R1/R2
    assert sql(dsn, 'select * from public.conta where id = %s', (c3['id'],))[0] == c3_pago
    # Estorno: parcela 3 volta a pendente, mas a despesa tem movimento; amortizar antes dela e bloqueado (Regra 1/4).
    rpc(dsn, 'estornar_pagamento_despesa', PESSOAL, c3['id'], pg['movimento_id'],
        {'motivo': 'teste', 'data_estorno': '2024-07-06'}, str(uuid.uuid4()))
    erro = falha(dsn, 'registrar_amortizacao_extra', PESSOAL, fid, {'data': '2024-07-01', 'valor': 1000, 'tipo': 'reduzir_parcela'},
                 str(uuid.uuid4()))
    assert erro[2] == 'PARCELA_PROTEGIDA'
    assert sql(dsn, 'select count(*) n from public.financiamento_amortizacao_extra where financiamento_id = %s', (fid,))[0]['n'] == 1


def test_reduzir_prazo_igual_ao_flask_sem_parcelas_so_de_taxa(cluster):  # noqa: F811
    """Correcao: o Flask mantem as parcelas que ficaram sem saldo cobrando a taxa administrativa; o novo as remove."""
    antigo, novo_ = com_tr(copiar(cluster)), com_tr(copiar(cluster))
    dados = {**FIXO, 'prazo_total_meses': 60}
    prazo = {'data': '2024-07-01', 'valor': 300000, 'tipo': 'reduzir_prazo'}
    flask(antigo, [('perfil', PESSOAL), ('fin', 'post', '/api/financiamentos', dados)])
    historicas_flask(antigo, 2)
    r = flask(antigo, [('perfil', PESSOAL), ('a', 'post', f'/api/financiamentos/{fin_id(antigo)}/amortizacao-extra', prazo)])
    assert r['a'][0] == 201, r['a']
    atribuir(novo_, 'PESSOAL')
    fid = novo(novo_, 'criar_financiamento', PESSOAL, dados)['data']['id']
    novo(novo_, 'registrar_parcelas_historicas', PESSOAL, fid, {'ate_parcela': 2})
    r = novo(novo_, 'registrar_amortizacao_extra', PESSOAL, fid, prazo)
    a, b = estado(antigo), estado(novo_)
    so_taxa = [p for p in a['parcelas'] if p['saldo_devedor_apos_pagamento'] == 0 and p['valor_amortizacao'] == 0]
    assert so_taxa and all(p['valor_previsto_total'] == Decimal('25.00') for p in so_taxa)
    assert r['parcelas_removidas'] == len(so_taxa)
    n = len(b['parcelas'])
    assert n == 60 - len(so_taxa) and len(b['contas']) == n
    assert diferencas({k: a[k][:n] if k in ('parcelas', 'contas') else a[k] for k in a}, b) == []


def test_continuidade_com_parcelas_pendentes_antes_da_data(cluster):  # noqa: F811
    """Correcao: a base do recalculo e o saldo apos a parcela anterior a primeira recalculada (o Flask usa a ultima paga)."""
    dsn = com_tr(copiar(cluster))
    atribuir(dsn, 'PESSOAL')
    fid = novo(dsn, 'criar_financiamento', PESSOAL, {**FIXO, 'prazo_total_meses': 60})['data']['id']
    novo(dsn, 'registrar_parcelas_historicas', PESSOAL, fid, {'ate_parcela': 2})
    p = {x['numero_parcela']: x for x in sql(dsn, 'select * from public.financiamento_parcela where financiamento_id = %s', (fid,))}
    novo(dsn, 'registrar_amortizacao_extra', PESSOAL, fid, {'data': '2024-09-10', 'valor': 50000, 'tipo': 'reduzir_parcela'})
    q = {x['numero_parcela']: x for x in sql(dsn, 'select * from public.financiamento_parcela where financiamento_id = %s', (fid,))}
    assert all(q[n] == p[n] for n in (1, 2, 3, 4, 5))  # antes da data: intactas (inclusive as pendentes 3 a 5)
    tr = TR_MENSAL['2024-10']
    base = p[5]['saldo_devedor_apos_pagamento'] - 50000
    assert abs(q[6]['saldo_devedor_apos_pagamento'] + q[6]['valor_amortizacao'] - base * (1 + tr)) <= Decimal('0.01')
    # Fora de ordem (data anterior a uma amortizacao registrada): recusada, nada gravado.
    assert falha(dsn, 'registrar_amortizacao_extra', PESSOAL, fid, {'data': '2024-08-01', 'valor': 1000, 'tipo': 'reduzir_parcela'},
                 str(uuid.uuid4()))[2] == 'AMORTIZACAO_POSTERIOR'
    # Segunda amortizacao com a primeira ainda nao refletida na parcela anterior: base = saldo da anterior - as duas.
    novo(dsn, 'registrar_amortizacao_extra', PESSOAL, fid, {'data': '2024-09-20', 'valor': 10000, 'tipo': 'reduzir_parcela'})
    s = {x['numero_parcela']: x for x in sql(dsn, 'select * from public.financiamento_parcela where financiamento_id = %s', (fid,))}
    base = p[5]['saldo_devedor_apos_pagamento'] - 60000
    assert abs(s[6]['saldo_devedor_apos_pagamento'] + s[6]['valor_amortizacao'] - base * (1 + tr)) <= Decimal('0.01')


def test_tr_ausente_falha_sem_gravar(cluster):  # noqa: F811
    dsn = com_tr(copiar(cluster), sem='2025-08')
    atribuir(dsn, 'PESSOAL')
    antes = sql(dsn, 'select (select count(*) from public.financiamento) f, (select count(*) from public.conta) c, '
                     '(select count(*) from public.item_despesa) i')[0]
    erro = falha(dsn, 'criar_financiamento', PESSOAL, FIXO, str(uuid.uuid4()))
    assert erro[2] == 'TR_AUSENTE' and 'competencia 2025-08' in erro[1]
    assert sql(dsn, 'select (select count(*) from public.financiamento) f, (select count(*) from public.conta) c, '
                    '(select count(*) from public.item_despesa) i')[0] == antes


def test_price_amortiza_e_validacoes_do_flask(cluster):  # noqa: F811
    dsn = com_tr(copiar(cluster))
    atribuir(dsn, 'PESSOAL')
    preco = novo(dsn, 'criar_financiamento', PESSOAL, {**FIXO, 'nome': 'Price (ficticio)', 'sistema_amortizacao': 'PRICE',
                                                        'indexador_saldo': None, 'prazo_total_meses': 12})['data']['id']
    assert novo(dsn, 'registrar_amortizacao_extra', PESSOAL, preco, {'data': '2024-04-01', 'valor': 100, 'tipo': 'reduzir_parcela'})['success']
    assert falha(dsn, 'criar_financiamento', PESSOAL, {**FIXO, 'vigencias_seguro': []}, str(uuid.uuid4()))[1] == \
        'É obrigatório informar pelo menos uma vigência de seguro'
    assert falha(dsn, 'criar_financiamento', PESSOAL, {**FIXO, 'taxa_juros_nominal_anual': 0}, str(uuid.uuid4()))[1] == \
        'Taxa de juros não pode ser negativa'
    fid = novo(dsn, 'criar_financiamento', PESSOAL, {**FIXO, 'prazo_total_meses': 12})['data']['id']
    assert falha(dsn, 'registrar_amortizacao_extra', PESSOAL, fid, {'data': '2024-06-01', 'valor': 10 ** 7, 'tipo': 'reduzir_parcela'},
                 str(uuid.uuid4()))[2] == 'VALOR_ACIMA_DO_SALDO'
    r = rpc(dsn, 'regenerar_parcelas_financiamento', PESSOAL, fid)  # sem execucao: regenera, sem duplicar
    assert r['parcelas_geradas'] == 12
    assert sql(dsn, 'select count(*) n from public.conta c join public.financiamento_parcela p on p.id = c.financiamento_parcela_id '
                    'where p.financiamento_id = %s', (fid,))[0]['n'] == 12


def test_escritor_unico_permissoes_isolamento_e_idempotencia(cluster):  # noqa: F811
    dsn = com_tr(copiar(cluster))
    dados = {**FIXO, 'prazo_total_meses': 12}
    assert falha(dsn, 'criar_financiamento', PESSOAL, dados, str(uuid.uuid4()))[2] == 'SISTEMA_FLASK'  # perfil no Flask
    atribuir(dsn, 'PESSOAL')
    assert falha(dsn, 'criar_financiamento', PESSOAL, dados, str(uuid.uuid4()), usuario=USUARIO_B)[0] == '42501'
    assert falha(dsn, 'criar_financiamento', EMPRESA, dados, str(uuid.uuid4()))[0] == '42501'  # A so le a Empresa
    chave = str(uuid.uuid4())
    a = novo(dsn, 'criar_financiamento', PESSOAL, dados, chave=chave)
    b = novo(dsn, 'criar_financiamento', PESSOAL, dados, chave=chave)
    assert a['data']['id'] == b['data']['id'] and b['repetida'] is True
    assert sql(dsn, 'select count(*) n from public.financiamento where nome = %s', (NOME,))[0]['n'] == 1
    atribuir(dsn, 'PERFIL_B')
    assert falha(dsn, 'registrar_amortizacao_extra', ID['PERFIL_B'], a['data']['id'],
                 {'data': '2024-06-01', 'valor': 10, 'tipo': 'reduzir_parcela'}, str(uuid.uuid4()), usuario=USUARIO_B)[2] == 'NAO_ENCONTRADO'
    # O Flask recusa escrever no perfil do novo aplicativo (guarda de FIN-CONTRATOS-2).
    r = flask(dsn, [('perfil', PESSOAL), ('c', 'post', '/api/financiamentos', {**dados, 'nome': 'Pelo Flask'}),
                    ('a', 'post', f"/api/financiamentos/{a['data']['id']}/amortizacao-extra",
                     {'data': '2024-06-01', 'valor': 10, 'tipo': 'reduzir_parcela'})])
    assert r['c'][0] == 409 and r['a'][0] == 409
    assert sql(dsn, "select count(*) n from public.financiamento where nome = 'Pelo Flask'")[0]['n'] == 0


def test_exclusao_segura_igual_ao_flask(cluster):  # noqa: F811
    antigo, novo_ = com_tr(copiar(cluster)), com_tr(copiar(cluster))
    dados = {**FIXO, 'prazo_total_meses': 24}
    r = flask(antigo, [('perfil', PESSOAL), ('fin', 'post', '/api/financiamentos', dados),
                       ('del', 'delete', '/api/financiamentos/{fin}', None)])
    assert r['del'][0] == 200, r['del']
    atribuir(novo_, 'PESSOAL')
    fid = novo(novo_, 'criar_financiamento', PESSOAL, dados)['data']['id']
    assert rpc(novo_, 'excluir_financiamento', PESSOAL, fid)['parcelas_removidas'] == 24
    assert diferencas(estado(antigo), estado(novo_)) == []
    for dsn in (antigo, novo_):  # o item de despesa automatico fica, sem despesas
        assert sql(dsn, "select count(*) n from public.item_despesa where nome = %s and tipo = 'Financiamento'", (NOME,))[0]['n'] == 1
    # Com execucao financeira (parcela historica): recusada, nada removido.
    fid = novo(novo_, 'criar_financiamento', PESSOAL, dados)['data']['id']
    novo(novo_, 'registrar_parcelas_historicas', PESSOAL, fid, {'ate_parcela': 1})
    assert falha(novo_, 'excluir_financiamento', PESSOAL, fid)[2] == 'COM_EXECUCAO'
    assert len(estado(novo_)['parcelas']) == 24


def _par(cluster, dados):  # noqa: F811
    """Mesmo contrato no Flask (copia A) e no novo aplicativo (copia B)."""
    antigo, novo_ = com_tr(copiar(cluster)), com_tr(copiar(cluster))
    r = flask(antigo, [('perfil', PESSOAL), ('fin', 'post', '/api/financiamentos', dados)])
    assert r['fin'][0] == 201, r['fin']
    atribuir(novo_, 'PESSOAL')
    fid = novo(novo_, 'criar_financiamento', PESSOAL, dados)['data']['id']
    return antigo, novo_, fin_id(antigo, dados['nome']), fid


def test_edicao_estrutural_sem_execucao_igual_ao_flask(cluster):  # noqa: F811
    dados = {**FIXO, 'prazo_total_meses': 36}
    antigo, novo_, fa, fn = _par(cluster, dados)
    edicao = {**dados, 'valor_financiado': 420000.55, 'prazo_total_meses': 48, 'taxa_juros_nominal_anual': 10.1,
              'valor_seguro_mensal': 175.5, 'taxa_administracao_fixa': 30, 'regenerar_cronograma': True, 'ativo': True}
    edicao.pop('vigencias_seguro')
    r = flask(antigo, [('perfil', PESSOAL), ('e', 'put', f'/api/financiamentos/{fa}', edicao)])
    assert r['e'][0] == 200, r['e']
    novo(novo_, 'atualizar_financiamento', PESSOAL, fn, edicao)
    a, b = estado(antigo), estado(novo_)
    assert len(b['parcelas']) == 48 and diferencas(a, b) == []


def test_edicao_com_execucao_bloqueia_estrutural_e_renomeia_so_pendentes(cluster):  # noqa: F811
    dados = {**FIXO, 'prazo_total_meses': 24}
    antigo, novo_, fa, fn = _par(cluster, dados)
    historicas_flask(antigo, 2)
    novo(novo_, 'registrar_parcelas_historicas', PESSOAL, fn, {'ate_parcela': 2})
    estrutural = {'valor_financiado': 400000}
    r = flask(antigo, [('perfil', PESSOAL), ('e', 'put', f'/api/financiamentos/{fa}', estrutural)])
    assert r['e'][0] == 400
    assert falha(novo_, 'atualizar_financiamento', PESSOAL, fn, estrutural, str(uuid.uuid4()))[2] == 'COM_EXECUCAO'
    # Nome: permitido nos dois; o Flask deixa a descricao antiga em todas as despesas; o novo renomeia so as pendentes.
    nome = {'nome': 'Financiamento Renomeado (ficticio)', 'produto': 'SFH 2'}
    r = flask(antigo, [('perfil', PESSOAL), ('e', 'put', f'/api/financiamentos/{fa}', nome)])
    assert r['e'][0] == 200, r['e']
    novo(novo_, 'atualizar_financiamento', PESSOAL, fn, nome)
    a, b = estado(antigo, nome['nome']), estado(novo_, nome['nome'])
    sem_descricao = lambda e: {**e, 'contas': [{k: v for k, v in c.items() if k != 'descricao'} for c in e['contas']]}  # noqa: E731
    assert diferencas(sem_descricao(a), sem_descricao(b)) == []
    assert all(c['descricao'].startswith(NOME) for c in a['contas'])
    assert [c['descricao'].startswith(NOME) for c in b['contas']] == [True, True] + [False] * 22


def test_vigencia_nova_igual_ao_flask_e_despesa_acompanha(cluster):  # noqa: F811
    """Recalculo so do seguro: parcelas iguais ao Flask; correcao: a despesa pendente acompanha (no Flask fica com o valor
    antigo, como as 398 despesas reais R$ 1,00 acima das parcelas)."""
    dados = {**FIXO, 'prazo_total_meses': 24}
    antigo, novo_, fa, fn = _par(cluster, dados)
    historicas_flask(antigo, 2)
    novo(novo_, 'registrar_parcelas_historicas', PESSOAL, fn, {'ate_parcela': 2})
    vig = {'competencia_inicio': '2025-05', 'valor_mensal': 240.07, 'observacoes': 'reajuste'}
    r = flask(antigo, [('perfil', PESSOAL), ('v', 'post', f'/api/financiamentos/{fa}/vigencias-seguro', vig)])
    assert r['v'][0] == 201, r['v']
    rn = novo(novo_, 'adicionar_vigencia_seguro', PESSOAL, fn, vig)
    assert rn['data']['parcelas_atualizadas'] == r['v'][1]['data']['parcelas_atualizadas']
    a, b = estado(antigo), estado(novo_)
    assert diferencas({**a, 'contas': []}, {**b, 'contas': []}) == []
    # O defeito do Flask, reproduzido: as despesas das parcelas 13 a 15 (vigencia 2025-05 a 2025-07) ficam R$ 8,00 acima.
    dif = {p['numero_parcela']: c['valor'] - p['valor_previsto_total'] for p, c in zip(a['parcelas'], a['contas'])}
    assert all(abs(dif[n] - Decimal('8.00')) <= Decimal('0.01') for n in (13, 14, 15))
    assert all(c['valor'] == p['valor_previsto_total'] for p, c in zip(b['parcelas'], b['contas']))
    assert [c['valor'] for c in b['contas'][:2]] == [c['valor'] for c in a['contas'][:2]]  # historicas intactas


def test_ajuste_de_saldo_igual_ao_flask(cluster):  # noqa: F811
    dados = {**FIXO, 'prazo_total_meses': 36}
    antigo, novo_, fa, fn = _par(cluster, dados)
    historicas_flask(antigo, 2)
    novo(novo_, 'registrar_parcelas_historicas', PESSOAL, fn, {'ate_parcela': 2})
    ajuste = {'numero_parcela': 2, 'saldo_devedor_real': 471234.56, 'observacao': 'extrato Caixa'}
    r = flask(antigo, [('perfil', PESSOAL), ('a', 'post', f'/api/financiamentos/{fa}/ajustar-saldo', ajuste)])
    assert r['a'][0] == 200, r['a']
    rn = novo(novo_, 'ajustar_saldo_devedor', PESSOAL, fn, ajuste)
    assert rn['parcelas_recalculadas'] == r['a'][1]['parcelas_recalculadas'] == 34
    a, b = estado(antigo), estado(novo_)
    assert diferencas(a, b) == []
    assert b['parcelas'][0]['status'] == b['parcelas'][1]['status'] == 'pago'
    # Sem recalculo: so o registro e o estado do contrato, igual ao Flask.
    sem = {'numero_parcela': 3, 'saldo_devedor_real': 470000, 'recalcular_parcelas_futuras': False}
    r = flask(antigo, [('perfil', PESSOAL), ('a', 'post', f'/api/financiamentos/{fa}/ajustar-saldo', sem)])
    assert r['a'][0] == 200, r['a']
    novo(novo_, 'ajustar_saldo_devedor', PESSOAL, fn, sem)
    assert diferencas(estado(antigo), estado(novo_)) == []
    # Parcela protegida na faixa (paga em Despesas): recusado, nada gravado.
    banco = sql(novo_, "select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")[0]['id']
    c5 = sql(novo_, 'select c.id, c.valor from public.conta c join public.financiamento_parcela p on p.id = c.financiamento_parcela_id '
                    'where p.financiamento_id = %s and p.numero_parcela = 5', (fn,))[0]
    rpc(novo_, 'pagar_despesa', PESSOAL, c5['id'], {'conta_bancaria_id': banco, 'data_pagamento': '2024-09-05',
                                                     'valor_pago': str(c5['valor']), 'valor_devido': str(c5['valor'])}, str(uuid.uuid4()))
    antes = estado(novo_)
    assert falha(novo_, 'ajustar_saldo_devedor', PESSOAL, fn, {'numero_parcela': 3, 'saldo_devedor_real': 1000},
                 str(uuid.uuid4()))[2] == 'PARCELA_PROTEGIDA'
    assert estado(novo_) == antes


@pytest.mark.parametrize('extra', [
    {'nome': 'SAC sem indexador (ficticio)', 'indexador_saldo': None},
    {'nome': 'SAC IPCA (ficticio)', 'indexador_saldo': 'IPCA'},
    {'nome': 'SAC nominal (ficticio)', 'indexador_saldo': None, 'modo_taxa_mensal': 'nominal_dividida_12'},
    {'nome': 'PRICE (ficticio)', 'sistema_amortizacao': 'PRICE', 'indexador_saldo': None},
    {'nome': 'SIMPLES (ficticio)', 'sistema_amortizacao': 'SIMPLES', 'indexador_saldo': None},
    {'nome': 'PRICE DFI MIP (ficticio)', 'sistema_amortizacao': 'PRICE', 'indexador_saldo': None, 'seguro_modo': 'estimado_dfi_mip',
     'seguro_data_nascimento_titular': '1979-02-01', 'seguro_fator_dfi': 0.0489, 'vigencias_seguro': []},
])
def test_demais_modalidades_iguais_ao_flask(cluster, extra):  # noqa: F811
    """Cadastro, edicao estrutural (regenera) e regeneracao de SAC sem TR, PRICE e SIMPLES iguais ao Flask ao centavo."""
    dados = {**FIXO, 'prazo_total_meses': 120, **extra}
    antigo, novo_ = com_tr(copiar(cluster)), com_tr(copiar(cluster))
    for dsn in (antigo, novo_):  # IPCA ficticio de 2024-2025 (indexador_mensal, em %)
        sql(dsn, """insert into public.indexador_mensal (nome, data_referencia, valor, criado_em)
                    select 'IPCA', d::date, 0.35 + extract(month from d) / 100.0, now()
                      from generate_series('2024-05-01'::date, '2025-12-01'::date, interval '1 month') d""")
    r = flask(antigo, [('perfil', PESSOAL), ('fin', 'post', '/api/financiamentos', dados)])
    assert r['fin'][0] == 201, r['fin']
    atribuir(novo_, 'PESSOAL')
    fn = novo(novo_, 'criar_financiamento', PESSOAL, dados)['data']['id']
    nome = dados['nome']
    assert diferencas(estado(antigo, nome), estado(novo_, nome)) == []
    edicao = {'valor_financiado': 333333.33, 'prazo_total_meses': 96, 'taxa_juros_nominal_anual': 11.27}
    r = flask(antigo, [('perfil', PESSOAL), ('e', 'put', f'/api/financiamentos/{fin_id(antigo, nome)}', edicao)])
    assert r['e'][0] == 200, r['e']
    novo(novo_, 'atualizar_financiamento', PESSOAL, fn, edicao)
    assert diferencas(estado(antigo, nome), estado(novo_, nome)) == []
    r = flask(antigo, [('perfil', PESSOAL), ('g', 'post', f'/api/financiamentos/{fin_id(antigo, nome)}/regenerar-parcelas', {})])
    assert r['g'][0] == 200, r['g']
    rpc(novo_, 'regenerar_parcelas_financiamento', PESSOAL, fn)
    assert diferencas(estado(antigo, nome), estado(novo_, nome)) == []
    # Amortizacoes (reduzir parcela e reduzir prazo) e ajuste de saldo, com 2 parcelas historicas.
    fa = fin_id(antigo, nome)
    historicas_flask(antigo, 2, nome)
    novo(novo_, 'registrar_parcelas_historicas', PESSOAL, fn, {'ate_parcela': 2})
    for passo in ({'data': '2024-06-20', 'valor': 25000, 'tipo': 'reduzir_parcela'},
                  {'data': '2024-06-25', 'valor': 40000, 'tipo': 'reduzir_prazo'}):
        r = flask(antigo, [('perfil', PESSOAL), ('a', 'post', f'/api/financiamentos/{fa}/amortizacao-extra', passo)])
        assert r['a'][0] == 201, r['a']
        novo(novo_, 'registrar_amortizacao_extra', PESSOAL, fn, passo)
        assert diferencas(estado(antigo, nome), estado(novo_, nome)) == [], passo
    ajuste = {'numero_parcela': 3, 'saldo_devedor_real': 251234.56}
    r = flask(antigo, [('perfil', PESSOAL), ('a', 'post', f'/api/financiamentos/{fa}/ajustar-saldo', ajuste)])
    assert r['a'][0] == 200, r['a']
    novo(novo_, 'ajustar_saldo_devedor', PESSOAL, fn, ajuste)
    assert diferencas(estado(antigo, nome), estado(novo_, nome)) == []


def test_simulacao_de_quitacao_igual_ao_flask_sem_gravar(fidelidade):
    """So leitura: mesmo resultado do Flask (SAC/TR, TR da competencia, desconto) e nada gravado; quem so le simula."""
    antigo, dsn = fidelidade['antigo'], fidelidade['novo']
    pedido = {'data_quitacao': '2025-12-10', 'desconto_banco_percentual': 12.5}
    r = flask(antigo, [('perfil', PESSOAL), ('q', 'post', f'/api/financiamentos/{fin_id(antigo)}/simular-quitacao', pedido)])
    assert r['q'][0] == 200, r['q']
    antes = estado(dsn)
    n = rpc(dsn, 'simular_quitacao', PESSOAL, fin_id(dsn), pedido)
    assert estado(dsn) == antes
    f, nv = r['q'][1]['data'], n['data']
    for k, v in f.items():
        if k in ('financiamento_id',):
            continue
        if isinstance(v, float):
            assert abs(v - float(nv[k])) < 1e-6, k
        else:
            assert v == nv[k], (k, v, nv[k])
    assert falha(dsn, 'simular_quitacao', PESSOAL, fin_id(dsn), pedido, usuario=USUARIO_B)[0] == '42501'  # sem acesso ao perfil
    # FIN-AJUSTE-FINANCIAMENTO-REAL-01: depois da ultima TR publicada (2060-12 aqui), a projetada, com aviso; lacuna
    # entre publicadas continua recusada.
    futura = rpc(dsn, 'simular_quitacao', PESSOAL, fin_id(dsn), {'data_quitacao': '2099-01-10'})['data']
    assert any('(projetada: TR de 2060-12, a última publicada)' in o for o in futura['observacoes'])
    sql(dsn, "delete from public.indice_tr_mensal where competencia = '2030-01'")
    assert falha(dsn, 'simular_quitacao', PESSOAL, fin_id(dsn), {'data_quitacao': '2030-01-10'})[2] == 'TR_AUSENTE'


def test_reversao_remove_o_motor_e_volta(cluster):  # noqa: F811
    """A reversao tira funcoes, registro historico e indices, devolve o saldo pela cadeia da 1120; reaplicar volta igual."""
    from pathlib import Path
    from tests.test_supabase_recorrencia import ROOT
    supabase = Path(ROOT) / 'supabase'
    dsn = copiar(cluster)
    catalogo = ("select p.oid::regprocedure::text s, md5(p.prosrc) c, coalesce(p.proacl::text, '') a from pg_proc p "
                "join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro'")
    indices = "select indexname from pg_indexes where indexname in ('financiamento_parcela_numero_unico', 'conta_financiamento_parcela_unica')"
    completo = {r['s']: r for r in sql(dsn, catalogo)}

    def executar(arquivo):
        conn = psycopg2.connect(dsn)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(arquivo.read_text(encoding='utf-8'))
        finally:
            conn.close()

    # FIN-AJUSTE-FINANCIAMENTO-REAL-01: a 20261204 redefine funcoes do motor; a reversao e em ordem (a mais nova antes).
    executar(supabase / 'reversao' / '20261204090000_tr_projetada_anterior.sql')
    com = {r['s']: r for r in sql(dsn, catalogo)}
    executar(supabase / 'reversao' / '20261123090000_remover_motor_financiamentos.sql')
    sem = {r['s']: r for r in sql(dsn, catalogo)}
    removidas = set(com) - set(sem)
    assert {'financeiro.criar_financiamento(integer,jsonb,uuid)', 'financeiro.fin_r(numeric)',
            'financeiro.simular_quitacao(integer,integer,jsonb)', 'financeiro.atualizar_financiamento(integer,integer,jsonb,uuid)'} <= removidas
    assert all(s.startswith('financeiro.') for s in removidas) and len(removidas) == len(sem.keys() ^ com.keys())
    assert sql(dsn, indices) == [] and sql(dsn, "select to_regclass('financeiro.parcela_historica') r")[0]['r'] is None
    origem = (supabase / 'migrations' / '20261120090000_financeiro_contratos_pagamento.sql').read_text(encoding='utf-8')
    corpo = sql(dsn, "select prosrc from pg_proc where oid = 'financeiro.saldo_devedor_pelas_parcelas(integer)'::regprocedure")[0]['prosrc']
    assert corpo in origem
    assert set(sem) < set(com) and all(sem[s] == com[s] for s in sem if s != 'financeiro.saldo_devedor_pelas_parcelas(integer)')
    executar(supabase / 'migrations' / '20261123090000_financeiro_financiamentos_motor.sql')
    assert {r['s']: r for r in sql(dsn, catalogo)} == com and len(sql(dsn, indices)) == 2
    executar(supabase / 'migrations' / '20261204090000_financeiro_tr_projetada.sql')
    assert {r['s']: r for r in sql(dsn, catalogo)} == completo
