"""
Migration: Adicionar suporte a Grupos Agregadores para categorias compartilhadas entre cartões

Permite que casais/famílias agrupem categorias de diferentes cartões para:
- Análise consolidada (ex: Farmácia Cartão A + Farmácia Cartão B)
- Alertas de limite total compartilhado
- Planejamento familiar

IMPORTANTE: Grupos são apenas para consolidação e análise.
NÃO possuem orçamento próprio, NÃO bloqueiam lançamentos.

Mudanças:
- Nova tabela: grupo_agregador (id, nome, descricao, ativo, criado_em)
- Nova coluna em item_agregado: grupo_agregador_id (nullable FK)

Executar com: python backend/migrations/add_grupo_agregador.py
"""
from sqlalchemy import create_engine, text
import os
from datetime import datetime

# Caminho do banco de dados
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'financeiro.db')
DATABASE_URI = f'sqlite:///{DB_PATH}'

def upgrade():
    """Adiciona suporte a grupos agregadores"""
    engine = create_engine(DATABASE_URI)

    with engine.connect() as conn:
        # ==================================================================
        # CRIAR TABELA GRUPO_AGREGADOR
        # ==================================================================
        result = conn.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='grupo_agregador'
        """))

        if not result.fetchone():
            print("Criando tabela grupo_agregador...")
            conn.execute(text("""
                CREATE TABLE grupo_agregador (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome VARCHAR(100) NOT NULL UNIQUE,
                    descricao TEXT,
                    ativo BOOLEAN DEFAULT 1,
                    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("OK - Tabela grupo_agregador criada")
        else:
            print("OK - Tabela grupo_agregador ja existe")

        # ==================================================================
        # ADICIONAR COLUNA grupo_agregador_id EM item_agregado
        # ==================================================================
        result = conn.execute(text("PRAGMA table_info(item_agregado)"))
        columns = [row[1] for row in result.fetchall()]

        if 'grupo_agregador_id' not in columns:
            print("Adicionando coluna grupo_agregador_id em item_agregado...")
            conn.execute(text("""
                ALTER TABLE item_agregado
                ADD COLUMN grupo_agregador_id INTEGER REFERENCES grupo_agregador(id)
            """))
            conn.commit()
            print("OK - Coluna grupo_agregador_id adicionada")
            print("    (NULL = categoria sem agrupamento, apenas do cartão individual)")
        else:
            print("OK - Coluna grupo_agregador_id ja existe")

        print("\n=== REGRAS DE NEGÓCIO ===")
        print("1. Categorias podem ter o mesmo nome em cartões diferentes")
        print("2. Grupos são opcionais (grupo_agregador_id pode ser NULL)")
        print("3. Grupos NÃO possuem orçamento próprio")
        print("4. Grupos NÃO bloqueiam lançamentos")
        print("5. Cada cartão possui seu próprio orçamento (dono do budget)")
        print("6. Grupos servem apenas para consolidação e alertas futuros")

        print("\nOK - Migracao concluida com sucesso!")

def downgrade():
    """Remove alterações (SQLite limitado para DROP COLUMN)"""
    print("AVISO - SQLite nao suporta DROP COLUMN diretamente.")
    print("Para reverter completamente seria necessario recriar as tabelas.")

    engine = create_engine(DATABASE_URI)
    with engine.connect() as conn:
        # Podemos remover a tabela grupo_agregador
        print("Removendo tabela grupo_agregador...")
        conn.execute(text("DROP TABLE IF EXISTS grupo_agregador"))
        conn.commit()
        print("OK - Tabela grupo_agregador removida")

if __name__ == '__main__':
    print("=== Migration: Adicionar Grupos Agregadores para Categorias Compartilhadas ===\n")
    upgrade()
    print("\n=== Migration concluida ===")
