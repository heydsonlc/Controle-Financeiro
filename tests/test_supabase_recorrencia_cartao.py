"""
Testes FIN-FIDELIDADE-CARTOES-2 — R2 (recorrencia no cartao, migration 20261106090000) e o modelo previsto / realizado /
pago da fatura do Flask (routes/despesas.py _calcular_totais_fatura_cartao_previsto e CartaoService.calcular_planejado).

Cenario FICTICIO do FIN-RECORRENCIA-1: Cartao Teste (910, Pessoal, vence dia 31), Categoria do Cartao 961 (limite 981)
mapeada a categoria 952; Cartao Sem Config (911); Cartao B (930, Perfil B).
"""
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest

from tests.test_supabase_cartoes import ASSINATURAS, CARTAO, CARTAO_B, MORADIA, comprar, edicao, fatura, pagar, tabela
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    gerar,
    previa,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
SEM_CONFIG = 911
DADOS = {'nome': 'Streaming no cartao', 'valor': '45.90', 'categoria_id': ASSINATURAS, 'data_vencimento': '2029-05-20',
         'tipo_recorrencia': 'mensal', 'cartao_id': CARTAO, 'descricao': 'Plano familia'}
NOVAS = ['financeiro.criar_recorrencia_cartao(integer, jsonb, uuid)',
         'financeiro.editar_recorrencia_cartao(integer, integer, text, jsonb)',
         'financeiro.definir_situacao_recorrencia_cartao(integer, integer, text, boolean)']


@pytest.fixture
def banco(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    return dsn


def rpc(dsn, funcao, *args, usuario=USUARIO_A):
    valores = [json.dumps(a) if isinstance(a, (dict, list)) else a for a in args]
    marcadores = ', '.join('%s::jsonb' if isinstance(a, (dict, list)) else '%s' for a in args)
    return chamar(dsn, usuario, f'select financeiro.{funcao}({marcadores})', valores)


def falha(dsn, funcao, *args, usuario=USUARIO_A):
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, funcao, *args, usuario=usuario)
    return erro.value.pgcode, erro.value.diag.message_primary


def criar(dsn, perfil=PESSOAL, usuario=USUARIO_A, **campos):
    return rpc(dsn, 'criar_recorrencia_cartao', perfil, {**DADOS, **campos}, str(uuid.uuid4()), usuario=usuario)


def versao(dsn, item):
    return next(r['versao'] for r in tabela(dsn, 'recorrencias_do_perfil', PESSOAL) if r['id'] == item)


def compras_da_recorrencia(dsn, item):
    return sql(dsn, 'select * from public.lancamento_agregado where item_despesa_id = %s order by mes_fatura', (item,))


def gerar_mes(dsn, mes):
    p = previa(dsn, mes=mes)
    return gerar(dsn, p['a_gerar'], mes=mes)


@pytest.mark.parametrize('funcao', NOVAS)
def test_funcoes_seguras(banco, funcao):
    r = sql(banco, f"""select p.prosecdef as definer, coalesce(array_to_string(p.proconfig, ','), '') as config,
                              has_function_privilege('anon', '{funcao}', 'EXECUTE') as anon,
                              has_function_privilege('authenticated', '{funcao}', 'EXECUTE') as autenticado
                         from pg_proc p where p.oid = '{funcao}'::regprocedure""")[0]
    assert r['definer'] is True and 'search_path=""' in r['config'] and (r['anon'], r['autenticado']) == (False, True)
    for interna in ('financeiro.ler_dados_recorrencia_cartao(integer, jsonb, boolean)',
                    'financeiro.travar_recorrencia_cartao(integer, integer, text)'):
        assert sql(banco, f"select has_function_privilege('authenticated', '{interna}', 'EXECUTE') as x")[0]['x'] is False


def test_cadastro_como_o_flask_e_geracao_sem_duplicar(banco):
    item = criar(banco)['item_id']
    i = sql(banco, 'select * from public.item_despesa where id = %s', (item,))[0]
    assert (i['tipo'], i['recorrente'], i['meio_pagamento'], i['cartao_id'], i['categoria_cartao_id'], i['perfil_financeiro_id']) == \
        ('Simples', True, 'cartao', CARTAO, 961, PESSOAL)
    assert compras_da_recorrencia(banco, item) == []  # salvar nao gera: geracao explicita em Despesas
    linhas = [x for x in previa(banco, mes='2029-05-01')['itens'] if x['nome'] == 'Streaming no cartao']
    assert [(x['natureza'], str(x['competencia'])[:7]) for x in linhas] == [('LANCAMENTO_CARTAO', '2029-05'), ('LANCAMENTO_CARTAO', '2029-06')]
    gerar_mes(banco, '2029-05-01')
    gerados = compras_da_recorrencia(banco, item)
    assert [(str(g['mes_fatura']), g['valor'], g['is_recorrente'], g['categoria_cartao_id']) for g in gerados] == [
        ('2029-05-01', Decimal('45.90'), True, 961), ('2029-06-01', Decimal('45.90'), True, 961)]
    gerar_mes(banco, '2029-05-01')
    assert len(compras_da_recorrencia(banco, item)) == 2  # sem duplicidade
    assert edicao(banco, gerados[0]['id'])['parcelas'][0]['bloqueio'] == 'Gerada por recorrencia: edite a recorrencia'


def test_edicao_vale_para_as_proximas_e_preserva_a_paga(banco):
    item = criar(banco)['item_id']
    gerar_mes(banco, '2029-05-01')
    pagar(banco, CARTAO, date(2029, 5, 1))
    rpc(banco, 'editar_recorrencia_cartao', PESSOAL, item, versao(banco, item), {'valor': '50.00', 'nome': 'Streaming premium'})
    gerar_mes(banco, '2029-07-01')
    g = compras_da_recorrencia(banco, item)
    assert [(str(x['mes_fatura']), x['valor']) for x in g] == [
        ('2029-05-01', Decimal('45.90')), ('2029-06-01', Decimal('45.90')), ('2029-07-01', Decimal('50.00')), ('2029-08-01', Decimal('50.00'))]
    assert fatura(banco, CARTAO, date(2029, 5, 1))['status_pagamento'] == 'Pago'


def test_trocar_cartao_e_categoria_resolve_de_novo(banco):
    item = criar(banco)['item_id']
    rpc(banco, 'editar_recorrencia_cartao', PESSOAL, item, versao(banco, item), {'categoria_id': MORADIA})
    assert sql(banco, 'select categoria_cartao_id from public.item_despesa where id = %s', (item,))[0]['categoria_cartao_id'] is None


def test_inativar_e_reativar(banco):
    item = criar(banco)['item_id']
    rpc(banco, 'definir_situacao_recorrencia_cartao', PESSOAL, item, versao(banco, item), False)
    assert not [x for x in previa(banco, mes='2029-05-01')['itens'] if x['nome'] == 'Streaming no cartao']
    rpc(banco, 'definir_situacao_recorrencia_cartao', PESSOAL, item, versao(banco, item), True)
    assert [x for x in previa(banco, mes='2029-05-01')['itens'] if x['nome'] == 'Streaming no cartao']


@pytest.mark.parametrize('campos, trecho', [
    ({'tipo_recorrencia': 'semanal'}, 'mensal e anual'),
    ({'cartao_id': SEM_CONFIG}, 'dia de vencimento'),
    ({'cartao_id': CARTAO_B}, 'nao encontrado neste perfil'),
    ({'valor': '0'}, 'Valor'),
    ({'data_vencimento': None}, 'primeiro vencimento'),
    ({'categoria_id': 999999}, 'Categoria'),
])
def test_cadastro_invalido_recusado(banco, campos, trecho):
    antes = sql(banco, 'select count(*) as n from public.item_despesa')[0]['n']
    assert trecho in falha(banco, 'criar_recorrencia_cartao', PESSOAL, {**DADOS, **campos}, str(uuid.uuid4()))[1]
    assert sql(banco, 'select count(*) as n from public.item_despesa')[0]['n'] == antes


def test_isolamento_leitor_versao_e_outro_modulo(banco):
    item = criar(banco)['item_id']
    v = versao(banco, item)
    assert falha(banco, 'criar_recorrencia_cartao', PESSOAL, DADOS, str(uuid.uuid4()), usuario=USUARIO_B)[0] == '42501'
    assert falha(banco, 'criar_recorrencia_cartao', ID['EMPRESA'], DADOS, str(uuid.uuid4()))[0] == '42501'
    assert falha(banco, 'editar_recorrencia_cartao', PESSOAL, item, v, {'valor': '1'}, usuario=USUARIO_B)[0] == '42501'
    rpc(banco, 'editar_recorrencia_cartao', PESSOAL, item, v, {'valor': '46.00'})
    assert falha(banco, 'editar_recorrencia_cartao', PESSOAL, item, v, {'valor': '47.00'})[1].startswith('A recorrencia foi alterada')
    # Recorrencia comum (boleto) nao e alterada por aqui, e a de cartao nao e alterada pela comum.
    assert 'outro modulo' in falha(banco, 'editar_recorrencia_cartao', PESSOAL, 901, versao(banco, 901), {'valor': '1'})[1]
    assert 'outro modulo' in falha(banco, 'editar_recorrencia', PESSOAL, item, versao(banco, item), {'valor': '1'})[1]


def test_perfil_gerado_pelo_flask_nao_muda_dia_nem_frequencia(banco):
    item = criar(banco)['item_id']
    atribuir(banco, 'PESSOAL', 'FLASK')
    codigo, _ = falha(banco, 'editar_recorrencia_cartao', PESSOAL, item, versao(banco, item), {'data_vencimento': '2029-05-25'})
    assert codigo == 'P0001'
    rpc(banco, 'editar_recorrencia_cartao', PESSOAL, item, versao(banco, item), {'valor': '48.00'})  # o resto muda


def test_mesma_chave_nao_duplica(banco):
    chave = str(uuid.uuid4())
    a = rpc(banco, 'criar_recorrencia_cartao', PESSOAL, DADOS, chave)
    b = rpc(banco, 'criar_recorrencia_cartao', PESSOAL, DADOS, chave)
    assert a['item_id'] == b['item_id'] and b['repetida'] is True


# ---------------------------------------------------------------------------
# Previsto, realizado e pago (regra consolidada do Flask; nada redesenhado)
# ---------------------------------------------------------------------------

def _fatura_na_tela(dsn, mes):
    f = fatura(dsn, CARTAO, mes)
    linha = next(c for c in tabela(dsn, 'contas_do_mes', PESSOAL, str(mes)) if c['id'] == f['id'])
    return f, linha


def test_previsto_realizado_e_pago_como_o_flask(banco):
    # So o limite do exemplo: Categoria do Cartao 961 com previsao de R$ 300 (o legado 983 fora).
    sql(banco, "update public.cartao_categoria_limite set limite_mensal = 300 where id = 981")
    sql(banco, "update public.cartao_categoria_limite set ativo = false where id = 983")
    comprar(banco, total_parcelas=1, valor='90.00')  # 952 -> 961
    f, linha = _fatura_na_tela(banco, date(2029, 5, 1))
    # Projecao R$ 300 (previsto da fatura e planejado gravado), realizado R$ 90, a pagar R$ 90.
    assert (Decimal(str(linha['valor'])), Decimal(str(linha['valor_previsto'])), Decimal(str(linha['valor_executado']))) == \
        (Decimal('300.00'), Decimal('300.00'), Decimal('90.00'))
    assert (f['valor_planejado'], f['valor_executado']) == (Decimal('300.00'), Decimal('90.00'))
    limite = next(x for x in tabela(banco, 'limites_do_cartao', PESSOAL, CARTAO, '2029-05-01') if x['id'] == 981)
    assert (limite['limite_mensal'], limite['gasto_atual'], limite['disponivel']) == (300, 90, 210)
    pagar(banco, CARTAO, date(2029, 5, 1))
    _, linha = _fatura_na_tela(banco, date(2029, 5, 1))
    assert Decimal(str(linha['valor'])) == Decimal('90.00')  # paga: o realizado, sem somar a previsao


def test_consumo_acima_da_previsao_nao_muda_a_previsao(banco):
    sql(banco, "update public.cartao_categoria_limite set limite_mensal = 600 where id = 981")
    sql(banco, "update public.cartao_categoria_limite set ativo = false where id = 983")
    comprar(banco, total_parcelas=1, valor='620.00')
    f, linha = _fatura_na_tela(banco, date(2029, 5, 1))
    # Previsto da fatura = max(previsao, gasto) por categoria = 620; a previsao (planejado) continua 600.
    assert (Decimal(str(linha['valor_previsto'])), Decimal(str(linha['valor_executado'])), f['valor_planejado'],
            f['estouro_orcamento']) == (Decimal('620.00'), Decimal('620.00'), Decimal('600.00'), True)
    limite = next(x for x in tabela(banco, 'limites_do_cartao', PESSOAL, CARTAO, '2029-05-01') if x['id'] == 981)
    assert (limite['limite_mensal'], limite['disponivel']) == (600, -20)
    status = rpc(banco, 'fatura_por_categoria', PESSOAL, CARTAO, '2029-05-01')['categorias'][0]['status']
    assert status == 'Estourado'


# ---------------------------------------------------------------------------
# Exemplo do titular: combustivel, 4 abastecimentos previstos de R$ 150 (previsao de R$ 600 na Categoria do Cartao).
# No Flask, essa previsao e o limite da categoria; as compras realizadas (manuais ou importadas) compoem o realizado e
# o previsto da fatura e realizado + o que falta da previsao. Nada duplica e o mes seguinte continua com R$ 600.
# ---------------------------------------------------------------------------

def _so_combustivel(dsn):
    sql(dsn, "update public.cartao_categoria_limite set limite_mensal = 600 where id = 981")  # 961: "combustivel" do exemplo
    sql(dsn, "update public.cartao_categoria_limite set ativo = false where id = 983")


def _linha_importada(n, valor, data):
    texto = f'POSTO {n}'
    return {'linha_id': f'csv-{n}', 'linha_origem': n, 'data_compra': data, 'descricao_original': texto,
            'descricao_normalizada': texto, 'descricao_exibida': texto, 'descricao_classificacao': texto.lower(),
            'valor': valor, 'parcela_atual': 1, 'total_parcelas': 1, 'tipo_movimento': 'debito', 'categoria_id': ASSINATURAS}


def _apuracao(dsn, mes):
    f, linha = _fatura_na_tela(dsn, mes)
    return Decimal(str(linha['valor_previsto'])), Decimal(str(linha['valor_executado'])), Decimal(str(linha['valor']))


@pytest.mark.parametrize('origem', ['manual', 'importada'])
def test_combustivel_previsto_realizado_devido_e_mes_seguinte(banco, origem):
    _so_combustivel(banco)
    abastecimentos = [('145.00', '2029-05-03'), ('160.00', '2029-05-10'), ('155.00', '2029-05-17')]  # o 4o nao acontece
    if origem == 'manual':
        for valor, data in abastecimentos:
            comprar(banco, total_parcelas=1, valor=valor, data_compra=data)
    else:
        linhas = [_linha_importada(i + 1, v, d) for i, (v, d) in enumerate(abastecimentos)]
        r = rpc(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, '2029-05-01', linhas, str(uuid.uuid4()))
        assert r['inseridos'] == 3
        # Reimportar a mesma fatura nao duplica nada.
        assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, '2029-05-01', linhas, str(uuid.uuid4()))[1] == 'Nenhuma linha para importar'
    # Previsao R$ 600 (realizado R$ 460 + R$ 140 que falta), realizado R$ 460; aberta, a tela mostra a previsao.
    assert _apuracao(banco, date(2029, 5, 1)) == (Decimal('600.00'), Decimal('460.00'), Decimal('600.00'))
    # O mes seguinte continua com a previsao de R$ 600 (nada foi reprogramado).
    comprar(banco, total_parcelas=1, valor='10.00', data_compra='2029-06-02', mes_fatura='2029-06-01')
    assert _apuracao(banco, date(2029, 6, 1)) == (Decimal('600.00'), Decimal('10.00'), Decimal('600.00'))
    # Paga, a fatura de maio vale o realizado: o devido e R$ 460, sem a parte prevista e nao realizada.
    pagar(banco, CARTAO, date(2029, 5, 1))
    assert _apuracao(banco, date(2029, 5, 1))[2] == Decimal('460.00')
    assert fatura(banco, CARTAO, date(2029, 5, 1))['valor_planejado'] == Decimal('600.00')


def test_gasto_acima_da_previsao_nao_reprograma_o_mes_seguinte(banco):
    _so_combustivel(banco)
    for valor in ('300.00', '320.00'):
        comprar(banco, total_parcelas=1, valor=valor)
    assert _apuracao(banco, date(2029, 5, 1))[:2] == (Decimal('620.00'), Decimal('620.00'))
    comprar(banco, total_parcelas=1, valor='1.00', data_compra='2029-06-02', mes_fatura='2029-06-01')
    assert _apuracao(banco, date(2029, 6, 1))[0] == Decimal('600.00')


def test_recorrencia_importada_com_valor_diferente_nao_duplica_a_ocorrencia(banco):
    """Como vincular_linha_recorrencia do Flask: a ocorrencia do mes ja existe; a linha nao gera outra compra."""
    item = criar(banco)['item_id']
    gerar_mes(banco, '2029-05-01')
    linha = {**_linha_importada(1, '49.90', '2029-05-20'), 'descricao_original': 'Streaming no cartao',
             'descricao_normalizada': 'Streaming no cartao', 'descricao_exibida': 'Streaming no cartao',
             'descricao_classificacao': 'streaming no cartao'}
    analise = rpc(banco, 'analisar_importacao_cartao', PESSOAL, CARTAO, '2029-05-01', [linha])['linhas'][0]
    assert (analise['status'], analise['ignorar'], analise['conciliacao']['valor']) == ('conciliado', True, 45.9)
    assert 'Recorrencia ja lancada nesta fatura' in ' '.join(analise['mensagens'])
    assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, '2029-05-01', [linha], str(uuid.uuid4()))[1] == 'Nenhuma linha para importar'
    assert [x['valor'] for x in compras_da_recorrencia(banco, item) if str(x['mes_fatura']) == '2029-05-01'] == [Decimal('45.90')]


def test_recorrencia_importada_antes_da_geracao_e_reconhecida_pelo_gerador(banco):
    """Sem compra no mes, a linha importada vira a ocorrencia da recorrencia; o gerador nao lanca outra."""
    item = criar(banco)['item_id']
    linha = {**_linha_importada(1, '45.90', '2029-05-20'), 'descricao_original': 'Streaming no cartao',
             'descricao_normalizada': 'Streaming no cartao', 'descricao_exibida': 'Streaming no cartao',
             'descricao_classificacao': 'streaming no cartao'}
    rpc(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, '2029-05-01', [linha], str(uuid.uuid4()))
    gerar_mes(banco, '2029-05-01')
    maio = [x for x in compras_da_recorrencia(banco, item) if str(x['mes_fatura']) == '2029-05-01']
    assert [(x['valor'], x['is_importado']) for x in maio] == [(Decimal('45.90'), True)]
