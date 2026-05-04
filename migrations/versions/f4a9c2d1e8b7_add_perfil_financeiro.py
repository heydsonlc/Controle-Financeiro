"""add_perfil_financeiro

Revision ID: f4a9c2d1e8b7
Revises: c3d4e5f6a7b8
Create Date: 2026-05-04 18:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4a9c2d1e8b7'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'perfil_financeiro',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=120), nullable=False),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('documento', sa.String(length=32), nullable=True),
        sa.Column('avatar', sa.String(length=20), nullable=True),
        sa.Column('logo_url', sa.String(length=255), nullable=True),
        sa.Column('cor', sa.String(length=7), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nome'),
    )
    op.create_index('ix_perfil_financeiro_ativo', 'perfil_financeiro', ['ativo'], unique=False)
    op.create_index('ix_perfil_financeiro_tipo', 'perfil_financeiro', ['tipo'], unique=False)

    perfis = sa.table(
        'perfil_financeiro',
        sa.column('nome', sa.String),
        sa.column('tipo', sa.String),
        sa.column('avatar', sa.String),
        sa.column('cor', sa.String),
        sa.column('ativo', sa.Boolean),
    )

    bind = op.get_bind()
    existentes = {
        row[0]
        for row in bind.execute(sa.text("SELECT nome FROM perfil_financeiro WHERE nome IN ('Pessoal', 'Empresa')"))
    }
    novos = [
        {'nome': 'Pessoal', 'tipo': 'PESSOAL', 'avatar': 'PE', 'cor': '#2563eb', 'ativo': True},
        {'nome': 'Empresa', 'tipo': 'EMPRESA', 'avatar': 'EM', 'cor': '#0f766e', 'ativo': True},
    ]
    op.bulk_insert(perfis, [perfil for perfil in novos if perfil['nome'] not in existentes])


def downgrade():
    op.drop_index('ix_perfil_financeiro_tipo', table_name='perfil_financeiro')
    op.drop_index('ix_perfil_financeiro_ativo', table_name='perfil_financeiro')
    op.drop_table('perfil_financeiro')
