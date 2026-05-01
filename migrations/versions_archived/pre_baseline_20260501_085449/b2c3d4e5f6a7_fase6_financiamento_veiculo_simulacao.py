"""FASE 6: financiamento projetivo do veículo (simulação)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-03

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'veiculo_financiamento',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('veiculo_id', sa.Integer(), nullable=False),
        sa.Column('valor_bem', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('entrada', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('valor_financiado', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('numero_parcelas', sa.Integer(), nullable=False),
        sa.Column('taxa_juros_mensal', sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column('indexador_tipo', sa.String(length=20), nullable=True),
        sa.Column('iof_percentual', sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column('iof_valor', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('categoria_id', sa.Integer(), nullable=True),
        sa.Column('custo_total_financiamento', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['veiculo_id'], ['veiculo.id']),
        sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id']),
        sa.UniqueConstraint('veiculo_id'),
    )


def downgrade():
    op.drop_table('veiculo_financiamento')

