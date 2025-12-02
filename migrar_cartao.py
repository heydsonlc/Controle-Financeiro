"""
Migração: Adicionar campos numero_cartao e codigo_seguranca na tabela config_agregador
"""
import sqlite3

def migrar_database():
    # Conectar ao banco
    conn = sqlite3.connect('data/gastos.db')
    cursor = conn.cursor()

    try:
        # Verificar se as colunas já existem
        cursor.execute("PRAGMA table_info(config_agregador)")
        colunas_existentes = [col[1] for col in cursor.fetchall()]

        print(f"Colunas existentes na tabela config_agregador: {colunas_existentes}")

        # Adicionar numero_cartao se não existir
        if 'numero_cartao' not in colunas_existentes:
            print("Adicionando coluna numero_cartao...")
            cursor.execute("""
                ALTER TABLE config_agregador
                ADD COLUMN numero_cartao VARCHAR(19)
            """)
            print("OK - Coluna numero_cartao adicionada!")
        else:
            print("OK - Coluna numero_cartao ja existe")

        # Adicionar codigo_seguranca se não existir
        if 'codigo_seguranca' not in colunas_existentes:
            print("Adicionando coluna codigo_seguranca...")
            cursor.execute("""
                ALTER TABLE config_agregador
                ADD COLUMN codigo_seguranca VARCHAR(4)
            """)
            print("OK - Coluna codigo_seguranca adicionada!")
        else:
            print("OK - Coluna codigo_seguranca ja existe")

        # Commit
        conn.commit()
        print("\nSUCESSO - Migracao concluida!")

    except Exception as e:
        print(f"\nERRO durante migracao: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrar_database()
