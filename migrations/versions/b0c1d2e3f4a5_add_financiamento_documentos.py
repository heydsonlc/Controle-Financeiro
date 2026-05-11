"""adiciona documentos do financiamento

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-05-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b0c1d2e3f4a5'
down_revision = 'a9b0c1d2e3f4'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(table_name):
    return table_name in _insp().get_table_names()


def _index_exists(table_name, index_name):
    if not _table_exists(table_name):
        return False
    return index_name in {index['name'] for index in _insp().get_indexes(table_name)}


def upgrade():
    if _table_exists('financiamento_documento'):
        return

    op.create_table(
        'financiamento_documento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('perfil_financeiro_id', sa.Integer(), nullable=True),
        sa.Column('financiamento_id', sa.Integer(), nullable=False),
        sa.Column('tipo_documento', sa.String(length=80), nullable=False),
        sa.Column('competencia', sa.String(length=7), nullable=True),
        sa.Column('ano_base', sa.Integer(), nullable=True),
        sa.Column('data_documento', sa.Date(), nullable=True),
        sa.Column('nome_original', sa.String(length=255), nullable=False),
        sa.Column('nome_armazenado', sa.String(length=120), nullable=False),
        sa.Column('mime_type', sa.String(length=120), nullable=True),
        sa.Column('tamanho_bytes', sa.Integer(), nullable=False),
        sa.Column('hash_arquivo', sa.String(length=64), nullable=False),
        sa.Column('caminho_relativo', sa.String(length=500), nullable=False),
        sa.Column('observacao', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['financiamento_id'], ['financiamento.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    for index_name, columns in (
        ('idx_fin_doc_financiamento', ['financiamento_id']),
        ('idx_fin_doc_perfil_financiamento', ['perfil_financeiro_id', 'financiamento_id']),
        ('idx_fin_doc_tipo', ['tipo_documento']),
        ('idx_fin_doc_competencia', ['competencia']),
        ('idx_fin_doc_hash', ['hash_arquivo']),
    ):
        if not _index_exists('financiamento_documento', index_name):
            op.create_index(index_name, 'financiamento_documento', columns)


def downgrade():
    if not _table_exists('financiamento_documento'):
        return

    for index_name in (
        'idx_fin_doc_hash',
        'idx_fin_doc_competencia',
        'idx_fin_doc_tipo',
        'idx_fin_doc_perfil_financiamento',
        'idx_fin_doc_financiamento',
    ):
        if _index_exists('financiamento_documento', index_name):
            op.drop_index(index_name, table_name='financiamento_documento')

    op.drop_table('financiamento_documento')
