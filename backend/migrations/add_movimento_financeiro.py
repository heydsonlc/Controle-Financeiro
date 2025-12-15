"""
Migration: Adicionar tabela de movimentações financeiras

Permite registrar débitos/créditos em contas bancárias quando faturas são pagas

Mudanças:
- Nova tabela: movimento_financeiro
  - Registra DEBITO ou CREDITO
  - Impacta saldo_atual de ContaBancaria
  - Opcional: vinculado a fatura_id (para pagamentos de cartão)

Executar com: python backend/migrations/add_movimento_financeiro.py
"""
from sqlalchemy import create_engine, text
import os
from datetime import datetime

# Caminho do banco de dados
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'financeiro.db')
DATABASE_URI = f'sqlite:///{DB_PATH}'

def upgrade():
    """Adiciona tabela movimento_financeiro"""
    engine = create_engine(DATABASE_URI)

    with engine.connect() as conn:
        # ==================================================================
        # CRIAR TABELA MOVIMENTO_FINANCEIRO
        # ==================================================================
        result = conn.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='movimento_financeiro'
        """))

        if not result.fetchone():
            print("Criando tabela movimento_financeiro...")
            conn.execute(text("""
                CREATE TABLE movimento_financeiro (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conta_bancaria_id INTEGER NOT NULL REFERENCES conta_bancaria(id),
                    tipo VARCHAR(20) NOT NULL,
                    valor NUMERIC(15, 2) NOT NULL,
                    descricao VARCHAR(200) NOT NULL,
                    data_movimento DATE NOT NULL,
                    fatura_id INTEGER REFERENCES conta(id),
                    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("OK - Tabela movimento_financeiro criada")

            # Criar índices
            print("Criando índices...")
            conn.execute(text("""
                CREATE INDEX idx_movimento_conta ON movimento_financeiro(conta_bancaria_id)
            """))
            conn.execute(text("""
                CREATE INDEX idx_movimento_data ON movimento_financeiro(data_movimento)
            """))
            conn.execute(text("""
                CREATE INDEX idx_movimento_fatura ON movimento_financeiro(fatura_id)
            """))
            conn.commit()
            print("OK - Índices criados")
        else:
            print("OK - Tabela movimento_financeiro já existe")

        print("\n=== REGRAS DE NEGÓCIO ===")
        print("1. Movimentos são criados automaticamente ao pagar faturas")
        print("2. Tipo DEBITO = saída de dinheiro (pagamento)")
        print("3. Tipo CREDITO = entrada de dinheiro")
        print("4. fatura_id é opcional (NULL para movimentos não relacionados a faturas)")
        print("5. Cada movimento impacta o saldo_atual da conta bancária")

        print("\nOK - Migração concluída com sucesso!")

def downgrade():
    """Remove tabela movimento_financeiro"""
    engine = create_engine(DATABASE_URI)
    with engine.connect() as conn:
        print("Removendo tabela movimento_financeiro...")
        conn.execute(text("DROP TABLE IF EXISTS movimento_financeiro"))
        conn.commit()
        print("OK - Tabela movimento_financeiro removida")

if __name__ == '__main__':
    print("=== Migration: Adicionar tabela MovimentoFinanceiro ===\n")
    upgrade()
    print("\n=== Migration concluída ===")
