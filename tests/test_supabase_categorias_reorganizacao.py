"""
Testes FIN-CATEGORIAS-REORGANIZACAO-01 (migration 20261229090000), em cluster local descartavel com cenario FICTICIO:
um catalogo como o da producao (Outros com "outros"/"diversos", Servicos gerais com oito palavras genericas, Manutencao
residencial, Servicos domesticos, Assinaturas, Entretenimento), um financiamento sem categoria com contas pagas e
futuras, recorrencias em Outros, dois consorcios vigentes e um inativo em Outros, compras de cartao em Outros (inclusive
duas de "ajuste" que NAO podem mudar).
- reclassificacao por manifesto: so a coluna da categoria muda (o resto do banco fica identico), as contas herdam;
  previa com hash, previa mudada, bloqueios, falha com rollback, execucao repetida, inversa e inversa repetida;
- permissoes: so quem administra o catalogo e gere o perfil; perfil no Flask recusado;
- natureza gerencial: CONSUMO por omissao, definicao auditada, indicadores do mes iguais ao total do Dashboard (sem dupla
  contagem) e a posicao dos consorcios de aporte (retorno de capital x ganho);
- importacao: Outros (NAO_DEFINIDO) nao se propaga pelo historico; palavra-chave tem prioridade; escolha especifica vale;
- o roteiro completo (scripts/reorganizar_categorias.py) com as excecoes intactas, e a reversao da migration.
"""
import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartao_despesas_fixas import PESSOAL, banco  # noqa: F401
from tests.test_supabase_cartoes import CARTAO, comprar
from tests.test_supabase_categorias_consolidacao import executar_arquivo, incorporar, nova_categoria, retrato
from tests.test_supabase_categorias_recorrencias import catalogo_novo
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, USUARIO_B, cluster, copiar, sql  # noqa: F401
from tests.test_supabase_recorrencia_cartao import chamar, falha, rpc

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

SUPABASE = Path(__file__).resolve().parent.parent / 'supabase'
MIGRATION = SUPABASE / 'migrations' / '20261229090000_financeiro_categorias_reorganizacao.sql'
REVERSAO = SUPABASE / 'reversao' / '20261229090000_categorias_reorganizacao_anterior.sql'
EMPRESA = ID['EMPRESA']
MES = '2031-03-01'


def chave():
    return str(uuid.uuid4())


def item(dsn, nome, categoria, contas, tipo='Simples', perfil=PESSOAL, valor='100.00', recorrente=False):
    """Item de despesa com contas (competencia, situacao): o que a tela e os geradores gravam, direto na tabela."""
    iid = sql(dsn, "insert into public.item_despesa (perfil_financeiro_id, nome, descricao, valor, data_vencimento, categoria_id, "
                   "pago, recorrente, tipo, tipo_recorrencia, ativo, criado_em) values (%s, %s, '', %s, '2031-01-10', %s, false, %s, %s, "
                   "'mensal', true, now()) returning id", (perfil, nome, valor, categoria, recorrente, tipo))[0]['id']
    for mes, situacao in contas:
        sql(dsn, "insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, data_vencimento, "
                 "data_pagamento, status_pagamento, debito_automatico, is_fatura_cartao, estouro_orcamento, status_fatura) "
                 "values (%s, %s, %s, %s, %s, %s, %s, %s, false, false, false, 'ABERTA')",
            (perfil, iid, mes, nome, valor, mes[:8] + '10', mes[:8] + '10' if situacao == 'Pago' else None, situacao))
    return iid


@pytest.fixture
def cen(banco):  # noqa: F811
    """Catalogo NOVO administrado pelo titular ficticio e os registros do cenario."""
    catalogo_novo(banco)
    c = {'outros': nova_categoria(banco, 'Outros', ['outros', 'diversos']),
         'moradia': nova_categoria(banco, 'Moradia (reorg)', ['aluguel']),
         'extra': nova_categoria(banco, 'Atividades Extra-Curriculares', ['natacao']),
         'impostos': nova_categoria(banco, 'Impostos e Taxas', ['taxa']),
         'assin': nova_categoria(banco, 'Assinaturas (reorg)', ['supabase', 'google one', 'streaming']),
         'entret': nova_categoria(banco, 'Entretenimento', ['netflix', 'streaming']),
         'domest': nova_categoria(banco, 'Serviços domésticos', ['diarista', 'limpeza']),
         'manut': nova_categoria(banco, 'Manutenção residencial', ['encanador', 'eletricista']),
         'gerais': nova_categoria(banco, 'Serviços gerais', ['servico', 'serviço', 'manutencao', 'manutenção', 'instalacao',
                                                             'instalação', 'assistencia', 'assistência'])}
    c['fin'] = item(banco, 'Financiamento (ficticio)', None, [('2031-01-01', 'Pago'), ('2031-02-01', 'Pago'), ('2031-03-01', 'Pendente'),
                                                              ('2031-04-01', 'Pendente')], tipo='Financiamento', valor='2500.00')
    c['natacao'] = item(banco, 'Natacao (ficticia)', c['outros'], [('2031-02-01', 'Pago'), ('2031-03-01', 'Pendente')], valor='500.00', recorrente=True)
    c['futebol'] = item(banco, 'Futebol (ficticio)', c['outros'], [('2031-03-01', 'Pendente')], valor='120.00', recorrente=True)
    c['emprestimo'] = item(banco, 'Emprestimo (ficticio)', c['outros'], [('2031-03-01', 'Pendente')], valor='2800.00')
    # conta dispensada e conta substituida: fora do Dashboard e, por isso, fora dos indicadores
    item(banco, 'Dispensada (ficticia)', c['outros'], [('2031-03-01', 'Dispensada'), ('2031-03-01', 'Substituida')], valor='250.00')
    for nome in ('Poupanca 1 (ficticia)', 'Poupanca 2 (ficticia)'):
        rpc(banco, 'criar_consorcio', PESSOAL, {'nome': nome, 'valor_inicial': 500, 'numero_parcelas': 4, 'categoria_id': c['outros'],
                                               'mes_inicio': '2031-02', 'tipo_reajuste': 'fixo', 'valor_reajuste': 10,
                                               'mes_contemplacao': '2031-04'}, chave())
    rpc(banco, 'criar_consorcio', PESSOAL, {'nome': 'Legado (ficticio)', 'valor_inicial': 200, 'numero_parcelas': 3,
                                           'categoria_id': c['outros'], 'mes_inicio': '2030-01'}, chave())
    sql(banco, "update public.contrato_consorcio set ativo = false where nome = 'Legado (ficticio)'")
    c['parcelas'] = [r['id'] for r in sql(banco, "select id from public.item_despesa where tipo = 'Consorcio' and nome like "
                                                 "'Poupanca %% (ficticia) - Parcela %%' order by id")]
    c['legado'] = [r['id'] for r in sql(banco, "select id from public.item_despesa where tipo = 'Consorcio' and nome like 'Legado%%' order by id")]
    compras = {}
    for nome, valor in (('IOF COMPRA INTERNACIONAL', '8.02'), ('SUPABASE (ficticio)', '229.28'), ('Ajuste de saldo', '1906.00'),
                        ('Ajustes de Saldo', '1663.06'), ('AMAZONMKTPLC (ficticio)', '150.00')):
        r = comprar(banco, descricao=nome, valor=valor, total_parcelas=1, categoria_id=c['outros'], mes_fatura=MES, data_compra='2031-02-20')
        compras[nome] = sql(banco, 'select id from public.lancamento_agregado where compra_id = %s', (r['compra_id'],))[0]['id']
    c['compras'] = compras
    return c


def manifesto(c):
    return {'itens': [{'id': c['fin'], 'de': None, 'para': c['moradia']},
                      {'id': c['natacao'], 'de': c['outros'], 'para': c['extra']},
                      *[{'id': p, 'de': c['outros'], 'para': c['extra']} for p in c['parcelas']]],
            'compras': [{'id': c['compras']['IOF COMPRA INTERNACIONAL'], 'de': c['outros'], 'para': c['impostos']},
                        {'id': c['compras']['SUPABASE (ficticio)'], 'de': c['outros'], 'para': c['assin']}]}


def categorias_de(dsn):
    return {**{('item', r['id']): r['categoria_id'] for r in sql(dsn, 'select id, categoria_id from public.item_despesa')},
            **{('compra', r['id']): r['categoria_id'] for r in sql(dsn, 'select id, categoria_id from public.lancamento_agregado')}}


def test_reclassificacao_troca_so_a_categoria_e_a_inversa_devolve(banco, cen):  # noqa: F811
    c, m = cen, manifesto(cen)
    antes, cats_antes = retrato(banco), categorias_de(banco)
    p = rpc(banco, 'previa_reclassificacao_categorias', m)
    assert p['bloqueios'] == [] and retrato(banco) == antes and categorias_de(banco) == cats_antes  # a previa nao altera nada
    assert p['totais'] == {'itens': 10, 'compras': 2, 'contas_por_heranca': 4 + 2 + 8, 'valor_das_contas': 4 * 2500 + 2 * 500 + 2 * (500 + 510 + 520 + 530),
                           'valor_das_compras': 237.30}
    k = chave()
    r = rpc(banco, 'reclassificar_categorias', m, p['hash'], k)
    assert r['totais'] == p['totais'] and 'fotos' not in r
    depois = categorias_de(banco)
    mudaram = {x for x in depois if depois[x] != cats_antes[x]}
    assert mudaram == {('item', c['fin']), ('item', c['natacao']), *[('item', x) for x in c['parcelas']],
                       ('compra', c['compras']['IOF COMPRA INTERNACIONAL']), ('compra', c['compras']['SUPABASE (ficticio)'])}
    assert depois[('item', c['fin'])] == c['moradia'] and depois[('compra', c['compras']['IOF COMPRA INTERNACIONAL'])] == c['impostos']
    # o resto do banco identico: contas, valores, vencimentos, pagamentos, faturas, movimentos, recorrencias, consorcios
    meio = retrato(banco)
    assert {t for t in antes if antes[t] != meio[t]} == set()
    # o que ficou de fora por decisao: ajustes, marketplace, emprestimo, futebol (fora deste manifesto) e o consorcio inativo
    for fora in ([('compra', c['compras'][n]) for n in ('Ajuste de saldo', 'Ajustes de Saldo', 'AMAZONMKTPLC (ficticio)')]
                 + [('item', c['emprestimo']), ('item', c['futebol'])] + [('item', x) for x in c['legado']]):
        assert depois[fora] == c['outros']
    # as contas herdam a categoria do item: a leitura das despesas do mes ja mostra a nova
    nomes = chamar(banco, USUARIO_A, 'select jsonb_object_agg(x.nome, x.categoria_nome) from financeiro.contas_do_mes(%s, %s) x', (PESSOAL, MES))
    assert nomes['Financiamento (ficticio)'] == 'Moradia (reorg)' and nomes['Natacao (ficticia)'] == 'Atividades Extra-Curriculares'
    # auditoria com a categoria anterior de cada registro
    foto = sql(banco, "select resultado from financeiro.operacao_catalogo where chave = %s", (k,))[0]['resultado']
    assert len(foto['fotos']) == 12 and {'tabela': 'item_despesa', 'id': c['fin'], 'de': None, 'para': c['moradia'], 'contas': 4} in foto['fotos']
    # repetir com a mesma chave devolve o resultado anterior; com outra chave, o manifesto ja nao confere e nada muda
    assert rpc(banco, 'reclassificar_categorias', m, p['hash'], k)['repetida'] is True
    assert falha(banco, 'reclassificar_categorias', m, p['hash'], chave())[0] == '40001'
    assert categorias_de(banco) == depois
    # inversa: tudo como antes; segunda inversa recusada
    kr = chave()
    assert rpc(banco, 'reverter_reclassificacao_categorias', k, kr) == {'origem': k, 'registros_restaurados': 12}
    assert categorias_de(banco) == cats_antes and retrato(banco) == antes
    assert rpc(banco, 'reverter_reclassificacao_categorias', k, kr)['repetida'] is True
    assert 'ja foi revertida' in falha(banco, 'reverter_reclassificacao_categorias', k, chave())[1]


def test_previa_mudada_bloqueios_e_falha_sem_alterar_nada(banco, cen):  # noqa: F811
    c, m = cen, manifesto(cen)
    p = rpc(banco, 'previa_reclassificacao_categorias', m)
    antes = categorias_de(banco)
    # o estado mudou depois da previa (uma conta nova no item): o hash nao confere
    item_id = c['natacao']
    sql(banco, "insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, data_vencimento, "
               "status_pagamento, debito_automatico, is_fatura_cartao, estouro_orcamento, status_fatura) "
               "values (%s, %s, '2031-04-01', 'nova', '500.00', '2031-04-10', 'Pendente', false, false, false, 'ABERTA')", (PESSOAL, item_id))
    codigo, texto = falha(banco, 'reclassificar_categorias', m, p['hash'], chave())
    assert codigo == '40001' and 'previa da reclassificacao mudou' in texto and categorias_de(banco) == antes
    # bloqueios: registro inexistente, categoria diferente da esperada, destino inativo, cartao, sem mudanca
    ruim = {'itens': [{'id': 99999999, 'de': None, 'para': c['moradia']}, {'id': c['futebol'], 'de': c['moradia'], 'para': c['extra']},
                      {'id': CARTAO, 'de': None, 'para': c['moradia']}, {'id': c['emprestimo'], 'de': c['outros'], 'para': c['outros']}],
            'compras': [{'id': c['compras']['Ajuste de saldo'], 'de': c['outros'], 'para': 99999999}]}
    pr = rpc(banco, 'previa_reclassificacao_categorias', ruim)
    assert {b['codigo'] for b in pr['bloqueios']} == {'NAO_ENCONTRADO', 'CATEGORIA_MUDOU', 'CARTAO', 'SEM_MUDANCA', 'DESTINO_INVALIDO'}
    codigo, texto = falha(banco, 'reclassificar_categorias', ruim, pr['hash'], chave())
    assert codigo == 'P0001' and 'Nada foi alterado' in texto and categorias_de(banco) == antes
    # um registro valido junto de um invalido: nada e aplicado (uma transacao)
    misto = {'itens': [{'id': c['futebol'], 'de': c['outros'], 'para': c['extra']}, {'id': 99999999, 'de': None, 'para': c['moradia']}]}
    pm = rpc(banco, 'previa_reclassificacao_categorias', misto)
    assert falha(banco, 'reclassificar_categorias', misto, pm['hash'], chave())[0] == 'P0001' and categorias_de(banco) == antes
    # manifestos invalidos
    for invalido in ({}, {'itens': []}, {'itens': [{'id': c['futebol']}]}, {'itens': 'x'},
                     {'itens': [{'id': c['futebol'], 'de': c['outros'], 'para': c['extra']}] * 2}):
        assert falha(banco, 'previa_reclassificacao_categorias', invalido)[0] == '22023'
    assert falha(banco, 'reclassificar_categorias', m, p['hash'], None)[0] == '22023'
    # inversa recusada quando o registro mudou depois da reclassificacao
    p2 = rpc(banco, 'previa_reclassificacao_categorias', m)
    k = chave()
    rpc(banco, 'reclassificar_categorias', m, p2['hash'], k)
    sql(banco, 'update public.item_despesa set categoria_id = %s where id = %s', (c['impostos'], c['natacao']))
    feito = categorias_de(banco)
    assert 'alterado depois' in falha(banco, 'reverter_reclassificacao_categorias', k, chave())[1] and categorias_de(banco) == feito


def test_permissoes_perfis_e_privilegios(banco, cen):  # noqa: F811
    c, m = cen, manifesto(cen)
    p = rpc(banco, 'previa_reclassificacao_categorias', m)
    # quem nao administra o catalogo nao ve a previa nem executa
    for funcao, args in (('previa_reclassificacao_categorias', (m,)), ('reclassificar_categorias', (m, p['hash'], chave())),
                         ('reverter_reclassificacao_categorias', (chave(), chave())), ('definir_natureza_categoria', (c['outros'], 'NAO_DEFINIDO', chave()))):
        assert falha(banco, funcao, *args, usuario=USUARIO_B)[0] == '42501'
    # item de perfil ainda no Flask (Empresa): recusado sem alterar nada
    da_empresa = item(banco, 'Despesa da Empresa (ficticia)', c['outros'], [('2031-03-01', 'Pendente')], perfil=EMPRESA)
    me = {'itens': [{'id': da_empresa, 'de': c['outros'], 'para': c['moradia']}, {'id': c['futebol'], 'de': c['outros'], 'para': c['extra']}]}
    antes = categorias_de(banco)
    codigo, texto = falha(banco, 'reclassificar_categorias', me, rpc(banco, 'previa_reclassificacao_categorias', me)['hash'], chave())
    assert codigo in ('P0001', '42501') and categorias_de(banco) == antes
    linhas = {r['n']: (r['a'], r['x']) for r in sql(banco, """
        select p.proname n, has_function_privilege('authenticated', p.oid, 'EXECUTE') a, has_function_privilege('anon', p.oid, 'EXECUTE') x
          from pg_proc p join pg_namespace s on s.oid = p.pronamespace
         where s.nspname = 'financeiro' and p.proname in ('natureza_da_categoria', 'naturezas_das_categorias', 'definir_natureza_categoria',
               'previa_reclassificacao_categorias', 'reclassificar_categorias', 'reverter_reclassificacao_categorias',
               'indicadores_gerenciais', 'poupanca_programada_tela')""")}
    assert linhas == {'natureza_da_categoria': (False, False), 'naturezas_das_categorias': (True, False),
                      'definir_natureza_categoria': (True, False), 'previa_reclassificacao_categorias': (True, False),
                      'reclassificar_categorias': (True, False), 'reverter_reclassificacao_categorias': (True, False),
                      'indicadores_gerenciais': (True, False), 'poupanca_programada_tela': (True, False)}
    # a tabela so pelas funcoes; leitura de outro perfil recusada
    assert sql(banco, "select has_table_privilege('authenticated', 'financeiro.categoria_natureza', 'SELECT') s")[0]['s'] is False
    assert falha(banco, 'indicadores_gerenciais', PESSOAL, '2031-03', usuario=USUARIO_B)[0] == '42501'
    assert falha(banco, 'poupanca_programada_tela', PESSOAL, usuario=USUARIO_B)[0] == '42501'


def test_natureza_gerencial_indicadores_e_poupanca_programada(banco, cen):  # noqa: F811
    c = cen
    # sem linha: CONSUMO (como hoje); sem categoria: NAO_DEFINIDO; nunca pelo nome
    naturezas = {n['categoria_id']: n for n in rpc(banco, 'naturezas_das_categorias')}
    assert naturezas[c['outros']] == {'categoria_id': c['outros'], 'nome': 'Outros', 'ativo': True, 'natureza': 'CONSUMO', 'definida': False, 'padrao': True}
    antes = rpc(banco, 'indicadores_gerenciais', PESSOAL, '2031-03')
    dashboard = rpc(banco, 'dashboard_resumo_tela', PESSOAL, '2031-03')['fluxo_caixa']['resumo']['despesas_previstas']
    assert Decimal(str(antes['fluxo_total'])) == Decimal(str(dashboard))  # o mesmo conjunto do Dashboard
    assert antes['aportes'] == 0 and antes['nao_definido'] == 2500  # o financiamento sem categoria
    # categoria nova de aporte, parcelas dos dois consorcios vigentes nela e Outros como NAO_DEFINIDO
    poupanca = rpc(banco, 'criar_categoria', {'nome': 'Poupança Programada', 'padrao': True}, chave())['categoria_id']
    k = chave()
    assert rpc(banco, 'definir_natureza_categoria', poupanca, 'APORTE', k) == {
        'categoria_id': poupanca, 'natureza': 'APORTE', 'natureza_anterior': None, 'tinha_linha': False}
    assert rpc(banco, 'definir_natureza_categoria', poupanca, 'APORTE', k)['repetida'] is True
    rpc(banco, 'definir_natureza_categoria', c['outros'], 'NAO_DEFINIDO', chave())
    assert falha(banco, 'definir_natureza_categoria', c['outros'], 'INVESTIMENTO', chave())[0] == '22023'
    assert falha(banco, 'definir_natureza_categoria', 99999999, 'CONSUMO', chave())[0] == 'P0001'
    # natureza nula retira a linha (volta ao padrao) e devolve a anterior
    assert rpc(banco, 'definir_natureza_categoria', c['impostos'], 'AJUSTE_TECNICO', chave())['tinha_linha'] is False
    volta = rpc(banco, 'definir_natureza_categoria', c['impostos'], None, chave())
    assert (volta['natureza'], volta['natureza_anterior'], volta['tinha_linha']) == (None, 'AJUSTE_TECNICO', True)
    assert {n['categoria_id']: n for n in rpc(banco, 'naturezas_das_categorias')}[c['impostos']]['definida'] is False
    m = {'itens': [{'id': p, 'de': c['outros'], 'para': poupanca} for p in c['parcelas']] + [{'id': c['fin'], 'de': None, 'para': c['moradia']}]}
    rpc(banco, 'reclassificar_categorias', m, rpc(banco, 'previa_reclassificacao_categorias', m)['hash'], chave())
    depois = rpc(banco, 'indicadores_gerenciais', PESSOAL, '2031-03')
    # 03/2031: financiamento 2500 (consumo), natacao 500, futebol 120 e emprestimo 2800 (Outros = nao definido) e a 2a parcela
    # de cada consorcio (510 + 510 = aporte). O total do fluxo nao muda: nada some, so muda de linha.
    assert depois['fluxo_total'] == antes['fluxo_total'] == dashboard
    assert (depois['aportes'], depois['consumo'], depois['nao_definido'], depois['ajustes_tecnicos']) == (1020, 2500, 3420, 0)
    assert depois['consumo'] + depois['aportes'] + depois['nao_definido'] + depois['ajustes_tecnicos'] + depois['transferencias_internas'] == depois['fluxo_total']
    assert depois['obrigacoes']['APORTE'] == {'quantidade': 2, 'previsto': 1020, 'pago': 0}
    assert rpc(banco, 'dashboard_resumo_tela', PESSOAL, '2031-03')['fluxo_caixa']['resumo']['despesas_previstas'] == dashboard
    # compras do cartao por natureza (informativo; as faturas nao se somam de novo): tudo em Outros
    assert depois['cartao'] == {'NAO_DEFINIDO': {'quantidade': 5, 'valor': 3956.36}}

    # posicao dos consorcios de aporte: so os dois vigentes; o resgate nao e todo ganho
    pagar = sql(banco, "select c.id from public.conta c join public.item_despesa i on i.id = c.item_despesa_id "
                       "where i.nome = 'Poupanca 1 (ficticia) - Parcela 1/4'")[0]['id']
    sql(banco, "update public.conta set status_pagamento = 'Pago', data_pagamento = '2031-02-05' where id = %s", (pagar,))
    posicao = {x['nome']: x for x in rpc(banco, 'poupanca_programada_tela', PESSOAL)}
    assert set(posicao) == {'Poupanca 1 (ficticia)', 'Poupanca 2 (ficticia)'}
    p1 = posicao['Poupanca 1 (ficticia)']
    # parcelas 500, 510, 520, 530 = 2060; premio = parcela da posicao 3 (520) x 4 = 2080; ganho 20, o resto e retorno de capital
    assert (p1['parcelas'], p1['aporte_previsto'], p1['aporte_pago'], p1['aporte_a_pagar']) == (4, 2060, 500, 1560)
    assert (p1['resgate_previsto'], p1['retorno_de_capital_previsto'], p1['ganho_previsto'], p1['perda_prevista']) == (2080, 2060, 20, 0)
    assert (p1['resgate_recebido'], p1['retorno_de_capital_recebido'], p1['ganho_recebido'], p1['posicao']) == (0, 0, 0, 500)
    # o resgate so conta como recebido com o movimento bancario; nenhuma receita e alterada pela leitura
    receitas = sql(banco, "select md5(coalesce(string_agg(r::text, '|' order by r.id), '')) h from public.receita_realizada r")[0]['h']
    rpc(banco, 'poupanca_programada_tela', PESSOAL)
    assert sql(banco, "select md5(coalesce(string_agg(r::text, '|' order by r.id), '')) h from public.receita_realizada r")[0]['h'] == receitas


def sugestao(dsn, descricao, fallback=None):
    return sql(dsn, 'select financeiro.sugestao_categoria_importacao(%s, %s, %s, %s) s', (PESSOAL, descricao.lower(), descricao.lower(), fallback))[0]['s']


def test_importacao_outros_nao_se_propaga_pelo_historico(banco, cen):  # noqa: F811
    c = cen
    # antes da natureza: a descricao ja classificada em Outros volta como Outros, com confianca alta (o defeito)
    assert (sugestao(banco, 'AMAZONMKTPLC (ficticio)')['categoria_id'], sugestao(banco, 'AMAZONMKTPLC (ficticio)')['confianca']) == (c['outros'], 'alta')
    rpc(banco, 'definir_natureza_categoria', c['outros'], 'NAO_DEFINIDO', chave())
    compras_antes = sql(banco, "select md5(string_agg(l::text, '|' order by l.id)) h from public.lancamento_agregado l")[0]['h']
    # depois: sem sugestao (a tela pede a decisao ou usa a categoria que o usuario escolheu para o lote, com confianca media)
    s = sugestao(banco, 'AMAZONMKTPLC (ficticio)')
    assert (s['categoria_id'], s['origem'], s['confianca']) == (None, 'sem_sugestao', 'baixa')
    s = sugestao(banco, 'AMAZONMKTPLC (ficticio)', c['moradia'])
    assert (s['categoria_id'], s['origem'], s['confianca']) == (c['moradia'], 'fallback', 'media')
    # palavra-chave especifica tem prioridade sobre o historico em Outros
    s = sugestao(banco, 'SUPABASE (ficticio)')
    assert (s['categoria_id'], s['origem']) == (c['assin'], 'palavra_chave')
    # termo em duas categorias: ambigua, sem categoria definitiva
    s = sugestao(banco, 'streaming qualquer')
    assert (s['categoria_id'], s['ambigua'], s['origem']) == (None, True, 'ambigua')
    # a escolha especifica confirmada pelo usuario vale como historico, mesmo havendo depois a mesma descricao em Outros
    comprar(banco, descricao='LOJA DO BAIRRO', valor='10.00', total_parcelas=1, categoria_id=c['moradia'], mes_fatura=MES, data_compra='2031-02-21')
    comprar(banco, descricao='LOJA DO BAIRRO', valor='12.00', total_parcelas=1, categoria_id=c['outros'], mes_fatura=MES, data_compra='2031-02-22')
    s = sugestao(banco, 'LOJA DO BAIRRO')
    assert (s['categoria_id'], s['origem'], s['confianca']) == (c['moradia'], 'historico', 'alta')
    # nenhuma compra antiga muda pela sugestao
    assert sql(banco, "select md5(string_agg(l::text, '|' order by l.id)) h from public.lancamento_agregado l where l.descricao <> 'LOJA DO BAIRRO'")[0]['h'] != ''
    assert sql(banco, "select count(*) n from public.lancamento_agregado l where l.descricao = 'AMAZONMKTPLC (ficticio)' and l.categoria_id = %s",
               (c['outros'],))[0]['n'] == 1
    assert compras_antes  # (as compras do cenario seguem como estavam: conferido pelo retrato nos outros testes)


def test_incorporacao_oficial_e_palavras_chave_pelas_funcoes_oficiais(banco, cen):  # noqa: F811
    c = cen
    # as oito palavras genericas de Servicos gerais sao desativadas antes; a incorporacao oficial nao leva nenhuma ativa
    for p in sql(banco, 'select id from public.categoria_palavra_chave where categoria_id = %s', (c['gerais'],)):
        rpc(banco, 'remover_palavra_chave', c['gerais'], p['id'])
    incorporar(banco, c['gerais'], c['manut'])
    assert sql(banco, 'select count(*) n from public.categoria where id = %s', (c['gerais'],))[0]['n'] == 0
    ativas = {r['palavra'] for r in sql(banco, 'select palavra from public.categoria_palavra_chave where categoria_id = %s and ativo', (c['manut'],))}
    assert ativas == {'encanador', 'eletricista'}
    rpc(banco, 'criar_palavra_chave', c['manut'], 'Higienização de Sofá')
    assert sugestao(banco, 'higienização de sofá da sala')['categoria_id'] == c['manut']
    # "instalacao" e "servico" sozinhos nao decidem mais nada; Servicos domesticos continua independente
    assert sugestao(banco, 'instalacao')['origem'] == 'sem_sugestao' and sugestao(banco, 'posto de servico')['origem'] == 'sem_sugestao'
    assert sugestao(banco, 'diarista')['categoria_id'] == c['domest']
    assert sql(banco, 'select count(*) n from public.categoria where id = %s', (c['domest'],))[0]['n'] == 1


def test_reversao_da_migration_recusada_com_dados_e_reaplicacao(banco, cen, cluster):  # noqa: F811
    c = cen
    rpc(banco, 'definir_natureza_categoria', c['outros'], 'NAO_DEFINIDO', chave())
    with pytest.raises(psycopg2.Error) as e:
        executar_arquivo(banco, REVERSAO)
    assert 'naturezas gerenciais gravadas' in str(e.value)
    sql(banco, 'delete from financeiro.categoria_natureza')
    m = {'itens': [{'id': c['futebol'], 'de': c['outros'], 'para': c['extra']}]}
    k = chave()
    rpc(banco, 'reclassificar_categorias', m, rpc(banco, 'previa_reclassificacao_categorias', m)['hash'], k)
    with pytest.raises(psycopg2.Error) as e:
        executar_arquivo(banco, REVERSAO)
    assert 'nao revertida' in str(e.value)
    rpc(banco, 'reverter_reclassificacao_categorias', k, chave())
    executar_arquivo(banco, REVERSAO)
    assert sql(banco, "select to_regclass('financeiro.categoria_natureza') t")[0]['t'] is None
    assert sql(banco, "select to_regprocedure('financeiro.reclassificar_categorias(jsonb, text, uuid)') f")[0]['f'] is None
    definicao = sql(banco, "select pg_get_functiondef('financeiro.sugestao_categoria_importacao(integer, text, text, integer)'::regprocedure) d")[0]['d']
    assert 'natureza_da_categoria' not in definicao
    assert sugestao(banco, 'AMAZONMKTPLC (ficticio)')['categoria_id'] == c['outros']  # o comportamento anterior
    executar_arquivo(banco, MIGRATION)
    assert sql(banco, "select to_regprocedure('financeiro.reclassificar_categorias(jsonb, text, uuid)') f")[0]['f']
    assert json.dumps(rpc(banco, 'naturezas_das_categorias'))  # leitura de novo disponivel
