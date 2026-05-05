"""add bem patrimonial

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-05 14:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(table_name):
    return table_name in _inspector().get_table_names()


def _index_exists(table_name, index_name):
    if not _table_exists(table_name):
        return False
    return index_name in {index['name'] for index in _inspector().get_indexes(table_name)}


def _constraint_exists(table_name, constraint_name):
    if not _table_exists(table_name):
        return False
    constraints = _inspector().get_unique_constraints(table_name)
    return constraint_name in {constraint['name'] for constraint in constraints}


def _create_index(table_name, index_name, columns):
    if _table_exists(table_name) and not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade():
    if not _table_exists('bem_patrimonial'):
        op.create_table(
            'bem_patrimonial',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('perfil_financeiro_id', sa.Integer(), nullable=False),
            sa.Column('nome', sa.String(length=160), nullable=False),
            sa.Column('codigo', sa.String(length=60), nullable=True),
            sa.Column('categoria', sa.String(length=80), nullable=True),
            sa.Column('descricao', sa.Text(), nullable=True),
            sa.Column('fornecedor', sa.String(length=255), nullable=True),
            sa.Column('documento_numero', sa.String(length=80), nullable=True),
            sa.Column('imagem_arquivo', sa.String(length=255), nullable=True),
            sa.Column('data_aquisicao', sa.Date(), nullable=True),
            sa.Column('valor_aquisicao', sa.Numeric(12, 2), nullable=True),
            sa.Column('vida_util_meses', sa.Integer(), nullable=True),
            sa.Column('depreciacao_mensal', sa.Numeric(12, 2), nullable=True),
            sa.Column('centro_custo', sa.String(length=120), nullable=True),
            sa.Column('localizacao', sa.String(length=120), nullable=True),
            sa.Column('responsavel', sa.String(length=120), nullable=True),
            sa.Column('status', sa.String(length=30), nullable=False, server_default='ATIVO'),
            sa.Column('status_documental', sa.String(length=40), nullable=False, server_default='SEM_DOCUMENTO'),
            sa.Column('observacoes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('perfil_financeiro_id', 'codigo', name='ux_bem_patrimonial_perfil_codigo'),
        )
        op.alter_column('bem_patrimonial', 'status', server_default=None)
        op.alter_column('bem_patrimonial', 'status_documental', server_default=None)

    _create_index('bem_patrimonial', 'ix_bem_patrimonial_perfil_financeiro_id', ['perfil_financeiro_id'])
    _create_index('bem_patrimonial', 'ix_bem_patrimonial_perfil_status', ['perfil_financeiro_id', 'status'])
    _create_index('bem_patrimonial', 'ix_bem_patrimonial_perfil_status_documental', ['perfil_financeiro_id', 'status_documental'])
    _create_index('bem_patrimonial', 'ix_bem_patrimonial_perfil_categoria', ['perfil_financeiro_id', 'categoria'])
    _create_index('bem_patrimonial', 'ix_bem_patrimonial_perfil_data', ['perfil_financeiro_id', 'data_aquisicao'])


def downgrade():
    for index_name in (
        'ix_bem_patrimonial_perfil_data',
        'ix_bem_patrimonial_perfil_categoria',
        'ix_bem_patrimonial_perfil_status_documental',
        'ix_bem_patrimonial_perfil_status',
        'ix_bem_patrimonial_perfil_financeiro_id',
    ):
        if _index_exists('bem_patrimonial', index_name):
            op.drop_index(index_name, table_name='bem_patrimonial')
    if _table_exists('bem_patrimonial'):
        op.drop_table('bem_patrimonial')
