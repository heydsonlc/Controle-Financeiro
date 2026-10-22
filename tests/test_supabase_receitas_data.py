"""
Testes FIN-RECEITAS-1 (ajuste de data) — data prevista de recebimento independente da competencia.

Mesmo cluster/cenario de tests/test_supabase_receitas.py. Conferem: competencia e data prevista
independentes (inclusive virada de ano), regra de datas na recorrencia sem deriva, fevereiro de
ano bissexto, registros antigos sem data (regra do dia da fonte), preservacao das datas explicitas,
concorrencia, bloqueios, ausencia de movimento, autorizacao, compatibilidade com o Flask real e a
migration Alembic em banco ficticio.
"""
import importlib.util
import os
import subprocess
import sys
import uuid
from datetime import date

import pytest

from tests.test_supabase_receitas import (
    ID,
    MES,
    PG_BIN,
    ROOT,
    TABELAS_DINHEIRO,
    USUARIO_A,
    _paralelo,
    banco,  # noqa: F401  (fixture reaproveitada)
    cluster,  # noqa: F401
    copiar,
    criar,
    edicao,
    editar,
    flask,
    orcamento,
    por_nome,
    receitas,
    rpc,
    semear,
    sql,
)
from tests.test_supabase_recorrencia import digital

psycopg2 = pytest.importorskip('psycopg2')
from psycopg2 import errors  # noqa: E402

pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

D = date
SALARIO = {'nome': 'Salario out', 'tipo': 'SALARIO_FIXO', 'valor': '5000.00'}


def datas_da_fonte(dsn, item):
    return [(str(x['mes_referencia']), str(x['data_prevista'])) for x in sql(
        dsn, 'select mes_referencia, data_prevista from public.receita_orcamento where item_receita_id = %s order by 1', (item,))]


@pytest.mark.parametrize('competencia,data,outro_mes', [
    ('2026-10-01', '2026-11-05', '2026-11-01'),   # 1. salario de outubro recebido em novembro
    ('2026-12-01', '2027-01-05', '2027-01-01'),   # 2. virada de ano
    ('2027-03-01', '2027-03-20', None),            # 3. mesmo mes
])
def test_competencia_e_data_prevista_independentes(banco, competencia, data, outro_mes):  # noqa: F811
    dsn, _ = banco
    antes = digital(dsn, tabelas=TABELAS_DINHEIRO)
    criar(dsn, {**SALARIO, 'competencia': competencia, 'data_prevista': data})
    linha = por_nome(receitas(dsn, mes=competencia))['Salario out']
    assert (linha['competencia'], linha['data_prevista'], linha['data_prevista_explicita'], linha['situacao']) == \
        (competencia, data, True, 'PREVISTA')
    if outro_mes:  # o total pertence a competencia, nao ao mes da data prevista
        assert 'Salario out' not in por_nome(receitas(dsn, mes=outro_mes))
    assert digital(dsn, tabelas=TABELAS_DINHEIRO) == antes


def test_registros_antigos_sem_data_usam_o_dia_da_fonte(banco):  # noqa: F811
    dsn, ids = banco
    assert orcamento(dsn, ids['prev_salario'])['data_prevista'] is None  # nada preenchido retroativamente
    linha = por_nome(receitas(dsn))['Salario X']
    assert (linha['data_prevista'], linha['data_prevista_explicita']) == ('2027-03-05', False)


def test_recorrente_12_competencias_com_regra_de_data_e_virada_de_ano(banco):  # noqa: F811
    dsn, _ = banco
    r = criar(dsn, {**SALARIO, 'competencia': '2026-10-01', 'data_prevista': '2026-11-05', 'recorrente': True})
    esperado = [(f'{a}-{m:02d}-01', f'{a2}-{m2:02d}-05') for a, m, a2, m2 in (
        (2026, 10, 2026, 11), (2026, 11, 2026, 12), (2026, 12, 2027, 1), (2027, 1, 2027, 2), (2027, 2, 2027, 3),
        (2027, 3, 2027, 4), (2027, 4, 2027, 5), (2027, 5, 2027, 6), (2027, 6, 2027, 7), (2027, 7, 2027, 8),
        (2027, 8, 2027, 9), (2027, 9, 2027, 10))]
    assert datas_da_fonte(dsn, r['item_receita_id']) == esperado
    assert sql(dsn, 'select dia_previsto_pagamento from public.item_receita where id = %s', (r['item_receita_id'],))[0][
        'dia_previsto_pagamento'] == 5


def test_dia_31_sem_deriva_e_fevereiro_bissexto(banco):  # noqa: F811
    dsn, _ = banco
    r = criar(dsn, {**SALARIO, 'nome': 'Dia 31', 'competencia': '2026-12-01', 'data_prevista': '2027-01-31',
                    'recorrente': True})
    datas = dict(datas_da_fonte(dsn, r['item_receita_id']))
    assert [datas['2026-12-01'], datas['2027-01-01'], datas['2027-02-01'], datas['2027-03-01']] == \
        ['2027-01-31', '2027-02-28', '2027-03-31', '2027-04-30']
    b = criar(dsn, {**SALARIO, 'nome': 'Bissexto', 'competencia': '2027-12-01', 'data_prevista': '2028-01-30',
                    'recorrente': True})
    datas = dict(datas_da_fonte(dsn, b['item_receita_id']))
    assert (datas['2028-01-01'], datas['2028-02-01']) == ('2028-02-29', '2028-03-30')


def test_excecao_de_data_nao_desloca_as_competencias_seguintes(banco):  # noqa: F811
    dsn, _ = banco
    r = criar(dsn, {**SALARIO, 'competencia': '2026-10-01', 'data_prevista': '2026-11-05', 'recorrente': True})
    novembro = r['previsoes'][1]
    editar(dsn, novembro, {'data_prevista': '2026-12-20'})
    datas = dict(datas_da_fonte(dsn, r['item_receita_id']))
    assert (datas['2026-10-01'], datas['2026-11-01'], datas['2026-12-01']) == ('2026-11-05', '2026-12-20', '2027-01-05')
    editar(dsn, novembro, {'data_prevista': None})  # volta a regra do dia da fonte
    linha = por_nome(receitas(dsn, mes='2026-11-01'))['Salario out']
    assert (linha['data_prevista'], linha['data_prevista_explicita']) == ('2026-11-05', False)


def test_editar_a_fonte_preserva_as_datas_explicitas(banco):  # noqa: F811
    dsn, ids = banco
    r = criar(dsn, {**SALARIO, 'competencia': '2026-10-01', 'data_prevista': '2026-11-05', 'recorrente': True})
    antes = datas_da_fonte(dsn, r['item_receita_id'])
    e = edicao(dsn, r['previsoes'][0])
    rpc(dsn, 'editar_fonte_receita', ID['PESSOAL'], r['item_receita_id'], e['versao_fonte'], {'dia_previsto': 20})
    assert datas_da_fonte(dsn, r['item_receita_id']) == antes
    # Registro antigo (sem data) acompanha o dia da fonte, como sempre.
    e2 = edicao(dsn, ids['prev_aula'])
    rpc(dsn, 'editar_fonte_receita', ID['PESSOAL'], ids['aula'], e2['versao_fonte'], {'dia_previsto': 25})
    assert por_nome(receitas(dsn))['Aulas']['data_prevista'] == '2027-03-25'


@pytest.mark.parametrize('dados,mensagem', [
    ({'competencia': '2026-10-01', 'data_prevista': '2028-01-05'}, '12 meses'),
    ({'competencia': '2026-10-01', 'data_prevista': '2025-09-30'}, '12 meses'),
    ({'competencia': '2026-10-01', 'data_prevista': '2026-02-30'}, 'Data prevista invalida'),
])
def test_data_prevista_invalida_recusada(banco, dados, mensagem):  # noqa: F811
    dsn, _ = banco
    with pytest.raises(errors.InvalidParameterValue, match=mensagem):
        criar(dsn, {**SALARIO, **dados})


def test_edicoes_simultaneas_da_data_so_uma_vale(banco):  # noqa: F811
    dsn, _ = banco
    r = criar(dsn, {**SALARIO, 'competencia': '2026-10-01', 'data_prevista': '2026-11-05'})
    versao = edicao(dsn, r['previsoes'][0])['versao']
    resultados = _paralelo([lambda d=d: editar(dsn, r['previsoes'][0], {'data_prevista': d}, versao=versao)
                            for d in ('2026-11-06', '2026-11-07')])
    assert sorted(x[0] for x in resultados) == ['erro', 'ok']
    chave = str(uuid.uuid4())
    paralelos = _paralelo([lambda: criar(dsn, {**SALARIO, 'nome': 'Paralela data', 'competencia': '2026-10-01',
                                               'data_prevista': '2026-11-05'}, chave=chave) for _ in range(3)])
    assert [x[0] for x in paralelos] == ['ok'] * 3
    assert sql(dsn, "select count(*) as n from public.item_receita where nome = 'Paralela data'")[0]['n'] == 1


def test_previsao_recebida_nao_muda_de_data_e_leitor_nao_edita(banco):  # noqa: F811
    dsn, ids = banco
    with pytest.raises(errors.RaiseException, match='Operacao bloqueada'):
        editar(dsn, ids['prev_salario'], {'data_prevista': '2027-03-10'})
    e = edicao(dsn, ids['prev_consultoria'], 'EMPRESA')
    with pytest.raises(errors.InsufficientPrivilege):
        editar(dsn, ids['prev_consultoria'], {'data_prevista': '2027-03-20'}, 'EMPRESA', versao=e['versao'])
    assert orcamento(dsn, ids['prev_consultoria'])['data_prevista'] is None


def test_flask_atualizando_a_previsao_preserva_a_data_explicita(cluster):  # noqa: F811
    dsn = copiar(cluster)
    ids = semear(dsn)
    sql(dsn, "update public.receita_orcamento set data_prevista = '2027-04-05' where id = %s", (ids['prev_aula'],))
    saida = flask(dsn, [['post', '/api/receitas/orcamento', {'item_receita_id': ids['aula'], 'ano_mes': MES,
                                                              'valor_previsto': 650, 'periodicidade': 'UNICA',
                                                              'observacoes': 'Atualizado no Flask'}],
                        ['get', '/api/receitas/orcamento?ano=2027', None]])
    assert [x['status'] for x in saida] == [201, 200]
    o = orcamento(dsn, ids['prev_aula'])
    assert (float(o['valor_esperado']), o['observacoes'], o['data_prevista']) == (650.0, 'Atualizado no Flask', D(2027, 4, 5))


def _migration_alembic():
    caminho = next((ROOT / 'migrations' / 'versions').glob('e3b7c9d1a2f4_*.py'))
    spec = importlib.util.spec_from_file_location('migration_data_prevista', caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_migration_alembic_em_banco_ficticio_postgres(cluster):  # noqa: F811
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    dsn = copiar(cluster)
    sql(dsn, 'alter table public.receita_orcamento drop column data_prevista')
    engine = create_engine(dsn)
    try:
        for _ in range(2):  # idempotente
            with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
                _migration_alembic().upgrade()
    finally:
        engine.dispose()
    assert sql(dsn, "select data_type, is_nullable from information_schema.columns where table_name = 'receita_orcamento' "
                    "and column_name = 'data_prevista'") == [{'data_type': 'date', 'is_nullable': 'YES'}]


_SCRIPT_SQLITE = r'''
import importlib.util, sys
from datetime import date
from flask import Flask
from sqlalchemy import text
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from backend.models import db, ReceitaOrcamento
from backend.services.receita_service import ReceitaService
app = Flask(__name__)
app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///' + sys.argv[1], SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)
with app.app_context():
    db.create_all()
    db.session.execute(text('alter table receita_orcamento drop column data_prevista'))  # banco antigo, sem a coluna
    db.session.commit()
    item = ReceitaService.criar_item_receita({'nome': 'Salario', 'tipo': 'SALARIO_FIXO', 'valor_base_mensal': 5000})
    ReceitaService.gerar_orcamento_recorrente(item.id, '2026-10-01', '2027-09-01', 5000)
    ReceitaService.criar_ou_atualizar_orcamento_mensal(item.id, '2026-10-01', 5100)
    assert len(ReceitaService.obter_orcamentos_por_ano(2027)) == 9
    print('SEM_COLUNA_OK', len(ReceitaOrcamento.query.all()))
    spec = importlib.util.spec_from_file_location('m', sys.argv[2]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    with db.engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        m.upgrade(); m.upgrade()
    db.session.execute(text("update receita_orcamento set data_prevista = '2026-11-05' where mes_referencia = '2026-10-01'"))
    db.session.commit()
    ReceitaService.criar_ou_atualizar_orcamento_mensal(item.id, '2026-10-01', 5200, observacoes='ajuste')
    print('DATA_PRESERVADA', db.session.execute(text("select data_prevista from receita_orcamento where mes_referencia = '2026-10-01'")).scalar())
'''


def test_flask_em_sqlite_sem_a_coluna_e_migration_alembic(tmp_path):
    caminho = next((ROOT / 'migrations' / 'versions').glob('e3b7c9d1a2f4_*.py'))
    r = subprocess.run([sys.executable, '-c', _SCRIPT_SQLITE, str(tmp_path / 'ficticio.db'), str(caminho)], cwd=ROOT,
                       env={**os.environ, 'APP_ENV': 'local'}, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    assert 'SEM_COLUNA_OK 12' in r.stdout and 'DATA_PRESERVADA 2026-11-05' in r.stdout
