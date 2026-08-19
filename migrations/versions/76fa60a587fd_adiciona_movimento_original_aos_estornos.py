"""Adiciona movimento original aos estornos

Revision ID: 76fa60a587fd
Revises: 9b8a09ecc52f
Create Date: 2026-08-19 19:45:10.923008

MOV-REF-1: referência explícita entre o movimento de estorno e o movimento
financeiro original que ele compensa. Campo nullable — estornos anteriores a
esta migration continuam válidos, localizados pela lógica indireta existente
(origem/conta_id/receita_realizada_id/financiamento_parcela_id/tipo).

Escopo estritamente limitado a esta coluna/índice/FK. O autogenerate do
Alembic detectou drift pré-existente e não relacionado (constraints de check
em mobilidade_assinatura/mobilidade_cenario_ativo, índice
idx_movimento_financiamento_parcela) que foi removido manualmente deste
arquivo — fora do escopo do MOV-REF-1.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '76fa60a587fd'
down_revision = '9b8a09ecc52f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('movimento_financeiro', schema=None) as batch_op:
        batch_op.add_column(sa.Column('movimento_original_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_movimento_financeiro_movimento_original_id', ['movimento_original_id'], unique=False)
        batch_op.create_foreign_key('fk_movimento_financeiro_movimento_original', 'movimento_financeiro', ['movimento_original_id'], ['id'])


def downgrade():
    with op.batch_alter_table('movimento_financeiro', schema=None) as batch_op:
        batch_op.drop_constraint('fk_movimento_financeiro_movimento_original', type_='foreignkey')
        batch_op.drop_index('ix_movimento_financeiro_movimento_original_id')
        batch_op.drop_column('movimento_original_id')
