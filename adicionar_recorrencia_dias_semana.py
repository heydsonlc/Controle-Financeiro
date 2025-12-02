"""
Script para adicionar campos de recorrencia por dia da semana
"""
import sqlite3
from pathlib import Path

# Caminho do banco de dados
DB_PATH = Path(__file__).parent / 'backend' / 'financeiro.db'

def adicionar_campos_recorrencia():
    """Adiciona campos para recorrencia por dia da semana"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("=== Adicionando campos de recorrencia por dia da semana ===\n")

        # Verificar colunas existentes
        cursor.execute("PRAGMA table_info(item_despesa)")
        colunas_existentes = [col[1] for col in cursor.fetchall()]
        print(f"Colunas existentes: {', '.join(colunas_existentes)}\n")

        # Campos a adicionar
        novos_campos = [
            ("dias_semana", "TEXT"),  # JSON array com dias: ["segunda", "terca", "quinta"]
            ("frequencia_semanal", "VARCHAR(20) DEFAULT 'toda_semana'")  # 'toda_semana' ou 'alternado'
        ]

        # Adicionar colunas que nao existem
        for coluna_nome, coluna_tipo in novos_campos:
            if coluna_nome not in colunas_existentes:
                try:
                    sql = f"ALTER TABLE item_despesa ADD COLUMN {coluna_nome} {coluna_tipo}"
                    print(f"Executando: {sql}")
                    cursor.execute(sql)
                    print(f"=> Coluna '{coluna_nome}' adicionada com sucesso!\n")
                except Exception as e:
                    print(f"=> Erro ao adicionar coluna '{coluna_nome}': {e}\n")
            else:
                print(f"=> Coluna '{coluna_nome}' ja existe, pulando...\n")

        # Commit e fechar conexao
        conn.commit()
        print("=> Migracao concluida com sucesso!")
        print("=> Reinicie o servidor Flask para aplicar as mudancas.")

    except Exception as e:
        conn.rollback()
        print(f"Erro ao executar migracao: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    adicionar_campos_recorrencia()
