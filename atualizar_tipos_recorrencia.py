"""
Script para atualizar tipos de recorrencia existentes
"""
import sqlite3
from pathlib import Path

# Caminho do banco de dados
DB_PATH = Path(__file__).parent / 'backend' / 'financeiro.db'

def atualizar_tipos_recorrencia():
    """Atualiza despesas existentes com novos tipos de recorrencia"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Verificar se existem despesas com tipo_recorrencia 'quinzenal'
        cursor.execute("SELECT COUNT(*) FROM item_despesa WHERE tipo_recorrencia = 'quinzenal'")
        count = cursor.fetchone()[0]

        if count > 0:
            print(f"=> Encontradas {count} despesas com tipo 'quinzenal'")
            print("=> Atualizando para 'a_cada_2_semanas'...")

            cursor.execute("""
                UPDATE item_despesa
                SET tipo_recorrencia = 'a_cada_2_semanas'
                WHERE tipo_recorrencia = 'quinzenal'
            """)

            print(f"=> {cursor.rowcount} despesas atualizadas com sucesso!")
        else:
            print("=> Nenhuma despesa com tipo 'quinzenal' encontrada")

        conn.commit()
        print("\n=> Script executado com sucesso!")

    except Exception as e:
        conn.rollback()
        print(f"Erro ao atualizar tipos de recorrencia: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    print("=== Atualizando Tipos de Recorrencia ===\n")
    atualizar_tipos_recorrencia()
