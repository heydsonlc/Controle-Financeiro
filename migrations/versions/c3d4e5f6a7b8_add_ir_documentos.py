"""add_ir_documentos

Revision ID: c3d4e5f6a7b8
Revises: ea039138b34d
Create Date: 2026-05-04 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'ea039138b34d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ir_categoria',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('dedutivel', sa.Boolean(), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('observacao_fiscal', sa.Text(), nullable=True),
        sa.Column('ordem', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nome'),
    )

    op.create_table(
        'ir_categoria_despesa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('categoria_ir_id', sa.Integer(), nullable=False),
        sa.Column('categoria_id', sa.Integer(), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id']),
        sa.ForeignKeyConstraint(['categoria_ir_id'], ['ir_categoria.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('categoria_ir_id', 'categoria_id', name='ux_ir_categoria_despesa_ir_categoria'),
    )
    op.create_index('ix_ir_categoria_despesa_categoria', 'ir_categoria_despesa', ['categoria_id'], unique=False)
    op.create_index('ix_ir_categoria_despesa_categoria_ir', 'ir_categoria_despesa', ['categoria_ir_id'], unique=False)

    op.create_table(
        'ir_comprovante',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ano_calendario', sa.Integer(), nullable=False),
        sa.Column('data_documento', sa.Date(), nullable=True),
        sa.Column('prestador_nome', sa.String(length=255), nullable=True),
        sa.Column('prestador_cpf_cnpj', sa.String(length=20), nullable=True),
        sa.Column('tomador_nome', sa.String(length=255), nullable=True),
        sa.Column('tomador_cpf', sa.String(length=20), nullable=True),
        sa.Column('valor', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('categoria_id', sa.Integer(), nullable=True),
        sa.Column('categoria_ir_id', sa.Integer(), nullable=True),
        sa.Column('dedutivel', sa.Boolean(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('confianca', sa.String(length=30), nullable=True),
        sa.Column('origem_classificacao', sa.String(length=50), nullable=True),
        sa.Column('texto_extraido', sa.Text(), nullable=True),
        sa.Column('observacoes', sa.Text(), nullable=True),
        sa.Column('hash_arquivo', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id']),
        sa.ForeignKeyConstraint(['categoria_ir_id'], ['ir_categoria.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('hash_arquivo'),
    )
    op.create_index('ix_ir_comprovante_ano_calendario', 'ir_comprovante', ['ano_calendario'], unique=False)
    op.create_index('ix_ir_comprovante_hash_arquivo', 'ir_comprovante', ['hash_arquivo'], unique=False)

    op.create_table(
        'ir_comprovante_arquivo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('comprovante_id', sa.Integer(), nullable=False),
        sa.Column('nome_arquivo', sa.String(length=255), nullable=False),
        sa.Column('mime_type', sa.String(length=120), nullable=False),
        sa.Column('tamanho_bytes', sa.Integer(), nullable=False),
        sa.Column('conteudo', sa.LargeBinary(), nullable=False),
        sa.Column('hash_arquivo', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['comprovante_id'], ['ir_comprovante.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('comprovante_id'),
    )
    op.create_index('ix_ir_comprovante_arquivo_hash_arquivo', 'ir_comprovante_arquivo', ['hash_arquivo'], unique=False)

    op.create_table(
        'ir_comprovante_evento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('comprovante_id', sa.Integer(), nullable=False),
        sa.Column('tipo_evento', sa.String(length=50), nullable=False),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['comprovante_id'], ['ir_comprovante.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    categorias = sa.table(
        'ir_categoria',
        sa.column('nome', sa.String),
        sa.column('descricao', sa.Text),
        sa.column('dedutivel', sa.Boolean),
        sa.column('ativo', sa.Boolean),
        sa.column('observacao_fiscal', sa.Text),
        sa.column('ordem', sa.Integer),
    )
    op.bulk_insert(categorias, [
        {'nome': 'Saude', 'descricao': 'Despesas medicas e assistenciais', 'dedutivel': True, 'ativo': True, 'observacao_fiscal': 'Revisar comprovantes com contador.', 'ordem': 10},
        {'nome': 'Odontologia', 'descricao': 'Tratamentos odontologicos', 'dedutivel': True, 'ativo': True, 'observacao_fiscal': 'Revisar comprovantes com contador.', 'ordem': 20},
        {'nome': 'Psicologia', 'descricao': 'Consultas e tratamentos psicologicos', 'dedutivel': True, 'ativo': True, 'observacao_fiscal': 'Revisar comprovantes com contador.', 'ordem': 30},
        {'nome': 'Educacao', 'descricao': 'Despesas educacionais', 'dedutivel': True, 'ativo': True, 'observacao_fiscal': 'Sujeito aos limites legais aplicaveis.', 'ordem': 40},
        {'nome': 'Fisioterapia', 'descricao': 'Fisioterapia e reabilitacao', 'dedutivel': True, 'ativo': True, 'observacao_fiscal': 'Revisar comprovantes com contador.', 'ordem': 50},
        {'nome': 'Exames', 'descricao': 'Exames laboratoriais e diagnosticos', 'dedutivel': True, 'ativo': True, 'observacao_fiscal': 'Revisar comprovantes com contador.', 'ordem': 60},
        {'nome': 'Plano de Saude', 'descricao': 'Plano de saude e mensalidades assistenciais', 'dedutivel': True, 'ativo': True, 'observacao_fiscal': 'Revisar comprovantes com contador.', 'ordem': 70},
        {'nome': 'Outros', 'descricao': 'Comprovantes relevantes para revisao', 'dedutivel': False, 'ativo': True, 'observacao_fiscal': 'Classificacao potencial, revisar antes da declaracao.', 'ordem': 999},
    ])


def downgrade():
    op.drop_table('ir_comprovante_evento')
    op.drop_index('ix_ir_comprovante_arquivo_hash_arquivo', table_name='ir_comprovante_arquivo')
    op.drop_table('ir_comprovante_arquivo')
    op.drop_index('ix_ir_comprovante_hash_arquivo', table_name='ir_comprovante')
    op.drop_index('ix_ir_comprovante_ano_calendario', table_name='ir_comprovante')
    op.drop_table('ir_comprovante')
    op.drop_index('ix_ir_categoria_despesa_categoria_ir', table_name='ir_categoria_despesa')
    op.drop_index('ix_ir_categoria_despesa_categoria', table_name='ir_categoria_despesa')
    op.drop_table('ir_categoria_despesa')
    op.drop_table('ir_categoria')
