"""
Testes FIN-MOB-ABAST-LANCAMENTOS-01 — abastecimento no formulario de Novo Lancamento (migration 20261217090000), em cluster
PostgreSQL local descartavel e com dados ficticios.

Uma despesa (compra a vista no cartao ou despesa direta, nova ou ja lancada) e o seu registro operacional de abastecimento,
gravados e vinculados numa so transacao. O abastecimento nunca e outra despesa: fatura, saldos, recorrencias e Dashboard so
veem a despesa. Falha em qualquer parte nao grava nada; repetir com a mesma chave nao duplica.
"""
import datetime as dt
import uuid
from decimal import Decimal

import pytest

from tests.test_supabase_cartoes import CARTAO, MORADIA, SEM_CONFIG, rpc
from tests.test_supabase_mobilidade_abastecimento import (
    ONTEM,
    abastecer,
    cartao_fisico,
    compra,
    historico,
    mensagem,
)
from tests.test_supabase_mobilidade_escrita import (  # noqa: F401  (fixtures de modulo reaproveitadas)
    HOJE,
    PERFIL_B,
    PESSOAL,
    banco,
    chave,
    cluster,
)
from tests.test_supabase_mobilidade_integridade import ATIVO, FLEX, SIMULADO, criar, dados_financeiros, dashboard
from tests.test_supabase_recorrencia import PG_BIN, USUARIO_B, sql

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

MIGRATION = 'supabase/migrations/20261217090000_financeiro_abastecimento_lancamento.sql'


def combustivel(dsn):
    return rpc(dsn, 'formulario_abastecimento_lancamento', PESSOAL)['categoria_combustivel_id']


def compra_nova(dsn, valor='176.00', dia=None, cartao=CARTAO, **extra):
    dia = dia or ONTEM
    return {'tipo': 'compra', 'dados': {'cartao_id': cartao, 'descricao': 'POSTO FICTICIO', 'valor': valor, 'total_parcelas': 1,
                                        'data_compra': dia.isoformat(), 'mes_fatura': dia.replace(day=1).isoformat(),
                                        'categoria_id': combustivel(dsn), 'observacoes': '', **extra}}


def despesa_nova(dsn, valor='176.00', dia=None):
    dia = dia or ONTEM
    return {'tipo': 'despesa', 'dados': {'nome': 'Posto direto (ficticio)', 'valor': valor, 'descricao': '', 'categoria_id': combustivel(dsn),
                                         'data_vencimento': dia.isoformat(), 'debito_automatico': False, 'conta_bancaria_id': None}}


def operacional(veiculo, **extra):
    return {'veiculo_id': veiculo, 'combustivel': 'gasolina', 'hodometro_km': 10000, 'preco_litro': 4.40, **extra}


def salvar(dsn, lancamento, abastecimento, chave_=None, perfil=PESSOAL, usuario=None):
    extra = {'usuario': usuario} if usuario else {}
    return rpc(dsn, 'salvar_lancamento_abastecimento', perfil, {'lancamento': lancamento, 'abastecimento': abastecimento},
               chave_ or chave(), **extra)


def recusa(dsn, lancamento, abastecimento, **extra):
    with pytest.raises(psycopg2.Error) as e:
        salvar(dsn, lancamento, abastecimento, **extra)
    return mensagem(e.value)


def contagens(dsn):
    return sql(dsn, 'select (select count(*) from public.lancamento_agregado) compras, (select count(*) from public.conta) contas, '
                    '(select count(*) from financeiro.abastecimento) abastecimentos')[0]


def fatura(dsn, cartao=CARTAO, mes=None):
    mes = mes or ONTEM.replace(day=1)
    return sql(dsn, 'select coalesce(sum(valor), 0) t from public.lancamento_agregado where cartao_id = %s and mes_fatura = %s', (cartao, mes))[0]['t']


# =====================================================================================================================
# Formulario
# =====================================================================================================================

def test_formulario_identifica_combustivel_pelo_codigo_e_lista_os_veiculos_do_perfil(banco):
    a, b = criar(banco, SIMULADO), criar(banco, ATIVO)
    f = rpc(banco, 'formulario_abastecimento_lancamento', PESSOAL)
    codigo = sql(banco, 'select codigo_sistema c from public.categoria where id = %s', (f['categoria_combustivel_id'],))[0]['c']
    assert codigo == 'MOB_COMBUSTIVEL'
    assert sorted(v['id'] for v in f['veiculos']) == sorted([a, b])
    assert {v['id']: v['situacao_uso'] for v in f['veiculos']}[a] == 'SIMULADO'
    assert rpc(banco, 'formulario_abastecimento_lancamento', PERFIL_B, usuario=USUARIO_B)['veiculos'] == []


# =====================================================================================================================
# 7. Uma despesa, um abastecimento
# =====================================================================================================================

def test_compra_no_cartao_gera_um_abastecimento_vinculado_sem_outra_despesa(banco):
    v = criar(banco, SIMULADO)
    antes = contagens(banco)
    despesas = 'select count(*) n from public.conta where not coalesce(is_fatura_cartao, false)'
    despesas_antes = sql(banco, despesas)[0]['n']
    r = salvar(banco, compra_nova(banco), operacional(v))
    a = r['abastecimento']
    assert (a['situacao_vinculo'], a['lancamento_id'], a['conta_id']) == ('VINCULADO', r['lancamento_id'], None)
    assert (Decimal(str(a['valor_total'])), Decimal(str(a['litros'])), a['data_abastecimento'], a['cartao_id'], a['meio_pagamento']) == \
        (Decimal('176.00'), Decimal('40'), ONTEM.isoformat(), CARTAO, 'cartao')
    assert a['estabelecimento'] == 'POSTO FICTICIO'
    depois = contagens(banco)
    assert (depois['compras'] - antes['compras'], depois['abastecimentos'] - antes['abastecimentos']) == (1, 1)
    assert depois['contas'] - antes['contas'] in (0, 1)  # so a fatura do mes, se ainda nao existia
    assert sql(banco, despesas)[0]['n'] == despesas_antes  # nenhuma despesa a mais


def test_despesa_direta_gera_um_abastecimento_vinculado(banco):
    v = criar(banco, SIMULADO)
    antes = contagens(banco)
    r = salvar(banco, despesa_nova(banco), operacional(v, meio_pagamento='pix'))
    a = r['abastecimento']
    assert (a['conta_id'], a['lancamento_id'], a['meio_pagamento'], a['cartao_id']) == (r['conta_id'], None, 'pix', None)
    depois = contagens(banco)
    assert (depois['contas'] - antes['contas'], depois['compras'] - antes['compras'], depois['abastecimentos'] - antes['abastecimentos']) == (1, 0, 1)


# =====================================================================================================================
# 8, 9. Varios veiculos e cartoes fisicos
# =====================================================================================================================

def test_dois_veiculos_na_mesma_competencia_com_hodometros_independentes(banco):
    a, b = criar(banco, SIMULADO), criar(banco, FLEX)
    salvar(banco, compra_nova(banco), operacional(a, hodometro_km=50000))
    salvar(banco, compra_nova(banco, valor='150.00'), operacional(b, hodometro_km=1200, combustivel='etanol', preco_litro=3.75))
    assert [x['hodometro_km'] for x in historico(banco, a)['abastecimentos']] == [50000]
    assert [x['hodometro_km'] for x in historico(banco, b)['abastecimentos']] == [1200]


def test_dois_cartoes_fisicos_da_mesma_fatura_identificados_na_compra_e_no_abastecimento(banco):
    a, b = criar(banco, SIMULADO), criar(banco, FLEX)
    titular, adicional = cartao_fisico(banco, '1111'), cartao_fisico(banco, '2222')
    r1 = salvar(banco, compra_nova(banco), operacional(a, cartao_vinculado_id=titular))
    r2 = salvar(banco, compra_nova(banco, valor='150.00'), operacional(b, combustivel='etanol', preco_litro=3.75, cartao_vinculado_id=adicional))
    assert (r1['abastecimento']['cartao_final'], r2['abastecimento']['cartao_final']) == ('1111', '2222')
    fisicos = {x['id']: x['c'] for x in sql(banco, 'select id, cartao_vinculado_id c from public.lancamento_agregado where id in (%s, %s)',
                                             (r1['lancamento_id'], r2['lancamento_id']))}
    assert fisicos == {r1['lancamento_id']: titular, r2['lancamento_id']: adicional}
    assert fatura(banco) == Decimal('326.00')


def test_cartao_sem_cartao_fisico_cadastrado_nao_impede_o_lancamento(banco):
    v = criar(banco, SIMULADO)
    r = salvar(banco, compra_nova(banco), operacional(v))
    assert (r['abastecimento']['cartao_id'], r['abastecimento']['cartao_vinculado_id']) == (CARTAO, None)


def test_cartao_fisico_de_outro_contrato_e_recusado_sem_gravar(banco):
    v = criar(banco, SIMULADO)
    outro = cartao_fisico(banco, '3333', contrato=SEM_CONFIG)  # outro contrato do mesmo perfil
    antes = contagens(banco)
    assert 'não pertence ao cartão' in recusa(banco, compra_nova(banco), operacional(v, cartao_vinculado_id=outro))
    assert contagens(banco) == antes


# =====================================================================================================================
# 10, 11, 12. Validacoes, sem gravar nada
# =====================================================================================================================

def test_veiculo_de_outro_perfil_e_recusado(banco):
    alheio = rpc(banco, 'criar_veiculo', PERFIL_B, {'nome': 'Carro B', 'tipo': 'carro', 'combustivel': 'gasolina', 'status': 'SIMULADO',
                                                    'autonomia_km_l': 10}, chave(), usuario=USUARIO_B)['veiculo_id']
    antes = contagens(banco)
    with pytest.raises(psycopg2.Error):
        salvar(banco, compra_nova(banco), operacional(alheio))
    assert contagens(banco) == antes


def test_hodometro_regressivo_e_recusado_sem_criar_a_compra(banco):
    v = criar(banco, SIMULADO)
    salvar(banco, compra_nova(banco, dia=ONTEM - dt.timedelta(days=2)), operacional(v, hodometro_km=20000))
    antes = contagens(banco)
    assert 'odômetro' in recusa(banco, compra_nova(banco, valor='90.00'), operacional(v, hodometro_km=19000)).replace('hod', 'od')
    assert contagens(banco) == antes


@pytest.mark.parametrize('campo,valor,trecho', [('preco_litro', 0, 'preço por litro'), ('preco_litro', -1, 'preço por litro'),
                                               ('combustivel', 'diesel', 'incompatível'), ('veiculo_id', None, 'Selecione o veículo')])
def test_dados_operacionais_invalidos_recusados(banco, campo, valor, trecho):
    v = criar(banco, SIMULADO)
    antes = contagens(banco)
    assert trecho in recusa(banco, compra_nova(banco), operacional(v, **{campo: valor}))
    assert contagens(banco) == antes


def test_valor_invalido_da_compra_e_recusado(banco):
    v = criar(banco, SIMULADO)
    antes = contagens(banco)
    with pytest.raises(psycopg2.Error):
        salvar(banco, compra_nova(banco, valor='0'), operacional(v))
    assert contagens(banco) == antes


def test_compra_parcelada_nao_recebe_abastecimento(banco):
    v = criar(banco, SIMULADO)
    lanc = compra_nova(banco)
    lanc['dados']['total_parcelas'] = 2
    antes = contagens(banco)
    assert 'à vista' in recusa(banco, lanc, operacional(v))
    assert contagens(banco) == antes


def test_data_futura_recusada_sem_criar_a_compra(banco):
    v = criar(banco, SIMULADO)
    antes = contagens(banco)
    assert 'futura' in recusa(banco, compra_nova(banco, dia=HOJE + dt.timedelta(days=3)), operacional(v))
    assert contagens(banco) == antes


# =====================================================================================================================
# 13, 14. Falha parcial e repeticao
# =====================================================================================================================

def test_falha_depois_da_compra_desfaz_tudo_e_a_nova_tentativa_grava_uma_vez(banco):
    """O abastecimento repetido so e descoberto depois de criar a compra: a transacao desfaz a compra; corrigido, grava uma vez."""
    v = criar(banco, SIMULADO)
    vinculado = salvar(banco, compra_nova(banco), operacional(v))['abastecimento']
    antes = contagens(banco)
    k = chave()
    # mesmo veiculo, data, hodometro e valor de um abastecimento ja vinculado: registrar recusa depois de criar_compra
    with pytest.raises(psycopg2.Error, match='já foi registrado'):
        salvar(banco, compra_nova(banco), operacional(v), chave_=k)
    assert contagens(banco) == antes
    r = salvar(banco, compra_nova(banco), operacional(v, hodometro_km=10350), chave_=chave())
    assert r['abastecimento']['id'] != vinculado['id']
    assert contagens(banco)['compras'] - antes['compras'] == 1


def test_repetir_a_mesma_operacao_nao_duplica_compra_nem_abastecimento(banco):
    v = criar(banco, SIMULADO)
    k = chave()
    r1 = salvar(banco, compra_nova(banco), operacional(v), chave_=k)
    antes = contagens(banco)
    r2 = salvar(banco, compra_nova(banco), operacional(v), chave_=k)
    assert r2['repetida'] is True and r2['lancamento_id'] == r1['lancamento_id'] and r2['abastecimento']['id'] == r1['abastecimento']['id']
    assert contagens(banco) == antes


def test_chave_de_outra_operacao_e_recusada(banco):
    v = criar(banco, SIMULADO)
    k = chave()
    rpc(banco, 'registrar_abastecimento', PESSOAL, {'veiculo_id': v, 'data_abastecimento': ONTEM.isoformat(), 'hodometro_km': 1, 'combustivel': 'gasolina',
                                                    'preco_litro': 4, 'valor_total': 40}, k)
    assert 'ja usada' in recusa(banco, compra_nova(banco), operacional(v, hodometro_km=5), chave_=k)


# =====================================================================================================================
# 15, 16. Despesa ja lancada e abastecimento ja registrado
# =====================================================================================================================

def test_compra_existente_recebe_abastecimento_sem_mudar_a_compra(banco):
    v = criar(banco, SIMULADO)
    lanc = compra(banco)
    linha = sql(banco, 'select md5(t::text) h from public.lancamento_agregado t where id = %s', (lanc,))[0]['h']
    total = fatura(banco)
    r = salvar(banco, {'tipo': 'compra_existente', 'id': lanc}, operacional(v))
    assert (r['lancamento_id'], r['abastecimento']['lancamento_id'], Decimal(str(r['abastecimento']['valor_total']))) == (lanc, lanc, Decimal('176.00'))
    assert sql(banco, 'select md5(t::text) h from public.lancamento_agregado t where id = %s', (lanc,))[0]['h'] == linha
    assert fatura(banco) == total
    # e uma segunda vez nao cria outro vinculo
    assert 'já tem um abastecimento' in recusa(banco, {'tipo': 'compra_existente', 'id': lanc}, operacional(v, hodometro_km=10500))


def test_abastecimento_ja_registrado_e_reaproveitado_pela_compra(banco):
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v)  # registrado antes em Mobilidade, aguardando a despesa
    lanc = compra(banco)
    leitura = rpc(banco, 'abastecimento_do_lancamento', PESSOAL, lanc, None)
    assert leitura['abastecimento'] is None and [c['id'] for c in leitura['candidatos']] == [a['id']]
    antes = contagens(banco)
    r = salvar(banco, {'tipo': 'compra_existente', 'id': lanc}, {'id': a['id']})
    assert (r['reaproveitado'], r['abastecimento']['id'], r['abastecimento']['lancamento_id']) == (True, a['id'], lanc)
    assert contagens(banco) == antes
    assert rpc(banco, 'abastecimento_do_lancamento', PESSOAL, lanc, None)['abastecimento']['id'] == a['id']


def test_mesmos_dados_de_um_abastecimento_aguardando_reaproveitam_o_registro(banco):
    """Quem registrou em Mobilidade e depois lanca a compra com os mesmos dados nao fica com dois abastecimentos."""
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v)
    antes = contagens(banco)
    r = salvar(banco, compra_nova(banco), operacional(v))
    assert (r['reaproveitado'], r['abastecimento']['id']) == (True, a['id'])
    assert contagens(banco)['abastecimentos'] == antes['abastecimentos']


def test_despesa_existente_editada_e_o_abastecimento_acompanha_com_historico(banco):
    v = criar(banco, SIMULADO)
    r = salvar(banco, despesa_nova(banco), operacional(v))
    conta_id, ab = r['conta_id'], r['abastecimento']['id']
    versao = rpc(banco, 'despesa_para_edicao', PESSOAL, conta_id)['versao']
    novo = salvar(banco, {'tipo': 'despesa_existente', 'id': conta_id, 'versao': versao,
                          'dados': {'valor': '180.40', 'nome': 'Posto direto (ficticio)'}},
                  operacional(v, id=ab, hodometro_km=10010, preco_litro=4.51))
    a = novo['abastecimento']
    assert (a['id'], a['conta_id'], Decimal(str(a['valor_total'])), Decimal(str(a['hodometro_km'])), a['corrigido']) == \
        (ab, conta_id, Decimal('180.40'), Decimal('10010'), True)
    assert sql(banco, 'select valor from public.conta where id = %s', (conta_id,))[0]['valor'] == Decimal('180.40')
    acoes = [x['acao'] for x in sql(banco, 'select acao from financeiro.abastecimento_historico where abastecimento_id = %s order by id', (ab,))]
    assert acoes == ['VINCULO', 'DESVINCULO', 'CORRECAO', 'VINCULO']


# =====================================================================================================================
# 17. Exclusao da despesa
# =====================================================================================================================

def test_excluir_a_compra_preserva_o_abastecimento_e_o_hodometro(banco):
    v = criar(banco, SIMULADO)
    r = salvar(banco, compra_nova(banco), operacional(v))
    versao = rpc(banco, 'compra_para_edicao', PESSOAL, r['lancamento_id'])['versao']
    rpc(banco, 'excluir_compra', PESSOAL, r['lancamento_id'], versao)
    a = historico(banco, v)['abastecimentos']
    assert [(x['id'], x['lancamento_id'], x['situacao_vinculo'], x['hodometro_km']) for x in a] == \
        [(r['abastecimento']['id'], None, 'AGUARDANDO', 10000)]


def test_excluir_a_despesa_direta_preserva_o_abastecimento(banco):
    v = criar(banco, SIMULADO)
    r = salvar(banco, despesa_nova(banco), operacional(v))
    versao = rpc(banco, 'despesa_para_edicao', PESSOAL, r['conta_id'])['versao']
    rpc(banco, 'excluir_despesa', PESSOAL, r['conta_id'], versao)
    assert [x['conta_id'] for x in historico(banco, v)['abastecimentos']] == [None]


# =====================================================================================================================
# 18. Mudanca de categoria: nada e excluido sozinho
# =====================================================================================================================

def test_mudar_a_categoria_da_despesa_nao_exclui_o_abastecimento(banco):
    v = criar(banco, SIMULADO)
    r = salvar(banco, despesa_nova(banco), operacional(v))
    versao = rpc(banco, 'despesa_para_edicao', PESSOAL, r['conta_id'])['versao']
    rpc(banco, 'editar_despesa', PESSOAL, r['conta_id'], versao, {'categoria_id': MORADIA})
    assert rpc(banco, 'abastecimento_do_lancamento', PESSOAL, None, r['conta_id'])['abastecimento']['id'] == r['abastecimento']['id']


# =====================================================================================================================
# 19 a 22. Regressao financeira
# =====================================================================================================================

def test_fatura_dashboard_saldos_e_recorrencias_so_veem_a_despesa(banco):
    v = criar(banco, SIMULADO)
    mes = ONTEM.replace(day=1)
    recorrencias = sql(banco, "select md5(coalesce(string_agg(t::text, '|' order by id), '')) h from public.item_despesa t where recorrente")[0]['h']
    bancos = sql(banco, "select md5(coalesce(string_agg(t::text, '|' order by id), '')) h from public.conta_bancaria t")[0]['h']
    movimentos = sql(banco, 'select count(*) n from public.movimento_financeiro')[0]['n']
    # a mesma compra com e sem abastecimento: os totais sao iguais
    sem = (fatura(banco), dashboard(banco, mes)['fluxo_caixa']['saidas'][-1])
    lanc = compra(banco, valor='176.00')
    so_compra = (fatura(banco), dashboard(banco, mes)['fluxo_caixa']['saidas'][-1])
    salvar(banco, {'tipo': 'compra_existente', 'id': lanc}, operacional(v))
    assert (fatura(banco), dashboard(banco, mes)['fluxo_caixa']['saidas'][-1]) == so_compra
    assert so_compra[0] - sem[0] == Decimal('176.00')
    assert sql(banco, "select md5(coalesce(string_agg(t::text, '|' order by id), '')) h from public.item_despesa t where recorrente")[0]['h'] == recorrencias
    assert sql(banco, "select md5(coalesce(string_agg(t::text, '|' order by id), '')) h from public.conta_bancaria t")[0]['h'] == bancos
    assert sql(banco, 'select count(*) n from public.movimento_financeiro')[0]['n'] == movimentos
    # o custo do veiculo conta a compra uma vez, como registrado; o abastecimento fica so como operacional
    custos = {c['veiculo_id']: c for c in rpc(banco, 'custos_veiculos_tela', PESSOAL, mes.isoformat())}[v]
    assert (Decimal(str(custos['registrado'])), Decimal(str(custos['abastecido']))) == (Decimal('176.00'), Decimal('176.00'))


def test_abastecimento_nao_muda_o_cenario_da_mobilidade(banco):
    v = criar(banco, SIMULADO)
    antes = sql(banco, "select md5(coalesce(string_agg(t::text, '|' order by id), '')) h from public.mobilidade_cenario_ativo t")[0]['h']
    salvar(banco, compra_nova(banco), operacional(v))
    assert sql(banco, "select md5(coalesce(string_agg(t::text, '|' order by id), '')) h from public.mobilidade_cenario_ativo t")[0]['h'] == antes


# =====================================================================================================================
# Permissoes e reversao
# =====================================================================================================================

def test_permissoes_das_funcoes_novas(banco):
    for funcao in ('formulario_abastecimento_lancamento(integer)', 'abastecimento_do_lancamento(integer, integer, integer)',
                   'salvar_lancamento_abastecimento(integer, jsonb, uuid)'):
        r = sql(banco, f"select has_function_privilege('authenticated', 'financeiro.{funcao}', 'execute') a, "
                       f"has_function_privilege('anon', 'financeiro.{funcao}', 'execute') n")[0]
        assert (r['a'], r['n']) == (True, False), funcao
    v = criar(banco, SIMULADO)
    with pytest.raises(psycopg2.Error):
        salvar(banco, compra_nova(banco), operacional(v), usuario=USUARIO_B)  # B nao gere o Pessoal


def test_reversao_remove_so_as_funcoes_e_reaplica(banco):
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    v = criar(banco, SIMULADO)
    r = salvar(banco, compra_nova(banco), operacional(v))
    antes = (dados_financeiros(banco), sql(banco, "select md5(string_agg(t::text, '|' order by id)) h from financeiro.abastecimento t")[0]['h'])
    conn = psycopg2.connect(banco)
    try:
        with conn, conn.cursor() as cur:
            cur.execute((raiz / 'supabase/reversao/20261217090000_abastecimento_lancamento_anterior.sql').read_text(encoding='utf-8'))
            cur.execute("select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro' "
                        "and p.proname in ('formulario_abastecimento_lancamento', 'abastecimento_do_lancamento', 'salvar_lancamento_abastecimento')")
            assert cur.fetchone()[0] == 0
        assert (dados_financeiros(banco), sql(banco, "select md5(string_agg(t::text, '|' order by id)) h from financeiro.abastecimento t")[0]['h']) == antes
        with conn, conn.cursor() as cur:
            cur.execute((raiz / MIGRATION).read_text(encoding='utf-8'))
    finally:
        conn.close()
    assert rpc(banco, 'abastecimento_do_lancamento', PESSOAL, r['lancamento_id'], None)['abastecimento']['id'] == r['abastecimento']['id']
