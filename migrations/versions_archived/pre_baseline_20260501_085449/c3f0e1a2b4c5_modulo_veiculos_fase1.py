"""Modulo veiculos (fase 1): tabelas veiculo e despesa_prevista

Revision ID: c3f0e1a2b4c5
Revises: b60e2da6e02c
Create Date: 2026-01-03

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f0e1a2b4c5'
down_revision = 'b60e2da6e02c'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'veiculo',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('combustivel', sa.String(length=20), nullable=False),
        sa.Column('autonomia_km_l', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='SIMULADO'),
        sa.Column('data_inicio', sa.Date(), nullable=True),
        sa.Column('categoria_combustivel_id', sa.Integer(), nullable=True),
        sa.Column('combustivel_valor_mensal', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('ipva_categoria_id', sa.Integer(), nullable=True),
        sa.Column('ipva_mes', sa.Integer(), nullable=True),
        sa.Column('ipva_valor', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('seguro_categoria_id', sa.Integer(), nullable=True),
        sa.Column('seguro_mes', sa.Integer(), nullable=True),
        sa.Column('seguro_valor', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('licenciamento_categoria_id', sa.Integer(), nullable=True),
        sa.Column('licenciamento_mes', sa.Integer(), nullable=True),
        sa.Column('licenciamento_valor', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['categoria_combustivel_id'], ['categoria.id']),
        sa.ForeignKeyConstraint(['ipva_categoria_id'], ['categoria.id']),
        sa.ForeignKeyConstraint(['seguro_categoria_id'], ['categoria.id']),
        sa.ForeignKeyConstraint(['licenciamento_categoria_id'], ['categoria.id']),
    )

    op.create_table(
        'despesa_prevista',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('origem_tipo', sa.String(length=20), nullable=False),
        sa.Column('origem_id', sa.Integer(), nullable=False),
        sa.Column('categoria_id', sa.Integer(), nullable=False),
        sa.Column('data_prevista', sa.Date(), nullable=False),
        sa.Column('valor_previsto', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PREVISTA'),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id']),
    )

    op.create_index(
        'idx_desp_prev_origem_data',
        'despesa_prevista',
        ['origem_tipo', 'origem_id', 'data_prevista'],
        unique=False
    )


def downgrade():
    op.drop_index('idx_desp_prev_origem_data', table_name='despesa_prevista')
    op.drop_table('despesa_prevista')
    op.drop_table('veiculo')

