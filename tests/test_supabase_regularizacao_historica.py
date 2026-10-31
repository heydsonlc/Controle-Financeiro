"""
Testes FIN-REGULARIZACAO-HISTORICO-01 — pagamento historico sem movimento (migration 20261205090000), em cluster local
descartavel, com dados FICTICIOS criados aqui no "Pessoal" (usuario A):
- plano sem gravar: pendentes ate o corte (despesa, fatura, parcelas de financiamento) entram; paga, posterior ao corte,
  com movimento e despesa de item pago por cartao ja representada na fatura ficam fora;
- confirmar: tudo pago na data do vencimento, parcelas pagas pelo valor previsto, SEM movimento, saldos de conta e saldo
  devedor do financiamento intactos, outubro em diante e Empresa intactos, auditoria por item, idempotencia;
- recusas: plano mudou, competencia aberta, quem nao gere, perfil no Flask;
- reversao do lote (e recusa se um item mudou) e reversao da migration (recusada com lote vigente).
"""
import uuid
from datetime import date
from pathlib import Path

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_financiamentos_motor import FIXO, com_tr, fin_id
from tests.test_supabase_recorrencia import (  # noqa: F401  (fixture de modulo reaproveitada)
    ID,
    PG_BIN,
    USUARIO_B,
    atribuir,
    cluster,
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL, EMPRESA = ID['PESSOAL'], ID['EMPRESA']
CORTE = '2026-09'
REVERSAO = Path(__file__).resolve().parent.parent / 'supabase' / 'reversao' / '20261205090000_regularizacao_historica_anterior.sql'


def item(dsn, nome, meio=None, cartao=None, perfil=PESSOAL):
    return sql(dsn, """insert into public.item_despesa (perfil_financeiro_id, nome, tipo, ativo, recorrente, categoria_id,
                                                        meio_pagamento, cartao_id)
                       values (%s, %s, 'Simples', true, false, (select min(id) from public.categoria), %s, %s)
                       returning id""", (perfil, nome, meio, cartao))[0]['id']


def despesa(dsn, item_id, vencimento, valor, descricao, pago=False, fatura=False, perfil=PESSOAL):
    return sql(dsn, """insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor,
                                                 data_vencimento, data_pagamento, status_pagamento, debito_automatico,
                                                 is_fatura_cartao, estouro_orcamento, status_fatura)
                       values (%s, %s, date_trunc('month', %s::date), %s, %s, %s, %s, %s, false, %s, false, 'ABERTA')
                       returning id""",
               (perfil, item_id, vencimento, descricao, valor, vencimento, vencimento if pago else None,
                'Pago' if pago else 'Pendente', fatura))[0]['id']


@pytest.fixture
def cenario(cluster):  # noqa: F811
    dsn = com_tr(copiar(cluster))
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'EMPRESA')
    rpc(dsn, 'criar_financiamento', PESSOAL, FIXO, str(uuid.uuid4()))
    luz = item(dsn, 'Luz (ficticia)')
    cartao = item(dsn, 'Cartao Regularizacao (ficticio)')
    sql(dsn, "update public.item_despesa set tipo = 'Agregador' where id = %s", (cartao,))
    streaming = item(dsn, 'Streaming no cartao (ficticio)', meio='cartao', cartao=cartao)
    ids = {
        'pendente': despesa(dsn, luz, '2026-05-10', 210.50, 'Luz 05/2026 (ficticia)'),
        'pendente_set': despesa(dsn, luz, '2026-09-10', 199.90, 'Luz 09/2026 (ficticia)'),
        'paga': despesa(dsn, luz, '2026-06-10', 205.00, 'Luz 06/2026 paga (ficticia)', pago=True),
        'outubro': despesa(dsn, luz, '2026-10-10', 220.00, 'Luz 10/2026 (ficticia)'),
        'fatura': despesa(dsn, cartao, '2026-07-05', 980.00, 'Fatura 07/2026 (ficticia)', fatura=True),
        'fatura_zero': despesa(dsn, cartao, '2026-08-05', 0, 'Fatura 08/2026 (ficticia)', fatura=True),
        'fatura_outubro': despesa(dsn, cartao, '2026-10-05', 500.00, 'Fatura 10/2026 (ficticia)', fatura=True),
        'no_cartao': despesa(dsn, streaming, '2026-05-01', 59.90, 'Streaming (ficticio)'),
        'empresa': despesa(dsn, item(dsn, 'Aluguel Empresa (ficticio)', perfil=EMPRESA), '2026-05-10', 1000, 'Aluguel (ficticio)',
                           perfil=EMPRESA),
    }
    sql(dsn, """insert into public.lancamento_agregado (id, item_despesa_id, cartao_id, perfil_financeiro_id, categoria_id, descricao,
                                                        valor, data_compra, mes_fatura, numero_parcela, total_parcelas,
                                                        observacoes, is_recorrente, is_importado)
                values ((select coalesce(max(id), 0) + 1 from public.lancamento_agregado), %s, %s, %s,
                        (select min(id) from public.categoria), 'Streaming', 59.90,
                        '2026-05-01', '2026-05-01', 1, 1, '', true, false)""", (streaming, cartao, PESSOAL))
    return dsn, ids


def plano(dsn, perfil=PESSOAL, ate=CORTE, usuario=None):
    return rpc(dsn, 'regularizar_historico', perfil, {'ate_competencia': ate}, str(uuid.uuid4()),
               **({'usuario': usuario} if usuario else {}))


def confirmar(dsn, p, chave=None, **extra):
    return rpc(dsn, 'regularizar_historico', PESSOAL,
               {'ate_competencia': CORTE, 'confirmar': True, 'esperado': {'quantidade': p['quantidade'], 'valor': p['valor']}, **extra},
               chave or str(uuid.uuid4()))


def falha(dsn, *args, usuario=None):
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'regularizar_historico', *args, **({'usuario': usuario} if usuario else {}))
    return erro.value.pgcode, erro.value.diag.message_primary, erro.value.diag.message_hint


def foto(dsn):
    return {
        'contas': {r['id']: r for r in sql(dsn, 'select * from public.conta order by id')},
        'parcelas': {r['id']: r for r in sql(dsn, 'select * from public.financiamento_parcela order by id')},
        'financiamentos': sql(dsn, 'select * from public.financiamento order by id'),
        'movimentos': sql(dsn, 'select count(*) as n from public.movimento_financeiro')[0]['n'],
        'bancos': sql(dsn, 'select id, saldo_atual from public.conta_bancaria order by id'),
        'compras': sql(dsn, "select md5(string_agg(l::text, '|' order by l.id)) as h from public.lancamento_agregado l")[0]['h'],
        'receitas': sql(dsn, "select md5(coalesce(string_agg(r::text, '|' order by r.id), '')) as h from public.receita_realizada r")[0]['h'],
    }


def test_plano_sem_gravar_e_elegibilidade(cenario):
    dsn, ids = cenario
    antes = foto(dsn)
    p = plano(dsn)
    assert p['confirmado'] is False
    contas = {i['conta_id']: i for i in p['itens']}
    assert {ids['pendente'], ids['pendente_set'], ids['fatura'], ids['fatura_zero']} <= set(contas)
    assert not {ids['paga'], ids['outubro'], ids['fatura_outubro'], ids['no_cartao'], ids['empresa']} & set(contas)
    assert [r['conta_id'] for r in p['representadas_na_fatura']] == [ids['no_cartao']]
    parcelas = [i for i in p['itens'] if i['tipo'] == 'PARCELA']
    assert len(parcelas) == 29 and max(i['competencia'] for i in parcelas) == CORTE
    assert contas[ids['fatura']]['tipo'] == 'FATURA' and contas[ids['pendente']]['data_pagamento'] == '2026-05-10'
    assert [i['competencia'] for i in p['itens']] == sorted(i['competencia'] for i in p['itens'])  # cronologico
    assert p['quantidade'] == len(p['itens']) and float(p['valor']) == pytest.approx(sum(float(i['valor']) for i in p['itens']))
    assert all(i['competencia'] <= CORTE for i in p['itens'])
    assert foto(dsn) == antes  # so o plano: nada gravado


def test_confirmar_regulariza_sem_movimento_nem_saldo(cenario):
    dsn, ids = cenario
    antes = foto(dsn)
    p = plano(dsn)
    chave = str(uuid.uuid4())
    r = confirmar(dsn, p, chave)
    assert r['confirmado'] is True and r['quantidade'] == p['quantidade']
    depois = foto(dsn)
    alvo = {i['conta_id'] for i in p['itens']}
    for cid, c in depois['contas'].items():
        if cid in alvo:
            assert (c['status_pagamento'], c['data_pagamento']) == ('Pago', antes['contas'][cid]['data_vencimento'])
            assert {k: v for k, v in c.items() if k not in ('status_pagamento', 'data_pagamento')} == \
                {k: v for k, v in antes['contas'][cid].items() if k not in ('status_pagamento', 'data_pagamento')}
        else:
            assert c == antes['contas'][cid]  # paga, outubro, cartao, Empresa e o resto: intactos
    assert depois['contas'][ids['no_cartao']]['status_pagamento'] == 'Pendente'
    fid = fin_id(dsn)
    pp = {r['numero_parcela']: r for r in sql(dsn, 'select * from public.financiamento_parcela where financiamento_id = %s', (fid,))}
    assert all(pp[n]['status'] == 'pago' and pp[n]['valor_pago'] == pp[n]['valor_previsto_total'] for n in range(1, 30))
    assert all(pp[n]['status'] == 'pendente' for n in range(30, 421))
    assert depois['financiamentos'] == antes['financiamentos']  # saldo devedor nao vem do historico estimado
    assert (depois['movimentos'], depois['bancos'], depois['compras'], depois['receitas']) == \
        (antes['movimentos'], antes['bancos'], antes['compras'], antes['receitas'])
    auditoria = sql(dsn, 'select * from financeiro.regularizacao_historica where lote = %s', (r['lote'],))
    assert len(auditoria) == p['quantidade'] and all(a['anterior']['status_pagamento'] == 'Pendente' for a in auditoria)
    # Repeticao pela chave: a mesma resposta, nada de novo; um segundo plano ja nao tem nada.
    assert confirmar(dsn, p, chave)['repetida'] is True
    assert plano(dsn)['quantidade'] == 0


def test_recusas_sem_gravar(cenario):
    dsn, _ = cenario
    antes = foto(dsn)
    p = plano(dsn)
    assert falha(dsn, PESSOAL, {'ate_competencia': CORTE, 'confirmar': True, 'esperado': {'quantidade': p['quantidade'] - 1,
                                                                                          'valor': p['valor']}},
                 str(uuid.uuid4()))[2] == 'PLANO_MUDOU'
    assert falha(dsn, PESSOAL, {'ate_competencia': date.today().strftime('%Y-%m')}, str(uuid.uuid4()))[2] == 'COMPETENCIA_ABERTA'
    assert falha(dsn, PESSOAL, {'ate_competencia': CORTE}, str(uuid.uuid4()), usuario=USUARIO_B)[0] == '42501'
    atribuir(dsn, 'PESSOAL', 'FLASK')
    assert falha(dsn, PESSOAL, {'ate_competencia': CORTE}, str(uuid.uuid4()))[2] == 'SISTEMA_FLASK'
    atribuir(dsn, 'PESSOAL')
    assert foto(dsn) == antes


def test_reversao_do_lote_e_recusa_com_item_alterado(cenario):
    dsn, ids = cenario
    antes = foto(dsn)
    lote = confirmar(dsn, plano(dsn))['lote']
    r = rpc(dsn, 'reverter_regularizacao_historica', PESSOAL, lote, str(uuid.uuid4()))
    assert r['revertidos'] > 0
    assert foto(dsn) == antes  # estado anterior inteiro de volta

    lote = confirmar(dsn, plano(dsn))['lote']
    meio = foto(dsn)
    sql(dsn, "update public.conta set data_pagamento = '2026-05-20' where id = %s", (ids['pendente'],))  # item mudou depois
    with pytest.raises(psycopg2.Error, match='mudou depois da regularizacao'):
        rpc(dsn, 'reverter_regularizacao_historica', PESSOAL, lote, str(uuid.uuid4()))
    sql(dsn, "update public.conta set data_pagamento = '2026-05-10' where id = %s", (ids['pendente'],))
    assert foto(dsn) == meio  # nada revertido


def test_reversao_da_migration(cenario):
    dsn, _ = cenario
    lote = confirmar(dsn, plano(dsn))['lote']

    def executar():
        conn = psycopg2.connect(dsn)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(REVERSAO.read_text(encoding='utf-8'))
        finally:
            conn.close()

    with pytest.raises(psycopg2.Error, match='regularizacao historica vigente'):
        executar()
    rpc(dsn, 'reverter_regularizacao_historica', PESSOAL, lote, str(uuid.uuid4()))
    executar()
    assert sql(dsn, "select to_regclass('financeiro.regularizacao_historica') as t")[0]['t'] is None
    assert sql(dsn, "select count(*) as n from pg_proc where proname in ('regularizar_historico', 'reverter_regularizacao_historica', "
                    "'plano_regularizacao_historica')")[0]['n'] == 0
