"""adiciona ajuste de saldo devedor real

Revision ID: e7f8a9b0c1d2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'e7f8a9b0c1d2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(table_name):
    return table_name in _insp().get_table_names()


def _index_exists(table_name, index_name):
    if not _table_exists(table_name):
        return False
    return index_name in {index['name'] for index in _insp().get_indexes(table_name)}


def upgrade():
    if not _table_exists('financiamento_ajuste_saldo'):
        op.create_table(
            'financiamento_ajuste_saldo',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('perfil_financeiro_id', sa.Integer(), nullable=True),
            sa.Column('financiamento_id', sa.Integer(), nullable=False),
            sa.Column('parcela_referencia_id', sa.Integer(), nullable=True),
            sa.Column('numero_parcela', sa.Integer(), nullable=False),
            sa.Column('data_referencia', sa.Date(), nullable=False),
            sa.Column('saldo_devedor_anterior', sa.Numeric(12, 2), nullable=False),
            sa.Column('saldo_devedor_real', sa.Numeric(12, 2), nullable=False),
            sa.Column('diferenca', sa.Numeric(12, 2), nullable=False),
            sa.Column('tipo_ajuste', sa.String(length=40), nullable=True, server_default='ajuste_saldo_real'),
            sa.Column('observacao', sa.Text(), nullable=True),
            sa.Column('parcelas_recalculadas', sa.Integer(), nullable=True, server_default='0'),
            sa.Column('criado_em', sa.DateTime(), nullable=True),
            sa.Column('atualizado_em', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['financiamento_id'], ['financiamento.id']),
            sa.ForeignKeyConstraint(['parcela_referencia_id'], ['financiamento_parcela.id']),
            sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if _table_exists('financiamento_ajuste_saldo'):
        if not _index_exists('financiamento_ajuste_saldo', 'idx_ajuste_saldo_financ'):
            op.create_index('idx_ajuste_saldo_financ', 'financiamento_ajuste_saldo', ['financiamento_id'])
        if not _index_exists('financiamento_ajuste_saldo', 'idx_ajuste_saldo_parcela_ref'):
            op.create_index('idx_ajuste_saldo_parcela_ref', 'financiamento_ajuste_saldo', ['parcela_referencia_id'])
        if not _index_exists('financiamento_ajuste_saldo', 'idx_ajuste_saldo_perfil_data'):
            op.create_index('idx_ajuste_saldo_perfil_data', 'financiamento_ajuste_saldo', ['perfil_financeiro_id', 'data_referencia'])


def downgrade():
    if _table_exists('financiamento_ajuste_saldo'):
        for index_name in [
            'idx_ajuste_saldo_perfil_data',
            'idx_ajuste_saldo_parcela_ref',
            'idx_ajuste_saldo_financ',
        ]:
            if _index_exists('financiamento_ajuste_saldo', index_name):
                op.drop_index(index_name, table_name='financiamento_ajuste_saldo')
        op.drop_table('financiamento_ajuste_saldo')
