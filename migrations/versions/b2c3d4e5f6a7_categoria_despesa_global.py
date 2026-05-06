"""categoria despesa global — remove isolamento por perfil em Categoria de Despesa

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-06 12:00:00.000000

Regra aplicada:
  - Categoria de Despesa passa a ser global (compartilhada entre perfis).
  - CategoriaCartao e CategoriaCartaoDespesa permanecem por perfil.
  - IrCategoriaDespesa permanece por perfil/contexto.

Estrategia de deduplicacao:
  - Para categorias com mesmo nome normalizado (lowercase + trim):
    * Prefere categoria ativa.
    * Em empate, prefere menor id (canonica mais antiga).
  - Referencias migradas da duplicada para a canonica nas tabelas relevantes.
  - Palavras-chave das duplicadas movidas para a canonica (deduplicadas).
  - Categorias duplicadas inativadas (nao removidas).
  - Constraint ux_categoria_perfil_nome substituida por ux_categoria_nome_global.
  - Coluna perfil_financeiro_id mantida como legado (deixa de ser usada funcionalmente).
"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def _table_exists(insp, table):
    return table in insp.get_table_names()


def _column_exists(insp, table, column):
    if not _table_exists(insp, table):
        return False
    return column in {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # ----------------------------------------------------------------
    # 1. Identificar e deduplicar categorias por nome (case-insensitive)
    # ----------------------------------------------------------------
    # Seleciona grupos com nome repetido (case-insensitive); dentro de cada
    # grupo escolhe o id canonico (ativo preferido, menor id como desempate).
    # Retorna pares (id_duplicado, id_canonico) para migrar referencias.
    resultado = bind.execute(sa.text("""
        SELECT dup.id AS dup_id, can.id AS can_id
        FROM categoria dup
        JOIN (
            SELECT LOWER(TRIM(nome)) AS nome_norm,
                   MIN(CASE WHEN ativo THEN 0 ELSE 1 END * 1000000 + id) AS sort_key
            FROM categoria
            GROUP BY LOWER(TRIM(nome))
            HAVING COUNT(*) > 1
        ) grp ON LOWER(TRIM(dup.nome)) = grp.nome_norm
        JOIN categoria can ON can.id = (
            SELECT id FROM categoria
            WHERE LOWER(TRIM(nome)) = grp.nome_norm
            ORDER BY CASE WHEN ativo THEN 0 ELSE 1 END, id
            LIMIT 1
        )
        WHERE dup.id != can.id
    """)).fetchall()

    pares = [(row[0], row[1]) for row in resultado]

    # Tabelas que referenciam categoria.id — verificar existencia antes de atualizar
    REFS = [
        ('item_despesa', 'categoria_id'),
        ('lancamento_agregado', 'categoria_id'),
        ('despesa_prevista', 'categoria_id'),
        ('ir_comprovante', 'categoria_id'),
        ('categoria_cartao_despesa', 'categoria_id'),
        ('ir_categoria_despesa', 'categoria_id'),
        ('mobilidade_cenario_ativo', 'categoria_id'),
    ]

    for dup_id, can_id in pares:
        for table, col in REFS:
            if _column_exists(insp, table, col):
                bind.execute(sa.text(
                    f'UPDATE {table} SET {col} = :can WHERE {col} = :dup'
                ), {'can': can_id, 'dup': dup_id})

        # Migrar palavras-chave (deduplicar por palavra)
        if _table_exists(insp, 'categoria_palavra_chave'):
            # Palavras que já existem na canonica — só inativar na duplicada
            bind.execute(sa.text("""
                UPDATE categoria_palavra_chave
                SET ativo = 0
                WHERE categoria_id = :dup
                  AND palavra IN (
                      SELECT palavra FROM categoria_palavra_chave
                      WHERE categoria_id = :can AND ativo = 1
                  )
            """), {'dup': dup_id, 'can': can_id})
            # Mover restantes para a canonica
            bind.execute(sa.text("""
                UPDATE categoria_palavra_chave
                SET categoria_id = :can
                WHERE categoria_id = :dup
            """), {'dup': dup_id, 'can': can_id})

        # Inativar categoria duplicada
        bind.execute(sa.text(
            'UPDATE categoria SET ativo = 0 WHERE id = :dup'
        ), {'dup': dup_id})

    # ----------------------------------------------------------------
    # 2. Substituir constraint de unicidade por perfil → unicidade global
    # ----------------------------------------------------------------
    constraints = {c['name'] for c in insp.get_unique_constraints('categoria')} if _table_exists(insp, 'categoria') else set()

    # Detectar dialect para syntax correta
    dialect = bind.dialect.name  # 'postgresql' ou 'sqlite'

    if 'ux_categoria_perfil_nome' in constraints:
        if dialect == 'postgresql':
            op.drop_constraint('ux_categoria_perfil_nome', 'categoria', type_='unique')
        else:
            # SQLite nao suporta DROP CONSTRAINT — recriar tabela nao é trivial;
            # a constraint sera gerenciada na camada de servico.
            pass

    # Adicionar constraint global se ainda nao existir
    if 'ux_categoria_nome_global' not in constraints:
        if dialect == 'postgresql':
            op.create_unique_constraint('ux_categoria_nome_global', 'categoria', ['nome'])
        # SQLite: gerenciado no service (sem suporte nativo a ADD CONSTRAINT)


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == 'postgresql':
        try:
            op.drop_constraint('ux_categoria_nome_global', 'categoria', type_='unique')
        except Exception:
            pass
        try:
            op.create_unique_constraint('ux_categoria_perfil_nome', 'categoria', ['perfil_financeiro_id', 'nome'])
        except Exception:
            pass
