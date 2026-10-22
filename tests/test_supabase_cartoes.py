"""
Testes FIN-CARTOES-1 — cartoes, compras a vista e parceladas e faturas (sem pagamento).

Cluster PostgreSQL descartavel com o cenario FICTICIO do FIN-RECORRENCIA-1 (copia por
teste): Cartao Teste (910, Pessoal, vence dia 31, limite ativo de R$ 500 na categoria do
cartao 961, mapeada a categoria de despesa 952), Cartao Sem Config (911) e Cartao B (930).
As operacoes passam pelas funcoes do schema `financeiro` como o navegador as chama. A
comparacao com o Flask usa o Flask real (POST /api/cartoes e /api/cartoes/<id>/lancamentos).
"""
import json
import threading
import time
import uuid
from datetime import date
from decimal import Decimal

import pytest

from tests.test_supabase_despesas import _paralelo, flask
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    digital,
    gerar,
    previa,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
from psycopg2 import errors  # noqa: E402

pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

D = date
CARTAO, SEM_CONFIG, CARTAO_B = 910, 911, 930
MORADIA, ASSINATURAS = 951, 952  # 952 -> categoria do cartao 961 (limite R$ 500 no cartao 910)
COMPRA = {'cartao_id': CARTAO, 'descricao': 'Notebook', 'valor': '100.00', 'total_parcelas': 3,
          'data_compra': '2029-05-10', 'mes_fatura': '2029-05-01', 'categoria_id': ASSINATURAS}


@pytest.fixture
def banco(cluster):  # noqa: F811
    return copiar(cluster)


def rpc(dsn, funcao, *args, usuario=USUARIO_A):
    valores = [json.dumps(a) if isinstance(a, dict) else a for a in args]
    marcadores = ', '.join('%s::jsonb' if isinstance(a, dict) else '%s' for a in args)
    return chamar(dsn, usuario, f'select financeiro.{funcao}({marcadores})', valores)


def tabela(dsn, funcao, *args, usuario=USUARIO_A):
    marcadores = ', '.join(['%s'] * len(args))
    return chamar(dsn, usuario, f"select coalesce(json_agg(x), '[]'::json) from financeiro.{funcao}({marcadores}) x", args)


def comprar(dsn, dados=None, perfil='PESSOAL', usuario=USUARIO_A, chave=None, **campos):
    return rpc(dsn, 'criar_compra', ID.get(perfil, perfil), {**(dados or COMPRA), **campos},
               chave or str(uuid.uuid4()), usuario=usuario)


def previa_compra(dsn, perfil='PESSOAL', usuario=USUARIO_A, **campos):
    return rpc(dsn, 'previa_compra', ID.get(perfil, perfil), {**COMPRA, **campos}, usuario=usuario)


def edicao(dsn, lancamento_id, perfil='PESSOAL', usuario=USUARIO_A):
    return rpc(dsn, 'compra_para_edicao', ID.get(perfil, perfil), lancamento_id, usuario=usuario)


def editar(dsn, lancamento_id, dados, perfil='PESSOAL', usuario=USUARIO_A, versao=None):
    versao = versao or edicao(dsn, lancamento_id, perfil, usuario)['versao']
    return rpc(dsn, 'editar_compra', ID.get(perfil, perfil), lancamento_id, versao, dados, usuario=usuario)


def excluir(dsn, lancamento_id, perfil='PESSOAL', usuario=USUARIO_A, versao=None):
    versao = versao or edicao(dsn, lancamento_id, perfil, usuario)['versao']
    return rpc(dsn, 'excluir_compra', ID.get(perfil, perfil), lancamento_id, versao, usuario=usuario)


def cartoes(dsn, perfil='PESSOAL', usuario=USUARIO_A):
    return tabela(dsn, 'cartoes_do_perfil', ID.get(perfil, perfil), usuario=usuario)


def faturas(dsn, mes, perfil='PESSOAL', usuario=USUARIO_A):
    return {f['cartao_id']: f for f in tabela(dsn, 'faturas_do_mes', ID.get(perfil, perfil), mes, usuario=usuario)}


def parcelas(dsn, compra_id):
    return sql(dsn, 'select * from public.lancamento_agregado where compra_id = %s order by numero_parcela', (compra_id,))


def fatura(dsn, cartao, mes):
    linhas = sql(dsn, 'select * from public.conta where is_fatura_cartao and item_despesa_id = %s and cartao_competencia = %s',
                 (cartao, mes))
    assert len(linhas) <= 1
    return linhas[0] if linhas else None


def pagar(dsn, cartao, mes):
    """Simula o pagamento do Flask (status_pagamento; o Flask nunca grava status_fatura 'PAGA')."""
    sql(dsn, "update public.conta set status_pagamento = 'Pago', data_pagamento = %s "
             "where is_fatura_cartao and item_despesa_id = %s and cartao_competencia = %s", (mes, cartao, mes))


def md5_faturas(dsn):
    return sql(dsn, "select coalesce(md5(string_agg(t::text, '|' order by id)), '') as h from public.conta t "
                    "where is_fatura_cartao")[0]['h']


# ---------------------------------------------------------------------------
# 1, 2. Cartoes: cadastro, edicao segura, inativacao, dados sensiveis
# ---------------------------------------------------------------------------

def test_cadastro_de_cartao_como_o_flask_sem_dados_sensiveis(banco):
    r = rpc(banco, 'criar_cartao', ID['PESSOAL'], {'nome': 'Visa Teste', 'dia_fechamento': 3, 'dia_vencimento': 10,
                                                   'limite_credito': '5000.00', 'observacoes': 'ficticio'},
            str(uuid.uuid4()))
    item = sql(banco, 'select * from public.item_despesa where id = %s', (r['cartao_id'],))[0]
    cfg = sql(banco, 'select * from public.config_agregador where item_despesa_id = %s', (r['cartao_id'],))[0]
    assert (item['tipo'], item['perfil_financeiro_id'], item['ativo'], item['recorrente'], item['tipo_recorrencia']) == \
        ('Agregador', ID['PESSOAL'], True, True, 'mensal')
    assert (cfg['dia_fechamento'], cfg['dia_vencimento'], cfg['limite_credito'], cfg['numero_cartao'],
            cfg['codigo_seguranca']) == (3, 10, Decimal('5000.00'), None, None)
    assert 'Visa Teste' in [c['nome'] for c in cartoes(banco)]


@pytest.mark.parametrize('dados, mensagem', [
    ({'nome': 'X', 'dia_fechamento': 3, 'dia_vencimento': 10, 'numero_cartao': '4111111111111111'}, 'Numero'),
    ({'nome': 'X', 'dia_fechamento': 3, 'dia_vencimento': 10, 'codigo_seguranca': '123'}, 'codigo de seguranca'),
    ({'nome': '', 'dia_fechamento': 3, 'dia_vencimento': 10}, 'Nome'),
    ({'nome': 'X', 'dia_fechamento': 0, 'dia_vencimento': 10}, 'entre 1 e 31'),
    ({'nome': 'X', 'dia_fechamento': 3, 'dia_vencimento': 32}, 'entre 1 e 31'),
    ({'nome': 'X', 'dia_fechamento': 3, 'dia_vencimento': 10, 'limite_credito': '-1'}, 'Limite'),
])
def test_cadastro_de_cartao_invalido_recusado(banco, dados, mensagem):
    antes = digital(banco, tabelas=('item_despesa', 'config_agregador'))
    with pytest.raises(errors.InvalidParameterValue, match=mensagem):
        rpc(banco, 'criar_cartao', ID['PESSOAL'], dados, str(uuid.uuid4()))
    assert digital(banco, tabelas=('item_despesa', 'config_agregador')) == antes


def test_numero_completo_e_cvv_nunca_saem_do_banco(banco):
    sql(banco, "update public.config_agregador set numero_cartao = '4111 2222 3333 4444', codigo_seguranca = '987', "
               "data_validade = '12/2031' where item_despesa_id = %s", (CARTAO,))
    lista = cartoes(banco)
    texto = json.dumps(lista)
    assert next(c for c in lista if c['id'] == CARTAO)['final_numero'] == '4444'
    for sensivel in ('4111', '2222', '3333', '987', '12/2031', 'numero_cartao', 'codigo_seguranca'):
        assert sensivel not in texto


def test_edicao_do_cartao_com_versao_e_faturas_existentes_preservadas(banco):
    comprar(banco)
    venc_antes = fatura(banco, CARTAO, D(2029, 5, 1))['data_vencimento']
    versao = next(c for c in cartoes(banco) if c['id'] == CARTAO)['versao']
    rpc(banco, 'editar_cartao', ID['PESSOAL'], CARTAO, versao, {'nome': 'Cartao Renomeado', 'dia_vencimento': 15})
    with pytest.raises(errors.RaiseException, match='alterado por outra operacao'):
        rpc(banco, 'editar_cartao', ID['PESSOAL'], CARTAO, versao, {'nome': 'De novo'})
    assert fatura(banco, CARTAO, D(2029, 5, 1))['data_vencimento'] == venc_antes == D(2029, 5, 31)
    comprar(banco, mes_fatura='2029-09-01', total_parcelas=1)
    assert fatura(banco, CARTAO, D(2029, 9, 1))['data_vencimento'] == D(2029, 9, 15)  # novo dia so nas proximas
    with pytest.raises(errors.InvalidParameterValue, match='Numero'):
        rpc(banco, 'editar_cartao', ID['PESSOAL'], CARTAO, next(c for c in cartoes(banco) if c['id'] == CARTAO)['versao'],
            {'numero_cartao': '1'})


def test_inativacao_nao_exclui_e_preserva_compras_e_faturas(banco):
    r = comprar(banco)
    antes = (md5_faturas(banco), [p['id'] for p in parcelas(banco, r['compra_id'])])
    versao = next(c for c in cartoes(banco) if c['id'] == CARTAO)['versao']
    rpc(banco, 'inativar_cartao', ID['PESSOAL'], CARTAO, versao)
    assert sql(banco, 'select ativo from public.item_despesa where id = %s', (CARTAO,))[0]['ativo'] is False
    assert (md5_faturas(banco), [p['id'] for p in parcelas(banco, r['compra_id'])]) == antes
    assert CARTAO not in faturas(banco, '2029-05-01')
    with pytest.raises(errors.InvalidParameterValue, match='inativo'):
        comprar(banco)


# ---------------------------------------------------------------------------
# 3-8. Compras: a vista, parcelada, centavos, virada, fechamento, vencimento
# ---------------------------------------------------------------------------

def test_compra_a_vista_cria_fatura_e_recalcula_como_o_flask(banco):
    r = comprar(banco, total_parcelas=1, valor='120.00')
    [p] = parcelas(banco, r['compra_id'])
    assert (p['valor'], p['mes_fatura'], p['data_compra'], p['numero_parcela'], p['total_parcelas'], p['categoria_id'],
            p['categoria_cartao_id'], p['perfil_financeiro_id'], p['is_recorrente']) == \
        (Decimal('120.00'), D(2029, 5, 1), D(2029, 5, 10), 1, 1, ASSINATURAS, 961, ID['PESSOAL'], False)
    f = fatura(banco, CARTAO, D(2029, 5, 1))
    assert (f['valor_planejado'], f['valor_executado'], f['valor'], f['estouro_orcamento'], f['status_pagamento'],
            f['data_vencimento'], f['descricao']) == \
        (Decimal('500.00'), Decimal('120.00'), Decimal('500.00'), False, 'Pendente', D(2029, 5, 31),
         'Fatura Cartao Teste - 05/2029')


def test_compra_parcelada_distribui_centavos_e_meses(banco):
    r = comprar(banco)
    ps = parcelas(banco, r['compra_id'])
    assert [(p['numero_parcela'], p['valor'], p['mes_fatura'], p['data_compra']) for p in ps] == [
        (1, Decimal('33.34'), D(2029, 5, 1), D(2029, 5, 10)),
        (2, Decimal('33.33'), D(2029, 6, 1), D(2029, 6, 10)),
        (3, Decimal('33.33'), D(2029, 7, 1), D(2029, 7, 10)),
    ]
    assert len({p['compra_id'] for p in ps}) == 1 and all(p['total_parcelas'] == 3 for p in ps)
    assert [fatura(banco, CARTAO, D(2029, m, 1))['valor_executado'] for m in (5, 6, 7)] == \
        [Decimal('33.34'), Decimal('33.33'), Decimal('33.33')]


@pytest.mark.parametrize('valor, n, esperado', [
    ('0.05', 3, ['0.02', '0.02', '0.01']),
    ('1000.00', 7, ['142.86'] * 5 + ['142.85'] * 2),
    ('99.99', 12, ['8.34'] * 3 + ['8.33'] * 9),
])
def test_arredondamento_monetario_soma_exata(banco, valor, n, esperado):
    r = comprar(banco, valor=valor, total_parcelas=n)
    valores = [p['valor'] for p in parcelas(banco, r['compra_id'])]
    assert sum(valores) == Decimal(valor)
    assert valores == [Decimal(v) for v in esperado]
    assert max(valores) - min(valores) <= Decimal('0.01')
    prev = previa_compra(banco, valor=valor, total_parcelas=n)
    assert Decimal(str(prev['soma'])) == Decimal(valor) and len(prev['parcelas']) == n


@pytest.mark.parametrize('campos, mensagem', [
    ({'valor': '0.02', 'total_parcelas': 3}, 'Parcelas'),
    ({'valor': '10.001'}, '2 casas'),
    ({'valor': '-5'}, 'positivo'),
    ({'total_parcelas': 61}, 'Parcelas'),
    ({'descricao': '  '}, 'Descricao'),
    ({'categoria_id': 999999}, 'Categoria'),
    ({'mes_fatura': '2031-01-01'}, '12 meses'),
    ({'cartao_id': SEM_CONFIG}, 'vencimento'),
    ({'data_compra': 'ontem'}, 'invalidos'),
])
def test_compra_invalida_recusada_sem_gravar(banco, campos, mensagem):
    antes = (digital(banco, tabelas=('lancamento_agregado',)), md5_faturas(banco))
    with pytest.raises(errors.InvalidParameterValue, match=mensagem):
        comprar(banco, **campos)
    assert (digital(banco, tabelas=('lancamento_agregado',)), md5_faturas(banco)) == antes


def test_virada_de_mes_e_de_ano_com_dia_31(banco):
    r = comprar(banco, data_compra='2029-10-31', mes_fatura='2029-11-01', total_parcelas=4, valor='400.00')
    assert [(p['mes_fatura'], p['data_compra']) for p in parcelas(banco, r['compra_id'])] == [
        (D(2029, 11, 1), D(2029, 10, 31)), (D(2029, 12, 1), D(2029, 11, 30)),
        (D(2030, 1, 1), D(2029, 12, 31)), (D(2030, 2, 1), D(2030, 1, 31)),
    ]


def test_fechamento_mes_da_fatura_e_o_escolhido_como_no_flask(banco):
    """O Flask nao deriva a fatura do dia de fechamento: vale o mes informado (exibido na previa)."""
    prev = previa_compra(banco, data_compra='2029-05-28', mes_fatura='2029-06-01', total_parcelas=1)
    assert prev['parcelas'][0]['mes_fatura'] == '2029-06-01'
    r = comprar(banco, data_compra='2029-05-28', mes_fatura='2029-05-01', total_parcelas=1)  # depois do fechamento (25)
    assert parcelas(banco, r['compra_id'])[0]['mes_fatura'] == D(2029, 5, 1)


def test_vencimento_da_fatura_pelo_dia_contratual(banco):
    r = comprar(banco, mes_fatura='2028-01-01', data_compra='2028-01-02', total_parcelas=4, valor='40.00')
    assert [fatura(banco, CARTAO, p['mes_fatura'])['data_vencimento'] for p in parcelas(banco, r['compra_id'])] == \
        [D(2028, 1, 31), D(2028, 2, 29), D(2028, 3, 31), D(2028, 4, 30)]


# ---------------------------------------------------------------------------
# 9, 10, 11, 20. Fatura paga, pendente, previsto por categoria, sem dupla contagem
# ---------------------------------------------------------------------------

def test_fatura_paga_nao_recebe_compra_e_as_parcelas_andam_juntas(banco):
    comprar(banco, total_parcelas=1, valor='10.00')
    pagar(banco, CARTAO, D(2029, 5, 1))
    paga_antes = fatura(banco, CARTAO, D(2029, 5, 1))
    prev = previa_compra(banco)
    assert [(p['mes_fatura'], p['redirecionada']) for p in prev['parcelas']] == \
        [('2029-06-01', True), ('2029-07-01', True), ('2029-08-01', True)]
    r = comprar(banco)
    assert [p['mes_fatura'] for p in parcelas(banco, r['compra_id'])] == [D(2029, 6, 1), D(2029, 7, 1), D(2029, 8, 1)]
    assert fatura(banco, CARTAO, D(2029, 5, 1)) == paga_antes  # valores da fatura paga intactos


def test_fatura_pendente_e_previsto_por_categoria_igual_a_tela_de_contas(banco):
    comprar(banco, total_parcelas=1, valor='120.00')                                  # 952 -> 961 (limite 500)
    comprar(banco, total_parcelas=1, valor='50.00', categoria_id=MORADIA)             # sem categoria do cartao
    f = faturas(banco, '2029-05-01')[CARTAO]
    # executado 170; complemento: 961 (500 - 120) + 963 (200, limite legado ativo) = 580
    assert (f['situacao'], Decimal(str(f['valor_executado'])), Decimal(str(f['valor_previsto'])), f['compras']) == \
        ('ABERTA', Decimal('170.00'), Decimal('750.00'), 2)
    tela = tabela(banco, 'contas_do_mes', ID['PESSOAL'], '2029-05-01')
    assert Decimal(str(next(c for c in tela if c['id'] == f['fatura_id'])['valor'])) == Decimal('750.00')
    gravada = fatura(banco, CARTAO, D(2029, 5, 1))
    assert (gravada['valor_executado'], gravada['valor_planejado'], gravada['estouro_orcamento']) == \
        (Decimal('170.00'), Decimal('500.00'), False)  # planejado do Flask: so limites do perfil
    comprar(banco, total_parcelas=1, valor='400.00')
    assert fatura(banco, CARTAO, D(2029, 5, 1))['estouro_orcamento'] is True


def test_fatura_paga_mostra_o_executado(banco):
    comprar(banco, total_parcelas=1, valor='120.00')
    pagar(banco, CARTAO, D(2029, 5, 1))
    f = faturas(banco, '2029-05-01')[CARTAO]
    assert (f['situacao'], Decimal(str(f['valor_previsto']))) == ('PAGA', Decimal('120.00'))


def test_sem_dupla_contagem_entre_compras_parcelas_e_faturas(banco):
    r = comprar(banco, valor='300.00', total_parcelas=3)
    comprar(banco, total_parcelas=1, valor='20.00', mes_fatura='2029-06-01')
    soma = sum(p['valor'] for p in parcelas(banco, r['compra_id']))
    assert soma == Decimal('300.00')
    for mes, esperado in (('2029-05-01', '100.00'), ('2029-06-01', '120.00'), ('2029-07-01', '100.00')):
        f = faturas(banco, mes)[CARTAO]
        assert Decimal(str(f['valor_executado'])) == Decimal(esperado)
        assert len(tabela(banco, 'compras_da_fatura', ID['PESSOAL'], CARTAO, mes)) == f['compras']
    n = sql(banco, "select count(*) as n from public.conta where is_fatura_cartao and item_despesa_id = %s", (CARTAO,))
    assert n[0]['n'] == 3


# ---------------------------------------------------------------------------
# 12, 13. Unicidade da fatura e recorrencia no cartao
# ---------------------------------------------------------------------------

def test_fatura_criada_por_outra_transacao_e_reaproveitada(banco):
    """Como o Flask (get_or_create_fatura) criando a mesma fatura ao mesmo tempo: o indice unico decide."""
    outra = psycopg2.connect(banco)
    cur = outra.cursor()
    cur.execute("insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, "
                "valor_planejado, valor_executado, data_vencimento, status_pagamento, is_fatura_cartao, "
                "cartao_competencia, estouro_orcamento, debito_automatico, status_fatura) "
                "values (%s, %s, '2029-05-01', 'Fatura Cartao Teste - 05/2029', 500, 500, 0, '2029-05-31', 'Pendente', "
                "true, '2029-05-01', false, false, 'ABERTA')", (ID['PESSOAL'], CARTAO))
    resultado = {}
    tarefa = threading.Thread(target=lambda: resultado.setdefault('r', comprar(banco, total_parcelas=1)))
    tarefa.start()
    time.sleep(1.5)
    assert tarefa.is_alive()  # espera o indice unico
    outra.commit()
    outra.close()
    tarefa.join(30)
    assert resultado['r']['lancamentos']
    assert fatura(banco, CARTAO, D(2029, 5, 1))['valor_executado'] == Decimal('100.00')


def test_compras_simultaneas_no_mesmo_cartao_uma_fatura_e_soma_exata(banco):
    resultados = _paralelo([lambda v=v: comprar(banco, total_parcelas=1, valor=v) for v in ('10.00', '20.00', '30.00')])
    assert [r[0] for r in resultados] == ['ok'] * 3
    assert fatura(banco, CARTAO, D(2029, 5, 1))['valor_executado'] == Decimal('60.00')


def test_recorrencia_do_cartao_nao_e_editada_aqui_e_convive_com_a_compra(banco):
    atribuir(banco, 'PESSOAL')
    edic = edicao(banco, 970)  # compra recorrente ja gravada pelo Flask
    assert edic['abertas'] == 0 and 'recorrencia' in edic['parcelas'][0]['bloqueio']
    with pytest.raises(errors.RaiseException, match='recorrencia'):
        editar(banco, 970, {'descricao': 'X'})
    comprar(banco, mes_fatura='2027-03-01', data_compra='2027-03-02', total_parcelas=1, valor='15.00')
    gerar(banco, previa(banco)['a_gerar'])  # gera o streaming de 03/2027 no mesmo cartao
    assert fatura(banco, CARTAO, D(2027, 3, 1)) is not None  # uma so (o indice impede outra)
    f = faturas(banco, '2027-03-01')[CARTAO]
    assert Decimal(str(f['valor_executado'])) == Decimal('54.90') and f['compras'] == 2


def test_compra_concorrente_com_a_geracao_de_recorrencias(banco):
    atribuir(banco, 'PESSOAL')
    total = previa(banco)['a_gerar']
    resultados = _paralelo([
        lambda: gerar(banco, total),
        lambda: comprar(banco, mes_fatura='2027-03-01', data_compra='2027-03-02', total_parcelas=2, valor='15.00'),
    ])
    geracao, compra = resultados
    assert compra[0] == 'ok', resultados
    if geracao[0] == 'erro':  # a compra venceu e criou as faturas: a previa mudou e a geracao pede nova confirmacao
        assert 'previa mudou' in str(geracao[1])
        gerar(banco, previa(banco)['a_gerar'])
    n = sql(banco, "select cartao_competencia, count(*) as n from public.conta where is_fatura_cartao "
                   "group by 1 having count(*) > 1")
    assert n == []
    f = faturas(banco, '2027-03-01')[CARTAO]
    assert Decimal(str(f['valor_executado'])) == Decimal('47.40')  # 39.90 + 7.50


# ---------------------------------------------------------------------------
# 14, 15. Exclusao e edicao seguras; concorrencia
# ---------------------------------------------------------------------------

def test_exclusao_remove_parcelas_abertas_e_recalcula(banco):
    r = comprar(banco)
    excluir(banco, r['lancamentos'][1])
    assert parcelas(banco, r['compra_id']) == []
    assert [fatura(banco, CARTAO, D(2029, m, 1))['valor_executado'] for m in (5, 6, 7)] == [Decimal('0')] * 3


def test_parcelas_em_fatura_paga_ficam_e_as_abertas_saem(banco):
    r = comprar(banco)
    pagar(banco, CARTAO, D(2029, 5, 1))
    edic = edicao(banco, r['lancamentos'][0])
    assert edic['abertas'] == 2 and 'paga' in edic['parcelas'][0]['bloqueio']
    saida = excluir(banco, r['lancamentos'][0])
    assert saida == {'excluidas': 2, 'preservadas': 1}
    [restante] = parcelas(banco, r['compra_id'])
    assert (restante['numero_parcela'], restante['mes_fatura']) == (1, D(2029, 5, 1))  # historico, mesmo compra_id
    with pytest.raises(errors.RaiseException, match='Fatura paga'):
        excluir(banco, restante['id'])


def test_fatura_fechada_bloqueia_edicao(banco):
    r = comprar(banco, total_parcelas=1)
    sql(banco, "update public.conta set status_fatura = 'FECHADA' where is_fatura_cartao and cartao_competencia = '2029-05-01'")
    with pytest.raises(errors.RaiseException, match='fechada'):
        editar(banco, r['lancamentos'][0], {'descricao': 'Outro'})


def test_edicao_de_compra_a_vista_e_parcelada(banco):
    av = comprar(banco, total_parcelas=1, valor='50.00')
    editar(banco, av['lancamentos'][0], {'valor': '70.00', 'mes_fatura': '2029-06-01', 'categoria_id': MORADIA})
    [p] = parcelas(banco, av['compra_id'])
    assert (p['valor'], p['mes_fatura'], p['categoria_id'], p['categoria_cartao_id']) == \
        (Decimal('70.00'), D(2029, 6, 1), MORADIA, None)
    assert fatura(banco, CARTAO, D(2029, 5, 1))['valor_executado'] == Decimal('0')
    assert fatura(banco, CARTAO, D(2029, 6, 1))['valor_executado'] == Decimal('70.00')
    pa = comprar(banco)
    editar(banco, pa['lancamentos'][0], {'descricao': 'Notebook novo', 'observacoes': 'nota'})
    assert {p['descricao'] for p in parcelas(banco, pa['compra_id'])} == {'Notebook novo'}
    with pytest.raises(errors.InvalidParameterValue, match='parcelada'):
        editar(banco, pa['lancamentos'][0], {'valor': '1.00'})


def test_edicoes_simultaneas_da_mesma_versao_so_uma_vale(banco):
    r = comprar(banco, total_parcelas=1)
    versao = edicao(banco, r['lancamentos'][0])['versao']
    resultados = _paralelo([lambda v=v: editar(banco, r['lancamentos'][0], {'valor': v}, versao=versao)
                            for v in ('40.00', '50.00')])
    assert sorted(x[0] for x in resultados) == ['erro', 'ok']
    assert 'alterada por outra operacao' in str(next(x[1] for x in resultados if x[0] == 'erro'))


def test_compra_numa_fatura_sendo_paga_espera_e_e_recusada(banco):
    comprar(banco, total_parcelas=1, valor='10.00')
    pagamento = psycopg2.connect(banco)
    cur = pagamento.cursor()
    cur.execute("update public.conta set status_pagamento = 'Pago' where is_fatura_cartao and cartao_competencia = '2029-05-01'")
    resultado = {}

    def tentar():
        try:
            comprar(banco, total_parcelas=1)
        except Exception as exc:  # noqa: BLE001
            resultado['erro'] = exc

    tarefa = threading.Thread(target=tentar)
    tarefa.start()
    time.sleep(1.5)
    assert tarefa.is_alive()
    pagamento.commit()
    pagamento.close()
    tarefa.join(30)
    assert 'foi paga durante o cadastro' in str(resultado['erro'])
    assert fatura(banco, CARTAO, D(2029, 5, 1))['valor_executado'] == Decimal('10.00')


def test_edicao_durante_um_pagamento_espera_e_e_bloqueada(banco):
    r = comprar(banco, total_parcelas=1)
    versao = edicao(banco, r['lancamentos'][0])['versao']
    pagamento = psycopg2.connect(banco)
    cur = pagamento.cursor()
    cur.execute("update public.conta set status_pagamento = 'Pago' where is_fatura_cartao and cartao_competencia = '2029-05-01'")
    resultado = {}

    def tentar():
        try:
            editar(banco, r['lancamentos'][0], {'valor': '1.00'}, versao=versao)
        except Exception as exc:  # noqa: BLE001
            resultado['erro'] = exc

    tarefa = threading.Thread(target=tentar)
    tarefa.start()
    time.sleep(1.5)
    assert tarefa.is_alive()
    pagamento.commit()
    pagamento.close()
    tarefa.join(30)
    assert 'Operacao bloqueada' in str(resultado['erro'])
    assert parcelas(banco, r['compra_id'])[0]['valor'] == Decimal('100.00')


# ---------------------------------------------------------------------------
# 16. Idempotencia
# ---------------------------------------------------------------------------

def test_mesma_chave_nao_duplica_nem_em_paralelo(banco):
    chave = str(uuid.uuid4())
    resultados = _paralelo([lambda: comprar(banco, chave=chave) for _ in range(3)])
    assert [r[0] for r in resultados] == ['ok'] * 3
    assert len({r[1]['compra_id'] for r in resultados}) == 1
    assert sql(banco, "select count(*) as n from public.lancamento_agregado where descricao = 'Notebook'")[0]['n'] == 3
    with pytest.raises(errors.InvalidParameterValue, match='ja usada'):
        comprar(banco, {**COMPRA, 'cartao_id': CARTAO_B}, perfil='PERFIL_B', usuario=USUARIO_B, chave=chave)


# ---------------------------------------------------------------------------
# 17, 18. Perfis e acesso anonimo
# ---------------------------------------------------------------------------

def test_leitor_ve_mas_nao_escreve(banco):
    sql(banco, "update financeiro.perfil_acesso set papel = 'LEITOR', pode_gerir = false "
               "where perfil_financeiro_id = %s", (ID['PESSOAL'],))
    assert CARTAO in faturas(banco, '2029-05-01')
    assert previa_compra(banco)['parcelas']
    for chamada in (lambda: comprar(banco),
                    lambda: rpc(banco, 'criar_cartao', ID['PESSOAL'], {'nome': 'X', 'dia_fechamento': 1,
                                                                       'dia_vencimento': 2}, str(uuid.uuid4())),
                    lambda: rpc(banco, 'inativar_cartao', ID['PESSOAL'], CARTAO, 'x'),
                    lambda: rpc(banco, 'editar_compra', ID['PESSOAL'], 970, 'x', {}),
                    lambda: rpc(banco, 'excluir_compra', ID['PESSOAL'], 970, 'x')):
        with pytest.raises(errors.InsufficientPrivilege):
            chamada()
    assert not tabela(banco, 'compras_da_fatura', ID['PESSOAL'], CARTAO, '2027-01-01')[0]['pode_editar']


@pytest.mark.parametrize('usuario, perfil, cartao', [
    (USUARIO_B, 'PESSOAL', CARTAO),        # perfil de outro usuario
    (USUARIO_A, 'PERFIL_B', CARTAO_B),
    (USUARIO_A, 'INATIVO_A', CARTAO),      # vinculo com gestao, perfil inativo
    (USUARIO_A, 'PESSOAL', CARTAO_B),      # cartao de outro perfil
])
def test_outro_usuario_ou_perfil_nao_alcanca(banco, usuario, perfil, cartao):
    with pytest.raises(errors.InsufficientPrivilege):
        comprar(banco, {**COMPRA, 'cartao_id': cartao}, perfil=perfil, usuario=usuario)
    if cartao == CARTAO:
        with pytest.raises(errors.InsufficientPrivilege):
            edicao(banco, 970, perfil=perfil, usuario=usuario)


@pytest.mark.parametrize('comando', [
    "select financeiro.cartoes_do_perfil(101)",
    "select financeiro.faturas_do_mes(101, '2029-05-01')",
    "select financeiro.compras_da_fatura(101, 910, '2029-05-01')",
    "select financeiro.compra_para_edicao(101, 970)",
    "select financeiro.previa_compra(101, '{}'::jsonb)",
    "select financeiro.criar_compra(101, '{}'::jsonb, gen_random_uuid())",
    "select financeiro.editar_compra(101, 970, 'x', '{}'::jsonb)",
    "select financeiro.excluir_compra(101, 970, 'x')",
    "select financeiro.criar_cartao(101, '{}'::jsonb, gen_random_uuid())",
    "select financeiro.editar_cartao(101, 910, 'x', '{}'::jsonb)",
    "select financeiro.inativar_cartao(101, 910, 'x')",
])
def test_anonimo_nao_executa(banco, comando):
    with pytest.raises(errors.InsufficientPrivilege):
        chamar(banco, None, comando)


@pytest.mark.parametrize('comando', [
    "select financeiro.garantir_fatura(101, 910, '2029-05-01')",
    "select financeiro.recalcular_fatura(101, 910, '2029-05-01')",
    "select * from financeiro.plano_compra(101, '{}'::jsonb)",
    "select financeiro.travar_compra(101, 970, 'x')",
    "select financeiro.fatura_esta_paga(1)",
    "select * from financeiro.operacao_cartao",
    "select * from public.lancamento_agregado",
])
def test_navegador_nao_acessa_funcoes_internas_nem_tabelas(banco, comando):
    with pytest.raises(errors.InsufficientPrivilege):
        chamar(banco, USUARIO_A, comando)


# ---------------------------------------------------------------------------
# 19. Movimentos, saldos e demais contas intactos
# ---------------------------------------------------------------------------

def test_operacoes_nao_tocam_movimentos_saldos_nem_contas_comuns(banco):
    comuns = "select coalesce(md5(string_agg(t::text, '|' order by id)), '') as h from public.conta t where not is_fatura_cartao"
    antes = (digital(banco, tabelas=('conta_bancaria', 'movimento_financeiro', 'categoria', 'categoria_cartao',
                                     'cartao_categoria_limite')), sql(banco, comuns))
    r = comprar(banco)
    editar(banco, r['lancamentos'][0], {'descricao': 'Outro'})
    excluir(banco, r['lancamentos'][0])
    c = rpc(banco, 'criar_cartao', ID['PESSOAL'], {'nome': 'Novo', 'dia_fechamento': 1, 'dia_vencimento': 8},
            str(uuid.uuid4()))
    rpc(banco, 'inativar_cartao', ID['PESSOAL'], c['cartao_id'],
        next(x for x in cartoes(banco) if x['id'] == c['cartao_id'])['versao'])
    depois = (digital(banco, tabelas=('conta_bancaria', 'movimento_financeiro', 'categoria', 'categoria_cartao',
                                      'cartao_categoria_limite')), sql(banco, comuns))
    assert depois == antes


# ---------------------------------------------------------------------------
# Equivalencia com o Flask real (mesmos dados ficticios)
# ---------------------------------------------------------------------------

def _sem_ids(linha, extra=()):
    return {k: v for k, v in linha.items() if k not in ('id', 'criado_em', 'compra_id', *extra)}


def _flask_pessoal(dsn):
    sql(dsn, 'update public.config_agregador set dia_vencimento = 10 where item_despesa_id = %s', (CARTAO,))  # o Flask
    # quebra com dia 31 em mes de 30 dias (date.replace); o novo usa o dia contratual


def test_equivalencia_com_o_flask_nas_compras(cluster):  # noqa: F811
    dsn_flask, dsn_novo = copiar(cluster), copiar(cluster)
    for dsn in (dsn_flask, dsn_novo):
        _flask_pessoal(dsn)
    compras = [{**COMPRA}, {**COMPRA, 'descricao': 'Cafe', 'valor': '0.05', 'total_parcelas': 1,
                            'categoria_id': MORADIA, 'data_compra': '2029-06-03', 'mes_fatura': '2029-06-01'},
               {**COMPRA, 'descricao': 'Sofa', 'valor': '1000.00', 'total_parcelas': 7, 'data_compra': '2029-10-31',
                'mes_fatura': '2029-11-01', 'observacoes': 'loja'}]
    saida = flask(dsn_flask, [['post', f'/api/cartoes/{CARTAO}/lancamentos', {k: v for k, v in c.items() if k != 'cartao_id'}]
                              for c in compras])
    assert [s['status'] for s in saida] == [201] * 3, saida
    for c in compras:
        comprar(dsn_novo, c)
    consulta = ('select * from public.lancamento_agregado where cartao_id = %s and not coalesce(is_recorrente, false) '
                'order by descricao, numero_parcela')
    f = [_sem_ids(x) for x in sql(dsn_flask, consulta, (CARTAO,))]
    n = [_sem_ids(x) for x in sql(dsn_novo, consulta, (CARTAO,))]
    assert len(f) == 11 and f == n
    faturas_sql = 'select * from public.conta where is_fatura_cartao order by cartao_competencia'
    assert [_sem_ids(x) for x in sql(dsn_flask, faturas_sql)] == [_sem_ids(x) for x in sql(dsn_novo, faturas_sql)]


def test_equivalencia_com_o_flask_no_cadastro_do_cartao(cluster):  # noqa: F811
    dsn_flask, dsn_novo = copiar(cluster), copiar(cluster)
    dados = {'nome': 'Master Teste', 'dia_fechamento': 3, 'dia_vencimento': 10, 'limite_credito': '2500.00',
             'observacoes': 'ficticio'}
    assert flask(dsn_flask, [['post', '/api/cartoes', dados]])[0]['status'] == 201
    rpc(dsn_novo, 'criar_cartao', ID['PESSOAL'], dados, str(uuid.uuid4()))
    consulta = ("select i.*, row_to_json(c)::jsonb - 'id' - 'item_despesa_id' - 'criado_em' as cfg "
                "from public.item_despesa i join public.config_agregador c on c.item_despesa_id = i.id "
                "where i.nome = 'Master Teste'")
    assert [_sem_ids(x) for x in sql(dsn_flask, consulta)] == [_sem_ids(x) for x in sql(dsn_novo, consulta)]


def test_correcao_intencional_flask_altera_parcela_de_fatura_paga_e_o_novo_bloqueia(cluster):  # noqa: F811
    dsn = copiar(cluster)
    _flask_pessoal(dsn)
    r = comprar(dsn, total_parcelas=1)
    pagar(dsn, CARTAO, D(2029, 5, 1))
    fatura_antes = fatura(dsn, CARTAO, D(2029, 5, 1))
    with pytest.raises(errors.RaiseException, match='Fatura paga'):
        editar(dsn, r['lancamentos'][0], {'descricao': 'X'})
    saida = flask(dsn, [['put', f"/api/cartoes/lancamentos/{r['lancamentos'][0]}", {'valor': '1.00'}]])
    assert saida[0]['status'] == 200  # defeito do Flask: altera compra de fatura paga, sem recalcular
    assert parcelas(dsn, r['compra_id'])[0]['valor'] == Decimal('1.00')
    assert fatura(dsn, CARTAO, D(2029, 5, 1)) == fatura_antes
