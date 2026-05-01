"""Add cartao_id to lancamento_agregado and make item_agregado_id nullable

Revision ID: add_cartao_id_lanc
Revises:
Create Date: 2025-01-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_cartao_id_lanc'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Adicionar coluna cartao_id (temporariamente nullable)
    op.add_column('lancamento_agregado', sa.Column('cartao_id', sa.Integer(), nullable=True))

    # Preencher cartao_id baseado em item_agregado_id
    op.execute("""
        UPDATE lancamento_agregado la
        SET cartao_id = (
            SELECT ia.item_despesa_id
            FROM item_agregado ia
            WHERE ia.id = la.item_agregado_id
        )
    """)

    # Tornar cartao_id NOT NULL
    op.alter_column('lancamento_agregado', 'cartao_id', nullable=False)

    # Criar foreign key para cartao_id
    op.create_foreign_key('fk_lancamento_agregado_cartao', 'lancamento_agregado', 'item_despesa', ['cartao_id'], ['id'])

    # Tornar item_agregado_id nullable
    op.alter_column('lancamento_agregado', 'item_agregado_id', nullable=True)


def downgrade():
    # Reverter item_agregado_id para NOT NULL
    op.alter_column('lancamento_agregado', 'item_agregado_id', nullable=False)

    # Remover foreign key de cartao_id
    op.drop_constraint('fk_lancamento_agregado_cartao', 'lancamento_agregado', type_='foreignkey')

    # Remover coluna cartao_id
    op.drop_column('lancamento_agregado', 'cartao_id')
