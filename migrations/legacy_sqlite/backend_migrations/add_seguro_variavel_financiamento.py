"""
Migração: Adicionar campos de seguro variável à tabela financiamento

Adiciona três novos campos para suportar seguro variável baseado em percentual do saldo:
- seguro_tipo: tipo de seguro ('fixo' ou 'percentual_saldo')
- seguro_percentual: percentual aplicado sobre o saldo (ex: 0.0006 = 0.06%)
- valor_seguro_mensal: mantido para compatibilidade com contratos existentes (tipo fixo)

Data: 2025-12-04
"""

import sqlite3
import os
import sys

# Adicionar o diretório backend ao path para importar os modelos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_migration():
    """Executa a migração para adicionar campos de seguro variável"""

    # Caminho do banco de dados
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    project_dir = os.path.dirname(backend_dir)
    db_path = os.path.join(project_dir, 'data', 'gastos.db')

    print(f"[*] Conectando ao banco de dados: {db_path}")

    try:
        # Conectar ao banco
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Verificar se a tabela existe
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='financiamento'
        """)

        if not cursor.fetchone():
            print("[AVISO] Tabela 'financiamento' não existe. Pulando migração.")
            return

        # Verificar quais colunas já existem
        cursor.execute("PRAGMA table_info(financiamento)")
        columns = [column[1] for column in cursor.fetchall()]

        columns_to_add = []

        if 'seguro_tipo' not in columns:
            columns_to_add.append(('seguro_tipo', "VARCHAR(20) DEFAULT 'fixo'"))

        if 'seguro_percentual' not in columns:
            columns_to_add.append(('seguro_percentual', "NUMERIC(8, 6) DEFAULT 0.0006"))

        if 'valor_seguro_mensal' not in columns:
            columns_to_add.append(('valor_seguro_mensal', "NUMERIC(10, 2) DEFAULT 0"))

        if not columns_to_add:
            print("[OK] Todos os campos de seguro variável já existem na tabela financiamento")
            return

        # Adicionar colunas faltantes
        for column_name, column_def in columns_to_add:
            print(f"[*] Adicionando campo '{column_name}' à tabela financiamento...")
            cursor.execute(f"""
                ALTER TABLE financiamento
                ADD COLUMN {column_name} {column_def}
            """)

        # Para financiamentos existentes, garantir que têm tipo 'fixo'
        print("[*] Atualizando financiamentos existentes com tipo 'fixo'...")
        cursor.execute("""
            UPDATE financiamento
            SET seguro_tipo = 'fixo'
            WHERE seguro_tipo IS NULL
        """)

        # Commit das mudanças
        conn.commit()

        print("[OK] Migração concluída com sucesso!")
        for column_name, _ in columns_to_add:
            print(f"   - Campo '{column_name}' adicionado")

        # Mostrar estatísticas
        cursor.execute("SELECT COUNT(*) FROM financiamento")
        total_financiamentos = cursor.fetchone()[0]
        print(f"   - {total_financiamentos} financiamentos atualizados com compatibilidade retroativa")

    except Exception as e:
        print(f"[ERRO] Erro na migração: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    print("=" * 70)
    print("MIGRAÇÃO: Adicionar campos de seguro variável ao financiamento")
    print("=" * 70)
    run_migration()
    print("=" * 70)
