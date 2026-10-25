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
