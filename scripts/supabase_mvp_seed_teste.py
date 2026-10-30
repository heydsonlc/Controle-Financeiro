"""
AUTH-REAL-1 — dados FICTICIOS para validar o MVP contra o Supabase Auth real.

Insere em financeiro.categorias as mesmas categorias de teste do ambiente
isolado ('Moradia (A)', ..., 'Educacao (B)') para DUAS contas de teste ja
criadas no Supabase Auth do projeto do Controle Financeiro. Idempotente.

Seguranca:
- conecta pelo DATABASE_URL do .env.staging (projeto do Controle Financeiro);
  recusa o projeto da Calculadora Judicial;
- so toca em linhas dessas duas contas; nunca le nem altera tabelas do Flask;
- sem --confirmar executa numa transacao e a DESFAZ no final (rollback):
  mostra o que faria e nada e gravado;
- nao imprime e-mails completos nem identificadores.

Uso:
    venv\\Scripts\\python.exe scripts\\supabase_mvp_seed_teste.py --email-a A --email-b B            # simulacao
    venv\\Scripts\\python.exe scripts\\supabase_mvp_seed_teste.py --email-a A --email-b B --confirmar
    venv\\Scripts\\python.exe scripts\\supabase_mvp_seed_teste.py --email-a A --email-b B --remover --confirmar
"""
# FIN-PUBLICACAO-SEGURA-1: o projeto de teste virou a producao; recusa antes de ler credenciais ou conectar.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from guarda_producao import recusar_em_producao
recusar_em_producao(__file__)
import argparse
import os
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.supabase_local import CATEGORIAS_A, CATEGORIAS_B  # noqa: E402

PROJETOS_PROIBIDOS = {'dshqjhyymtpxpxuntzbz'}  # Calculadora Judicial / Portal Kortex
DESCRICAO = 'Dado ficticio de teste (AUTH-REAL-1)'


def mascarar(email):
    nome, _, dominio = email.partition('@')
    return f'{nome[:2]}***@{dominio}'


def conectar():
    import psycopg2
    from dotenv import dotenv_values
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    url = dotenv_values(os.path.join(raiz, '.env.staging'), encoding='utf-8-sig').get('DATABASE_URL') or ''
    usuario = urlsplit(url).username or ''
    ref = usuario.split('.', 1)[1] if usuario.startswith('postgres.') else ''
    if not ref or ref in PROJETOS_PROIBIDOS:
        raise SystemExit('Projeto invalido ou proibido no .env.staging.')
    return psycopg2.connect(url, connect_timeout=15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--email-a', required=True)
    parser.add_argument('--email-b', required=True)
    parser.add_argument('--remover', action='store_true', help='remove as categorias de teste dessas contas')
    parser.add_argument('--confirmar', action='store_true', help='sem isto, nada e gravado')
    args = parser.parse_args()

    contas = {'A': (args.email_a.strip().lower(), CATEGORIAS_A), 'B': (args.email_b.strip().lower(), CATEGORIAS_B)}
    if contas['A'][0] == contas['B'][0]:
        raise SystemExit('As duas contas de teste precisam ser diferentes.')

    conn = conectar()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            ids = {}
            for rotulo, (email, _) in contas.items():
                cur.execute('select id from auth.users where lower(email) = %s', (email,))
                linha = cur.fetchone()
                if not linha:
                    raise SystemExit(f'Conta {rotulo} ({mascarar(email)}) nao existe no Supabase Auth.')
                ids[rotulo] = linha[0]

            for rotulo, (email, nomes) in contas.items():
                if args.remover:
                    cur.execute('delete from financeiro.categorias where user_id = %s and descricao = %s',
                                (ids[rotulo], DESCRICAO))
                    print(f'Conta {rotulo} ({mascarar(email)}): {cur.rowcount} categoria(s) de teste removida(s)')
                    continue
                inseridas = 0
                for nome in nomes:
                    cur.execute(
                        """insert into financeiro.categorias (user_id, nome, descricao)
                           values (%s, %s, %s)
                           on conflict (user_id, lower(btrim(nome))) do nothing""",
                        (ids[rotulo], nome, DESCRICAO),
                    )
                    inseridas += cur.rowcount
                cur.execute('select count(*) from financeiro.categorias where user_id = %s', (ids[rotulo],))
                print(f'Conta {rotulo} ({mascarar(email)}): {inseridas} inserida(s); total da conta: {cur.fetchone()[0]}')

        if args.confirmar:
            conn.commit()
            print('CONFIRMADO: alteracoes gravadas.')
        else:
            conn.rollback()
            print('SIMULACAO: nada foi gravado (use --confirmar).')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
