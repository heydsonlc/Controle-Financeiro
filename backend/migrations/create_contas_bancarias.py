"""
Script de migração para criar a tabela contas_bancarias
Execução: python backend/migrations/create_contas_bancarias.py
"""
import sys
from pathlib import Path
from datetime import datetime

# Adicionar diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app import app, db

def migrate():
    with app.app_context():
        # Conectar ao banco
        conn = db.engine.connect()

        print("Iniciando migração de contas bancárias...")

        try:
            # Verificar se a tabela já existe
            result = conn.execute(db.text("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='conta_bancaria'
            """))
            table_exists = result.fetchone() is not None

            if not table_exists:
                print("Criando tabela conta_bancaria...")

                conn.execute(db.text("""
                    CREATE TABLE conta_bancaria (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT NOT NULL,
                        instituicao TEXT NOT NULL,
                        tipo TEXT NOT NULL,
                        agencia TEXT,
                        numero_conta TEXT,
                        digito_conta TEXT,
                        saldo_inicial REAL DEFAULT 0,
                        saldo_atual REAL DEFAULT 0,
                        cor_display TEXT DEFAULT '#3b82f6',
                        icone TEXT,
                        data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
                        data_atualizacao DATETIME DEFAULT CURRENT_TIMESTAMP,
                        status TEXT DEFAULT 'ATIVO'
                    )
                """))
                conn.commit()
                print("[OK] Tabela conta_bancaria criada com sucesso!")

                # Criar índices para melhorar performance
                print("Criando índices...")
                conn.execute(db.text("""
                    CREATE INDEX idx_conta_bancaria_status
                    ON conta_bancaria(status)
                """))
                conn.execute(db.text("""
                    CREATE INDEX idx_conta_bancaria_instituicao
                    ON conta_bancaria(instituicao)
                """))
                conn.commit()
                print("[OK] Índices criados com sucesso!")

            else:
                print("[-] Tabela conta_bancaria já existe")

            print("\n[OK] Migração concluída com sucesso!")

        except Exception as e:
            print(f"\n[ERRO] Erro durante migração: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

if __name__ == '__main__':
    migrate()
