"""add lastro financeiro pendencia

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-05 13:20:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(table_name):
    return table_name in _inspector().get_table_names()


def _index_exists(table_name, index_name):
    if not _table_exists(table_name):
        return False
    return index_name in {index['name'] for index in _inspector().get_indexes(table_name)}


def _create_index(table_name, index_name, columns):
    if _table_exists(table_name) and not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade():
    if not _table_exists('lastro_financeiro_pendencia'):
        op.create_table(
            'lastro_financeiro_pendencia',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('perfil_financeiro_id', sa.Integer(), nullable=False),
            sa.Column('tipo_entidade', sa.String(length=40), nullable=False),
            sa.Column('entidade_id', sa.Integer(), nullable=False),
            sa.Column('status_lastro', sa.String(length=40), nullable=False, server_default='PENDENTE'),
            sa.Column('natureza', sa.String(length=50), nullable=False, server_default='OUTRO'),
            sa.Column('observacoes', sa.Text(), nullable=True),
            sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.alter_column('lastro_financeiro_pendencia', 'status_lastro', server_default=None)
        op.alter_column('lastro_financeiro_pendencia', 'natureza', server_default=None)
        op.alter_column('lastro_financeiro_pendencia', 'ativo', server_default=None)

    _create_index('lastro_financeiro_pendencia', 'ix_lastro_pendencia_perfil_status', ['perfil_financeiro_id', 'status_lastro'])
    _create_index('lastro_financeiro_pendencia', 'ix_lastro_pendencia_entidade', ['perfil_financeiro_id', 'tipo_entidade', 'entidade_id'])


def downgrade():
    if _index_exists('lastro_financeiro_pendencia', 'ix_lastro_pendencia_entidade'):
        op.drop_index('ix_lastro_pendencia_entidade', table_name='lastro_financeiro_pendencia')
    if _index_exists('lastro_financeiro_pendencia', 'ix_lastro_pendencia_perfil_status'):
        op.drop_index('ix_lastro_pendencia_perfil_status', table_name='lastro_financeiro_pendencia')
    if _table_exists('lastro_financeiro_pendencia'):
        op.drop_table('lastro_financeiro_pendencia')
