"""
SUPABASE-MIGRATE-1: verifica o estado do banco apontado por DATABASE_URL
sem alterar nada e sem nunca imprimir a connection string ou senha.

Uso:
    venv/Scripts/python.exe scripts/check_supabase_db.py

Le DATABASE_URL do ambiente (via .env.local, ou de qualquer .env.*
carregado antes de chamar o script — ex.: `set -a && source .env.staging
&& set +a` no bash, ou definindo a variavel diretamente no processo).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv('.env.local', encoding='utf-8-sig')

import psycopg2


def main():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print('DATABASE_URL nao configurada no ambiente atual.')
        sys.exit(1)

    try:
        conn = psycopg2.connect(database_url)
    except Exception as e:
        print(f'Falha ao conectar: {type(e).__name__}')
        sys.exit(1)

    try:
        cur = conn.cursor()

        cur.execute('SELECT 1')
        print('Conexao: OK')

        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tabelas = [r[0] for r in cur.fetchall()]
        print(f'Tabelas no schema public: {len(tabelas)}')
        for t in tabelas:
            print(f'  - {t}')

        try:
            cur.execute('SELECT version_num FROM alembic_version')
            versao = cur.fetchone()
            print(f'alembic_version: {versao[0] if versao else "(vazia)"}')
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            print('alembic_version: tabela nao existe (nenhuma migration aplicada ainda)')

    finally:
        conn.close()


if __name__ == '__main__':
    main()
