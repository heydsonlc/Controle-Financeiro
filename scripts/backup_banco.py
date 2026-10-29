"""
FIN-RELATORIOS-CONFIG-1 (FIN-BLOCO-B-1, B2) — backup e restauracao verificavel do banco do novo aplicativo (PostgreSQL /
Supabase), sem dependencia nova (pg_dump/pg_restore do PostgreSQL instalado).

  exportar  --dsn-env VAR --saida PASTA   num unico snapshot (consistente): pg_dump de public, financeiro e do historico
                                          supabase_migrations (estrutura, dados, funcoes, politicas e privilegios) +
                                          arquivo separado so com os documentos (public.ir_comprovante_arquivo) + contas
                                          do Auth (auth.users e auth.identities, com a estrutura) + manifesto (SHA-256,
                                          tamanho e o retrato do banco: linhas e md5 por tabela, funcoes, politicas, RLS,
                                          privilegios, restricoes, gatilhos, migrations; nenhum valor dos dados). Le o
                                          banco, nunca grava nele.
  verificar --manifesto ARQ               confere os SHA-256 dos arquivos do manifesto.
  restaurar --manifesto ARQ --dsn-env VAR restaura SO num banco vazio (sem tabelas em public/financeiro; recusa um banco
                                          existente) e HOMOLOGA: o retrato restaurado tem de ser igual ao do manifesto.
                                          Num projeto Supabase as contas entram so como dados; num banco de conferencia
                                          sem o Auth, com a estrutura. FIN-BLOCO-D-2.

Ferramentas: CF_PG_BIN_BACKUP (pasta bin do PostgreSQL) escolhe pg_dump/pg_restore; sem ela, PATH e depois a instalacao
local. FIN-PRE-PRODUCAO-1: para o Supabase (PostgreSQL 17), usar as ferramentas 17 (ensaiado em tests/test_backup_banco.py).

A conexao vem sempre de uma variavel de ambiente (--dsn-env) e nunca e impressa. Restauracao sobre banco existente e
recusada; restaurar no Supabase de teste ou de producao exige autorizacao especifica (FIN-BLOCO-C-1, C4).
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ESQUEMAS = ('public', 'financeiro')
TABELA_DOCUMENTOS = 'public.ir_comprovante_arquivo'
# FIN-BLOCO-D-2: o historico das migrations vai junto (quando existe), para reconstruir o estado anterior.
ESQUEMA_MIGRATIONS = 'supabase_migrations'
# Contas do Auth: users (os user_id das tabelas apontam para ela) e identities (o login por e-mail depende dela).
TABELAS_AUTH = ('auth.users', 'auth.identities')
PAPEIS_DA_API = ('anon', 'authenticated', 'service_role')
# A restauracao reescreve "x = ANY ((ARRAY['a'::varchar])::text[])" como "x = ANY (ARRAY[('a'::varchar)::text])": mesma
# regra; a forma e normalizada antes de comparar.
FORMA_RESTRICAO = re.compile(r'::(character varying|text)(\[\])?|[()\s]')


def conectar(dsn, leitura=True):
    import psycopg2
    conn = psycopg2.connect(dsn, connect_timeout=20)
    conn.set_session(readonly=leitura, autocommit=False)
    with conn.cursor() as cur:
        cur.execute("set timezone = 'UTC'; set datestyle = 'ISO, YMD'; set extra_float_digits = 1")
    return conn


def retrato(conn, esquemas=(*ESQUEMAS, ESQUEMA_MIGRATIONS)):
    """Impressao do banco sem nenhum valor dos dados: linhas e md5 por tabela, sequencias, funcoes, execucao pelos papeis
    da API, politicas, RLS, restricoes, gatilhos, privilegios (pelas ACLs: o information_schema so mostra o que o
    usuario conectado enxerga) e migrations aplicadas."""
    cur = conn.cursor()

    def q(sql, p=None):
        cur.execute(sql, p)
        return cur.fetchall()

    nsp = "('public'::regnamespace, 'financeiro'::regnamespace)"
    r = {'tabelas': {}, 'md5': {}}
    for (t,) in q("select table_schema || '.' || table_name from information_schema.tables where table_type = 'BASE TABLE' "
                  "and table_schema = any(%s) order by 1", (list(esquemas),)):
        esquema, nome = t.split('.')
        r['tabelas'][t] = q(f'select count(*) from "{esquema}"."{nome}"')[0][0]
        r['md5'][t] = q(f'select md5(coalesce(string_agg(x::text, \'|\' order by x::text), \'\')) from "{esquema}"."{nome}" x')[0][0]
    r['sequencias'] = dict(q("select schemaname || '.' || sequencename, coalesce(last_value, 0) from pg_sequences "
                             "where schemaname in ('public', 'financeiro')"))
    r['funcoes'] = dict(q("select p.oid::regprocedure::text, md5(p.prosrc || coalesce(array_to_string(p.proconfig, ','), '') "
                          f"|| p.prosecdef::text) from pg_proc p where p.pronamespace in {nsp}"))
    r['execucao'] = sorted(f'{g}:{f}' for g, f in q(
        "select g.rolname, p.oid::regprocedure::text from pg_proc p cross join (values ('anon'), ('authenticated'), ('service_role')) g(rolname) "
        f"where p.pronamespace in {nsp} and has_function_privilege(g.rolname, p.oid, 'execute')"))
    r['politicas'] = sorted('|'.join(map(str, x)) for x in q(
        "select schemaname, tablename, policyname, cmd, roles::text, coalesce(qual, ''), coalesce(with_check, '') from pg_policies "
        "where schemaname in ('public', 'financeiro')"))
    r['rls'] = sorted(f'{t}:{a}:{f}' for t, a, f in q(
        f"select c.oid::regclass::text, c.relrowsecurity, c.relforcerowsecurity from pg_class c where c.relkind = 'r' and c.relnamespace in {nsp}"))
    r['restricoes'] = sorted(f'{t}:{n}:{FORMA_RESTRICAO.sub("", d)}' for t, n, d in q(
        f"select conrelid::regclass::text, conname, pg_get_constraintdef(oid) from pg_constraint where contype in ('f', 'c', 'u', 'p') "
        f"and connamespace in {nsp}"))
    r['gatilhos'] = sorted(f'{t}:{n}' for t, n in q(
        f"select tgrelid::regclass::text, tgname from pg_trigger where not tgisinternal and tgrelid in (select oid from pg_class where relnamespace in {nsp})"))
    r['privilegios'] = sorted('|'.join(map(str, x)) for x in q(
        "select coalesce(nullif(a.grantee, 0)::regrole::text, 'PUBLIC'), c.oid::regclass::text, a.privilege_type "
        f"from pg_class c cross join lateral aclexplode(c.relacl) a where c.relnamespace in {nsp} and c.relkind in ('r', 'v', 'S') "
        "and (a.grantee = 0 or a.grantee::regrole::text in ('anon', 'authenticated', 'service_role'))"))
    tem_migrations = q("select to_regclass('supabase_migrations.schema_migrations') is not null")[0][0]
    r['migrations'] = [v for (v,) in q('select version from supabase_migrations.schema_migrations order by 1')] if tem_migrations else []
    conn.rollback()
    return r


def retrato_dsn(dsn, **kw):
    conn = conectar(dsn)
    try:
        return retrato(conn, **kw)
    finally:
        conn.close()


def comparar(a, b, ignorar_tabelas=()):
    """Diferencas entre dois retratos (nomes e quantidades; nenhum valor dos dados)."""
    difs = []
    for chave in ('tabelas', 'md5'):
        for t in sorted(set(a[chave]) | set(b[chave])):
            if t not in ignorar_tabelas and a[chave].get(t) != b[chave].get(t):
                difs.append(f'{chave}:{t}')
    for chave in ('sequencias', 'funcoes'):
        for t in sorted(set(a[chave]) | set(b[chave])):
            if a[chave].get(t) != b[chave].get(t):
                difs.append(f'{chave}:{t}')
    for chave in ('execucao', 'politicas', 'rls', 'restricoes', 'gatilhos', 'privilegios', 'migrations'):
        so_a, so_b = set(a[chave]) - set(b[chave]), set(b[chave]) - set(a[chave])
        if so_a or so_b:
            difs.append(f'{chave}: {len(so_a)} so no primeiro, {len(so_b)} so no segundo; ex.: '
                        f'{sorted(so_a)[:3]} / {sorted(so_b)[:3]}')
    return difs


def _ferramenta(nome):
    pasta_escolhida = os.environ.get('CF_PG_BIN_BACKUP')
    if pasta_escolhida:
        caminho = str(Path(pasta_escolhida) / (nome + ('.exe' if os.name == 'nt' else '')))
        if not Path(caminho).exists():
            raise SystemExit(f'{nome} nao encontrado em CF_PG_BIN_BACKUP.')
        return caminho
    caminho = shutil.which(nome)
    if not caminho:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tests.supabase_local import encontrar_pg_bin
        pasta = encontrar_pg_bin()
        caminho = str(Path(pasta) / (nome + ('.exe' if os.name == 'nt' else ''))) if pasta else None
    if not caminho or not Path(caminho).exists():
        raise SystemExit(f'{nome} nao encontrado (instale o PostgreSQL ou ponha-o no PATH).')
    return caminho


def _dsn(variavel):
    valor = os.environ.get(variavel or '')
    if not valor:
        raise SystemExit(f'Variavel de ambiente {variavel!r} vazia: informe a conexao por ela (nunca na linha de comando).')
    return valor


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, 'rb') as f:
        for bloco in iter(lambda: f.read(1 << 20), b''):
            h.update(bloco)
    return h.hexdigest()


def _linhas_por_tabela(dsn):
    import psycopg2
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True)
    try:
        with conn.cursor() as cur:
            cur.execute("select table_schema || '.' || table_name from information_schema.tables "
                        "where table_schema = any(%s) and table_type = 'BASE TABLE' order by 1", (list(ESQUEMAS),))
            tabelas = [r[0] for r in cur.fetchall()]
            saida = {}
            for t in tabelas:
                esquema, nome = t.split('.', 1)
                cur.execute(f'select count(*) from "{esquema}"."{nome}"')
                saida[t] = cur.fetchone()[0]
            return saida
    finally:
        conn.rollback()
        conn.close()


def _consulta(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def _existentes(cur, tabelas):
    return [t for t in tabelas if _consulta(cur, 'select to_regclass(%s) is not null', (t,))[0][0]]


def _ref(dsn):
    from urllib.parse import urlsplit
    partes = urlsplit(dsn)
    usuario, host = partes.username or '', partes.hostname or ''
    if usuario.startswith('postgres.'):
        return usuario.split('.', 1)[1]
    if host.startswith('db.') and host.endswith('.supabase.co'):
        return host.split('.')[1]
    return None


def exportar(args):
    """Backup logico consistente (so leitura): um snapshot exportado e usado por todos os pg_dump e pelo retrato do
    manifesto, que fica assim exatamente igual ao conteudo dos arquivos."""
    dsn = _dsn(args.dsn_env)
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    banco = pasta / f'banco_{carimbo}.dump'
    documentos = pasta / f'documentos_{carimbo}.dump'
    usuarios = pasta / f'usuarios_{carimbo}.dump'
    pg_dump = _ferramenta('pg_dump')
    conn = conectar(dsn)
    try:
        conn.rollback()
        cur = conn.cursor()
        cur.execute('set transaction isolation level repeatable read, read only')
        cur.execute("set local timezone = 'UTC'; set local datestyle = 'ISO, YMD'; set local extra_float_digits = 1")
        snapshot = _consulta(cur, 'select pg_export_snapshot()')[0][0]
        servidor = _consulta(cur, 'show server_version')[0][0]
        esquemas = list(ESQUEMAS) + ([ESQUEMA_MIGRATIONS] if _consulta(
            cur, 'select to_regnamespace(%s) is not null', (ESQUEMA_MIGRATIONS,))[0][0] else [])
        auth = _existentes(cur, TABELAS_AUTH)
        comuns = ['--format=custom', '--no-owner', f'--snapshot={snapshot}', f'--dbname={dsn}']
        # Banco: estrutura, dados, funcoes, politicas e privilegios (GRANT/REVOKE) de public, financeiro e do historico.
        subprocess.run([pg_dump, *comuns, *[f'--schema={e}' for e in esquemas], f'--file={banco}'], check=True, capture_output=True)
        subprocess.run([pg_dump, *comuns, '--no-privileges', '--data-only', f'--table={TABELA_DOCUMENTOS}', f'--file={documentos}'],
                       check=True, capture_output=True)
        # Contas do Auth com a estrutura (so usada se o destino nao tiver o schema auth do Supabase), sem os privilegios
        # internos da plataforma.
        subprocess.run([pg_dump, *comuns, '--no-privileges', *[f'--table={t}' for t in auth], f'--file={usuarios}'],
                       check=True, capture_output=True)
        linhas_auth = {t: _consulta(cur, f'select count(*) from {t}')[0][0] for t in auth}
        foto = retrato(conn, esquemas=esquemas)  # mesmo snapshot (a transacao segue aberta ate aqui)
    finally:
        conn.rollback()
        conn.close()
    versao = subprocess.run([pg_dump, '--version'], capture_output=True, text=True).stdout.strip()
    manifesto = {
        'gerado_em': dt.datetime.now().isoformat(timespec='seconds'), 'servidor': servidor, 'pg_dump': versao,
        'projeto_ref': _ref(dsn), 'esquemas': esquemas, 'auth': auth, 'snapshot_unico': True,
        'arquivos': {p.name: {'sha256': _sha256(p), 'bytes': p.stat().st_size} for p in (banco, documentos, usuarios)},
        'banco': banco.name, 'documentos': documentos.name, 'usuarios': usuarios.name,
        'linhas': {t: n for t, n in foto['tabelas'].items() if t.split('.')[0] in ESQUEMAS},
        'linhas_auth': linhas_auth, 'retrato': foto,
    }
    caminho = pasta / f'manifesto_{carimbo}.json'
    caminho.write_text(json.dumps(manifesto, indent=1, ensure_ascii=False, default=str), encoding='utf-8')
    print(f'Backup gravado: {banco.name}, {documentos.name}, {usuarios.name}, {caminho.name} '
          f'({sum(manifesto["linhas"].values())} linhas em {len(manifesto["linhas"])} tabelas; '
          f'{len(foto["migrations"])} migrations; Auth: {", ".join(f"{t} {n}" for t, n in linhas_auth.items()) or "nenhuma"})')
    return caminho


def verificar(args):
    caminho = Path(args.manifesto)
    manifesto = json.loads(caminho.read_text(encoding='utf-8'))
    erros = [nome for nome, d in manifesto['arquivos'].items() if _sha256(caminho.parent / nome) != d['sha256']]
    if erros:
        raise SystemExit(f'Arquivos alterados ou corrompidos: {", ".join(erros)}')
    print('Backup integro (SHA-256 conferidos).')
    return manifesto


def _erros(stderr):
    """Erros do pg_restore, fora o unico aceito: schema que ja existe no banco novo (public; supabase_migrations num
    projeto Supabase)."""
    return [l for l in (stderr or '').splitlines() if 'error:' in l.lower()
            and not re.search(r'schema "[a-z_]+" already exists', l) and 'errors ignored on restore' not in l]


def restaurar(args):
    """Restaura SO num banco sem tabelas em public/financeiro e homologa: o retrato restaurado tem de ser IGUAL ao do
    manifesto (dados, funcoes, politicas, RLS, privilegios, restricoes, gatilhos, migrations) e as contas do Auth tem de
    ter as mesmas linhas. Devolve o que foi restaurado e o que depende de configuracao do Supabase."""
    manifesto = verificar(args)
    dsn = _dsn(args.dsn_env)
    conn = conectar(dsn, leitura=False)
    try:
        cur = conn.cursor()
        cur.execute("select count(*) from information_schema.tables where table_schema = any(%s)", (list(ESQUEMAS),))
        if cur.fetchone()[0]:
            raise SystemExit('Destino nao esta vazio (ha tabelas em public/financeiro): restauracao recusada. '
                             'Restaure so num banco novo e vazio.')
        # Privilegios padrao do destino (no Supabase: ALL para anon/authenticated nas tabelas novas do public) dariam as
        # tabelas restauradas mais acesso que no backup, que so emite o que difere do padrao do PostgreSQL.
        papeis = [r[0] for r in _consulta(cur, 'select rolname from pg_roles where rolname = any(%s)', (list(PAPEIS_DA_API),))]
        if papeis:
            for tipo in ('tables', 'sequences', 'functions'):
                cur.execute(f'alter default privileges in schema public revoke all on {tipo} from {", ".join(papeis)}')
        auth_no_destino = _existentes(cur, manifesto.get('auth', ['auth.users']))
        conn.commit()
    finally:
        conn.close()
    pg_restore = _ferramenta('pg_restore')
    pasta = Path(args.manifesto).parent
    resultado = {'restaurado': [], 'depende_do_supabase': []}
    # 1o as contas do Auth (as tabelas financeiras apontam para auth.users), depois o banco. Projeto Supabase (as tabelas
    # do Auth ja existem): so os dados. Banco de conferencia sem nenhuma delas: o arquivo inteiro (estrutura, chaves e
    # indices). Parcial: recusado (o shim local tem um auth.users simplificado; retire-o antes).
    auth = manifesto.get('auth', ['auth.users'])
    if auth_no_destino and set(auth_no_destino) != set(auth):
        raise SystemExit(f'Destino com so parte das tabelas do Auth ({auth_no_destino} de {auth}): restauracao recusada')
    so_dados = bool(auth_no_destino)
    r = subprocess.run([pg_restore, '--no-owner', '--no-privileges', '--exit-on-error', *(['--data-only'] if so_dados else []),
                        f'--dbname={dsn}', str(pasta / manifesto['usuarios'])], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('pg_restore (Auth) falhou: ' + (r.stderr or '')[-1500:])
    resultado['restaurado'].append(f'{", ".join(auth)}: dados' + ('' if so_dados else ', estrutura, chaves e indices (banco sem o Auth do Supabase)'))
    r = subprocess.run([pg_restore, '--no-owner', f'--dbname={dsn}', str(pasta / manifesto['banco'])], capture_output=True, text=True)
    erros = _erros(r.stderr)
    if erros:
        raise SystemExit('pg_restore falhou: ' + ' | '.join(erros)[-1500:])
    resultado['restaurado'].append(f'{", ".join(manifesto.get("esquemas", ESQUEMAS))}: estrutura, dados, funcoes, politicas '
                                   'e privilegios')
    resultado['depende_do_supabase'] = [
        'configuracao do Auth (provedores, cadastro, URLs, SMTP, MFA) e chaves da API: sao do projeto, fora do banco',
        'demais tabelas do schema auth (sessoes, refresh tokens, fatores MFA): nao copiadas; o titular entra de novo',
        'privilegios internos da plataforma sobre o schema auth',
    ]
    if 'retrato' in manifesto:
        difs = comparar(manifesto['retrato'], retrato_dsn(dsn, esquemas=manifesto['esquemas']))
        conn = conectar(dsn)
        try:
            linhas_auth = {t: _consulta(conn.cursor(), f'select count(*) from {t}')[0][0] for t in manifesto.get('auth', [])}
        finally:
            conn.close()
        if linhas_auth != manifesto.get('linhas_auth', linhas_auth):
            difs.append(f'auth: {linhas_auth} restauradas, {manifesto["linhas_auth"]} no backup')
        if difs:
            raise SystemExit(f'Backup NAO HOMOLOGADO: a restauracao diverge do backup: {difs[:20]}')
        resultado['homologacao'] = ('HOMOLOGADO: restauracao identica ao backup (dados, sequencias, funcoes, politicas, RLS, '
                                    'privilegios, restricoes, gatilhos, migrations e contas do Auth)')
    else:
        restauradas = _linhas_por_tabela(dsn)
        divergentes = {t: (n, restauradas.get(t)) for t, n in manifesto['linhas'].items() if restauradas.get(t) != n}
        if divergentes:
            raise SystemExit(f'Linhas divergentes depois da restauracao: {divergentes}')
        resultado['homologacao'] = 'linhas por tabela iguais (manifesto antigo, sem retrato)'
    print(f'Restauracao conferida: {resultado["homologacao"]}')
    return resultado


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='comando', required=True)
    e = sub.add_parser('exportar')
    e.add_argument('--dsn-env', required=True)
    e.add_argument('--saida', required=True)
    v = sub.add_parser('verificar')
    v.add_argument('--manifesto', required=True)
    r = sub.add_parser('restaurar')
    r.add_argument('--manifesto', required=True)
    r.add_argument('--dsn-env', required=True)
    args = p.parse_args(argv)
    return {'exportar': exportar, 'verificar': verificar, 'restaurar': restaurar}[args.comando](args)


if __name__ == '__main__':
    main()
