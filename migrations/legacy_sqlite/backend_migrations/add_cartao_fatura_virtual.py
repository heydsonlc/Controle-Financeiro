"""
Migration: Adicionar campos para suporte a faturas virtuais de cartão

Campos adicionados:
- Conta: is_fatura_cartao, valor_planejado, valor_executado, estouro_orcamento, cartao_competencia
- OrcamentoAgregado: vigencia_inicio, vigencia_fim, ativo

Executar com: python backend/migrations/add_cartao_fatura_virtual.py
"""
from sqlalchemy import create_engine, text
import os
from datetime import date

# Caminho do banco de dados
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'financeiro.db')
DATABASE_URI = f'sqlite:///{DB_PATH}'

def upgrade():
    """Adiciona colunas para faturas virtuais de cartão"""
    engine = create_engine(DATABASE_URI)

    with engine.connect() as conn:
        # ==================================================================
        # TABELA CONTA - Adicionar campos de fatura virtual
        # ==================================================================
        result = conn.execute(text("PRAGMA table_info(conta)"))
        columns = [row[1] for row in result.fetchall()]

        if 'is_fatura_cartao' not in columns:
            print("Adicionando coluna is_fatura_cartao...")
            conn.execute(text("""
                ALTER TABLE conta
                ADD COLUMN is_fatura_cartao BOOLEAN DEFAULT 0
            """))
            conn.commit()
            print("OK - Coluna is_fatura_cartao adicionada")
        else:
            print("OK - Coluna is_fatura_cartao ja existe")

        if 'valor_planejado' not in columns:
            print("Adicionando coluna valor_planejado...")
            conn.execute(text("""
                ALTER TABLE conta
                ADD COLUMN valor_planejado NUMERIC(10, 2)
            """))
            conn.commit()
            print("OK - Coluna valor_planejado adicionada")
        else:
            print("OK - Coluna valor_planejado ja existe")

        if 'valor_executado' not in columns:
            print("Adicionando coluna valor_executado...")
            conn.execute(text("""
                ALTER TABLE conta
                ADD COLUMN valor_executado NUMERIC(10, 2)
            """))
            conn.commit()
            print("OK - Coluna valor_executado adicionada")
        else:
            print("OK - Coluna valor_executado ja existe")

        if 'estouro_orcamento' not in columns:
            print("Adicionando coluna estouro_orcamento...")
            conn.execute(text("""
                ALTER TABLE conta
                ADD COLUMN estouro_orcamento BOOLEAN DEFAULT 0
            """))
            conn.commit()
            print("OK - Coluna estouro_orcamento adicionada")
        else:
            print("OK - Coluna estouro_orcamento ja existe")

        if 'cartao_competencia' not in columns:
            print("Adicionando coluna cartao_competencia...")
            conn.execute(text("""
                ALTER TABLE conta
                ADD COLUMN cartao_competencia DATE
            """))
            conn.commit()
            print("OK - Coluna cartao_competencia adicionada")
        else:
            print("OK - Coluna cartao_competencia ja existe")

        # ==================================================================
        # TABELA ORCAMENTO_AGREGADO - Adicionar histórico de vigência
        # ==================================================================
        result = conn.execute(text("PRAGMA table_info(orcamento_agregado)"))
        columns = [row[1] for row in result.fetchall()]

        if 'vigencia_inicio' not in columns:
            print("Adicionando coluna vigencia_inicio...")
            conn.execute(text("""
                ALTER TABLE orcamento_agregado
                ADD COLUMN vigencia_inicio DATE
            """))
            conn.commit()
            print("OK - Coluna vigencia_inicio adicionada")

            # Atualizar registros existentes com primeiro dia do mês_referencia
            print("Atualizando registros existentes com vigencia_inicio...")
            conn.execute(text("""
                UPDATE orcamento_agregado
                SET vigencia_inicio = DATE(mes_referencia, 'start of month')
                WHERE vigencia_inicio IS NULL
            """))
            conn.commit()
            print("OK - Registros atualizados")
        else:
            print("OK - Coluna vigencia_inicio ja existe")

        if 'vigencia_fim' not in columns:
            print("Adicionando coluna vigencia_fim...")
            conn.execute(text("""
                ALTER TABLE orcamento_agregado
                ADD COLUMN vigencia_fim DATE
            """))
            conn.commit()
            print("OK - Coluna vigencia_fim adicionada (NULL = vigencia atual)")
        else:
            print("OK - Coluna vigencia_fim ja existe")

        if 'ativo' not in columns:
            print("Adicionando coluna ativo...")
            conn.execute(text("""
                ALTER TABLE orcamento_agregado
                ADD COLUMN ativo BOOLEAN DEFAULT 1
            """))
            conn.commit()
            print("OK - Coluna ativo adicionada")

            # Marcar todos os registros existentes como ativos
            print("Marcando registros existentes como ativos...")
            conn.execute(text("""
                UPDATE orcamento_agregado
                SET ativo = 1
                WHERE ativo IS NULL
            """))
            conn.commit()
            print("OK - Registros marcados como ativos")
        else:
            print("OK - Coluna ativo ja existe")

        print("\nOK - Migracao concluida com sucesso!")

def downgrade():
    """Remove colunas (SQLite não suporta DROP COLUMN diretamente)"""
    print("AVISO - SQLite nao suporta DROP COLUMN. Para reverter, seria necessario recriar as tabelas.")

if __name__ == '__main__':
    print("=== Migration: Adicionar campos para faturas virtuais de cartao ===\n")
    upgrade()
    print("\n=== Migration concluida ===")
