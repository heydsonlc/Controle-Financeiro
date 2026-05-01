"""
Migração: Adicionar campo valor_pago à tabela item_despesa

Este campo permite rastrear o valor realmente pago de uma despesa,
que pode ser diferente do valor previsto/orçado.

Data: 2025-11-28
"""

import sqlite3
import os
import sys

# Adicionar o diretório backend ao path para importar os modelos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_migration():
    """Executa a migração para adicionar campo valor_pago"""

    # Caminho do banco de dados
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    project_dir = os.path.dirname(backend_dir)
    db_path = os.path.join(project_dir, 'data', 'gastos.db')

    print(f"[*] Conectando ao banco de dados: {db_path}")

    try:
        # Conectar ao banco
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Verificar se a coluna já existe
        cursor.execute("PRAGMA table_info(item_despesa)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'valor_pago' in columns:
            print("[OK] Campo 'valor_pago' ja existe na tabela item_despesa")
            return

        print("[*] Adicionando campo 'valor_pago' a tabela item_despesa...")

        # Adicionar a coluna valor_pago
        cursor.execute("""
            ALTER TABLE item_despesa
            ADD COLUMN valor_pago NUMERIC(10, 2)
        """)

        # Para despesas já pagas, copiar o valor previsto para valor_pago
        print("[*] Atualizando despesas ja pagas...")
        cursor.execute("""
            UPDATE item_despesa
            SET valor_pago = valor
            WHERE pago = 1 AND valor_pago IS NULL
        """)

        # Commit das mudanças
        conn.commit()

        print("[OK] Migracao concluida com sucesso!")
        print(f"   - Campo 'valor_pago' adicionado")

        # Mostrar estatísticas
        cursor.execute("SELECT COUNT(*) FROM item_despesa WHERE pago = 1")
        despesas_pagas = cursor.fetchone()[0]
        print(f"   - {despesas_pagas} despesas pagas atualizadas com valor_pago")

    except Exception as e:
        print(f"[ERRO] Erro na migracao: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("MIGRAÇÃO: Adicionar campo valor_pago")
    print("=" * 60)
    run_migration()
    print("=" * 60)
