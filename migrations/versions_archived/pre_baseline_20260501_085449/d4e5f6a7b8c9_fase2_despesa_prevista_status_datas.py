"""FASE 2: status e datas imutáveis em despesa_prevista

Revision ID: d4e5f6a7b8c9
Revises: c3f0e1a2b4c5
Create Date: 2026-01-03

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3f0e1a2b4c5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('despesa_prevista', schema=None) as batch_op:
        batch_op.add_column(sa.Column('data_original_prevista', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('data_atual_prevista', sa.Date(), nullable=True))

    conn = op.get_bind()
    # Popular valores iniciais (data_original_prevista == data_atual_prevista == data_prevista)
    conn.execute(sa.text("""
        UPDATE despesa_prevista
        SET data_original_prevista = COALESCE(data_original_prevista, data_prevista),
            data_atual_prevista = COALESCE(data_atual_prevista, data_prevista)
    """))

    # Garantir status default PREVISTA para registros existentes (se houver NULL)
    conn.execute(sa.text("""
        UPDATE despesa_prevista
        SET status = 'PREVISTA'
        WHERE status IS NULL
    """))

    with op.batch_alter_table('despesa_prevista', schema=None) as batch_op:
        batch_op.alter_column('data_original_prevista', existing_type=sa.Date(), nullable=False)
        batch_op.alter_column('data_atual_prevista', existing_type=sa.Date(), nullable=False)


def downgrade():
    with op.batch_alter_table('despesa_prevista', schema=None) as batch_op:
        batch_op.drop_column('data_atual_prevista')
        batch_op.drop_column('data_original_prevista')

