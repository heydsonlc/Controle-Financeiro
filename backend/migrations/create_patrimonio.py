"""
Script de migração para criar as tabelas do módulo de Patrimônio
Execução: python backend/migrations/create_patrimonio.py
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

        print("Iniciando migração do módulo de Patrimônio...")

        try:
            # Verificar se a tabela conta_patrimonio já existe
            result = conn.execute(db.text("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='conta_patrimonio'
            """))
            conta_patrimonio_exists = result.fetchone() is not None

            if not conta_patrimonio_exists:
                print("Criando tabela conta_patrimonio...")

                conn.execute(db.text("""
                    CREATE TABLE conta_patrimonio (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome VARCHAR(100) NOT NULL UNIQUE,
                        tipo VARCHAR(50),
                        saldo_inicial NUMERIC(10, 2) DEFAULT 0,
                        saldo_atual NUMERIC(10, 2) DEFAULT 0,
                        meta NUMERIC(10, 2),
                        cor VARCHAR(7) DEFAULT '#28a745',
                        ativo BOOLEAN DEFAULT 1,
                        observacoes TEXT,
                        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.commit()
                print("[OK] Tabela conta_patrimonio criada com sucesso!")

            else:
                print("[-] Tabela conta_patrimonio já existe")

            # Verificar se a tabela transferencia já existe
            result = conn.execute(db.text("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='transferencia'
            """))
            transferencia_exists = result.fetchone() is not None

            if not transferencia_exists:
                print("Criando tabela transferencia...")

                conn.execute(db.text("""
                    CREATE TABLE transferencia (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conta_origem_id INTEGER NOT NULL,
                        conta_destino_id INTEGER NOT NULL,
                        valor NUMERIC(10, 2) NOT NULL,
                        data_transferencia DATE NOT NULL,
                        descricao VARCHAR(200),
                        observacoes TEXT,
                        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (conta_origem_id) REFERENCES conta_patrimonio (id),
                        FOREIGN KEY (conta_destino_id) REFERENCES conta_patrimonio (id)
                    )
                """))
                conn.commit()
                print("[OK] Tabela transferencia criada com sucesso!")

                # Criar índices para transferencia
                print("Criando índices para transferencia...")
                conn.execute(db.text("""
                    CREATE INDEX idx_transf_data
                    ON transferencia(data_transferencia)
                """))
                conn.execute(db.text("""
                    CREATE INDEX idx_transf_origem
                    ON transferencia(conta_origem_id)
                """))
                conn.execute(db.text("""
                    CREATE INDEX idx_transf_destino
                    ON transferencia(conta_destino_id)
                """))
                conn.commit()
                print("[OK] Índices criados com sucesso!")

            else:
                print("[-] Tabela transferencia já existe")

            print("\n[OK] Migração do módulo de Patrimônio concluída com sucesso!")

        except Exception as e:
            print(f"\n[ERRO] Erro durante migração: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

if __name__ == '__main__':
    migrate()
