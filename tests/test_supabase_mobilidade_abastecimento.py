"""
Testes FIN-MVP-MOB-01 (contrato complementar) — abastecimentos, quilometragem real e estimada, varios veiculos, cartoes fisicos,
vinculo com a despesa e troca de modalidade (migration 20261215090000), em cluster PostgreSQL local descartavel e com dados
ficticios.

Abastecimento e registro operacional: nunca cria despesa, com litros calculados e hodometro proprio de cada veiculo. A leitura
real manda na quilometragem e a estimativa so completa os dias depois dela. Na troca de modalidade, cada despesa futura da
anterior e decidida (manter ou substituir), com registro; o substituido fica preservado e fora dos indicadores.
"""
import datetime as dt
import json
from decimal import Decimal

import pytest
from dateutil.relativedelta import relativedelta

from tests.test_supabase_cartoes import CARTAO, MORADIA, rpc
from tests.test_supabase_mobilidade_escrita import (  # noqa: F401  (fixtures de modulo reaproveitadas)
    HOJE,
    PERFIL_B,
    PESSOAL,
    REGRA,
    REVERSAO_1215,
    VEICULO_2,
    banco,
    chave,
    cluster,
    erro,
)
from tests.test_supabase_mobilidade_integridade import (
    ATIVO,
    DEPOIS,
    FLEX,
    MES,
    PROXIMO,
    SIMULADO,
    ativar,
    conta_bancaria,
    contas_item,
    criar,
    dados_financeiros,
    dashboard,
    despesas_do_mes,
    executar,
    pagar,
    previstas,
    saidas_previstas,
)
from tests.test_supabase_recorrencia import PG_BIN, USUARIO_A, USUARIO_B, chamar, gerar_confirmado, sql

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

ONTEM = HOJE - dt.timedelta(days=1)
ETANOL = {'nome': 'Etanol (ficticio)', 'tipo': 'carro', 'combustivel': 'etanol', 'autonomia_km_l': 8, 'status': 'SIMULADO',
          'combustivel_valor_mensal': 400, 'preco_medio_combustivel': 4}


def dados(veiculo, **extra):
    return {'veiculo_id': veiculo, 'data_abastecimento': ONTEM.isoformat(), 'hodometro_km': 10000, 'combustivel': 'gasolina',
            'preco_litro': 4.40, 'valor_total': 176, **extra}


def abastecer(dsn, veiculo, **extra):
    return rpc(dsn, 'registrar_abastecimento', PESSOAL, dados(veiculo, **extra), chave())['abastecimento']


def historico(dsn, veiculo):
    return rpc(dsn, 'abastecimentos_veiculo_tela', PESSOAL, veiculo)


def mensagem(e):
    return e.diag.message_primary


def compra(dsn, cartao=CARTAO, valor='176.00', dia=None, descricao='POSTO FICTICIO', cartao_vinculado=None):
    dia = dia or ONTEM
    r = sql(dsn, 'insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, categoria_id, descricao, valor, data_compra, mes_fatura, '
                 'numero_parcela, total_parcelas, is_importado, cartao_vinculado_id) values (%s, %s, %s, %s, %s, %s, %s, 1, 1, true, %s) returning id',
            (PESSOAL, cartao, MORADIA, descricao, valor, dia, dia.replace(day=1), cartao_vinculado))
    return r[0]['id']


def cartao_fisico(dsn, final, contrato=CARTAO):
    return rpc(dsn, 'salvar_cartao_vinculado', PESSOAL, contrato, None, {'nome': f'Cartao {final}', 'final': final, 'tipo': 'FISICO'}, None)['id']


def assinatura(dsn, valor=900):
    return rpc(dsn, 'criar_assinatura_mobilidade', PESSOAL, {'nome': 'Assinatura (ficticia)', 'valor_mensal': valor}, chave())['assinatura_id']


def trocar(dsn, tipo, origem, decisoes=None, **extra):
    corpo = {'tipo_modalidade': tipo, 'origem_id': origem, 'confirmado': True, **extra}
    if decisoes is not None:
        corpo['decisoes'] = decisoes
    return rpc(dsn, 'ativar_mobilidade', PESSOAL, corpo, chave())


def conflitos(dsn, tipo, origem):
    return rpc(dsn, 'previa_mobilidade', PESSOAL, {'tipo_modalidade': tipo, 'origem_id': origem}).get('conflitos')


def decidir(lista, decisao):
    return [{'natureza': c['natureza'], 'id': c['registro_id'], 'decisao': decisao} for c in lista]


# =====================================================================================================================
# Cadastro
# =====================================================================================================================

def test_veiculo_unico_com_litros_calculados_sem_despesa(banco):
    v = criar(banco, SIMULADO)
    base = dados_financeiros(banco)
    a = abastecer(banco, v, estabelecimento='  Posto Ficticio ', observacoes='Viagem')
    assert Decimal(str(a['litros'])) == Decimal('40') and a['situacao_vinculo'] == 'AGUARDANDO'
    assert a['estabelecimento'] == 'Posto Ficticio' and a['meio_pagamento'] is None
    # Registrar e operacional: nenhuma conta, compra, movimento ou saldo muda; nem o cenario.
    assert dados_financeiros(banco) == base
    assert sql(banco, 'select count(*) n from public.mobilidade_cenario_ativo')[0]['n'] == 0


def test_litros_guardam_a_precisao_para_auditoria(banco):
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v, preco_litro=5.899, valor_total=150.33)
    guardado = sql(banco, 'select litros, preco_litro, valor_total from financeiro.abastecimento where id = %s', (a['id'],))[0]
    assert abs(guardado['litros'] - guardado['valor_total'] / guardado['preco_litro']) < Decimal('0.0000000001')
    assert guardado['litros'] != round(guardado['litros'], 3)  # so a tela mostra tres casas


@pytest.mark.parametrize('campo,valor,texto', [('preco_litro', 0, 'preço por litro'), ('preco_litro', -1, 'preço por litro'),
                                               ('valor_total', 0, 'valor abastecido'), ('valor_total', None, 'valor abastecido'),
                                               ('hodometro_km', None, 'hodômetro'), ('combustivel', '', 'combustível'),
                                               ('data_abastecimento', None, 'data')])
def test_valida_os_campos_obrigatorios(banco, campo, valor, texto):
    v = criar(banco, SIMULADO)
    e = erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(v, **{campo: valor}), chave())
    assert texto in mensagem(e)
    assert sql(banco, 'select count(*) n from financeiro.abastecimento')[0]['n'] == 0


def test_veiculo_obrigatorio_mesmo_com_um_so_e_data_futura_recusada(banco):
    v = criar(banco, SIMULADO)
    assert 'Selecione o veículo' in mensagem(erro(rpc, banco, 'registrar_abastecimento', PESSOAL, {**dados(v), 'veiculo_id': None}, chave()))
    futura = (HOJE + dt.timedelta(days=1)).isoformat()
    assert 'futura' in mensagem(erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(v, data_abastecimento=futura), chave()))


def test_mesma_chave_e_mesmo_registro_nao_duplicam(banco):
    v = criar(banco, SIMULADO)
    k = chave()
    primeiro = rpc(banco, 'registrar_abastecimento', PESSOAL, dados(v), k)
    assert rpc(banco, 'registrar_abastecimento', PESSOAL, dados(v), k)['repetida'] is True
    e = erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(v), chave())
    assert e.diag.message_hint == 'ABASTECIMENTO_REPETIDO'
    assert len(historico(banco, v)['abastecimentos']) == 1 and primeiro['abastecimento']['id']


def test_outro_perfil_nao_alcanca_veiculo_nem_abastecimento(banco):
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v)
    assert sql(banco, "select has_table_privilege('authenticated', 'financeiro.abastecimento', 'select') p")[0]['p'] is False
    assert 'não encontrado' in mensagem(erro(rpc, banco, 'corrigir_abastecimento', PERFIL_B, a['id'], {'motivo': 'x', 'hodometro_km': 1}, usuario=USUARIO_B))
    assert 'não encontrado' in mensagem(erro(rpc, banco, 'abastecimentos_veiculo_tela', PERFIL_B, v, usuario=USUARIO_B))
    assert erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(v, hodometro_km=10500), chave(), usuario=USUARIO_B).pgcode == '42501'
    for funcao in ('mob_km_veiculo(public.veiculo, numeric)', 'mob_conflitos_troca(integer, text, integer, date)'):
        assert sql(banco, f"select has_function_privilege('authenticated', 'financeiro.{funcao}', 'execute') p")[0]['p'] is False


# =====================================================================================================================
# Flex e combustivel unico
# =====================================================================================================================

def test_flex_registra_o_combustivel_usado_e_ignora_mudanca_de_autonomia(banco):
    v = criar(banco, FLEX)
    a = abastecer(banco, v, combustivel='etanol', preco_litro=4, valor_total=100)
    assert a['combustivel'] == 'etanol' and Decimal(str(a['litros'])) == 25  # a referencia da projecao e gasolina
    assert 'incompatível' in mensagem(erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(v, combustivel='diesel'), chave()))
    antes = sql(banco, 'select litros, combustivel, preco_litro, valor_total, hodometro_km from financeiro.abastecimento')
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'autonomia_etanol_km_l': 5, 'autonomia_gasolina_km_l': 9, 'combustivel_referencia': 'etanol', 'preco_etanol': 9})
    assert sql(banco, 'select litros, combustivel, preco_litro, valor_total, hodometro_km from financeiro.abastecimento') == antes


def test_combustivel_unico_so_aceita_o_do_veiculo_e_eletrico_recusa(banco):
    v = criar(banco, ETANOL)
    assert abastecer(banco, v, combustivel='etanol')['combustivel'] == 'etanol'
    assert 'incompatível' in mensagem(erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(v, combustivel='gasolina', hodometro_km=10100), chave()))
    maiuscula = criar(banco, {**ETANOL, 'combustivel': 'Gasolina', 'nome': 'Cadastro antigo (ficticio)'})  # cadastros antigos
    assert abastecer(banco, maiuscula)['combustivel'] == 'gasolina'
    assert 'incompatível' in mensagem(erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(maiuscula, combustivel='etanol', hodometro_km=10100), chave()))
    eletrico = criar(banco, {**ETANOL, 'combustivel': 'eletrico', 'nome': 'Eletrico (ficticio)'})
    assert 'elétrico' in mensagem(erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(eletrico), chave()))


# =====================================================================================================================
# Hodometro
# =====================================================================================================================

def test_historico_independente_por_veiculo(banco):
    a, b = criar(banco, SIMULADO), criar(banco, {**VEICULO_2, 'nome': 'Segundo (ficticio)'})
    abastecer(banco, a, hodometro_km=50000)
    abastecer(banco, b, hodometro_km=1000)  # mesma data e leitura bem menor: outro veiculo, sem conflito
    assert [x['hodometro_km'] for x in historico(banco, a)['abastecimentos']] == [50000.0]
    assert [x['hodometro_km'] for x in historico(banco, b)['abastecimentos']] == [1000.0]
    assert sql(banco, 'select count(*) n from public.mobilidade_cenario_ativo')[0]['n'] == 0


def test_sequencia_cronologica_recusa_regressao(banco):
    v = criar(banco, SIMULADO)
    d = [(HOJE - dt.timedelta(days=n)).isoformat() for n in (30, 20, 10)]
    abastecer(banco, v, data_abastecimento=d[0], hodometro_km=10000, valor_total=100)
    abastecer(banco, v, data_abastecimento=d[2], hodometro_km=11000, valor_total=110)
    e = erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(v, data_abastecimento=HOJE.isoformat(), hodometro_km=10999), chave())
    assert e.diag.message_hint == 'HODOMETRO_REGRESSAO' and 'menor' in mensagem(e)
    # Entre duas leituras, data retroativa: precisa caber entre elas.
    e = erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(v, data_abastecimento=d[1], hodometro_km=11500), chave())
    assert e.diag.message_hint == 'HODOMETRO_REGRESSAO' and 'maior' in mensagem(e)
    r = abastecer(banco, v, data_abastecimento=d[1], hodometro_km=10500)
    linhas = historico(banco, v)['abastecimentos']
    assert [x['id'] for x in linhas][1] == r['id'] and [x['km_rodados'] for x in linhas] == [500.0, 500.0, None]


def test_no_mesmo_dia_vale_a_ordem_de_registro(banco):
    v = criar(banco, SIMULADO)
    primeiro = abastecer(banco, v, hodometro_km=10000)
    segundo = abastecer(banco, v, hodometro_km=10300, valor_total=90)
    assert erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(v, hodometro_km=10200, valor_total=50), chave()).diag.message_hint == 'HODOMETRO_REGRESSAO'
    assert erro(rpc, banco, 'corrigir_abastecimento', PESSOAL, primeiro['id'], {'hodometro_km': 10400, 'motivo': 'x'}).diag.message_hint == 'HODOMETRO_REGRESSAO'
    assert rpc(banco, 'corrigir_abastecimento', PESSOAL, segundo['id'], {'hodometro_km': 10250, 'motivo': 'x'})['abastecimento']['hodometro_km'] == 10250.0


def test_corrigir_leitura_com_motivo_preserva_rastro_e_nao_toca_em_despesa(banco):
    v = criar(banco, SIMULADO)
    errado = abastecer(banco, v, data_abastecimento=(HOJE - dt.timedelta(days=9)).isoformat(), hodometro_km=100000)
    assert erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(v, hodometro_km=10200), chave()).diag.message_hint == 'HODOMETRO_REGRESSAO'
    base = dados_financeiros(banco)
    assert 'motivo' in mensagem(erro(rpc, banco, 'corrigir_abastecimento', PESSOAL, errado['id'], {'hodometro_km': 10000}))
    corrigido = rpc(banco, 'corrigir_abastecimento', PESSOAL, errado['id'], {'hodometro_km': 10000, 'motivo': 'Digitei um zero a mais'})['abastecimento']
    assert corrigido['hodometro_km'] == 10000.0 and corrigido['corrigido'] is True
    rastro = sql(banco, 'select acao, motivo, antes, depois from financeiro.abastecimento_historico where abastecimento_id = %s', (errado['id'],))
    assert len(rastro) == 1 and rastro[0]['acao'] == 'CORRECAO' and rastro[0]['motivo'] == 'Digitei um zero a mais'
    assert Decimal(str(rastro[0]['antes']['hodometro_km'])) == 100000 and Decimal(str(rastro[0]['depois']['hodometro_km'])) == 10000
    assert dados_financeiros(banco) == base
    abastecer(banco, v, hodometro_km=10200)  # a sequencia voltou a aceitar
    # A correcao tambem respeita a sequencia.
    e = erro(rpc, banco, 'corrigir_abastecimento', PESSOAL, corrigido['id'], {'hodometro_km': 20000, 'motivo': 'Teste'})
    assert e.diag.message_hint == 'HODOMETRO_REGRESSAO'


def test_anular_preserva_o_registro_e_sai_da_quilometragem(banco):
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v, hodometro_km=90000)
    assert 'motivo' in mensagem(erro(rpc, banco, 'anular_abastecimento', PESSOAL, a['id'], {}))
    rpc(banco, 'anular_abastecimento', PESSOAL, a['id'], {'motivo': 'Veiculo errado'})
    assert historico(banco, v)['quilometragem']['km_real'] is None
    linhas = historico(banco, v)['abastecimentos']
    assert len(linhas) == 1 and linhas[0]['anulado'] is True and linhas[0]['km_rodados'] is None
    abastecer(banco, v, hodometro_km=100)  # a leitura anulada nao trava a sequencia
    assert 'anulado' in mensagem(erro(rpc, banco, 'corrigir_abastecimento', PESSOAL, a['id'], {'hodometro_km': 1, 'motivo': 'x'}))


def test_veiculo_com_abastecimento_nao_e_excluido(banco):
    v = criar(banco, SIMULADO)
    abastecer(banco, v)
    e = erro(rpc, banco, 'excluir_veiculo', PESSOAL, v)
    assert e.diag.message_hint == 'COM_HISTORICO' and 'abastecimentos' in mensagem(e)


# =====================================================================================================================
# Quilometragem real e estimada, manutencao
# =====================================================================================================================

def test_leitura_real_nao_soma_de_novo_o_acumulado_das_confirmacoes(banco):
    v = criar(banco, {**ATIVO, 'preco_medio_combustivel': 5})
    p = previstas(banco, v)[0]
    rpc(banco, 'confirmar_despesa_prevista', PESSOAL, p['id'], {})
    acumulado = sql(banco, 'select km_estimado_acumulado k from public.veiculo where id = %s', (v,))[0]['k']
    assert acumulado == Decimal('1200.00')  # 200 / 5 x 30
    abastecer(banco, v, data_abastecimento=HOJE.isoformat(), hodometro_km=50000)
    km = historico(banco, v)['quilometragem']
    assert km['km_real'] == 50000.0 and km['km_estimado'] == 0 and km['km_atual'] == 50000.0  # nao e 51.200
    # A confirmacao nao e necessaria para atualizar o hodometro; o acumulado segue so como estimativa antiga.
    assert sql(banco, 'select km_estimado_acumulado k from public.veiculo where id = %s', (v,))[0]['k'] == acumulado


def test_estimativa_so_completa_os_dias_depois_da_leitura(banco):
    v = criar(banco, {**SIMULADO, 'km_mensal_estimado': 3043.75})
    abastecer(banco, v, data_abastecimento=(HOJE - dt.timedelta(days=10)).isoformat(), hodometro_km=20000)
    km = historico(banco, v)['quilometragem']
    assert km['fonte_km_mes'] == 'CADASTRO' and km['km_estimado'] == 1000 and km['km_atual'] == 21000


def test_media_vem_das_leituras_quando_ha_intervalo(banco):
    v = criar(banco, {**SIMULADO, 'km_mensal_estimado': 5000})
    abastecer(banco, v, data_abastecimento=(HOJE - dt.timedelta(days=61)).isoformat(), hodometro_km=10000)
    abastecer(banco, v, data_abastecimento=HOJE.isoformat(), hodometro_km=12000)
    km = historico(banco, v)['quilometragem']
    assert km['fonte_km_mes'] == 'LEITURAS' and km['leituras'] == 2
    assert abs(Decimal(str(km['km_mes'])) - Decimal('997.95')) < Decimal('0.01') and km['km_atual'] == 12000


def test_veiculo_coberto_pela_recorrencia_sem_leitura_continua_estimando(banco):
    """O defeito que parou a publicacao: com a recorrencia, confirmar deixa de existir e o km congelava."""
    v = criar(banco, {**ATIVO, 'preco_medio_combustivel': 5})
    ativar(banco, v)
    assert 'quilometragem' not in sql(banco, 'select financeiro.uso_do_veiculo(v, 3) u from public.veiculo v where v.id = %s', (v,))[0]['u']
    sql(banco, "update public.despesa_prevista set data_prevista = data_prevista - interval '2 months', data_original_prevista = data_original_prevista - interval '2 months', "
               "periodo_referencia = periodo_referencia - interval '2 months' where origem_id = %s and obrigacao = 'COMBUSTIVEL' and status = 'SUPRIMIDA' "
               'and data_prevista in (%s, %s)', (v, MES, PROXIMO))
    uso = sql(banco, 'select financeiro.uso_do_veiculo(v, 3) u from public.veiculo v where v.id = %s', (v,))[0]['u']
    assert uso['quilometragem']['km_estimado'] == 2400  # duas competencias encerradas x 1.200 km
    assert uso['quilometragem']['km_atual'] == 2400


def test_manutencao_por_km_usa_a_leitura_real(banco):
    v = criar(banco, {**SIMULADO, 'km_mensal_estimado': 1000})
    regra = rpc(banco, 'criar_regra_km_veiculo', PESSOAL, v, REGRA, chave())['regra_id']
    abastecer(banco, v, data_abastecimento=HOJE.isoformat(), hodometro_km=52000)  # intervalo de 5.000 km: faltam 3.000
    tela = rpc(banco, 'veiculo_manutencoes_km_tela', PESSOAL, v, 3)
    item = tela['estimativas'][0]
    assert tela['km_real'] == 52000.0 and item['km_atual_estimado'] == 52000.0 and item['km_restante'] == 3000 and item['meses_estimados'] == 3
    gerada = rpc(banco, 'gerar_manutencao_km_veiculo', PESSOAL, v, {'regra_id': regra})
    assert gerada['gerada'] is True
    assert gerada['data']['data_prevista'][:7] == (MES + relativedelta(months=3)).strftime('%Y-%m')


def test_manutencao_avanca_com_veiculo_coberto_pela_recorrencia(banco):
    v = criar(banco, {**ATIVO, 'preco_medio_combustivel': 5})
    ativar(banco, v)
    rpc(banco, 'criar_regra_km_veiculo', PESSOAL, v, REGRA, chave())
    primeiro = rpc(banco, 'veiculo_manutencoes_km_tela', PESSOAL, v, 3)['estimativas'][0]['km_restante']
    abastecer(banco, v, data_abastecimento=HOJE.isoformat(), hodometro_km=4800)
    assert primeiro == 5000 and rpc(banco, 'veiculo_manutencoes_km_tela', PESSOAL, v, 3)['estimativas'][0]['km_restante'] == 200


# =====================================================================================================================
# Varios veiculos
# =====================================================================================================================

def test_veiculos_na_mesma_competencia_sem_cenario_ativo(banco):
    a, b = criar(banco, {**VEICULO_2, 'nome': 'A (ficticio)'}), criar(banco, {**SIMULADO, 'nome': 'B (ficticio)'})
    base = dados_financeiros(banco)
    abastecer(banco, a, hodometro_km=100)
    abastecer(banco, b, hodometro_km=200, valor_total=88)
    assert dados_financeiros(banco) == base and sql(banco, 'select count(*) n from public.mobilidade_cenario_ativo')[0]['n'] == 0


def test_um_cenario_ativo_por_perfil_e_garantido_pelo_banco(banco):
    a, b = criar(banco, ATIVO), criar(banco, {**ATIVO, 'nome': 'B (ficticio)'})
    ativar(banco, a)
    with pytest.raises(psycopg2.errors.UniqueViolation):
        sql(banco, "insert into public.mobilidade_cenario_ativo (perfil_financeiro_id, tipo_modalidade, origem_id, ativo_desde, status) "
                   "values (%s, 'VEICULO', %s, %s, 'ATIVO')", (PESSOAL, b, MES))


def test_segundo_veiculo_em_uso_continua_contando_e_o_que_saiu_do_cenario_nao(banco):
    a = criar(banco, {**ATIVO, 'nome': 'Sai do cenario (ficticio)', 'combustivel_valor_mensal': 200})
    b = criar(banco, {**ATIVO, 'nome': 'Sempre em uso (ficticio)', 'combustivel_valor_mensal': 50})
    c = criar(banco, {**ATIVO, 'nome': 'Entra no cenario (ficticio)', 'combustivel_valor_mensal': 70})
    saidas_antes = despesas_do_mes(banco)[0]
    ativar(banco, a)
    trocar(banco, 'VEICULO', c, meio_pagamento='pix')
    saidas = despesas_do_mes(banco)[0]
    # c e a recorrencia ainda sem conta gerada; b (nunca foi o cenario) conta; a saiu do cenario e nao conta mais.
    assert saidas == saidas_antes - 200 - 70
    assert {p['status'] for p in previstas(banco, a) if p['data_prevista'] >= DEPOIS} == {'PREVISTA'}  # continua na tela de Mobilidade
    trocar(banco, 'VEICULO', a, meio_pagamento='pix')  # voltar ao cenario: a volta a ser a recorrencia, sem duplicar
    assert {p['status'] for p in previstas(banco, a)} == {'SUPRIMIDA'}


def test_caminho_de_app_fora_do_cenario_nao_conta(banco):
    base = despesas_do_mes(banco)
    caminho = rpc(banco, 'criar_caminho_app', PESSOAL, {'nome': 'App (ficticio)', 'km_mensal_estimado': 300, 'preco_medio_por_km': 2.5, 'meses_futuros': 3}, chave())['id']
    assert sql(banco, "select count(*) n from public.despesa_prevista where origem_tipo = 'TRANSPORTE_APP'")[0]['n'] == 3
    assert despesas_do_mes(banco) == base and saidas_previstas(banco) == []  # simulacao fora do financeiro real
    trocar(banco, 'TRANSPORTE_APP', caminho)  # cenario ativo sem recorrencia: a previsao passa a contar
    assert despesas_do_mes(banco) == (base[0] + 750, base[1] + 750)


# =====================================================================================================================
# Cartoes fisicos e vinculo com a despesa
# =====================================================================================================================

def test_cartao_fisico_precisa_ser_do_contrato_e_so_o_final_e_guardado(banco):
    v = criar(banco, SIMULADO)
    fisico = cartao_fisico(banco, '1234')
    a = abastecer(banco, v, cartao_id=CARTAO, cartao_vinculado_id=fisico)
    assert a['meio_pagamento'] == 'cartao' and a['cartao_final'] == '1234' and a['cartao_vinculado_id'] == fisico
    colunas = {c['column_name'] for c in sql(banco, "select column_name from information_schema.columns where table_schema = 'financeiro' and table_name = 'abastecimento'")}
    assert not colunas & {'cvv', 'numero', 'numero_cartao'}
    e = erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(v, cartao_vinculado_id=fisico, hodometro_km=10010), chave())
    assert 'físico' in mensagem(e)
    e = erro(rpc, banco, 'registrar_abastecimento', PESSOAL, dados(v, meio_pagamento='pix', cartao_id=CARTAO, hodometro_km=10010), chave())
    assert 'outro meio' in mensagem(e)


def test_abastecimentos_de_veiculos_diferentes_na_mesma_fatura(banco):
    a, b = criar(banco, {**VEICULO_2, 'nome': 'A (ficticio)'}), criar(banco, {**SIMULADO, 'nome': 'B (ficticio)'})
    f1, f2 = cartao_fisico(banco, '1111'), cartao_fisico(banco, '2222')
    x = abastecer(banco, a, cartao_id=CARTAO, cartao_vinculado_id=f1, hodometro_km=100)
    y = abastecer(banco, b, cartao_id=CARTAO, cartao_vinculado_id=f2, hodometro_km=200)
    c1, c2 = compra(banco, cartao_vinculado=f1), compra(banco, cartao_vinculado=f2)
    # O cartao fisico distingue as duas compras de mesmo valor.
    assert [c['id'] for c in rpc(banco, 'candidatas_abastecimento', PESSOAL, x['id'])['candidatas']] == [c1]
    assert [c['id'] for c in rpc(banco, 'candidatas_abastecimento', PESSOAL, y['id'])['candidatas']] == [c2]
    assert rpc(banco, 'vincular_abastecimento', PESSOAL, x['id'], {'lancamento_id': c1})['abastecimento']['situacao_vinculo'] == 'VINCULADO'
    rpc(banco, 'vincular_abastecimento', PESSOAL, y['id'], {'lancamento_id': c2})
    vinculos = sql(banco, 'select veiculo_id, lancamento_id from financeiro.abastecimento order by id')
    assert [(l['veiculo_id'], l['lancamento_id']) for l in vinculos] == [(a, c1), (b, c2)]


def test_sem_cartao_fisico_e_ambiguo_e_nada_e_vinculado_sozinho(banco):
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v, cartao_id=CARTAO)
    compra(banco)
    compra(banco, dia=ONTEM + dt.timedelta(days=1))
    r = rpc(banco, 'candidatas_abastecimento', PESSOAL, a['id'])
    assert len(r['candidatas']) == 2 and r['ambigua'] is True
    assert sql(banco, 'select lancamento_id, conta_id from financeiro.abastecimento') == [{'lancamento_id': None, 'conta_id': None}]


def test_vincular_nao_cria_nem_altera_compra_e_preserva_a_importada(banco):
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v, cartao_id=CARTAO)
    c = compra(banco)
    consulta = 'select * from public.lancamento_agregado order by id'
    antes = sql(banco, consulta)
    r = rpc(banco, 'vincular_abastecimento', PESSOAL, a['id'], {'lancamento_id': c})['abastecimento']
    assert r['lancamento_id'] == c and sql(banco, consulta) == antes
    # Corrigir o hodometro nao mexe no vinculo nem na compra; valor e veiculo exigem desvincular.
    rpc(banco, 'corrigir_abastecimento', PESSOAL, a['id'], {'hodometro_km': 10001, 'motivo': 'Ajuste'})
    assert sql(banco, consulta) == antes
    assert erro(rpc, banco, 'corrigir_abastecimento', PESSOAL, a['id'], {'valor_total': 170, 'motivo': 'x'}).diag.message_hint == 'ABASTECIMENTO_VINCULADO'
    assert erro(rpc, banco, 'anular_abastecimento', PESSOAL, a['id'], {'motivo': 'x'}).diag.message_hint == 'ABASTECIMENTO_VINCULADO'
    # Excluir a compra (limpeza de importacao) so limpa o vinculo: o abastecimento continua, aguardando.
    sql(banco, 'delete from public.lancamento_agregado where id = %s', (c,))
    assert historico(banco, v)['abastecimentos'][0]['situacao_vinculo'] == 'AGUARDANDO'


def test_vinculo_recusa_divergencia_e_compra_ja_usada(banco):
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v, cartao_id=CARTAO, hodometro_km=100)
    b = abastecer(banco, v, cartao_id=CARTAO, hodometro_km=200, valor_total=177)
    certa, valor_outro = compra(banco), compra(banco, valor='10.00')
    assert erro(rpc, banco, 'vincular_abastecimento', PESSOAL, a['id'], {'lancamento_id': valor_outro}).diag.message_hint == 'VALOR_DIVERGENTE'
    rpc(banco, 'vincular_abastecimento', PESSOAL, a['id'], {'lancamento_id': certa})
    assert erro(rpc, banco, 'vincular_abastecimento', PESSOAL, a['id'], {'lancamento_id': certa}).diag.message_hint == 'ABASTECIMENTO_VINCULADO'
    sql(banco, 'update public.lancamento_agregado set valor = 177 where id = %s', (certa,))
    assert erro(rpc, banco, 'vincular_abastecimento', PESSOAL, b['id'], {'lancamento_id': certa}).diag.message_hint == 'DESPESA_JA_VINCULADA'
    sql(banco, 'update public.lancamento_agregado set valor = 176 where id = %s', (certa,))
    rpc(banco, 'desvincular_abastecimento', PESSOAL, a['id'])
    assert [r['acao'] for r in sql(banco, 'select acao from financeiro.abastecimento_historico where abastecimento_id = %s order by id', (a['id'],))] == ['VINCULO', 'DESVINCULO']
    fisico_a, fisico_b = cartao_fisico(banco, '3333'), cartao_fisico(banco, '4444')
    rpc(banco, 'corrigir_abastecimento', PESSOAL, a['id'], {'cartao_vinculado_id': fisico_a, 'motivo': 'Cartao certo'})
    outra = compra(banco, cartao_vinculado=fisico_b)
    assert erro(rpc, banco, 'vincular_abastecimento', PESSOAL, a['id'], {'lancamento_id': outra}).diag.message_hint == 'CARTAO_DIVERGENTE'


def test_pagamento_por_pix_vincula_com_a_conta(banco):
    v = criar(banco, ATIVO)
    a = abastecer(banco, v, meio_pagamento='pix', combustivel='gasolina', valor_total=200, preco_litro=5, data_abastecimento=MES.isoformat())
    conta = rpc(banco, 'confirmar_despesa_prevista', PESSOAL, previstas(banco, v)[0]['id'], {'meio_pagamento': 'pix', 'data_vencimento': MES.isoformat()})['entidade_criada']['id']
    linhas = rpc(banco, 'candidatas_abastecimento', PESSOAL, a['id'])['candidatas']
    assert [(c['natureza'], c['id']) for c in linhas] == [('CONTA', conta)]
    base = dados_financeiros(banco)
    assert rpc(banco, 'vincular_abastecimento', PESSOAL, a['id'], {'conta_id': conta})['abastecimento']['conta_id'] == conta
    assert dados_financeiros(banco) == base


# =====================================================================================================================
# Troca de modalidade
# =====================================================================================================================

def preparar_troca(dsn):
    v = criar(dsn, ATIVO)
    item = ativar(dsn, v)['recorrencia']['id']
    gerar_confirmado(dsn, mes=DEPOIS.isoformat())  # contas de MES, PROXIMO, DEPOIS e do mes seguinte
    return v, item, contas_item(dsn, item)


def test_previa_mostra_as_futuras_e_o_mes_corrente_nao_muda(banco):
    v, item, contas = preparar_troca(banco)
    ass = assinatura(banco)
    c = conflitos(banco, 'ASSINATURA', ass)
    assert [x['registro_id'] for x in c['decidir']] == [x['id'] for x in contas[1:]]
    assert [x['registro_id'] for x in c['sem_alteracao']] == [contas[0]['id']]
    assert c['decidir'][0]['modalidade_tipo'] == 'VEICULO' and c['decidir'][0]['modalidade_origem_id'] == v
    # Sem conflito a previa continua igual: reativar o proprio veiculo nao pergunta nada.
    assert conflitos(banco, 'VEICULO', v) is None


def test_troca_nao_conclui_com_conflito_sem_decisao(banco):
    v, item, contas = preparar_troca(banco)
    ass = assinatura(banco)
    base, cenarios = dados_financeiros(banco), sql(banco, 'select * from public.mobilidade_cenario_ativo order by id')
    e = erro(trocar, banco, 'ASSINATURA', ass)
    assert e.diag.message_hint == 'CONFLITOS_PENDENTES'
    parcial = decidir(conflitos(banco, 'ASSINATURA', ass)['decidir'], 'SUBSTITUIR')[:-1]
    assert erro(trocar, banco, 'ASSINATURA', ass, parcial).diag.message_hint == 'CONFLITOS_PENDENTES'
    assert erro(trocar, banco, 'ASSINATURA', ass, parcial + [{'natureza': 'CONTA', 'id': 999999, 'decisao': 'MANTER'}]).diag.message_hint in ('CONFLITOS_PENDENTES', 'PREVIA_DESATUALIZADA')
    tudo = decidir(conflitos(banco, 'ASSINATURA', ass)['decidir'], 'MANTER')
    e = erro(trocar, banco, 'ASSINATURA', ass, tudo + [{'natureza': 'CONTA', 'id': contas[0]['id'], 'decisao': 'SUBSTITUIR'}])
    assert e.diag.message_hint == 'PREVIA_DESATUALIZADA'  # o mes corrente nao pode ser substituido
    assert 'invalida' in mensagem(erro(trocar, banco, 'ASSINATURA', ass, [dict(tudo[0], decisao='APAGAR')] + tudo[1:]))
    assert dados_financeiros(banco) == base and sql(banco, 'select * from public.mobilidade_cenario_ativo order by id') == cenarios
    assert sql(banco, 'select count(*) n from financeiro.mobilidade_troca_decisao')[0]['n'] == 0


def test_escolha_individual_substituida_fora_dos_indicadores_e_preservada(banco):
    v, item, contas = preparar_troca(banco)
    ass = assinatura(banco)
    lista = conflitos(banco, 'ASSINATURA', ass)['decidir']
    mantida, substituida, *resto = lista
    decisoes = decidir([mantida], 'MANTER') + decidir([substituida], 'SUBSTITUIR') + decidir(resto, 'SUBSTITUIR')
    antes_mes = dashboard(banco, DEPOIS)['fluxo_caixa']['resumo']['despesas_previstas']
    r = trocar(banco, 'ASSINATURA', ass, decisoes)
    assert r['troca'] == {'substituidas': 2, 'mantidas': 1}
    # Preservada, com a decisao registrada e a foto de antes.
    linha = sql(banco, 'select valor, status_pagamento from public.conta where id = %s', (substituida['registro_id'],))[0]
    assert linha == {'valor': Decimal('200.00'), 'status_pagamento': 'Substituida'}
    reg = sql(banco, 'select decisao, valor, registro_antes, user_id from financeiro.mobilidade_troca_decisao where conta_id = %s', (substituida['registro_id'],))[0]
    assert reg['decisao'] == 'SUBSTITUIR' and reg['registro_antes']['status_pagamento'] == 'Pendente' and reg['user_id']
    # Fora das despesas do mes, do Dashboard e das saidas; mantida e mes corrente seguem.
    depois_mes = dashboard(banco, DEPOIS)['fluxo_caixa']['resumo']['despesas_previstas']
    assert Decimal(str(antes_mes)) - Decimal(str(depois_mes)) == 200
    do_mes = chamar(banco, USUARIO_A, "select coalesce(jsonb_agg(c.id), '[]') from financeiro.contas_do_mes(%s, %s) c", (PESSOAL, substituida['competencia']))
    assert substituida['registro_id'] not in do_mes
    saidas = sql(banco, 'select financeiro.saidas_lastro(%s, %s::jsonb) r', (PESSOAL, json.dumps({'ano': DEPOIS.year, 'mes': DEPOIS.month})))[0]['r']
    assert substituida['registro_id'] not in [s['entidade_id'] for s in saidas or [] if s['tipo_entidade'] == 'CONTA']
    assert sql(banco, 'select status_pagamento from public.conta where id = %s', (mantida['registro_id'],)) == [{'status_pagamento': 'Pendente'}]
    assert sql(banco, 'select status_pagamento from public.conta where id = %s', (contas[0]['id'],)) == [{'status_pagamento': 'Pendente'}]
    lista_tela = [c['id'] for c in rpc(banco, 'despesas_diretas_tela', PESSOAL)]
    assert substituida['registro_id'] not in lista_tela and mantida['registro_id'] in lista_tela


def test_substituida_nao_pode_ser_paga_nem_editada(banco):
    v, item, contas = preparar_troca(banco)
    ass = assinatura(banco)
    alvo = conflitos(banco, 'ASSINATURA', ass)['decidir']
    trocar(banco, 'ASSINATURA', ass, decidir(alvo, 'SUBSTITUIR'))
    bid = conta_bancaria(banco)
    with pytest.raises(psycopg2.Error) as e:
        pagar(banco, alvo[0]['registro_id'], bid)
    assert 'substituida' in str(e.value)


def test_pagas_e_com_movimento_ficam_fora_da_troca(banco):
    v, item, contas = preparar_troca(banco)
    bid = conta_bancaria(banco)
    pagar(banco, contas[1]['id'], bid)
    ass = assinatura(banco)
    c = conflitos(banco, 'ASSINATURA', ass)
    assert contas[1]['id'] not in [x['registro_id'] for x in c['decidir']]
    movimentos = sql(banco, 'select id, valor from public.movimento_financeiro where conta_id = %s', (contas[1]['id'],))
    saldo = sql(banco, 'select saldo_atual from public.conta_bancaria where id = %s', (bid,))
    trocar(banco, 'ASSINATURA', ass, decidir(c['decidir'], 'SUBSTITUIR'))
    assert sql(banco, 'select status_pagamento from public.conta where id = %s', (contas[1]['id'],)) == [{'status_pagamento': 'Pago'}]
    assert sql(banco, 'select id, valor from public.movimento_financeiro where conta_id = %s', (contas[1]['id'],)) == movimentos
    assert sql(banco, 'select saldo_atual from public.conta_bancaria where id = %s', (bid,)) == saldo


def test_compra_prevista_no_cartao_substituida_sai_da_fatura_e_fica_preservada(banco):
    v = criar(banco, ATIVO)
    item = ativar(banco, v, meio='cartao', cartao_id=CARTAO)['recorrencia']['id']
    gerar_confirmado(banco, mes=PROXIMO.isoformat())
    compras = sql(banco, 'select id, mes_fatura from public.lancamento_agregado where item_despesa_id = %s order by mes_fatura', (item,))
    futura = compras[1]
    assert rpc(banco, 'fatura_por_categoria', PESSOAL, CARTAO, futura['mes_fatura'])['total_previsto_pendente'] == 200
    ass = assinatura(banco)
    c = conflitos(banco, 'ASSINATURA', ass)
    assert [x['natureza'] for x in c['decidir']] == ['COMPRA'] * (len(compras) - 1) and c['sem_alteracao'][0]['registro_id'] == compras[0]['id']
    r = trocar(banco, 'ASSINATURA', ass, decidir(c['decidir'], 'SUBSTITUIR'))
    assert r['troca']['substituidas'] == len(compras) - 1
    assert sql(banco, 'select valor from public.lancamento_agregado where id = %s', (futura['id'],)) == [{'valor': Decimal('200.00')}]
    fatura = rpc(banco, 'fatura_por_categoria', PESSOAL, CARTAO, futura['mes_fatura'])
    assert fatura['total_previsto_pendente'] == 0 and fatura['total_fatura'] == 0


def test_alternar_modalidades_nao_duplica_e_nao_repete_a_decisao(banco):
    v, item, contas = preparar_troca(banco)
    ass = assinatura(banco)
    trocar(banco, 'ASSINATURA', ass, decidir(conflitos(banco, 'ASSINATURA', ass)['decidir'], 'SUBSTITUIR'), meio_pagamento='pix')
    item_ass = sql(banco, "select id from public.item_despesa where origem_tipo = 'ASSINATURA' and origem_id = %s", (ass,))[0]['id']
    gerar_confirmado(banco, mes=DEPOIS.isoformat())
    futuras_b = [c for c in contas_item(banco, item_ass) if c['mes_referencia'].replace(day=1) > MES]
    assert futuras_b
    # Volta ao veiculo: so a assinatura tem futuras a decidir; as do veiculo ja decididas nao voltam a perguntar.
    lista = conflitos(banco, 'VEICULO', v)['decidir']
    assert {x['modalidade_tipo'] for x in lista} == {'ASSINATURA'} and [x['registro_id'] for x in lista] == [c['id'] for c in futuras_b]
    novo = trocar(banco, 'VEICULO', v, decidir(lista, 'SUBSTITUIR'), meio_pagamento='pix')
    gerar_confirmado(banco, mes=DEPOIS.isoformat())
    meses = {}
    for c in sql(banco, "select c.mes_referencia, c.valor from public.conta c join public.item_despesa i on i.id = c.item_despesa_id "
                        "where i.origem_tipo in ('VEICULO', 'ASSINATURA') and c.status_pagamento = 'Pendente' and c.mes_referencia >= %s", (PROXIMO,)):
        mes = c['mes_referencia'].replace(day=1)
        meses[mes] = meses.get(mes, 0) + 1
    assert set(meses.values()) == {1}  # uma despesa viva por competencia, depois de A -> B -> A
    assert sql(banco, 'select count(*) n from financeiro.mobilidade_troca_decisao')[0]['n'] == len(contas[1:]) + len(futuras_b)
    assert novo['recorrencia']['id'] != item


def test_repetir_a_ativacao_pela_chave_nao_reaplica(banco):
    v, item, contas = preparar_troca(banco)
    ass = assinatura(banco)
    corpo = {'tipo_modalidade': 'ASSINATURA', 'origem_id': ass, 'confirmado': True, 'decisoes': decidir(conflitos(banco, 'ASSINATURA', ass)['decidir'], 'SUBSTITUIR')}
    k = chave()
    rpc(banco, 'ativar_mobilidade', PESSOAL, corpo, k)
    assert rpc(banco, 'ativar_mobilidade', PESSOAL, corpo, k)['repetida'] is True
    assert sql(banco, "select count(*) n from public.mobilidade_cenario_ativo where status = 'ATIVO'")[0]['n'] == 1


def test_simulado_com_abastecimento_continua_fora_do_dashboard(banco):
    base = dashboard(banco)
    v = criar(banco, SIMULADO)
    abastecer(banco, v)
    assert dashboard(banco)['fluxo_caixa'] == base['fluxo_caixa'] and saidas_previstas(banco) == []
    assert sql(banco, 'select status from public.veiculo where id = %s', (v,)) == [{'status': 'SIMULADO'}]


# =====================================================================================================================
# Migration
# =====================================================================================================================

def test_reversao_recusa_abastecimento_e_decisao(banco):
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v)
    assert 'abastecimentos registrados' in str(erro(executar, banco, REVERSAO_1215))
    sql(banco, 'delete from financeiro.abastecimento_historico')
    sql(banco, 'delete from financeiro.abastecimento where id = %s', (a['id'],))
    w, item, contas = preparar_troca(banco)
    ass = assinatura(banco)
    trocar(banco, 'ASSINATURA', ass, decidir(conflitos(banco, 'ASSINATURA', ass)['decidir'], 'MANTER'))
    assert 'decisoes de troca' in str(erro(executar, banco, REVERSAO_1215))


def test_funcoes_de_tela_liberadas_so_para_quem_tem_login(banco):
    for assinatura_ in ('registrar_abastecimento(integer, jsonb, uuid)', 'abastecimentos_veiculo_tela(integer, integer)',
                        'candidatas_abastecimento(integer, integer)', 'vincular_abastecimento(integer, integer, jsonb)'):
        assert sql(banco, f"select has_function_privilege('anon', 'financeiro.{assinatura_}', 'execute') p")[0]['p'] is False
        assert sql(banco, f"select has_function_privilege('authenticated', 'financeiro.{assinatura_}', 'execute') p")[0]['p'] is True
