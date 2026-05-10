"""adiciona seguro estimado dfi mip para financiamento

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(table_name):
    return table_name in _insp().get_table_names()


def _columns(table_name):
    if not _table_exists(table_name):
        return set()
    return {column['name'] for column in _insp().get_columns(table_name)}


def _column_exists(table_name, column_name):
    return column_name in _columns(table_name)


def _index_exists(table_name, index_name):
    if not _table_exists(table_name):
        return False
    return index_name in {index['name'] for index in _insp().get_indexes(table_name)}


def upgrade():
    bind = op.get_bind()

    if _table_exists('financiamento'):
        if not _column_exists('financiamento', 'seguro_modo'):
            op.add_column(
                'financiamento',
                sa.Column('seguro_modo', sa.String(length=30), nullable=True, server_default='fixo'),
            )
        if not _column_exists('financiamento', 'seguro_fator_dfi'):
            op.add_column(
                'financiamento',
                sa.Column('seguro_fator_dfi', sa.Numeric(10, 5), nullable=True),
            )
        if not _column_exists('financiamento', 'seguro_data_nascimento_titular'):
            op.add_column(
                'financiamento',
                sa.Column('seguro_data_nascimento_titular', sa.Date(), nullable=True),
            )
        if not _column_exists('financiamento', 'seguro_mes_reajuste_idade'):
            op.add_column(
                'financiamento',
                sa.Column('seguro_mes_reajuste_idade', sa.Integer(), nullable=True, server_default='2'),
            )

        bind.execute(sa.text("UPDATE financiamento SET seguro_modo = 'fixo' WHERE seguro_modo IS NULL"))
        bind.execute(sa.text("UPDATE financiamento SET seguro_mes_reajuste_idade = 2 WHERE seguro_mes_reajuste_idade IS NULL"))

    if not _table_exists('financiamento_seguro_faixa_mip'):
        op.create_table(
            'financiamento_seguro_faixa_mip',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('perfil_financeiro_id', sa.Integer(), nullable=True),
            sa.Column('financiamento_id', sa.Integer(), nullable=False),
            sa.Column('idade_inicio', sa.Integer(), nullable=False),
            sa.Column('idade_fim', sa.Integer(), nullable=False),
            sa.Column('fator_mip', sa.Numeric(10, 5), nullable=False),
            sa.Column('vigencia_inicio', sa.Date(), nullable=True),
            sa.Column('vigencia_fim', sa.Date(), nullable=True),
            sa.Column('ativo', sa.Boolean(), nullable=True, server_default=sa.true()),
            sa.Column('criado_em', sa.DateTime(), nullable=True),
            sa.Column('atualizado_em', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['financiamento_id'], ['financiamento.id']),
            sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if _table_exists('financiamento_seguro_faixa_mip'):
        if not _index_exists('financiamento_seguro_faixa_mip', 'idx_seguro_mip_financ'):
            op.create_index('idx_seguro_mip_financ', 'financiamento_seguro_faixa_mip', ['financiamento_id'])
        if not _index_exists('financiamento_seguro_faixa_mip', 'idx_seguro_mip_idade'):
            op.create_index('idx_seguro_mip_idade', 'financiamento_seguro_faixa_mip', ['idade_inicio', 'idade_fim'])
        if not _index_exists('financiamento_seguro_faixa_mip', 'idx_seguro_mip_perfil_ativo'):
            op.create_index('idx_seguro_mip_perfil_ativo', 'financiamento_seguro_faixa_mip', ['perfil_financeiro_id', 'ativo'])


def downgrade():
    if _table_exists('financiamento_seguro_faixa_mip'):
        for index_name in [
            'idx_seguro_mip_perfil_ativo',
            'idx_seguro_mip_idade',
            'idx_seguro_mip_financ',
        ]:
            if _index_exists('financiamento_seguro_faixa_mip', index_name):
                op.drop_index(index_name, table_name='financiamento_seguro_faixa_mip')
        op.drop_table('financiamento_seguro_faixa_mip')

    if _table_exists('financiamento'):
        for column_name in [
            'seguro_mes_reajuste_idade',
            'seguro_data_nascimento_titular',
            'seguro_fator_dfi',
            'seguro_modo',
        ]:
            if _column_exists('financiamento', column_name):
                op.drop_column('financiamento', column_name)
