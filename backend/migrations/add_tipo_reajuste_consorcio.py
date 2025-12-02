"""
Migração: Adicionar campos tipo_reajuste e valor_reajuste à tabela contrato_consorcio

Estes campos permitem definir se o reajuste das parcelas é por valor fixo ou percentual.

Data: 2025-11-28
"""

import sqlite3
import os
import sys

# Adicionar o diretório backend ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_migration():
    """Executa a migração para adicionar campos de reajuste"""

    # Caminho do banco de dados
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    project_dir = os.path.dirname(backend_dir)
    db_path = os.path.join(project_dir, 'data', 'gastos.db')

    print(f"[*] Conectando ao banco de dados: {db_path}")

    try:
        # Conectar ao banco
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Verificar se as colunas já existem
        cursor.execute("PRAGMA table_info(contrato_consorcio)")
        columns = [column[1] for column in cursor.fetchall()]

        alteracoes = []

        if 'tipo_reajuste' not in columns:
            print("[*] Adicionando campo 'tipo_reajuste'...")
            cursor.execute("""
                ALTER TABLE contrato_consorcio
                ADD COLUMN tipo_reajuste VARCHAR(20) DEFAULT 'nenhum'
            """)
            alteracoes.append("tipo_reajuste")
        else:
            print("[OK] Campo 'tipo_reajuste' ja existe")

        if 'valor_reajuste' not in columns:
            print("[*] Adicionando campo 'valor_reajuste'...")
            cursor.execute("""
                ALTER TABLE contrato_consorcio
                ADD COLUMN valor_reajuste NUMERIC(10, 2) DEFAULT 0
            """)
            alteracoes.append("valor_reajuste")
        else:
            print("[OK] Campo 'valor_reajuste' ja existe")

        if alteracoes:
            # Commit das mudanças
            conn.commit()
            print("[OK] Migracao concluida com sucesso!")
            print(f"   - Campos adicionados: {', '.join(alteracoes)}")
        else:
            print("[OK] Nenhuma alteracao necessaria")

    except Exception as e:
        print(f"[ERRO] Erro na migracao: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("MIGRACAO: Adicionar campos de reajuste ao consorcio")
    print("=" * 60)
    run_migration()
    print("=" * 60)
