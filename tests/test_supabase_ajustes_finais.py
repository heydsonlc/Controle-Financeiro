"""
Testes FIN-MULTIUSUARIO-AJUSTES-FINAIS-01 (na migration 20270101090000) — acao "Alterar categoria" das palavras-chave, em
cluster PostgreSQL local descartavel e com dados ficticios.

Conferido: reassociacao de palavra padrao e de palavra propria; restauracao da associacao padrao; categoria particular como
destino; bloqueio da categoria e do ajuste de outro usuario; a configuracao do outro usuario nao muda; as sugestoes de
classificacao acompanham; despesas e compras ja classificadas nao mudam; repetir nao duplica. (A recusa a conta sem acesso
liberado e conferida pela sonda permanente de tests/test_supabase_acesso.py, que chama toda funcao exposta.)
"""
import uuid

import pytest

from tests.test_supabase_cadastros_padrao import c, digest, palavra_padrao, palavras, sugestao  # noqa: F401
from tests.test_supabase_cartoes import ASSINATURAS, MORADIA, banco, comprar, rpc  # noqa: F401
from tests.test_supabase_categorias_recorrencias import erro
from tests.test_supabase_integracao_1123_1126 import resumo_tabelas
from tests.test_supabase_recorrencia import PG_BIN, USUARIO_A, USUARIO_B, atribuir, cluster, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')
chave = lambda: str(uuid.uuid4())  # noqa: E731


def alterar(dsn, usuario, palavra_id, categoria):
    return rpc(dsn, 'alterar_categoria_da_palavra_chave', palavra_id, categoria, usuario=usuario)


def ajustes(dsn):
    return sql(dsn, 'select user_id::text u, tipo, palavra, categoria_id, categoria_padrao_id from financeiro.palavra_chave_usuario order by id')


def test_palavra_padrao_muda_de_categoria_so_para_o_usuario_e_restaura(c):  # noqa: F811
    dsn, pa, pb = c['dsn'], c['pa'], c['pb']
    pid = palavra_padrao(dsn, MORADIA, 'streaming qualquer')
    catalogo = digest(dsn)
    assert sugestao(dsn, pb, 'STREAMING QUALQUER 123')['categoria_id'] == MORADIA
    r = alterar(dsn, USUARIO_B, pid, ASSINATURAS)
    assert (r['origem'], r['categoria_id'], r['categoria_padrao_id'], r['alterada']) == ('REASSOCIADA', ASSINATURAS, MORADIA, True) and r['id'] < 0
    # o catalogo padrao nao muda; so existe o ajuste de B
    depois = digest(dsn)
    assert {k: v for k, v in depois.items() if k != 'ajustes'} == {k: v for k, v in catalogo.items() if k != 'ajustes'} and depois['ajustes'] == catalogo['ajustes'] + 1
    # para B: vale na nova categoria (marcada como reassociada, com a origem) e aparece como MOVIDA na de origem
    em_destino = palavras(dsn, USUARIO_B, pb, ASSINATURAS)['streaming qualquer']
    assert (em_destino['origem'], em_destino['ativo'], em_destino['categoria_padrao_id'], em_destino['id']) == ('REASSOCIADA', True, MORADIA, r['id'])
    em_origem = palavras(dsn, USUARIO_B, pb, MORADIA)['streaming qualquer']
    assert (em_origem['origem'], em_origem['ativo'], em_origem['categoria_destino_id'], em_origem['id']) == ('MOVIDA', False, ASSINATURAS, r['id'])
    assert sugestao(dsn, pb, 'STREAMING QUALQUER 123')['categoria_id'] == ASSINATURAS  # a sugestao acompanha
    # para A: nada mudou
    assert palavras(dsn, USUARIO_A, pa, MORADIA)['streaming qualquer']['origem'] == 'PADRAO'
    assert 'streaming qualquer' not in palavras(dsn, USUARIO_A, pa, ASSINATURAS)
    assert sugestao(dsn, pa, 'STREAMING QUALQUER 123')['categoria_id'] == MORADIA
    # repetir (pelo id padrao ou pelo id do ajuste) nao duplica nem falha
    for pid_repetido in (pid, r['id']):
        rep = alterar(dsn, USUARIO_B, pid_repetido, ASSINATURAS)
        assert (rep['alterada'], rep['id'], rep['categoria_id']) == (False, r['id'], ASSINATURAS)
    assert digest(dsn) == depois
    # restaurar: voltar a categoria de origem remove o ajuste
    volta = alterar(dsn, USUARIO_B, r['id'], MORADIA)
    assert (volta['origem'], volta['restaurada'], volta['id'], volta['categoria_id']) == ('PADRAO', True, pid, MORADIA)
    assert digest(dsn) == catalogo and ajustes(dsn) == []
    assert palavras(dsn, USUARIO_B, pb, MORADIA)['streaming qualquer']['origem'] == 'PADRAO'
    assert sugestao(dsn, pb, 'STREAMING QUALQUER 123')['categoria_id'] == MORADIA
    # a outra forma de restaurar (remover o ajuste) continua valendo
    r2 = alterar(dsn, USUARIO_B, pid, ASSINATURAS)
    assert rpc(dsn, 'remover_minha_palavra_chave', -r2['id'], usuario=USUARIO_B)['volta_ao_padrao'] is True
    assert digest(dsn) == catalogo


def test_palavra_propria_muda_de_categoria_inclusive_para_categoria_particular(c):  # noqa: F811
    dsn, pb = c['dsn'], c['pb']
    pets_b = rpc(dsn, 'criar_categoria', {'nome': 'Pets'}, chave(), usuario=USUARIO_B)['categoria_id']
    pets_a = rpc(dsn, 'criar_categoria', {'nome': 'Pets'}, chave(), usuario=USUARIO_A)['categoria_id']
    propria = rpc(dsn, 'criar_minha_palavra_chave', MORADIA, 'banho e tosa', usuario=USUARIO_B)
    r = alterar(dsn, USUARIO_B, propria['id'], pets_b)
    assert (r['origem'], r['categoria_id'], r['alterada'], r['id']) == ('PROPRIA', pets_b, True, propria['id'])
    assert 'banho e tosa' not in palavras(dsn, USUARIO_B, pb, MORADIA) and palavras(dsn, USUARIO_B, pb, pets_b)['banho e tosa']['origem'] == 'PROPRIA'
    assert sugestao(dsn, pb, 'BANHO E TOSA DO REX')['categoria_id'] == pets_b
    assert [(a['tipo'], a['categoria_id'], a['categoria_padrao_id']) for a in ajustes(dsn)] == [('NOVA', pets_b, None)]
    assert alterar(dsn, USUARIO_B, propria['id'], pets_b)['alterada'] is False  # repetir
    assert len(ajustes(dsn)) == 1
    # palavra PADRAO tambem pode ir para a categoria particular do usuario
    pid = palavra_padrao(dsn, MORADIA, 'racao premium')
    r = alterar(dsn, USUARIO_B, pid, pets_b)
    assert (r['origem'], r['categoria_id']) == ('REASSOCIADA', pets_b) and sugestao(dsn, pb, 'RACAO PREMIUM 10KG')['categoria_id'] == pets_b
    # ... e a de A segue no padrao
    assert sugestao(dsn, c['pa'], 'RACAO PREMIUM 10KG')['categoria_id'] == MORADIA
    # categoria particular de OUTRO usuario como destino: responde como inexistente, nada gravado
    antes = ajustes(dsn)
    for palavra_id in (propria['id'], pid, r['id']):
        for destino in (pets_a, 999999):
            e = erro(alterar, dsn, USUARIO_B, palavra_id, destino)
            assert (e.pgcode, e.diag.message_hint, e.diag.message_primary) == ('P0001', 'NAO_ENCONTRADA', 'Categoria de Despesa nao encontrada')
    assert ajustes(dsn) == antes


def test_ajuste_de_outro_usuario_nao_e_alterado_e_duplicidade_e_recusada(c):  # noqa: F811
    dsn, pa, pb = c['dsn'], c['pa'], c['pb']
    de_b = rpc(dsn, 'criar_minha_palavra_chave', MORADIA, 'so do b', usuario=USUARIO_B)
    antes = ajustes(dsn)
    # A nao altera a palavra de B (nem a distingue de uma inexistente)
    for alvo in (de_b['id'], -987654321):
        e = erro(alterar, dsn, USUARIO_A, alvo, ASSINATURAS)
        assert (e.pgcode, e.diag.message_hint, e.diag.message_primary) == ('P0001', 'NAO_ENCONTRADA', 'Palavra-chave nao encontrada')
    assert ajustes(dsn) == antes and palavras(dsn, USUARIO_B, pb, MORADIA)['so do b']['origem'] == 'PROPRIA'
    assert erro(alterar, dsn, USUARIO_A, 0, ASSINATURAS).diag.message_hint == 'NAO_ENCONTRADA'
    # duplicidade: a categoria de destino ja tem a mesma palavra para o usuario
    rpc(dsn, 'criar_minha_palavra_chave', ASSINATURAS, 'so do b', usuario=USUARIO_B)
    assert erro(alterar, dsn, USUARIO_B, de_b['id'], ASSINATURAS).diag.message_hint == 'JA_EXISTE'
    em_moradia, em_assinaturas = palavra_padrao(dsn, MORADIA, 'duplicada'), palavra_padrao(dsn, ASSINATURAS, 'duplicada')
    assert erro(alterar, dsn, USUARIO_B, em_moradia, ASSINATURAS).diag.message_hint == 'JA_EXISTE'
    assert em_assinaturas and len(ajustes(dsn)) == 2
    # palavra desligada pode ser levada a outra categoria (passa a reassociada) e restaurada
    pid = palavra_padrao(dsn, MORADIA, 'desligada antes')
    rpc(dsn, 'desligar_palavra_chave_padrao', pid, usuario=USUARIO_B)
    r = alterar(dsn, USUARIO_B, pid, ASSINATURAS)
    assert r['origem'] == 'REASSOCIADA' and palavras(dsn, USUARIO_B, pb, ASSINATURAS)['desligada antes']['ativo'] is True
    assert alterar(dsn, USUARIO_B, pid, MORADIA)['restaurada'] is True
    assert palavras(dsn, USUARIO_A, pa, MORADIA)['desligada antes']['origem'] == 'PADRAO'


def test_alterar_categoria_nao_reclassifica_nada_e_exige_o_catalogo_no_novo_aplicativo(c):  # noqa: F811
    dsn, pb = c['dsn'], c['pb']
    atribuir(dsn, pb)
    conta = rpc(dsn, 'criar_conta_bancaria', pb, {'nome': 'Conta', 'instituicao': 'Banco', 'tipo': 'Conta Corrente', 'saldo_inicial': 500}, chave(), usuario=USUARIO_B)
    conta_id = conta['id'] if 'id' in conta else conta['conta_bancaria']['id']
    rpc(dsn, 'criar_despesa_paga', pb, {'nome': 'Despesa ja classificada', 'valor': '50.00', 'categoria_id': MORADIA, 'data_vencimento': '2027-03-10'},
        {'conta_bancaria_id': conta_id, 'data_pagamento': '2027-03-10'}, chave(), usuario=USUARIO_B)
    pid = palavra_padrao(dsn, MORADIA, 'ja classificada')
    financeiro = resumo_tabelas(dsn)
    alterar(dsn, USUARIO_B, pid, ASSINATURAS)
    depois = resumo_tabelas(dsn)
    assert {t for t in depois if depois[t] != financeiro[t]} == {'financeiro.palavra_chave_usuario'}  # nenhuma despesa, compra, saldo ou movimento
    # catalogo no sistema anterior: nada do catalogo e gravado, nem o que e do usuario
    sql(dsn, "update financeiro.catalogo_categorias set escritor = 'FLASK'")
    assert erro(alterar, dsn, USUARIO_B, pid, MORADIA).diag.message_hint == 'CATALOGO_FLASK'
    agora = resumo_tabelas(dsn)
    assert {t for t in agora if agora[t] != depois[t]} == {'financeiro.catalogo_categorias'}  # so a troca de escritor feita pelo teste
    # sem sessao: a funcao nao e executavel
    assert sql(dsn, "select has_function_privilege('anon', 'financeiro.alterar_categoria_da_palavra_chave(bigint, integer)', 'execute') p")[0]['p'] is False


def test_categoria_particular_de_outro_usuario_no_vinculo_do_cartao_responde_como_inexistente(c):  # noqa: F811
    dsn, pb = c['dsn'], c['pb']
    atribuir(dsn, pb)
    pets_a = rpc(dsn, 'criar_categoria', {'nome': 'Pets'}, chave(), usuario=USUARIO_A)['categoria_id']
    cc = rpc(dsn, 'criar_categoria_cartao', pb, {'nome': 'Animais'}, usuario=USUARIO_B)
    cc_id = cc.get('id') or cc.get('categoria_cartao_id') or cc['categoria']['id']
    respostas = set()
    for categoria in (pets_a, 999999):
        e = erro(rpc, dsn, 'vincular_despesa_categoria_cartao', pb, cc_id, categoria, True, usuario=USUARIO_B)
        respostas.add((e.pgcode, e.diag.message_primary, e.diag.message_hint))
    assert len(respostas) == 1, respostas  # identica: a particular de outro usuario nao e distinguida de uma inexistente
    assert rpc(dsn, 'vincular_despesa_categoria_cartao', pb, cc_id, MORADIA, True, usuario=USUARIO_B)  # a padrao continua valendo
