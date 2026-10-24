"""
Testes FIN-CARTOES-PAGAMENTO-1 — pagamento e estorno de fatura de cartao no novo aplicativo (Supabase).

Bancos ISOLADOS e dados FICTICIOS: copia do cluster PostgreSQL descartavel com todas as migrations do repositorio
(cenario do FIN-PAGAMENTO-TRAVA-1: perfil "Pessoal" ficticio 101, cartao 910, fatura 06/2027 com 250,00 lancada pelo
proprio Flask, conta bancaria com saldo 1000). Novo aplicativo como `authenticated` (usuario A); Flask em processo
real. Nunca o gastos.db nem o Supabase remoto.
"""
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest

from tests.supabase_local import claims_usuario
from tests.test_pagamento_trava import (  # noqa: F401  (fixtures reaproveitadas)
    CARTAO, FATURA_MES, PERFIL, base, conta, http, movimentos, pagar_corpo, pg, saldo,
)
from tests.test_supabase_fatura_unica import aguardar_bloqueio, em_thread
from tests.test_supabase_recorrencia import ID, USUARIO_A, USUARIO_B, atribuir, chamar, cluster, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')

D = date
PAGAR = 'select financeiro.pagar_fatura(%s, %s, %s::jsonb, %s)'
ESTORNAR = 'select financeiro.estornar_pagamento_fatura(%s, %s, %s, %s::jsonb, %s)'


def novo(pg):  # noqa: F811
    """Perfil atribuido ao novo aplicativo (D5): so assim ele paga e estorna."""
    atribuir(pg['dsn'], 'PESSOAL')
    return pg['dsn'], pg['fatura'], pg['banco']


def pagar(dsn, fatura, banco, valor='250.00', visto='250.00', chave=None, usuario=USUARIO_A, perfil=PERFIL, **extra):
    dados = {'conta_bancaria_id': banco, 'data_pagamento': '2027-07-10', 'valor_pago': valor, 'valor_executado': visto,
             **extra}
    return chamar(dsn, usuario, PAGAR, (perfil, fatura, json.dumps(dados), chave or str(uuid.uuid4())))


def estornar(dsn, fatura, movimento, motivo='Pagamento em duplicidade no banco', chave=None, usuario=USUARIO_A):
    return chamar(dsn, usuario, ESTORNAR, (PERFIL, fatura, movimento,
                                           json.dumps({'motivo': motivo, 'data_estorno': '2027-07-15'}),
                                           chave or str(uuid.uuid4())))


def dados(dsn, fatura, usuario=USUARIO_A, perfil=PERFIL):
    return chamar(dsn, usuario, 'select financeiro.dados_pagamento_fatura(%s, %s)', (perfil, fatura))


def erro(funcao):
    try:
        funcao()
    except psycopg2.Error as exc:
        return exc
    raise AssertionError('a operacao deveria ter sido recusada')


def registros(dsn, fatura):
    return sql(dsn, 'select * from financeiro.pagamento_fatura where fatura_id = %s order by id', (fatura,))


def compras_md5(dsn):
    return sql(dsn, "select md5(string_agg(t::text, '|' order by id)) as h from public.lancamento_agregado t "
                    'where mes_fatura = %s', (FATURA_MES,))[0]['h']


def nada_mudou(dsn, fatura, banco):
    f = conta(dsn, fatura)
    return f['status_pagamento'] == 'Pendente' and movimentos(dsn, fatura) == [] and registros(dsn, fatura) == [] \
        and saldo(dsn, banco)[1] == Decimal('1000.00')


# 1. Pagamento integral
def test_pagamento_integral_debita_e_marca_paga(pg):
    d, fatura, banco = novo(pg)
    antes = compras_md5(d)
    tela = dados(d, fatura)
    assert (Decimal(str(tela['fatura']['valor_executado'])), tela['pode_pagar'], tela['sistema']) == (Decimal('250.00'), True, 'NOVO')
    assert any(c['id'] == banco and Decimal(str(c['saldo'])) == Decimal('1000.00') for c in tela['contas'])
    r = pagar(d, fatura, banco)
    f = conta(d, fatura)
    assert (f['status_pagamento'], f['valor'], f['valor_executado'], f['data_pagamento'], f['conta_bancaria_id'],
            f['status_fatura']) == ('Pago', Decimal('250.00'), Decimal('250.00'), D(2027, 7, 10), banco, 'ABERTA')
    assert movimentos(d, fatura) == [{'tipo': 'DEBITO', 'valor': Decimal('250.00'), 'origem': 'FATURA',
                                      'movimento_original_id': None}]
    assert saldo(d, banco) == (Decimal('750.00'), Decimal('750.00')) and Decimal(str(r['saldo_conta'])) == Decimal('750.00')
    [p] = registros(d, fatura)
    assert (p['movimento_id'], p['origem'], p['valor_executado'], p['tipo_ajuste'], p['user_id'], p['estornado_em']) == \
        (r['movimento_id'], 'NOVO_APP', Decimal('250.00'), None, USUARIO_A['id'], None)
    assert compras_md5(d) == antes  # o pagamento nao mexe nas compras
    tela = dados(d, fatura)
    assert (tela['pode_pagar'], tela['pode_estornar'], [x['vigente'] for x in tela['pagamentos']]) == (False, True, [True])


# 2. Juros justificados; classificacao incoerente ou sem justificativa recusada
def test_pagamento_com_juros_justificados(pg):
    d, fatura, banco = novo(pg)
    for extra in ({}, {'tipo_ajuste': 'JUROS'}, {'tipo_ajuste': 'DESCONTO', 'justificativa': 'x'}):
        e = erro(lambda: pagar(d, fatura, banco, valor='265.00', **extra))
        assert e.diag.message_hint == 'AJUSTE_OBRIGATORIO'
    assert nada_mudou(d, fatura, banco)
    r = pagar(d, fatura, banco, valor='265.00', tipo_ajuste='JUROS', justificativa='Pago com atraso')
    f = conta(d, fatura)
    assert (f['valor'], f['valor_executado'], Decimal(str(r['diferenca']))) == (Decimal('265.00'), Decimal('250.00'), Decimal('15.00'))
    assert [m['valor'] for m in movimentos(d, fatura)] == [Decimal('265.00')] and saldo(d, banco)[0] == Decimal('735.00')
    assert (registros(d, fatura)[0]['tipo_ajuste'], registros(d, fatura)[0]['justificativa']) == ('JUROS', 'Pago com atraso')


# 3. Desconto: quitacao integral justificada (sem saldo pendente)
def test_pagamento_com_desconto_quita_a_fatura(pg):
    d, fatura, banco = novo(pg)
    assert erro(lambda: pagar(d, fatura, banco, valor='240.00', tipo_ajuste='JUROS', justificativa='x')).diag.message_hint \
        == 'AJUSTE_OBRIGATORIO'
    pagar(d, fatura, banco, valor='240.00', tipo_ajuste='DESCONTO', justificativa='Desconto do banco por antecipacao')
    f = conta(d, fatura)
    assert (f['status_pagamento'], f['valor'], f['valor_executado']) == ('Pago', Decimal('240.00'), Decimal('250.00'))
    assert saldo(d, banco)[0] == Decimal('760.00')
    assert dados(d, fatura)['pode_pagar'] is False  # quitada: nada fica pendente


# 4 e 5. Conta de outro perfil e conta inativa
def test_conta_de_outro_perfil_ou_inativa_recusada(pg):
    d, fatura, banco = novo(pg)
    empresa = sql(d, "select id from public.conta_bancaria where nome = 'Conta Empresa (A)'")[0]['id']
    inativa = sql(d, "insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, status, cor_display) "
                     "values (%s, 'Conta encerrada', 'Banco ficticio', 'Conta Corrente', 'INATIVO', '#3b82f6') returning id",
                  (PERFIL,))[0]['id']
    assert 'nao encontrada neste perfil' in str(erro(lambda: pagar(d, fatura, empresa)))
    assert 'inativa' in str(erro(lambda: pagar(d, fatura, inativa)))
    assert all(c['id'] not in (empresa, inativa) for c in dados(d, fatura)['contas'])
    assert nada_mudou(d, fatura, banco)


# 6. Mesma solicitacao repetida; outra solicitacao para fatura ja paga
def test_pagamento_repetido_sem_segundo_debito(pg):
    d, fatura, banco = novo(pg)
    chave = str(uuid.uuid4())
    r1 = pagar(d, fatura, banco, chave=chave)
    r2 = pagar(d, fatura, banco, chave=chave)
    assert r2['repetida'] is True and r2['movimento_id'] == r1['movimento_id']
    assert erro(lambda: pagar(d, fatura, banco)).diag.message_hint == 'FATURA_PAGA'
    assert len(movimentos(d, fatura)) == 1 and saldo(d, banco)[0] == Decimal('750.00')


# 7. Pagamentos simultaneos (chaves diferentes e a mesma chave)
def test_pagamentos_simultaneos_uma_operacao(pg):
    d, fatura, banco = novo(pg)
    tarefas = [em_thread(lambda: pagar(d, fatura, banco)) for _ in range(3)]
    for t, _ in tarefas:
        t.join(60)
    ok = [r['valor'] for _, r in tarefas if 'valor' in r]
    recusas = [r['erro'] for _, r in tarefas if 'erro' in r]
    assert len(ok) == 1 and [e.diag.message_hint for e in recusas] == ['FATURA_PAGA', 'FATURA_PAGA']
    assert len(movimentos(d, fatura)) == 1 and saldo(d, banco)[0] == Decimal('750.00')


def test_mesma_chave_simultanea_um_debito(pg):
    d, fatura, banco = novo(pg)
    chave = str(uuid.uuid4())
    tarefas = [em_thread(lambda: pagar(d, fatura, banco, chave=chave)) for _ in range(3)]
    for t, _ in tarefas:
        t.join(60)
    assert all('valor' in r for _, r in tarefas)
    assert len({r['valor']['movimento_id'] for _, r in tarefas}) == 1 and len(movimentos(d, fatura)) == 1


# 8. Falha no meio: nada fica (movimento, saldo e situacao revertidos)
def test_falha_durante_o_pagamento_reverte_tudo(pg):
    d, fatura, banco = novo(pg)
    sql(d, "create function public.falha_teste() returns trigger language plpgsql as $$ "
           "begin raise exception 'falha injetada'; end $$")
    sql(d, 'create trigger falha before insert on financeiro.pagamento_fatura for each row execute function public.falha_teste()')
    assert 'falha injetada' in str(erro(lambda: pagar(d, fatura, banco)))
    assert nada_mudou(d, fatura, banco) and conta(d, fatura)['valor_executado'] == Decimal('250.00')
    assert sql(d, "select count(*) as n from financeiro.operacao_cartao where operacao = 'pagar_fatura'")[0]['n'] == 0


# 9 e 10. Estorno e estorno repetido
def test_estorno_credita_e_reabre_preservando_o_fechamento(pg):
    d, fatura, banco = novo(pg)
    sql(d, "update public.conta set status_fatura = 'FECHADA', valor_consolidado = 250 where id = %s", (fatura,))
    r = pagar(d, fatura, banco)
    chave = str(uuid.uuid4())
    e = estornar(d, fatura, r['movimento_id'], chave=chave)
    f = conta(d, fatura)
    planejado = sql(d, 'select financeiro.planejado_fatura(%s, %s, %s) as p', (PERFIL, CARTAO, FATURA_MES))[0]['p']
    assert (f['status_pagamento'], f['data_pagamento'], f['valor'], f['valor_executado'], f['status_fatura']) == \
        ('Pendente', None, planejado, Decimal('250.00'), 'FECHADA')
    assert '[ESTORNO] 2027-07-15' in f['observacoes']
    assert movimentos(d, fatura) == [
        {'tipo': 'DEBITO', 'valor': Decimal('250.00'), 'origem': 'FATURA', 'movimento_original_id': None},
        {'tipo': 'CREDITO', 'valor': Decimal('250.00'), 'origem': 'ESTORNO_FATURA', 'movimento_original_id': r['movimento_id']}]
    assert saldo(d, banco) == (Decimal('1000.00'), Decimal('1000.00'))
    [p] = registros(d, fatura)
    assert (p['estorno_movimento_id'], p['estorno_motivo'], p['estorno_user_id']) == \
        (e['movimento_estorno_id'], 'Pagamento em duplicidade no banco', USUARIO_A['id'])
    # Repetido: a mesma solicitacao devolve o mesmo estorno; outra e recusada. Sem segundo credito.
    assert estornar(d, fatura, r['movimento_id'], chave=chave)['repetida'] is True
    assert erro(lambda: estornar(d, fatura, r['movimento_id'])).diag.message_hint == 'NAO_PAGA'
    assert len(movimentos(d, fatura)) == 2
    assert 'motivo' in str(erro(lambda: estornar(d, fatura, r['movimento_id'], motivo='  ')))


# Fatura consolidada pelo Flask (rota real), paga e estornada: situacao financeira e consolidacao sao independentes.
def test_fatura_consolidada_paga_e_estornada_mantem_a_consolidacao(pg):
    d, fatura, banco = novo(pg)
    r = http(d, pg['pasta'], 'cons', 'post', f'/api/cartoes/{CARTAO}/faturas/2027-06/consolidar').resultado()
    assert r['status'] == 200

    def consolidacao():
        f = conta(d, fatura)
        return f['status_fatura'], f['valor_consolidado'], f['data_consolidacao']

    consolidada = consolidacao()
    assert consolidada[:2] == ('FECHADA', Decimal('250.00')) and consolidada[2] is not None
    pago = pagar(d, fatura, banco)
    assert conta(d, fatura)['status_pagamento'] == 'Pago' and consolidacao() == consolidada
    assert [(m['tipo'], m['valor']) for m in movimentos(d, fatura)] == [('DEBITO', Decimal('250.00'))]
    assert saldo(d, banco)[0] == Decimal('750.00')
    estornar(d, fatura, pago['movimento_id'])
    assert conta(d, fatura)['status_pagamento'] == 'Pendente' and consolidacao() == consolidada
    assert [(m['tipo'], m['valor'], m['movimento_original_id']) for m in movimentos(d, fatura)] == \
        [('DEBITO', Decimal('250.00'), None), ('CREDITO', Decimal('250.00'), pago['movimento_id'])]
    assert saldo(d, banco) == (Decimal('1000.00'), Decimal('1000.00'))
    [h] = dados(d, fatura)['pagamentos']
    assert (h['vigente'], h['estorno'] is not None, dados(d, fatura)['fatura']['status_fatura']) == (False, True, 'FECHADA')
    # D6 continua valendo na fatura reaberta: compra sem a confirmacao do total consolidado e recusada.
    compra = {'cartao_id': CARTAO, 'descricao': 'Na consolidada reaberta', 'valor': '10.00', 'total_parcelas': 1,
              'data_compra': '2027-06-22', 'mes_fatura': FATURA_MES, 'categoria_id': 951}
    e = erro(lambda: chamar(d, USUARIO_A, 'select financeiro.criar_compra(%s, %s::jsonb, gen_random_uuid())',
                            (PERFIL, json.dumps(compra))))
    assert e.diag.message_hint == 'CONSOLIDADA' and consolidacao() == consolidada


# 11. Pagar, estornar, pagar e estornar de novo: cada estorno referencia o seu pagamento
def test_pagar_estornar_pagar_estornar(pg):
    d, fatura, banco = novo(pg)
    r1 = pagar(d, fatura, banco)
    estornar(d, fatura, r1['movimento_id'])
    r2 = pagar(d, fatura, banco, valor='260.00', tipo_ajuste='JUROS', justificativa='Multa')
    assert erro(lambda: estornar(d, fatura, r1['movimento_id'])).diag.message_hint == 'JA_ESTORNADO'  # nao o 1o de novo
    e2 = estornar(d, fatura, r2['movimento_id'])
    ms = movimentos(d, fatura)
    assert [(m['tipo'], m['valor'], m['movimento_original_id']) for m in ms] == [
        ('DEBITO', Decimal('250.00'), None), ('CREDITO', Decimal('250.00'), r1['movimento_id']),
        ('DEBITO', Decimal('260.00'), None), ('CREDITO', Decimal('260.00'), r2['movimento_id'])]
    assert e2['movimento_original_id'] == r2['movimento_id'] and saldo(d, banco) == (Decimal('1000.00'), Decimal('1000.00'))
    tela = dados(d, fatura)
    assert [(Decimal(str(p['valor_pago'])), p['vigente'], p['estorno'] is not None) for p in tela['pagamentos']] == \
        [(Decimal('250.00'), False, True), (Decimal('260.00'), False, True)]
    assert (tela['pode_pagar'], tela['pode_estornar']) == (True, False)
    assert all(p['estornado_em'] is not None for p in registros(d, fatura))


# 12. Compras durante o pagamento (novo aplicativo e Flask): esperam a trava e nao entram na fatura paga
def test_compras_esperam_o_pagamento_e_vao_para_a_proxima(pg):
    d, fatura, banco = novo(pg)
    antes = compras_md5(d)
    conn = psycopg2.connect(d)  # pagamento em andamento: transacao aberta segurando perfil, fatura e conta
    cur = conn.cursor()
    cur.execute('set local role authenticated')
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims_usuario(USUARIO_A)),))
    cur.execute(PAGAR, (PERFIL, fatura, json.dumps({'conta_bancaria_id': banco, 'data_pagamento': '2027-07-10',
                                                    'valor_pago': '250.00', 'valor_executado': '250.00'}), str(uuid.uuid4())))
    compra = {'cartao_id': CARTAO, 'descricao': 'Compra no novo durante o pagamento', 'valor': '30.00', 'total_parcelas': 1,
              'data_compra': '2027-06-20', 'mes_fatura': FATURA_MES, 'categoria_id': 951}
    tarefa, resposta = em_thread(lambda: chamar(d, USUARIO_A, 'select financeiro.criar_compra(%s, %s::jsonb, gen_random_uuid())',
                                                (PERFIL, json.dumps(compra))))
    aguardar_bloqueio(d)
    flask = http(d, pg['pasta'], 'compra', 'post', f'/api/cartoes/{CARTAO}/lancamentos',
                 {'descricao': 'Compra no Flask durante o pagamento', 'valor': '20.00', 'data_compra': '2027-06-21',
                  'mes_fatura': '2027-06', 'categoria_id': 951, 'total_parcelas': 1})
    assert tarefa.is_alive() and flask.processo.poll() is None
    conn.commit()
    conn.close()
    tarefa.join(60)
    rf = flask.resultado()
    assert 'valor' in resposta and rf['status'] == 201
    meses = sql(d, "select descricao, mes_fatura from public.lancamento_agregado where descricao like 'Compra no %%' "
                   'order by descricao')
    assert [m['mes_fatura'] for m in meses] == [D(2027, 7, 1), D(2027, 7, 1)]  # as duas foram para a seguinte
    assert compras_md5(d) == antes and conta(d, fatura)['valor_executado'] == Decimal('250.00')
    assert len(movimentos(d, fatura)) == 1


# 13. Fatura paga: compra posterior segue a regra existente (vai para a proxima; a paga nao muda)
def test_compra_depois_do_pagamento_vai_para_a_proxima(pg):
    d, fatura, banco = novo(pg)
    pagar(d, fatura, banco)
    paga = sql(d, 'select md5(t::text) as h from public.conta t where id = %s', (fatura,))[0]['h']
    compra = {'cartao_id': CARTAO, 'descricao': 'Depois do pagamento', 'valor': '30.00', 'total_parcelas': 1,
              'data_compra': '2027-06-25', 'mes_fatura': FATURA_MES, 'categoria_id': 951}
    chamar(d, USUARIO_A, 'select financeiro.criar_compra(%s, %s::jsonb, gen_random_uuid())', (PERFIL, json.dumps(compra)))
    assert sql(d, "select mes_fatura from public.lancamento_agregado where descricao = 'Depois do pagamento'") == \
        [{'mes_fatura': D(2027, 7, 1)}]
    assert sql(d, 'select md5(t::text) as h from public.conta t where id = %s', (fatura,))[0]['h'] == paga


# 14. Sem permissao: anonimo, outro usuario, outro perfil, funcoes e tabela internas
def test_acesso_sem_permissao_recusado(pg):
    d, fatura, banco = novo(pg)
    assert 'permission denied' in str(erro(lambda: pagar(d, fatura, banco, usuario=None)))
    assert 'permission denied' in str(erro(lambda: dados(d, fatura, usuario=None)))
    assert 'nao autorizado' in str(erro(lambda: pagar(d, fatura, banco, usuario=USUARIO_B)))
    assert 'nao autorizado' in str(erro(lambda: dados(d, fatura, usuario=USUARIO_B)))
    assert 'nao autorizado' in str(erro(lambda: pagar(d, fatura, banco, perfil=ID['EMPRESA'])))  # A e LEITOR da Empresa
    for interna in ('executado_fatura(1)', 'saldo_da_conta(1)', 'atualizar_saldo_conta(1)', 'exigir_pagamento_novo(101)',
                    'travar_fatura_do_perfil(101, 1)', 'pagamento_vigente(1)'):
        assert 'permission denied' in str(erro(lambda: chamar(d, USUARIO_A, f'select financeiro.{interna}')))
    assert 'permission denied' in str(erro(lambda: chamar(d, USUARIO_A, 'select count(*) from financeiro.pagamento_fatura')))
    assert nada_mudou(d, fatura, banco)


# D5: um sistema por perfil. Perfil no Flask: o novo nao paga; perfil no novo: o Flask nao paga nem estorna fatura.
def test_um_sistema_responsavel_por_perfil(pg):
    d, fatura, banco = pg['dsn'], pg['fatura'], pg['banco']
    assert erro(lambda: pagar(d, fatura, banco)).diag.message_hint == 'SISTEMA_FLASK'
    assert dados(d, fatura)['sistema'] == 'FLASK' and dados(d, fatura)['pode_pagar'] is False
    assert nada_mudou(d, fatura, banco)
    atribuir(d, 'PESSOAL')
    r = http(d, pg['pasta'], 'pag', 'post', f'/api/despesas/{fatura}/pagar', pagar_corpo(banco)).resultado()
    assert (r['status'], r['json']['codigo']) == (409, 'SISTEMA_NOVO') and nada_mudou(d, fatura, banco)
    pago = pagar(d, fatura, banco)
    r = http(d, pg['pasta'], 'est', 'post', f'/api/despesas/{fatura}/estornar-pagamento',
             {'motivo': 'teste', 'data_estorno': '2027-07-15'}).resultado()
    assert (r['status'], r['json']['codigo']) == (409, 'SISTEMA_NOVO')
    assert [m['tipo'] for m in movimentos(d, fatura)] == ['DEBITO'] and pago['movimento_id']


# Pagamento feito pelo Flask (antes da migracao do perfil) pode ser estornado pelo novo aplicativo.
def test_estorno_de_pagamento_feito_pelo_flask(pg):
    d, fatura, banco = pg['dsn'], pg['fatura'], pg['banco']
    assert http(d, pg['pasta'], 'pag', 'post', f'/api/despesas/{fatura}/pagar', pagar_corpo(banco)).resultado()['status'] == 200
    atribuir(d, 'PESSOAL')
    [p] = dados(d, fatura)['pagamentos']
    assert (p['origem'], p['vigente']) == ('FLASK', True)
    estornar(d, fatura, p['movimento_id'])
    [r] = registros(d, fatura)
    assert (r['origem'], r['movimento_id'], r['valor_executado'], r['estornado_em'] is not None) == \
        ('FLASK', p['movimento_id'], None, True)
    assert conta(d, fatura)['status_pagamento'] == 'Pendente' and saldo(d, banco) == (Decimal('1000.00'), Decimal('1000.00'))
