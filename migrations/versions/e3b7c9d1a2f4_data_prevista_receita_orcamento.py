"""Data prevista de recebimento na previsao de receita (independente da competencia)

Revision ID: e3b7c9d1a2f4
Revises: d81f5a2b9c3e
Create Date: 2026-10-22 09:00:00

FIN-RECEITAS-1: receita_orcamento ganha `data_prevista` (DATE, nula). A competencia
(`mes_referencia`) continua sendo o mes do orcamento; a data prevista diz quando se espera
receber (ex.: competencia 10/2026, prevista 05/11/2026). NULL mantem a regra antiga (dia
previsto da fonte no mes da competencia): nada e preenchido retroativamente, nenhum valor,
competencia ou recebimento e alterado. A mesma coluna e criada pela migration do Supabase
20261027090000_financeiro_receitas (IF NOT EXISTS: a que rodar primeiro cria).
O model a mapeia como deferred, com server_default NULL e eager_defaults=False, para que o
Flask funcione tambem num banco que ainda nao rodou esta migration.
"""
from alembic import op


revision = 'e3b7c9d1a2f4'
down_revision = 'd81f5a2b9c3e'
branch_labels = None
depends_on = None


def _tem_coluna(conn):
    if conn.dialect.name == 'sqlite':
        return any(r[1] == 'data_prevista' for r in conn.exec_driver_sql("PRAGMA table_info('receita_orcamento')"))
    return conn.exec_driver_sql(
        "select count(*) from information_schema.columns where table_schema = current_schema() "
        "and table_name = 'receita_orcamento' and column_name = 'data_prevista'"
    ).scalar() == 1


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name not in ('sqlite', 'postgresql'):
        raise RuntimeError(f'FIN-RECEITAS-1: dialeto nao suportado ({conn.dialect.name})')
    if not _tem_coluna(conn):
        conn.exec_driver_sql('alter table receita_orcamento add column data_prevista date')


def downgrade():
    conn = op.get_bind()
    if _tem_coluna(conn):
        conn.exec_driver_sql('alter table receita_orcamento drop column data_prevista')
