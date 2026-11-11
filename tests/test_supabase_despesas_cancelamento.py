"""
Testes FIN-DESPESAS-CANCELAMENTO-01 (P23, migration 20261226090000, retomada sobre a 1224 e a 1225) — cancelar a obrigacao de uma ocorrencia de despesa
cujo pagamento foi integralmente estornado, em cluster PostgreSQL local descartavel e com dados ficticios.

Cenario como o real (Psicologa, 11/2026): recorrencia semanal de R$ 250 (terca), Pix e sem conta bancaria; as 4 sessoes
de 02/2027 pagas no lote, os 4 pagamentos estornados e a sessao de 09/02 paga de novo. A sessao de 02/02 foi desmarcada:
cancelar so ela. A conta fica 'Dispensada' (fora das pendencias), o pagamento e o estorno ficam, a recorrencia continua
ativa e o gerador nao recria a ocorrencia.
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_categorias_recorrencias import CATEGORIA, banco, contas, erro, nova_recorrencia, versao_despesa  # noqa: F401
from tests.test_supabase_despesas import _paralelo
from tests.test_supabase_pagamento_lote import lote, md5, saldo
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, USUARIO_B, chamar, cluster, gerar_confirmado, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
MES = '2027-02-01'  # 4 tercas: 02, 09, 16 e 23
RAIZ = Path(__file__).resolve().parent.parent
MIGRATION = RAIZ / 'supabase/migrations/20261226090000_financeiro_despesas_cancelamento.sql'
REVERSAO = RAIZ / 'supabase/reversao/20261226090000_despesas_cancelamento_anterior.sql'


def banco_pessoal(dsn):
    return sql(dsn, "select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")[0]['id']


def do_mes(dsn, item):
    return sql(dsn, 'select id, descricao, valor, data_vencimento, status_pagamento from public.conta '
                    'where item_despesa_id = %s and mes_referencia = %s order by data_vencimento', (item, MES))


def pagar(dsn, conta_id, banco_id, valor='250.00'):
    return rpc(dsn, 'pagar_despesa', PESSOAL, conta_id, {'conta_bancaria_id': banco_id, 'data_pagamento': '2027-02-12',
                                                         'valor_pago': valor, 'valor_devido': valor}, str(uuid.uuid4()))


def estornar(dsn, conta_id):
    movimento = sql(dsn, "select financeiro.debito_vigente(%s, 'DESPESA') m", (conta_id,))[0]['m']
    return rpc(dsn, 'estornar_pagamento_despesa', PESSOAL, conta_id, movimento,
               {'motivo': 'Pago por engano', 'data_estorno': '2027-02-13'}, str(uuid.uuid4()))


def cancelar(dsn, conta_id, versao=None, usuario=USUARIO_A, perfil=PESSOAL):
    return rpc(dsn, 'cancelar_despesa', perfil, conta_id, versao or versao_despesa(dsn, conta_id), usuario=usuario)


def previa(dsn, conta_id, usuario=USUARIO_A):
    return rpc(dsn, 'previa_cancelamento_despesa', PESSOAL, conta_id, usuario=usuario)


def pendentes_na_tela(dsn, item):
    """O que Despesas lista em 02/2027 para a recorrencia (contas_do_mes), sem as pagas: o agrupamento das pendentes."""
    linhas = chamar(dsn, USUARIO_A, "select coalesce(json_agg(x), '[]'::json) from financeiro.contas_do_mes(%s, %s) x", (PESSOAL, MES))
    nome = sql(dsn, 'select nome from public.item_despesa where id = %s', (item,))[0]['nome']
    return [x for x in linhas if x['nome'].startswith(nome) and x['situacao'] != 'PAGA']


def total(linhas):
    return sum(Decimal(str(x['valor'])) for x in linhas)


def caso_real(dsn):
    """Psicologa: 4 sessoes pagas no lote, 4 estornos, 09/02 paga de novo. Devolve (item, banco, contas por dia)."""
    item = nova_recorrencia(dsn, 'Psicologa', 'semanal_1_2', '2027-02-02', valor='250.00')
    sql(dsn, "update public.item_despesa set meio_pagamento = 'pix' where id = %s", (item,))
    gerar_confirmado(dsn, mes=MES)
    banco_id = banco_pessoal(dsn)
    sessoes = do_mes(dsn, item)
    assert [c['data_vencimento'].day for c in sessoes] == [2, 9, 16, 23]
    lote(dsn, sessoes, banco_id)
    for c in sessoes:
        estornar(dsn, c['id'])
    pagar(dsn, sessoes[1]['id'], banco_id)
    return item, banco_id, {c['data_vencimento'].day: c['id'] for c in sessoes}


def retrato(dsn, item, banco_id):
    return {'movimentos': md5(dsn, 'public.movimento_financeiro'), 'pagamentos': md5(dsn, 'financeiro.pagamento_fatura'),
            'recorrencia': md5(dsn, 'public.item_despesa', 'id = %s', (item,)), 'saldo': saldo(dsn, banco_id),
            'bancos': md5(dsn, 'public.conta_bancaria'), 'operacoes': sql(dsn, 'select count(*) n from financeiro.operacao_despesa')[0]['n'],
            'contas': sql(dsn, 'select count(*) n from public.conta')[0]['n']}


# =====================================================================================================================
# Caso real: so a sessao de 02/02 deixa de ser exigivel
# =====================================================================================================================

def test_estornada_integralmente_cancela_so_a_sessao_e_preserva_o_historico(banco):
    item, banco_id, dia = caso_real(banco)
    antes = pendentes_na_tela(banco, item)
    assert [x['data_vencimento'] for x in antes] == ['2027-02-02', '2027-02-16', '2027-02-23'] and total(antes) == Decimal('750.00')
    p = previa(banco, dia[2])
    assert p['elegivel'] is True and len(p['pagamentos']) == 1 and len(p['estornos']) == 1
    assert Decimal(str(p['valor_pago'])) == Decimal(str(p['valor_estornado'])) == Decimal('250.00')
    outras = md5(banco, 'public.conta', 'id = any(%s)', ([dia[9], dia[16], dia[23]],))
    r0 = retrato(banco, item, banco_id)

    r = cancelar(banco, dia[2])
    assert r['cancelada'] is True and r['competencia_dispensada'] is True and Decimal(str(r['valor'])) == Decimal('250.00')
    r0['operacoes'] += 1  # a linha de auditoria do cancelamento

    depois = pendentes_na_tela(banco, item)
    assert [x['data_vencimento'] for x in depois] == ['2027-02-16', '2027-02-23'] and total(depois) == Decimal('500.00')
    assert sql(banco, 'select status_pagamento s, data_pagamento d, valor v from public.conta where id = %s', (dia[2],))[0] == \
        {'s': 'Dispensada', 'd': None, 'v': Decimal('250.00')}
    # pagamento, estorno, registro do pagamento, saldo, recorrencia (ativa) e as outras sessoes: tudo igual
    assert retrato(banco, item, banco_id) == r0
    assert md5(banco, 'public.conta', 'id = any(%s)', ([dia[9], dia[16], dia[23]],)) == outras
    assert sql(banco, 'select ativo from public.item_despesa where id = %s', (item,))[0]['ativo'] is True
    oc = sql(banco, "select situacao, conta_id, motivo from financeiro.recorrencia_ocorrencia where item_despesa_id = %s "
                    "and data_ocorrencia = '2027-02-02'", (item,))[0]
    assert oc['situacao'] == 'DISPENSADA' and oc['conta_id'] == dia[2]
    assert oc['motivo'].startswith(f"Obrigacao cancelada pelo usuario: conta {dia[2]}, R$ 250.00, vencimento 02/02/2027")
    # trilha de auditoria: uma operacao com a conta antes, o pagamento e o estorno preservados e o motivo
    aud = sql(banco, "select user_id::text u, perfil_financeiro_id p, resultado r from financeiro.operacao_despesa where operacao = 'cancelar_despesa'")
    assert len(aud) == 1 and aud[0]['u'] == USUARIO_A['id'] and aud[0]['p'] == PESSOAL
    assert (aud[0]['r']['conta_id'], aud[0]['r']['conta_antes']['status_pagamento'], len(aud[0]['r']['pagamentos']), len(aud[0]['r']['estornos'])) ==         (dia[2], 'Pendente', 1, 1)


def test_nao_cria_pagamento_nem_estorno(banco):
    item, banco_id, dia = caso_real(banco)
    n = sql(banco, 'select count(*) n from public.movimento_financeiro where conta_id = %s', (dia[2],))[0]['n']
    cancelar(banco, dia[2])
    movs = sql(banco, 'select tipo, origem, valor from public.movimento_financeiro where conta_id = %s order by id', (dia[2],))
    assert len(movs) == n == 2 and [(m['tipo'], m['origem']) for m in movs] == [('DEBITO', 'DESPESA'), ('CREDITO', 'ESTORNO_DESPESA')]


def test_gerador_nao_recria_a_sessao_cancelada(banco):
    item, banco_id, dia = caso_real(banco)
    cancelar(banco, dia[2])
    n = sql(banco, 'select count(*) n from public.conta where item_despesa_id = %s', (item,))[0]['n']
    for mes in (MES, '2027-03-01'):
        gerar_confirmado(banco, mes=mes)
    assert sql(banco, "select count(*) n from public.conta where item_despesa_id = %s and data_vencimento = '2027-02-02'", (item,))[0]['n'] == 1
    assert sql(banco, "select count(*) n from public.conta where item_despesa_id = %s and mes_referencia = %s", (item, MES))[0]['n'] == 4
    plano = chamar(banco, USUARIO_A, 'select financeiro.previa_geracao(%s, %s)', (PESSOAL, MES))
    alvo = [x for x in plano['itens'] if x.get('item_id') == item and x.get('data_vencimento') == '2027-02-02']
    assert all(x.get('situacao') != 'A_GERAR' for x in alvo)
    assert sql(banco, "select count(*) n from public.conta where item_despesa_id = %s", (item,))[0]['n'] >= n


def test_repetir_nao_muda_nada(banco):
    item, banco_id, dia = caso_real(banco)
    cancelar(banco, dia[2])
    r0 = retrato(banco, item, banco_id)
    ocorrencias = lambda: sql(banco, 'select md5(string_agg(t::text, %s order by data_ocorrencia)) h '  # noqa: E731
                                     'from financeiro.recorrencia_ocorrencia t where item_despesa_id = %s', ('|', item))[0]['h']
    oc = ocorrencias()
    r = cancelar(banco, dia[2], versao='qualquer')  # ja cancelada: idempotente, sem conferir versao
    assert r == {'conta_id': dia[2], 'cancelada': True, 'repetida': True}
    assert retrato(banco, item, banco_id) == r0
    assert ocorrencias() == oc
    assert previa(banco, dia[2])['cancelada'] is True


def test_versao_desatualizada_e_recusada(banco):
    item, banco_id, dia = caso_real(banco)
    e = erro(cancelar, banco, dia[2], versao='versao-antiga')
    assert 'alterada por outra operacao' in str(e)
    assert sql(banco, 'select status_pagamento s from public.conta where id = %s', (dia[2],))[0]['s'] == 'Pendente'


# =====================================================================================================================
# Matriz de decisao
# =====================================================================================================================

def test_nunca_paga_segue_pela_exclusao_comum(banco):
    item, banco_id, dia = caso_real(banco)
    sessao = do_mes(banco, item)[2]['id']  # 16/02 ja estornada; usa uma de 03/2027 nunca paga
    gerar_confirmado(banco, mes='2027-03-01')
    nunca = contas(banco, item)[-1]['id']
    p = previa(banco, nunca)
    assert p['elegivel'] is False and p['exclusao'] is True
    assert 'use Excluir' in str(erro(cancelar, banco, nunca))
    # a exclusao comum continua a mesma (P22): conta sai e a ocorrencia fica dispensada, sem conta
    rpc(banco, 'excluir_despesa', PESSOAL, nunca, versao_despesa(banco, nunca))
    assert not sql(banco, 'select 1 from public.conta where id = %s', (nunca,))
    oc = sql(banco, "select situacao, conta_id, motivo from financeiro.recorrencia_ocorrencia where item_despesa_id = %s "
                    "and situacao = 'DISPENSADA' order by data_ocorrencia desc limit 1", (item,))[0]
    assert (oc['situacao'], oc['conta_id'], oc['motivo']) == ('DISPENSADA', None, 'Conta excluida pelo usuario')
    assert sessao  # a estornada nao foi tocada
    assert sql(banco, 'select status_pagamento s from public.conta where id = %s', (sessao,))[0]['s'] == 'Pendente'


def test_paga_com_pagamento_valido_e_bloqueada(banco):
    item, banco_id, dia = caso_real(banco)  # 09/02 foi paga de novo
    p = previa(banco, dia[9])
    assert p['elegivel'] is False and 'Pagamento ainda valido' in p['motivo']
    assert 'Pagamento ainda valido' in str(erro(cancelar, banco, dia[9]))
    assert sql(banco, 'select status_pagamento s from public.conta where id = %s', (dia[9],))[0]['s'] == 'Pago'


def test_estorno_parcial_com_valor_residual_e_bloqueado(banco):
    item, banco_id, dia = caso_real(banco)
    # dado ficticio do cluster: o estorno da sessao de 16/02 passa a devolver so R$ 100
    sql(banco, "update public.movimento_financeiro set valor = 100 where conta_id = %s and origem = 'ESTORNO_DESPESA'", (dia[16],))
    p = previa(banco, dia[16])
    assert p['elegivel'] is False and 'parcialmente estornado' in p['motivo'] and Decimal(str(p['valor_residual'])) == Decimal('150')
    assert 'parcialmente estornado' in str(erro(cancelar, banco, dia[16]))


def test_pagamento_sem_estorno_em_conta_pendente_e_bloqueado(banco):
    item, banco_id, dia = caso_real(banco)
    sql(banco, "delete from public.movimento_financeiro where conta_id = %s and origem = 'ESTORNO_DESPESA'", (dia[23],))
    assert 'parcialmente estornado' in previa(banco, dia[23])['motivo']


@pytest.mark.parametrize('alteracao', [
    "insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento, "
    "conta_id, origem) values ({perfil}, {banco}, 'CREDITO', 10, 'Ajuste avulso', '2027-02-14', {conta}, 'AJUSTE')",
    "update public.movimento_financeiro set movimento_original_id = null where conta_id = {conta} and origem = 'ESTORNO_DESPESA'",
    "update financeiro.pagamento_fatura set estorno_movimento_id = null where fatura_id = {conta}",
])
def test_movimento_nao_conciliado_e_bloqueado(banco, alteracao):
    item, banco_id, dia = caso_real(banco)
    sql(banco, alteracao.format(perfil=PESSOAL, banco=banco_id, conta=dia[16]))
    p = previa(banco, dia[16])
    assert p['elegivel'] is False and ('nao conciliado' in p['motivo'] or 'parcialmente' in p['motivo'])
    assert 'Operacao bloqueada' in str(erro(cancelar, banco, dia[16]))


def test_outro_vinculo_financeiro_bloqueia_com_justificativa(banco):
    item, banco_id, dia = caso_real(banco)
    sql(banco, "insert into public.despesa_prevista (origem_tipo, origem_id, categoria_id, data_prevista, data_original_prevista, "
               "data_atual_prevista, valor_previsto, status, conta_id, perfil_financeiro_id) values "
               "('TESTE', 1, %s, '2027-02-16', '2027-02-16', '2027-02-16', 250, 'CONFIRMADA', %s, %s)", (CATEGORIA, dia[16], PESSOAL))
    p = previa(banco, dia[16])
    assert p['elegivel'] is False and p['motivo'] == 'Protegida por outro vinculo financeiro: despesa prevista'
    assert 'despesa prevista' in str(erro(cancelar, banco, dia[16]))


def test_avulsa_estornada_tambem_cancela_sem_registro_de_recorrencia(banco):
    banco_id = banco_pessoal(banco)
    criada = rpc(banco, 'criar_despesa', PESSOAL, {'nome': 'Consulta avulsa', 'valor': '180.00', 'categoria_id': CATEGORIA,
                                                   'data_vencimento': '2027-02-11'}, str(uuid.uuid4()))
    pagar(banco, criada['conta_id'], banco_id, '180.00')
    estornar(banco, criada['conta_id'])
    r = cancelar(banco, criada['conta_id'])
    assert r['cancelada'] is True and r['competencia_dispensada'] is False
    assert sql(banco, 'select status_pagamento s from public.conta where id = %s', (criada['conta_id'],))[0]['s'] == 'Dispensada'
    assert sql(banco, 'select count(*) n from public.item_despesa where id = %s', (criada['item_id'],))[0]['n'] == 1


# =====================================================================================================================
# Depois do cancelamento: pagamento recusado, fora dos totais, P22 sem a cancelada
# =====================================================================================================================

def test_obrigacao_cancelada_nao_se_paga_nem_entra_no_lote(banco):
    item, banco_id, dia = caso_real(banco)
    cancelar(banco, dia[2])
    assert 'Obrigacao cancelada' in str(erro(pagar, banco, dia[2], banco_id))
    pend = [c for c in do_mes(banco, item) if c['status_pagamento'] == 'Pendente']
    assert [c['data_vencimento'].day for c in pend] == [16, 23]
    com_cancelada = [c for c in do_mes(banco, item) if c['status_pagamento'] != 'Pago']
    assert erro(lote, banco, com_cancelada, banco_id)  # a tela nao a mostra; o banco tambem nao a aceita no lote
    r = lote(banco, pend, banco_id)
    assert r['pagas'] == 2 and Decimal(str(r['valor_total'])) == Decimal('500.00')
    assert sql(banco, 'select status_pagamento s from public.conta where id = %s', (dia[2],))[0]['s'] == 'Dispensada'


def test_fora_do_dashboard_e_das_despesas_diretas(banco):
    item, banco_id, dia = caso_real(banco)
    painel = lambda: Decimal(str(rpc(banco, 'dashboard_resumo_tela', PESSOAL, MES[:7])['fluxo_caixa']['resumo']['despesas_previstas']))  # noqa: E731
    diretas = lambda: {x['id'] for x in rpc(banco, 'despesas_diretas_tela', PESSOAL)}  # noqa: E731
    d0, ids0 = painel(), diretas()
    assert dia[2] in ids0
    cancelar(banco, dia[2])
    assert painel() == d0 - Decimal('250.00')
    assert diretas() == ids0 - {dia[2]}


def test_p22_previa_nao_lista_a_cancelada(banco):
    item, banco_id, dia = caso_real(banco)
    cancelar(banco, dia[2])
    p = rpc(banco, 'previa_interrupcao_recorrencia', PESSOAL, item, MES, None)
    ids = {x['registro_id'] for x in p['afetadas']} | {x['registro_id'] for x in p['preservadas']}
    assert dia[2] not in ids and {dia[9], dia[16], dia[23]} <= ids


def test_p22_interrupcao_depois_do_cancelamento(banco):
    item, banco_id, dia = caso_real(banco)
    cancelar(banco, dia[2])
    gerar_confirmado(banco, mes='2027-03-01')
    p = rpc(banco, 'previa_interrupcao_recorrencia', PESSOAL, item, '2027-03-01', None)
    r = rpc(banco, 'interromper_recorrencia', PESSOAL, item, sql(banco, 'select financeiro.versao_recorrencia(%s) v', (item,))[0]['v'],
            '2027-03-01', p['quantidade'], None)
    assert r['canceladas'] == p['quantidade'] > 0
    assert sql(banco, 'select status_pagamento s from public.conta where id = %s', (dia[2],))[0]['s'] == 'Dispensada'


# =====================================================================================================================
# Concorrencia, perfis e permissoes
# =====================================================================================================================

def test_cancelamento_e_pagamento_simultaneos_so_um_vale(banco):
    item, banco_id, dia = caso_real(banco)
    versao = versao_despesa(banco, dia[2])
    resultados = _paralelo([lambda: cancelar(banco, dia[2], versao=versao), lambda: pagar(banco, dia[2], banco_id)])
    oks = [r[0] for r in resultados]
    assert oks.count('ok') == 1, resultados
    conta = sql(banco, 'select status_pagamento s from public.conta where id = %s', (dia[2],))[0]['s']
    movs = sql(banco, "select count(*) n from public.movimento_financeiro where conta_id = %s and origem = 'DESPESA'", (dia[2],))[0]['n']
    if resultados[0][0] == 'ok':  # cancelou: o pagamento esperou a conta e encontrou a obrigacao cancelada
        assert conta == 'Dispensada' and movs == 1
    else:  # pagou primeiro: a versao mudou e o cancelamento foi recusado
        assert conta == 'Pago' and movs == 2


def test_outro_perfil_e_somente_leitura_sao_recusados(banco):
    item, banco_id, dia = caso_real(banco)
    assert 'nao autorizado' in str(erro(cancelar, banco, dia[2], usuario=USUARIO_B)) or \
        'nao encontrada' in str(erro(cancelar, banco, dia[2], usuario=USUARIO_B))
    assert 'nao autorizado' in str(erro(previa, banco, dia[2], usuario=USUARIO_B))
    assert sql(banco, 'select status_pagamento s from public.conta where id = %s', (dia[2],))[0]['s'] == 'Pendente'


def test_permissoes_das_funcoes(banco):
    linhas = sql(banco, """select p.proname f, has_function_privilege('authenticated', p.oid, 'execute') a,
                                  has_function_privilege('anon', p.oid, 'execute') n, p.prosecdef d,
                                  coalesce(array_to_string(p.proconfig, ','), '') = 'search_path=""' s
                             from pg_proc p join pg_namespace s on s.oid = p.pronamespace
                            where s.nspname = 'financeiro' and p.proname in ('cancelar_despesa', 'previa_cancelamento_despesa',
                                  'situacao_cancelamento_despesa', 'registrar_dispensa_recorrente') order by 1""")
    assert {x['f']: (x['a'], x['n']) for x in linhas} == {
        'cancelar_despesa': (True, False), 'previa_cancelamento_despesa': (True, False),
        'registrar_dispensa_recorrente': (False, False), 'situacao_cancelamento_despesa': (False, False)}
    assert all(x['d'] and x['s'] for x in linhas)


# =====================================================================================================================
# Reversao
# =====================================================================================================================

def _executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_reversao_recusa_com_obrigacao_cancelada_e_reaplica_sem_ela(banco):
    item, banco_id, dia = caso_real(banco)
    cancelar(banco, dia[2])
    assert 'obrigacao cancelada' in str(erro(_executar, banco, REVERSAO))
    assert sql(banco, "select count(*) n from pg_proc where proname = 'cancelar_despesa'")[0]['n'] == 1  # nada mudou
    sql(banco, "update public.conta set status_pagamento = 'Pendente' where id = %s", (dia[2],))  # so no cluster descartavel
    _executar(banco, REVERSAO)
    assert sql(banco, "select count(*) n from pg_proc where proname in ('cancelar_despesa', 'registrar_dispensa_recorrente')")[0]['n'] == 0
    assert 'Possui movimento financeiro vinculado' in str(erro(rpc, banco, 'excluir_despesa', PESSOAL, dia[16], versao_despesa(banco, dia[16])))
    _executar(banco, MIGRATION)
    assert cancelar(banco, dia[16])['cancelada'] is True
