"""FASE 5: ciclo de manutenção e log de ação (cascata consciente)

Revision ID: a1b2c3d4e5f6
Revises: f4a5b6c7d8e9
Create Date: 2026-01-03

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'veiculo_ciclo_manutencao',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('veiculo_id', sa.Integer(), nullable=False),
        sa.Column('tipo_evento', sa.String(length=50), nullable=False),
        sa.Column('regra_id', sa.Integer(), nullable=False),
        sa.Column('intervalo_km', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['veiculo_id'], ['veiculo.id']),
        sa.ForeignKeyConstraint(['regra_id'], ['veiculo_regra_manutencao_km.id']),
    )
    op.create_index('idx_ciclo_veiculo_tipo', 'veiculo_ciclo_manutencao', ['veiculo_id', 'tipo_evento'], unique=False)

    op.create_table(
        'despesa_prevista_acao_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('despesa_prevista_id', sa.Integer(), nullable=False),
        sa.Column('acao', sa.String(length=30), nullable=False),
        sa.Column('ajustar_ciclo', sa.Boolean(), nullable=True),
        sa.Column('despesa_prevista_criada_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['despesa_prevista_id'], ['despesa_prevista.id']),
        sa.ForeignKeyConstraint(['despesa_prevista_criada_id'], ['despesa_prevista.id']),
    )


def downgrade():
    op.drop_table('despesa_prevista_acao_log')
    op.drop_index('idx_ciclo_veiculo_tipo', table_name='veiculo_ciclo_manutencao')
    op.drop_table('veiculo_ciclo_manutencao')

