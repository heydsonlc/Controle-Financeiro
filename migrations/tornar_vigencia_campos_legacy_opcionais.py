"""
Migration: Tornar campos legacy de vigência opcionais

Data: 2026-01-07
Motivo: Seguro passou a ser 100% manual (não depende de saldo_devedor_vigencia nem taxa_percentual)

Mudanças:
- saldo_devedor_vigencia: nullable=False → nullable=True
- taxa_percentual: nullable=False → nullable=True
"""
import sys
import os

# Adicionar diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app
from backend.models import db
import sqlite3

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("MIGRATION: Tornar campos legacy de vigência opcionais")
    print("="*80)

    db_path = app.config.get('SQLALCHEMY_DATABASE_URI', '').replace('sqlite:///', '')

    if not db_path:
        print("\n[ERRO] Não foi possível determinar o caminho do banco de dados")
        sys.exit(1)

    print(f"\n[1] Banco de dados: {db_path}")

    try:
        # Conectar diretamente ao SQLite
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print("\n[2] Verificando estrutura atual da tabela...")
        cursor.execute("PRAGMA table_info(financiamento_seguro_vigencia)")
        colunas = cursor.fetchall()

        print("\n    Colunas encontradas:")
        for col in colunas:
            col_id, nome, tipo, not_null, default, pk = col
            nullable_str = "NOT NULL" if not_null else "NULL"
            print(f"      - {nome}: {tipo} ({nullable_str})")

        # SQLite não suporta ALTER COLUMN diretamente, precisa recriar a tabela
        print("\n[3] Aplicando migration (recriando tabela)...")

        # 1. Criar tabela temporária com nova estrutura
        cursor.execute("""
            CREATE TABLE financiamento_seguro_vigencia_new (
                id INTEGER PRIMARY KEY,
                financiamento_id INTEGER NOT NULL,
                competencia_inicio DATE NOT NULL,
                valor_mensal NUMERIC(10, 2) NOT NULL,
                saldo_devedor_vigencia NUMERIC(12, 2),  -- Agora NULL
                taxa_percentual NUMERIC(8, 6),           -- Agora NULL
                data_nascimento_segurado DATE,
                observacoes TEXT,
                vigencia_ativa BOOLEAN DEFAULT 1,
                data_encerramento DATE,
                criado_em DATETIME,
                FOREIGN KEY (financiamento_id) REFERENCES financiamento(id)
            )
        """)

        # 2. Copiar dados da tabela antiga para a nova
        cursor.execute("""
            INSERT INTO financiamento_seguro_vigencia_new
            SELECT * FROM financiamento_seguro_vigencia
        """)

        # 3. Dropar tabela antiga
        cursor.execute("DROP TABLE financiamento_seguro_vigencia")

        # 4. Renomear tabela nova para o nome original
        cursor.execute("""
            ALTER TABLE financiamento_seguro_vigencia_new
            RENAME TO financiamento_seguro_vigencia
        """)

        # 5. Recriar índices (se houver)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_vigencia_financiamento
            ON financiamento_seguro_vigencia(financiamento_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_vigencia_competencia
            ON financiamento_seguro_vigencia(competencia_inicio)
        """)

        # Commit
        conn.commit()

        print("\n[4] Verificando nova estrutura...")
        cursor.execute("PRAGMA table_info(financiamento_seguro_vigencia)")
        colunas_novas = cursor.fetchall()

        print("\n    Colunas após migration:")
        for col in colunas_novas:
            col_id, nome, tipo, not_null, default, pk = col
            nullable_str = "NOT NULL" if not_null else "NULL"
            print(f"      - {nome}: {tipo} ({nullable_str})")

        print("\n" + "="*80)
        print("MIGRATION CONCLUÍDA COM SUCESSO!")
        print("="*80)
        print("\nCampos 'saldo_devedor_vigencia' e 'taxa_percentual' agora são OPCIONAIS.")
        print("O sistema pode criar vigências sem esses campos legacy.")

        conn.close()

    except Exception as e:
        print("\n" + "="*80)
        print("ERRO NA MIGRATION!")
        print("="*80)
        print(f"\nErro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print()
