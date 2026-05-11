"""adiciona conferencia CAIXA de financiamento

Revision ID: c8d9e0f1a2b3
Revises: b0c1d2e3f4a5
Create Date: 2026-05-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'c8d9e0f1a2b3'
down_revision = 'b0c1d2e3f4a5'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(table_name):
    return table_name in _insp().get_table_names()


def _column_exists(table_name, column_name):
    if not _table_exists(table_name):
        return False
    return column_name in {column['name'] for column in _insp().get_columns(table_name)}


def _index_exists(table_name, index_name):
    if not _table_exists(table_name):
        return False
    return index_name in {index['name'] for index in _insp().get_indexes(table_name)}


def _create_index(table_name, index_name, columns):
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _add_financiamento_documento_links():
    if not _table_exists('financiamento_documento'):
        return

    for column_name in ('parcela_id', 'amortizacao_id', 'ajuste_saldo_id'):
        if not _column_exists('financiamento_documento', column_name):
            op.add_column('financiamento_documento', sa.Column(column_name, sa.Integer(), nullable=True))

    _create_index('financiamento_documento', 'idx_fin_doc_parcela', ['parcela_id'])
    _create_index('financiamento_documento', 'idx_fin_doc_amortizacao', ['amortizacao_id'])
    _create_index('financiamento_documento', 'idx_fin_doc_ajuste_saldo', ['ajuste_saldo_id'])


def upgrade():
    _add_financiamento_documento_links()

    if _table_exists('financiamento_conferencia_caixa'):
        return

    op.create_table(
        'financiamento_conferencia_caixa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('perfil_financeiro_id', sa.Integer(), nullable=True),
        sa.Column('financiamento_id', sa.Integer(), nullable=False),
        sa.Column('documento_id', sa.Integer(), nullable=True),
        sa.Column('tipo_conferencia', sa.String(length=40), nullable=False),
        sa.Column('competencia', sa.String(length=7), nullable=True),
        sa.Column('ano_base', sa.Integer(), nullable=True),
        sa.Column('data_referencia', sa.Date(), nullable=True),
        sa.Column('parcela_id', sa.Integer(), nullable=True),
        sa.Column('valor_real_amortizacao', sa.Numeric(12, 2), nullable=True),
        sa.Column('valor_real_juros', sa.Numeric(12, 2), nullable=True),
        sa.Column('valor_real_seguro', sa.Numeric(12, 2), nullable=True),
        sa.Column('valor_real_taxa_adm', sa.Numeric(12, 2), nullable=True),
        sa.Column('valor_real_total', sa.Numeric(12, 2), nullable=True),
        sa.Column('saldo_devedor_real', sa.Numeric(12, 2), nullable=True),
        sa.Column('juros_correcao_mes_real', sa.Numeric(12, 2), nullable=True),
        sa.Column('amortizacao_mes_real', sa.Numeric(12, 2), nullable=True),
        sa.Column('prazo_remanescente_real', sa.Integer(), nullable=True),
        sa.Column('valor_simulado_amortizacao', sa.Numeric(12, 2), nullable=True),
        sa.Column('valor_simulado_juros', sa.Numeric(12, 2), nullable=True),
        sa.Column('valor_simulado_seguro', sa.Numeric(12, 2), nullable=True),
        sa.Column('valor_simulado_taxa_adm', sa.Numeric(12, 2), nullable=True),
        sa.Column('valor_simulado_total', sa.Numeric(12, 2), nullable=True),
        sa.Column('saldo_devedor_simulado', sa.Numeric(12, 2), nullable=True),
        sa.Column('diferenca_amortizacao', sa.Numeric(12, 2), nullable=True),
        sa.Column('diferenca_juros', sa.Numeric(12, 2), nullable=True),
        sa.Column('diferenca_seguro', sa.Numeric(12, 2), nullable=True),
        sa.Column('diferenca_taxa_adm', sa.Numeric(12, 2), nullable=True),
        sa.Column('diferenca_total', sa.Numeric(12, 2), nullable=True),
        sa.Column('diferenca_saldo', sa.Numeric(12, 2), nullable=True),
        sa.Column('observacao', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['documento_id'], ['financiamento_documento.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['financiamento_id'], ['financiamento.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parcela_id'], ['financiamento_parcela.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    _create_index('financiamento_conferencia_caixa', 'idx_fin_conf_financiamento', ['financiamento_id'])
    _create_index('financiamento_conferencia_caixa', 'idx_fin_conf_documento', ['documento_id'])
    _create_index(
        'financiamento_conferencia_caixa',
        'idx_fin_conf_perfil_financiamento',
        ['perfil_financeiro_id', 'financiamento_id'],
    )
    _create_index('financiamento_conferencia_caixa', 'idx_fin_conf_competencia', ['competencia'])
    _create_index('financiamento_conferencia_caixa', 'idx_fin_conf_tipo', ['tipo_conferencia'])
    _create_index('financiamento_conferencia_caixa', 'idx_fin_conf_parcela', ['parcela_id'])


def downgrade():
    if _table_exists('financiamento_conferencia_caixa'):
        for index_name in (
            'idx_fin_conf_parcela',
            'idx_fin_conf_tipo',
            'idx_fin_conf_competencia',
            'idx_fin_conf_perfil_financiamento',
            'idx_fin_conf_documento',
            'idx_fin_conf_financiamento',
        ):
            if _index_exists('financiamento_conferencia_caixa', index_name):
                op.drop_index(index_name, table_name='financiamento_conferencia_caixa')
        op.drop_table('financiamento_conferencia_caixa')

    if _table_exists('financiamento_documento'):
        for index_name in (
            'idx_fin_doc_ajuste_saldo',
            'idx_fin_doc_amortizacao',
            'idx_fin_doc_parcela',
        ):
            if _index_exists('financiamento_documento', index_name):
                op.drop_index(index_name, table_name='financiamento_documento')
        for column_name in ('ajuste_saldo_id', 'amortizacao_id', 'parcela_id'):
            if _column_exists('financiamento_documento', column_name):
                op.drop_column('financiamento_documento', column_name)
