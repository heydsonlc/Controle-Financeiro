"""Adiciona tabela de usuario

Revision ID: 5c91e95eb05d
Revises: 76fa60a587fd
Create Date: 2026-08-19 21:57:20.529916

SEG-1: tabela de usuario unico para autenticacao global da aplicacao.

Escopo estritamente limitado a esta tabela/indice. O autogenerate do Alembic
detectou drift pre-existente e nao relacionado (constraints de check em
mobilidade_assinatura/mobilidade_cenario_ativo, indice
idx_movimento_financiamento_parcela — o mesmo drift ja visto e removido
manualmente na migration 76fa60a587fd) que foi removido deste arquivo —
fora do escopo do SEG-1.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5c91e95eb05d'
down_revision = '76fa60a587fd'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('usuario',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('usuario', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_usuario_email'), ['email'], unique=True)


def downgrade():
    with op.batch_alter_table('usuario', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_usuario_email'))

    op.drop_table('usuario')
