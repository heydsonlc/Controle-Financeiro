"""add_perfil_financeiro_padrao

Revision ID: c1d2e3f4a5b6
Revises: b9d2e3f4a5c6
Create Date: 2026-05-04 23:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c1d2e3f4a5b6'
down_revision = 'b9d2e3f4a5c6'
branch_labels = None
depends_on = None


def _column_exists(bind, table_name, column_name):
    inspector = sa.inspect(bind)
    return column_name in {column['name'] for column in inspector.get_columns(table_name)}


def _index_exists(bind, table_name, index_name):
    inspector = sa.inspect(bind)
    return index_name in {index['name'] for index in inspector.get_indexes(table_name)}


def upgrade():
    bind = op.get_bind()

    if not _column_exists(bind, 'perfil_financeiro', 'padrao'):
        op.add_column(
            'perfil_financeiro',
            sa.Column('padrao', sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.alter_column('perfil_financeiro', 'padrao', server_default=None)

    if not _index_exists(bind, 'perfil_financeiro', 'ix_perfil_financeiro_padrao'):
        op.create_index('ix_perfil_financeiro_padrao', 'perfil_financeiro', ['padrao'], unique=False)

    pessoal_id = bind.execute(
        sa.text("SELECT id FROM perfil_financeiro WHERE nome = 'Pessoal' ORDER BY id LIMIT 1")
    ).scalar()
    if pessoal_id is None:
        bind.execute(sa.text("""
            INSERT INTO perfil_financeiro (nome, tipo, avatar, cor, ativo, padrao, created_at, updated_at)
            VALUES ('Pessoal', 'PESSOAL', 'PE', '#2563eb', true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
        pessoal_id = bind.execute(
            sa.text("SELECT id FROM perfil_financeiro WHERE nome = 'Pessoal' ORDER BY id LIMIT 1")
        ).scalar()

    bind.execute(sa.text("UPDATE perfil_financeiro SET padrao = false"))
    bind.execute(sa.text("UPDATE perfil_financeiro SET ativo = true, padrao = true WHERE id = :id"), {'id': pessoal_id})


def downgrade():
    bind = op.get_bind()
    if _index_exists(bind, 'perfil_financeiro', 'ix_perfil_financeiro_padrao'):
        op.drop_index('ix_perfil_financeiro_padrao', table_name='perfil_financeiro')
    if _column_exists(bind, 'perfil_financeiro', 'padrao'):
        op.drop_column('perfil_financeiro', 'padrao')
