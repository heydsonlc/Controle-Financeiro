"""
Migration: Tornar item_receita_id nullable em ReceitaRealizada
Para permitir receitas pontuais sem vínculo com fonte fixa
"""
import sqlite3

def migrate():
    """Executa a migration"""
    conn = sqlite3.connect('backend/financeiro.db')
    cursor = conn.cursor()

    try:
        # SQLite não suporta ALTER COLUMN diretamente
        # Precisamos recriar a tabela

        # 1. Criar tabela temporária com estrutura correta
        cursor.execute('''
            CREATE TABLE receita_realizada_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_receita_id INTEGER,
                data_recebimento DATE NOT NULL,
                valor_recebido NUMERIC(10, 2) NOT NULL,
                mes_referencia DATE NOT NULL,
                conta_origem_id INTEGER,
                descricao VARCHAR(200),
                orcamento_id INTEGER,
                observacoes TEXT,
                criado_em DATETIME,
                FOREIGN KEY (item_receita_id) REFERENCES item_receita(id),
                FOREIGN KEY (conta_origem_id) REFERENCES conta_patrimonio(id),
                FOREIGN KEY (orcamento_id) REFERENCES receita_orcamento(id)
            )
        ''')

        # 2. Copiar dados da tabela antiga
        cursor.execute('''
            INSERT INTO receita_realizada_new
            SELECT * FROM receita_realizada
        ''')

        # 3. Remover tabela antiga
        cursor.execute('DROP TABLE receita_realizada')

        # 4. Renomear tabela nova
        cursor.execute('ALTER TABLE receita_realizada_new RENAME TO receita_realizada')

        conn.commit()
        print("✅ Migration executada com sucesso!")
        print("   item_receita_id agora permite NULL")

    except Exception as e:
        conn.rollback()
        print(f"❌ Erro na migration: {e}")
        raise

    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
