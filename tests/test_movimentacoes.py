"""
Testes FIN-MOVIMENTACOES-1 — pagamento de despesa comum, recebimento de receita, estornos e movimentos do mes no novo
aplicativo (Supabase).

Bancos ISOLADOS e dados FICTICIOS: copia do cluster PostgreSQL descartavel com todas as migrations (cenario do
FIN-PAGAMENTO-TRAVA-1: perfil "Pessoal" ficticio 101, despesas 7001 de 350,40 e 7002 de 120,00, debito automatico 7003
vencido, conta bancaria com saldo 1000) e uma previsao de receita ficticia criada aqui. Novo aplicativo como
`authenticated` (usuario A); Flask em processo real. Nunca o gastos.db nem o Supabase remoto.
"""
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest

from tests.test_pagamento_trava import (  # noqa: F401  (fixtures reaproveitadas)
    CONTA, CONTA_B, CONTA_DA, PERFIL, base, conta, http, pagar_corpo, pg, saldo,
)
from tests.test_supabase_fatura_unica import em_thread
from tests.test_supabase_recorrencia import ID, USUARIO_A, USUARIO_B, atribuir, chamar, cluster, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')

D = date
MES = '2027-05-01'


def novo(pg):  # noqa: F811
    """Perfil atribuido ao novo aplicativo (D6): so assim ele paga e recebe."""
    atribuir(pg['dsn'], 'PESSOAL')
    return pg['dsn'], pg['banco']


def erro(funcao):
    try:
        funcao()
    except psycopg2.Error as exc:
        return exc
    raise AssertionError('a operacao deveria ter sido recusada')


def rpc(dsn, funcao, args, usuario=USUARIO_A):
    marcadores = ', '.join(f'{k} => %s' for k in args)
    valores = tuple(json.dumps(v) if isinstance(v, dict) else v for v in args.values())
    return chamar(dsn, usuario, f'select financeiro.{funcao}({marcadores})', valores)


def pagar(dsn, conta_id, banco, valor='350.40', devido='350.40', chave=None, usuario=USUARIO_A, **extra):
    return rpc(dsn, 'pagar_despesa', {'p_perfil_id': PERFIL, 'p_conta_id': conta_id, 'p_dados': {
        'conta_bancaria_id': banco, 'data_pagamento': '2027-05-10', 'valor_pago': valor, 'valor_devido': devido, **extra},
        'p_chave': chave or str(uuid.uuid4())}, usuario)


def estornar_despesa(dsn, conta_id, movimento, chave=None):
    return rpc(dsn, 'estornar_pagamento_despesa', {'p_perfil_id': PERFIL, 'p_conta_id': conta_id, 'p_movimento_id': movimento,
               'p_dados': {'motivo': 'Pago em duplicidade', 'data_estorno': '2027-05-15'}, 'p_chave': chave or str(uuid.uuid4())})


def receber(dsn, orcamento, banco, valor, falta, chave=None, usuario=USUARIO_A, **extra):
    return rpc(dsn, 'receber_receita', {'p_perfil_id': PERFIL, 'p_orcamento_id': orcamento, 'p_dados': {
        'conta_bancaria_id': banco, 'data_recebimento': '2027-05-05', 'valor_recebido': valor, 'falta': falta, **extra},
        'p_chave': chave or str(uuid.uuid4())}, usuario)


def estornar_recebimento(dsn, realizada, chave=None):
    return rpc(dsn, 'estornar_recebimento', {'p_perfil_id': PERFIL, 'p_realizada_id': realizada,
               'p_dados': {'motivo': 'Credito devolvido pelo banco', 'data_estorno': '2027-05-20'}, 'p_chave': chave or str(uuid.uuid4())})


def movs_conta(dsn, conta_id):
    return [(m['tipo'], m['valor'], m['origem'], m['movimento_original_id']) for m in sql(
        dsn, 'select tipo, valor, origem, movimento_original_id from public.movimento_financeiro where conta_id = %s '
             'order by id', (conta_id,))]


def movs_receita(dsn, orcamento):
    return [(m['tipo'], m['valor'], m['origem'], m['movimento_original_id']) for m in sql(
        dsn, 'select m.tipo, m.valor, m.origem, m.movimento_original_id from public.movimento_financeiro m '
             'join public.receita_realizada r on r.id = m.receita_realizada_id where r.orcamento_id = %s order by m.id',
        (orcamento,))]


def previsao(dsn, valor='1000.00'):
    """Fonte e previsao ficticias de 05/2027 no Pessoal ficticio."""
    item = sql(dsn, "insert into public.item_receita (perfil_financeiro_id, nome, tipo, descricao, ativo, valor_base_mensal, "
                    "dia_previsto_pagamento, recorrente) values (%s, 'Salario teste', 'SALARIO_FIXO', '', true, %s, 5, true) "
                    'returning id', (PERFIL, valor))[0]['id']
    return sql(dsn, "insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, "
                    "valor_esperado, periodicidade) values (%s, %s, %s, %s, 'MENSAL_FIXA') returning id",
               (PERFIL, item, MES, valor))[0]['id']


def situacao_receita(dsn, orcamento):
    linhas = chamar(dsn, USUARIO_A, "select coalesce(json_agg(x), '[]'::json) from financeiro.receitas_do_mes(%s, %s) x",
                    (PERFIL, MES))
    return next(l['situacao'] for l in linhas if l['origem'] == 'PREVISAO' and l['id'] == orcamento)


def saldo_ok(dsn, banco, esperado):
    return saldo(dsn, banco) == (Decimal(esperado), Decimal(esperado))


# --- Despesas ----------------------------------------------------------------------------------------------------

# 1. Pagamento de despesa
def test_pagar_despesa_debita_e_marca_paga(pg):
    d, banco = novo(pg)
    tela = rpc(d, 'dados_pagamento_despesa', {'p_perfil_id': PERFIL, 'p_conta_id': CONTA})
    assert (tela['pode_pagar'], tela['sistema'], Decimal(str(tela['despesa']['valor']))) == (True, 'NOVO', Decimal('350.40'))
    r = pagar(d, CONTA, banco)
    c = conta(d, CONTA)
    assert (c['status_pagamento'], c['valor'], c['data_pagamento'], c['conta_bancaria_id']) == \
        ('Pago', Decimal('350.40'), D(2027, 5, 10), banco)
    assert movs_conta(d, CONTA) == [('DEBITO', Decimal('350.40'), 'DESPESA', None)] and saldo_ok(d, banco, '649.60')
    assert Decimal(str(r['saldo_conta'])) == Decimal('649.60')
    [p] = sql(d, 'select * from financeiro.pagamento_fatura where fatura_id = %s', (CONTA,))
    assert (p['movimento_id'], p['valor_executado'], p['user_id']) == (r['movimento_id'], Decimal('350.40'), USUARIO_A['id'])


# 3 e 12. Diferenca justificada; estorno devolve o valor devido original
def test_pagamento_com_juros_e_estorno_devolve_o_devido(pg):
    d, banco = novo(pg)
    for extra in ({}, {'tipo_ajuste': 'DESCONTO', 'justificativa': 'x'}):
        assert erro(lambda: pagar(d, CONTA, banco, valor='360.00', **extra)).diag.message_hint == 'AJUSTE_OBRIGATORIO'
    assert movs_conta(d, CONTA) == [] and conta(d, CONTA)['status_pagamento'] == 'Pendente'
    r = pagar(d, CONTA, banco, valor='360.00', tipo_ajuste='JUROS', justificativa='Multa por atraso')
    assert conta(d, CONTA)['valor'] == Decimal('360.00') and saldo_ok(d, banco, '640.00')
    e = estornar_despesa(d, CONTA, r['movimento_id'])
    c = conta(d, CONTA)
    assert (c['status_pagamento'], c['data_pagamento'], c['valor']) == ('Pendente', None, Decimal('350.40'))
    assert '[ESTORNO] 2027-05-15' in c['observacoes']
    assert movs_conta(d, CONTA) == [('DEBITO', Decimal('360.00'), 'DESPESA', None),
                                    ('CREDITO', Decimal('360.00'), 'ESTORNO_DESPESA', r['movimento_id'])]
    assert e['movimento_original_id'] == r['movimento_id'] and saldo_ok(d, banco, '1000.00')


# 5 e 6. Conta inativa e de outro perfil
def test_conta_inativa_ou_de_outro_perfil_recusada(pg):
    d, banco = novo(pg)
    empresa = sql(d, "select id from public.conta_bancaria where nome = 'Conta Empresa (A)'")[0]['id']
    inativa = sql(d, "insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, status, cor_display) "
                     "values (%s, 'Conta encerrada', 'Banco ficticio', 'Conta Corrente', 'INATIVO', '#3b82f6') returning id",
                  (PERFIL,))[0]['id']
    orc = previsao(d)
    assert 'nao encontrada neste perfil' in str(erro(lambda: pagar(d, CONTA, empresa)))
    assert 'inativa' in str(erro(lambda: pagar(d, CONTA, inativa)))
    assert 'nao encontrada neste perfil' in str(erro(lambda: receber(d, orc, empresa, '1000.00', '1000.00')))
    assert 'inativa' in str(erro(lambda: receber(d, orc, inativa, '1000.00', '1000.00')))
    assert movs_conta(d, CONTA) == [] and movs_receita(d, orc) == [] and saldo_ok(d, banco, '1000.00')
    assert sql(d, 'select count(*) as n from public.receita_realizada where orcamento_id = %s', (orc,))[0]['n'] == 0


# 7 e 9. Pagamento duplicado e simultaneo
def test_pagamento_duplicado_e_simultaneo_um_debito(pg):
    d, banco = novo(pg)
    chave = str(uuid.uuid4())
    r1, r2 = pagar(d, CONTA, banco, chave=chave), pagar(d, CONTA, banco, chave=chave)
    assert r2['repetida'] is True and r2['movimento_id'] == r1['movimento_id']
    assert erro(lambda: pagar(d, CONTA, banco)).diag.message_hint == 'DESPESA_PAGA'
    tarefas = [em_thread(lambda: pagar(d, CONTA_B, banco, valor='120.00', devido='120.00')) for _ in range(3)]
    for t, _ in tarefas:
        t.join(60)
    assert sum('valor' in r for _, r in tarefas) == 1
    assert [r['erro'].diag.message_hint for _, r in tarefas if 'erro' in r] == ['DESPESA_PAGA', 'DESPESA_PAGA']
    assert len(movs_conta(d, CONTA)) == len(movs_conta(d, CONTA_B)) == 1 and saldo_ok(d, banco, '529.60')


# 14. Pagar, estornar, pagar e estornar (sem o defeito do Flask)
def test_pagar_estornar_pagar_estornar_despesa(pg):
    d, banco = novo(pg)
    a = pagar(d, CONTA, banco)
    estornar_despesa(d, CONTA, a['movimento_id'])
    b = pagar(d, CONTA, banco)
    assert erro(lambda: estornar_despesa(d, CONTA, a['movimento_id'])).diag.message_hint == 'JA_ESTORNADO'
    estornar_despesa(d, CONTA, b['movimento_id'])
    assert [(m[0], m[3]) for m in movs_conta(d, CONTA)] == [
        ('DEBITO', None), ('CREDITO', a['movimento_id']), ('DEBITO', None), ('CREDITO', b['movimento_id'])]
    assert conta(d, CONTA)['status_pagamento'] == 'Pendente' and saldo_ok(d, banco, '1000.00')
    tela = rpc(d, 'dados_pagamento_despesa', {'p_perfil_id': PERFIL, 'p_conta_id': CONTA})
    assert [p['estorno'] is not None for p in tela['pagamentos']] == [True, True] and tela['pode_pagar'] is True


# FIN-CONTRATOS-2: parcela de consorcio (despesa do item 'Consorcio') e paga aqui pelo escritor do perfil; o Flask, com o
# perfil no novo aplicativo, recusa (antes desta etapa era o contrario: o Flask pagava e o novo aplicativo recusava).
def test_consorcio_pago_pelo_escritor_do_perfil(pg):
    d, banco = novo(pg)
    item = sql(d, "insert into public.item_despesa (perfil_financeiro_id, nome, tipo, ativo, categoria_id) "
                  "values (%s, 'Consorcio teste', 'Consorcio', true, 951) returning id", (PERFIL,))[0]['id']
    cid = sql(d, "insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, "
                 "data_vencimento, status_pagamento, debito_automatico, is_fatura_cartao, estouro_orcamento, status_fatura) "
                 "values (%s, %s, '2027-05-01', 'Parcela consorcio', 200, '2027-05-10', 'Pendente', false, false, false, "
                 "'ABERTA') returning id", (PERFIL, item))[0]['id']
    assert rpc(d, 'dados_pagamento_despesa', {'p_perfil_id': PERFIL, 'p_conta_id': cid})['pode_pagar'] is True
    r = http(d, pg['pasta'], 'cons', 'post', f'/api/despesas/{cid}/pagar', pagar_corpo(banco)).resultado()
    assert (r['status'], r['json']['codigo']) == (409, 'SISTEMA_NOVO') and conta(d, cid)['status_pagamento'] == 'Pendente'
    pagar(d, cid, banco, valor='200.00', devido='200.00')
    assert conta(d, cid)['status_pagamento'] == 'Pago'


# 11. Falha no meio: nada fica (despesa e receita)
def test_falha_intermediaria_reverte_tudo(pg):
    d, banco = novo(pg)
    orc = previsao(d)
    sql(d, "create function public.falha_teste() returns trigger language plpgsql as $$ "
           "begin if new.origem in ('DESPESA', 'RECEITA') then raise exception 'falha injetada'; end if; return new; end $$")
    sql(d, 'create trigger falha before insert on public.movimento_financeiro for each row execute function public.falha_teste()')
    assert 'falha injetada' in str(erro(lambda: pagar(d, CONTA, banco)))
    assert 'falha injetada' in str(erro(lambda: receber(d, orc, banco, '1000.00', '1000.00')))
    assert conta(d, CONTA)['status_pagamento'] == 'Pendente' and movs_conta(d, CONTA) == []
    # O Flask grava o recebimento antes do movimento; aqui recebimento e credito vao juntos ou nada fica.
    assert sql(d, 'select count(*) as n from public.receita_realizada where orcamento_id = %s', (orc,))[0]['n'] == 0
    assert saldo_ok(d, banco, '1000.00')
    assert sql(d, "select count(*) as n from financeiro.operacao_despesa where operacao = 'pagar_despesa'")[0]['n'] == 0


# --- Receitas ----------------------------------------------------------------------------------------------------

# 2 e 4. Recebimento integral e parcial (semantica mantida), acima do que falta so justificado
def test_recebimento_parcial_e_acima_do_previsto(pg):
    d, banco = novo(pg)
    orc = previsao(d)
    tela = rpc(d, 'dados_recebimento_receita', {'p_perfil_id': PERFIL, 'p_orcamento_id': orc})
    assert (tela['pode_receber'], Decimal(str(tela['receita']['falta']))) == (True, Decimal('1000.00'))
    r1 = receber(d, orc, banco, '400.00', '1000.00')  # parcial: sem justificativa
    assert situacao_receita(d, orc) == 'PARCIAL' and Decimal(str(r1['falta_depois'])) == Decimal('600.00')
    assert erro(lambda: receber(d, orc, banco, '700.00', '600.00')).diag.message_hint == 'JUSTIFICATIVA_OBRIGATORIA'
    r2 = receber(d, orc, banco, '700.00', '600.00', justificativa='Bonus pago junto')
    assert situacao_receita(d, orc) == 'RECEBIDA' and saldo_ok(d, banco, '2100.00')
    assert movs_receita(d, orc) == [('CREDITO', Decimal('400.00'), 'RECEITA', None), ('CREDITO', Decimal('700.00'), 'RECEITA', None)]
    [_, b] = sql(d, 'select * from public.receita_realizada where orcamento_id = %s order by id', (orc,))
    assert (b['id'], b['mes_referencia'], b['observacoes']) == (r2['receita_realizada_id'], D(2027, 5, 1),
                                                               '[ACIMA DO PREVISTO] Bonus pago junto')
    assert Decimal(str(r2['saldo_conta'])) == Decimal('2100.00')


# 8 e 10. Recebimento duplicado e simultaneo: um credito
def test_recebimento_duplicado_e_simultaneo(pg):
    d, banco = novo(pg)
    orc = previsao(d)
    chave = str(uuid.uuid4())
    r1, r2 = receber(d, orc, banco, '1000.00', '1000.00', chave=chave), receber(d, orc, banco, '1000.00', '1000.00', chave=chave)
    assert r2['repetida'] is True and r2['receita_realizada_id'] == r1['receita_realizada_id']
    assert erro(lambda: receber(d, orc, banco, '1000.00', '1000.00')).diag.message_hint == 'VALOR_MUDOU'  # ja recebida
    orc2 = sql(d, "insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, valor_esperado, "
                  "periodicidade) select %s, item_receita_id, '2027-06-01', 500, 'MENSAL_FIXA' from public.receita_orcamento "
                  'where id = %s returning id', (PERFIL, orc))[0]['id']
    tarefas = [em_thread(lambda: receber(d, orc2, banco, '500.00', '500.00')) for _ in range(3)]
    for t, _ in tarefas:
        t.join(60)
    assert sum('valor' in r for _, r in tarefas) == 1
    assert [r['erro'].diag.message_hint for _, r in tarefas if 'erro' in r] == ['VALOR_MUDOU', 'VALOR_MUDOU']
    assert len(movs_receita(d, orc)) == len(movs_receita(d, orc2)) == 1 and saldo_ok(d, banco, '2500.00')


# 13 e 15. Estorno de recebimento; receber, estornar, receber e estornar de novo
def test_receber_estornar_receber_estornar(pg):
    d, banco = novo(pg)
    orc = previsao(d)
    a = receber(d, orc, banco, '1000.00', '1000.00')
    e1 = estornar_recebimento(d, a['receita_realizada_id'])
    assert situacao_receita(d, orc) == 'PREVISTA' and saldo_ok(d, banco, '1000.00')
    assert erro(lambda: estornar_recebimento(d, a['receita_realizada_id'])).diag.message_hint == 'JA_ESTORNADO'
    b = receber(d, orc, banco, '1000.00', '1000.00')  # o que falta voltou a 1000
    estornar_recebimento(d, b['receita_realizada_id'])
    assert movs_receita(d, orc) == [
        ('CREDITO', Decimal('1000.00'), 'RECEITA', None), ('DEBITO', Decimal('1000.00'), 'ESTORNO_RECEITA', a['movimento_id']),
        ('CREDITO', Decimal('1000.00'), 'RECEITA', None), ('DEBITO', Decimal('1000.00'), 'ESTORNO_RECEITA', b['movimento_id'])]
    assert e1['movimento_original_id'] == a['movimento_id'] and saldo_ok(d, banco, '1000.00')
    assert situacao_receita(d, orc) == 'PREVISTA'
    tela = rpc(d, 'dados_recebimento_receita', {'p_perfil_id': PERFIL, 'p_orcamento_id': orc})
    assert [(r['estornado'], r['pode_estornar']) for r in tela['recebimentos']] == [(True, False), (True, False)]
    assert all('[ESTORNO] 2027-05-20' in r['observacoes'] for r in tela['recebimentos'])


# 16 e 17. Saldo e movimentos do mes (extrato)
def test_movimentos_do_mes_e_saldo(pg):
    d, banco = novo(pg)
    orc = previsao(d)
    p = pagar(d, CONTA, banco)
    estornar_despesa(d, CONTA, p['movimento_id'])
    receber(d, orc, banco, '1000.00', '1000.00')
    extrato = rpc(d, 'movimentos_do_mes', {'p_perfil_id': PERFIL, 'p_mes': MES})
    minha = next(c for c in extrato['contas'] if c['id'] == banco)
    assert Decimal(str(minha['saldo'])) == Decimal('2000.00') and saldo_ok(d, banco, '2000.00')
    linhas = [(m['tipo'], m['origem'], Decimal(str(m['valor'])), m['referencia']) for m in extrato['movimentos']
              if m['conta_bancaria_id'] == banco]
    assert linhas == [('CREDITO', 'RECEITA', Decimal('1000.00'), 'Salario teste'),
                      ('DEBITO', 'DESPESA', Decimal('350.40'), 'Conserto geladeira'),
                      ('CREDITO', 'ESTORNO_DESPESA', Decimal('350.40'), 'Conserto geladeira')]
    assert next(m for m in extrato['movimentos'] if m['origem'] == 'ESTORNO_DESPESA')['estorno_de'] == p['movimento_id']


# 18. Isolamento: outro usuario, anonimo, funcoes internas
def test_isolamento_entre_perfis(pg):
    d, banco = novo(pg)
    orc = previsao(d)
    for funcao, args in (('dados_pagamento_despesa', {'p_perfil_id': PERFIL, 'p_conta_id': CONTA}),
                         ('dados_recebimento_receita', {'p_perfil_id': PERFIL, 'p_orcamento_id': orc}),
                         ('movimentos_do_mes', {'p_perfil_id': PERFIL, 'p_mes': MES})):
        assert 'nao autorizado' in str(erro(lambda: rpc(d, funcao, args, USUARIO_B)))
        assert 'permission denied' in str(erro(lambda: rpc(d, funcao, args, None)))
    assert 'nao autorizado' in str(erro(lambda: pagar(d, CONTA, banco, usuario=USUARIO_B)))
    assert 'nao autorizado' in str(erro(lambda: receber(d, orc, banco, '1000.00', '1000.00', usuario=USUARIO_B)))
    assert 'nao autorizado' in str(erro(lambda: rpc(d, 'pagar_despesa', {
        'p_perfil_id': ID['EMPRESA'], 'p_conta_id': CONTA, 'p_dados': {}, 'p_chave': str(uuid.uuid4())})))  # A e LEITOR
    for interna in ('debito_vigente(1, \'DESPESA\')', 'bloqueio_do_pagamento(1)', 'recebido_da_previsao(1)',
                    'contas_ativas_com_saldo(101)', 'travar_conta_bancaria(101, 1)', 'bloqueio_do_recebimento(1)'):
        assert 'permission denied' in str(erro(lambda: chamar(d, USUARIO_A, f'select financeiro.{interna}')))
    assert movs_conta(d, CONTA) == [] and saldo_ok(d, banco, '1000.00')


# D6: um sistema por perfil. Perfil no Flask: o novo recusa; perfil no novo: o Flask recusa e nao baixa debito automatico.
def test_um_sistema_por_perfil(pg):
    d, banco = pg['dsn'], pg['banco']
    orc = previsao(d)
    assert erro(lambda: pagar(d, CONTA, banco)).diag.message_hint == 'SISTEMA_FLASK'
    assert erro(lambda: receber(d, orc, banco, '1000.00', '1000.00')).diag.message_hint == 'SISTEMA_FLASK'
    atribuir(d, 'PESSOAL')
    r = http(d, pg['pasta'], 'pag', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(banco)).resultado()
    assert (r['status'], r['json']['codigo']) == (409, 'SISTEMA_NOVO')
    item = sql(d, 'select item_receita_id from public.receita_orcamento where id = %s', (orc,))[0]['item_receita_id']
    r = http(d, pg['pasta'], 'rec', 'post', '/api/receitas/realizadas', {
        'item_receita_id': item, 'data_recebimento': '2027-05-05', 'valor_recebido': 1000, 'conta_bancaria_id': banco,
        'competencia': MES}).resultado()
    assert (r['status'], r['json']['codigo']) == (409, 'SISTEMA_NOVO')
    real = receber(d, orc, banco, '1000.00', '1000.00')
    r = http(d, pg['pasta'], 'est', 'post', f"/api/receitas/realizadas/{real['receita_realizada_id']}/estornar",
             {'motivo': 'teste', 'data_estorno': '2027-05-20'}).resultado()
    assert (r['status'], r['json']['codigo']) == (409, 'SISTEMA_NOVO')
    # A tela de despesas do Flask nao baixa o debito automatico vencido do perfil do novo aplicativo.
    assert http(d, pg['pasta'], 'lista', 'get', '/api/despesas/').resultado()['status'] == 200
    assert conta(d, CONTA_DA)['status_pagamento'] == 'Pendente'
    assert movs_conta(d, CONTA) == [] and movs_conta(d, CONTA_DA) == [] and len(movs_receita(d, orc)) == 1


# Pagamento feito pelo Flask antes da migracao do perfil: o novo aplicativo estorna pela identidade do debito.
def test_estorno_de_pagamento_feito_pelo_flask(pg):
    d, banco = pg['dsn'], pg['banco']
    assert http(d, pg['pasta'], 'pag', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(banco)).resultado()['status'] == 200
    atribuir(d, 'PESSOAL')
    [p] = rpc(d, 'dados_pagamento_despesa', {'p_perfil_id': PERFIL, 'p_conta_id': CONTA})['pagamentos']
    assert (p['origem'], p['vigente']) == ('FLASK', True)
    estornar_despesa(d, CONTA, p['movimento_id'])
    assert conta(d, CONTA)['status_pagamento'] == 'Pendente' and saldo_ok(d, banco, '1000.00')
    assert sql(d, 'select origem from financeiro.pagamento_fatura where movimento_id = %s', (p['movimento_id'],)) == \
        [{'origem': 'FLASK'}]
