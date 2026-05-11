"""adiciona categorias sistemicas de mobilidade

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-05-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a9b0c1d2e3f4'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


CATEGORIAS_MOBILIDADE = [
    ('MOB_COMBUSTIVEL', 'Combustível', 'Combustível e abastecimento de veículos.', '#f97316', 'fuel'),
    ('MOB_SEGURO_VEICULAR', 'Seguro Veicular', 'Seguro do veículo.', '#2563eb', 'shield'),
    ('MOB_TRIBUTOS_VEICULARES', 'Tributos Veiculares', 'IPVA, licenciamento e taxas obrigatórias similares.', '#7c3aed', 'receipt'),
    ('MOB_REVISAO', 'Revisão', 'Revisões programadas do veículo.', '#0891b2', 'clipboard-check'),
    ('MOB_MANUTENCAO', 'Manutenção Veicular', 'Manutenção geral, preventiva ou corretiva.', '#475569', 'wrench'),
    ('MOB_PNEUS', 'Pneus', 'Pneus, troca de pneus e alinhamento associado.', '#111827', 'circle'),
    ('MOB_USO_VEICULO', 'Uso do Veículo', 'Estacionamento, pedágio e custos de uso do carro próprio.', '#0f766e', 'road'),
    ('MOB_APP', 'Transporte por Aplicativo', 'Uber, 99, táxi e aplicativos similares.', '#16a34a', 'smartphone'),
    ('MOB_ASSINATURA', 'Assinatura Veicular', 'Carro por assinatura.', '#9333ea', 'calendar'),
    ('MOB_LAVAGEM', 'Lavagem Veicular', 'Lavagem, higienização e lava-jato.', '#0284c7', 'sparkles'),
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


def _unique_constraint_exists(table_name, constraint_name):
    if not _table_exists(table_name):
        return False
    return constraint_name in {constraint['name'] for constraint in _insp().get_unique_constraints(table_name)}


def _seed_categorias(bind):
    for codigo, nome, descricao, cor, icone in CATEGORIAS_MOBILIDADE:
        bind.execute(
            sa.text(
                """
                UPDATE categoria
                SET
                    nome = :nome,
                    descricao = :descricao,
                    cor = :cor,
                    icone = :icone,
                    ativo = true,
                    sistemica = true,
                    codigo_sistema = :codigo,
                    modulo_origem = 'mobilidade',
                    bloquear_edicao = true,
                    bloquear_exclusao = true
                WHERE codigo_sistema = :codigo
                   OR (codigo_sistema IS NULL AND LOWER(TRIM(nome)) = LOWER(:nome))
                """
            ),
            {
                'codigo': codigo,
                'nome': nome,
                'descricao': descricao,
                'cor': cor,
                'icone': icone,
            },
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO categoria
                    (nome, descricao, cor, icone, ativo, sistemica, codigo_sistema,
                     modulo_origem, bloquear_edicao, bloquear_exclusao, criado_em)
                SELECT
                    :nome, :descricao, :cor, :icone, true, true, :codigo,
                    'mobilidade', true, true, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                    SELECT 1 FROM categoria WHERE codigo_sistema = :codigo
                )
                """
            ),
            {
                'codigo': codigo,
                'nome': nome,
                'descricao': descricao,
                'cor': cor,
                'icone': icone,
            },
        )


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if not _table_exists('categoria'):
        return

    if not _column_exists('categoria', 'sistemica'):
        op.add_column('categoria', sa.Column('sistemica', sa.Boolean(), nullable=False, server_default=sa.false()))
    if not _column_exists('categoria', 'codigo_sistema'):
        op.add_column('categoria', sa.Column('codigo_sistema', sa.String(length=80), nullable=True))
    if not _column_exists('categoria', 'modulo_origem'):
        op.add_column('categoria', sa.Column('modulo_origem', sa.String(length=50), nullable=True))
    if not _column_exists('categoria', 'bloquear_edicao'):
        op.add_column('categoria', sa.Column('bloquear_edicao', sa.Boolean(), nullable=False, server_default=sa.false()))
    if not _column_exists('categoria', 'bloquear_exclusao'):
        op.add_column('categoria', sa.Column('bloquear_exclusao', sa.Boolean(), nullable=False, server_default=sa.false()))

    if dialect == 'postgresql':
        if not _unique_constraint_exists('categoria', 'ux_categoria_codigo_sistema'):
            op.create_unique_constraint('ux_categoria_codigo_sistema', 'categoria', ['codigo_sistema'])
    elif not _index_exists('categoria', 'ux_categoria_codigo_sistema'):
        op.create_index('ux_categoria_codigo_sistema', 'categoria', ['codigo_sistema'], unique=True)

    if not _index_exists('categoria', 'ix_categoria_sistemica_modulo'):
        op.create_index('ix_categoria_sistemica_modulo', 'categoria', ['sistemica', 'modulo_origem'])

    _seed_categorias(bind)


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if not _table_exists('categoria'):
        return

    if _index_exists('categoria', 'ix_categoria_sistemica_modulo'):
        op.drop_index('ix_categoria_sistemica_modulo', table_name='categoria')

    if dialect == 'postgresql':
        if _unique_constraint_exists('categoria', 'ux_categoria_codigo_sistema'):
            op.drop_constraint('ux_categoria_codigo_sistema', 'categoria', type_='unique')
    elif _index_exists('categoria', 'ux_categoria_codigo_sistema'):
        op.drop_index('ux_categoria_codigo_sistema', table_name='categoria')

    for column in ('bloquear_exclusao', 'bloquear_edicao', 'modulo_origem', 'codigo_sistema', 'sistemica'):
        if _column_exists('categoria', column):
            op.drop_column('categoria', column)
