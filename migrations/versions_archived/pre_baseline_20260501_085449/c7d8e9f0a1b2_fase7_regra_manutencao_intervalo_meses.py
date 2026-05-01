"""FASE 7: intervalo temporal opcional nas regras de manutenÇõÇœo

Revision ID: c7d8e9f0a1b2
Revises: b2c3d4e5f6a7
Create Date: 2026-01-07

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d8e9f0a1b2'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'veiculo_regra_manutencao_km',
        sa.Column('meses_intervalo', sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column('veiculo_regra_manutencao_km', 'meses_intervalo')

