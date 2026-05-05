"""scope modulos avancados por perfil

Revision ID: b9d2e3f4a5c6
Revises: a8c1e2d3f4b5
Create Date: 2026-05-04 22:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b9d2e3f4a5c6'
down_revision = 'a8c1e2d3f4b5'
branch_labels = None
depends_on = None


TABELAS_PERFIL = [
    'ir_categoria_despesa',
    'ir_comprovante',
    'conta_patrimonio',
    'transferencia',
    'financiamento',
    'financiamento_parcela',
    'financiamento_amortizacao_extra',
    'financiamento_seguro_vigencia',
    'veiculo',
    'veiculo_regra_manutencao_km',
    'veiculo_ciclo_manutencao',
    'veiculo_financiamento',
    'mobilidade_cenario_ativo',
    'mobilidade_assinatura',
]


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(table_name):
    return table_name in _inspector().get_table_names()


def _column_exists(table_name, column_name):
    if not _table_exists(table_name):
        return False
    return column_name in {column['name'] for column in _inspector().get_columns(table_name)}


def _index_exists(table_name, index_name):
    if not _table_exists(table_name):
        return False
    return index_name in {index['name'] for index in _inspector().get_indexes(table_name)}


def _unique_exists(table_name, constraint_name):
    if not _table_exists(table_name):
        return False
    return constraint_name in {constraint['name'] for constraint in _inspector().get_unique_constraints(table_name)}


def _fk_name(table_name):
    return f'fk_{table_name}_perfil_financeiro'


def _add_perfil_column(table_name):
    if not _table_exists(table_name) or _column_exists(table_name, 'perfil_financeiro_id'):
        return
    op.add_column(table_name, sa.Column('perfil_financeiro_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        _fk_name(table_name),
        table_name,
        'perfil_financeiro',
        ['perfil_financeiro_id'],
        ['id'],
    )


def _create_index(table_name, index_name, columns, unique=False):
    if _table_exists(table_name) and not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_unique_if_exists(table_name, constraint_name):
    if _unique_exists(table_name, constraint_name):
        op.drop_constraint(constraint_name, table_name, type_='unique')


def _ensure_pessoal_id():
    conn = op.get_bind()
    perfil = conn.execute(
        sa.text("SELECT id FROM perfil_financeiro WHERE tipo = 'PESSOAL' ORDER BY id LIMIT 1")
    ).fetchone()
    if perfil:
        return perfil[0]

    conn.execute(sa.text("""
        INSERT INTO perfil_financeiro (nome, tipo, cor, ativo, created_at, updated_at)
        VALUES ('Pessoal', 'PESSOAL', '#2563eb', TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """))
    return conn.execute(
        sa.text("SELECT id FROM perfil_financeiro WHERE tipo = 'PESSOAL' ORDER BY id LIMIT 1")
    ).scalar()


def upgrade():
    pessoal_id = _ensure_pessoal_id()

    for table_name in TABELAS_PERFIL:
        _add_perfil_column(table_name)
        if _table_exists(table_name) and _column_exists(table_name, 'perfil_financeiro_id'):
            op.execute(
                sa.text(f"UPDATE {table_name} SET perfil_financeiro_id = :perfil_id WHERE perfil_financeiro_id IS NULL")
                .bindparams(perfil_id=pessoal_id)
            )

    _drop_unique_if_exists('conta_patrimonio', 'conta_patrimonio_nome_key')
    _drop_unique_if_exists('ir_comprovante', 'ir_comprovante_hash_arquivo_key')
    _drop_unique_if_exists('ir_categoria_despesa', 'ux_ir_categoria_despesa_ir_categoria')

    _create_index('ir_categoria_despesa', 'ix_ir_categoria_despesa_perfil_ativo', ['perfil_financeiro_id', 'ativo'])
    _create_index('ir_comprovante', 'ix_ir_comprovante_perfil_ano', ['perfil_financeiro_id', 'ano_calendario'])
    _create_index('conta_patrimonio', 'idx_conta_patrimonio_perfil_ativo', ['perfil_financeiro_id', 'ativo'])
    _create_index('transferencia', 'idx_transf_perfil_data', ['perfil_financeiro_id', 'data_transferencia'])
    _create_index('financiamento', 'idx_financiamento_perfil_ativo', ['perfil_financeiro_id', 'ativo'])
    _create_index('financiamento_parcela', 'idx_fin_parc_perfil_status', ['perfil_financeiro_id', 'status'])
    _create_index('financiamento_amortizacao_extra', 'idx_amort_perfil_data', ['perfil_financeiro_id', 'data'])
    _create_index('financiamento_seguro_vigencia', 'idx_seguro_vig_perfil_ativa', ['perfil_financeiro_id', 'vigencia_ativa'])
    _create_index('veiculo', 'idx_veiculo_perfil_status', ['perfil_financeiro_id', 'status'])
    _create_index('mobilidade_cenario_ativo', 'idx_mob_cenario_perfil_status', ['perfil_financeiro_id', 'status'])
    _create_index('mobilidade_assinatura', 'idx_mob_assinatura_perfil_status', ['perfil_financeiro_id', 'status'])

    if _table_exists('conta_patrimonio') and not _unique_exists('conta_patrimonio', 'ux_conta_patrimonio_perfil_nome'):
        op.create_unique_constraint('ux_conta_patrimonio_perfil_nome', 'conta_patrimonio', ['perfil_financeiro_id', 'nome'])
    if _table_exists('ir_comprovante') and not _unique_exists('ir_comprovante', 'ux_ir_comprovante_perfil_hash'):
        op.create_unique_constraint('ux_ir_comprovante_perfil_hash', 'ir_comprovante', ['perfil_financeiro_id', 'hash_arquivo'])
    if _table_exists('ir_categoria_despesa') and not _unique_exists('ir_categoria_despesa', 'ux_ir_categoria_despesa_perfil_ir_categoria'):
        op.create_unique_constraint(
            'ux_ir_categoria_despesa_perfil_ir_categoria',
            'ir_categoria_despesa',
            ['perfil_financeiro_id', 'categoria_ir_id', 'categoria_id'],
        )


def downgrade():
    _drop_unique_if_exists('ir_categoria_despesa', 'ux_ir_categoria_despesa_perfil_ir_categoria')
    _drop_unique_if_exists('ir_comprovante', 'ux_ir_comprovante_perfil_hash')
    _drop_unique_if_exists('conta_patrimonio', 'ux_conta_patrimonio_perfil_nome')

    for table_name, index_name in [
        ('mobilidade_assinatura', 'idx_mob_assinatura_perfil_status'),
        ('mobilidade_cenario_ativo', 'idx_mob_cenario_perfil_status'),
        ('veiculo', 'idx_veiculo_perfil_status'),
        ('financiamento_seguro_vigencia', 'idx_seguro_vig_perfil_ativa'),
        ('financiamento_amortizacao_extra', 'idx_amort_perfil_data'),
        ('financiamento_parcela', 'idx_fin_parc_perfil_status'),
        ('financiamento', 'idx_financiamento_perfil_ativo'),
        ('transferencia', 'idx_transf_perfil_data'),
        ('conta_patrimonio', 'idx_conta_patrimonio_perfil_ativo'),
        ('ir_comprovante', 'ix_ir_comprovante_perfil_ano'),
        ('ir_categoria_despesa', 'ix_ir_categoria_despesa_perfil_ativo'),
    ]:
        if _index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name in reversed(TABELAS_PERFIL):
        if _table_exists(table_name) and _column_exists(table_name, 'perfil_financeiro_id'):
            fk = _fk_name(table_name)
            if any(item.get('name') == fk for item in _inspector().get_foreign_keys(table_name)):
                op.drop_constraint(fk, table_name, type_='foreignkey')
            op.drop_column(table_name, 'perfil_financeiro_id')

    if _table_exists('conta_patrimonio') and not _unique_exists('conta_patrimonio', 'conta_patrimonio_nome_key'):
        op.create_unique_constraint('conta_patrimonio_nome_key', 'conta_patrimonio', ['nome'])
    if _table_exists('ir_comprovante') and not _unique_exists('ir_comprovante', 'ir_comprovante_hash_arquivo_key'):
        op.create_unique_constraint('ir_comprovante_hash_arquivo_key', 'ir_comprovante', ['hash_arquivo'])
    if _table_exists('ir_categoria_despesa') and not _unique_exists('ir_categoria_despesa', 'ux_ir_categoria_despesa_ir_categoria'):
        op.create_unique_constraint('ux_ir_categoria_despesa_ir_categoria', 'ir_categoria_despesa', ['categoria_ir_id', 'categoria_id'])
