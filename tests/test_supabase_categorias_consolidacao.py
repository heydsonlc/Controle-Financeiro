"""
Testes FIN-CATEGORIAS-CONSOLIDACAO-01 (migration 20261214090000), em cluster local descartavel com o cenario FICTICIO dos
cartoes (contrato 910 do Pessoal, Categoria do Cartao 961 com limite) e um catalogo como o da producao: as 9 categorias
sistemicas de Mobilidade, a "Revisao" (MOB_REVISAO) legada e as quatro redundantes do seed BASE-REAL-1B (Transporte por
App, Manutencao de Veiculo, Assinaturas, Software e IA), com palavras-chave e vinculos com a Categoria do Cartao.
- as quatro incorporacoes aprovadas (96->8, 98->5 com pneu e lavajato, 4->5, 99->100 renomeada) pela previa conferida;
- lancamentos, faturas pagas, recorrencias, previsoes, Categorias do Cartao e o resto do banco iguais (so a coluna da
  categoria muda); a classificacao automatica no mesmo agrupamento da fatura;
- Mobilidade: revisoes em MOB_MANUTENCAO, cenario efetivado, alterado e trocado sem duplicar; o Flask nao recria;
- duplicidades, execucao repetida, rollback, perfis, bloqueios, limpeza e reimportacao dos cartoes; reversao.
"""
import json
import os
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartao_despesas_fixas import MES, PESSOAL, banco, recorrencia  # noqa: F401
from tests.test_supabase_cartoes import CARTAO, comprar, fatura, pagar
from tests.test_supabase_cartoes_multiplos import importar, limpar, limpeza, linha
from tests.test_supabase_categorias_recorrencias import catalogo_novo, digest_catalogo, gestor
from tests.test_supabase_mobilidade_escrita import ASSINATURA, CAMINHO, VEICULO_2
from tests.test_supabase_recorrencia import ID, PG_BIN, ROOT, USUARIO_B, cluster, copiar, sql  # noqa: F401
from tests.test_supabase_recorrencia_cartao import falha, gerar_mes, rpc

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

SUPABASE = Path(__file__).resolve().parent.parent / 'supabase'
MIGRATION = SUPABASE / 'migrations' / '20261214090000_financeiro_categorias_consolidacao.sql'
REVERSAO = SUPABASE / 'reversao' / '20261214090000_categorias_consolidacao_anterior.sql'
MOBILIDADE_CC = 964  # Categoria do Cartao "Mobilidade" do Pessoal (ficticia), com limite no contrato 910

PALAVRAS = {
    'tapp': ['99', 'corrida', 'taxi', 'táxi', 'transporte app', 'uber'],
    'mveic': ['autopecas', 'autopeças', 'lavajato', 'mecanica', 'mecânica', 'oficina', 'oleo', 'óleo', 'pneu', 'revisao',
              'revisão'],
    'assin': ['amazon prime', 'assinatura', 'disney', 'mensalidade', 'netflix', 'prime', 'spotify', 'streaming', 'youtube'],
    'soft': ['canva', 'chatgpt', 'claude', 'google workspace', 'inteligencia artificial', 'microsoft', 'openai', 'saas',
             'software', 'supabase'],
}


def chave():
    return str(uuid.uuid4())


def nova_categoria(dsn, nome, palavras=(), **sistemica):
    cid = sql(dsn, "insert into public.categoria (nome, ativo, sistemica, codigo_sistema, modulo_origem, bloquear_edicao, "
                   "bloquear_exclusao) values (%s, true, %s, %s, %s, %s, %s) returning id",
              (nome, bool(sistemica), sistemica.get('codigo'), 'mobilidade' if sistemica else None, bool(sistemica),
               bool(sistemica)))[0]['id']
    for p in palavras:
        sql(dsn, 'insert into public.categoria_palavra_chave (categoria_id, palavra, ativo) values (%s, %s, true)', (cid, p))
    return cid


def vincular(dsn, categoria, cc, perfil=PESSOAL):
    sql(dsn, 'insert into public.categoria_cartao_despesa (categoria_cartao_id, categoria_id, ativo, perfil_financeiro_id) '
             'values (%s, %s, true, %s)', (cc, categoria, perfil))


@pytest.fixture
def cat(banco):  # noqa: F811
    """O catalogo como o da producao (ids proprios do cluster) e o titular ficticio gestor do catalogo NOVO."""
    catalogo_novo(banco)
    c = {r['codigo_sistema']: r['id'] for r in sql(banco, 'select id, codigo_sistema from public.categoria '
                                                          'where codigo_sistema is not null')}
    ids = {'manut': c['MOB_MANUTENCAO'], 'app': c['MOB_APP'], 'pneus': c['MOB_PNEUS'], 'lavagem': c['MOB_LAVAGEM'],
           'assin_veic': c['MOB_ASSINATURA']}
    ids['revisao'] = nova_categoria(banco, 'Revisão', codigo='MOB_REVISAO')
    ids['tapp'] = nova_categoria(banco, 'Transporte por App', PALAVRAS['tapp'])
    ids['mveic'] = nova_categoria(banco, 'Manutenção de Veículo', PALAVRAS['mveic'])
    ids['assin'] = nova_categoria(banco, 'Assinaturas', PALAVRAS['assin'])
    ids['soft'] = nova_categoria(banco, 'Software e IA', PALAVRAS['soft'])
    sql(banco, "insert into public.categoria_cartao (id, nome, ativo, perfil_financeiro_id) values (%s, 'Mobilidade CC', true, %s)",
        (MOBILIDADE_CC, PESSOAL))
    sql(banco, "insert into public.cartao_categoria_limite (id, cartao_id, categoria_cartao_id, limite_mensal, ativo, "
               "perfil_financeiro_id) values (984, %s, %s, '300.00', true, %s)", (CARTAO, MOBILIDADE_CC, PESSOAL))
    for chave_cat in ('tapp', 'mveic'):
        vincular(banco, ids[chave_cat], MOBILIDADE_CC)
    for chave_cat in ('assin', 'soft'):
        vincular(banco, ids[chave_cat], 961)
    return ids


def plano(c):
    """As quatro incorporacoes aprovadas, na ordem de execucao."""
    return [(c['tapp'], c['app'], {}),
            (c['mveic'], c['manut'], {'palavras': {'pneu': c['pneus'], 'lavajato': c['lavagem']}}),
            (c['revisao'], c['manut'], {}),
            (c['assin'], c['soft'], {'renomear_destino': 'Assinaturas'})]


def previa(dsn, origem, destino, opcoes=None, usuario=None):
    return rpc(dsn, 'previa_incorporacao_categoria', origem, destino, opcoes or {}, **({'usuario': usuario} if usuario else {}))


def incorporar(dsn, origem, destino, opcoes=None, p=None, k=None):
    p = p or previa(dsn, origem, destino, opcoes)
    return rpc(dsn, 'incorporar_categoria', origem, destino, opcoes or {}, p['hash'], k or chave())


def erro(funcao, *args, **kw):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args, **kw)
    return e.value


FORA = {'categoria', 'categoria_palavra_chave', 'categoria_cartao_despesa', 'ir_categoria_despesa', 'operacao_catalogo'}


def retrato(dsn):
    """md5 de cada tabela (public e financeiro) sem as colunas que apontam a categoria e sem o proprio catalogo."""
    fks = {}
    for r in sql(dsn, "select t.relname tabela, a.attname coluna from pg_constraint k join pg_class t on t.oid = k.conrelid "
                      "join pg_attribute a on a.attrelid = k.conrelid and a.attnum = k.conkey[1] "
                      "where k.contype = 'f' and k.confrelid = 'public.categoria'::regclass"):
        fks.setdefault(r['tabela'], []).append(r['coluna'])
    saida = {}
    for t in sql(dsn, "select n.nspname esquema, c.relname tabela from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                      "where c.relkind = 'r' and n.nspname in ('public', 'financeiro') order by 1, 2"):
        if t['tabela'] in FORA:
            continue
        menos = ''.join(f" - '{c}'" for c in fks.get(t['tabela'], []))
        saida[f"{t['esquema']}.{t['tabela']}"] = sql(
            dsn, f"select md5(coalesce(string_agg(x, '|' order by x), '')) h from "
                 f"(select (to_jsonb(t){menos})::text x from {t['esquema']}.{t['tabela']} t) z")[0]['h']
    return saida


def palavras_de(dsn, categoria):
    return sorted(r['palavra'] for r in sql(dsn, 'select palavra from public.categoria_palavra_chave where categoria_id = %s',
                                            (categoria,)))


def vinculos_de(dsn, categoria):
    return sorted((r['categoria_cartao_id'], r['ativo']) for r in sql(
        dsn, 'select categoria_cartao_id, ativo from public.categoria_cartao_despesa where categoria_id = %s', (categoria,)))


def existe(dsn, categoria):
    return bool(sql(dsn, 'select 1 from public.categoria where id = %s', (categoria,)))


def neutro(x):
    """Tira as chaves da Categoria de Despesa (id e nome), que a incorporacao muda de proposito."""
    if isinstance(x, dict):
        return {k: neutro(v) for k, v in x.items() if not ('categoria' in k and 'cartao' not in k)}
    if isinstance(x, list):
        return [neutro(v) for v in x]
    return x


def classificar(dsn, *descricoes):
    r = rpc(dsn, 'analisar_importacao_cartao', PESSOAL, CARTAO, MES,
            [linha(n, d, '10.00', categoria=None) for n, d in enumerate(descricoes, 1)])
    return [(x['categoria_id'], x['categoria_cartao_id']) for x in r['linhas']]


# ---------------------------------------------------------------------------------------------------------------------
# 1. As quatro incorporacoes
# ---------------------------------------------------------------------------------------------------------------------

def test_quatro_incorporacoes_preservam_o_banco_e_a_classificacao(banco, cat):  # noqa: F811
    c = cat
    # historico: compras nas categorias de origem (uma fatura paga), recorrencias, previsoes
    comprar(banco, descricao='Uber (ficticio)', valor='32.00', total_parcelas=1, categoria_id=c['tapp'],
            data_compra='2029-04-03', mes_fatura='2029-04-01')
    comprar(banco, descricao='Oficina (ficticia)', valor='150.00', total_parcelas=1, categoria_id=c['mveic'])
    comprar(banco, descricao='Spotify (ficticio)', valor='21.90', total_parcelas=1, categoria_id=c['assin'],
            data_compra='2029-04-05', mes_fatura='2029-04-01')
    pagar(banco, CARTAO, '2029-04-01')
    tv = recorrencia(banco, 'TV por assinatura (ficticia)', '220.00', c['assin'])
    ia = recorrencia(banco, 'Claude (ficticio)', '109.90', c['soft'])
    gerar_mes(banco, '2029-06-01')
    antes = retrato(banco)
    paga = fatura(banco, CARTAO, '2029-04-01')
    descricoes = ('UBER TRIP', 'OFICINA DO ZE', 'PNEU CENTER', 'LAVAJATO CENTRO', 'SPOTIFY', 'CLAUDE AI')
    assert classificar(banco, *descricoes) == [(c['tapp'], MOBILIDADE_CC), (c['mveic'], MOBILIDADE_CC),
                                               (c['mveic'], MOBILIDADE_CC), (c['mveic'], MOBILIDADE_CC),
                                               (c['assin'], 961), (c['soft'], 961)]
    resumos = {m: neutro(rpc(banco, 'fatura_por_categoria', PESSOAL, CARTAO, m)) for m in ('2029-04-01', MES, '2029-06-01')}

    # previa da 98 -> 5: o destino de cada palavra-chave e os vinculos estendidos a Pneus e Lavagem Veicular
    p = previa(banco, *plano(c)[1][:2], plano(c)[1][2])
    assert p['executavel'] and p['bloqueios'] == []
    destino = {x['palavra']: x['destino_id'] for x in p['palavras']}
    assert destino == {**{w: c['manut'] for w in PALAVRAS['mveic']}, 'pneu': c['pneus'], 'lavajato': c['lavagem']}
    assert sorted((x['categoria_id'], x['situacao']) for x in p['vinculos_palavras']) == \
        sorted([(c['pneus'], 'CRIAR'), (c['lavagem'], 'CRIAR')])
    assert [(x['categoria_cartao_id'], x['situacao']) for x in p['vinculos']] == [(MOBILIDADE_CC, 'MOVER')]
    assert {(r['tabela'], r['registros']) for r in p['referencias']} >= {('lancamento_agregado', 1), ('categoria_palavra_chave', 11)}

    resultados = [incorporar(banco, o, d, op) for o, d, op in plano(c)]
    assert [r['destino'] for r in resultados] == ['Transporte por Aplicativo', 'Manutenção Veicular', 'Manutenção Veicular',
                                                 'Assinaturas']
    # IDs definitivos 8, 5 e 100 (aqui, os do cluster): as origens nao existem mais
    assert [existe(banco, c[k]) for k in ('tapp', 'mveic', 'revisao', 'assin')] == [False] * 4
    assert sql(banco, 'select nome from public.categoria where id = %s', (c['soft'],)) == [{'nome': 'Assinaturas'}]
    # palavras-chave: sem duplicar, pneu em Pneus, lavajato em Lavagem Veicular
    assert palavras_de(banco, c['app']) == sorted(PALAVRAS['tapp'])
    assert palavras_de(banco, c['manut']) == sorted(set(PALAVRAS['mveic']) - {'pneu', 'lavajato'})
    assert (palavras_de(banco, c['pneus']), palavras_de(banco, c['lavagem'])) == (['pneu'], ['lavajato'])
    assert palavras_de(banco, c['soft']) == sorted(PALAVRAS['assin'] + PALAVRAS['soft'])
    # Categorias do Cartao: Mobilidade em 5, 8, Pneus e Lavagem; Assinaturas (961) na sobrevivente
    for k in ('app', 'manut', 'pneus', 'lavagem'):
        assert vinculos_de(banco, c[k]) == [(MOBILIDADE_CC, True)], k
    assert vinculos_de(banco, c['soft']) == [(961, True)]
    # nada mais mudou: valores, datas, competencias, pagamentos, faturas, recorrencias, previsoes, limites
    assert retrato(banco) == antes
    assert fatura(banco, CARTAO, '2029-04-01') == paga
    assert {m: neutro(rpc(banco, 'fatura_por_categoria', PESSOAL, CARTAO, m)) for m in resumos} == resumos
    assert sql(banco, 'select categoria_id from public.item_despesa where id in (%s, %s) order by id', (tv, ia)) == \
        [{'categoria_id': c['soft']}, {'categoria_id': c['soft']}]
    # a classificacao automatica continua no mesmo agrupamento da fatura
    assert classificar(banco, *descricoes) == [(c['app'], MOBILIDADE_CC), (c['manut'], MOBILIDADE_CC),
                                               (c['pneus'], MOBILIDADE_CC), (c['lavagem'], MOBILIDADE_CC),
                                               (c['soft'], 961), (c['soft'], 961)]
    # a recorrencia nao gera de novo nem duplica a ocorrencia do mes
    gerar_mes(banco, '2029-06-01')
    assert sql(banco, "select count(*) n from public.lancamento_agregado where item_despesa_id in (%s, %s) "
                      "and mes_fatura = '2029-06-01'", (tv, ia))[0]['n'] == 2
    auditoria = sql(banco, "select resultado from financeiro.operacao_catalogo where operacao = 'incorporar_categoria' "
                           "order by criado_em")
    assert [a['resultado']['origem_id'] for a in auditoria] == [c['tapp'], c['mveic'], c['revisao'], c['assin']]
    assert auditoria[0]['resultado']['fotos']['origem']['nome'] == 'Transporte por App'


def test_duplicidades_unidas_e_execucao_repetida(banco, cat):  # noqa: F811
    c = cat
    sql(banco, "insert into public.categoria_palavra_chave (categoria_id, palavra, ativo) values (%s, 'oficina', false)",
        (c['manut'],))
    vincular(banco, c['manut'], MOBILIDADE_CC)
    sql(banco, 'update public.categoria_cartao_despesa set ativo = false where categoria_id = %s', (c['manut'],))
    p = previa(banco, c['mveic'], c['manut'])
    assert {x['palavra']: x['situacao'] for x in p['palavras']}['oficina'] == 'JA_NO_DESTINO'
    assert [x['situacao'] for x in p['vinculos']] == ['JA_NO_DESTINO']
    k = chave()
    r = incorporar(banco, c['mveic'], c['manut'], p=p, k=k)
    assert {x['palavra']: x['acao'] for x in r['palavras']}['oficina'] == 'UNIDA'
    assert sql(banco, "select ativo from public.categoria_palavra_chave where categoria_id = %s and palavra = 'oficina'",
               (c['manut'],)) == [{'ativo': True}]
    assert vinculos_de(banco, c['manut']) == [(MOBILIDADE_CC, True)]  # um so, reativado
    # repetida: pela mesma chave e por outra chave, o mesmo resultado sem alterar nada; para outro destino, recusada
    depois = (retrato(banco), digest_catalogo(banco))
    assert incorporar(banco, c['mveic'], c['manut'], p=p, k=k)['repetida'] is True
    assert rpc(banco, 'incorporar_categoria', c['mveic'], c['manut'], {}, 'x', chave())['repetida'] is True
    e = erro(rpc, banco, 'incorporar_categoria', c['mveic'], c['app'], {}, 'x', chave())
    assert e.diag.message_hint == 'JA_INCORPORADA'
    assert (retrato(banco), digest_catalogo(banco)) == depois
    assert sql(banco, "select count(*) n from financeiro.operacao_catalogo where operacao = 'incorporar_categoria'")[0]['n'] == 1


def test_bloqueios_previa_mudada_e_falha_com_rollback(banco, cat):  # noqa: F811
    c = cat
    antes = (retrato(banco), digest_catalogo(banco))
    # sistemica ainda obrigatoria, destino sistemico renomeado, nome em uso, palavra de outra categoria
    p = previa(banco, c['lavagem'], c['manut'])
    assert [b['codigo'] for b in p['bloqueios']] == ['SISTEMICA_OBRIGATORIA'] and not p['executavel']
    assert erro(incorporar, banco, c['lavagem'], c['manut'], p=p).diag.message_hint == 'SISTEMICA_OBRIGATORIA'
    assert [b['codigo'] for b in previa(banco, c['tapp'], c['app'], {'renomear_destino': 'App'})['bloqueios']] == \
        ['DESTINO_SISTEMICO']
    assert [b['codigo'] for b in previa(banco, c['assin'], c['soft'], {'renomear_destino': 'Transporte por App'})['bloqueios']] == \
        ['NOME_EM_USO']
    assert [b['codigo'] for b in previa(banco, c['mveic'], c['manut'], {'palavras': {'uber': c['pneus']}})['bloqueios']] == \
        ['PALAVRA_INVALIDA']
    # vinculo conflitante: Transporte por Aplicativo ja numa outra Categoria do Cartao
    vincular(banco, c['app'], 961)
    p = previa(banco, c['tapp'], c['app'])
    assert [b['codigo'] for b in p['bloqueios']] == ['VINCULO_CONFLITANTE']
    sql(banco, 'delete from public.categoria_cartao_despesa where categoria_id = %s', (c['app'],))
    # previa que mudou desde a conferencia
    p = previa(banco, c['assin'], c['soft'], {'renomear_destino': 'Assinaturas'})
    comprar(banco, descricao='Disney (ficticio)', valor='33.90', total_parcelas=1, categoria_id=c['assin'])
    assert erro(incorporar, banco, c['assin'], c['soft'], {'renomear_destino': 'Assinaturas'}, p=p).pgcode == '40001'
    # falha no meio (gatilho de teste na recorrencia): tudo desfeito
    recorrencia(banco, 'TV por assinatura (ficticia)', '220.00', c['assin'])
    sql(banco, "create function public.falha_simulada() returns trigger language plpgsql as $$ begin "
               "raise exception 'falha simulada'; end $$")
    sql(banco, 'create trigger falha_simulada before update of categoria_id on public.item_despesa '
               'for each row execute function public.falha_simulada()')
    meio = (retrato(banco), digest_catalogo(banco), palavras_de(banco, c['assin']), vinculos_de(banco, c['assin']))
    assert 'falha simulada' in str(erro(incorporar, banco, c['assin'], c['soft'], {'renomear_destino': 'Assinaturas'}))
    assert (retrato(banco), digest_catalogo(banco), palavras_de(banco, c['assin']), vinculos_de(banco, c['assin'])) == meio
    assert sql(banco, 'select count(*) n from financeiro.operacao_catalogo')[0]['n'] == 0
    assert antes[0] != meio[0]  # a compra e a recorrencia de teste entraram antes da falha


def test_permissoes_e_perfis(banco, cat, cluster):  # noqa: F811
    c = cat
    assert erro(previa, banco, c['tapp'], c['app'], usuario=USUARIO_B).pgcode == '42501'
    assert erro(rpc, banco, 'incorporar_categoria', c['tapp'], c['app'], {}, 'x', chave(), usuario=USUARIO_B).pgcode == '42501'
    # registro de outro perfil (Perfil B, do usuario B) na categoria de origem: recusada, nada alterado
    sql(banco, "insert into public.item_despesa (nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente) "
               "values ('Do Perfil B (ficticio)', 'Simples', %s, %s, true, false)", (ID['PERFIL_B'], c['tapp']))
    p = previa(banco, c['tapp'], c['app'])
    assert [b['codigo'] for b in p['bloqueios']] == ['PERFIL_SEM_ACESSO']
    antes = (retrato(banco), digest_catalogo(banco))
    assert erro(incorporar, banco, c['tapp'], c['app'], p=p).pgcode == '42501'
    assert (retrato(banco), digest_catalogo(banco)) == antes
    # catalogo ainda no Flask: recusada
    limpo = copiar(cluster)
    gestor(limpo)
    cid = nova_categoria(limpo, 'Origem (ficticia)')
    destino = nova_categoria(limpo, 'Destino (ficticio)')
    e = erro(rpc, limpo, 'incorporar_categoria', cid, destino, {}, 'x', chave())
    assert e.diag.message_hint == 'CATALOGO_FLASK'


# ---------------------------------------------------------------------------------------------------------------------
# 2. Mobilidade
# ---------------------------------------------------------------------------------------------------------------------

def test_revisao_usa_manutencao_e_legado_incorporado_sem_duplicar(banco, cat):  # noqa: F811
    c = cat
    assert {r['codigo'] for r in sql(banco, 'select codigo from financeiro.categorias_sistemicas_mobilidade()')} == {
        'MOB_COMBUSTIVEL', 'MOB_SEGURO_VEICULAR', 'MOB_TRIBUTOS_VEICULARES', 'MOB_MANUTENCAO', 'MOB_PNEUS',
        'MOB_USO_VEICULO', 'MOB_APP', 'MOB_ASSINATURA', 'MOB_LAVAGEM'}
    # com preco do combustivel o km do mes e estimado e a revisao por km entra nas previstas
    v = rpc(banco, 'criar_veiculo', PESSOAL, {**VEICULO_2, 'preco_medio_combustivel': 6}, chave())['veiculo_id']
    regra = rpc(banco, 'criar_regra_km_veiculo', PESSOAL, v, {'tipo_evento': 'REVISAO', 'intervalo_km': 10000,
                                                               'custo_estimado': 500, 'meses_intervalo': 12}, chave())['regra_id']
    rpc(banco, 'gerar_manutencao_km_veiculo', PESSOAL, v, {'regra_id': regra})
    revisoes = "from public.despesa_prevista where origem_id = %s and metadata::jsonb ->> 'tipo_evento' = 'REVISAO'"
    assert {r['categoria_id'] for r in sql(banco, 'select categoria_id ' + revisoes, (v,))} == {c['manut']}
    assert sql(banco, 'select categoria_id from public.veiculo_regra_manutencao_km where id = %s', (regra,)) == \
        [{'categoria_id': c['manut']}]
    # legado do Flask: a regra e as previstas na "Revisao" (MOB_REVISAO); incorporada, tudo em Manutencao Veicular
    sql(banco, 'update public.veiculo_regra_manutencao_km set categoria_id = %s where id = %s', (c['revisao'], regra))
    sql(banco, 'update public.despesa_prevista set categoria_id = %s where origem_id = %s', (c['revisao'], v))
    previstas = sql(banco, "select id, valor_previsto, data_prevista, status, metadata " + revisoes + ' order by id', (v,))
    antes = retrato(banco)
    incorporar(banco, c['revisao'], c['manut'])
    assert retrato(banco) == antes and not existe(banco, c['revisao'])
    assert sql(banco, "select id, valor_previsto, data_prevista, status, metadata " + revisoes + ' order by id', (v,)) == previstas
    assert {r['categoria_id'] for r in sql(banco, 'select categoria_id ' + revisoes, (v,))} == {c['manut']}
    rpc(banco, 'gerar_manutencao_km_veiculo', PESSOAL, v, {'regra_id': regra})
    assert sql(banco, "select count(*) n " + revisoes + " and status = 'PREVISTA'", (v,))[0]['n'] == \
        sum(1 for x in previstas if x['status'] == 'PREVISTA')
    # a "Revisao" nao e recriada pelas projecoes do veiculo
    rpc(banco, 'gerar_projecoes_veiculo', PESSOAL, v, {})
    assert sql(banco, "select count(*) n from public.categoria where codigo_sistema = 'MOB_REVISAO' or nome = 'Revisão'")[0]['n'] == 0


def test_cenario_efetivado_alterado_e_trocado_depois_da_consolidacao(banco, cat):  # noqa: F811
    c = cat
    caminho = rpc(banco, 'criar_caminho_app', PESSOAL, CAMINHO, chave())['id']
    r = rpc(banco, 'ativar_mobilidade', PESSOAL, {'tipo_modalidade': 'TRANSPORTE_APP', 'origem_id': caminho,
                                                  'meio_pagamento': 'pix', 'confirmado': True}, chave())
    item = r['recorrencia']['id']
    mob = 'select id, categoria_id, valor_previsto, data_prevista, status from public.despesa_prevista where origem_tipo = %s order by id'
    previstas = sql(banco, mob, ('TRANSPORTE_APP',))
    assert previstas and {x['categoria_id'] for x in previstas} == {c['app']}
    comprar(banco, descricao='Uber (ficticio)', valor='32.00', total_parcelas=1, categoria_id=c['tapp'])
    for o, d, op in plano(c):
        incorporar(banco, o, d, op)
    assert sql(banco, mob, ('TRANSPORTE_APP',)) == previstas  # o cenario efetivado nao muda
    assert sql(banco, 'select categoria_id, ativo from public.item_despesa where id = %s', (item,)) == \
        [{'categoria_id': c['app'], 'ativo': True}]
    # alteracao do caminho: as projecoes sao refeitas (as suprimidas pela recorrencia ativa bloqueiam a competencia) na
    # mesma categoria, uma por competencia
    rpc(banco, 'editar_caminho_app', PESSOAL, caminho, {**CAMINHO, 'km_mensal_estimado': 400})
    depois = sql(banco, mob, ('TRANSPORTE_APP',))
    assert len(depois) == len(previstas) and {x['categoria_id'] for x in depois} == {c['app']}
    assert len({x['data_prevista'] for x in depois}) == len(depois)
    # troca de modalidade (cancela a anterior): a recorrencia do app fica inativa, a nova na categoria sistemica
    ass = rpc(banco, 'criar_assinatura_mobilidade', PESSOAL, ASSINATURA, chave())['assinatura_id']
    r2 = rpc(banco, 'ativar_mobilidade', PESSOAL, {'tipo_modalidade': 'ASSINATURA', 'origem_id': ass, 'meio_pagamento': 'pix',
                                                   'confirmado': True}, chave())
    assert sql(banco, 'select ativo from public.item_despesa where id = %s', (item,)) == [{'ativo': False}]
    assert sql(banco, 'select categoria_id from public.item_despesa where id = %s', (r2['recorrencia']['id'],)) == \
        [{'categoria_id': c['assin_veic']}]
    eliminadas = [c[k] for k in ('tapp', 'mveic', 'revisao', 'assin')]
    # todas as tabelas que apontam a categoria, em qualquer esquema (FIN-MVP-MOB-02: financeiro.veiculo_projecao)
    for r in sql(banco, 'select n.nspname esquema, t.relname tabela, a.attname coluna from pg_constraint k '
                        'join pg_class t on t.oid = k.conrelid join pg_namespace n on n.oid = t.relnamespace '
                        "join pg_attribute a on a.attrelid = k.conrelid and a.attnum = k.conkey[1] "
                        "where k.contype = 'f' and k.confrelid = 'public.categoria'::regclass"):
        assert sql(banco, f"select count(*) n from {r['esquema']}.{r['tabela']} where {r['coluna']} = any(%s)", (eliminadas,))[0]['n'] == 0


SCRIPT_FLASK = """
import json
from backend.app import create_app
from backend.models import db
app = create_app('local')
saida = {}
with app.app_context():
    from backend.services import categoria_default as cd
    for nome, f in (('manutencao', lambda: cd.obter_categoria_sistemica_id('MOB_MANUTENCAO')),
                    ('revisao_evento', lambda: cd.categoria_sistemica_mobilidade_id_para_tipo_evento('REVISAO_PROGRAMADA')),
                    ('revisao_codigo', lambda: cd.obter_categoria_sistemica_id('MOB_REVISAO')),
                    ('lavagem', lambda: cd.obter_categoria_sistemica_id('MOB_LAVAGEM')),
                    ('garantir', lambda: len(cd.garantir_categorias_sistemicas_mobilidade()))):
        try:
            saida[nome] = f()
            db.session.commit()  # o que o helper gravasse ficaria no banco
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            saida[nome] = 'ERRO ' + type(e).__name__
print('FLASK_JSON ' + json.dumps(saida))
"""


def helper_flask(dsn):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', SCRIPT_FLASK], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    linha_json = next((x for x in r.stdout.splitlines() if x.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha_json, r.stderr[-3000:]
    return json.loads(linha_json[len('FLASK_JSON '):])


def test_flask_nao_recria_nem_reescreve_categorias(banco, cat, cluster):  # noqa: F811
    c = cat
    incorporar(banco, c['revisao'], c['manut'])
    sql(banco, "update public.categoria set descricao = 'legado' where id = %s", (c['manut'],))
    sql(banco, 'delete from public.categoria where id = %s', (c['lavagem'],))  # sistemica ausente (sem registros)
    antes = digest_catalogo(banco)
    r = helper_flask(banco)
    assert r == {'manutencao': c['manut'], 'revisao_evento': c['manut'], 'revisao_codigo': 'ERRO ValueError',
                 'lavagem': 'ERRO CategoriaSistemicaAusente', 'garantir': 'ERRO CategoriaSistemicaAusente'}
    assert digest_catalogo(banco) == antes  # nada criado, promovido ou reescrito com o catalogo no novo aplicativo
    # catalogo no Flask (legado): o helper cria as 9, nunca a "Revisao"
    limpo = copiar(cluster)
    assert helper_flask(limpo)['garantir'] == 9
    assert sql(limpo, "select count(*) n from public.categoria where codigo_sistema = 'MOB_REVISAO' or nome = 'Revisão'")[0]['n'] == 0


# ---------------------------------------------------------------------------------------------------------------------
# 3. Limpeza seletiva e reimportacao dos cartoes
# ---------------------------------------------------------------------------------------------------------------------

def _compras(dsn):
    return sql(dsn, 'select descricao, valor, categoria_id from public.lancamento_agregado where is_importado and cartao_id = %s '
                    'and mes_fatura = %s order by descricao', (CARTAO, MES))


def test_cenario_a_reconstrucao_concluida_e_a_janela_proibida(banco, cat):  # noqa: F811
    c = cat
    linhas = [linha(1, 'OFICINA DO ZE', '150.00', categoria=c['mveic']), linha(2, 'SPOTIFY', '21.90', categoria=c['assin'])]
    importar(banco, *linhas)
    limpar(banco, limpeza(banco))
    # entre a limpeza e a reimportacao: proibido consolidar
    p = previa(banco, c['mveic'], c['manut'])
    assert [b['codigo'] for b in p['bloqueios']] == ['RECONSTRUCAO_PENDENTE']
    assert p['reconstrucao_pendente'][0]['competencia'] == MES[:7]
    assert erro(incorporar, banco, c['mveic'], c['manut'], p=p).diag.message_hint == 'RECONSTRUCAO_PENDENTE'
    assert existe(banco, c['mveic'])
    # reimportada (com a categoria da foto da limpeza), a consolidacao segue
    importar(banco, *[{k: v for k, v in x.items() if k != 'categoria_id'} for x in linhas])
    assert _compras(banco) == [{'descricao': 'OFICINA DO ZE', 'valor': Decimal('150.00'), 'categoria_id': c['mveic']},
                               {'descricao': 'SPOTIFY', 'valor': Decimal('21.90'), 'categoria_id': c['assin']}]
    for o, d, op in plano(c):
        incorporar(banco, o, d, op)
    assert _compras(banco) == [{'descricao': 'OFICINA DO ZE', 'valor': Decimal('150.00'), 'categoria_id': c['manut']},
                               {'descricao': 'SPOTIFY', 'valor': Decimal('21.90'), 'categoria_id': c['soft']}]


def test_cenario_b_consolidacao_antes_da_limpeza(banco, cat):  # noqa: F811
    c = cat
    linhas = [linha(1, 'OFICINA DO ZE', '150.00', categoria=c['mveic']), linha(2, 'SPOTIFY', '21.90', categoria=c['assin'])]
    importar(banco, *linhas)
    for o, d, op in plano(c):
        incorporar(banco, o, d, op)
    limpar(banco, limpeza(banco))
    r = importar(banco, *[{k: v for k, v in x.items() if k != 'categoria_id'} for x in linhas])
    assert r['inseridos'] == 2
    # a reconstrucao usa os IDs sobreviventes da foto da limpeza: nenhuma referencia eliminada volta
    assert _compras(banco) == [{'descricao': 'OFICINA DO ZE', 'valor': Decimal('150.00'), 'categoria_id': c['manut']},
                               {'descricao': 'SPOTIFY', 'valor': Decimal('21.90'), 'categoria_id': c['soft']}]
    assert [existe(banco, c[k]) for k in ('mveic', 'assin')] == [False, False]


# ---------------------------------------------------------------------------------------------------------------------
# 4. Reversao
# ---------------------------------------------------------------------------------------------------------------------

def executar_arquivo(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_reversao_recusada_apos_incorporar_e_reaplicacao(banco, cat, cluster):  # noqa: F811
    c = cat
    incorporar(banco, c['tapp'], c['app'])
    assert 'incorporadas' in str(erro(executar_arquivo, banco, REVERSAO))
    limpo = copiar(cluster)
    executar_arquivo(limpo, REVERSAO)
    assert 'MOB_REVISAO' in {r['codigo'] for r in sql(limpo, 'select codigo from financeiro.categorias_sistemicas_mobilidade()')}
    definicao = sql(limpo, "select pg_get_functiondef('financeiro.mob_categoria_evento(text)'::regprocedure) d")[0]['d']
    assert "when 'REVISAO' then 'MOB_REVISAO'" in definicao
    assert sql(limpo, "select to_regprocedure('financeiro.incorporar_categoria(integer, integer, jsonb, text, uuid)') f")[0]['f'] is None
    executar_arquivo(limpo, MIGRATION)
    assert len(sql(limpo, 'select codigo from financeiro.categorias_sistemicas_mobilidade()')) == 9
    assert sql(limpo, "select to_regprocedure('financeiro.incorporar_categoria(integer, integer, jsonb, text, uuid)') f")[0]['f']


def test_privilegios(banco):  # noqa: F811
    linhas = {r['n']: (r['a'], r['x']) for r in sql(banco, """
        select p.proname n, has_function_privilege('authenticated', p.oid, 'EXECUTE') a,
               has_function_privilege('anon', p.oid, 'EXECUTE') x, p.prosecdef d
          from pg_proc p join pg_namespace s on s.oid = p.pronamespace
         where s.nspname = 'financeiro' and p.proname in ('referencias_categoria', 'previa_incorporacao_categoria',
                                                          'incorporar_categoria')""")}
    assert linhas == {'referencias_categoria': (False, False), 'previa_incorporacao_categoria': (True, False),
                      'incorporar_categoria': (True, False)}
    assert falha(banco, 'incorporar_categoria', 1, 2, {}, 'x', None)[0] in ('42501', 'P0001', '22023')
