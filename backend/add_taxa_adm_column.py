"""
Script simples para adicionar coluna taxa_administracao_fixa
"""
import sqlite3
import os

# Caminho do banco
db_path = os.path.join(os.path.dirname(__file__), 'financeiro.db')

# Conectar
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Verificar se tabela financiamento existe
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='financiamento'")
tabela_existe = cursor.fetchone()

if tabela_existe:
    # Verificar se coluna já existe
    cursor.execute("PRAGMA table_info(financiamento)")
    colunas = [row[1] for row in cursor.fetchall()]

    if 'taxa_administracao_fixa' not in colunas:
        print("Adicionando coluna taxa_administracao_fixa...")
        cursor.execute("""
            ALTER TABLE financiamento
            ADD COLUMN taxa_administracao_fixa NUMERIC(10, 2) DEFAULT 0
        """)
        conn.commit()
        print("OK - Coluna adicionada com sucesso!")
    else:
        print("OK - Coluna taxa_administracao_fixa ja existe")
else:
    print("AVISO - Tabela 'financiamento' nao existe no banco. Ela sera criada quando o servidor iniciar.")

conn.close()
