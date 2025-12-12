"""
Migration: Adicionar campo taxa_administracao_fixa ao modelo Financiamento

Executar com: python backend/migrations/add_taxa_administracao_financiamento.py
"""
from sqlalchemy import create_engine, text
import os

# Caminho do banco de dados
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'financeiro.db')
DATABASE_URI = f'sqlite:///{DB_PATH}'

def upgrade():
    """Adiciona coluna taxa_administracao_fixa à tabela financiamento"""
    engine = create_engine(DATABASE_URI)

    with engine.connect() as conn:
        # Verificar se a coluna já existe
        result = conn.execute(text("PRAGMA table_info(financiamento)"))
        columns = [row[1] for row in result.fetchall()]

        if 'taxa_administracao_fixa' not in columns:
            print("Adicionando coluna taxa_administracao_fixa...")
            conn.execute(text("""
                ALTER TABLE financiamento
                ADD COLUMN taxa_administracao_fixa NUMERIC(10, 2) DEFAULT 0
            """))
            conn.commit()
            print("✓ Coluna taxa_administracao_fixa adicionada com sucesso!")
        else:
            print("✓ Coluna taxa_administracao_fixa já existe")

def downgrade():
    """Remove coluna taxa_administracao_fixa (SQLite não suporta DROP COLUMN diretamente)"""
    print("⚠ SQLite não suporta DROP COLUMN. Para reverter, seria necessário recriar a tabela.")

if __name__ == '__main__':
    print("=== Migration: Adicionar taxa_administracao_fixa ===")
    upgrade()
    print("=== Migration concluída ===")
