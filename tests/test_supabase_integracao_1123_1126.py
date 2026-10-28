"""
Testes FIN-INTEGRACAO-1123-1126-1 — homologacao integrada dos MVPs 1123 (motor de Financiamentos), 1124 (escritor
unico), 1125 (Categorias e Recorrencias) e 1126 (Patrimonio), em cluster PostgreSQL local descartavel, so com dados
ficticios (o Flask, quando entra, roda em subprocesso contra a copia do cluster).

I1 ciclo financeiro integrado no mesmo perfil; I2 estorno x amortizacao (regra atual do motor); I3 guarda de escritor
percorrendo o esquema e as rotas do Flask; I4 alternancia de escritor; I5 isolamento entre tres perfis; I6
concorrencia entre modulos; I7 reversoes em ordem inversa e reaplicacao; I8 as tres escritas do Flask que ficavam sem
guarda (xfail estrito na homologacao; corrigidas em FIN-ESCRITOR-UNICO-GUARDAS-1, agora regressao).

Integridade: resumos (md5) das tabelas antes e depois de cada cenario relevante; operacao recusada nao muda nada.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.supabase_local import ClusterLocal, claims_usuario
from tests.test_supabase_cartoes import rpc
from tests.test_supabase_receitas_categorias_tela import flask
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    ROOT,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    gerar,
    gerar_confirmado,
    previa,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL, EMPRESA, PERFIL_B = ID['PESSOAL'], ID['EMPRESA'], ID['PERFIL_B']
CATEGORIA = 951  # 'Moradia R' (cenario ficticio de semear_recorrencias)
MIGRATIONS = ROOT / 'supabase' / 'migrations'
REVERSAO = ROOT / 'supabase' / 'reversao'
VERSOES = ('20261123090000', '20261124090000', '20261125090000', '20261126090000')

FIN = {  # SAC sem indexador (nao depende de TR), 24 parcelas a partir de 05/03/2027
    'nome': 'SAC integracao (ficticio)', 'produto': 'SFH', 'sistema_amortizacao': 'SAC', 'indexador_saldo': None,
    'valor_financiado': 24000, 'prazo_total_meses': 24, 'taxa_juros_nominal_anual': 9.0, 'data_contrato': '2027-02-05',
    'data_primeira_parcela': '2027-03-05', 'seguro_modo': 'fixo', 'taxa_administracao_fixa': 25,
    'vigencias_seguro': [{'competencia_inicio': '2027-03', 'valor_mensal': 20}],
}


# =====================================================================================================================
# Apoio
# =====================================================================================================================

@pytest.fixture
def banco(cluster):  # noqa: F811
    """Pessoal e Perfil B no novo aplicativo; Empresa no Flask. Recorrencias semeadas inativas (so as do teste geram)."""
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    sql(dsn, "update public.item_despesa set ativo = false where tipo is distinct from 'Agregador'")
    return dsn


def chave():
    return str(uuid.uuid4())


def erro(funcao, *args, **kw):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args, **kw)
    return e.value


def tabelas_financeiras(dsn):
    return [r['t'] for r in sql(dsn, "select table_schema || '.' || table_name t from information_schema.tables "
                                     "where table_schema in ('public', 'financeiro') and table_type = 'BASE TABLE' "
                                     "and table_name <> 'usuario' order by 1")]


def resumo_tabelas(dsn):
    """{tabela: md5 do conteudo} (public e financeiro, fora a conta de login do roteiro do Flask)."""
    saida = {}
    for t in tabelas_financeiras(dsn):
        saida[t] = sql(dsn, f"select md5(coalesce(string_agg(x::text, '|' order by x::text), '')) d from {t} x")[0]['d']
    return saida


def tabelas_alteradas(antes, depois):
    return sorted(t for t in set(antes) | set(depois) if antes.get(t) != depois.get(t))


# Tabelas ligadas a um perfil sem coluna propria de perfil: o perfil vem do registro pai.
INDIRETAS = {
    'financeiro.recorrencia_ocorrencia': 'select x.* from financeiro.recorrencia_ocorrencia x join public.item_despesa i '
                                         'on i.id = x.item_despesa_id where i.perfil_financeiro_id = %s',
    'financeiro.recorrencia_competencia': 'select x.* from financeiro.recorrencia_competencia x join public.item_despesa i '
                                          'on i.id = x.item_despesa_id where i.perfil_financeiro_id = %s',
}


def resumo_perfil(dsn, perfil):
    """md5 de tudo o que pertence ao perfil (tabelas com perfil_financeiro_id e as INDIRETAS)."""
    tabelas = [r['t'] for r in sql(dsn, """select c.table_schema || '.' || c.table_name t from information_schema.columns c
                                            join information_schema.tables t on t.table_schema = c.table_schema
                                             and t.table_name = c.table_name and t.table_type = 'BASE TABLE'
                                           where c.column_name = 'perfil_financeiro_id'
                                             and c.table_schema in ('public', 'financeiro') order by 1""")]
    h = hashlib.sha256()
    for t in tabelas:
        d = sql(dsn, f"select md5(coalesce(string_agg(x::text, '|' order by x::text), '')) d from {t} x "
                     f"where x.perfil_financeiro_id = %s", (perfil,))[0]['d']
        h.update(f'{t}:{d}'.encode())
    for t, consulta in INDIRETAS.items():
        d = sql(dsn, f"select md5(coalesce(string_agg(y::text, '|' order by y::text), '')) d from ({consulta}) y", (perfil,))[0]['d']
        h.update(f'{t}:{d}'.encode())
    return h.hexdigest()


def linhas_md5(dsn, tabela, ids):
    if not ids:
        return {}
    return {r['id']: r['h'] for r in sql(dsn, f'select id, md5(x::text) h from {tabela} x where id = any(%s)', (list(ids),))}


def conta_bancaria(dsn, perfil):
    return sql(dsn, "select id from public.conta_bancaria where perfil_financeiro_id = %s and nome <> 'Carteira legado sem perfil' "
                    "order by id limit 1", (perfil,))[0]['id']


def conferir_saldo_bancario(dsn, conta):
    """saldo_atual (cache) = saldo_inicial + creditos - debitos, calculado aqui e pela funcao do banco."""
    r = sql(dsn, """select cb.saldo_atual, cb.saldo_inicial, financeiro.saldo_da_conta(cb.id) as funcao,
                           coalesce((select sum(case m.tipo when 'CREDITO' then m.valor else -m.valor end)
                                       from public.movimento_financeiro m where m.conta_bancaria_id = cb.id), 0) as liquido,
                           (select count(*) from public.movimento_financeiro m where m.conta_bancaria_id = cb.id) as movimentos
                      from public.conta_bancaria cb where cb.id = %s""", (conta,))[0]
    calculado = (r['saldo_inicial'] or 0) + r['liquido']
    # Conta semeada sem movimento ainda nao tem o cache (saldo_atual nulo); com movimento, ele tem de bater.
    atual = calculado if r['saldo_atual'] is None and r['movimentos'] == 0 else r['saldo_atual']
    assert atual == calculado == r['funcao'], r
    return calculado


def nova_recorrencia(dsn, nome, tipo, vencimento, valor='30.00', perfil=PESSOAL, usuario=USUARIO_A):
    dados = {'nome': nome, 'valor': valor, 'categoria_id': CATEGORIA, 'data_vencimento': vencimento,
             'recorrente': True, 'tipo_recorrencia': tipo}
    return rpc(dsn, 'criar_despesa', perfil, dados, chave(), usuario=usuario)['item_id']


def contas_do_item(dsn, item):
    return sql(dsn, 'select id, data_vencimento, valor, status_pagamento from public.conta where item_despesa_id = %s '
                    'order by data_vencimento, id', (item,))


def versao_recorrencia(dsn, item):
    return sql(dsn, 'select financeiro.versao_recorrencia(%s) as v', (item,))[0]['v']


def versao_despesa(dsn, conta):
    return sql(dsn, 'select financeiro.versao_despesa(%s) as v', (conta,))[0]['v']


def novo_financiamento(dsn, perfil=PESSOAL, usuario=USUARIO_A, **extra):
    return rpc(dsn, 'criar_financiamento', perfil, {**FIN, **extra}, chave(), usuario=usuario)['data']['id']


def parcela(dsn, fid, numero):
    """Parcela e a despesa que a cobra."""
    return sql(dsn, """select p.id as parcela_id, p.status as parcela_status, c.id as conta_id, c.valor, c.status_pagamento,
                              c.data_vencimento
                         from public.financiamento_parcela p join public.conta c on c.financiamento_parcela_id = p.id
                        where p.financiamento_id = %s and p.numero_parcela = %s""", (fid, numero))[0]


def pagar(dsn, conta, data, perfil=PESSOAL, usuario=USUARIO_A, banco_id=None):
    valor = str(sql(dsn, 'select valor from public.conta where id = %s', (conta,))[0]['valor'])
    return rpc(dsn, 'pagar_despesa', perfil, conta,
               {'conta_bancaria_id': banco_id or conta_bancaria(dsn, perfil), 'data_pagamento': data,
                'valor_pago': valor, 'valor_devido': valor}, chave(), usuario=usuario)


def amortizar(dsn, fid, data, valor, perfil=PESSOAL, usuario=USUARIO_A):
    return rpc(dsn, 'registrar_amortizacao_extra', perfil, fid, {'data': data, 'valor': valor, 'tipo': 'reduzir_parcela'},
               chave(), usuario=usuario)


def caixinha(dsn, nome, saldo, perfil=PESSOAL, usuario=USUARIO_A):
    return rpc(dsn, 'criar_caixinha', perfil, {'nome': nome, 'tipo': 'Reserva', 'saldo_inicial': saldo}, chave(),
               usuario=usuario)['conta_id']


def transferir(dsn, origem, destino, valor, data='2027-03-10', perfil=PESSOAL, usuario=USUARIO_A):
    return rpc(dsn, 'criar_transferencia_patrimonio', perfil,
               {'conta_origem_id': origem, 'conta_destino_id': destino, 'valor': valor, 'data_transferencia': data},
               chave(), usuario=usuario)['transferencia_id']


def saldos_patrimonio(dsn, ids):
    return {r['id']: r['saldo_atual'] for r in sql(dsn, 'select id, saldo_atual from public.conta_patrimonio where id = any(%s)',
                                                   (list(ids),))}


def conferir_patrimonio(dsn, ids):
    """Saldo de cada caixinha = saldo inicial + transferencias recebidas - enviadas; soma conservada."""
    linhas = sql(dsn, """select cp.id, cp.saldo_inicial, cp.saldo_atual,
                                coalesce((select sum(t.valor) from public.transferencia t where t.conta_destino_id = cp.id), 0)
                              - coalesce((select sum(t.valor) from public.transferencia t where t.conta_origem_id = cp.id), 0) as liquido
                           from public.conta_patrimonio cp where cp.id = any(%s)""", (list(ids),))
    for r in linhas:
        assert r['saldo_atual'] == r['saldo_inicial'] + r['liquido'] and r['saldo_atual'] >= 0, r
    assert sum(r['saldo_atual'] for r in linhas) == sum(r['saldo_inicial'] for r in linhas)


def sem_duplicidade(dsn):
    """Nenhuma conta duplicada por recorrencia e data, nem parcela/despesa duplicada por financiamento."""
    assert sql(dsn, """select item_despesa_id, data_vencimento, count(*) n from public.conta c
                         where item_despesa_id is not null and financiamento_parcela_id is null and not is_fatura_cartao
                           and exists (select 1 from public.item_despesa i where i.id = c.item_despesa_id and i.recorrente)
                         group by 1, 2 having count(*) > 1""") == []
    assert sql(dsn, 'select financiamento_id, numero_parcela from public.financiamento_parcela group by 1, 2 having count(*) > 1') == []
    assert sql(dsn, 'select financiamento_parcela_id from public.conta where financiamento_parcela_id is not null '
                    'group by 1 having count(*) > 1') == []


def em_paralelo(*funcoes, timeout=90):
    """Roda as funcoes ao mesmo tempo (barreira). Devolve [(resultado, excecao)] na ordem dada."""
    barreira = threading.Barrier(len(funcoes))
    saida = [None] * len(funcoes)

    def rodar(i, f):
        try:
            barreira.wait(timeout=20)
            saida[i] = (f(), None)
        except Exception as exc:  # noqa: BLE001
            saida[i] = (None, exc)

    tarefas = [threading.Thread(target=rodar, args=(i, f)) for i, f in enumerate(funcoes)]
    for t in tarefas:
        t.start()
    for t in tarefas:
        t.join(timeout=timeout)
    assert not any(t.is_alive() for t in tarefas), 'operacao simultanea nao terminou (possivel bloqueio)'
    for _, exc in saida:  # nenhum impasse detectado pelo PostgreSQL
        assert not (isinstance(exc, psycopg2.Error) and exc.pgcode == '40P01'), exc
    return saida


# =====================================================================================================================
# I1 — Ciclo financeiro integrado no mesmo perfil
# =====================================================================================================================

def test_i1_ciclo_financeiro_integrado(banco):
    outros_antes = {p: resumo_perfil(banco, p) for p in (EMPRESA, PERFIL_B)}
    conta = conta_bancaria(banco, PESSOAL)
    saldo_inicial = conferir_saldo_bancario(banco, conta)
    movimentos_iniciais = sql(banco, 'select count(*) n from public.movimento_financeiro')[0]['n']

    semanal = nova_recorrencia(banco, 'Diarista integ', 'semanal_1_3', '2027-03-03')
    quinzenal = nova_recorrencia(banco, 'Jardim integ', 'semanal_2_1', '2027-03-01', valor='50.00')
    fid = novo_financiamento(banco)
    cx = [caixinha(banco, 'Reserva integ', 1000), caixinha(banco, 'Viagem integ', 200)]
    transferir(banco, cx[0], cx[1], 300)
    gerar_confirmado(banco, mes='2027-03-01')
    assert len(contas_do_item(banco, semanal)) == 9 and len(contas_do_item(banco, quinzenal)) == 5  # marco e abril

    # Pagamentos pela conta bancaria: a 1a semanal e a parcela 1.
    paga_sem = contas_do_item(banco, semanal)[0]['id']
    p1 = parcela(banco, fid, 1)
    pagamentos = [pagar(banco, paga_sem, '2027-03-03'), pagar(banco, p1['conta_id'], '2027-03-05')]
    pagas = linhas_md5(banco, 'public.conta', [paga_sem, p1['conta_id']])
    movimentos = linhas_md5(banco, 'public.movimento_financeiro', [p['movimento_id'] for p in pagamentos])
    parcela_paga = linhas_md5(banco, 'public.financiamento_parcela', [p1['parcela_id']])
    total_pago = sum(sql(banco, 'select valor from public.movimento_financeiro where id = %s', (p['movimento_id'],))[0]['valor']
                     for p in pagamentos)
    geradas = {c['id']: c['valor'] for c in contas_do_item(banco, semanal)}

    # Alteracoes posteriores: valor da recorrencia, nova geracao, amortizacao, regeneracao, mais transferencias.
    rpc(banco, 'editar_recorrencia', PESSOAL, semanal, versao_recorrencia(banco, semanal), {'valor': '45.00'})
    gerar_confirmado(banco, mes='2027-05-01')
    gerar_confirmado(banco, mes='2027-05-01')  # repetida: nada novo
    antes_amortizacao = sql(banco, 'select numero_parcela, valor_previsto_total from public.financiamento_parcela '
                                   'where financiamento_id = %s and numero_parcela > 1 order by 1', (fid,))
    amortizar(banco, fid, '2027-03-20', 2000)  # recalcula as parcelas elegiveis (pendentes sem movimento)
    recalculadas = sql(banco, 'select numero_parcela, valor_previsto_total from public.financiamento_parcela '
                              'where financiamento_id = %s and numero_parcela > 1 order by 1', (fid,))
    assert recalculadas != antes_amortizacao
    # Regra atual (igual ao Flask): com parcela paga, a regeneracao estrutural e recusada por inteiro, sem gravar.
    antes = resumo_tabelas(banco)
    regen = erro(rpc, banco, 'regenerar_parcelas_financiamento', PESSOAL, fid)
    assert regen.diag.message_hint == 'COM_EXECUCAO' and resumo_tabelas(banco) == antes
    transferir(banco, cx[1], cx[0], 120.5, data='2027-04-02')

    # Contas pagas, movimentos e parcela executada intactos.
    assert linhas_md5(banco, 'public.conta', pagas) == pagas
    assert linhas_md5(banco, 'public.movimento_financeiro', movimentos) == movimentos
    assert linhas_md5(banco, 'public.financiamento_parcela', parcela_paga) == parcela_paga
    # Ja geradas mantem o valor; as novas tem o valor novo.
    depois = contas_do_item(banco, semanal)
    assert {c['id']: c['valor'] for c in depois if c['id'] in geradas} == geradas
    assert {c['valor'] for c in depois if c['id'] not in geradas} == {Decimal('45.00')}
    assert len(depois) == len({c['data_vencimento'] for c in depois})
    sem_duplicidade(banco)
    # Amortizacao recalculou so as pendentes; parcelas e despesas continuam 1 para 1.
    n_parcelas = sql(banco, 'select count(*) n from public.financiamento_parcela where financiamento_id = %s', (fid,))[0]['n']
    n_despesas = sql(banco, 'select count(*) n from public.conta c join public.financiamento_parcela p on p.id = c.financiamento_parcela_id '
                            'where p.financiamento_id = %s', (fid,))[0]['n']
    assert n_parcelas == n_despesas > 0, (n_parcelas, n_despesas, regen)
    # Saldo bancario = movimentos; so os 2 pagamentos movimentaram a conta (transferencias de Patrimonio nao).
    assert conferir_saldo_bancario(banco, conta) == saldo_inicial - total_pago
    assert sql(banco, 'select count(*) n from public.movimento_financeiro')[0]['n'] == movimentos_iniciais + 2
    conferir_patrimonio(banco, cx)
    assert saldos_patrimonio(banco, cx) == {cx[0]: Decimal('820.50'), cx[1]: Decimal('379.50')}
    # Nada dos outros perfis mudou.
    assert {p: resumo_perfil(banco, p) for p in (EMPRESA, PERFIL_B)} == outros_antes


# =====================================================================================================================
# I2 — Estorno x amortizacao (regra atual do motor, Regras 1 e 4 de docs/FIN_FINANCIAMENTOS_MOTOR_1.md)
# =====================================================================================================================

def test_i2_estorno_e_amortizacao_seguem_a_regra_atual(banco):
    fid = novo_financiamento(banco)
    conta = conta_bancaria(banco, PESSOAL)
    p2 = parcela(banco, fid, 2)  # vencimento 05/04/2027
    pg = pagar(banco, p2['conta_id'], '2027-04-05')
    protegida = linhas_md5(banco, 'public.financiamento_parcela', [p2['parcela_id']])

    # Regra atual: amortizacao com parcela protegida (paga ou com movimento) DEPOIS da data e recusada, sem gravar nada.
    antes = resumo_tabelas(banco)
    e = erro(amortizar, banco, fid, '2027-03-20', 500)
    assert e.diag.message_hint == 'PARCELA_PROTEGIDA', (e.pgcode, str(e))
    assert resumo_tabelas(banco) == antes

    # Depois da ultima parcela protegida: permitida; a parcela paga nao muda.
    assert amortizar(banco, fid, '2027-04-20', 500)['success']
    assert linhas_md5(banco, 'public.financiamento_parcela', protegida) == protegida
    assert sql(banco, 'select count(*) n from public.financiamento_amortizacao_extra where financiamento_id = %s', (fid,))[0]['n'] == 1

    # Estorno: a parcela volta a pendente, mas o movimento (estornado) continua a protege-la.
    original = linhas_md5(banco, 'public.movimento_financeiro', [pg['movimento_id']])
    rpc(banco, 'estornar_pagamento_despesa', PESSOAL, p2['conta_id'], pg['movimento_id'],
        {'motivo': 'teste integrado', 'data_estorno': '2027-04-25'}, chave())
    assert parcela(banco, fid, 2)['status_pagamento'] != 'Pago'
    antes = resumo_tabelas(banco)
    e = erro(amortizar, banco, fid, '2027-03-25', 500)
    assert e.diag.message_hint == 'PARCELA_PROTEGIDA', (e.pgcode, str(e))
    e = erro(rpc, banco, 'regenerar_parcelas_financiamento', PESSOAL, fid)  # regeneracao tambem nao alcanca a parcela
    assert e.diag.message_hint == 'COM_EXECUCAO' and resumo_tabelas(banco) == antes, e
    # Historico: movimento original intacto, estorno registrado como movimento proprio, saldo coerente.
    assert linhas_md5(banco, 'public.movimento_financeiro', original) == original
    estornos = sql(banco, 'select tipo, valor from public.movimento_financeiro where movimento_original_id = %s', (pg['movimento_id'],))
    assert len(estornos) == 1 and estornos[0]['tipo'] == 'CREDITO'
    conferir_saldo_bancario(banco, conta)
    assert sql(banco, 'select count(*) n from public.financiamento_amortizacao_extra where financiamento_id = %s', (fid,))[0]['n'] == 1


# =====================================================================================================================
# I3 — Guarda de escritor, percorrendo o esquema (novo aplicativo) e as rotas (Flask)
# =====================================================================================================================

VALOR = {'integer': '0', 'bigint': '0', 'smallint': '0', 'numeric': '0', 'jsonb': "'{}'::jsonb", 'json': "'{}'::json",
         'uuid': "'00000000-0000-4000-8000-000000000001'::uuid", 'text': "''", 'character varying': "''",
         'date': "'2030-01-01'::date", 'boolean': 'false', 'integer[]': "'{}'::integer[]", 'text[]': "'{}'::text[]",
         'jsonb[]': "'{}'::jsonb[]"}
# Excecoes documentadas: gestao de perfil, fora da guarda nos dois aplicativos (docs/FIN_ESCRITOR_UNICO_FINAL_1.md §3).
SEM_GUARDA_DOCUMENTADA = {'criar_perfil', 'definir_perfil_padrao'}


def funcoes_de_escrita(dsn):
    """Funcoes financeiro.* volateis executaveis pelo usuario autenticado."""
    return sql(dsn, """select p.proname as nome, pg_get_function_identity_arguments(p.oid) as args
                         from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                        where n.nspname = 'financeiro' and p.provolatile = 'v' and p.prokind = 'f'
                          and has_function_privilege('authenticated', p.oid, 'EXECUTE')
                        order by 1, 2""")


def chamada(nome, args, perfil, jsonb=None):
    valores = []
    for i, arg in enumerate(a.strip() for a in args.split(',') if a.strip()):
        partes = arg.split(' ', 1)
        tipo = partes[1] if len(partes) == 2 and partes[0].startswith('p_') else arg
        tipo = re.sub(r'\s+default\s+.*$', '', tipo, flags=re.I).strip()
        if i == 0 and tipo == 'integer':
            valores.append(str(perfil))
        elif tipo == 'jsonb' and jsonb is not None:
            valores.append("'" + json.dumps(jsonb).replace("'", "''") + "'::jsonb")
        else:
            valores.append(VALOR[tipo])
    return f"select financeiro.{nome}({', '.join(valores)})"


# Recusas que vem da atribuicao de escritor do perfil (financeiro.gerador_recorrencia) ou do catalogo global.
RECUSAS_DO_ESCRITOR = {'SISTEMA_FLASK', 'GERADOR_FLASK', 'CATALOGO_FLASK'}


def test_i3_toda_escrita_do_novo_aplicativo_recusa_perfil_do_flask_sem_gravar(banco):
    sql(banco, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true where perfil_financeiro_id = %s",
        (EMPRESA,))  # A gere a Empresa, que esta no Flask: a recusa tem de vir do escritor, nao da permissao
    contas = [r['id'] for r in sql(banco, 'select id from public.conta_bancaria where perfil_financeiro_id = %s or '
                                          'perfil_financeiro_id is null order by id', (EMPRESA,))]
    # Dados plausiveis, para que a validacao de entrada (feita antes da guarda em algumas funcoes) nao esconda a guarda.
    plausiveis = {'nome': 'Guarda (ficticio)', 'instituicao': 'Banco ficticio', 'tipo': 'Conta Corrente', 'valor': '10.00',
                  'valor_pago': '10.00', 'valor_devido': '10.00', 'valor_recebido': '10.00', 'data': '2027-03-05',
                  'data_pagamento': '2027-03-05', 'data_recebimento': '2027-03-05', 'data_estorno': '2027-03-06',
                  'motivo': 'teste de guarda', 'conta_bancaria_id': contas[0], 'conta_origem_id': contas[0],
                  'conta_destino_id': contas[-1], 'fonte_id': 0, 'descricao': 'Guarda (ficticio)'}
    antes = resumo_tabelas(banco)
    resultado = {}
    for f in funcoes_de_escrita(banco):
        if f['nome'] in SEM_GUARDA_DOCUMENTADA:
            resultado[f['nome']] = 'EXCECAO_DOCUMENTADA'
            continue
        for dados in (None, plausiveis):  # vazio; se a validacao recusar antes da guarda, de novo com dados plausiveis
            try:
                chamar(banco, USUARIO_A, chamada(f['nome'], f['args'], EMPRESA, dados))
                resultado[f['nome']] = 'SEM_RECUSA'
            except psycopg2.Error as e:
                resultado[f['nome']] = e.diag.message_hint or f'{e.pgcode}: {e.diag.message_primary}'
            if resultado[f['nome']] in RECUSAS_DO_ESCRITOR:
                break
    assert resumo_tabelas(banco) == antes  # nenhuma gravacao, nem parcial
    assert set(resultado) >= SEM_GUARDA_DOCUMENTADA
    inesperadas = {n: r for n, r in resultado.items() if r not in RECUSAS_DO_ESCRITOR | {'EXCECAO_DOCUMENTADA'}}
    assert inesperadas == {}, inesperadas
    assert len(resultado) >= 80


_SCRIPT_ROTAS = """
import json, re, sys, uuid
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    email = f'flask.integ.{uuid.uuid4().hex[:8]}@teste.local'
    u = Usuario(email=email, nome='Integ', ativo=True)
    u.definir_senha('Senha-ficticia-integ-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': email, 'senha': 'Senha-ficticia-integ-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
ids = json.loads(sys.argv[2])  # {blueprint: {parametro: id real do perfil}}; demais inteiros: 999999 (perfil ativo)
guardados = sorted(bp for bp, fs in app.before_request_funcs.items() if bp and any(f.__name__ == '_escritor_unico' for f in fs))
guardados = sorted(set(guardados) | set(json.loads(sys.argv[3])))  # guarda propria: financiamentos, consorcios, contas
saida = []
for regra in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    bp = regra.endpoint.rsplit('.', 1)[0] if '.' in regra.endpoint else None
    if bp not in guardados:
        continue
    url = re.sub(r'<(?:int:|float:)?([a-zA-Z_]+)>', lambda m: str(ids.get(bp, {}).get(m.group(1), 999999)), regra.rule)
    url = re.sub(r'<(?:string:|path:)?([a-zA-Z_]+)>', 'x', url)
    for metodo in sorted(regra.methods & {'POST', 'PUT', 'PATCH', 'DELETE'}):
        r = c.open(url, method=metodo, json={})
        j = r.get_json(silent=True) or {}
        saida.append([regra.endpoint, metodo, r.status_code, j.get('codigo') if isinstance(j, dict) else None])
print('FLASK_JSON ' + json.dumps({'guardados': guardados, 'rotas': saida}))
"""


def rotas_do_flask(dsn, perfil, ids, guarda_propria):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT_ROTAS, str(perfil), json.dumps(ids), json.dumps(guarda_propria)],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


# Escritas que o proprio codigo isenta da guarda (isentos= / _ESCRITAS_LIVRES), por so lerem ou por serem catalogos
# globais do Flask (FIN-ESCRITOR-UNICO-FINAL-1 §3): revelar codigo do cartao, analises da importacao, gestao de perfil
# (criar, tornar padrao, perfil ativo), simulacao de quitacao e o catalogo de indices.
ISENTAS_DOCUMENTADAS = {
    'cartoes.revelar_codigo_seguranca', 'importacao_cartao.analisar_importacao_cartao', 'importacao_cartao.upload_csv',
    'importacao_cartao.previsualizar_importacao', 'importacao_cartao.sugerir_categorias',
    'perfis_financeiros.criar_perfil_financeiro', 'perfis_financeiros.definir_perfil_financeiro_padrao',
    'perfis_financeiros.definir_perfil_financeiro_ativo', 'financiamentos.simular_quitacao', 'financiamentos.criar_indexador',
}
GUARDA_PROPRIA = ['financiamentos', 'consorcios', 'contas_bancarias']


def perfis_sem_preferencia(dsn):
    linhas = sql(dsn, 'select * from public.perfil_financeiro order by id')
    return [{k: v for k, v in linha.items() if k not in ('padrao', 'updated_at')} for linha in linhas]


def test_i3_flask_recusa_toda_escrita_guardada_em_perfil_do_novo_aplicativo(banco):
    fid = novo_financiamento(banco)
    conta = conta_bancaria(banco, PESSOAL)
    consorcio = sql(banco, "insert into public.contrato_consorcio (perfil_financeiro_id, nome, valor_inicial, numero_parcelas, "
                           "mes_inicio, ativo) values (%s, 'Consorcio guarda (ficticio)', 1000, 10, '2027-03-01', true) "
                           "returning id", (PESSOAL,))[0]['id']
    pid = parcela(banco, fid, 1)['parcela_id']
    vigencia = sql(banco, 'select id from public.financiamento_seguro_vigencia where financiamento_id = %s limit 1', (fid,))[0]['id']
    ajuste = sql(banco, "insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, "
                        "data_movimento, origem, ajustavel, criado_em) values (%s, %s, 'CREDITO', 1, 'Ajuste guarda (ficticio)', "
                        "'2027-03-01', 'AJUSTE', true, now()) returning id", (PESSOAL, conta))[0]['id']
    ids = {'perfis_financeiros': {'perfil_id': PESSOAL}, 'financiamentos': {'id': fid, 'parcela_id': pid},
           'financiamento_seguro': {'financiamento_id': fid, 'vigencia_id': vigencia}, 'consorcios': {'id': consorcio},
           'contas_bancarias': {'id': conta, 'conta_id': conta, 'mov_id': ajuste}}
    antes = resumo_tabelas(banco)
    perfis_antes = perfis_sem_preferencia(banco)
    r = rotas_do_flask(banco, PESSOAL, ids, GUARDA_PROPRIA)
    assert set(r['guardados']) >= {'cartoes', 'despesas', 'patrimonio', 'receitas', 'recorrencias', *GUARDA_PROPRIA}, r['guardados']
    recusadas = [x for x in r['rotas'] if x[2] == 409 and x[3] == 'SISTEMA_NOVO']
    passaram = sorted({(e, m, s) for e, m, s, codigo in r['rotas'] if not (s == 409 and codigo == 'SISTEMA_NOVO')})
    assert {e for e, _, _ in passaram} <= ISENTAS_DOCUMENTADAS, passaram
    assert len(recusadas) >= 60, len(recusadas)
    # Unico efeito admitido: "tornar padrao" (isento, preferencia do usuario) regrava padrao/updated_at dos perfis.
    assert tabelas_alteradas(antes, resumo_tabelas(banco)) in ([], ['public.perfil_financeiro'])
    assert perfis_sem_preferencia(banco) == perfis_antes


# =====================================================================================================================
# I4 — Alternancia de escritor: Flask -> novo aplicativo -> Flask
# =====================================================================================================================

def test_i4_alternancia_de_escritor_preserva_historico(cluster):  # noqa: F811
    dsn = copiar(cluster)  # Pessoal no Flask
    despesa = {'nome': 'Alternancia', 'valor': '12.00', 'categoria_id': CATEGORIA, 'data_vencimento': '2027-03-10',
               'recorrente': False}

    def flask_cria(nome):
        r = flask(dsn, [('perfil', PESSOAL), ('d', 'post', '/api/despesas/', {'nome': nome, 'valor': 10, 'tipo': 'Simples', 'categoria_id': CATEGORIA, 'data_vencimento': '2027-03-10'})])
        return r['d']

    # Fase 1: Flask escreve; o novo aplicativo e recusado sem gravar.
    assert flask_cria('Fase 1 Flask (ficticia)')[0] in (200, 201)
    antes = resumo_tabelas(dsn)
    assert erro(rpc, dsn, 'criar_despesa', PESSOAL, {**despesa, 'nome': 'Fase 1 novo'}, chave()).diag.message_hint == 'SISTEMA_FLASK'
    assert resumo_tabelas(dsn) == antes
    fase1 = {r['id']: r['h'] for r in sql(dsn, "select id, md5(i::text) h from public.item_despesa i where nome like 'Fase 1%%'")}

    # Fase 2: novo aplicativo escreve; o Flask e recusado (409) sem gravar.
    atribuir(dsn, 'PESSOAL')
    rpc(dsn, 'criar_despesa', PESSOAL, {**despesa, 'nome': 'Fase 2 novo (ficticia)'}, chave())
    antes = resumo_tabelas(dsn)
    status, corpo = flask_cria('Fase 2 Flask')
    assert status == 409 and corpo['codigo'] == 'SISTEMA_NOVO'
    assert tabelas_alteradas(antes, resumo_tabelas(dsn)) == []

    # Fase 3: volta ao Flask; o novo aplicativo volta a ser recusado.
    atribuir(dsn, 'PESSOAL', 'FLASK')
    assert flask_cria('Fase 3 Flask (ficticia)')[0] in (200, 201)
    antes = resumo_tabelas(dsn)
    assert erro(rpc, dsn, 'criar_despesa', PESSOAL, {**despesa, 'nome': 'Fase 3 novo'}, chave()).diag.message_hint == 'SISTEMA_FLASK'
    assert resumo_tabelas(dsn) == antes

    # Historico: o que cada fase gravou continua igual; nada das tentativas recusadas.
    nomes = [r['nome'] for r in sql(dsn, "select nome from public.item_despesa where nome like 'Fase %%' order by nome")]
    assert nomes == ['Fase 1 Flask (ficticia)', 'Fase 2 novo (ficticia)', 'Fase 3 Flask (ficticia)']
    assert {r['id']: r['h'] for r in sql(dsn, "select id, md5(i::text) h from public.item_despesa i where nome like 'Fase 1%%'")} == fase1
    # As duas trocas ficaram registradas no historico, em ordem.
    trocas = sql(dsn, 'select gerador_anterior, gerador_novo from financeiro.gerador_recorrencia_historico '
                      'where perfil_financeiro_id = %s order by id', (PESSOAL,))
    assert [(t['gerador_anterior'] or 'FLASK', t['gerador_novo']) for t in trocas][-2:] == [('FLASK', 'NOVO'), ('NOVO', 'FLASK')], trocas
    assert sql(dsn, "select coalesce((select escritor from financeiro.catalogo_categorias limit 1), 'FLASK') e")[0]['e'] == 'FLASK'


# =====================================================================================================================
# I5 — Isolamento integrado: A e B no novo aplicativo, C (Empresa) no Flask
# =====================================================================================================================

def test_i5_isolamento_entre_tres_perfis(banco):
    sql(banco, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true where perfil_financeiro_id = %s",
        (EMPRESA,))
    # Cada perfil do novo aplicativo com recorrencia gerada e paga, financiamento e caixinhas.
    dados = {}
    for perfil, usuario in ((PESSOAL, USUARIO_A), (PERFIL_B, USUARIO_B)):
        item = nova_recorrencia(banco, f'Isolamento {perfil}', 'semanal_1_3', '2027-03-03', perfil=perfil, usuario=usuario)
        gerar_confirmado(banco, perfil=perfil, usuario=usuario, mes='2027-03-01')
        conta = contas_do_item(banco, item)[0]['id']
        pagar(banco, conta, '2027-03-03', perfil=perfil, usuario=usuario)
        fid = novo_financiamento(banco, perfil=perfil, usuario=usuario, nome=f'Fin isolamento {perfil}')
        cx = [caixinha(banco, f'Cx1 {perfil}', 500, perfil, usuario), caixinha(banco, f'Cx2 {perfil}', 0, perfil, usuario)]
        dados[perfil] = {'item': item, 'conta': conta, 'pendente': contas_do_item(banco, item)[1]['id'], 'fid': fid, 'cx': cx,
                         'banco': conta_bancaria(banco, perfil)}
    a, b = dados[PESSOAL], dados[PERFIL_B]
    resumos = {p: resumo_perfil(banco, p) for p in (PESSOAL, PERFIL_B, EMPRESA)}
    tudo = resumo_tabelas(banco)

    tentativas = {
        # A, no proprio perfil, com identificadores de B
        'pagar conta de B': lambda: pagar(banco, b['pendente'], '2027-03-10'),
        'pagar com a conta bancaria de B': lambda: pagar(banco, a['pendente'], '2027-03-10', banco_id=b['banco']),
        'excluir despesa de B': lambda: rpc(banco, 'excluir_despesa', PESSOAL, b['pendente'], versao_despesa(banco, b['pendente'])),
        'editar recorrencia de B': lambda: rpc(banco, 'editar_recorrencia', PESSOAL, b['item'], versao_recorrencia(banco, b['item']),
                                               {'valor': '1.00'}),
        'amortizar financiamento de B': lambda: amortizar(banco, b['fid'], '2027-03-20', 100),
        'regenerar financiamento de B': lambda: rpc(banco, 'regenerar_parcelas_financiamento', PESSOAL, b['fid']),
        'transferir da caixinha de B': lambda: transferir(banco, b['cx'][0], a['cx'][1], 10),
        'transferir para a caixinha de B': lambda: transferir(banco, a['cx'][0], b['cx'][1], 10),
        'estornar pagamento de B': lambda: rpc(banco, 'estornar_pagamento_despesa', PESSOAL, b['conta'],
                                               sql(banco, 'select id from public.movimento_financeiro where conta_id = %s', (b['conta'],))[0]['id'],
                                               {'motivo': 'x', 'data_estorno': '2027-03-11'}, chave()),
        # Perfis alheios
        'A no perfil B': lambda: amortizar(banco, b['fid'], '2027-03-20', 100, perfil=PERFIL_B),
        'B no perfil A': lambda: transferir(banco, a['cx'][0], a['cx'][1], 10, usuario=USUARIO_B),
        'A no perfil C (Flask)': lambda: caixinha(banco, 'Cx Empresa', 10, perfil=EMPRESA),
        'A gera mes do perfil C (Flask)': lambda: gerar(banco, 0, perfil=EMPRESA, mes='2027-03-01'),
    }
    for nome, tentativa in tentativas.items():
        with pytest.raises(psycopg2.Error) as e:
            tentativa()
        assert e.value.pgcode in ('22023', 'P0001', '42501', 'P0002'), (nome, e.value.pgcode, str(e.value))
    assert resumo_tabelas(banco) == tudo
    assert {p: resumo_perfil(banco, p) for p in (PESSOAL, PERFIL_B, EMPRESA)} == resumos


# =====================================================================================================================
# I6 — Concorrencia entre modulos (mesmo perfil)
# =====================================================================================================================

def test_i6_pagamento_de_parcela_e_amortizacao_simultaneos(banco):
    fid = novo_financiamento(banco)
    conta = conta_bancaria(banco, PESSOAL)
    p3 = parcela(banco, fid, 3)  # 05/05/2027
    r_pag, r_amo = em_paralelo(lambda: pagar(banco, p3['conta_id'], '2027-05-05'),
                               lambda: amortizar(banco, fid, '2027-04-20', 1500))
    # Serializados pela trava do perfil: as duas passam (amortizacao antes, pagamento do valor recalculado) ou a
    # amortizacao e recusada porque a parcela ja foi paga.
    pagou, amortizou = r_pag[1] is None, r_amo[1] is None
    assert pagou or amortizou, (r_pag, r_amo)
    if not amortizou:
        assert r_amo[1].diag.message_hint == 'PARCELA_PROTEGIDA', r_amo[1]
    if not pagou:  # pagamento com valor devido antigo depois do recalculo: recusa limpa
        assert r_pag[1].pgcode in ('22023', 'P0001', '40001'), r_pag[1]
    n_amort = sql(banco, 'select count(*) n from public.financiamento_amortizacao_extra where financiamento_id = %s', (fid,))[0]['n']
    assert n_amort == (1 if amortizou else 0)
    movs = sql(banco, 'select count(*) n from public.movimento_financeiro where conta_id = %s', (p3['conta_id'],))[0]['n']
    final = parcela(banco, fid, 3)
    assert movs == (1 if pagou else 0) and (final['status_pagamento'] == 'Pago') == pagou
    conferir_saldo_bancario(banco, conta)
    sem_duplicidade(banco)


def test_i6_geracao_e_exclusao_simultaneas(banco):
    item = nova_recorrencia(banco, 'Concorrencia integ', 'semanal_1_4', '2027-03-04')
    gerar_confirmado(banco, mes='2027-03-01')
    alvo = next(c for c in contas_do_item(banco, item) if str(c['data_vencimento']) == '2027-03-18')
    versao = versao_despesa(banco, alvo['id'])
    total = previa(banco, mes='2027-05-01')['a_gerar']
    r_ger, r_exc = em_paralelo(lambda: gerar(banco, total, mes='2027-05-01'),
                               lambda: rpc(banco, 'excluir_despesa', PESSOAL, alvo['id'], versao))
    assert r_exc[1] is None, r_exc[1]
    assert r_ger[1] is None or 'desatualizad' in str(r_ger[1]).lower() or r_ger[1].pgcode in ('40001', 'P0001'), r_ger[1]
    if r_ger[1] is not None:  # previa ficou desatualizada: nova previa e geracao
        gerar_confirmado(banco, mes='2027-05-01')
    datas = [str(c['data_vencimento']) for c in contas_do_item(banco, item)]
    assert '2027-03-18' not in datas and len(datas) == len(set(datas))
    assert sql(banco, "select situacao from financeiro.recorrencia_ocorrencia where item_despesa_id = %s and data_ocorrencia = '2027-03-18'",
               (item,)) == [{'situacao': 'DISPENSADA'}]
    gerar_confirmado(banco, mes='2027-05-01')
    assert '2027-03-18' not in [str(c['data_vencimento']) for c in contas_do_item(banco, item)]
    sem_duplicidade(banco)


def test_i6_transferencias_patrimoniais_cruzadas_simultaneas(banco):
    cx = [caixinha(banco, f'Cruzada {i}', 100) for i in range(3)]
    pares = [(0, 1), (1, 0), (1, 2), (2, 1), (2, 0), (0, 2)] * 2
    resultados = em_paralelo(*[lambda o=o, d=d: transferir(banco, cx[o], cx[d], 30) for o, d in pares])
    falhas = [e for _, e in resultados if e is not None]
    assert all('Saldo insuficiente' in str(e) for e in falhas), falhas
    assert sql(banco, 'select count(*) n from public.transferencia where conta_origem_id = any(%s)', (cx,))[0]['n'] == \
        len(pares) - len(falhas)
    conferir_patrimonio(banco, cx)


def test_i6_troca_de_escritor_espera_a_escrita_em_andamento(banco):
    """A escrita (trava do perfil) segura a troca de escritor ate terminar; depois da troca, a escrita e recusada."""
    conn = psycopg2.connect(banco)
    try:
        with conn.cursor() as cur:  # transacao aberta de uma escrita do novo aplicativo, ainda sem commit
            cur.execute('set local role authenticated')
            cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims_usuario(USUARIO_A)),))
            cur.execute('select financeiro.criar_caixinha(%s, %s::jsonb, %s)',
                        (PESSOAL, json.dumps({'nome': 'Durante a troca', 'tipo': 'Reserva', 'saldo_inicial': 1}), chave()))
            troca = []
            t = threading.Thread(target=lambda: troca.append(atribuir(banco, 'PESSOAL', 'FLASK')))
            t.start()
            time.sleep(2)
            assert t.is_alive() and troca == []  # a troca espera a escrita
            conn.commit()
            t.join(timeout=30)
            assert not t.is_alive() and troca
    finally:
        conn.close()
    assert sql(banco, "select count(*) n from public.conta_patrimonio where nome = 'Durante a troca'")[0]['n'] == 1
    assert erro(caixinha, banco, 'Depois da troca', 1).diag.message_hint == 'SISTEMA_FLASK'
    # E o inverso: troca em andamento segura a escrita, que entao e recusada pelo novo escritor.
    atribuir(banco, 'PESSOAL')
    conn = psycopg2.connect(banco)
    try:
        with conn.cursor() as cur:
            cur.execute('select financeiro.definir_gerador_recorrencia(%s, %s, %s, %s)',
                        (PESSOAL, 'FLASK', 'administrador de teste', 'concorrencia'))
            escrita = []
            t = threading.Thread(target=lambda: escrita.append(erro(caixinha, banco, 'Na troca', 1)))
            t.start()
            time.sleep(2)
            assert t.is_alive()
            conn.commit()
            t.join(timeout=30)
    finally:
        conn.close()
    assert escrita and escrita[0].diag.message_hint == 'SISTEMA_FLASK'
    assert sql(banco, "select count(*) n from public.conta_patrimonio where nome in ('Na troca', 'Depois da troca')")[0]['n'] == 0


# =====================================================================================================================
# I7 — Reversoes em ordem inversa (1126 -> 1123) e reaplicacao em ordem crescente
# =====================================================================================================================

def esquema(dsn):
    """Definicoes de funcoes e colunas dos esquemas financeiro e public (para comparar estados)."""
    funcoes = {f"{r['n']}({r['a']})": r['h'] for r in sql(dsn, """
        select p.proname n, pg_get_function_identity_arguments(p.oid) a, md5(pg_get_functiondef(p.oid)) h
          from pg_proc p join pg_namespace s on s.oid = p.pronamespace
         where s.nspname in ('financeiro', 'public') and p.prokind = 'f'""")}
    colunas = sorted(f"{r['t']}.{r['c']}:{r['d']}" for r in sql(dsn, """
        select table_schema || '.' || table_name t, column_name c, data_type d from information_schema.columns
         where table_schema in ('financeiro', 'public')"""))
    privilegios = sorted(f"{r['f']}" for r in sql(dsn, """
        select p.proname || ':' || has_function_privilege('authenticated', p.oid, 'EXECUTE') f
          from pg_proc p join pg_namespace s on s.oid = p.pronamespace where s.nspname = 'financeiro'"""))
    return {'funcoes': funcoes, 'colunas': colunas, 'privilegios': privilegios}


def executar_arquivo(dsn, caminho):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(Path(caminho).read_text(encoding='utf-8'))
    finally:
        conn.close()


def diferenca_esquema(a, b):
    f = {k for k in set(a['funcoes']) | set(b['funcoes']) if a['funcoes'].get(k) != b['funcoes'].get(k)}
    return {'funcoes': sorted(f), 'colunas': sorted(set(a['colunas']) ^ set(b['colunas'])),
            'privilegios': sorted(set(a['privilegios']) ^ set(b['privilegios']))}


@pytest.fixture(scope='module')
def base_1122(tmp_path_factory):
    """Cluster so com as migrations ate 20261122 (o estado anterior aos quatro MVPs)."""
    with ClusterLocal(PG_BIN, tmp_path_factory.mktemp('base_1122')) as c:
        c.aplicar_shim()
        c.criar_tabelas_legadas()
        for m in sorted(MIGRATIONS.glob('*.sql')):
            if m.name[:14] < VERSOES[0]:
                executar_arquivo(c.dsn(), m)
        yield esquema(c.dsn())


def test_i7_reversoes_em_ordem_inversa_e_reaplicacao(cluster, base_1122):  # noqa: F811
    dsn = copiar(cluster)
    completo = esquema(dsn)
    reversoes = {v: next(REVERSAO.glob(f'{v}_*.sql')) for v in VERSOES}
    for versao in reversed(VERSOES):  # 1126, 1125, 1124, 1123
        executar_arquivo(dsn, reversoes[versao])
    assert diferenca_esquema(esquema(dsn), base_1122) == {'funcoes': [], 'colunas': [], 'privilegios': []}
    for versao in VERSOES:  # 1123, 1124, 1125, 1126
        executar_arquivo(dsn, next(MIGRATIONS.glob(f'{versao}_*.sql')))
    assert diferenca_esquema(esquema(dsn), completo) == {'funcoes': [], 'colunas': [], 'privilegios': []}
    # Funciona depois da reaplicacao: recorrencia semanal, financiamento e caixinha num perfil do novo aplicativo.
    atribuir(dsn, 'PESSOAL')
    sql(dsn, "update public.item_despesa set ativo = false where tipo is distinct from 'Agregador'")
    item = nova_recorrencia(dsn, 'Depois da reaplicacao', 'semanal_1_3', '2027-03-03')
    gerar_confirmado(dsn, mes='2027-03-01')
    assert len(contas_do_item(dsn, item)) == 9
    assert novo_financiamento(dsn) and caixinha(dsn, 'Depois da reaplicacao', 10)


# =====================================================================================================================
# I8 — As tres escritas do Flask que ficavam sem guarda de escritor (FIN-ESCRITOR-UNICO-GUARDAS-1, G1-G3)
# =====================================================================================================================

def comprovante(dsn, perfil):
    return sql(dsn, "insert into public.ir_comprovante (perfil_financeiro_id, ano_calendario, data_documento, prestador_nome, "
                    "valor, status, hash_arquivo, created_at, updated_at) values (%s, 2027, '2027-03-08', "
                    "'Fornecedor ficticio integ', 123.45, 'IMPORTADO', md5(random()::text), now(), now()) returning id",
               (perfil,))[0]['id']


def despesa_prevista(dsn, perfil):
    return sql(dsn, "insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista, "
                    "data_original_prevista, data_atual_prevista, valor_previsto, status) values "
                    "(%s, 'MANUAL', 1, %s, '2027-03-01', '2027-03-01', '2027-03-01', 80, 'PREVISTA') returning id",
               (perfil, CATEGORIA))[0]['id']


def bem_da_empresa(dsn):
    sql(dsn, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true where perfil_financeiro_id = %s",
        (EMPRESA,))
    atribuir(dsn, 'EMPRESA')
    bem = rpc(dsn, 'criar_bem_patrimonial', EMPRESA, {'nome': 'Bem integ (ficticio)', 'valor_aquisicao': 1000}, chave())['bem_id']
    atribuir(dsn, 'EMPRESA', 'FLASK')
    return bem


def escrita_flask(caso, dsn):
    """Monta o cenario e devolve (perfil, passo do Flask)."""
    if caso == 'criar_financeiro_comprovante':
        doc = comprovante(dsn, PESSOAL)
        return PESSOAL, ('w', 'post', f'/api/ir/comprovantes/{doc}/criar-financeiro',
                         {'tipo_destino': 'DESPESA', 'forma_pagamento': 'pix', 'categoria_id': CATEGORIA, 'valor': 123.45,
                          'data': '2027-03-10'})
    if caso == 'despesas_previstas_confirmar':
        prevista = despesa_prevista(dsn, PESSOAL)
        return PESSOAL, ('w', 'post', f'/api/despesas-previstas/{prevista}/confirmar',
                         {'meio_pagamento': 'pix', 'categoria_id': CATEGORIA, 'data_vencimento': '2027-03-10'})
    bem = bem_da_empresa(dsn)
    doc = comprovante(dsn, EMPRESA)
    return EMPRESA, ('w', 'post', f'/api/ir/comprovantes/{doc}/vinculos',
                     {'tipo_entidade': 'PATRIMONIO', 'entidade_id': bem, 'tipo_vinculo': 'NOTA_FISCAL'})


CASOS_I8 = ['criar_financeiro_comprovante', 'despesas_previstas_confirmar', 'vinculo_patrimonial_documento_fiscal']


@pytest.mark.parametrize('caso', CASOS_I8)
def test_i8_controle_com_perfil_no_flask_a_mesma_escrita_grava(cluster, caso):  # noqa: F811
    """Controle: a requisicao do I8 e valida e grava quando o perfil esta no Flask."""
    dsn = copiar(cluster)
    perfil, passo = escrita_flask(caso, dsn)
    antes = resumo_tabelas(dsn)
    r = flask(dsn, [('perfil', perfil), passo])
    assert r['w'][0] in (200, 201), r['w']
    assert tabelas_alteradas(antes, resumo_tabelas(dsn))


@pytest.mark.parametrize('caso', CASOS_I8)
def test_i8_flask_recusa_sem_gravar_em_perfil_do_novo_aplicativo(cluster, caso):  # noqa: F811
    """Comportamento exigido: com o perfil no novo aplicativo, o Flask recusa (409 SISTEMA_NOVO) e nada e gravado."""
    dsn = copiar(cluster)
    perfil, passo = escrita_flask(caso, dsn)
    atribuir(dsn, 'PESSOAL' if perfil == PESSOAL else 'EMPRESA')
    antes = resumo_tabelas(dsn)
    r = flask(dsn, [('perfil', perfil), passo])
    alteradas = tabelas_alteradas(antes, resumo_tabelas(dsn))
    assert r['w'][0] == 409 and (r['w'][1] or {}).get('codigo') == 'SISTEMA_NOVO' and alteradas == [], (r['w'][0], alteradas)
