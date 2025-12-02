"""
Script para adicionar campos de número e código de segurança ao cartão
"""
import sqlite3
from pathlib import Path

# Caminho do banco de dados
DB_PATH = Path(__file__).parent / 'backend' / 'financeiro.db'

def adicionar_campos():
    """Adiciona campos de número do cartão e código de segurança"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("=== Adicionando campos ao config_agregador ===\n")

        # Verificar colunas existentes
        cursor.execute("PRAGMA table_info(config_agregador)")
        colunas_existentes = [col[1] for col in cursor.fetchall()]
        print(f"Colunas existentes: {', '.join(colunas_existentes)}\n")

        # Campos a adicionar
        novos_campos = [
            ("numero_cartao", "VARCHAR(19)"),  # Formato: 1234 5678 9012 3456
            ("codigo_seguranca", "VARCHAR(4)")  # CVV/CVC
        ]

        # Adicionar colunas que não existem
        for coluna_nome, coluna_tipo in novos_campos:
            if coluna_nome not in colunas_existentes:
                try:
                    sql = f"ALTER TABLE config_agregador ADD COLUMN {coluna_nome} {coluna_tipo}"
                    print(f"Executando: {sql}")
                    cursor.execute(sql)
                    print(f"=> Coluna '{coluna_nome}' adicionada com sucesso!\n")
                except Exception as e:
                    print(f"=> Erro ao adicionar coluna '{coluna_nome}': {e}\n")
            else:
                print(f"=> Coluna '{coluna_nome}' já existe, pulando...\n")

        # Commit e fechar conexão
        conn.commit()
        print("=> Migração concluída com sucesso!")

    except Exception as e:
        conn.rollback()
        print(f"Erro ao executar migração: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    adicionar_campos()
