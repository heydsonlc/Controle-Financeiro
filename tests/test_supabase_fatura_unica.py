"""
Testes FIN-FATURA-UNICA-1 — concorrencia REAL no PostgreSQL.

Cluster descartavel com o cenario FICTICIO do FIN-RECORRENCIA-1 (copia por teste).
Os acessos do Flask sao processos Python reais (CartaoService), e os do novo
aplicativo sao chamadas a financeiro.gerar_mes em conexoes proprias. Para que a
corrida aconteca de verdade (e nao em sequencia), os processos Flask param em
barreiras por arquivo:
- `antes_do_insert`: a consulta "a fatura existe?" ja respondeu NAO e o INSERT ainda
  nao foi feito (pausa no calculo do planejado, que fica entre os dois);
- `antes_do_commit`: o INSERT ja foi feito e a transacao ainda esta aberta.
O teste de controle mostra que, sem o indice unico, a mesma corrida duplica a fatura.
"""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_recorrencia import (
    ID,
    MES,
    PG_BIN,
    ROOT,
    USUARIO_A,
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

CARTAO = 910
MIGRATION = ROOT / 'supabase' / 'migrations' / '20261025090000_financeiro_fatura_unica.sql'

_WORKER = r'''
import json, sys, time
from datetime import date
from pathlib import Path
cfg = json.loads(sys.argv[1])
pasta = Path(cfg['pasta'])

def esperar(etapa):
    (pasta / f"{cfg['nome']}_{etapa}").touch()
    limite = time.time() + 120
    while not (pasta / f'liberar_{etapa}').exists():
        if time.time() > limite:
            raise SystemExit('barreira expirou: ' + etapa)
        time.sleep(0.02)

from backend.app import create_app
from backend.models import db
from backend.services.cartao_service import CartaoService

if cfg.get('pausa') == 'antes_do_insert':
    original = CartaoService.calcular_planejado
    feito = []
    def pausado(cartao_id, competencia):
        if not feito:
            feito.append(1)
            esperar('consultou')
        return original(cartao_id, competencia)
    CartaoService.calcular_planejado = staticmethod(pausado)

app = create_app('local')
with app.app_context():
    if cfg.get('pausa') == 'antes_do_commit':
        commit_original = db.session.commit
        feito = []
        def commit_pausado():
            if not feito:
                feito.append(1)
                esperar('inseriu')
            return commit_original()
        db.session.commit = commit_pausado
    if cfg['acao'] == 'fatura':
        fatura = CartaoService.get_or_create_fatura(cfg['cartao'], date.fromisoformat(cfg['competencia']))
        print('RESULTADO ' + json.dumps({'fatura': fatura.id}))
    else:
        dados = dict(cfg['dados'])
        dados['data_compra'] = date.fromisoformat(dados['data_compra'])  # a rota converte; aqui o servico direto
        lancamento, fatura = CartaoService.adicionar_lancamento(dados)
        print('RESULTADO ' + json.dumps({'lancamento': lancamento.id, 'fatura': fatura.id}))
'''


class Flask:
    """Processo Flask real executando uma criacao de fatura ou uma compra."""

    def __init__(self, dsn, pasta, nome, **cfg):
        env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
        env.pop('FLASK_ENV', None)
        # Saida em arquivo, nao em pipe: o log do Flask encheria o pipe e travaria o processo.
        self.saida, self.erro = Path(pasta) / f'{nome}.out', Path(pasta) / f'{nome}.err'
        with open(self.saida, 'w') as saida, open(self.erro, 'w') as erro:
            self.processo = subprocess.Popen(
                [sys.executable, '-c', _WORKER, json.dumps({'pasta': str(pasta), 'nome': nome, **cfg})],
                cwd=ROOT, env=env, stdout=saida, stderr=erro, stdin=subprocess.DEVNULL)

    def log(self):
        return self.erro.read_text(errors='replace')

    def resultado(self):
        self.processo.wait(timeout=180)
        assert self.processo.returncode == 0, self.log()[-2000:]
        linhas = self.saida.read_text(errors='replace').splitlines()
        return json.loads([linha for linha in linhas if linha.startswith('RESULTADO ')][-1][10:])


def aguardar(pasta, nomes, processos=(), limite=150):
    fim = time.time() + limite
    while not all((pasta / nome).exists() for nome in nomes):
        for p in processos:  # processo que morreu antes da barreira: mostra o motivo
            if p.processo.poll() is not None:
                raise AssertionError(f'processo Flask encerrou: {p.log()[-2000:]}')
        if time.time() > fim:
            raise AssertionError(f'barreira nao alcancada: {nomes}')
        time.sleep(0.05)


def liberar(pasta, etapa):
    (pasta / f'liberar_{etapa}').touch()


def aguardar_bloqueio(dsn, limite=30):
    """Espera uma sessao parada na trava do indice unico (prova de que a corrida ocorreu)."""
    fim = time.time() + limite
    while time.time() < fim:
        if sql(dsn, "select count(*) as n from pg_stat_activity where datname = current_database() "
                    "and wait_event_type = 'Lock'")[0]['n']:
            return
        time.sleep(0.05)
    raise AssertionError('nenhuma sessao esperou a trava')


def faturas(dsn, competencia, cartao=CARTAO):
    return sql(dsn, 'select * from public.conta where item_despesa_id = %s and is_fatura_cartao '
                    'and cartao_competencia = %s order by id', (cartao, competencia))


def em_thread(funcao):
    resultado = {}

    def executar():
        try:
            resultado['valor'] = funcao()
        except Exception as exc:  # noqa: BLE001
            resultado['erro'] = exc

    tarefa = threading.Thread(target=executar)
    tarefa.start()
    return tarefa, resultado


def compra(descricao, mes_fatura='2027-06-01', parcelas=3, valor='300.00'):
    return {'cartao_id': CARTAO, 'valor': valor, 'descricao': descricao, 'data_compra': mes_fatura[:8] + '05',
            'mes_fatura': mes_fatura, 'categoria_id': 952, 'total_parcelas': parcelas}


@pytest.fixture
def banco(cluster):  # noqa: F811
    """Copia com vencimento dia 10 no cartao: o Flask nao cria fatura de dia 31 em mes de 30 dias
    (defeito conhecido, Q3 do FIN-RECORRENCIA-1), o que impediria testar a corrida em junho."""
    dsn = copiar(cluster)
    sql(dsn, 'update public.config_agregador set dia_vencimento = 10 where item_despesa_id = %s', (CARTAO,))
    # O Flask completa o avatar do perfil na primeira leitura (UPDATE); com um processo pausado na
    # barreira, o outro esperaria essa linha. Ja preenchido, como em semear_contas.
    sql(dsn, 'update public.perfil_financeiro set avatar = upper(left(nome, 2))')
    return dsn


# ---------------------------------------------------------------------------
# 1. Flask x Flask
# ---------------------------------------------------------------------------

def test_duas_requisicoes_flask_simultaneas_criam_uma_unica_fatura(banco, tmp_path):
    processos = [Flask(banco, tmp_path, f'f{i}', acao='fatura', cartao=CARTAO, competencia='2027-06-01',
                       pausa='antes_do_insert') for i in (1, 2)]
    aguardar(tmp_path, ['f1_consultou', 'f2_consultou'], processos)  # as duas ja viram "nao existe"
    liberar(tmp_path, 'consultou')
    ids = {p.resultado()['fatura'] for p in processos}
    assert len(faturas(banco, '2027-06-01')) == 1
    assert ids == {faturas(banco, '2027-06-01')[0]['id']}  # o perdedor recebeu a existente


def test_sem_o_indice_a_trava_do_cartao_ainda_impede_a_duplicidade(banco, tmp_path):
    """Antes (FIN-FATURA-UNICA-1) este controle duplicava: a consulta previa nao bastava sem o indice.
    FIN-FATURA-INTEGRIDADE-1: criar fatura trava o cartao e reconsulta, entao as duas criacoes ficam em
    serie mesmo sem o indice; o indice unico continua como segunda defesa no banco."""
    sql(banco, 'drop index public.ux_conta_fatura_cartao_competencia')
    processos = [Flask(banco, tmp_path, f'f{i}', acao='fatura', cartao=CARTAO, competencia='2027-06-01',
                       pausa='antes_do_insert') for i in (1, 2)]
    aguardar(tmp_path, ['f1_consultou', 'f2_consultou'], processos)
    liberar(tmp_path, 'consultou')
    ids = {p.resultado()['fatura'] for p in processos}
    assert len(faturas(banco, '2027-06-01')) == 1 and len(ids) == 1


# ---------------------------------------------------------------------------
# 2. Novo aplicativo x novo aplicativo
# ---------------------------------------------------------------------------

def test_duas_geracoes_simultaneas_do_novo_aplicativo(banco):
    atribuir(banco, 'PESSOAL')
    total = previa(banco)['a_gerar']
    barreira = threading.Barrier(2)
    tarefas = [em_thread(lambda: (barreira.wait(10), gerar(banco, total))[1]) for _ in range(2)]
    for tarefa, _ in tarefas:
        tarefa.join(60)
    assert sorted(r['valor']['criadas']['faturas'] for _, r in tarefas) == [0, 2]
    for comp in ('2027-03-01', '2027-04-01'):
        assert len(faturas(banco, comp)) == 1


# ---------------------------------------------------------------------------
# 3. Flask x novo aplicativo (nos dois sentidos)
# ---------------------------------------------------------------------------

def test_flask_consultou_antes_e_o_novo_aplicativo_criou_primeiro(banco, tmp_path):
    atribuir(banco, 'PESSOAL')
    antes = digital(banco)
    processo = Flask(banco, tmp_path, 'f1', acao='fatura', cartao=CARTAO, competencia=MES, pausa='antes_do_insert')
    aguardar(tmp_path, ['f1_consultou'], [processo])
    r = gerar(banco, previa(banco)['a_gerar'])  # cria e grava a fatura de marco
    liberar(tmp_path, 'consultou')
    resultado = processo.resultado()
    assert r['criadas']['faturas'] == 2
    assert [f['id'] for f in faturas(banco, MES)] == [resultado['fatura']]
    assert digital(banco) == antes  # sem movimento bancario nem alteracao de saldo


def test_flask_inseriu_sem_commit_e_o_novo_aplicativo_reconhece(banco, tmp_path):
    atribuir(banco, 'PESSOAL')
    processo = Flask(banco, tmp_path, 'f1', acao='fatura', cartao=CARTAO, competencia=MES, pausa='antes_do_commit')
    aguardar(tmp_path, ['f1_inseriu'], [processo])
    total = previa(banco)['a_gerar']  # a fatura do Flask ainda nao e visivel: conta como "a gerar"
    tarefa, geracao = em_thread(lambda: gerar(banco, total))
    aguardar_bloqueio(banco)  # o INSERT do novo motor espera a transacao do Flask
    liberar(tmp_path, 'inseriu')
    resultado = processo.resultado()
    tarefa.join(60)
    r = geracao['valor']
    assert (r['criadas']['faturas'], r['criadas']['total']) == (1, total - 1)  # abril; marco veio do Flask
    assert r['existentes'] == 3 + 1
    assert [f['id'] for f in faturas(banco, MES)] == [resultado['fatura']]


# ---------------------------------------------------------------------------
# 4-5. Compras parceladas e recorrencia + compra no mesmo mes
# ---------------------------------------------------------------------------

def test_compras_parceladas_simultaneas_sem_perder_compras(banco, tmp_path):
    antes = digital(banco)
    processos = [Flask(banco, tmp_path, nome, acao='compra', dados=compra(f'Compra {nome}'), pausa='antes_do_insert')
                 for nome in ('x', 'y')]
    aguardar(tmp_path, ['x_consultou', 'y_consultou'], processos)
    liberar(tmp_path, 'consultou')
    for p in processos:
        p.resultado()
    for comp in ('2027-06-01', '2027-07-01', '2027-08-01'):
        assert len(faturas(banco, comp)) == 1
    parcelas = sql(banco, "select descricao, numero_parcela, mes_fatura, valor, compra_id from public.lancamento_agregado "
                          "where descricao like 'Compra %%' order by descricao, numero_parcela")
    assert len(parcelas) == 6 and len({p['compra_id'] for p in parcelas}) == 2
    for nome in ('Compra x', 'Compra y'):
        minhas = [p for p in parcelas if p['descricao'] == nome]
        assert [p['numero_parcela'] for p in minhas] == [1, 2, 3]
        assert sum(p['valor'] for p in minhas) == Decimal('300.00')
    assert digital(banco) == antes


def test_geracao_de_recorrencias_e_compra_no_mesmo_mes(banco, tmp_path):
    atribuir(banco, 'PESSOAL')
    processo = Flask(banco, tmp_path, 'f1', acao='compra', dados=compra('Compra marco', MES, 1, '80.00'),
                     pausa='antes_do_insert')
    aguardar(tmp_path, ['f1_consultou'], [processo])
    gerar(banco, previa(banco)['a_gerar'])
    liberar(tmp_path, 'consultou')
    resultado = processo.resultado()
    assert [f['id'] for f in faturas(banco, MES)] == [resultado['fatura']]
    compras = sql(banco, 'select descricao, is_recorrente from public.lancamento_agregado where cartao_id = %s '
                         'and mes_fatura = %s order by descricao', (CARTAO, MES))
    assert compras == [{'descricao': 'Compra marco', 'is_recorrente': False},
                       {'descricao': 'Streaming', 'is_recorrente': True}]


# ---------------------------------------------------------------------------
# Faturas pagas e faturas com lancamentos existentes
# ---------------------------------------------------------------------------

def test_fatura_paga_preservada_e_parcelas_redirecionadas_sem_duplicar(banco, tmp_path):
    sql(banco, "insert into public.conta (id, item_despesa_id, perfil_financeiro_id, mes_referencia, descricao, valor, "
               "valor_planejado, valor_executado, data_vencimento, status_pagamento, data_pagamento, is_fatura_cartao, "
               "cartao_competencia, status_fatura, estouro_orcamento) values (990, 910, 101, '2027-06-01', "
               "'Fatura Cartao Teste - 06/2027', 500, 500, 120, '2027-06-30', 'Pago', '2027-06-29', true, '2027-06-01', "
               "'PAGA', false)")
    paga = sql(banco, 'select md5(t::text) as h from public.conta t where id = 990')
    # FIN-PAGAMENTO-TRAVA-1: x trava a fatura paga, desvia e para ao criar a de julho; y espera a
    # trava (nao chega a barreira) e, liberado x, ve julho ja criada e entra nela.
    x = Flask(banco, tmp_path, 'x', acao='compra', dados=compra('Compra x', parcelas=1, valor='10.00'),
              pausa='antes_do_insert')
    aguardar(tmp_path, ['x_consultou'], [x])
    y = Flask(banco, tmp_path, 'y', acao='compra', dados=compra('Compra y', parcelas=1, valor='10.00'),
              pausa='antes_do_insert')
    time.sleep(3)
    assert y.processo.poll() is None and not (tmp_path / 'y_consultou').exists()  # esperando a trava
    liberar(tmp_path, 'consultou')
    for p in (x, y):
        p.resultado()
    assert sql(banco, 'select md5(t::text) as h from public.conta t where id = 990') == paga
    assert len(faturas(banco, '2027-06-01')) == 1 and len(faturas(banco, '2027-07-01')) == 1
    assert {x['mes_fatura'] for x in sql(banco, "select mes_fatura from public.lancamento_agregado "
                                                "where descricao like 'Compra %%'")} == {date(2027, 7, 1)}


def _aplicar_migration(dsn):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(MIGRATION.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_migration_preserva_faturas_e_lancamentos_existentes(banco):
    atribuir(banco, 'PESSOAL')
    gerar(banco, previa(banco)['a_gerar'])  # faturas e compras recorrentes ja existentes
    sql(banco, 'drop index public.ux_conta_fatura_cartao_competencia')  # banco como antes da migration
    antes = (sql(banco, "select md5(string_agg(t::text, '|' order by id)) as h from public.conta t"),
             sql(banco, "select md5(string_agg(t::text, '|' order by id)) as h from public.lancamento_agregado t"))
    _aplicar_migration(banco)
    depois = (sql(banco, "select md5(string_agg(t::text, '|' order by id)) as h from public.conta t"),
              sql(banco, "select md5(string_agg(t::text, '|' order by id)) as h from public.lancamento_agregado t"))
    assert depois == antes
    assert sql(banco, "select to_regclass('public.ux_conta_fatura_cartao_competencia') is not null as ok")[0]['ok']


def test_migration_aborta_sem_alterar_nada_se_houver_duplicidade(banco):
    sql(banco, 'drop index public.ux_conta_fatura_cartao_competencia')
    for _ in range(2):
        sql(banco, "insert into public.conta (item_despesa_id, mes_referencia, descricao, valor, data_vencimento, "
                   "is_fatura_cartao, cartao_competencia) values (910, '2027-06-01', 'Duplicada', 0, '2027-06-30', "
                   "true, '2027-06-01')")
    with pytest.raises(errors.RaiseException, match='duplicada'):
        _aplicar_migration(banco)
    assert len(faturas(banco, '2027-06-01')) == 2  # nada excluido nem consolidado
    assert sql(banco, "select to_regclass('public.ux_conta_fatura_cartao_competencia') is null as ausente")[0]['ausente']


# ---------------------------------------------------------------------------
# Seguranca
# ---------------------------------------------------------------------------

def test_navegador_continua_sem_criar_faturas_nem_executar_o_motor_interno(banco):
    with pytest.raises(errors.InsufficientPrivilege):
        chamar(banco, USUARIO_A, "insert into public.conta (item_despesa_id, mes_referencia, descricao, valor, "
                                 "data_vencimento, is_fatura_cartao, cartao_competencia) values "
                                 "(910, '2027-06-01', 'x', 0, '2027-06-30', true, '2027-06-01')")
    with pytest.raises(errors.InsufficientPrivilege):
        chamar(banco, USUARIO_A, "select financeiro.gerar_mes_interno(101, '2027-03-01', 17, '[]')")
    privilegios = sql(banco, "select has_function_privilege('authenticated', "
                             "'financeiro.gerar_mes_interno(integer, date, integer, jsonb)', 'execute') as interno, "
                             "has_function_privilege('anon', 'financeiro.gerar_mes(integer, date, integer, jsonb)', "
                             "'execute') as anon")[0]
    assert privilegios == {'interno': False, 'anon': False}
    with pytest.raises(errors.RaiseException, match='sistema atual'):  # T1 continua valendo (Pessoal no Flask)
        gerar(banco, 17)
    assert ID['PESSOAL'] == 101


# ---------------------------------------------------------------------------
# Regra unica, qualquer que seja o mecanismo (Supabase, Alembic, create_all do Flask)
# ---------------------------------------------------------------------------

DEFINICAO_APROVADA = ('CREATE UNIQUE INDEX ux_conta_fatura_cartao_competencia ON public.conta USING btree '
                      '(item_despesa_id, cartao_competencia) WHERE is_fatura_cartao')


def _migration_alembic():
    import importlib.util
    caminho = next((ROOT / 'migrations' / 'versions').glob('d81f5a2b9c3e_*.py'))
    spec = importlib.util.spec_from_file_location('migration_fatura_unica_pg', caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _alembic_upgrade(dsn):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine
    engine = create_engine(dsn)
    try:
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            _migration_alembic().upgrade()
    finally:
        engine.dispose()


def _indices_da_regra(dsn):
    return sql(dsn, "select indexname, indexdef from pg_indexes where schemaname = 'public' and tablename = 'conta' "
                    "and indexdef like '%%(item_despesa_id, cartao_competencia)%%'")


def test_um_unico_indice_com_a_definicao_aprovada_e_o_alembic_nao_cria_outro(banco):
    # O cluster tem o create_all do model e a migration do Supabase aplicados.
    assert _indices_da_regra(banco) == [{'indexname': 'ux_conta_fatura_cartao_competencia',
                                         'indexdef': DEFINICAO_APROVADA}]
    assert _migration_alembic().definicao_confere(DEFINICAO_APROVADA, 'postgresql')
    _alembic_upgrade(banco)
    assert _indices_da_regra(banco) == [{'indexname': 'ux_conta_fatura_cartao_competencia',
                                         'indexdef': DEFINICAO_APROVADA}]


def test_alembic_sozinho_cria_exatamente_a_mesma_definicao(banco):
    sql(banco, 'drop index public.ux_conta_fatura_cartao_competencia')
    _alembic_upgrade(banco)
    assert _indices_da_regra(banco) == [{'indexname': 'ux_conta_fatura_cartao_competencia',
                                         'indexdef': DEFINICAO_APROVADA}]
    _aplicar_migration(banco)  # a do Supabase depois: nao cria outro
    assert len(_indices_da_regra(banco)) == 1


def test_alembic_aborta_se_o_indice_existente_tiver_outra_regra(banco):
    sql(banco, 'drop index public.ux_conta_fatura_cartao_competencia')
    sql(banco, 'create unique index ux_conta_fatura_cartao_competencia on public.conta '
               '(item_despesa_id, cartao_competencia, perfil_financeiro_id) where is_fatura_cartao')
    with pytest.raises(RuntimeError, match='outra definicao'):
        _alembic_upgrade(banco)
