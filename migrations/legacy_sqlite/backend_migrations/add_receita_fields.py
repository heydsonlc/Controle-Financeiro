"""
Script de migração para adicionar novos campos às tabelas de receita
Execução: python backend/migrations/add_receita_fields.py
"""
import sys
from pathlib import Path

# Adicionar diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app import app, db

def migrate():
    with app.app_context():
        # Conectar ao banco
        conn = db.engine.connect()

        print("Iniciando migração de receitas...")

        try:
            # Adicionar colunas em item_receita
            print("Adicionando colunas em item_receita...")

            # Verificar se as colunas já existem
            result = conn.execute(db.text("PRAGMA table_info(item_receita)"))
            existing_columns = [row[1] for row in result]

            if 'valor_base_mensal' not in existing_columns:
                conn.execute(db.text("ALTER TABLE item_receita ADD COLUMN valor_base_mensal NUMERIC(10, 2)"))
                conn.commit()
                print("[OK] Coluna valor_base_mensal adicionada")
            else:
                print("[-] Coluna valor_base_mensal ja existe")

            if 'dia_previsto_pagamento' not in existing_columns:
                conn.execute(db.text("ALTER TABLE item_receita ADD COLUMN dia_previsto_pagamento INTEGER"))
                conn.commit()
                print("[OK] Coluna dia_previsto_pagamento adicionada")
            else:
                print("[-] Coluna dia_previsto_pagamento ja existe")

            if 'conta_origem_id' not in existing_columns:
                conn.execute(db.text("ALTER TABLE item_receita ADD COLUMN conta_origem_id INTEGER"))
                conn.commit()
                print("[OK] Coluna conta_origem_id adicionada")
            else:
                print("[-] Coluna conta_origem_id ja existe")

            # Verificar e adicionar coluna em receita_orcamento
            print("\nVerificando receita_orcamento...")
            result = conn.execute(db.text("PRAGMA table_info(receita_orcamento)"))
            existing_columns_orcamento = [row[1] for row in result]

            if 'periodicidade' not in existing_columns_orcamento:
                conn.execute(db.text("ALTER TABLE receita_orcamento ADD COLUMN periodicidade VARCHAR(20) DEFAULT 'MENSAL_FIXA'"))
                conn.commit()
                print("[OK] Coluna periodicidade adicionada em receita_orcamento")
            else:
                print("[-] Coluna periodicidade ja existe em receita_orcamento")

            # Verificar e adicionar colunas em receita_realizada
            print("\nVerificando receita_realizada...")
            result = conn.execute(db.text("PRAGMA table_info(receita_realizada)"))
            existing_columns_realizada = [row[1] for row in result]

            if 'orcamento_id' not in existing_columns_realizada:
                conn.execute(db.text("ALTER TABLE receita_realizada ADD COLUMN orcamento_id INTEGER"))
                conn.commit()
                print("[OK] Coluna orcamento_id adicionada em receita_realizada")
            else:
                print("[-] Coluna orcamento_id ja existe em receita_realizada")

            if 'competencia' not in existing_columns_realizada:
                conn.execute(db.text("ALTER TABLE receita_realizada ADD COLUMN competencia DATE"))
                conn.commit()
                print("[OK] Coluna competencia adicionada em receita_realizada")
            else:
                print("[-] Coluna competencia ja existe em receita_realizada")

            if 'conta_origem_id' not in existing_columns_realizada:
                conn.execute(db.text("ALTER TABLE receita_realizada ADD COLUMN conta_origem_id INTEGER"))
                conn.commit()
                print("[OK] Coluna conta_origem_id adicionada em receita_realizada")
            else:
                print("[-] Coluna conta_origem_id ja existe em receita_realizada")

            if 'atualizado_em' not in existing_columns_realizada:
                conn.execute(db.text("ALTER TABLE receita_realizada ADD COLUMN atualizado_em DATETIME"))
                conn.commit()
                print("[OK] Coluna atualizado_em adicionada em receita_realizada")
            else:
                print("[-] Coluna atualizado_em ja existe em receita_realizada")

            print("\n[OK] Migracao concluida com sucesso!")

        except Exception as e:
            print(f"\n[ERRO] Erro durante migracao: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

if __name__ == '__main__':
    migrate()
