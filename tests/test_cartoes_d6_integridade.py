"""
Testes FIN-CARTOES-D6-INTEGRIDADE-1 — nenhum caminho de escrita altera fatura consolidada em silencio.

Bancos ISOLADOS e dados FICTICIOS: copia do cluster PostgreSQL descartavel (cenario do FIN-RECORRENCIA-1:
perfil "Pessoal" ficticio 101, Cartao Teste 910, recorrencia "Streaming" 906 no cartao; base do
FIN-PAGAMENTO-TRAVA-1 com a fatura de 06/2027 e duas compras do Flask). Nunca o gastos.db nem o Supabase.

Flask real em processo proprio (conexao e transacao proprias); novo aplicativo como `authenticated`.
"Consolidar" = o mesmo que a consolidacao do Flask (FECHADA, valor_consolidado = executado) ou a propria rota.
"""
import json
import threading
import uuid
from datetime import date
from decimal import Decimal

import pytest

from tests.test_fatura_integridade import Flask as FlaskServico
from tests.test_fatura_integridade import compras, importada, md5_pagas, sem_duplicidade
from tests.test_pagamento_trava import (  # noqa: F401  (fixtures reaproveitadas)
    CARTAO,
    FATURA_MES,
    PERFIL,
    base,
    conta,
    http,
    pagar_corpo,
    pg,
)
from tests.test_supabase_fatura_unica import aguardar_bloqueio, em_thread
from tests.test_supabase_recorrencia import (  # noqa: F401
    PG_BIN,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,
    gerar,
    previa,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
from psycopg2 import errors  # noqa: E402

pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

D = date
STREAMING, MORADIA = 906, 951


def consolidar(dsn, mes, cartao=CARTAO):
    """Como a consolidacao do Flask (cria a fatura vazia se faltar)."""
    if not sql(dsn, 'select 1 from public.conta where is_fatura_cartao and item_despesa_id = %s and cartao_competencia = %s',
               (cartao, mes)):
        sql(dsn, "insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, "
                 "valor_planejado, valor_executado, data_vencimento, status_pagamento, is_fatura_cartao, cartao_competencia, "
                 "estouro_orcamento, debito_automatico, status_fatura) values (%s, %s, %s, 'Fatura teste', 0, 0, 0, %s, "
                 "'Pendente', true, %s, false, false, 'ABERTA')", (PERFIL, cartao, mes, mes[:8] + '10', mes))
    sql(dsn, "update public.conta set status_fatura = 'FECHADA', valor_consolidado = valor_executado, data_consolidacao = now() "
             "where is_fatura_cartao and item_despesa_id = %s and cartao_competencia = %s", (cartao, mes))
    return sql(dsn, 'select * from public.conta where is_fatura_cartao and item_despesa_id = %s and cartao_competencia = %s',
               (cartao, mes))[0]


def md5_fatura(dsn, fatura_id):
    return sql(dsn, 'select md5(t::text) as h from public.conta t where id = %s', (fatura_id,))[0]['h']


def md5_compras_do_mes(dsn, mes, cartao=CARTAO):
    return sql(dsn, "select coalesce(md5(string_agg(t::text, '|' order by id)), '') as h from public.lancamento_agregado t "
                    'where cartao_id = %s and mes_fatura = %s', (cartao, mes))[0]['h']


def auditoria(dsn, fatura_id):
    return sql(dsn, 'select * from public.fatura_consolidada_inclusao where fatura_id = %s order by id', (fatura_id,))


def compra_base(dsn, descricao='Compra base 0'):
    return sql(dsn, 'select * from public.lancamento_agregado where descricao = %s', (descricao,))[0]


def criar_novo(dsn, dados, usuario=USUARIO_A, perfil=PERFIL):
    return chamar(dsn, usuario, 'select financeiro.criar_compra(%s, %s::jsonb, %s)', (perfil, json.dumps(dados),
                                                                                     str(uuid.uuid4())))


def compra_nova(descricao, mes, valor='10.00', **extra):
    return {'cartao_id': CARTAO, 'descricao': descricao, 'valor': valor, 'total_parcelas': 1,
            'data_compra': mes[:8] + '05', 'mes_fatura': mes, 'categoria_id': MORADIA, **extra}


# ---------------------------------------------------------------------------
# A. Faturas: aberta, consolidada, paga; confirmacao correta, errada e reutilizada; totais e auditoria
# ---------------------------------------------------------------------------

def test_confirmacao_reutilizada_e_recusada_e_auditoria_fecha_a_conta(pg):
    d = pg['dsn']
    f = consolidar(d, FATURA_MES)  # 250,00 das compras do Flask
    atribuir(d, 'PESSOAL')  # FIN-ESCRITOR-UNICO-FINAL-1: as escritas do novo aplicativo exigem o perfil atribuido a ele
    conf = [{'fatura_id': f['id'], 'total_consolidado': '250.00'}]
    criar_novo(d, compra_nova('Com confirmacao', FATURA_MES, '10.00', confirmar_consolidadas=conf))
    with pytest.raises(errors.RaiseException, match='consolidada') as erro:
        criar_novo(d, compra_nova('Reuso', FATURA_MES, '10.00', confirmar_consolidadas=conf))  # total ja e 260
    assert erro.value.diag.message_hint == 'CONSOLIDADA'
    criar_novo(d, compra_nova('Com a nova', FATURA_MES, '5.00',
                              confirmar_consolidadas=[{'fatura_id': f['id'], 'total_consolidado': '260.00'}]))
    a = auditoria(d, f['id'])
    assert [(x['total_consolidado_anterior'], x['valor_incluido'], x['total_consolidado_novo']) for x in a] == \
        [(Decimal('250.00'), Decimal('10.00'), Decimal('260.00')), (Decimal('260.00'), Decimal('5.00'), Decimal('265.00'))]
    depois = conta(d, f['id'])
    assert depois['valor_consolidado'] == a[-1]['total_consolidado_novo'] == depois['valor_executado'] == Decimal('265.00')


def test_confirmacao_nao_abre_fatura_paga(pg):
    d = pg['dsn']
    f = consolidar(d, FATURA_MES)
    atribuir(d, 'PESSOAL')  # FIN-ESCRITOR-UNICO-FINAL-1: as escritas do novo aplicativo exigem o perfil atribuido a ele
    sql(d, "update public.conta set status_pagamento = 'Pago' where id = %s", (f['id'],))
    antes = md5_fatura(d, f['id'])
    r = criar_novo(d, compra_nova('Paga', FATURA_MES, '10.00',
                                  confirmar_consolidadas=[{'fatura_id': f['id'], 'total_consolidado': '250.00'}]))
    assert md5_fatura(d, f['id']) == antes and auditoria(d, f['id']) == []
    assert compras(d, 'id = %s', (r['lancamentos'][0],))[0]['mes_fatura'] == D(2027, 7, 1)  # desvio da paga, como antes


# ---------------------------------------------------------------------------
# B. Recorrencias (D5 preservada): novo motor e Flask
# ---------------------------------------------------------------------------

def test_recorrencia_do_novo_motor_com_destino_consolidado_fica_rejeitada(pg):
    d = pg['dsn']
    atribuir(d, 'PESSOAL')
    marco = consolidar(d, '2027-03-01')
    antes = (md5_fatura(d, marco['id']), md5_compras_do_mes(d, '2027-03-01'))
    resumo = gerar(d, previa(d)['a_gerar'])
    motivo = next(r['motivo'] for r in resumo['rejeicoes'] if r['item_id'] == STREAMING and r['competencia'] == '2027-03-01')
    assert 'Fatura de 03/2027 consolidada' in motivo and 'sem confirmacao' in motivo
    # Abril (aberta) e gerada normalmente; marco nao recebe nada e nao vai para outro mes.
    streaming = compras(d, 'item_despesa_id = %s and mes_fatura >= %s', (STREAMING, D(2027, 3, 1)))
    assert [(x['mes_fatura'], x['mes_fatura_original']) for x in streaming] == [(D(2027, 4, 1), None)]
    assert (md5_fatura(d, marco['id']), md5_compras_do_mes(d, '2027-03-01')) == antes and auditoria(d, marco['id']) == []
    assert previa(d)['a_gerar'] == 0  # reexecucao: nada novo, nada duplicado
    assert sem_duplicidade(d)


def test_recorrencia_desviada_da_paga_para_consolidada_tambem_fica_rejeitada(pg):
    d = pg['dsn']
    atribuir(d, 'PESSOAL')
    sql(d, "update public.conta set status_pagamento = 'Pago' where id = %s", (consolidar(d, '2027-03-01')['id'],))
    abril = consolidar(d, '2027-04-01')
    rejeicoes = gerar(d, previa(d)['a_gerar'])['rejeicoes']
    motivos = {r['competencia']: r['motivo'] for r in rejeicoes if r['item_id'] == STREAMING}
    assert 'Fatura de 04/2027 consolidada' in motivos['2027-03-01'] and 'Fatura de 04/2027 consolidada' in motivos['2027-04-01']
    assert compras(d, 'item_despesa_id = %s and mes_fatura >= %s', (STREAMING, D(2027, 3, 1))) == []
    assert auditoria(d, abril['id']) == []


def test_fatura_consolidada_entre_previa_e_geracao_nao_recebe_nada(pg):
    d = pg['dsn']
    atribuir(d, 'PESSOAL')
    total = previa(d)['a_gerar']
    marco = consolidar(d, '2027-03-01')  # depois da previa
    antes = md5_compras_do_mes(d, '2027-03-01')
    with pytest.raises(errors.RaiseException, match='previa mudou|consolidada'):
        gerar(d, total)
    assert md5_compras_do_mes(d, '2027-03-01') == antes and auditoria(d, marco['id']) == []


def test_recorrencia_do_flask_com_destino_consolidado_nao_e_lancada(pg):
    d, p = pg['dsn'], pg['pasta']
    marco = consolidar(d, '2027-03-01')
    antes = (md5_fatura(d, marco['id']), md5_compras_do_mes(d, '2027-03-01'))
    for i in (1, 2):  # reexecucao nao duplica nem muda nada
        r = FlaskServico(d, p, f'rec{i}', acao='recorrencia', item=STREAMING, meses=2, mes='2027-03-01').resultado()
        assert 'erro' not in r
    streaming = compras(d, 'item_despesa_id = %s and mes_fatura >= %s', (STREAMING, D(2027, 3, 1)))
    assert [(x['mes_fatura'], x['mes_fatura_original']) for x in streaming] == [(D(2027, 4, 1), None)]
    assert (md5_fatura(d, marco['id']), md5_compras_do_mes(d, '2027-03-01')) == antes
    assert 'FIN-CARTOES-D6' in (p / 'rec1.err').read_text(errors='replace')  # ocorrencia registrada no log


def test_recorrencia_em_fatura_aberta_e_paga_continua_como_antes(pg):
    d, p = pg['dsn'], pg['pasta']
    sql(d, "update public.conta set status_pagamento = 'Pago' where id = %s", (consolidar(d, '2027-03-01')['id'],))
    sql(d, "update public.conta set status_fatura = 'ABERTA' where is_fatura_cartao and cartao_competencia = '2027-03-01'")
    FlaskServico(d, p, 'rec', acao='recorrencia', item=STREAMING, meses=2, mes='2027-03-01').resultado()
    streaming = compras(d, 'item_despesa_id = %s and mes_fatura >= %s', (STREAMING, D(2027, 3, 1)))
    assert [(x['mes_fatura'], x['mes_fatura_original']) for x in streaming] == \
        [(D(2027, 4, 1), D(2027, 3, 1)), (D(2027, 4, 1), None)]  # paga: desvio do FIN-FATURA-INTEGRIDADE-1


# ---------------------------------------------------------------------------
# C. Importacao (D5 preservada): competencia do arquivo mantida, consolidada recusada por compra
# ---------------------------------------------------------------------------

def test_importacao_recusa_compras_com_destino_consolidado_e_mantem_as_demais(pg):
    d, p = pg['dsn'], pg['pasta']
    maio = consolidar(d, '2028-05-01')
    antes = (md5_fatura(d, maio['id']), md5_compras_do_mes(d, '2028-05-01'))
    lote = [importada('Loja maio', '2028-05-01', compra_id='imp-maio'),
            importada('Loja junho', '2028-06-01', compra_id='imp-junho'),
            importada('Parcelada', '2028-05-01', '30.00', 1, 2, 'imp-parc'),
            importada('Parcelada', '2028-06-01', '30.00', 2, 2, 'imp-parc')]
    r = FlaskServico(d, p, 'imp', acao='importar', lancamentos=lote).resultado()
    assert r['inseridos'] == 1 and len(r['erros']) == 3
    assert any('Fatura de 05/2028 consolidada' in e and 'Loja maio' in e for e in r['erros'])
    assert any('Parcela 2/2' in e and '05/2028' in e for e in r['erros'])  # a compra nao e dividida
    assert [(x['descricao'], x['mes_fatura']) for x in compras(d, "descricao in ('Loja maio', 'Loja junho', 'Parcelada')")] == \
        [('Loja junho', D(2028, 6, 1))]  # competencia do arquivo mantida; nada levado para outro mes
    assert (md5_fatura(d, maio['id']), md5_compras_do_mes(d, '2028-05-01')) == antes and auditoria(d, maio['id']) == []
    r2 = FlaskServico(d, p, 'imp2', acao='importar', lancamentos=lote).resultado()  # reimportacao
    assert (r2['inseridos'], r2['duplicados'], len(r2['erros'])) == (0, 1, 3)


def test_recorrencia_importada_para_fatura_consolidada_e_recusada(pg):
    d, p = pg['dsn'], pg['pasta']
    maio = consolidar(d, '2028-05-01')
    antes = md5_compras_do_mes(d, '2028-05-01')
    linha = {'descricao': 'STREAMING', 'valor': '39.90', 'data_compra': '2028-05-03'}
    r = FlaskServico(d, p, 'vinc', acao='vincular_recorrencia', linha=linha, competencia='2028-05-01',
                     item=STREAMING).resultado()
    assert 'Fatura de 05/2028 consolidada' in r.get('erro', '')
    assert md5_compras_do_mes(d, '2028-05-01') == antes and auditoria(d, maio['id']) == []


# ---------------------------------------------------------------------------
# D. Flask: edicao e exclusao de compra e de fatura
# ---------------------------------------------------------------------------

def test_flask_edicao_em_fatura_aberta_continua_permitida(pg):
    d, p = pg['dsn'], pg['pasta']
    lanc = compra_base(d)
    r = http(d, p, 'ed', 'put', f"/api/cartoes/lancamentos/{lanc['id']}", {'valor': '210.00'}).resultado()
    assert r['status'] == 200 and compra_base(d)['valor'] == Decimal('210.00')


def test_flask_compra_de_fatura_consolidada_so_muda_campos_descritivos(pg):
    d, p = pg['dsn'], pg['pasta']
    f = consolidar(d, FATURA_MES)
    lanc = compra_base(d)
    antes = (md5_fatura(d, f['id']), md5_compras_do_mes(d, FATURA_MES))
    tentativas = [({'valor': '1.00'}, ['valor']), ({'mes_fatura': '2027-07'}, ['mes_fatura']),
                  ({'total_parcelas': 3}, ['total_parcelas']), ({'numero_parcela': 2}, ['numero_parcela'])]
    for corpo, campos in tentativas:
        r = http(d, p, f'ed{campos[0]}', 'put', f"/api/cartoes/lancamentos/{lanc['id']}", corpo).resultado()
        assert (r['status'], r['json']['codigo'], r['json']['campos']) == (409, 'FATURA_CONSOLIDADA', campos)
    exc = http(d, p, 'ex', 'delete', f"/api/cartoes/lancamentos/{lanc['id']}").resultado()
    assert (exc['status'], exc['json']['codigo']) == (409, 'FATURA_CONSOLIDADA')
    assert (md5_fatura(d, f['id']), md5_compras_do_mes(d, FATURA_MES)) == antes  # nada mudou
    ok = http(d, p, 'desc', 'put', f"/api/cartoes/lancamentos/{lanc['id']}",
              {'descricao': 'Nova descricao', 'observacoes': 'nota', 'valor': str(lanc['valor'])}).resultado()
    assert ok['status'] == 200  # mesmo valor reenviado nao e mudanca financeira
    depois = compra_base(d, 'Nova descricao')
    assert (depois['valor'], depois['mes_fatura'], depois['observacoes']) == (lanc['valor'], lanc['mes_fatura'], 'nota')
    assert md5_fatura(d, f['id']) == antes[0] and auditoria(d, f['id']) == []


def test_flask_compra_de_fatura_paga_continua_bloqueada(pg):
    d, p = pg['dsn'], pg['pasta']
    f = consolidar(d, FATURA_MES)
    sql(d, "update public.conta set status_pagamento = 'Pago' where id = %s", (f['id'],))
    lanc = compra_base(d)
    r = http(d, p, 'ed', 'put', f"/api/cartoes/lancamentos/{lanc['id']}", {'valor': '1.00'}).resultado()
    assert r['status'] == 409 and 'paga' in r['json']['error']


def test_flask_fatura_consolidada_nao_muda_de_valor_nem_e_excluida_pela_rota_de_despesas(pg):
    d, p = pg['dsn'], pg['pasta']
    f = consolidar(d, FATURA_MES)
    antes = md5_fatura(d, f['id'])
    r1 = http(d, p, 'pv', 'put', f"/api/despesas/{f['id']}", {'valor': '1.00'}).resultado()
    r2 = http(d, p, 'dl', 'delete', f"/api/despesas/{f['id']}").resultado()
    assert (r1['status'], r1['json']['codigo'], r2['status'], r2['json']['codigo']) == \
        (409, 'FATURA_CONSOLIDADA', 409, 'FATURA_CONSOLIDADA')
    assert md5_fatura(d, f['id']) == antes
    r3 = http(d, p, 'po', 'put', f"/api/despesas/{f['id']}", {'observacoes': 'conferida'}).resultado()
    assert r3['status'] == 200 and conta(d, f['id'])['observacoes'] == 'conferida'


def test_novo_aplicativo_tambem_bloqueia_compra_de_fatura_consolidada(pg):
    d = pg['dsn']
    f = consolidar(d, FATURA_MES)
    atribuir(d, 'PESSOAL')  # FIN-ESCRITOR-UNICO-FINAL-1: as escritas do novo aplicativo exigem o perfil atribuido a ele
    lanc = compra_base(d)
    versao = chamar(d, USUARIO_A, 'select financeiro.compra_para_edicao(%s, %s)', (PERFIL, lanc['id']))['versao']
    for comando, params in (('select financeiro.editar_compra(%s, %s, %s, %s::jsonb)',
                             (PERFIL, lanc['id'], versao, json.dumps({'descricao': 'X'}))),
                            ('select financeiro.excluir_compra(%s, %s, %s)', (PERFIL, lanc['id'], versao))):
        with pytest.raises(errors.RaiseException, match='fechada'):
            chamar(d, USUARIO_A, comando, params)
    assert auditoria(d, f['id']) == []


# ---------------------------------------------------------------------------
# E. Seguranca e concorrencia
# ---------------------------------------------------------------------------

def test_edicao_do_flask_durante_a_consolidacao_espera_e_ve_a_fatura_consolidada(pg):
    """A consolidacao do Flask (pausada antes do commit, segurando cartao e fatura) e uma edicao de valor."""
    d, p = pg['dsn'], pg['pasta']
    lanc = compra_base(d)
    consolidacao = http(d, p, 'cons', 'post', f'/api/cartoes/{CARTAO}/faturas/2027-06/consolidar', pausa=True)
    consolidacao.pausado()
    edicao = http(d, p, 'ed', 'put', f"/api/cartoes/lancamentos/{lanc['id']}", {'valor': '1.00'})
    aguardar_bloqueio(d)
    consolidacao.liberar()
    assert consolidacao.resultado()['status'] == 200
    r = edicao.resultado()
    assert (r['status'], r['json']['codigo']) == (409, 'FATURA_CONSOLIDADA')
    f = sql(d, 'select valor_consolidado, valor_executado from public.conta where id = %s', (pg['fatura'],))[0]
    assert f['valor_consolidado'] == f['valor_executado'] == Decimal('250.00')


def test_consolidacao_soma_a_compra_que_entrou_enquanto_esperava(pg):
    """Compra em andamento (transacao propria segurando o cartao) e a consolidacao do Flask: o total consolidado
    inclui a compra (antes, o total vinha do recalculo e a compra podia ficar fora dele)."""
    d, p = pg['dsn'], pg['pasta']
    outra = psycopg2.connect(d)
    cur = outra.cursor()
    cur.execute('select 1 from public.item_despesa where id = %s for update', (CARTAO,))
    cur.execute("insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, categoria_id, descricao, valor, "
                "data_compra, mes_fatura, numero_parcela, total_parcelas, is_recorrente, is_importado) "
                "values (%s, %s, %s, 'Em andamento', 40, '2027-06-20', %s, 1, 1, false, false)",
                (PERFIL, CARTAO, MORADIA, FATURA_MES))
    consolidacao = http(d, p, 'cons', 'post', f'/api/cartoes/{CARTAO}/faturas/2027-06/consolidar')
    aguardar_bloqueio(d)  # a consolidacao espera o cartao
    outra.commit()
    outra.close()
    assert consolidacao.resultado()['status'] == 200
    f = sql(d, 'select status_fatura, valor_consolidado, valor_executado from public.conta where id = %s', (pg['fatura'],))[0]
    assert (f['status_fatura'], f['valor_consolidado'], f['valor_executado']) == ('FECHADA', Decimal('290.00'), Decimal('290.00'))


def test_isolamento_entre_perfis_e_funcoes_internas(pg):
    d = pg['dsn']
    f = consolidar(d, FATURA_MES)
    with pytest.raises(errors.InsufficientPrivilege):  # B tentando incluir na fatura do Pessoal, mesmo "confirmando"
        criar_novo(d, compra_nova('Alheia', FATURA_MES, confirmar_consolidadas=[
            {'fatura_id': f['id'], 'total_consolidado': '250.00'}]), usuario=USUARIO_B)
    for comando in ("select financeiro.fatura_consolidada_no_destino(910, '2027-06-01')",
                    "select * from financeiro.plano_recorrencia(101, '2027-03-01')",
                    "select financeiro.gerar_mes_interno(101, '2027-03-01', 0, '[]'::jsonb)",
                    "select financeiro.exigir_confirmacao_consolidada(1, '[]'::jsonb, 1)",
                    'select * from public.fatura_consolidada_inclusao',
                    "update public.conta set valor_consolidado = 0 where id = 1"):
        with pytest.raises(errors.InsufficientPrivilege):
            chamar(d, USUARIO_A, comando)
    assert auditoria(d, f['id']) == [] and conta(d, f['id'])['valor_consolidado'] == Decimal('250.00')


def test_inclusoes_simultaneas_com_a_mesma_confirmacao_uma_so_vale(pg):
    d = pg['dsn']
    f = consolidar(d, FATURA_MES)
    atribuir(d, 'PESSOAL')  # FIN-ESCRITOR-UNICO-FINAL-1: as escritas do novo aplicativo exigem o perfil atribuido a ele
    conf = [{'fatura_id': f['id'], 'total_consolidado': '250.00'}]
    barreira = threading.Barrier(2)

    def incluir(nome):
        barreira.wait(30)
        return criar_novo(d, compra_nova(nome, FATURA_MES, '10.00', confirmar_consolidadas=conf))

    tarefas = [em_thread(lambda n=n: incluir(n)) for n in ('X', 'Y')]
    for t, _ in tarefas:
        t.join(60)
    estados = sorted('valor' in r for _, r in tarefas)
    assert estados == [False, True]
    assert [x['total_consolidado_novo'] for x in auditoria(d, f['id'])] == [Decimal('260.00')]
    assert conta(d, f['id'])['valor_consolidado'] == Decimal('260.00')
