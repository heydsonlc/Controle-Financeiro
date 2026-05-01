"""FASE 3: sensor passivo de uso (km estimado via consumo)

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-01-03

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('veiculo', schema=None) as batch_op:
        batch_op.add_column(sa.Column('preco_medio_combustivel', sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.add_column(sa.Column('km_estimado_acumulado', sa.Numeric(precision=12, scale=2), nullable=True))
        batch_op.add_column(sa.Column('km_estimado_ultimo_calculo_em', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('km_estimado_ultimo_despesa_prevista_id', sa.Integer(), nullable=True))

    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE veiculo
        SET km_estimado_acumulado = COALESCE(km_estimado_acumulado, 0)
    """))

    with op.batch_alter_table('veiculo', schema=None) as batch_op:
        batch_op.alter_column('km_estimado_acumulado', existing_type=sa.Numeric(precision=12, scale=2), nullable=False)


def downgrade():
    with op.batch_alter_table('veiculo', schema=None) as batch_op:
        batch_op.drop_column('km_estimado_ultimo_despesa_prevista_id')
        batch_op.drop_column('km_estimado_ultimo_calculo_em')
        batch_op.drop_column('km_estimado_acumulado')
        batch_op.drop_column('preco_medio_combustivel')

