"""
SEC-SUPABASE-PUBLIC-1 — snapshot, comparacao e rollback da migration c4f7a2d91b3e.

So le metadados (RLS e ACLs) do schema public; nunca le registros. Nao executa
nada no banco remoto: o SQL de rollback e apenas GERADO, para revisao humana.

Subcomandos (com .env.staging carregado ou DATABASE_URL no ambiente):
    snapshot  --saida data/sec_public/antes.json
    comparar  --snapshot data/sec_public/antes.json      # exit 0 = so mudancas esperadas
    gerar-sql --snapshot data/sec_public/antes.json --saida data/sec_public/rollback.sql

Mudancas esperadas da migration (todo o resto e inesperado):
- RLS de desligada para ligada (sem FORCE);
- remocao de privilegios de anon/authenticated em tabelas, sequencias e funcoes;
- remocao dos default privileges de anon/authenticated do papel atual no public.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

PAPEIS_API = ('anon', 'authenticated')
TIPO_DEFAULT = {'r': 'tables', 'S': 'sequences', 'f': 'functions'}


def capturar(conn):
    """Estado de seguranca do schema public (somente catalogos)."""
    with conn.cursor() as cur:
        cur.execute('select current_user')
        papel = cur.fetchone()[0]
        cur.execute("""
            select c.relname, c.relkind, pg_get_userbyid(c.relowner), c.relrowsecurity, c.relforcerowsecurity,
                   coalesce((select json_agg(json_build_array(case when a.grantee = 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end,
                                                              a.privilege_type, a.is_grantable) order by 1)
                               from aclexplode(c.relacl) a), '[]'::json)
              from pg_class c join pg_namespace n on n.oid = c.relnamespace
             where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm', 'f', 'S')
             order by c.relname
        """)
        objetos = {nome: {'tipo': 'sequence' if kind == 'S' else 'table', 'dono': dono, 'rls': rls, 'force': force,
                          'acl': sorted(map(tuple, acl))}
                   for nome, kind, dono, rls, force, acl in cur.fetchall()}
        cur.execute("""
            select p.oid::regprocedure::text, pg_get_userbyid(p.proowner),
                   coalesce((select json_agg(json_build_array(case when a.grantee = 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end,
                                                              a.privilege_type, a.is_grantable))
                               from aclexplode(p.proacl) a), '[]'::json)
              from pg_proc p join pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public'
        """)
        funcoes = {sig: {'dono': dono, 'acl': sorted(map(tuple, acl))} for sig, dono, acl in cur.fetchall()}
        cur.execute("""
            select pg_get_userbyid(d.defaclrole), d.defaclobjtype,
                   coalesce((select json_agg(json_build_array(case when a.grantee = 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end,
                                                              a.privilege_type, a.is_grantable))
                               from aclexplode(d.defaclacl) a), '[]'::json)
              from pg_default_acl d join pg_namespace n on n.oid = d.defaclnamespace
             where n.nspname = 'public'
        """)
        defaults = {f'{dono}:{tipo}': sorted(map(tuple, acl)) for dono, tipo, acl in cur.fetchall()}
        cur.execute("select to_regclass('public.alembic_version') is not null")
        versao = None
        if cur.fetchone()[0]:
            cur.execute('select version_num from public.alembic_version')
            linha = cur.fetchone()
            versao = linha[0] if linha else None
    return {'capturado_em': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'papel': papel,
            'alembic_version': versao, 'objetos': objetos, 'funcoes': funcoes, 'defaults': defaults}


def _normalizar(snapshot):
    """JSON <-> memoria: listas viram tuplas para comparar."""
    for obj in list(snapshot['objetos'].values()) + list(snapshot['funcoes'].values()):
        obj['acl'] = sorted(tuple(x) for x in obj['acl'])
    snapshot['defaults'] = {k: sorted(tuple(x) for x in v) for k, v in snapshot['defaults'].items()}
    return snapshot


def comparar(antes, depois):
    """Lista (esperadas, inesperadas) de diferencas entre dois snapshots."""
    antes, depois = _normalizar(json.loads(json.dumps(antes))), _normalizar(json.loads(json.dumps(depois)))
    esperadas, inesperadas = [], []
    papel = antes['papel']

    for nome in sorted(set(antes['objetos']) | set(depois['objetos'])):
        a, d = antes['objetos'].get(nome), depois['objetos'].get(nome)
        if a is None or d is None:
            inesperadas.append(f'{nome}: objeto {"criado" if a is None else "removido"}')
            continue
        if a['dono'] != d['dono']:
            inesperadas.append(f'{nome}: dono mudou {a["dono"]} -> {d["dono"]}')
        if d['force'] != a['force']:
            inesperadas.append(f'{nome}: FORCE mudou {a["force"]} -> {d["force"]}')
        if a['rls'] != d['rls']:
            (esperadas if (not a['rls'] and d['rls'] and a['tipo'] == 'table' and a['dono'] == papel)
             else inesperadas).append(f'{nome}: RLS {a["rls"]} -> {d["rls"]}')
        removidos, adicionados = set(a['acl']) - set(d['acl']), set(d['acl']) - set(a['acl'])
        for item in sorted(removidos):
            (esperadas if item[0] in PAPEIS_API else inesperadas).append(f'{nome}: privilegio removido {item}')
        for item in sorted(adicionados):
            inesperadas.append(f'{nome}: privilegio adicionado {item}')

    for sig in sorted(set(antes['funcoes']) | set(depois['funcoes'])):
        a, d = antes['funcoes'].get(sig), depois['funcoes'].get(sig)
        if a is None or d is None:
            inesperadas.append(f'funcao {sig}: {"criada" if a is None else "removida"}')
            continue
        for item in sorted(set(a['acl']) - set(d['acl'])):
            (esperadas if item[0] in PAPEIS_API else inesperadas).append(f'funcao {sig}: privilegio removido {item}')
        for item in sorted(set(d['acl']) - set(a['acl'])):
            inesperadas.append(f'funcao {sig}: privilegio adicionado {item}')

    for chave in sorted(set(antes['defaults']) | set(depois['defaults'])):
        a, d = set(antes['defaults'].get(chave, [])), set(depois['defaults'].get(chave, []))
        dono = chave.split(':')[0]
        for item in sorted(a - d):
            (esperadas if item[0] in PAPEIS_API and dono == papel else inesperadas).append(
                f'default {chave}: removido {item}')
        for item in sorted(d - a):
            inesperadas.append(f'default {chave}: adicionado {item}')
    return esperadas, inesperadas


def _q(nome):
    return '"' + nome.replace('"', '""') + '"'


def gerar_sql(snapshot):
    """SQL que restaura, para anon/authenticated, o estado do snapshot. NAO executa."""
    snapshot = _normalizar(json.loads(json.dumps(snapshot)))
    linhas = [
        '-- Rollback da migration c4f7a2d91b3e (SEC-SUPABASE-PUBLIC-1), gerado a partir do snapshot',
        f"-- capturado em {snapshot['capturado_em']} (alembic {snapshot['alembic_version']}).",
        '-- ATENCAO: restaura os privilegios de anon/authenticated. Com o schema public exposto na',
        '-- Data API, isso REABRE a vulnerabilidade. Usar somente com o public fora dos Exposed schemas.',
        '-- Revisar antes de executar. Depois: python -m flask --app backend/app.py db stamp 5c91e95eb05d',
        'begin;',
    ]
    for nome, obj in sorted(snapshot['objetos'].items()):
        if obj['tipo'] == 'table' and not obj['rls'] and obj['dono'] == snapshot['papel']:
            linhas.append(f'alter table public.{_q(nome)} disable row level security;')
        for papel in PAPEIS_API:
            privs = sorted({p for (g, p, _) in obj['acl'] if g == papel})
            if privs:
                alvo = 'sequence' if obj['tipo'] == 'sequence' else 'table'
                linhas.append(f'grant {", ".join(privs).lower()} on {alvo} public.{_q(nome)} to {papel};')
    for sig, fn in sorted(snapshot['funcoes'].items()):
        for papel in PAPEIS_API:
            if any(g == papel for (g, _, _) in fn['acl']):
                linhas.append(f'grant execute on function {sig} to {papel};')
    for chave, acl in sorted(snapshot['defaults'].items()):
        dono, tipo = chave.split(':')
        if dono != snapshot['papel'] or tipo not in TIPO_DEFAULT:
            continue
        for papel in PAPEIS_API:
            privs = sorted({p for (g, p, _) in acl if g == papel})
            if privs:
                linhas.append(f'alter default privileges for role {_q(dono)} in schema public '
                              f'grant {", ".join(privs).lower()} on {TIPO_DEFAULT[tipo]} to {papel};')
    linhas.append('commit;')
    return '\n'.join(linhas) + '\n'


def _conectar():
    import psycopg2
    from dotenv import load_dotenv
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(raiz, '.env.staging'), override=False, encoding='utf-8-sig')
    url = os.getenv('DATABASE_URL')
    if not url:
        raise SystemExit('DATABASE_URL ausente.')
    conn = psycopg2.connect(url, connect_timeout=15)
    conn.set_session(readonly=True)
    return conn


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='comando', required=True)
    s = sub.add_parser('snapshot'); s.add_argument('--saida', required=True)
    c = sub.add_parser('comparar'); c.add_argument('--snapshot', required=True)
    g = sub.add_parser('gerar-sql'); g.add_argument('--snapshot', required=True); g.add_argument('--saida', required=True)
    args = parser.parse_args()

    if args.comando == 'gerar-sql':
        with open(args.snapshot, encoding='utf-8') as f:
            sql = gerar_sql(json.load(f))
        os.makedirs(os.path.dirname(os.path.abspath(args.saida)), exist_ok=True)
        with open(args.saida, 'w', encoding='utf-8') as f:
            f.write(sql)
        print(f'SQL de rollback gerado (nao executado): {args.saida} ({sql.count(chr(10))} linhas)')
        return 0

    conn = _conectar()
    try:
        atual = capturar(conn)
    finally:
        conn.close()
    if args.comando == 'snapshot':
        os.makedirs(os.path.dirname(os.path.abspath(args.saida)), exist_ok=True)
        with open(args.saida, 'w', encoding='utf-8') as f:
            json.dump(atual, f, ensure_ascii=False, indent=1)
        tabelas = [o for o in atual['objetos'].values() if o['tipo'] == 'table']
        print(f"Snapshot salvo: {args.saida} | alembic {atual['alembic_version']} | {len(tabelas)} tabelas "
              f"({sum(o['rls'] for o in tabelas)} com RLS) | {len(atual['objetos']) - len(tabelas)} sequencias")
        return 0

    with open(args.snapshot, encoding='utf-8') as f:
        antes = json.load(f)
    esperadas, inesperadas = comparar(antes, atual)
    print(f'Mudancas esperadas: {len(esperadas)} | inesperadas: {len(inesperadas)}')
    for item in inesperadas[:50]:
        print('  INESPERADA:', item)
    return 1 if inesperadas else 0


if __name__ == '__main__':
    sys.exit(main())
