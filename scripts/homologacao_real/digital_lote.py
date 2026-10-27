"""Impressao digital (so leitura) do Supabase de teste: md5 do conteudo de cada tabela de public/financeiro e das
funcoes do financeiro. Uso: digital_lote.py <saida.json>. Nao imprime credenciais."""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]  # raiz do projeto (scripts/homologacao_real/..)
sys.path.insert(0, str(RAIZ / 'scripts'))
import psycopg2  # noqa: E402
from psycopg2 import sql as q  # noqa: E402

import supabase_migrations as sm  # noqa: E402

url, ref = sm._url()
assert ref.startswith('fzjmge') and ref != 'dshqjhyymtpxpxuntzbz'
conn = psycopg2.connect(url, connect_timeout=15)
conn.set_session(readonly=True)
saida = {'tabelas': {}, 'funcoes': {}}
with conn.cursor() as cur:
    cur.execute("select table_schema, table_name from information_schema.tables where table_type = 'BASE TABLE' "
                "and table_schema in ('public', 'financeiro') order by 1, 2")
    for esquema, tabela in cur.fetchall():
        cur.execute(q.SQL("select count(*), coalesce(md5(string_agg(md5(t::text), '' order by md5(t::text))), '') from {}.{} t")
                    .format(q.Identifier(esquema), q.Identifier(tabela)))
        saida['tabelas'][f'{esquema}.{tabela}'] = list(cur.fetchone())
    cur.execute("select p.oid::regprocedure::text, md5(p.prosrc || coalesce(p.proacl::text, '')) from pg_proc p "
                "join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro'")
    saida['funcoes'] = dict(cur.fetchall())
    cur.execute('select version from supabase_migrations.schema_migrations order by 1')
    saida['migrations'] = [r[0] for r in cur.fetchall()]
conn.close()
Path(sys.argv[1]).write_text(json.dumps(saida, indent=1, sort_keys=True), encoding='utf-8')
print('tabelas', len(saida['tabelas']), '| linhas', sum(v[0] for v in saida['tabelas'].values()),
      '| funcoes', len(saida['funcoes']), '| migrations', len(saida['migrations']))
