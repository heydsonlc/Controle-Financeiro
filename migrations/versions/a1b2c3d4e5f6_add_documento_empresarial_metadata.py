"""add documento empresarial metadata

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-05-06 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'f6a7b8c9d0e1'
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


def _create_index(table_name, index_name, columns):
    if _table_exists(table_name) and not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade():
    if not _table_exists('documento_empresarial_metadata'):
        op.create_table(
            'documento_empresarial_metadata',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('comprovante_id', sa.Integer(), nullable=False),
            sa.Column('perfil_financeiro_id', sa.Integer(), nullable=False),
            sa.Column('tipo_documental', sa.String(length=60), nullable=False, server_default='OUTRO'),
            sa.Column('categoria_documental', sa.String(length=80), nullable=False, server_default='SEM_CATEGORIA'),
            sa.Column('subtipo', sa.String(length=120), nullable=True),
            sa.Column('numero_documento', sa.String(length=120), nullable=True),
            sa.Column('orgao_emissor', sa.String(length=160), nullable=True),
            sa.Column('data_emissao', sa.Date(), nullable=True),
            sa.Column('data_validade', sa.Date(), nullable=True),
            sa.Column('status_documental', sa.String(length=40), nullable=False, server_default='ATIVO'),
            sa.Column('obrigatorio', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('renovavel', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('alerta_dias_antes', sa.Integer(), nullable=True),
            sa.Column('responsavel_interno', sa.String(length=120), nullable=True),
            sa.Column('origem_documental', sa.String(length=40), nullable=True),
            sa.Column('tags', sa.Text(), nullable=True),
            sa.Column('observacoes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['comprovante_id'], ['ir_comprovante.id']),
            sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('comprovante_id', name='ux_documento_emp_metadata_comprovante'),
        )
        op.alter_column('documento_empresarial_metadata', 'tipo_documental', server_default=None)
        op.alter_column('documento_empresarial_metadata', 'categoria_documental', server_default=None)
        op.alter_column('documento_empresarial_metadata', 'status_documental', server_default=None)
        op.alter_column('documento_empresarial_metadata', 'obrigatorio', server_default=None)
        op.alter_column('documento_empresarial_metadata', 'renovavel', server_default=None)

    _create_index('documento_empresarial_metadata', 'ix_documento_emp_metadata_perfil', ['perfil_financeiro_id'])
    _create_index('documento_empresarial_metadata', 'ix_documento_emp_metadata_comprovante', ['comprovante_id'])
    _create_index('documento_empresarial_metadata', 'ix_documento_emp_metadata_tipo', ['tipo_documental'])
    _create_index('documento_empresarial_metadata', 'ix_documento_emp_metadata_categoria', ['categoria_documental'])
    _create_index('documento_empresarial_metadata', 'ix_documento_emp_metadata_status', ['status_documental'])
    _create_index('documento_empresarial_metadata', 'ix_documento_emp_metadata_validade', ['data_validade'])
    _create_index('documento_empresarial_metadata', 'ix_documento_emp_metadata_obrigatorio', ['obrigatorio'])


def downgrade():
    for index_name in (
        'ix_documento_emp_metadata_obrigatorio',
        'ix_documento_emp_metadata_validade',
        'ix_documento_emp_metadata_status',
        'ix_documento_emp_metadata_categoria',
        'ix_documento_emp_metadata_tipo',
        'ix_documento_emp_metadata_comprovante',
        'ix_documento_emp_metadata_perfil',
    ):
        if _index_exists('documento_empresarial_metadata', index_name):
            op.drop_index(index_name, table_name='documento_empresarial_metadata')
    if _table_exists('documento_empresarial_metadata'):
        op.drop_table('documento_empresarial_metadata')
