"""
Testes FIN-CONTRATOS-3 (fase A) — cadastro, edicao, regeneracao segura e exclusao de consorcios (migration 20261121090000).

Fidelidade: o PROPRIO Flask cria e edita consorcios FICTICIOS numa copia do cluster (perfil no Flask) e o novo
aplicativo faz o mesmo noutra (perfil atribuido a ele); contrato, parcelas (itens e despesas) e receita de contemplacao
sao comparados campo a campo. Defeitos do Flask que nao sao reproduzidos, demonstrados no proprio Flask: a regeneracao
apaga despesas pagas. Tambem: regeneracao/exclusao seguras, escritor unico, quem so le, isolamento, idempotencia.
"""
import uuid
from decimal import Decimal

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_receitas_categorias_tela import flask
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    USUARIO_B,
    atribuir,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL, EMPRESA = ID['PESSOAL'], ID['EMPRESA']


def banco_de(dsn):
    return sql(dsn, "select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")[0]['id']


def categoria_de(dsn):
    return sql(dsn, 'select id from public.categoria order by id limit 1')[0]['id']


def contratos(dsn, banco, categoria):
    return [
        {'nome': 'Consorcio Imovel (ficticio)', 'valor_inicial': 850.5, 'numero_parcelas': 12, 'categoria_id': categoria,
         'mes_inicio': '2031-01', 'tipo_reajuste': 'percentual', 'valor_reajuste': 2.5, 'mes_contemplacao': '2031-06',
         'meio_pagamento': 'debito_automatico', 'conta_bancaria_id': banco, 'observacoes': 'teste'},
        {'nome': 'Consorcio Moto (ficticio)', 'valor_inicial': 300, 'numero_parcelas': 6, 'categoria_id': categoria,
         'mes_inicio': '3/2031', 'tipo_reajuste': 'fixo', 'valor_reajuste': 15},
        {'nome': 'Consorcio Mes (ficticio)', 'valor_inicial': 120.33, 'numero_parcelas': 4, 'categoria_id': categoria,
         'data_inicial': '2032-05-10', 'mes_inicio': '7', 'mes_contemplacao': '9', 'meio_pagamento': 'boleto'},
    ]


def estado(dsn, nome_like='Consorcio %(ficticio)%'):
    c = sql(dsn, "select nome, valor_inicial, tipo_reajuste, valor_reajuste, numero_parcelas, mes_inicio, mes_contemplacao, "
                 "valor_premio, ativo, observacoes, perfil_financeiro_id from public.contrato_consorcio where nome like %s "
                 "order by nome", (nome_like,))
    itens = sql(dsn, "select nome, descricao, valor, data_vencimento, categoria_id, tipo, mes_competencia, meio_pagamento, "
                     "conta_bancaria_id, ativo, recorrente from public.item_despesa where tipo = 'Consorcio' and nome like %s "
                     "order by nome", (nome_like,))
    contas = sql(dsn, "select c.descricao, c.valor, c.data_vencimento, c.mes_referencia, c.status_pagamento, c.debito_automatico, "
                      "c.conta_bancaria_id, c.numero_parcela, c.total_parcelas from public.conta c join public.item_despesa d "
                      "on d.id = c.item_despesa_id where d.tipo = 'Consorcio' and d.nome like %s order by c.descricao", (nome_like,))
    receitas = sql(dsn, "select r.descricao, r.valor_recebido, r.data_recebimento, r.mes_referencia, r.conta_bancaria_id, "
                        "i.nome fonte from public.receita_realizada r join public.item_receita i on i.id = r.item_receita_id "
                        "where r.observacoes like 'consorcio_id=%%' order by r.descricao")
    return {'contratos': c, 'itens': itens, 'contas': contas, 'receitas': [{**r, 'descricao': r['descricao'].rsplit(' (ID', 1)[0]}
                                                                          for r in receitas]}


def novo_cria(dsn, dados, usuario=None, chave=None):
    return rpc(dsn, 'criar_consorcio', PESSOAL, dados, chave or str(uuid.uuid4()), **({'usuario': usuario} if usuario else {}))


def falha(dsn, funcao, *args, usuario=None):
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, funcao, *args, **({'usuario': usuario} if usuario else {}))
    return erro.value.pgcode, erro.value.diag.message_primary, erro.value.diag.message_hint


def test_cadastro_igual_ao_flask(cluster):  # noqa: F811
    antigo, novo = copiar(cluster), copiar(cluster)
    dados = contratos(antigo, banco_de(antigo), categoria_de(antigo))
    r = flask(antigo, [('perfil', PESSOAL)] + [(f'c{i}', 'post', '/api/consorcios/', d) for i, d in enumerate(dados)])
    assert all(s == 201 for s, _ in r.values()), r
    atribuir(novo, 'PESSOAL')
    for d in contratos(novo, banco_de(novo), categoria_de(novo)):
        res = novo_cria(novo, d)
        assert res['parcelas_geradas'] == d['numero_parcelas']
    a, b = estado(antigo), estado(novo)
    for chave in a:  # contrato, itens, despesas e receita de contemplacao, campo a campo
        assert len(b[chave]) == len(a[chave]), chave
        for x, y in zip(a[chave], b[chave]):
            assert x == y, (chave, {k: (x[k], y.get(k)) for k in x if x[k] != y.get(k)})


def test_edicao_igual_ao_flask_e_renomeia_parcelas(cluster):  # noqa: F811
    antigo, novo = copiar(cluster), copiar(cluster)
    dados = contratos(antigo, banco_de(antigo), categoria_de(antigo))[0]
    edicao = {'valor_inicial': 900, 'mes_contemplacao': '2031-08', 'meio_pagamento': 'boleto', 'observacoes': 'editado'}
    r = flask(antigo, [('perfil', PESSOAL), ('c', 'post', '/api/consorcios/', dados), ('e', 'put', '/api/consorcios/{c}', edicao)])
    assert r['e'][0] == 200, r
    atribuir(novo, 'PESSOAL')
    cid = novo_cria(novo, dados)['data']['id']
    rpc(novo, 'editar_consorcio', PESSOAL, cid, edicao)
    assert estado(novo) == estado(antigo)  # o Flask tambem nao regenera parcelas na edicao
    # Renomear: aqui as parcelas acompanham (no Flask o vinculo, que e pelo nome, se perde).
    rpc(novo, 'editar_consorcio', PESSOAL, cid, {'nome': 'Consorcio Casa (ficticio)'})
    nomes = [i['nome'] for i in estado(novo, 'Consorcio Casa (ficticio)%')['itens']]
    assert len(nomes) == 12 and all(n.startswith('Consorcio Casa (ficticio) - Parcela ') for n in nomes)
    assert estado(novo, 'Consorcio Imovel%')['itens'] == []
    # Migration 20261122090000: a descricao das despesas pendentes tambem acompanha (a lista de Despesas mostra ela).
    descricoes = [c['descricao'] for c in estado(novo, 'Consorcio Casa (ficticio)%')['contas']]
    assert len(descricoes) == 12 and all(d.startswith('Consorcio Casa (ficticio) - Parcela ') for d in descricoes)


def test_renomear_preserva_descricao_da_despesa_paga(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    banco = banco_de(dsn)
    cid = novo_cria(dsn, contratos(dsn, banco, categoria_de(dsn))[1])['data']['id']
    _pagar(dsn, _contas(dsn, 'Consorcio Moto')[1]['id'], banco, '2031-03-05')
    rpc(dsn, 'editar_consorcio', PESSOAL, cid, {'nome': 'Consorcio Bicicleta (ficticio)'})
    contas = {r['numero_parcela']: r['descricao'] for r in sql(
        dsn, "select c.numero_parcela, c.descricao from public.conta c join public.item_despesa d on d.id = c.item_despesa_id "
             "where d.tipo = 'Consorcio' and d.nome like 'Consorcio Bicicleta%%'")}
    assert contas[1] == 'Consorcio Moto (ficticio) - Parcela 1/6'  # paga: historico
    assert all(contas[i] == f'Consorcio Bicicleta (ficticio) - Parcela {i}/6' for i in range(2, 7))


def _pagar(dsn, conta, banco, data):
    valor = str(sql(dsn, 'select valor from public.conta where id = %s', (conta,))[0]['valor'])
    return rpc(dsn, 'pagar_despesa', PESSOAL, conta, {'conta_bancaria_id': banco, 'data_pagamento': data, 'valor_pago': valor,
                                                     'valor_devido': valor}, str(uuid.uuid4()))


def _contas(dsn, prefixo):
    return {r['numero_parcela']: r for r in sql(
        dsn, "select c.id, c.numero_parcela, c.valor, c.status_pagamento, c.descricao from public.conta c join public.item_despesa d "
             "on d.id = c.item_despesa_id where d.tipo = 'Consorcio' and d.nome like %s order by c.numero_parcela", (prefixo + '%',))}


def test_regeneracao_segura_preserva_efetivadas(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    banco = banco_de(dsn)
    dados = contratos(dsn, banco, categoria_de(dsn))[1]  # Moto: 6 parcelas, reajuste fixo
    cid = novo_cria(dsn, dados)['data']['id']
    contas = _contas(dsn, 'Consorcio Moto')
    _pagar(dsn, contas[1]['id'], banco, '2031-03-05')
    p2 = _pagar(dsn, contas[2]['id'], banco, '2031-04-05')
    rpc(dsn, 'estornar_pagamento_despesa', PESSOAL, contas[2]['id'], p2['movimento_id'],
        {'motivo': 'Teste', 'data_estorno': '2031-04-06'}, str(uuid.uuid4()))  # pendente, mas com movimento
    movs = sql(dsn, 'select * from public.movimento_financeiro order by id')
    contas = _contas(dsn, 'Consorcio Moto')  # depois do pagamento e do estorno
    rpc(dsn, 'editar_consorcio', PESSOAL, cid, {'valor_inicial': 400, 'numero_parcelas': 4})
    r = rpc(dsn, 'regenerar_parcelas_consorcio', PESSOAL, cid, {})
    assert (r['preservadas'], r['atualizadas'], r['removidas'], r['criadas']) == (2, 2, 2, 0)
    depois = _contas(dsn, 'Consorcio Moto')
    assert {n: (c['id'], c['valor'], c['status_pagamento']) for n, c in depois.items() if n <= 2} == \
           {n: (c['id'], c['valor'], c['status_pagamento']) for n, c in contas.items() if n <= 2}  # efetivadas intactas
    assert [(n, c['valor']) for n, c in depois.items() if n > 2] == [(3, Decimal('430.00')), (4, Decimal('445.00'))]
    assert sql(dsn, 'select * from public.movimento_financeiro order by id') == movs  # nenhum movimento tocado
    # De volta a 6 parcelas: as faltantes sao criadas, sem duplicar.
    rpc(dsn, 'editar_consorcio', PESSOAL, cid, {'numero_parcelas': 6})
    r = rpc(dsn, 'regenerar_parcelas_consorcio', PESSOAL, cid, {})
    assert (r['preservadas'], r['criadas']) == (2, 2) and sorted(_contas(dsn, 'Consorcio Moto')) == [1, 2, 3, 4, 5, 6]


def test_flask_regenerar_com_parcela_paga(cluster):  # noqa: F811
    """Defeito do Flask (nao reproduzido): regenerar manda apagar TODAS as despesas do contrato, inclusive a paga. No
    PostgreSQL a chave estrangeira do movimento barra o delete e a regeneracao inteira falha (500); no SQLite do Flask,
    que nao liga PRAGMA foreign_keys, a despesa paga e apagada de fato e o movimento fica orfao."""
    dsn = copiar(cluster)
    banco = banco_de(dsn)
    dados = contratos(dsn, banco, categoria_de(dsn))[1]
    r = flask(dsn, [('perfil', PESSOAL), ('c', 'post', '/api/consorcios/', dados)])
    conta = _contas(dsn, 'Consorcio Moto')[1]['id']
    r = flask(dsn, [('perfil', PESSOAL), ('p', 'post', f'/api/despesas/{conta}/pagar', {'conta_bancaria_id': banco,
                                                                                      'data_pagamento': '2031-03-05'}),
                    ('g', 'post', f"/api/consorcios/{r['c'][1]['data']['id']}/regenerar-parcelas", {})])
    assert r['p'][0] == 200 and r['g'][0] == 500  # aqui a regeneracao segura funciona (test_regeneracao_segura...)
    assert sql(dsn, 'select status_pagamento from public.conta where id = %s', (conta,))[0]['status_pagamento'] == 'Pago'


def test_exclusao_segura(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    banco = banco_de(dsn)
    dados = contratos(dsn, banco, categoria_de(dsn))[0]  # Imovel: 12 parcelas, contemplacao (receita)
    cid = novo_cria(dsn, dados)['data']['id']
    contas = _contas(dsn, 'Consorcio Imovel')
    _pagar(dsn, contas[1]['id'], banco, '2031-01-05')
    p2 = _pagar(dsn, contas[2]['id'], banco, '2031-02-05')
    rpc(dsn, 'estornar_pagamento_despesa', PESSOAL, contas[2]['id'], p2['movimento_id'],
        {'motivo': 'Teste', 'data_estorno': '2031-02-06'}, str(uuid.uuid4()))
    r = rpc(dsn, 'excluir_consorcio', PESSOAL, cid)
    assert r['despesas_pendentes_removidas'] == 10
    restantes = _contas(dsn, 'Consorcio Imovel')
    assert sorted(restantes) == [1, 2] and restantes[1]['status_pagamento'] == 'Pago'  # paga e a com movimento ficam
    assert sql(dsn, 'select ativo from public.contrato_consorcio where id = %s', (cid,))[0]['ativo'] is False
    assert sql(dsn, "select count(*) n from public.receita_realizada where observacoes like 'consorcio_id=%%'")[0]['n'] == 0
    assert sql(dsn, "select count(*) n from public.item_despesa where tipo = 'Consorcio' and ativo")[0]['n'] == 0


def test_escritor_unico_permissoes_e_idempotencia(cluster):  # noqa: F811
    dsn = copiar(cluster)
    dados = contratos(dsn, banco_de(dsn), categoria_de(dsn))[1]
    assert falha(dsn, 'criar_consorcio', PESSOAL, dados, str(uuid.uuid4()))[2] == 'SISTEMA_FLASK'  # perfil no Flask
    atribuir(dsn, 'PESSOAL')
    assert falha(dsn, 'criar_consorcio', PESSOAL, dados, str(uuid.uuid4()), usuario=USUARIO_B)[0] == '42501'
    assert falha(dsn, 'criar_consorcio', EMPRESA, dados, str(uuid.uuid4()))[0] == '42501'  # A so le a Empresa
    chave = str(uuid.uuid4())
    a = novo_cria(dsn, dados, chave=chave)
    b = novo_cria(dsn, dados, chave=chave)
    assert a['data']['id'] == b['data']['id'] and b['repetida'] is True
    assert len(_contas(dsn, 'Consorcio Moto')) == 6  # sem duplicar
    assert falha(dsn, 'criar_consorcio', PESSOAL, dados, str(uuid.uuid4()))[1] == 'Ja existe um consorcio ativo com este nome neste perfil'
    assert falha(dsn, 'criar_consorcio', PESSOAL, {**dados, 'nome': 'X', 'mes_contemplacao': '2035-01'}, str(uuid.uuid4()))[1] == \
        'Mes de contemplacao deve estar dentro do periodo do consorcio.'
    assert falha(dsn, 'criar_consorcio', PESSOAL, {k: v for k, v in dados.items() if k != 'categoria_id'}, str(uuid.uuid4()))[1] == \
        'Campo categoria_id é obrigatório'
    atribuir(dsn, 'PERFIL_B')
    assert falha(dsn, 'excluir_consorcio', ID['PERFIL_B'], a['data']['id'], usuario=USUARIO_B)[2] == 'NAO_ENCONTRADO'
