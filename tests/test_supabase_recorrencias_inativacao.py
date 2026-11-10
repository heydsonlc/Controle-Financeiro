"""
Testes FIN-RECORRENCIAS-INATIVACAO-01 (P22, migration 20261221090000), em cluster PostgreSQL local descartavel e com dados
ficticios (cenario do FIN-RECORRENCIA-1; as recorrencias dele ficam inativas, so as deste teste geram contas).

Inativar interrompe a recorrencia a partir da data de efeito: as ocorrencias ja geradas, pendentes, sem pagamento, sem
movimento e nao vencidas deixam de ser exigiveis (competencia DISPENSADA, como na exclusao de uma ocorrencia); pagas,
com movimento, vencidas e cobrancas reais ficam. Previa somente leitura, transacao unica, idempotencia, concorrencia,
isolamento por perfil, "esta e as futuras" de Despesas, cartao (previsoes da fatura), semanal, totais de Despesas,
Faturas e Dashboard, retomada sem periodo inativo e sem restaurar em silencio, reversao e reaplicacao.
"""
import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from dateutil.relativedelta import relativedelta

from tests.test_supabase_cartoes import ASSINATURAS, CARTAO, fatura
from tests.test_supabase_categorias_recorrencias import banco, nova_recorrencia  # noqa: F401  (fixture reaproveitada)
from tests.test_supabase_despesas import _paralelo
from tests.test_supabase_recorrencia import (  # noqa: F401
    ID,
    PG_BIN,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,
    gerar,
    gerar_confirmado,
    previa,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

RAIZ = Path(__file__).resolve().parent.parent
PESSOAL = ID['PESSOAL']
MIGRATION = RAIZ / 'supabase/migrations/20261221090000_financeiro_recorrencias_inativacao.sql'
REVERSAO = RAIZ / 'supabase/reversao/20261221090000_recorrencias_inativacao_anterior.sql'
PUBLICAS = ['financeiro.previa_interrupcao_recorrencia(integer, integer, date, integer)',
            'financeiro.interromper_recorrencia(integer, integer, text, date, integer, integer)',
            'financeiro.previa_retomada_recorrencia(integer, integer, date)',
            'financeiro.retomar_recorrencia(integer, integer, text, date, boolean)']
INTERNAS = ['financeiro.dispensar_conta_recorrente(public.item_despesa, public.conta, text)',
            'financeiro.efeito_interrupcao(date)', 'financeiro.motivo_sem_interrupcao(integer, public.item_despesa)',
            'financeiro.ocorrencias_interrupcao(integer, date, integer)', 'financeiro.lacunas_da_recorrencia(integer, date)',
            'financeiro.exigir_recorrencia_fora_do_cartao(integer, integer)']
TABELAS = ('public.conta', 'public.lancamento_agregado', 'financeiro.recorrencia_competencia', 'financeiro.recorrencia_ocorrencia',
           'public.movimento_financeiro', 'public.conta_bancaria', 'public.item_despesa')


def rpc(dsn, funcao, *args, usuario=USUARIO_A):
    valores = [json.dumps(a) if isinstance(a, (dict, list)) else a for a in args]
    marcadores = ', '.join('%s::jsonb' if isinstance(a, (dict, list)) else '%s' for a in args)
    return chamar(dsn, usuario, f'select financeiro.{funcao}({marcadores})', valores)


def erro(funcao, *args, **kw):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args, **kw)
    return e.value


def hoje(dsn):
    return sql(dsn, "select (now() at time zone 'America/Sao_Paulo')::date as d")[0]['d']


def mes(d, k=0):
    return (d.replace(day=1) + relativedelta(months=k))


def versao(dsn, item):
    return sql(dsn, 'select financeiro.versao_recorrencia(%s) as v', (item,))[0]['v']


def previa_int(dsn, item, efeito=None, conta=None, usuario=USUARIO_A, perfil=PESSOAL):
    return rpc(dsn, 'previa_interrupcao_recorrencia', perfil, item, efeito, conta, usuario=usuario)


def interromper(dsn, item, efeito=None, esperadas=None, conta=None, usuario=USUARIO_A, perfil=PESSOAL, versao_=None):
    return rpc(dsn, 'interromper_recorrencia', perfil, item, versao_ or versao(dsn, item), efeito, esperadas, conta, usuario=usuario)


def previa_ret(dsn, item, retomada=None, usuario=USUARIO_A):
    return rpc(dsn, 'previa_retomada_recorrencia', PESSOAL, item, retomada, usuario=usuario)


def retomar(dsn, item, retomada=None, restaurar=False, usuario=USUARIO_A):
    return rpc(dsn, 'retomar_recorrencia', PESSOAL, item, versao(dsn, item), retomada, restaurar, usuario=usuario)


def contas(dsn, item):
    return sql(dsn, 'select id, mes_referencia, data_vencimento, valor, status_pagamento from public.conta '
                    'where item_despesa_id = %s order by data_vencimento, id', (item,))


def competencias(dsn, item):
    return {r['competencia']: (r['situacao'], r['motivo']) for r in sql(
        dsn, 'select competencia, situacao, motivo from financeiro.recorrencia_competencia where item_despesa_id = %s', (item,))}


def gravado(dsn):
    return {t: sql(dsn, f"select count(*) as n, coalesce(md5(string_agg(x::text, '|' order by x::text)), '') as h from {t} x")[0]
            for t in TABELAS}


def conta_pessoal(dsn):
    return sql(dsn, "select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")[0]['id']


def pagar(dsn, conta, data):
    return rpc(dsn, 'pagar_despesa', PESSOAL, conta['id'], {'conta_bancaria_id': conta_pessoal(dsn), 'data_pagamento': str(data),
                                                           'valor_pago': str(conta['valor']), 'valor_devido': str(conta['valor'])},
               str(uuid.uuid4()))


def telefonia(dsn, meio='debito_automatico', dia=28):
    """Como o caso real: mensal de R$ 70 desde 2 meses atras, contas geradas ate 5 meses adiante; a de 2 meses atras paga
    (com movimento), a do mes passado vencida e pendente, as demais pendentes."""
    h = hoje(dsn)
    item = nova_recorrencia(dsn, 'Telefonia', 'mensal', str(mes(h, -2).replace(day=dia)), valor='70.00')
    if meio == 'debito_automatico':
        sql(dsn, "update public.item_despesa set meio_pagamento = 'debito_automatico', conta_bancaria_id = %s where id = %s",
            (conta_pessoal(dsn), item))
    else:
        sql(dsn, 'update public.item_despesa set meio_pagamento = %s where id = %s', (meio, item))
    gerar_confirmado(dsn, mes=str(mes(h, 4)))
    lista = contas(dsn, item)
    assert [c['mes_referencia'] for c in lista] == [mes(h, k) for k in range(-2, 6)]
    pagar(dsn, lista[0], h)
    return item, contas(dsn, item), h


def eleg(lista, h, efeito):
    """Esperado: pendente, competencia >= efeito e vencimento >= hoje."""
    return [c['id'] for c in lista if c['status_pagamento'] == 'Pendente' and c['mes_referencia'] >= efeito and c['data_vencimento'] >= h]


# ---------------------------------------------------------------------------
# Seguranca das funcoes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('funcao', PUBLICAS + INTERNAS)
def test_funcoes_seguras(banco, funcao):  # noqa: F811
    r = sql(banco, f"""select p.prosecdef as definer, coalesce(array_to_string(p.proconfig, ','), '') as config,
                              has_function_privilege('anon', '{funcao}', 'EXECUTE') as anon,
                              has_function_privilege('authenticated', '{funcao}', 'EXECUTE') as autenticado
                         from pg_proc p where p.oid = '{funcao}'::regprocedure""")[0]
    assert 'search_path=""' in r['config'] and r['anon'] is False
    assert r['autenticado'] is (funcao in PUBLICAS)


# ---------------------------------------------------------------------------
# 1-4. Inativacao, ocorrencias ja geradas, pagas e movimentos preservados
# ---------------------------------------------------------------------------

def test_previa_mostra_afetadas_e_preservadas_sem_gravar(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    antes = gravado(banco)
    p = previa_int(banco, item)
    efeito = mes(h, 1)
    assert p['efeito'] == str(efeito) and p['efeito_padrao'] == str(efeito) and p['pode_interromper'] is True
    assert [a['registro_id'] for a in p['afetadas']] == eleg(lista, h, efeito) == [c['id'] for c in lista[3:]]
    assert p['quantidade'] == 5 and Decimal(str(p['total'])) == Decimal('350.00')
    assert p['preservadas'] == []  # a paga e a vencida sao anteriores ao efeito: nem entram
    assert gravado(banco) == antes


def test_interromper_cancela_futuras_e_preserva_paga_vencida_e_atual(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    movimentos = sql(banco, 'select count(*) as n from public.movimento_financeiro')[0]['n']
    saldo = sql(banco, 'select saldo_atual from public.conta_bancaria where id = %s', (conta_pessoal(banco),))
    r = interromper(banco, item, esperadas=5)
    assert (r['canceladas'], Decimal(str(r['valor_cancelado'])), r['ativo']) == (5, Decimal('350.00'), False)
    restantes = contas(banco, item)
    assert [c['id'] for c in restantes] == [c['id'] for c in lista[:3]]  # paga, vencida e a do mes atual ficam
    assert restantes[0]['status_pagamento'] == 'Pago'
    comps = competencias(banco, item)
    for c in lista[3:]:
        situacao, motivo = comps[c['mes_referencia']]
        assert situacao == 'DISPENSADA' and motivo.startswith('Interrompida pela inativacao') and f"#{c['id']}" in motivo
    assert sql(banco, 'select ativo from public.item_despesa where id = %s', (item,))[0]['ativo'] is False
    # Movimento e saldo nao mudam (o pagamento fica como foi)
    assert sql(banco, 'select count(*) as n from public.movimento_financeiro')[0]['n'] == movimentos
    assert sql(banco, 'select saldo_atual from public.conta_bancaria where id = %s', (conta_pessoal(banco),)) == saldo


def test_incluir_competencia_atual_so_tira_o_que_nao_venceu(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    p = previa_int(banco, item, efeito=str(mes(h)))
    esperado = eleg(lista, h, mes(h))
    assert [a['registro_id'] for a in p['afetadas']] == esperado
    r = interromper(banco, item, efeito=str(mes(h)), esperadas=len(esperado))
    assert r['canceladas'] == len(esperado)
    assert {c['id'] for c in contas(banco, item)} == {c['id'] for c in lista} - set(esperado)


def test_conta_paga_e_com_movimento_depois_do_efeito_fica(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    futura = lista[5]
    pagar(banco, futura, h)  # paga adiantado: tem movimento
    p = previa_int(banco, item)
    assert futura['id'] in [x['registro_id'] for x in p['preservadas']]
    assert next(x for x in p['preservadas'] if x['registro_id'] == futura['id'])['motivo'].startswith('Despesa paga')
    interromper(banco, item, esperadas=p['quantidade'])
    assert sql(banco, 'select status_pagamento from public.conta where id = %s', (futura['id'],))[0]['status_pagamento'] == 'Pago'
    assert sql(banco, 'select count(*) as n from public.movimento_financeiro where conta_id = %s', (futura['id'],))[0]['n'] == 1


def test_previa_desatualizada_recusa_sem_gravar(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    antes = gravado(banco)
    e = erro(interromper, banco, item, esperadas=4)
    assert e.diag.message_hint == 'PREVIA' and gravado(banco) == antes


def test_repetir_nao_muda_mais_nada(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    interromper(banco, item, esperadas=5)
    depois = gravado(banco)
    r = interromper(banco, item)
    assert (r['canceladas'], r['ativo']) == (0, False) and gravado(banco) == depois


def test_versao_antiga_recusada(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    v = versao(banco, item)
    sql(banco, "update public.item_despesa set descricao = 'outra aba' where id = %s", (item,))
    antes = gravado(banco)
    assert erro(interromper, banco, item, versao_=v).diag.message_hint == 'VERSAO'
    assert gravado(banco) == antes


def test_falha_no_meio_desfaz_tudo(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    sql(banco, f"""create function public.t_falha() returns trigger language plpgsql as $$
                   begin if old.id = {lista[6]['id']} then raise exception 'falha simulada'; end if; return old; end $$;
                   create trigger t_falha before delete on public.conta for each row execute function public.t_falha()""")
    antes = gravado(banco)
    assert 'falha simulada' in str(erro(interromper, banco, item, esperadas=5))
    assert gravado(banco) == antes  # nem a recorrencia ficou inativa, nem parte das contas saiu


# ---------------------------------------------------------------------------
# 5-6. Despesas: apenas esta, esta e as futuras (inclusive em recorrencia ja inativa)
# ---------------------------------------------------------------------------

def test_recorrencia_ja_inativa_tem_as_futuras_interrompidas(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    sql(banco, 'update public.item_despesa set ativo = false where id = %s', (item,))  # inativada antes da P22
    p = previa_int(banco, item)
    assert p['ativo'] is False and p['pode_interromper'] is True and p['quantidade'] == 5
    r = interromper(banco, item, esperadas=5)
    assert r['canceladas'] == 5 and len(contas(banco, item)) == 3


def test_esta_e_as_futuras_inclui_a_escolhida_mesmo_vencida(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    sql(banco, 'update public.item_despesa set ativo = false where id = %s', (item,))
    vencida = lista[1]
    p = previa_int(banco, item, efeito=str(vencida['mes_referencia']), conta=vencida['id'])
    esperado = [vencida['id']] + eleg(lista, h, mes(h))
    assert [a['registro_id'] for a in p['afetadas']] == esperado
    interromper(banco, item, efeito=str(vencida['mes_referencia']), esperadas=len(esperado), conta=vencida['id'])
    assert [c['id'] for c in contas(banco, item)] == [lista[0]['id']] + [c['id'] for c in lista[2:] if c['id'] not in esperado]


def test_conta_de_outra_recorrencia_recusada(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    outra = nova_recorrencia(banco, 'Outra', 'mensal', str(mes(h, 1).replace(day=10)))
    antes = gravado(banco)
    assert erro(interromper, banco, outra, conta=lista[3]['id']).pgcode == '22023'
    assert gravado(banco) == antes


def test_excluir_apenas_esta_continua_so_nesta(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    alvo = lista[4]
    v = rpc(banco, 'despesa_para_edicao', PESSOAL, alvo['id'])['versao']
    rpc(banco, 'excluir_despesa', PESSOAL, alvo['id'], v)
    assert [c['id'] for c in contas(banco, item)] == [c['id'] for c in lista if c['id'] != alvo['id']]
    assert competencias(banco, item)[alvo['mes_referencia']] == ('DISPENSADA', 'Conta excluida pelo usuario')
    assert sql(banco, 'select ativo from public.item_despesa where id = %s', (item,))[0]['ativo'] is True


# ---------------------------------------------------------------------------
# 8. Geracao por competencia depois da interrupcao
# ---------------------------------------------------------------------------

def test_geracao_nao_recria_as_canceladas_nem_gera_depois(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    interromper(banco, item, esperadas=5)
    depois = [c['id'] for c in contas(banco, item)]
    for k in (2, 5, 8):
        gerar_confirmado(banco, mes=str(mes(h, k)))
    assert [c['id'] for c in contas(banco, item)] == depois
    linha = next(i for i in previa(banco, mes=str(mes(h, 8)))['itens'] if i['item_id'] == item) \
        if any(i['item_id'] == item for i in previa(banco, mes=str(mes(h, 8)))['itens']) else None
    assert linha is None or linha['situacao'] in ('INATIVA', 'DISPENSADA')


# ---------------------------------------------------------------------------
# 9. Pix, debito automatico, semanal e cartao
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('meio', ['pix', 'boleto', 'debito_automatico'])
def test_meios_de_pagamento_conta(banco, meio):  # noqa: F811
    item, lista, h = telefonia(banco, meio)
    assert interromper(banco, item, esperadas=5)['canceladas'] == 5
    assert len(contas(banco, item)) == 3


def test_semanal_dispensa_cada_ocorrencia(banco):  # noqa: F811
    h = hoje(banco)
    inicio = mes(h, 2)
    item = nova_recorrencia(banco, 'Feira', 'semanal_1_2', str(inicio + relativedelta(days=(1 - inicio.weekday()) % 7)))
    gerar_confirmado(banco, mes=str(mes(h, 2)))
    lista = contas(banco, item)
    assert len(lista) >= 8
    corte = mes(h, 3)
    r = interromper(banco, item, efeito=str(corte))
    canceladas = [c for c in lista if c['mes_referencia'] >= corte]
    assert r['canceladas'] == len(canceladas) > 0
    ocorr = sql(banco, "select data_ocorrencia, situacao, motivo from financeiro.recorrencia_ocorrencia where item_despesa_id = %s "
                       "and data_ocorrencia >= %s", (item, corte))
    assert {o['data_ocorrencia'] for o in ocorr} == {c['data_vencimento'] for c in canceladas}
    assert all(o['situacao'] == 'DISPENSADA' and o['motivo'].startswith('Interrompida') for o in ocorr)
    gerar_confirmado(banco, mes=str(mes(h, 3)))
    assert [c['id'] for c in contas(banco, item)] == [c['id'] for c in lista if c['mes_referencia'] < corte]


def criar_cartao(dsn, **campos):
    dados = {'nome': 'Streaming no cartao', 'valor': '45.90', 'categoria_id': ASSINATURAS, 'data_vencimento': '2029-05-20',
             'tipo_recorrencia': 'mensal', 'cartao_id': CARTAO, 'descricao': 'Plano familia', **campos}
    item = rpc(dsn, 'criar_recorrencia_cartao', PESSOAL, dados, str(uuid.uuid4()))['item_id']
    for m in ('2029-05-01', '2029-07-01'):
        gerar_confirmado(dsn, mes=m)
    return item


def compras(dsn, item):
    return sql(dsn, 'select id, mes_fatura, valor, is_importado from public.lancamento_agregado where item_despesa_id = %s '
                    'order by mes_fatura', (item,))


def test_cartao_previsoes_futuras_saem_e_fatura_recalcula(banco):  # noqa: F811
    item = criar_cartao(banco)
    lista = compras(banco, item)
    assert [c['mes_fatura'] for c in lista] == [date(2029, m, 1) for m in (5, 6, 7, 8)]
    sql(banco, "update public.conta set status_pagamento = 'Pago', data_pagamento = '2029-05-31' "
               "where is_fatura_cartao and item_despesa_id = %s and cartao_competencia = '2029-05-01'", (CARTAO,))
    sql(banco, 'update public.lancamento_agregado set is_importado = true where id = %s', (lista[1]['id'],))  # cobranca real
    p = previa_int(banco, item, efeito='2029-05-01')
    assert [a['registro_id'] for a in p['afetadas']] == [lista[2]['id'], lista[3]['id']]
    assert {x['registro_id']: x['motivo'] for x in p['preservadas']} == {
        lista[0]['id']: 'Fatura paga: preservada', lista[1]['id']: 'Cobranca importada: preservada'}
    r = rpc(banco, 'interromper_recorrencia', PESSOAL, item, versao(banco, item), '2029-05-01', 2, None)
    assert (r['canceladas'], r['preservadas']) == (2, 2)
    assert [c['id'] for c in compras(banco, item)] == [lista[0]['id'], lista[1]['id']]
    for m in ('2029-07-01', '2029-08-01'):
        f = fatura(banco, CARTAO, m)
        plan = sql(banco, 'select financeiro.planejado_fatura(%s, %s, %s) - financeiro.creditos_fatura(%s) as v',
                   (PESSOAL, CARTAO, m, f['id']))[0]['v']
        assert f['valor'] == plan  # recalculada sem a previsao
        assert competencias(banco, item)[date.fromisoformat(m)][0] == 'DISPENSADA'
    gerar_confirmado(banco, mes='2029-08-01')
    assert len(compras(banco, item)) == 2  # nao volta


def test_cartao_pela_situacao_antiga_e_retomada(banco):  # noqa: F811
    item = criar_cartao(banco)
    rpc(banco, 'definir_situacao_recorrencia_cartao', PESSOAL, item, versao(banco, item), False)
    assert compras(banco, item) == []  # 2029 e depois do efeito padrao (competencia seguinte): todas eram previsoes
    rpc(banco, 'definir_situacao_recorrencia_cartao', PESSOAL, item, versao(banco, item), True)
    assert sql(banco, 'select ativo from public.item_despesa where id = %s', (item,))[0]['ativo'] is True
    gerar_confirmado(banco, mes='2029-07-01')
    assert compras(banco, item) == []  # as canceladas nao voltam sem pedido


def test_funcoes_antigas_continuam_recusando_cartao(banco):  # noqa: F811
    item = criar_cartao(banco)
    for funcao in ('inativar_recorrencia', 'reativar_recorrencia'):
        e = erro(rpc, banco, funcao, PESSOAL, item, versao(banco, item))
        assert e.diag.message_hint == 'BLOQUEIO'


# ---------------------------------------------------------------------------
# 10-12. Totais de Despesas, Faturas e Dashboard
# ---------------------------------------------------------------------------

def test_totais_de_despesas_e_dashboard_sem_as_canceladas(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    alvo = mes(h, 2)

    def totais():
        linhas = chamar(banco, USUARIO_A, "select coalesce(json_agg(x), '[]'::json) from financeiro.contas_do_mes(%s, %s) x",
                        (PESSOAL, str(alvo)))
        painel = rpc(banco, 'dashboard_resumo_tela', PESSOAL, alvo.strftime('%Y-%m'))
        return (sum(Decimal(str(x['valor'])) for x in linhas), any(x['nome'] == 'Telefonia' for x in linhas),
                Decimal(str(painel['fluxo_caixa']['resumo']['despesas_previstas'])),
                painel['kpis']['recorrencias_ativas']['quantidade'])
    total, aparece, previstas, ativas = totais()
    assert aparece is True
    interromper(banco, item, esperadas=5)
    total2, aparece2, previstas2, ativas2 = totais()
    assert aparece2 is False and total - total2 == Decimal('70.00') and previstas - previstas2 == Decimal('70.00')
    assert ativas - ativas2 == 1


# ---------------------------------------------------------------------------
# 13. Isolamento por perfil e escritor unico; outro modulo
# ---------------------------------------------------------------------------

def test_isolamento_por_perfil_e_usuario(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    antes = gravado(banco)
    assert erro(previa_int, banco, item, usuario=USUARIO_B).pgcode == '42501'
    assert erro(interromper, banco, item, usuario=USUARIO_B).pgcode == '42501'
    assert erro(interromper, banco, item, usuario=USUARIO_B, perfil=ID['PERFIL_B']).pgcode == '42501'
    assert erro(interromper, banco, item, usuario=None).pgcode == '42501'
    assert erro(previa_ret, banco, item, usuario=USUARIO_B).pgcode == '42501'
    assert erro(retomar, banco, item, usuario=USUARIO_B).pgcode == '42501'
    assert gravado(banco) == antes


def test_perfil_no_flask_recusado(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    atribuir(banco, 'PESSOAL', 'FLASK')
    antes = gravado(banco)
    assert erro(interromper, banco, item).diag.message_hint == 'SISTEMA_FLASK'
    assert erro(retomar, banco, item).diag.message_hint == 'SISTEMA_FLASK'
    assert previa_int(banco, item)['pode_interromper'] is False
    assert gravado(banco) == antes


def test_recorrencia_de_outro_modulo_bloqueada(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    sql(banco, "update public.item_despesa set origem_tipo = 'veiculo' where id = %s", (item,))
    p = previa_int(banco, item)
    assert p['pode_interromper'] is False and 'outro modulo' in p['motivo']
    antes = gravado(banco)
    assert erro(interromper, banco, item).diag.message_hint == 'BLOQUEIO'
    assert gravado(banco) == antes


# ---------------------------------------------------------------------------
# 14-15. Concorrencia
# ---------------------------------------------------------------------------

def test_interrupcao_e_pagamento_simultaneos(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    alvo = lista[4]
    v = versao(banco, item)
    resultados = _paralelo([lambda: pagar(banco, alvo, h), lambda: interromper(banco, item, versao_=v)])
    assert not any(r[0] == 'erro' and getattr(r[1], 'pgcode', None) == '40P01' for r in resultados)  # sem deadlock
    restante = sql(banco, 'select status_pagamento from public.conta where id = %s', (alvo['id'],))
    movimentos = sql(banco, 'select count(*) as n from public.movimento_financeiro where conta_id = %s', (alvo['id'],))[0]['n']
    if restante:  # o pagamento venceu: a conta paga fica, com o movimento
        assert restante[0]['status_pagamento'] == 'Pago' and movimentos == 1
    else:  # a interrupcao venceu: o pagamento nao achou a conta e nada foi debitado
        assert resultados[0][0] == 'erro' and movimentos == 0


def test_interrupcao_e_exclusao_simultaneas_sem_deadlock(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    alvo = lista[5]
    va = rpc(banco, 'despesa_para_edicao', PESSOAL, alvo['id'])['versao']
    v = versao(banco, item)
    resultados = _paralelo([lambda: rpc(banco, 'excluir_despesa', PESSOAL, alvo['id'], va),
                            lambda: interromper(banco, item, versao_=v)])
    assert not any(r[0] == 'erro' and getattr(r[1], 'pgcode', None) == '40P01' for r in resultados)
    assert resultados[1][0] == 'ok'
    assert {c['id'] for c in contas(banco, item)} == {c['id'] for c in lista[:3]}


def test_duas_interrupcoes_simultaneas_uma_vale(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    v = versao(banco, item)
    resultados = _paralelo([lambda: interromper(banco, item, versao_=v), lambda: interromper(banco, item, versao_=v)])
    assert sorted(r[0] for r in resultados) == ['erro', 'ok']
    assert next(r[1] for r in resultados if r[0] == 'erro').diag.message_hint == 'VERSAO'
    assert len(contas(banco, item)) == 3


def test_interrupcao_e_geracao_simultaneas(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    v = versao(banco, item)
    resultados = _paralelo([lambda: interromper(banco, item, versao_=v), lambda: gerar_confirmado(banco, mes=str(mes(h, 7)))])
    assert resultados[0][0] == 'ok'
    assert not any(r[0] == 'erro' and getattr(r[1], 'pgcode', None) == '40P01' for r in resultados)
    # Gerada antes (a interrupcao viu e cancelou) ou depois (inativa: nada gerado): nenhuma pendente depois do efeito.
    assert [c for c in contas(banco, item) if c['mes_referencia'] >= mes(h, 1)] == []


# ---------------------------------------------------------------------------
# 7. Retomada sem duplicidade, sem periodo inativo e sem restaurar em silencio
# ---------------------------------------------------------------------------

def test_retomada_nao_gera_o_periodo_inativo(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    interromper(banco, item, esperadas=5)
    retomada = mes(h, 9)  # volta depois das canceladas (6 a 8 meses adiante nunca foram geradas)
    p = previa_ret(banco, item, str(retomada))
    assert [x['competencia'] for x in p['lacunas']] == [str(mes(h, k)) for k in (6, 7, 8)]
    assert p['quantidade_restauraveis'] == 0
    r = retomar(banco, item, str(retomada))
    assert (r['ativo'], r['lacunas_dispensadas'], r['restauradas']) == (True, 3, 0)
    gerar_confirmado(banco, mes=str(retomada))
    novas = [c['mes_referencia'] for c in contas(banco, item) if c['mes_referencia'] > mes(h)]
    assert novas == [mes(h, 9), mes(h, 10)]  # so a partir da retomada (sem as atrasadas do periodo inativo)


def test_sem_a_correcao_a_reativacao_geraria_contas_atrasadas(banco):  # noqa: F811
    """Prova do defeito com o corpo antigo (ativo = true e nada mais): o gerador cria as competencias do periodo inativo."""
    item, lista, h = telefonia(banco)
    interromper(banco, item, esperadas=5)
    sql(banco, 'update public.item_despesa set ativo = true where id = %s', (item,))  # o que reativar_recorrencia fazia
    gerar_confirmado(banco, mes=str(mes(h, 9)))
    assert [mes(h, k) for k in (6, 7, 8)] == [c['mes_referencia'] for c in contas(banco, item) if mes(h, 6) <= c['mes_referencia'] <= mes(h, 8)]


def test_retomada_nao_restaura_canceladas_sem_pedido(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    v = rpc(banco, 'despesa_para_edicao', PESSOAL, lista[3]['id'])['versao']
    rpc(banco, 'excluir_despesa', PESSOAL, lista[3]['id'], v)  # excluida pelo usuario: fica sempre
    interromper(banco, item, esperadas=4)
    p = previa_ret(banco, item, str(mes(h, 1)))
    assert p['quantidade_restauraveis'] == 4 and p['dispensadas_mantidas'] == 1 and p['quantidade_lacunas'] == 0
    retomar(banco, item, str(mes(h, 1)))
    gerar_confirmado(banco, mes=str(mes(h, 4)))
    assert [c['id'] for c in contas(banco, item)] == [c['id'] for c in lista[:3]]


def test_retomada_com_restauracao_regera_sem_duplicar(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    v = rpc(banco, 'despesa_para_edicao', PESSOAL, lista[3]['id'])['versao']
    rpc(banco, 'excluir_despesa', PESSOAL, lista[3]['id'], v)
    interromper(banco, item, esperadas=4)
    r = retomar(banco, item, str(mes(h, 1)), restaurar=True)
    assert r['restauradas'] == 4
    for _ in range(2):
        gerar_confirmado(banco, mes=str(mes(h, 4)))
    meses = [c['mes_referencia'] for c in contas(banco, item)]
    assert meses == sorted(set(meses))  # nenhuma duplicada
    assert mes(h, 1) not in meses  # a excluida pelo usuario nao volta
    assert meses[3:] == [mes(h, k) for k in (2, 3, 4, 5)]
    assert sql(banco, "select count(*) as n from public.conta where item_despesa_id = %s and status_pagamento = 'Pago'",
               (item,))[0]['n'] == 1  # a paga nao foi recriada


def test_reativar_padrao_e_retomar_ativa_nao_mudam_o_que_nao_deve(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    antes = gravado(banco)
    r = retomar(banco, item)  # ja ativa
    assert (r['ativo'], r['lacunas_dispensadas'], r['restauradas']) == (True, 0, 0) and gravado(banco) == antes
    interromper(banco, item, esperadas=5)
    r = rpc(banco, 'reativar_recorrencia', PESSOAL, item, versao(banco, item))
    assert r['ativo'] is True and r['retomada'] == str(mes(h)) and r['restauradas'] == 0


def test_funcoes_antigas_passam_pelo_mesmo_caminho(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    r = rpc(banco, 'inativar_recorrencia', PESSOAL, item, versao(banco, item))
    assert r['canceladas'] == 5 and r['efeito'] == str(mes(h, 1)) and len(contas(banco, item)) == 3


# ---------------------------------------------------------------------------
# Reversao e reaplicacao
# ---------------------------------------------------------------------------

def test_reversao_e_reaplicacao_preservam_os_dados(banco):  # noqa: F811
    item, lista, h = telefonia(banco)
    interromper(banco, item, esperadas=5)
    antes = gravado(banco)
    conn = psycopg2.connect(banco)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(REVERSAO.read_text(encoding='utf-8'))
            cur.execute("select count(*) from pg_proc where proname in ('interromper_recorrencia', 'retomar_recorrencia', "
                        "'dispensar_conta_recorrente', 'lacunas_da_recorrencia')")
            assert cur.fetchone()[0] == 0
            cur.execute("select prosrc from pg_proc where proname = 'inativar_recorrencia'")
            assert 'interromper' not in cur.fetchone()[0]
        assert gravado(banco) == antes
        with conn, conn.cursor() as cur:
            cur.execute(MIGRATION.read_text(encoding='utf-8'))
            cur.execute("select count(*) from pg_proc where proname in ('interromper_recorrencia', 'retomar_recorrencia')")
            assert cur.fetchone()[0] == 2
        assert gravado(banco) == antes
    finally:
        conn.close()
    gerar_confirmado(banco, mes=str(mes(h, 5)))
    assert len(contas(banco, item)) == 3
