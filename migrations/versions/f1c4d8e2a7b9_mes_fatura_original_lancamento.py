"""Competencia original da compra desviada de fatura paga

Revision ID: f1c4d8e2a7b9
Revises: e3b7c9d1a2f4
Create Date: 2026-10-22 15:00:00

FIN-FATURA-INTEGRIDADE-1: lancamento_agregado ganha `mes_fatura_original` (DATE, nula). Fatura paga
e imutavel quanto as compras: uma compra (nova, recorrente ou importada) cuja fatura ja esta paga vai
para a proxima fatura nao paga, e esta coluna guarda a competencia em que ela entraria. NULL = compra
nao desviada; nada e preenchido retroativamente e nenhuma compra ou fatura existente e alterada.
A mesma coluna e criada pela migration do Supabase 20261029090000_financeiro_fatura_integridade
(IF NOT EXISTS: a que rodar primeiro cria). O model a mapeia como deferred, com server_default NULL e
eager_defaults=False, e o servico so a grava quando ela existe: o Flask funciona num banco que ainda
nao rodou esta migration (o desvio de uma importacao e recusado ali, para nao perder a competencia
original usada na deduplicacao).
"""
from alembic import op


revision = 'f1c4d8e2a7b9'
down_revision = 'e3b7c9d1a2f4'
branch_labels = None
depends_on = None


def _tem_coluna(conn):
    if conn.dialect.name == 'sqlite':
        return any(r[1] == 'mes_fatura_original'
                   for r in conn.exec_driver_sql("PRAGMA table_info('lancamento_agregado')"))
    return conn.exec_driver_sql(
        "select count(*) from information_schema.columns where table_schema = current_schema() "
        "and table_name = 'lancamento_agregado' and column_name = 'mes_fatura_original'"
    ).scalar() == 1


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name not in ('sqlite', 'postgresql'):
        raise RuntimeError(f'FIN-FATURA-INTEGRIDADE-1: dialeto nao suportado ({conn.dialect.name})')
    if not _tem_coluna(conn):
        conn.exec_driver_sql('alter table lancamento_agregado add column mes_fatura_original date')


def downgrade():
    conn = op.get_bind()
    if _tem_coluna(conn):
        conn.exec_driver_sql('alter table lancamento_agregado drop column mes_fatura_original')
