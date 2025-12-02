"""
Script para adicionar campos necessários à tabela item_despesa
Campos: valor, data_vencimento, data_pagamento, pago, recorrente, tipo_recorrencia, mes_competencia
"""
import sqlite3
from pathlib import Path

# Caminho do banco de dados
db_path = Path(__file__).parent / 'data' / 'gastos.db'

print(f"Conectando ao banco de dados: {db_path}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Verificar colunas existentes
cursor.execute("PRAGMA table_info(item_despesa)")
colunas_existentes = [col[1] for col in cursor.fetchall()]
print(f"\nColunas existentes: {colunas_existentes}")

# Lista de colunas para adicionar
colunas_para_adicionar = [
    ("valor", "NUMERIC(10, 2)"),
    ("data_vencimento", "DATE"),
    ("data_pagamento", "DATE"),
    ("pago", "BOOLEAN DEFAULT 0"),
    ("recorrente", "BOOLEAN DEFAULT 0"),
    ("tipo_recorrencia", "VARCHAR(20) DEFAULT 'mensal'"),
    ("mes_competencia", "VARCHAR(7)")  # Formato: YYYY-MM
]

# Adicionar colunas que não existem
for coluna_nome, coluna_tipo in colunas_para_adicionar:
    if coluna_nome not in colunas_existentes:
        try:
            sql = f"ALTER TABLE item_despesa ADD COLUMN {coluna_nome} {coluna_tipo}"
            print(f"\nExecutando: {sql}")
            cursor.execute(sql)
            print(f"=> Coluna '{coluna_nome}' adicionada com sucesso!")
        except Exception as e:
            print(f"=> Erro ao adicionar coluna '{coluna_nome}': {e}")
    else:
        print(f"=> Coluna '{coluna_nome}' ja existe, pulando...")

# Adicionar categoria "Presentes" se não existir
print("\n--- Verificando categoria 'Presentes' ---")
cursor.execute("SELECT id FROM categoria WHERE nome = 'Presentes'")
categoria_existe = cursor.fetchone()

if not categoria_existe:
    try:
        cursor.execute("""
            INSERT INTO categoria (nome, descricao, cor, ativo)
            VALUES ('Presentes', 'Despesas com presentes de aniversário, natal, etc.', '#e91e63', 1)
        """)
        print("=> Categoria 'Presentes' adicionada com sucesso!")
    except Exception as e:
        print(f"=> Erro ao adicionar categoria 'Presentes': {e}")
else:
    print("=> Categoria 'Presentes' ja existe, pulando...")

# Commit e fechar conexão
conn.commit()
conn.close()

print("\n=> Migração concluída!")
print("=> Reinicie o servidor Flask para aplicar as mudanças.")
