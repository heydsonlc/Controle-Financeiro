"""documentos fiscais e lastro por contexto

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-05-05 00:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


CATEGORIAS_EMPRESA = [
    ('Despesa operacional', 'Notas, recibos e comprovantes de despesas da operacao', True, 'EMPRESA', 'DESPESA_OPERACIONAL', 10),
    ('Patrimonio / Imobilizado', 'Documentos de compra de bens e equipamentos', True, 'EMPRESA', 'PATRIMONIO_IMOBILIZADO', 20),
    ('Software / Assinaturas', 'Servicos digitais, licencas e assinaturas', True, 'EMPRESA', 'SOFTWARE_ASSINATURA', 30),
    ('Honorarios', 'Honorarios profissionais e servicos recorrentes', True, 'EMPRESA', 'DOCUMENTO_FISCAL', 40),
    ('Impostos e taxas', 'Guias, taxas e obrigacoes fiscais', True, 'EMPRESA', 'IMPOSTO_TAXA', 50),
    ('Pro-labore', 'Documento de suporte para retirada de socio', True, 'EMPRESA', 'PRO_LABORE', 60),
    ('Distribuicao de lucros', 'Documento de suporte para distribuicao de lucros', True, 'EMPRESA', 'DISTRIBUICAO_LUCROS', 70),
    ('Reembolso', 'Reembolsos e prestacoes de contas', True, 'EMPRESA', 'REEMBOLSO', 80),
    ('Emprestimo / Adiantamento', 'Mutuos, adiantamentos e emprestimos', True, 'EMPRESA', 'EMPRESTIMO', 90),
    ('Documento contabil', 'Documento fiscal ou contabil complementar', True, 'EMPRESA', 'DOCUMENTO_CONTABIL', 100),
    ('Outros documentos', 'Documentos empresariais para revisao do contador', False, 'EMPRESA', 'OUTRO', 999),
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


def _fk_exists(table_name, fk_name):
    if not _table_exists(table_name):
        return False
    return fk_name in {fk['name'] for fk in _inspector().get_foreign_keys(table_name)}


def _create_index(table_name, index_name, columns):
    if _table_exists(table_name) and not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade():
    bind = op.get_bind()

    if _table_exists('ir_categoria') and not _column_exists('ir_categoria', 'tipo_contexto'):
        op.add_column('ir_categoria', sa.Column('tipo_contexto', sa.String(length=20), nullable=False, server_default='PESSOAL'))
        op.alter_column('ir_categoria', 'tipo_contexto', server_default=None)
    if _table_exists('ir_categoria') and not _column_exists('ir_categoria', 'natureza'):
        op.add_column('ir_categoria', sa.Column('natureza', sa.String(length=50), nullable=True))

    if _table_exists('ir_categoria'):
        bind.execute(sa.text("""
            UPDATE ir_categoria
               SET tipo_contexto = 'PESSOAL',
                   natureza = COALESCE(natureza, 'DEDUCAO_IRPF')
             WHERE tipo_contexto IS NULL OR tipo_contexto = ''
        """))
        for nome, descricao, dedutivel, tipo_contexto, natureza, ordem in CATEGORIAS_EMPRESA:
            existente = bind.execute(
                sa.text("SELECT id FROM ir_categoria WHERE nome = :nome LIMIT 1"),
                {'nome': nome},
            ).fetchone()
            if existente:
                bind.execute(
                    sa.text("""
                        UPDATE ir_categoria
                           SET tipo_contexto = :tipo_contexto,
                               natureza = COALESCE(natureza, :natureza),
                               descricao = COALESCE(descricao, :descricao)
                         WHERE id = :id
                    """),
                    {
                        'id': existente[0],
                        'tipo_contexto': tipo_contexto,
                        'natureza': natureza,
                        'descricao': descricao,
                    },
                )
                continue
            bind.execute(
                sa.text("""
                    INSERT INTO ir_categoria
                        (nome, descricao, dedutivel, ativo, observacao_fiscal, ordem, tipo_contexto, natureza, created_at, updated_at)
                    VALUES
                        (:nome, :descricao, :dedutivel, true, :observacao, :ordem, :tipo_contexto, :natureza, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """),
                {
                    'nome': nome,
                    'descricao': descricao,
                    'dedutivel': dedutivel,
                    'observacao': 'Classificacao informativa, sujeita a validacao contabil.',
                    'ordem': ordem,
                    'tipo_contexto': tipo_contexto,
                    'natureza': natureza,
                },
            )

    if not _table_exists('ir_comprovante_vinculo'):
        op.create_table(
            'ir_comprovante_vinculo',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('comprovante_id', sa.Integer(), nullable=False),
            sa.Column('perfil_financeiro_id', sa.Integer(), nullable=True),
            sa.Column('tipo_entidade', sa.String(length=40), nullable=False),
            sa.Column('entidade_id', sa.Integer(), nullable=True),
            sa.Column('resumo_entidade', sa.String(length=255), nullable=True),
            sa.Column('tipo_vinculo', sa.String(length=40), nullable=False),
            sa.Column('natureza', sa.String(length=50), nullable=False),
            sa.Column('status_lastro', sa.String(length=40), nullable=False),
            sa.Column('observacoes', sa.Text(), nullable=True),
            sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['comprovante_id'], ['ir_comprovante.id']),
            sa.ForeignKeyConstraint(['perfil_financeiro_id'], ['perfil_financeiro.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.alter_column('ir_comprovante_vinculo', 'ativo', server_default=None)
    elif not _fk_exists('ir_comprovante_vinculo', 'fk_ir_comprovante_vinculo_perfil_financeiro'):
        pass

    _create_index('ir_comprovante_vinculo', 'ix_ir_comprovante_vinculo_comprovante', ['comprovante_id'])
    _create_index('ir_comprovante_vinculo', 'ix_ir_comprovante_vinculo_perfil_financeiro_id', ['perfil_financeiro_id'])
    _create_index('ir_comprovante_vinculo', 'ix_ir_comprovante_vinculo_perfil_status', ['perfil_financeiro_id', 'status_lastro'])
    _create_index('ir_comprovante_vinculo', 'ix_ir_comprovante_vinculo_entidade', ['tipo_entidade', 'entidade_id'])


def downgrade():
    if _index_exists('ir_comprovante_vinculo', 'ix_ir_comprovante_vinculo_entidade'):
        op.drop_index('ix_ir_comprovante_vinculo_entidade', table_name='ir_comprovante_vinculo')
    if _index_exists('ir_comprovante_vinculo', 'ix_ir_comprovante_vinculo_perfil_status'):
        op.drop_index('ix_ir_comprovante_vinculo_perfil_status', table_name='ir_comprovante_vinculo')
    if _index_exists('ir_comprovante_vinculo', 'ix_ir_comprovante_vinculo_perfil_financeiro_id'):
        op.drop_index('ix_ir_comprovante_vinculo_perfil_financeiro_id', table_name='ir_comprovante_vinculo')
    if _index_exists('ir_comprovante_vinculo', 'ix_ir_comprovante_vinculo_comprovante'):
        op.drop_index('ix_ir_comprovante_vinculo_comprovante', table_name='ir_comprovante_vinculo')
    if _table_exists('ir_comprovante_vinculo'):
        op.drop_table('ir_comprovante_vinculo')
    if _column_exists('ir_categoria', 'natureza'):
        op.drop_column('ir_categoria', 'natureza')
    if _column_exists('ir_categoria', 'tipo_contexto'):
        op.drop_column('ir_categoria', 'tipo_contexto')
