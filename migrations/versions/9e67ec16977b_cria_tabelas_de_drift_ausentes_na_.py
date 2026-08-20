"""cria tabelas de drift ausentes na cadeia de migrations

Revision ID: 9e67ec16977b
Revises: f4a9c2d1e8b7
Create Date: 2026-08-20 06:35:10.469016

SUPABASE-MIGRATE-1: seis tabelas usadas pelos modelos ativos
(categoria_cartao, categoria_palavra_chave, categoria_cartao_despesa,
cartao_categoria_limite, mobilidade_assinatura, mobilidade_cenario_ativo)
nunca foram criadas por nenhuma migration em toda a cadeia, e algumas
colunas (item_despesa.categoria_cartao_id/origem_tipo/origem_id/
origem_contexto, lancamento_agregado.categoria_cartao_id,
financiamento_documento.parcela_id/amortizacao_id/ajuste_saldo_id)
tambem nunca foram adicionadas por nenhuma migration a tabelas que ja
existiam — tudo existia apenas em bancos locais mais antigos por drift
fora do Alembic (ex.: db.create_all() em algum ponto anterior ao
baseline). Migrations posteriores (9b8a09ecc52f, a8c1e2d3f4b5,
b2c3d4e5f6a7, b9d2e3f4a5c6) assumem essas tabelas/colunas como
pre-existentes, o que funciona em bancos com o drift local mas falha
em qualquer banco criado do zero (ex.: Supabase).

Esta migration cria as tabelas/colunas com a estrutura exata que os
modelos SQLAlchemy esperam hoje (gerada a partir de db.metadata, nao
digitada a mao). E guardada por checagem de existencia: em bancos onde
ja existem (drift local), e um no-op; em bancos novos, cria o que
sempre deveria ter existido.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9e67ec16977b'
down_revision = 'f4a9c2d1e8b7'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existentes = set(inspector.get_table_names())

    if 'categoria_cartao' not in existentes:
        op.create_table(
            'categoria_cartao',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('perfil_financeiro_id', sa.Integer(), nullable=True),
            sa.Column('nome', sa.String(length=100), nullable=False),
            sa.Column('descricao', sa.Text(), nullable=True),
            sa.Column('cor', sa.String(length=7), nullable=True),
            sa.Column('icone', sa.String(length=50), nullable=True),
            sa.Column('logo_arquivo', sa.String(length=255), nullable=True),
            sa.Column('logo_mime', sa.String(length=100), nullable=True),
            sa.Column('logo_tamanho', sa.Integer(), nullable=True),
            sa.Column('logo_original_nome', sa.String(length=255), nullable=True),
            sa.Column('logo_criado_em', sa.DateTime(), nullable=True),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('perfil_financeiro_id', 'nome', name='ux_categoria_cartao_perfil_nome'),
        )
        # ix_categoria_cartao_perfil_financeiro_id (9b8a09ecc52f) e
        # ix_categoria_cartao_perfil_ativo (a8c1e2d3f4b5) sao criados mais
        # adiante na cadeia, sobre esta mesma tabela.

    if 'categoria_palavra_chave' not in existentes:
        op.create_table(
            'categoria_palavra_chave',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('categoria_id', sa.Integer(), nullable=False),
            sa.Column('palavra', sa.String(length=120), nullable=False),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('categoria_id', 'palavra', name='ux_categoria_palavra_chave_categoria_palavra'),
        )
        op.create_index('ix_categoria_palavra_chave_palavra', 'categoria_palavra_chave', ['palavra'])
        op.create_index('ix_categoria_palavra_chave_categoria', 'categoria_palavra_chave', ['categoria_id'])

    if 'categoria_cartao_despesa' not in existentes:
        op.create_table(
            'categoria_cartao_despesa',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('perfil_financeiro_id', sa.Integer(), nullable=True),
            sa.Column('categoria_cartao_id', sa.Integer(), nullable=False),
            sa.Column('categoria_id', sa.Integer(), nullable=False),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id']),
            sa.ForeignKeyConstraint(['categoria_cartao_id'], ['categoria_cartao.id']),
            sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('categoria_cartao_id', 'categoria_id', name='ux_categoria_cartao_despesa_par'),
        )
        # ix_categoria_cartao_despesa_perfil_financeiro_id (9b8a09ecc52f) e
        # ix_categoria_cartao_despesa_perfil (a8c1e2d3f4b5) sao criados mais
        # adiante na cadeia, sobre esta mesma tabela.
        op.create_index('ix_categoria_cartao_despesa_categoria', 'categoria_cartao_despesa', ['categoria_id'])
        op.create_index('ix_categoria_cartao_despesa_cartao', 'categoria_cartao_despesa', ['categoria_cartao_id'])

    if 'cartao_categoria_limite' not in existentes:
        op.create_table(
            'cartao_categoria_limite',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('perfil_financeiro_id', sa.Integer(), nullable=True),
            sa.Column('cartao_id', sa.Integer(), nullable=False),
            sa.Column('categoria_cartao_id', sa.Integer(), nullable=False),
            sa.Column('limite_mensal', sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column('vigencia_inicio', sa.Date(), nullable=True),
            sa.Column('vigencia_fim', sa.Date(), nullable=True),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id']),
            sa.ForeignKeyConstraint(['cartao_id'], ['item_despesa.id']),
            sa.ForeignKeyConstraint(['categoria_cartao_id'], ['categoria_cartao.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('cartao_id', 'categoria_cartao_id', name='ux_cartao_categoria_limite_cartao_categoria'),
        )
        op.create_index('ix_cartao_categoria_limite_cartao', 'cartao_categoria_limite', ['cartao_id'])
        op.create_index('ix_cartao_categoria_limite_categoria', 'cartao_categoria_limite', ['categoria_cartao_id'])
        # ix_cartao_categoria_limite_perfil_financeiro_id (9b8a09ecc52f) e
        # ix_cartao_categoria_limite_perfil (a8c1e2d3f4b5) sao criados mais
        # adiante na cadeia, sobre esta mesma tabela.

    if 'mobilidade_assinatura' not in existentes:
        op.create_table(
            'mobilidade_assinatura',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('perfil_financeiro_id', sa.Integer(), nullable=True),
            sa.Column('nome', sa.String(length=100), nullable=False),
            sa.Column('valor_mensal', sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column('categoria_id', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(length=10), nullable=False),
            sa.Column('metadata_json', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id']),
            sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        # ix_mobilidade_assinatura_perfil_financeiro_id e criado (e removido
        # de volta) por 9b8a09ecc52f, mais adiante na cadeia.

    if 'mobilidade_cenario_ativo' not in existentes:
        op.create_table(
            'mobilidade_cenario_ativo',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('perfil_financeiro_id', sa.Integer(), nullable=True),
            sa.Column('tipo_modalidade', sa.String(length=20), nullable=False),
            sa.Column('origem_id', sa.Integer(), nullable=False),
            sa.Column('ativo_desde', sa.Date(), nullable=False),
            sa.Column('meio_pagamento', sa.String(length=20), nullable=True),
            sa.Column('cartao_id', sa.Integer(), nullable=True),
            sa.Column('categoria_id', sa.Integer(), nullable=True),
            sa.Column('categoria_cartao_id', sa.Integer(), nullable=True),
            sa.Column('recorrencia_id', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(length=10), nullable=False),
            sa.Column('metadata_json', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id']),
            sa.ForeignKeyConstraint(['cartao_id'], ['item_despesa.id']),
            sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id']),
            sa.ForeignKeyConstraint(['categoria_cartao_id'], ['categoria_cartao.id']),
            sa.ForeignKeyConstraint(['recorrencia_id'], ['item_despesa.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        # ix_mobilidade_cenario_ativo_perfil_financeiro_id e criado (e
        # removido de volta) por 9b8a09ecc52f, mais adiante na cadeia.

    # Colunas de drift: adicionadas fora do Alembic em algum ponto antigo,
    # nunca capturadas por nenhuma migration. categoria_cartao ja existe
    # neste ponto da cadeia (criada acima), entao as FKs abaixo sao seguras.
    colunas_item_despesa = {c['name'] for c in inspector.get_columns('item_despesa')}
    if 'categoria_cartao_id' not in colunas_item_despesa:
        op.add_column('item_despesa', sa.Column('categoria_cartao_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            'item_despesa_categoria_cartao_id_fkey', 'item_despesa', 'categoria_cartao',
            ['categoria_cartao_id'], ['id'], ondelete='SET NULL',
        )
    if 'origem_tipo' not in colunas_item_despesa:
        op.add_column('item_despesa', sa.Column('origem_tipo', sa.String(length=30), nullable=True))
    if 'origem_id' not in colunas_item_despesa:
        op.add_column('item_despesa', sa.Column('origem_id', sa.Integer(), nullable=True))
    if 'origem_contexto' not in colunas_item_despesa:
        op.add_column('item_despesa', sa.Column('origem_contexto', sa.String(length=50), nullable=True))

    colunas_lancamento_agregado = {c['name'] for c in inspector.get_columns('lancamento_agregado')}
    if 'categoria_cartao_id' not in colunas_lancamento_agregado:
        op.add_column('lancamento_agregado', sa.Column('categoria_cartao_id', sa.Integer(), nullable=True))

    # financiamento_documento.parcela_id/amortizacao_id/ajuste_saldo_id: a
    # tabela so e criada por b0c1d2e3f4a5, mais adiante na cadeia — a
    # correcao dessas colunas fica na migration 9b8a09ecc52f, onde o
    # problema se manifesta (create_foreign_key assumindo colunas
    # pre-existentes), nao aqui.


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existentes = set(inspector.get_table_names())

    for tabela in ('mobilidade_cenario_ativo', 'mobilidade_assinatura', 'cartao_categoria_limite',
                   'categoria_cartao_despesa', 'categoria_palavra_chave', 'categoria_cartao'):
        if tabela in existentes:
            op.drop_table(tabela)
