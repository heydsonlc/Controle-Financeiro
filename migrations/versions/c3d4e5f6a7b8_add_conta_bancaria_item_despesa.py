"""add conta bancaria to item despesa

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-07 00:00:00.000000

Adiciona vinculo opcional de Conta Bancaria em ItemDespesa para recorrencias
com meio de pagamento debito_automatico. A coluna fica nullable para preservar
recorrencias existentes e demais meios de pagamento.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c4d5e6f7a8b9'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def _table_exists(insp, table):
    return table in insp.get_table_names()


def _column_exists(insp, table, column):
    if not _table_exists(insp, table):
        return False
    return column in {c['name'] for c in insp.get_columns(table)}


def _index_exists(insp, table, index_name):
    if not _table_exists(insp, table):
        return False
    return index_name in {idx['name'] for idx in insp.get_indexes(table)}


def _fk_exists(insp, table, fk_name):
    if not _table_exists(insp, table):
        return False
    return fk_name in {fk['name'] for fk in insp.get_foreign_keys(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not _table_exists(insp, 'item_despesa'):
        return

    with op.batch_alter_table('item_despesa') as batch_op:
        if not _column_exists(insp, 'item_despesa', 'conta_bancaria_id'):
            batch_op.add_column(sa.Column('conta_bancaria_id', sa.Integer(), nullable=True))

    insp = sa.inspect(bind)
    if not _index_exists(insp, 'item_despesa', 'ix_item_despesa_conta_bancaria_id'):
        op.create_index(
            'ix_item_despesa_conta_bancaria_id',
            'item_despesa',
            ['conta_bancaria_id'],
            unique=False,
        )

    insp = sa.inspect(bind)
    if _table_exists(insp, 'conta_bancaria') and not _fk_exists(
        insp, 'item_despesa', 'fk_item_despesa_conta_bancaria'
    ):
        with op.batch_alter_table('item_despesa') as batch_op:
            batch_op.create_foreign_key(
                'fk_item_despesa_conta_bancaria',
                'conta_bancaria',
                ['conta_bancaria_id'],
                ['id'],
            )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not _table_exists(insp, 'item_despesa'):
        return

    if _fk_exists(insp, 'item_despesa', 'fk_item_despesa_conta_bancaria'):
        with op.batch_alter_table('item_despesa') as batch_op:
            batch_op.drop_constraint('fk_item_despesa_conta_bancaria', type_='foreignkey')

    insp = sa.inspect(bind)
    if _index_exists(insp, 'item_despesa', 'ix_item_despesa_conta_bancaria_id'):
        op.drop_index('ix_item_despesa_conta_bancaria_id', table_name='item_despesa')

    insp = sa.inspect(bind)
    if _column_exists(insp, 'item_despesa', 'conta_bancaria_id'):
        with op.batch_alter_table('item_despesa') as batch_op:
            batch_op.drop_column('conta_bancaria_id')
