"""
Testes FIN-MVP-MOB-01 — integridade financeira da Mobilidade e combustivel Flex (migration 20261215090000), em cluster
PostgreSQL local descartavel e com dados ficticios.

Veiculo simulado sem reflexo financeiro real; com a recorrencia de combustivel ativa, ela e a fonte unica da despesa
(confirmacao, geracao, reativacao, troca de modalidade e Dashboard); IPVA, seguro e licenciamento identificados pela
obrigacao e pelo periodo; custo novo so nas ocorrencias futuras elegiveis; ids e vinculos preservados; calculo Flex,
precedencia entre custo manual e calculado e parametros gravados na confirmacao; a reversao.
"""
import datetime as dt
import json
import uuid
from decimal import Decimal

import pytest
from dateutil.relativedelta import relativedelta

from tests.test_supabase_cartoes import CARTAO, rpc
from tests.test_supabase_mobilidade_escrita import (  # noqa: F401  (fixtures de modulo reaproveitadas)
    HOJE,
    M2,
    M3,
    PESSOAL,
    REVERSAO_1215,
    MIGRATION_1215,
    VEICULO_1,
    VEICULO_2,
    banco,
    chave,
    cluster,
    erro,
    prevista,
)
from tests.test_supabase_recorrencia import PG_BIN, USUARIO_A, chamar, gerar_confirmado, sql

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

MES = HOJE.replace(day=1)
PROXIMO = MES + relativedelta(months=1)
DEPOIS = MES + relativedelta(months=2)
SIMULADO = {**VEICULO_1, 'meses_futuros': 12}
ATIVO = dict(VEICULO_2)
FLEX = {'nome': 'Flex (ficticio)', 'tipo': 'carro', 'combustivel': 'flex', 'status': 'ATIVO', 'data_inicio': HOJE.isoformat(),
        'autonomia_gasolina_km_l': 10, 'autonomia_etanol_km_l': 7, 'preco_gasolina': 6, 'preco_etanol': 4,
        'combustivel_referencia': 'gasolina', 'km_mensal_estimado': 1000, 'custo_combustivel_modo': 'CALCULADO'}


def criar(dsn, dados):
    return rpc(dsn, 'criar_veiculo', PESSOAL, dados, chave())['veiculo_id']


def ativar(dsn, veiculo, meio='pix', inicio=MES, **extra):
    return rpc(dsn, 'ativar_mobilidade', PESSOAL, {'tipo_modalidade': 'VEICULO', 'origem_id': veiculo, 'meio_pagamento': meio,
                                                   'data_inicio': inicio.isoformat(), 'confirmado': True, **extra}, chave())


def contas_item(dsn, item):
    return sql(dsn, 'select id, mes_referencia, valor, status_pagamento from public.conta where item_despesa_id = %s order by 2, 1', (item,))


def previstas(dsn, veiculo, tipo='COMBUSTIVEL'):
    return sql(dsn, 'select * from public.despesa_prevista where origem_id = %s and origem_tipo = %s and obrigacao = %s '
                    'order by periodo_referencia, id', (veiculo, 'VEICULO', tipo))


def dados_financeiros(dsn):
    """Tudo o que nao pode mudar por causa da Mobilidade: contas, compras, movimentos e saldos."""
    return sql(dsn, "select (select md5(coalesce(string_agg(x::text, '|' order by x.id), '')) from public.conta x) contas, "
                    "(select md5(coalesce(string_agg(x::text, '|' order by x.id), '')) from public.lancamento_agregado x) compras, "
                    "(select md5(coalesce(string_agg(x::text, '|' order by x.id), '')) from public.movimento_financeiro x) movimentos, "
                    "(select md5(coalesce(string_agg(x::text, '|' order by x.id), '')) from public.conta_bancaria x) bancos")


def dashboard(dsn, mes=MES):
    return rpc(dsn, 'dashboard_resumo_tela', PESSOAL, mes.strftime('%Y-%m'))


def despesas_do_mes(dsn):
    """Saidas do mes no fluxo do Dashboard (contas + previsoes que contam) e as despesas previstas do painel."""
    painel = dashboard(dsn)
    return Decimal(str(painel['fluxo_caixa']['saidas'][-1])), Decimal(str(painel['operacional']['despesas_previstas_mes']['valor']))


def saidas_previstas(dsn):
    r = sql(dsn, "select financeiro.saidas_lastro(%s, %s::jsonb) r", (PESSOAL, json.dumps({'ano': MES.year, 'mes': MES.month})))[0]['r']
    return [s for s in (r or []) if s['tipo_entidade'] == 'DESPESA_PREVISTA']


def conta_bancaria(dsn):
    return sql(dsn, "insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, saldo_atual, saldo_inicial, status, "
                    "cor_display) values (%s, 'Conta teste (ficticia)', 'Banco ficticio', 'corrente', 1000, 1000, 'ATIVO', '#000') "
                    "returning id", (PESSOAL,))[0]['id']


def pagar(dsn, conta, banco_id):
    valor = sql(dsn, 'select valor from public.conta where id = %s', (conta,))[0]['valor']
    return chamar(dsn, USUARIO_A, 'select financeiro.pagar_despesa(p_perfil_id => %s, p_conta_id => %s, p_chave => %s, p_dados => %s::jsonb)',
                  (PESSOAL, conta, str(uuid.uuid4()), json.dumps({'conta_bancaria_id': banco_id, 'data_pagamento': HOJE.isoformat(),
                                                                  'valor_pago': str(valor), 'valor_devido': str(valor)})))


# =====================================================================================================================
# Veiculo simulado
# =====================================================================================================================

def test_simulado_sem_reflexo_financeiro_real(banco):
    antes, base = dashboard(banco), dados_financeiros(banco)
    v = criar(banco, SIMULADO)
    assert len(previstas(banco, v)) == 12  # continua nas telas de Mobilidade
    assert rpc(banco, 'projecoes_mobilidade_tela', PESSOAL, 'VEICULO', v, 12)
    assert dashboard(banco) == antes
    assert dados_financeiros(banco) == base
    # Vencida: nao vira alerta de prevista atrasada; nas saidas sem lastro tambem nao entra.
    sql(banco, "update public.despesa_prevista set data_atual_prevista = %s where origem_id = %s and obrigacao = 'COMBUSTIVEL'",
        (MES - relativedelta(months=1), v))
    assert not [a for a in dashboard(banco)['alertas'] if a['tipo'] == 'prevista']
    sql(banco, "update public.despesa_prevista set data_atual_prevista = data_prevista where origem_id = %s", (v,))
    assert saidas_previstas(banco) == []
    # Controle: o mesmo veiculo, efetivado, aparece nas saidas e no alerta (o filtro e so do simulado).
    rpc(banco, 'converter_veiculo', PESSOAL, v, {'data_inicio': HOJE.isoformat()})
    assert saidas_previstas(banco)
    sql(banco, "update public.despesa_prevista set data_atual_prevista = %s where origem_id = %s and obrigacao = 'COMBUSTIVEL'",
        (MES - relativedelta(months=1), v))
    assert [a for a in dashboard(banco)['alertas'] if a['tipo'] == 'prevista']


def test_simulado_nao_gera_despesa_e_converter_passa_a_contar(banco):
    v = criar(banco, SIMULADO)
    alvo = prevista(banco, 'VEICULO', v, 'COMBUSTIVEL')
    base = dados_financeiros(banco)
    e = erro(rpc, banco, 'confirmar_despesa_prevista', PESSOAL, alvo, {'meio_pagamento': 'pix'})
    assert e.diag.message_hint == 'VEICULO_SIMULADO' and dados_financeiros(banco) == base
    assert sql(banco, 'select status from public.despesa_prevista where id = %s', (alvo,)) == [{'status': 'PREVISTA'}]
    # Sem pagamento, confirmar so muda o status (nada financeiro).
    rpc(banco, 'confirmar_despesa_prevista', PESSOAL, alvo, {})
    assert dados_financeiros(banco) == base

    outro = criar(banco, {**SIMULADO, 'nome': 'Segundo (ficticio)'})
    sem = dashboard(banco)
    rpc(banco, 'converter_veiculo', PESSOAL, outro, {'data_inicio': HOJE.isoformat()})
    assert dashboard(banco) != sem  # efetivado: as previsoes passam a contar, sem criar conta nem compra
    assert dados_financeiros(banco) == base


# =====================================================================================================================
# Veiculo ativo: recorrencia como fonte unica
# =====================================================================================================================

def test_ativo_sem_duplicar_combustivel_nem_no_dashboard(banco):
    saidas_base, previstas_base = despesas_do_mes(banco)
    v = criar(banco, ATIVO)
    assert {p['status'] for p in previstas(banco, v)} == {'PREVISTA'}
    # Ativo sem recorrencia: a previsao conta uma vez.
    assert despesas_do_mes(banco) == (saidas_base + 200, previstas_base + 200)
    r = ativar(banco, v)
    assert any('suprimida' in a for a in r['avisos'])
    assert {p['status'] for p in previstas(banco, v)} == {'SUPRIMIDA'}
    item = r['recorrencia']['id']
    gerar_confirmado(banco, mes=MES.isoformat())
    gerar_confirmado(banco, mes=MES.isoformat())
    contas = contas_item(banco, item)
    assert [c['mes_referencia'].replace(day=1) for c in contas] == [MES, PROXIMO] and all(c['valor'] == Decimal('200.00') for c in contas)
    # Dashboard: o combustivel do mes aparece uma vez (a conta), nao somado a previsao.
    assert despesas_do_mes(banco) == (saidas_base + 200, previstas_base)
    # A suprimida nao pode ser confirmada; a tela de projecoes continua mostrando.
    alvo = previstas(banco, v)[0]['id']
    assert 'Apenas despesas PREVISTA' in str(erro(rpc, banco, 'confirmar_despesa_prevista', PESSOAL, alvo, {'meio_pagamento': 'pix'}))
    assert rpc(banco, 'projecoes_mobilidade_tela', PESSOAL, 'VEICULO', v, 12)
    # Regerar nao faz a previsao voltar.
    rpc(banco, 'gerar_projecoes_veiculo', PESSOAL, v, {'meses_futuros': 18})
    assert {p['status'] for p in previstas(banco, v)} == {'SUPRIMIDA'} and len(previstas(banco, v)) == 18


def test_confirmar_em_competencia_coberta_e_recusado(banco):
    v = criar(banco, ATIVO)
    alvo = previstas(banco, v)[0]
    # Prevista anterior ao inicio da recorrencia: continua confirmavel (nao ha ocorrencia da recorrencia nesse mes).
    ativar(banco, v, inicio=PROXIMO)
    assert sql(banco, 'select status from public.despesa_prevista where id = %s', (alvo['id'],)) == [{'status': 'PREVISTA'}]
    criada = rpc(banco, 'confirmar_despesa_prevista', PESSOAL, alvo['id'], {'meio_pagamento': 'pix'})
    assert criada['entidade_criada']['tipo'] == 'conta'
    # Competencia da recorrencia: a data informada nao contorna.
    outra = criar(banco, {**ATIVO, 'nome': 'Terceiro (ficticio)'})
    ativar(banco, outra, inicio=PROXIMO)
    p = previstas(banco, outra)[0]
    base = dados_financeiros(banco)
    e = erro(rpc, banco, 'confirmar_despesa_prevista', PESSOAL, p['id'], {'meio_pagamento': 'pix', 'data_vencimento': PROXIMO.isoformat()})
    assert e.diag.message_hint == 'COMBUSTIVEL_COBERTO' and dados_financeiros(banco) == base


def test_ativar_nao_gera_competencia_ja_confirmada_com_despesa(banco):
    v = criar(banco, ATIVO)
    alvo = previstas(banco, v)[0]
    conta = rpc(banco, 'confirmar_despesa_prevista', PESSOAL, alvo['id'], {'meio_pagamento': 'pix'})['entidade_criada']['id']
    item = ativar(banco, v)['recorrencia']['id']
    gerar_confirmado(banco, mes=MES.isoformat())
    assert [c['mes_referencia'].replace(day=1) for c in contas_item(banco, item)] == [PROXIMO]  # o mes da confirmada nao repete
    assert sql(banco, 'select valor from public.conta where id = %s', (conta,)) == [{'valor': Decimal('200.00')}]
    registro = sql(banco, 'select situacao, motivo from financeiro.recorrencia_competencia where item_despesa_id = %s and competencia = %s', (item, MES))
    assert registro[0]['situacao'] == 'DISPENSADA' and 'coberta' in registro[0]['motivo']


def test_reativar_e_trocar_o_meio_nao_duplicam(banco):
    v = criar(banco, ATIVO)
    primeiro = ativar(banco, v)['recorrencia']['id']
    gerar_confirmado(banco, mes=MES.isoformat())
    assert len(contas_item(banco, primeiro)) == 2
    segundo = ativar(banco, v, meio='boleto')['recorrencia']['id']
    assert segundo != primeiro
    gerar_confirmado(banco, mes=DEPOIS.isoformat())
    assert len(contas_item(banco, primeiro)) == 2
    assert [c['mes_referencia'].replace(day=1) for c in contas_item(banco, segundo)] == [DEPOIS, DEPOIS + relativedelta(months=1)]


def test_trocar_de_modalidade_devolve_as_previsoes_nao_cobertas(banco):
    v = criar(banco, ATIVO)
    ativar(banco, v)
    gerar_confirmado(banco, mes=MES.isoformat())  # contas de MES e PROXIMO
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'combustivel_valor_mensal': 300})
    ass = rpc(banco, 'criar_assinatura_mobilidade', PESSOAL, {'nome': 'Assinatura (ficticia)', 'valor_mensal': 900}, chave())['assinatura_id']
    rpc(banco, 'ativar_mobilidade', PESSOAL, {'tipo_modalidade': 'ASSINATURA', 'origem_id': ass, 'confirmado': True}, chave())
    por_mes = {p['data_prevista']: p for p in previstas(banco, v)}
    assert por_mes[MES]['status'] == 'SUPRIMIDA' and por_mes[PROXIMO]['status'] == 'SUPRIMIDA'  # ja ha conta
    assert por_mes[DEPOIS]['status'] == 'PREVISTA' and por_mes[DEPOIS]['valor_previsto'] == Decimal('300.00')  # valor atual


# =====================================================================================================================
# Anuais: obrigacao + periodo
# =====================================================================================================================

def test_mudar_o_mes_nao_recria_o_periodo_confirmado(banco):
    v = criar(banco, SIMULADO)
    rpc(banco, 'converter_veiculo', PESSOAL, v, {'data_inicio': HOJE.isoformat()})
    alvo = previstas(banco, v, 'IPVA')[0]
    rpc(banco, 'confirmar_despesa_prevista', PESSOAL, alvo['id'], {'meio_pagamento': 'pix'})
    novo_mes = M3 if M3 != alvo['data_prevista'].month else M2
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'ipva_mes': novo_mes, 'meses_futuros': 12})
    linhas = previstas(banco, v, 'IPVA')
    do_ano = [p for p in linhas if p['periodo_referencia'] == alvo['periodo_referencia']]
    assert len(do_ano) == 1 and do_ano[0]['status'] == 'CONFIRMADA' and do_ano[0]['id'] == alvo['id']
    # Janela maior: o ano seguinte e outro periodo, e entra no mes novo.
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'meses_futuros': 26})
    seguintes = [p for p in previstas(banco, v, 'IPVA') if p['periodo_referencia'] != alvo['periodo_referencia']]
    assert seguintes and all(p['status'] == 'PREVISTA' and p['data_prevista'].month == novo_mes for p in seguintes)


def test_identidade_vale_para_seguro_licenciamento_e_data_fora_da_janela(banco):
    v = criar(banco, SIMULADO)
    rpc(banco, 'converter_veiculo', PESSOAL, v, {'data_inicio': HOJE.isoformat()})
    for tipo, campo in (('SEGURO', 'seguro_mes'), ('LICENCIAMENTO', 'licenciamento_mes')):
        alvo = previstas(banco, v, tipo)[0]
        rpc(banco, 'ignorar_despesa_prevista', PESSOAL, alvo['id'])
        # Mesmo com a acao antes do inicio da janela (o mes ja passou), o periodo continua identificado.
        sql(banco, 'update public.despesa_prevista set data_prevista = %s, data_original_prevista = %s, data_atual_prevista = %s where id = %s',
            (alvo['periodo_referencia'], alvo['periodo_referencia'], alvo['periodo_referencia'], alvo['id']))
        mes_novo = 12 if alvo['data_prevista'].month != 12 else 11
        rpc(banco, 'editar_veiculo', PESSOAL, v, {campo: mes_novo, 'meses_futuros': 12})
        assert [p['id'] for p in previstas(banco, v, tipo) if p['periodo_referencia'] == alvo['periodo_referencia']] == [alvo['id']]


def test_mudar_o_mes_de_prevista_nao_confirmada_preserva_o_id(banco):
    v = criar(banco, SIMULADO)
    alvo = previstas(banco, v, 'IPVA')[0]
    novo_mes = M3 if M3 != alvo['data_prevista'].month else M2
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'ipva_mes': novo_mes, 'ipva_valor': 1500, 'meses_futuros': 12})
    depois = [p for p in previstas(banco, v, 'IPVA') if p['id'] == alvo['id']]
    assert len(depois) == 1 and depois[0]['data_prevista'].month == novo_mes and depois[0]['valor_previsto'] == Decimal('1500.00')


def test_indice_unico_impede_duplicar_a_obrigacao(banco):
    v = criar(banco, SIMULADO)
    p = previstas(banco, v)[0]
    with pytest.raises(psycopg2.errors.UniqueViolation):
        sql(banco, 'insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista, '
                   'data_original_prevista, data_atual_prevista, valor_previsto, status, obrigacao, periodo_referencia) '
                   "select perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista, data_original_prevista, "
                   "data_atual_prevista, valor_previsto, 'ADIADA', obrigacao, periodo_referencia from public.despesa_prevista where id = %s", (p['id'],))


# =====================================================================================================================
# Custo novo: so o futuro elegivel
# =====================================================================================================================

def test_custo_novo_atualiza_recorrencia_e_so_as_futuras_elegiveis(banco):
    v = criar(banco, ATIVO)
    item = ativar(banco, v)['recorrencia']['id']
    gerar_confirmado(banco, mes=DEPOIS.isoformat())  # MES, PROXIMO, DEPOIS e o seguinte
    contas = contas_item(banco, item)
    assert len(contas) == 4
    banco_id = conta_bancaria(banco)
    pago = contas[2]['id']  # futura ja paga
    pagar(banco, pago, banco_id)
    movimentos = sql(banco, 'select id, valor from public.movimento_financeiro where conta_id = %s', (pago,))
    saldo = sql(banco, 'select saldo_atual from public.conta_bancaria where id = %s', (banco_id,))
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'combustivel_valor_mensal': 250})
    assert sql(banco, 'select valor from public.item_despesa where id = %s', (item,)) == [{'valor': Decimal('250.00')}]
    valores = {c['id']: c['valor'] for c in contas_item(banco, item)}
    assert valores[contas[0]['id']] == Decimal('200.00')  # mes corrente: nao e futuro
    assert valores[contas[1]['id']] == Decimal('250.00')  # futura pendente
    assert valores[pago] == Decimal('200.00')             # paga, com movimento
    assert valores[contas[3]['id']] == Decimal('250.00')
    assert sql(banco, 'select id, valor from public.movimento_financeiro where conta_id = %s', (pago,)) == movimentos
    assert sql(banco, 'select saldo_atual from public.conta_bancaria where id = %s', (banco_id,)) == saldo
    # Sem nova geracao para competencia que ja tem ocorrencia.
    gerar_confirmado(banco, mes=DEPOIS.isoformat())
    assert len(contas_item(banco, item)) == 4


def test_custo_novo_no_cartao_atualiza_a_previsao_e_a_fatura(banco):
    v = criar(banco, ATIVO)
    item = ativar(banco, v, meio='cartao', cartao_id=CARTAO)['recorrencia']['id']
    gerar_confirmado(banco, mes=PROXIMO.isoformat())
    compras = sql(banco, 'select id, mes_fatura, valor from public.lancamento_agregado where item_despesa_id = %s order by mes_fatura', (item,))
    assert len(compras) >= 2
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'combustivel_valor_mensal': 275})
    depois = {c['id']: c['valor'] for c in sql(banco, 'select id, valor from public.lancamento_agregado where item_despesa_id = %s', (item,))}
    atual, *futuras = compras
    assert atual['mes_fatura'] == MES and depois[atual['id']] == Decimal('200.00')
    assert all(depois[c['id']] == Decimal('275.00') for c in futuras)
    # Na fatura, a previsao continua pendente: fora do executado e no previsto com o valor novo.
    resumo = rpc(banco, 'fatura_por_categoria', PESSOAL, CARTAO, futuras[0]['mes_fatura'])
    assert resumo['total_fatura'] == 0 and resumo['total_previsto_pendente'] == 275


def test_veiculo_sem_recorrencia_nao_toca_em_despesa_alguma(banco):
    v = criar(banco, ATIVO)
    base = dados_financeiros(banco)
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'combustivel_valor_mensal': 999})
    assert dados_financeiros(banco) == base
    assert {p['valor_previsto'] for p in previstas(banco, v)} == {Decimal('999.00')}


# =====================================================================================================================
# Identificadores e vinculos
# =====================================================================================================================

def test_regerar_preserva_ids_e_valores_nao_tocados(banco):
    v = criar(banco, SIMULADO)
    antes = sql(banco, 'select id, data_prevista, valor_previsto, criado_em, atualizado_em from public.despesa_prevista where origem_id = %s order by id', (v,))
    rpc(banco, 'gerar_projecoes_veiculo', PESSOAL, v, {'meses_futuros': 12})
    assert sql(banco, 'select id, data_prevista, valor_previsto, criado_em, atualizado_em from public.despesa_prevista where origem_id = %s order by id', (v,)) == antes
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'combustivel_valor_mensal': 700, 'meses_futuros': 12})
    depois = sql(banco, "select id from public.despesa_prevista where origem_id = %s order by id", (v,))
    assert [d['id'] for d in depois] == [a['id'] for a in antes]


def test_vinculo_com_a_conta_e_a_compra(banco):
    v = criar(banco, ATIVO)
    p1, p2 = previstas(banco, v)[:2]
    conta = rpc(banco, 'confirmar_despesa_prevista', PESSOAL, p1['id'], {'meio_pagamento': 'pix'})['entidade_criada']['id']
    compra = rpc(banco, 'confirmar_despesa_prevista', PESSOAL, p2['id'], {'meio_pagamento': 'cartao', 'cartao_id': CARTAO})
    lancamento = compra['entidade_criada']['compra']['lancamentos'][0]
    linhas = {p['id']: p for p in previstas(banco, v)}
    assert linhas[p1['id']]['conta_id'] == conta and linhas[p1['id']]['lancamento_id'] is None
    assert linhas[p2['id']]['lancamento_id'] == lancamento and linhas[p2['id']]['conta_id'] is None
    # Excluir a conta nao apaga a prevista: so limpa o vinculo.
    sql(banco, 'delete from public.conta where id = %s', (conta,))
    assert sql(banco, 'select status, conta_id from public.despesa_prevista where id = %s', (p1['id'],)) == [{'status': 'CONFIRMADA', 'conta_id': None}]


# =====================================================================================================================
# Flex e custo
# =====================================================================================================================

def veiculo(dsn, v):
    return sql(dsn, 'select * from public.veiculo where id = %s', (v,))[0]


def test_flex_calcula_pelo_combustivel_de_referencia(banco):
    v = criar(banco, FLEX)
    r = veiculo(banco, v)
    assert (r['autonomia_km_l'], r['preco_medio_combustivel'], r['combustivel_valor_mensal']) == (Decimal('10.00'), Decimal('6.00'), Decimal('600.00'))
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'combustivel_referencia': 'etanol'})
    r = veiculo(banco, v)
    assert (r['autonomia_km_l'], r['preco_medio_combustivel'], r['combustivel_valor_mensal']) == (Decimal('7.00'), Decimal('4.00'), Decimal('571.43'))
    assert {p['valor_previsto'] for p in previstas(banco, v)} == {Decimal('571.43')}
    lido = rpc(banco, 'veiculos_tela', PESSOAL, v)
    assert lido['combustivel'] == 'flex' and lido['combustivel_referencia'] == 'etanol' and lido['custo_combustivel_modo'] == 'CALCULADO'
    assert lido['autonomia_gasolina_km_l'] == 10 and lido['preco_etanol'] == 4


def test_flex_valida_os_parametros(banco):
    for campos, trecho in (({'autonomia_etanol_km_l': None}, 'autonomia com gasolina e com etanol'),
                           ({'combustivel_referencia': 'diesel'}, 'combustível de referência'),
                           ({'km_mensal_estimado': None}, 'quilometragem mensal'),
                           ({'preco_gasolina': None}, 'preço por litro')):
        assert trecho in str(erro(criar, banco, {**FLEX, **campos}))
    assert 'Modo do custo' in str(erro(criar, banco, {**FLEX, 'custo_combustivel_modo': 'AUTO'}))
    assert sql(banco, "select count(*) n from public.veiculo where combustivel = 'flex'")[0]['n'] == 0


def test_alternar_manual_e_calculado_nunca_muda_valor_em_silencio(banco):
    v = criar(banco, FLEX)
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'custo_combustivel_modo': 'MANUAL', 'combustivel_valor_mensal': 450})
    assert veiculo(banco, v)['combustivel_valor_mensal'] == Decimal('450.00')
    # Em MANUAL, mudar referencia, preco e km nao altera o valor informado.
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'combustivel_referencia': 'etanol', 'preco_etanol': 5, 'km_mensal_estimado': 2000})
    r = veiculo(banco, v)
    assert r['combustivel_valor_mensal'] == Decimal('450.00') and r['autonomia_km_l'] == Decimal('7.00')
    # So ao escolher CALCULADO o valor passa a ser o da formula (2000 / 7 x 5).
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'custo_combustivel_modo': 'CALCULADO'})
    assert veiculo(banco, v)['combustivel_valor_mensal'] == Decimal('1428.57')
    # Em CALCULADO, um valor enviado nao prevalece sobre a formula.
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'combustivel_valor_mensal': 1})
    assert veiculo(banco, v)['combustivel_valor_mensal'] == Decimal('1428.57')


def test_combustivel_unico_continua_igual_e_pode_calcular(banco):
    v = criar(banco, ATIVO)
    r = veiculo(banco, v)
    assert r['custo_combustivel_modo'] == 'MANUAL' and r['combustivel_valor_mensal'] == Decimal('200.00')
    assert all(r[c] is None for c in ('autonomia_gasolina_km_l', 'autonomia_etanol_km_l', 'preco_gasolina', 'preco_etanol',
                                      'combustivel_referencia', 'km_mensal_estimado'))
    lido = rpc(banco, 'veiculos_tela', PESSOAL, v)
    assert 'custo_combustivel_modo' not in lido and 'combustivel_referencia' not in lido  # resposta como antes
    assert rpc(banco, 'editar_veiculo', PESSOAL, v, {'preco_medio_combustivel': 6, 'km_mensal_estimado': 600, 'custo_combustivel_modo': 'CALCULADO'})
    assert veiculo(banco, v)['combustivel_valor_mensal'] == Decimal('120.00')  # 600 / 30 x 6


def test_sair_do_flex_limpa_os_campos_e_mantem_a_autonomia_informada(banco):
    v = criar(banco, FLEX)
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'combustivel': 'gasolina', 'autonomia_km_l': 11, 'preco_medio_combustivel': 6, 'custo_combustivel_modo': 'MANUAL'})
    r = veiculo(banco, v)
    assert (r['combustivel'], r['autonomia_km_l'], r['combustivel_referencia'], r['autonomia_etanol_km_l']) == ('gasolina', Decimal('11.00'), None, None)


def test_confirmacao_grava_os_parametros_e_mudancas_nao_refazem_o_km(banco):
    v = criar(banco, FLEX)
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'combustivel_referencia': 'etanol'})
    p1 = previstas(banco, v)[0]
    rpc(banco, 'confirmar_despesa_prevista', PESSOAL, p1['id'], {})
    md = json.loads(sql(banco, 'select metadata from public.despesa_prevista where id = %s', (p1['id'],))[0]['metadata'])
    assert (md['combustivel'], md['autonomia_km_l'], md['preco_litro']) == ('etanol', 7, 4)
    km = veiculo(banco, v)['km_estimado_acumulado']
    assert km == Decimal('1000.00')  # 571,43 / 4 x 7 = 1000 km
    uso = rpc(banco, 'veiculo_uso_tela', PESSOAL, v, 3)
    # Trocar para gasolina nao muda o que ja foi consolidado
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'combustivel_referencia': 'gasolina', 'preco_gasolina': 7})
    assert veiculo(banco, v)['km_estimado_acumulado'] == km
    novo = rpc(banco, 'veiculo_uso_tela', PESSOAL, v, 3)
    assert uso['km_por_mes'] and novo['km_por_mes'] == uso['km_por_mes'] and novo['media_movel_km_mes'] == uso['media_movel_km_mes']


def test_confirmar_fora_de_ordem_conta_o_km(banco):
    v = criar(banco, {**ATIVO, 'preco_medio_combustivel': 5})
    p1, p2 = previstas(banco, v)[:2]
    rpc(banco, 'confirmar_despesa_prevista', PESSOAL, p2['id'], {})
    rpc(banco, 'confirmar_despesa_prevista', PESSOAL, p1['id'], {})
    assert veiculo(banco, v)['km_estimado_acumulado'] == Decimal('2400.00')  # 200 / 5 x 30, duas vezes


# =====================================================================================================================
# Migration e reversao
# =====================================================================================================================

def executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_migration_so_preenche_a_identidade_e_reversao_preserva(banco):
    v = criar(banco, SIMULADO)
    consulta = ("select id, perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista, data_original_prevista, "
                "data_atual_prevista, valor_previsto, status, metadata, criado_em, atualizado_em from public.despesa_prevista order by id")
    veic = ('select id, nome, tipo, combustivel, autonomia_km_l, status, data_inicio, combustivel_valor_mensal, preco_medio_combustivel, '
            'ipva_mes, ipva_valor, seguro_mes, seguro_valor, licenciamento_mes, licenciamento_valor, km_estimado_acumulado from public.veiculo order by id')
    antes, antes_v, base = sql(banco, consulta), sql(banco, veic), dados_financeiros(banco)
    executar(banco, REVERSAO_1215)
    assert sql(banco, "select to_regclass('public.ux_despesa_prevista_obrigacao_periodo') is null r")[0]['r']
    assert sql(banco, "select count(*) n from information_schema.columns where table_name = 'despesa_prevista' and column_name in ('obrigacao', 'conta_id')")[0]['n'] == 0
    assert sql(banco, consulta) == antes and sql(banco, veic) == antes_v
    executar(banco, MIGRATION_1215)
    assert sql(banco, consulta) == antes and sql(banco, veic) == antes_v and dados_financeiros(banco) == base
    identidade = sql(banco, 'select obrigacao, periodo_referencia, data_original_prevista from public.despesa_prevista where origem_id = %s', (v,))
    assert all(i['obrigacao'] for i in identidade)
    assert all(i['periodo_referencia'] == (i['data_original_prevista'].replace(month=1, day=1) if i['obrigacao'] != 'COMBUSTIVEL'
                                           else i['data_original_prevista'].replace(day=1)) for i in identidade)


def test_migration_recusa_duplicidade_e_reversao_recusa_perda_de_dados(banco):
    v = criar(banco, FLEX)
    assert 'veiculo Flex' in str(erro(executar, banco, REVERSAO_1215))
    sql(banco, 'delete from public.despesa_prevista where origem_id = %s', (v,))
    sql(banco, 'delete from public.veiculo where id = %s', (v,))
    v = criar(banco, ATIVO)
    rpc(banco, 'confirmar_despesa_prevista', PESSOAL, previstas(banco, v)[0]['id'], {'meio_pagamento': 'pix'})
    assert 'vinculadas' in str(erro(executar, banco, REVERSAO_1215))
    sql(banco, 'update public.despesa_prevista set conta_id = null')
    executar(banco, REVERSAO_1215)
    # Sem o indice, um banco com repeticao nao recebe a migration: nada e alterado.
    sql(banco, 'insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista, data_original_prevista, '
               'data_atual_prevista, valor_previsto, status, metadata) select perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista, '
               "data_original_prevista, data_atual_prevista, valor_previsto, 'PREVISTA', metadata from public.despesa_prevista where id = "
               '(select min(id) from public.despesa_prevista where origem_id = %s)', (v,))
    assert 'repetidas' in str(erro(executar, banco, MIGRATION_1215))
    assert sql(banco, "select count(*) n from information_schema.columns where table_name = 'despesa_prevista' and column_name = 'obrigacao'")[0]['n'] == 0


def test_funcoes_novas_sao_internas(banco):
    for assinatura in ('mob_periodo(text, date)', 'prevista_financeira(text, integer)', 'mob_sincronizar_combustivel(integer, integer, numeric)',
                       'mob_suprimir_combustivel(integer, integer)', 'mob_dados_flex(public.veiculo, jsonb)'):
        for papel in ('anon', 'authenticated'):
            assert sql(banco, f"select has_function_privilege('{papel}', 'financeiro.{assinatura}', 'execute') p")[0]['p'] is False, (assinatura, papel)
