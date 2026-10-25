"""
Testes FIN-FIDELIDADE-CARTOES-1 — Importar Cartao (migration 20261105090000).

Cenario FICTICIO do FIN-RECORRENCIA-1 (tests/supabase_local.py), copia por teste: Cartao Teste (910, Pessoal, vence dia
31, limite ativo na Categoria do Cartao 961 <- categoria de despesa 952 "Assinaturas R"), recorrencia "Streaming"
(906, cartao 910, R$ 39,90). As linhas chegam como o navegador as le do arquivo (o banco nunca ve o arquivo).
"""
import json
import re
import uuid
from decimal import Decimal

import pytest

from tests.test_supabase_cartoes import ASSINATURAS, CARTAO, MORADIA, comprar, fatura, pagar
from tests.test_supabase_despesas import _paralelo
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    previa,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
MES = '2029-05-01'
NOVAS = ['financeiro.analisar_importacao_cartao(integer, integer, date, jsonb)',
         'financeiro.importar_fatura_cartao(integer, integer, date, jsonb, uuid)',
         'financeiro.sugerir_categorias_importacao(integer, jsonb)',
         'financeiro.resolver_categoria_cartao_tela(integer, integer, integer)']


@pytest.fixture
def banco(cluster):  # noqa: F811
    dsn = copiar(cluster)
    sql(dsn, "insert into public.categoria_palavra_chave (categoria_id, palavra, ativo) values (%s, 'netflix', true), "
             "(%s, 'aluguel', true)", (ASSINATURAS, MORADIA))
    return dsn


def linha(n, descricao, valor, data='2029-05-10', parcela=(1, 1), **extra):
    normal = ' '.join(re.sub(r'[^\w\s]', ' ', descricao.lower()).split())  # como o navegador (Flask)
    return {'linha_id': f'csv-{n}', 'linha_origem': n, 'data_compra': data, 'descricao_original': descricao,
            'descricao_normalizada': descricao, 'descricao_exibida': descricao, 'descricao_classificacao': normal,
            'valor': valor, 'parcela_atual': parcela[0], 'total_parcelas': parcela[1], 'tipo_movimento': 'debito', **extra}


def rpc(dsn, funcao, *args, usuario=USUARIO_A):
    """Como o navegador: dict e list vao como jsonb."""
    valores = [json.dumps(a) if isinstance(a, (dict, list)) else a for a in args]
    marcadores = ', '.join('%s::jsonb' if isinstance(a, (dict, list)) else '%s' for a in args)
    return chamar(dsn, usuario, f'select financeiro.{funcao}({marcadores})', valores)


def analisar(dsn, linhas, mes=MES, perfil=PESSOAL, usuario=USUARIO_A, cartao=CARTAO):
    return rpc(dsn, 'analisar_importacao_cartao', perfil, cartao, mes, linhas, usuario=usuario)


def importar(dsn, linhas, mes=MES, perfil=PESSOAL, usuario=USUARIO_A, chave=None):
    return rpc(dsn, 'importar_fatura_cartao', perfil, CARTAO, mes, linhas, chave or str(uuid.uuid4()), usuario=usuario)


def falha(dsn, funcao, *args, usuario=USUARIO_A):
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, funcao, *args, usuario=usuario)
    return erro.value.pgcode, erro.value.diag.message_primary


def importados(dsn):
    return sql(dsn, 'select * from public.lancamento_agregado where is_importado order by id')


@pytest.mark.parametrize('funcao', NOVAS)
def test_funcoes_seguras(banco, funcao):
    r = sql(banco, f"""select p.prosecdef as definer, coalesce(array_to_string(p.proconfig, ','), '') as config,
                              has_function_privilege('anon', '{funcao}', 'EXECUTE') as anon,
                              has_function_privilege('authenticated', '{funcao}', 'EXECUTE') as autenticado
                         from pg_proc p where p.oid = '{funcao}'::regprocedure""")[0]
    assert r['definer'] is True and 'search_path=""' in r['config']
    assert r['anon'] is False and r['autenticado'] is True
    assert sql(banco, "select has_function_privilege('authenticated', "
                      "'financeiro.sugestao_categoria_importacao(integer, text, text, integer)', 'EXECUTE') as x")[0]['x'] is False


def test_analise_classifica_sugere_e_detecta_duplicidade_no_lote(banco):
    r = analisar(banco, [
        linha(1, 'NETFLIX.COM', '39.90'),
        linha(2, 'ESTORNO LOJA', '20.00', tipo_movimento='credito'),
        linha(3, 'PADARIA', '12.50', categoria_id=MORADIA),
        linha(4, 'PADARIA', '12.50', categoria_id=MORADIA),
        linha(5, 'SEM DATA', '5.00', data=None, categoria_id=MORADIA),
    ])
    l1, l2, l3, l4, l5 = r['linhas']
    assert (l1['status'], l1['categoria_id'], l1['categoria_origem'], l1['categoria_cartao_id'], l1['status_classificacao']) == \
        ('valido', ASSINATURAS, 'palavra_chave', 961, 'classificada')
    assert l1['palavras_chave_encontradas'] == ['netflix']
    assert (l2['status'], l2['ignorar']) == ('ignorado', True)
    assert (l3['status'], l3['categoria_origem'], l3['categoria_cartao_id'], l3['status_classificacao']) == \
        ('valido', 'manual', None, 'categoria_cartao_pendente')
    assert (l4['status'], l4['duplicidade'], l4['ignorar']) == ('duplicado', 'lote', True)
    assert (l5['status'], 'Data de compra ausente.' in l5['mensagens']) == ('revisar', True)
    v = r['validacoes']
    assert (v['total_linhas'], v['validas'], v['duplicadas'], v['creditos'], v['revisar'], v['total_importavel']) == \
        (5, 2, 1, 1, 1, 57.4)


def test_sugestao_ambigua_e_por_historico(banco):
    sql(banco, "insert into public.categoria_palavra_chave (categoria_id, palavra, ativo) values (%s, 'netflix', true)", (MORADIA,))
    r = analisar(banco, [linha(1, 'NETFLIX', '10.00')])['linhas'][0]
    assert (r['categoria_id'], r['categoria_origem'], r['status'], r['status_classificacao']) == (None, 'ambigua', 'revisar', 'ambigua')
    assert len(r['categorias_candidatas']) == 2
    comprar(banco, descricao='Farmacia Central', total_parcelas=1, categoria_id=MORADIA)
    r = analisar(banco, [linha(1, 'Farmacia Central', '10.00')])['linhas'][0]
    assert (r['categoria_id'], r['categoria_origem']) == (MORADIA, 'historico')


def test_importacao_grava_tudo_e_reimportar_nao_duplica(banco):
    linhas = [linha(1, 'NETFLIX.COM', '39.90'), linha(2, 'PADARIA', '12.50', categoria_id=MORADIA),
              linha(3, 'ESTORNO', '5.00', tipo_movimento='credito')]
    chave = str(uuid.uuid4())
    r = importar(banco, linhas, chave=chave)
    assert (r['inseridos'], r['linhas_importadas'], r['faturas']) == (2, 2, [MES])
    gravados = importados(banco)
    assert [(g['descricao_original'], g['valor'], str(g['mes_fatura']), g['origem_importacao'], g['categoria_cartao_id'])
            for g in gravados] == [('NETFLIX.COM', Decimal('39.90'), MES, 'csv', 961), ('PADARIA', Decimal('12.50'), MES, 'csv', None)]
    assert fatura(banco, CARTAO, MES)['valor_executado'] == Decimal('52.40')
    assert importar(banco, linhas, chave=chave)['repetida'] is True  # mesma chave: mesmo resultado
    reanalise = analisar(banco, linhas)['linhas']
    assert [x['duplicidade'] for x in reanalise[:2]] == ['banco', 'banco']
    assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, (linhas), str(uuid.uuid4()))[1] == 'Nenhuma linha para importar'
    assert len(importados(banco)) == 2


def test_conciliacao_com_compra_lancada_manualmente(banco):
    comprar(banco, descricao='Mercado do bairro', valor='50.00', total_parcelas=1, data_compra='2029-05-09', categoria_id=MORADIA)
    r = analisar(banco, [linha(1, 'MERCADO XYZ*BAIRRO', '50.00', data='2029-05-12', categoria_id=MORADIA),
                         linha(2, 'OUTRO MERCADO', '50.00', data='2029-05-12', categoria_id=MORADIA)])
    a, b = r['linhas']
    assert (a['status'], a['ignorar'], a['conciliacao']['descricao']) == ('conciliado', True, 'Mercado do bairro')
    assert (b['status'], b['conciliacao']) == ('valido', None)  # o lancamento concilia uma linha so
    assert r['validacoes']['conciliadas'] == 1
    mantida = analisar(banco, [linha(1, 'MERCADO XYZ*BAIRRO', '50.00', data='2029-05-12', categoria_id=MORADIA,
                                     manter_conciliada=True)])['linhas'][0]
    assert (mantida['status'], mantida['ignorar'], mantida['conciliacao']['mantida']) == ('valido', False, True)


def test_conciliada_nao_e_importada_sem_manter(banco):
    comprar(banco, descricao='Mercado do bairro', valor='50.00', total_parcelas=1, data_compra='2029-05-09', categoria_id=MORADIA)
    linhas = [linha(1, 'MERCADO XYZ', '50.00', data='2029-05-12', categoria_id=MORADIA), linha(2, 'PADARIA', '9.00', categoria_id=MORADIA)]
    r = importar(banco, linhas)
    assert (r['inseridos'], r['duplicados']) == (1, 1)
    assert [g['descricao_original'] for g in importados(banco)] == ['PADARIA']


def test_linha_pendente_recusa_tudo(banco):
    antes = sql(banco, 'select count(*) as n from public.lancamento_agregado')[0]['n']
    codigo, mensagem = falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES,
                             ([linha(1, 'PADARIA', '9.00', categoria_id=MORADIA), linha(2, 'SEM DATA', '1.00', data=None, categoria_id=MORADIA)]),
                             str(uuid.uuid4()))
    assert codigo == '22023' and mensagem.startswith('Importacao nao realizada: 1 linha(s) precisam de revisao')
    assert sql(banco, 'select count(*) as n from public.lancamento_agregado')[0]['n'] == antes
    r = importar(banco, [linha(1, 'PADARIA', '9.00', categoria_id=MORADIA),
                         linha(2, 'SEM DATA', '1.00', data=None, categoria_id=MORADIA, ignorar=True)])  # retirada pelo usuario
    assert r['inseridos'] == 1


def test_fatura_paga_desvia_e_consolidada_recusa(banco):
    comprar(banco, descricao='Abre fatura', total_parcelas=1, categoria_id=MORADIA)
    pagar(banco, CARTAO, MES)
    importar(banco, [linha(1, 'PADARIA', '9.00', categoria_id=MORADIA)])
    g = importados(banco)[0]
    assert (str(g['mes_fatura']), str(g['mes_fatura_original'])) == ('2029-06-01', MES)
    comprar(banco, descricao='Abre julho', total_parcelas=1, categoria_id=MORADIA, mes_fatura='2029-07-01', data_compra='2029-07-02')
    sql(banco, "update public.conta set status_fatura = 'FECHADA' where is_fatura_cartao and item_despesa_id = %s "
               "and cartao_competencia = '2029-07-01'", (CARTAO,))
    antes = len(importados(banco))
    codigo, mensagem = falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, '2029-07-01',
                             ([linha(1, 'CAFE', '3.00', data='2029-07-03', categoria_id=MORADIA)]), str(uuid.uuid4()))
    assert codigo == 'P0001' and 'consolidada' in mensagem
    assert len(importados(banco)) == antes


def test_parcelamento_da_linha_gera_atual_e_futuras(banco):
    r = importar(banco, [linha(1, 'LOJA X', '100.00', parcela=(3, 5), categoria_id=MORADIA, gerar_parcelas_futuras=True)])
    assert r['inseridos'] == 3
    g = importados(banco)
    assert [(x['numero_parcela'], x['total_parcelas'], str(x['mes_fatura']), str(x['data_compra']), x['descricao_exibida']) for x in g] == [
        (3, 5, '2029-05-01', '2029-05-10', 'LOJA X (3/5)'), (4, 5, '2029-06-01', '2029-06-10', 'LOJA X (4/5)'),
        (5, 5, '2029-07-01', '2029-07-10', 'LOJA X (5/5)')]
    assert len({x['compra_id'] for x in g}) == 1
    so_atual = analisar(banco, [linha(1, 'LOJA Y', '10.00', parcela=(2, 4), categoria_id=MORADIA)])['linhas'][0]
    assert so_atual['parcela'] == '2/4'


def test_compra_recorrente_do_cartao_reconhecida_e_nao_gerada_de_novo(banco):
    atribuir(banco, 'PESSOAL')
    a_gerar = lambda: [(i['nome'], str(i['competencia'])[:7]) for i in previa(banco, mes=MES)['itens']]  # noqa: E731
    assert ('Streaming', '2029-05') in a_gerar()  # antes: o gerador lancaria a compra recorrente de 05/2029
    r = analisar(banco, [linha(1, 'Streaming', '39.90', data='2029-05-31')])['linhas'][0]
    assert r['recorrencia_id'] == 906
    importar(banco, [linha(1, 'Streaming', '39.90', data='2029-05-31')])
    g = importados(banco)[0]
    assert (g['is_recorrente'], g['item_despesa_id']) == (True, 906)
    assert ('Streaming', '2029-05') not in a_gerar()  # a importada e a da competencia: nao e gerada de novo


@pytest.mark.parametrize('usuario, perfil', [(USUARIO_B, PESSOAL), (USUARIO_A, ID['PERFIL_B']), (None, PESSOAL)])
def test_isolamento(banco, usuario, perfil):
    assert falha(banco, 'analisar_importacao_cartao', perfil, CARTAO, MES, ([linha(1, 'X', '1.00')]), usuario=usuario)[0] == '42501'
    assert falha(banco, 'importar_fatura_cartao', perfil, CARTAO, MES, ([linha(1, 'X', '1.00', categoria_id=MORADIA)]),
                 str(uuid.uuid4()), usuario=usuario)[0] == '42501'
    assert importados(banco) == []


def test_leitor_nao_importa(banco):
    assert falha(banco, 'importar_fatura_cartao', ID['EMPRESA'], CARTAO, MES, ([linha(1, 'X', '1.00', categoria_id=MORADIA)]),
                 str(uuid.uuid4()))[0] == '42501'


def test_sugestoes_e_resolucao(banco):
    r = rpc(banco, 'sugerir_categorias_importacao', PESSOAL,
            ([{'descricao': 'NETFLIX.COM', 'classificacao': 'netflix com', 'normalizada': 'NETFLIX.COM'}]))
    assert (r['NETFLIX.COM']['categoria_id'], r['NETFLIX.COM']['origem']) == (ASSINATURAS, 'palavra_chave')
    assert rpc(banco, 'resolver_categoria_cartao_tela', PESSOAL, CARTAO, ASSINATURAS)['categoria_cartao_id'] == 961
    assert rpc(banco, 'resolver_categoria_cartao_tela', PESSOAL, CARTAO, MORADIA)['vinculada_ao_cartao'] is False


# ---------------------------------------------------------------------------
# Credito na fatura: pagamento, estorno e ajuste nunca entram como compra nem reduzem a fatura
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('descricao, tipo', [('Pagamento recebido', 'pagamento_fatura'), ('PGTO FATURA', 'pagamento_fatura'),
                                             ('ESTORNO LOJA X', 'estorno'), ('Credito de anuidade', 'credito_ajuste')])
def test_credito_classificado_e_nunca_importado(banco, descricao, tipo):
    comprar(banco, descricao='Compra da fatura', valor='100.00', total_parcelas=1, categoria_id=MORADIA)
    antes = fatura(banco, CARTAO, MES)
    # Mesmo que o cliente mande a linha como "debito" e nao retirada, valor negativo e credito.
    for l in (linha(1, descricao, '-80.00', categoria_id=MORADIA),
              linha(1, descricao, '80.00', categoria_id=MORADIA, tipo_movimento='credito', ignorar=False)):
        r = analisar(banco, [l])['linhas'][0]
        assert (r['tipo_movimento'], r['tipo_credito'], r['status'], r['ignorar']) == ('credito', tipo, 'ignorado', True)
        codigo, mensagem = falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, [l], str(uuid.uuid4()))
        assert (codigo, mensagem) == ('22023', 'Nenhuma linha para importar')
    assert importados(banco) == []
    depois = fatura(banco, CARTAO, MES)
    assert (depois['valor_executado'], depois['valor']) == (antes['valor_executado'], antes['valor']) == (Decimal('100.00'), antes['valor'])


def test_credito_no_meio_da_fatura_nao_reduz_o_total(banco):
    r = importar(banco, [linha(1, 'PADARIA', '40.00', categoria_id=MORADIA), linha(2, 'Pagamento recebido', '-500.00'),
                         linha(3, 'ESTORNO PADARIA', '-40.00')])
    assert r['inseridos'] == 1
    assert fatura(banco, CARTAO, MES)['valor_executado'] == Decimal('40.00')
    assert sql(banco, 'select count(*) as n from public.lancamento_agregado where valor <= 0')[0]['n'] == 0


# ---------------------------------------------------------------------------
# Concorrencia: duas confirmacoes simultaneas do mesmo arquivo nunca duplicam
# ---------------------------------------------------------------------------

def test_importacoes_simultaneas_do_mesmo_arquivo_gravam_uma_vez(banco):
    linhas = [linha(1, 'PADARIA', '9.00', categoria_id=MORADIA), linha(2, 'FARMACIA', '15.00', categoria_id=MORADIA)]
    resultados = _paralelo([lambda: importar(banco, linhas) for _ in range(3)])  # chaves diferentes
    oks = [r for r in resultados if r[0] == 'ok']
    erros = [r for r in resultados if r[0] == 'erro']
    assert len(oks) == 1 and oks[0][1]['inseridos'] == 2
    assert len(erros) == 2 and all('Nenhuma linha para importar' in str(e[1]) for e in erros)
    assert len(importados(banco)) == 2
    assert fatura(banco, CARTAO, MES)['valor_executado'] == Decimal('24.00')


def test_mesma_chave_em_paralelo_devolve_o_mesmo_resultado(banco):
    chave = str(uuid.uuid4())
    linhas = [linha(1, 'PADARIA', '9.00', categoria_id=MORADIA)]
    resultados = _paralelo([lambda: importar(banco, linhas, chave=chave) for _ in range(3)])
    assert [r[0] for r in resultados] == ['ok'] * 3
    assert len({tuple(r[1]['lancamentos']) for r in resultados}) == 1
    assert len(importados(banco)) == 1


def test_falha_no_meio_desfaz_tudo(banco):
    # A segunda linha cai numa fatura consolidada (julho): nada da primeira fica gravado.
    comprar(banco, descricao='Abre julho', total_parcelas=1, categoria_id=MORADIA, mes_fatura='2029-07-01', data_compra='2029-07-02')
    sql(banco, "update public.conta set status_fatura = 'FECHADA' where is_fatura_cartao and item_despesa_id = %s "
               "and cartao_competencia = '2029-07-01'", (CARTAO,))
    antes = sql(banco, 'select count(*) as n from public.lancamento_agregado')[0]['n']
    faturas_antes = sql(banco, 'select id, valor, valor_executado from public.conta where is_fatura_cartao order by id')
    codigo, _ = falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES,
                      [linha(1, 'PADARIA', '9.00', categoria_id=MORADIA),
                       linha(2, 'LOJA', '30.00', parcela=(1, 3), categoria_id=MORADIA, gerar_parcelas_futuras=True)],
                      str(uuid.uuid4()))
    assert codigo == 'P0001'
    assert sql(banco, 'select count(*) as n from public.lancamento_agregado')[0]['n'] == antes
    assert sql(banco, 'select id, valor, valor_executado from public.conta where is_fatura_cartao order by id') == faturas_antes
