"""
FIN-FATURA-INTEGRIDADE-1 — migration Alembic f1c4d8e2a7b9 (lancamento_agregado.mes_fatura_original),
testada SO em bancos ficticios: SQLite temporario e copia PostgreSQL descartavel. Nunca o gastos.db.
"""
import importlib.util
import sqlite3

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

from tests.test_supabase_recorrencia import PG_BIN, ROOT, cluster, copiar, sql  # noqa: F401

MIGRATION = ROOT / 'migrations' / 'versions' / 'f1c4d8e2a7b9_mes_fatura_original_lancamento.py'


def _modulo():
    spec = importlib.util.spec_from_file_location('mig_f1c4', MIGRATION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _rodar(url, funcao):
    motor = create_engine(url)
    modulo = _modulo()
    with motor.begin() as conn:
        contexto = MigrationContext.configure(conn)
        with Operations.context(contexto):
            getattr(modulo, funcao)()
    motor.dispose()


def test_revisao_encadeada():
    modulo = _modulo()
    assert (modulo.revision, modulo.down_revision) == ('f1c4d8e2a7b9', 'e3b7c9d1a2f4')


def test_sqlite_ficticio_sobe_idempotente_preserva_dados_e_desce(tmp_path):
    caminho = tmp_path / 'ficticio.db'
    with sqlite3.connect(caminho) as conn:
        conn.execute('create table lancamento_agregado (id integer primary key, descricao text, mes_fatura date)')
        conn.execute("insert into lancamento_agregado values (1, 'Compra antiga', '2026-05-01')")
    url = f'sqlite:///{caminho.as_posix()}'
    _rodar(url, 'upgrade')
    _rodar(url, 'upgrade')  # idempotente
    with sqlite3.connect(caminho) as conn:
        assert [r[1] for r in conn.execute("pragma table_info('lancamento_agregado')")][-1] == 'mes_fatura_original'
        assert conn.execute('select id, descricao, mes_fatura, mes_fatura_original from lancamento_agregado').fetchall() == \
            [(1, 'Compra antiga', '2026-05-01', None)]  # nada preenchido retroativamente
    _rodar(url, 'downgrade')
    with sqlite3.connect(caminho) as conn:
        assert 'mes_fatura_original' not in [r[1] for r in conn.execute("pragma table_info('lancamento_agregado')")]


@pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL nao encontrados')
def test_postgresql_ficticio_sobe_idempotente_preserva_dados_e_desce(cluster):  # noqa: F811
    dsn = copiar(cluster)
    sql(dsn, 'alter table public.lancamento_agregado drop column mes_fatura_original')  # como antes das migrations
    antes = sql(dsn, "select md5(string_agg(t::text, '|' order by id)) as h from public.lancamento_agregado t")
    url = dsn.replace('postgresql://', 'postgresql+psycopg2://')
    _rodar(url, 'upgrade')
    _rodar(url, 'upgrade')
    assert sql(dsn, 'select count(*) as n from public.lancamento_agregado where mes_fatura_original is not null')[0]['n'] == 0
    _rodar(url, 'downgrade')
    assert sql(dsn, "select md5(string_agg(t::text, '|' order by id)) as h from public.lancamento_agregado t") == antes
