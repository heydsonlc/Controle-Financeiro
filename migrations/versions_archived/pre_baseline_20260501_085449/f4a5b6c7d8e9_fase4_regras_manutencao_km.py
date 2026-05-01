"""FASE 4: regras de manutenção por km (por veículo)

Revision ID: f4a5b6c7d8e9
Revises: e1f2a3b4c5d6
Create Date: 2026-01-03

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4a5b6c7d8e9'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'veiculo_regra_manutencao_km',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('veiculo_id', sa.Integer(), nullable=False),
        sa.Column('tipo_evento', sa.String(length=50), nullable=False),
        sa.Column('intervalo_km', sa.Integer(), nullable=False),
        sa.Column('custo_estimado', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('categoria_id', sa.Integer(), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['veiculo_id'], ['veiculo.id']),
        sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id']),
    )

    op.create_index(
        'idx_regra_km_veiculo_tipo',
        'veiculo_regra_manutencao_km',
        ['veiculo_id', 'tipo_evento'],
        unique=False
    )


def downgrade():
    op.drop_index('idx_regra_km_veiculo_tipo', table_name='veiculo_regra_manutencao_km')
    op.drop_table('veiculo_regra_manutencao_km')

