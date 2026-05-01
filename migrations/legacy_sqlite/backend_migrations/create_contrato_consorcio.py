"""
Migração: Criar tabela contrato_consorcio

Esta tabela armazena os contratos de consórcio que geram automaticamente
parcelas de despesas e receitas na contemplação.

Data: 2025-11-28
"""

import sqlite3
import os
import sys

# Adicionar o diretório backend ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_migration():
    """Executa a migração para criar tabela contrato_consorcio"""

    # Caminho do banco de dados
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    project_dir = os.path.dirname(backend_dir)
    db_path = os.path.join(project_dir, 'data', 'gastos.db')

    print(f"[*] Conectando ao banco de dados: {db_path}")

    try:
        # Conectar ao banco
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Verificar se a tabela já existe
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='contrato_consorcio'
        """)

        if cursor.fetchone():
            print("[OK] Tabela 'contrato_consorcio' ja existe")
            return

        print("[*] Criando tabela 'contrato_consorcio'...")

        # Criar a tabela
        cursor.execute("""
            CREATE TABLE contrato_consorcio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome VARCHAR(100) NOT NULL,
                valor_inicial NUMERIC(10, 2) NOT NULL,
                taxa_correcao NUMERIC(5, 2) DEFAULT 0,
                tipo_reajuste VARCHAR(20) DEFAULT 'nenhum',
                valor_reajuste NUMERIC(10, 2) DEFAULT 0,
                numero_parcelas INTEGER NOT NULL,
                mes_inicio DATE NOT NULL,
                mes_contemplacao DATE,
                valor_premio NUMERIC(10, 2),
                item_despesa_id INTEGER,
                item_receita_id INTEGER,
                ativo BOOLEAN DEFAULT 1,
                observacoes TEXT,
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_despesa_id) REFERENCES item_despesa(id),
                FOREIGN KEY (item_receita_id) REFERENCES item_receita(id)
            )
        """)

        # Commit das mudanças
        conn.commit()

        print("[OK] Migracao concluida com sucesso!")
        print("   - Tabela 'contrato_consorcio' criada")

    except Exception as e:
        print(f"[ERRO] Erro na migracao: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("MIGRACAO: Criar tabela contrato_consorcio")
    print("=" * 60)
    run_migration()
    print("=" * 60)
