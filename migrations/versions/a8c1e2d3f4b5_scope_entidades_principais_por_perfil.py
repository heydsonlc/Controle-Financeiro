"""Escopa entidades financeiras principais por perfil.

Revision ID: a8c1e2d3f4b5
Revises: f4a9c2d1e8b7
Create Date: 2026-05-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'a8c1e2d3f4b5'
down_revision = 'f4a9c2d1e8b7'
branch_labels = None
depends_on = None


SCOPED_TABLES = (
    'categoria',
    'categoria_cartao',
    'categoria_cartao_despesa',
    'cartao_categoria_limite',
    'conta_bancaria',
    'movimento_financeiro',
    'item_despesa',
    'conta',
    'lancamento_agregado',
    'item_receita',
    'receita_orcamento',
    'receita_realizada',
    'despesa_prevista',
)

PROFILE_INDEXES = {
    'categoria': ('ix_categoria_perfil_ativo', ['perfil_financeiro_id', 'ativo']),
    'categoria_cartao': ('ix_categoria_cartao_perfil_ativo', ['perfil_financeiro_id', 'ativo']),
    'categoria_cartao_despesa': ('ix_categoria_cartao_despesa_perfil', ['perfil_financeiro_id']),
    'cartao_categoria_limite': ('ix_cartao_categoria_limite_perfil', ['perfil_financeiro_id']),
    'conta': ('idx_conta_perfil_status', ['perfil_financeiro_id', 'status_pagamento']),
    'lancamento_agregado': ('idx_lanc_agregado_perfil_fatura', ['perfil_financeiro_id', 'mes_fatura']),
    'item_receita': ('ix_item_receita_perfil_ativo', ['perfil_financeiro_id', 'ativo']),
    'receita_orcamento': ('idx_rec_orc_perfil_mes', ['perfil_financeiro_id', 'mes_referencia']),
    'receita_realizada': ('idx_rec_real_perfil_comp', ['perfil_financeiro_id', 'mes_referencia']),
    'movimento_financeiro': ('idx_movimento_perfil_data', ['perfil_financeiro_id', 'data_movimento']),
    'despesa_prevista': ('idx_desp_prev_perfil_data', ['perfil_financeiro_id', 'data_prevista']),
}

COMPOSITE_UNIQUES = {
    'categoria': ('ux_categoria_perfil_nome', ['perfil_financeiro_id', 'nome']),
    'categoria_cartao': ('ux_categoria_cartao_perfil_nome', ['perfil_financeiro_id', 'nome']),
    'item_receita': ('ux_item_receita_perfil_nome', ['perfil_financeiro_id', 'nome']),
}


def _table_names(bind):
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind, table_name):
    return {column['name'] for column in sa.inspect(bind).get_columns(table_name)}


def _index_names(bind, table_name):
    return {index['name'] for index in sa.inspect(bind).get_indexes(table_name)}


def _unique_constraints(bind, table_name):
    return sa.inspect(bind).get_unique_constraints(table_name)


def _seed_perfis(bind):
    perfil = sa.table(
        'perfil_financeiro',
        sa.column('id', sa.Integer),
        sa.column('nome', sa.String),
        sa.column('tipo', sa.String),
        sa.column('avatar', sa.String),
        sa.column('cor', sa.String),
        sa.column('ativo', sa.Boolean),
    )

    pessoal_id = bind.execute(
        sa.select(perfil.c.id).where(perfil.c.nome == 'Pessoal').limit(1)
    ).scalar()
    if not pessoal_id:
        bind.execute(
            perfil.insert().values(
                nome='Pessoal',
                tipo='PESSOAL',
                avatar='PE',
                cor='#2563eb',
                ativo=True,
            )
        )
        pessoal_id = bind.execute(
            sa.select(perfil.c.id).where(perfil.c.nome == 'Pessoal').limit(1)
        ).scalar()

    empresa_id = bind.execute(
        sa.select(perfil.c.id).where(perfil.c.nome == 'Empresa').limit(1)
    ).scalar()
    if not empresa_id:
        bind.execute(
            perfil.insert().values(
                nome='Empresa',
                tipo='EMPRESA',
                avatar='EM',
                cor='#0f766e',
                ativo=True,
            )
        )

    return pessoal_id


def _drop_nome_unique_if_exists(bind, table_name):
    for constraint in _unique_constraints(bind, table_name):
        if constraint.get('column_names') == ['nome'] and constraint.get('name'):
            op.drop_constraint(constraint['name'], table_name, type_='unique')


def upgrade():
    bind = op.get_bind()
    existing_tables = _table_names(bind)
    pessoal_id = _seed_perfis(bind)

    for table_name in SCOPED_TABLES:
        if table_name not in existing_tables:
            continue
        columns = _column_names(bind, table_name)
        if 'perfil_financeiro_id' not in columns:
            op.add_column(
                table_name,
                sa.Column(
                    'perfil_financeiro_id',
                    sa.Integer(),
                    sa.ForeignKey('perfil_financeiro.id'),
                    nullable=True,
                ),
            )
        op.execute(
            sa.text(f'UPDATE {table_name} SET perfil_financeiro_id = :perfil_id WHERE perfil_financeiro_id IS NULL')
            .bindparams(perfil_id=pessoal_id)
        )

    existing_tables = _table_names(bind)
    for table_name, (index_name, columns) in PROFILE_INDEXES.items():
        if table_name in existing_tables and index_name not in _index_names(bind, table_name):
            op.create_index(index_name, table_name, columns)

    for table_name, (constraint_name, columns) in COMPOSITE_UNIQUES.items():
        if table_name not in existing_tables:
            continue
        _drop_nome_unique_if_exists(bind, table_name)
        constraints = {constraint.get('name') for constraint in _unique_constraints(bind, table_name)}
        if constraint_name not in constraints:
            op.create_unique_constraint(constraint_name, table_name, columns)


def downgrade():
    bind = op.get_bind()
    existing_tables = _table_names(bind)

    for table_name, (constraint_name, _) in COMPOSITE_UNIQUES.items():
        if table_name in existing_tables:
            constraints = {constraint.get('name') for constraint in _unique_constraints(bind, table_name)}
            if constraint_name in constraints:
                op.drop_constraint(constraint_name, table_name, type_='unique')

    for table_name, (index_name, _) in PROFILE_INDEXES.items():
        if table_name in existing_tables and index_name in _index_names(bind, table_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name in reversed(SCOPED_TABLES):
        if table_name not in existing_tables:
            continue
        if 'perfil_financeiro_id' in _column_names(bind, table_name):
            op.drop_column(table_name, 'perfil_financeiro_id')
