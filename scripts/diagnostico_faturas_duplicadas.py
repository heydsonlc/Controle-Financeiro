"""
FIN-FATURA-UNICA-1 — diagnostico SOMENTE LEITURA das faturas de cartao.

Antes de criar a restricao de unicidade (cartao + competencia), mostra:
- grupos duplicados (mesmo cartao e competencia em mais de uma fatura);
- faturas sem competencia ou com competencia fora do dia 1;
- faturas cujo perfil difere do perfil do cartao;
- faturas cujo item nao e um cartao (tipo 'Agregador').
Nunca altera, exclui ou consolida nada. So ids e contagens (sem valores, nomes ou dados de conta).

Uso:
    scripts/diagnostico_faturas_duplicadas.py                 # banco do .env.staging (Supabase de teste)
    scripts/diagnostico_faturas_duplicadas.py --database-url URL
"""
import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
PROJETOS_PROIBIDOS = {'dshqjhyymtpxpxuntzbz'}

CONSULTAS = [
    ('faturas no total', "select count(*) from public.conta where is_fatura_cartao", False),
    ('grupos duplicados (cartao + competencia)',
     """select item_despesa_id, cartao_competencia, array_agg(id order by id)
          from public.conta where is_fatura_cartao and cartao_competencia is not null
         group by 1, 2 having count(*) > 1 order by 1, 2""", True),
    ('faturas sem competencia', "select id from public.conta where is_fatura_cartao and cartao_competencia is null", True),
    ('competencia fora do dia 1',
     "select id from public.conta where is_fatura_cartao and extract(day from cartao_competencia) <> 1", True),
    ('perfil da fatura diferente do perfil do cartao',
     """select f.id from public.conta f join public.item_despesa c on c.id = f.item_despesa_id
         where f.is_fatura_cartao and f.perfil_financeiro_id is distinct from c.perfil_financeiro_id""", True),
    ('fatura ligada a item que nao e cartao',
     """select f.id from public.conta f join public.item_despesa c on c.id = f.item_despesa_id
         where f.is_fatura_cartao and c.tipo <> 'Agregador'""", True),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database-url')
    args = parser.parse_args()
    url = args.database_url
    if not url:
        from dotenv import dotenv_values
        url = dotenv_values(RAIZ / '.env.staging', encoding='utf-8-sig').get('DATABASE_URL') or ''
    if any(ref in (urlsplit(url).username or '') for ref in PROJETOS_PROIBIDOS):
        raise SystemExit('Projeto proibido.')

    import psycopg2
    conn = psycopg2.connect(url, connect_timeout=15)
    conn.set_session(readonly=True)
    problemas = 0
    try:
        cur = conn.cursor()
        cur.execute("select to_regclass('public.ux_conta_fatura_cartao_competencia') is not null")
        print('restricao ux_conta_fatura_cartao_competencia presente:', cur.fetchone()[0])
        for titulo, sql, e_problema in CONSULTAS:
            cur.execute(sql)
            linhas = cur.fetchall()
            if not e_problema:
                print(f'{titulo}: {linhas[0][0]}')
                continue
            problemas += len(linhas) if titulo.startswith('grupos') else 0
            print(f'{titulo}: {len(linhas)}' + (f' -> {linhas[:20]}' if linhas else ''))
    finally:
        conn.close()
    print('RESULTADO:', 'DUPLICIDADES ENCONTRADAS (nao criar a restricao sem decisao)' if problemas else 'sem duplicidades')
    return 1 if problemas else 0


if __name__ == '__main__':
    sys.exit(main())
