"""adiciona modo caixa sac tr para financiamento

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-05-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'f8a9b0c1d2e3'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


TR_SEED = [
    ('2024-05', 2024, 5, '0.0008'),
    ('2024-06', 2024, 6, '0.0003'),
    ('2024-07', 2024, 7, '0.0007'),
    ('2024-08', 2024, 8, '0.0007'),
    ('2024-09', 2024, 9, '0.0006'),
    ('2024-10', 2024, 10, '0.0009'),
    ('2024-11', 2024, 11, '0.0006'),
    ('2024-12', 2024, 12, '0.0008'),
    ('2025-01', 2025, 1, '0.0016'),
    ('2025-02', 2025, 2, '0.0013'),
    ('2025-03', 2025, 3, '0.0010'),
    ('2025-04', 2025, 4, '0.0016'),
    ('2025-05', 2025, 5, '0.0017'),
    ('2025-06', 2025, 6, '0.0016'),
    ('2025-07', 2025, 7, '0.0017'),
    ('2025-08', 2025, 8, '0.0017'),
    ('2025-09', 2025, 9, '0.0017'),
    ('2025-10', 2025, 10, '0.0017'),
    ('2025-11', 2025, 11, '0.0016'),
    ('2025-12', 2025, 12, '0.0017'),
    ('2026-01', 2026, 1, '0.0017'),
    ('2026-02', 2026, 2, '0.0012'),
    ('2026-03', 2026, 3, '0.0017'),
    ('2026-04', 2026, 4, '0.0016'),
    ('2026-05', 2026, 5, '0.0016'),
]


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(table_name):
    return table_name in _insp().get_table_names()


def _columns(table_name):
    if not _table_exists(table_name):
        return set()
    return {column['name'] for column in _insp().get_columns(table_name)}


def _column_exists(table_name, column_name):
    return column_name in _columns(table_name)


def _index_exists(table_name, index_name):
    if not _table_exists(table_name):
        return False
    return index_name in {index['name'] for index in _insp().get_indexes(table_name)}


def _seed_tr(bind):
    for competencia, ano, mes, valor_decimal in TR_SEED:
        bind.execute(
            sa.text(
                """
                INSERT INTO indice_tr_mensal
                    (ano, mes, competencia, valor_decimal, fonte, criado_em, atualizado_em)
                SELECT
                    :ano, :mes, :competencia, :valor_decimal, 'BACEN',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                    SELECT 1 FROM indice_tr_mensal WHERE competencia = :competencia
                )
                """
            ),
            {
                'ano': ano,
                'mes': mes,
                'competencia': competencia,
                'valor_decimal': valor_decimal,
            },
        )


def upgrade():
    bind = op.get_bind()

    if _table_exists('financiamento'):
        if not _column_exists('financiamento', 'modo_calculo_financiamento'):
            op.add_column(
                'financiamento',
                sa.Column('modo_calculo_financiamento', sa.String(length=30), nullable=True, server_default='padrao'),
            )
        if not _column_exists('financiamento', 'modo_taxa_mensal'):
            op.add_column(
                'financiamento',
                sa.Column('modo_taxa_mensal', sa.String(length=30), nullable=True, server_default='efetiva_equivalente'),
            )
        if not _column_exists('financiamento', 'seguro_dfi_base'):
            op.add_column(
                'financiamento',
                sa.Column('seguro_dfi_base', sa.Numeric(12, 2), nullable=True),
            )

        bind.execute(sa.text("UPDATE financiamento SET modo_calculo_financiamento = 'padrao' WHERE modo_calculo_financiamento IS NULL"))
        bind.execute(sa.text("UPDATE financiamento SET modo_taxa_mensal = 'efetiva_equivalente' WHERE modo_taxa_mensal IS NULL"))

    if not _table_exists('indice_tr_mensal'):
        op.create_table(
            'indice_tr_mensal',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('ano', sa.Integer(), nullable=False),
            sa.Column('mes', sa.Integer(), nullable=False),
            sa.Column('competencia', sa.String(length=7), nullable=False),
            sa.Column('valor_decimal', sa.Numeric(12, 8), nullable=False),
            sa.Column('fonte', sa.String(length=50), nullable=True, server_default='BACEN'),
            sa.Column('criado_em', sa.DateTime(), nullable=True),
            sa.Column('atualizado_em', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('ano', 'mes', name='uq_indice_tr_mensal_ano_mes'),
            sa.UniqueConstraint('competencia', name='uq_indice_tr_mensal_competencia'),
        )

    if _table_exists('indice_tr_mensal'):
        if not _index_exists('indice_tr_mensal', 'idx_indice_tr_mensal_competencia'):
            op.create_index('idx_indice_tr_mensal_competencia', 'indice_tr_mensal', ['competencia'])
        _seed_tr(bind)


def downgrade():
    if _table_exists('indice_tr_mensal'):
        if _index_exists('indice_tr_mensal', 'idx_indice_tr_mensal_competencia'):
            op.drop_index('idx_indice_tr_mensal_competencia', table_name='indice_tr_mensal')
        op.drop_table('indice_tr_mensal')

    if _table_exists('financiamento'):
        for column_name in [
            'seguro_dfi_base',
            'modo_taxa_mensal',
            'modo_calculo_financiamento',
        ]:
            if _column_exists('financiamento', column_name):
                op.drop_column('financiamento', column_name)
