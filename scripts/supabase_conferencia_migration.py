"""
CONFERENCIA-MIGRATION — conferencia SOMENTE LEITURA de uma migration do Supabase, antes e depois de aplica-la.

Generaliza a verificacao do FIN-FATURA-INTEGRIDADE-REAL-1 (preparada no FIN-CARTOES-FECHAMENTO-1). Compara o banco
com o estado esperado, montado num cluster PostgreSQL descartavel com as migrations do repositorio:
- funcoes do schema financeiro: assinatura, retorno, SECURITY DEFINER, search_path, corpo (md5) e EXECUTE para
  PUBLIC, anon e authenticated;
- tabelas de public e financeiro: colunas, RLS (habilitada e forcada) e privilegios de anon e authenticated;
- conteudo de todas as tabelas (contagem + md5), sem as colunas que a migration cria: nada existente pode mudar;
- colunas criadas pela migration: so o valor padrao (nada preenchido retroativamente).
Nunca aplica migration no remoto, nunca grava nele (sessao read-only) e nunca imprime connection string nem linhas.

Uso (da raiz do repositorio):
    # local: cluster descartavel; lista o que a migration muda e confere dados e privilegios
    venv\\Scripts\\python.exe scripts\\supabase_conferencia_migration.py --alvo 20261030090000 local
    # remoto (Supabase de teste, .env.staging; SO com autorizacao do contrato *-REAL-1):
    venv\\Scripts\\python.exe scripts\\supabase_conferencia_migration.py --alvo 20261030090000 antes --saida <pasta>
    venv\\Scripts\\python.exe scripts\\supabase_conferencia_migration.py --alvo 20261030090000 depois --saida <pasta>
'antes' grava em --saida (fora do repositorio) a impressao digital e as definicoes atuais das funcoes que a
migration troca (diagnostico e base para um eventual rollback); 'depois' compara com ela.
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
MIGRATIONS = RAIZ / 'supabase' / 'migrations'
# O ref completo do projeto de teste nao e versionado (convencao do repositorio, como em supabase_migrations.py):
# vem do .env.staging; aqui so o prefixo ja citado nos documentos e o projeto proibido.
PREFIXO_AUTORIZADO = 'fzjmge'
PROJETOS_PROIBIDOS = {'dshqjhyymtpxpxuntzbz'}  # Calculadora Judicial / Portal Kortex
ESQUEMAS = ('public', 'financeiro')

Q_FUNCOES = """
select p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')', pg_get_function_result(p.oid),
       p.prosecdef, coalesce(array_to_string(p.proconfig, ','), ''), md5(replace(p.prosrc, chr(13), '')),
       exists (select 1 from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
                where a.grantee = 0 and a.privilege_type = 'EXECUTE'),
       has_function_privilege('anon', p.oid, 'EXECUTE'), has_function_privilege('authenticated', p.oid, 'EXECUTE')
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'financeiro'"""
CAMPOS_FUNCAO = ('retorno', 'definer', 'config', 'corpo', 'public', 'anon', 'authenticated')

Q_TABELAS = """
select n.nspname || '.' || c.relname, c.relrowsecurity, c.relforcerowsecurity,
       has_table_privilege('anon', c.oid, 'SELECT'), has_table_privilege('anon', c.oid, 'INSERT'),
       has_table_privilege('anon', c.oid, 'UPDATE'), has_table_privilege('anon', c.oid, 'DELETE'),
       has_table_privilege('authenticated', c.oid, 'SELECT'), has_table_privilege('authenticated', c.oid, 'INSERT'),
       has_table_privilege('authenticated', c.oid, 'UPDATE'), has_table_privilege('authenticated', c.oid, 'DELETE'),
       (select string_agg(a.attname || ':' || format_type(a.atttypid, a.atttypmod) || case when a.attnotnull
                          then ' not null' else '' end, ', ' order by a.attnum)
          from pg_attribute a where a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped)
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where c.relkind = 'r' and n.nspname in ('public', 'financeiro')"""


def arquivo_alvo(alvo):
    arquivos = sorted(MIGRATIONS.glob(f'{alvo}_*.sql'))
    if len(arquivos) != 1:
        raise SystemExit(f'migration {alvo} nao encontrada (ou ambigua) em supabase/migrations')
    return arquivos[0]


def objetos_criados(texto):
    """Colunas ({tabela: [colunas]}) e tabelas que a migration cria com IF NOT EXISTS."""
    colunas = {}
    for esquema, tabela, coluna in re.findall(r'alter\s+table\s+(?:only\s+)?(?:(\w+)\.)?(\w+)\s+add\s+column\s+'
                                              r'if\s+not\s+exists\s+(\w+)', texto, re.I):
        colunas.setdefault(f'{esquema or "public"}.{tabela}', []).append(coluna)
    tabelas = [f'{e or "public"}.{t}' for e, t in
               re.findall(r'create\s+table\s+if\s+not\s+exists\s+(?:(\w+)\.)?(\w+)', texto, re.I)]
    return colunas, tabelas


def capturar(cur, sem_colunas=None):
    """Catalogo e impressao digital do conteudo (sem as colunas indicadas, para comparar com o antes)."""
    sem_colunas = sem_colunas or {}
    cur.execute(Q_FUNCOES)
    funcoes = {r[0]: dict(zip(CAMPOS_FUNCAO, r[1:])) for r in cur.fetchall()}
    cur.execute(Q_TABELAS)
    tabelas = {r[0]: {'rls': [r[1], r[2]], 'anon': ''.join('SIUD'[i] if v else '-' for i, v in enumerate(r[3:7])),
                      'authenticated': ''.join('SIUD'[i] if v else '-' for i, v in enumerate(r[7:11])),
                      'colunas': r[11] or ''} for r in cur.fetchall()}
    conteudo = {}
    for tabela in sorted(tabelas):
        tirar = ''.join(f" - '{c}'" for c in sem_colunas.get(tabela, ()))
        cur.execute(f'select count(*), md5(coalesce(string_agg((to_jsonb(x){tirar})::text, \'|\' '
                    f'order by (to_jsonb(x){tirar})::text), \'\')) from {tabela} x')
        conteudo[tabela] = list(cur.fetchone())
    return {'funcoes': funcoes, 'tabelas': tabelas, 'conteudo': conteudo}


def mudancas(antes, depois):
    """O que mudou no catalogo (funcoes e tabelas), em texto."""
    linhas = []
    fa, fd = antes['funcoes'], depois['funcoes']
    for nome in sorted(set(fd) - set(fa)):
        f = fd[nome]
        linhas.append(f'funcao nova: {nome} | EXECUTE public/anon/authenticated = '
                      f'{f["public"]}/{f["anon"]}/{f["authenticated"]} | definer={f["definer"]} config={f["config"]}')
    for nome in sorted(set(fa) - set(fd)):
        linhas.append(f'funcao removida: {nome}')
    for nome in sorted(set(fa) & set(fd)):
        campos = [c for c in CAMPOS_FUNCAO if fa[nome][c] != fd[nome][c]]
        if campos:
            linhas.append(f'funcao alterada: {nome} ({", ".join(campos)})')
    ta, td = antes['tabelas'], depois['tabelas']
    for nome in sorted(set(td) - set(ta)):
        t = td[nome]
        linhas.append(f'tabela nova: {nome} | rls={t["rls"]} anon={t["anon"]} authenticated={t["authenticated"]}')
    for nome in sorted(set(ta) - set(td)):
        linhas.append(f'tabela removida: {nome}')
    for nome in sorted(set(ta) & set(td)):
        for campo in ('rls', 'anon', 'authenticated', 'colunas'):
            if ta[nome][campo] != td[nome][campo]:
                linhas.append(f'tabela alterada: {nome} ({campo}): {ta[nome][campo]} -> {td[nome][campo]}')
    return linhas


def diferencas(real, esperado):
    """Onde o catalogo real difere do esperado (funcoes do financeiro e tabelas comuns)."""
    falhas = []
    so_real = sorted(set(real['funcoes']) - set(esperado['funcoes']))
    so_esperado = sorted(set(esperado['funcoes']) - set(real['funcoes']))
    if so_real or so_esperado:
        falhas.append(f'funcoes: so no banco {so_real} | so no esperado {so_esperado}')
    for nome in sorted(set(real['funcoes']) & set(esperado['funcoes'])):
        campos = [c for c in CAMPOS_FUNCAO if real['funcoes'][nome][c] != esperado['funcoes'][nome][c]]
        if campos:
            falhas.append(f'funcao {nome} diferente do esperado ({", ".join(campos)})')
    for nome in sorted(set(real['tabelas']) & set(esperado['tabelas'])):
        for campo in ('rls', 'anon', 'authenticated'):
            if real['tabelas'][nome][campo] != esperado['tabelas'][nome][campo]:
                falhas.append(f'tabela {nome}: {campo} {real["tabelas"][nome][campo]} (esperado '
                              f'{esperado["tabelas"][nome][campo]})')
    for nome in sorted(set(esperado['tabelas']) - set(real['tabelas'])):
        falhas.append(f'tabela esperada ausente: {nome}')
    # SEC-SUPABASE-PUBLIC-1: nada do public exposto a Data API. No financeiro, tabelas lidas sob RLS pelo novo
    # aplicativo (categorias, perfil_acesso) tem privilegio por desenho: ja comparadas com o esperado acima.
    expostas = sorted(n for n, t in real['tabelas'].items()
                      if n.startswith('public.') and (t['anon'] != '----' or t['authenticated'] != '----'))
    if expostas:
        falhas.append(f'tabelas do public com privilegio para anon/authenticated: {expostas}')
    return falhas


def conferir_dados(antes, depois):
    """Tabelas existentes antes com conteudo diferente depois (sem as colunas novas)."""
    return sorted(t for t in antes['conteudo'] if antes['conteudo'][t] != depois['conteudo'].get(t))


def valores_fora_do_padrao(cur, colunas):
    """Colunas criadas pela migration com valor diferente do padrao (preenchimento retroativo indevido)."""
    falhas = []
    for tabela, nomes in colunas.items():
        esquema, nome_tabela = tabela.split('.')
        for coluna in nomes:
            cur.execute('select column_default from information_schema.columns where table_schema = %s '
                        'and table_name = %s and column_name = %s', (esquema, nome_tabela, coluna))
            linha = cur.fetchone()
            if linha is None:
                falhas.append(f'{tabela}.{coluna}: coluna ausente')
                continue
            cur.execute(f'select count(*) from {tabela} where {coluna} is distinct from ({linha[0] or "null"})')
            fora = cur.fetchone()[0]
            if fora:
                falhas.append(f'{tabela}.{coluna}: {fora} linha(s) fora do padrao {linha[0] or "null"}')
    return falhas


# ---------------------------------------------------------------------------
# Estado esperado: cluster descartavel com as migrations do repositorio
# ---------------------------------------------------------------------------

def preparar_antes(cluster, alvo, contas=True):
    """Cluster no estado 'antes' do alvo: tabelas do Flask sem o que o alvo cria + migrations anteriores + dados
    ficticios como os do tests/supabase_local.py. Devolve (colunas criadas, tabelas criadas, arquivo do alvo)."""
    sys.path.insert(0, str(RAIZ))
    from tests.supabase_local import (CATEGORIAS_A, CATEGORIAS_B, USUARIO_A, USUARIO_B, semear_contas,
                                      semear_perfis)
    caminho = arquivo_alvo(alvo)
    colunas, tabelas = objetos_criados(caminho.read_text(encoding='utf-8'))
    cluster.aplicar_shim()
    cluster.criar_tabelas_legadas()  # usa os models atuais, que ja tem o que o alvo cria: remover
    conn = cluster.conectar()
    try:
        with conn.cursor() as cur:
            for tabela in tabelas:
                cur.execute(f'drop table if exists {tabela} cascade')
            for tabela, nomes in colunas.items():
                for coluna in nomes:
                    cur.execute(f'alter table {tabela} drop column if exists {coluna} cascade')
            for migration in sorted(MIGRATIONS.glob('*.sql')):
                if migration.name < caminho.name:
                    cur.execute(migration.read_text(encoding='utf-8'))
            for usuario in (USUARIO_A, USUARIO_B):
                cur.execute('insert into auth.users (id, email) values (%s, %s)', (usuario['id'], usuario['email']))
            for usuario, nomes in ((USUARIO_A, CATEGORIAS_A), (USUARIO_B, CATEGORIAS_B)):
                for nome in nomes:
                    cur.execute('insert into financeiro.categorias (user_id, nome, descricao) values (%s, %s, %s)',
                                (usuario['id'], nome, 'Dado ficticio de teste'))
            semear_perfis(cur)
            if contas:
                semear_contas(cur)
    finally:
        conn.close()
    return colunas, tabelas, caminho


def conferencia_local(alvo, semear=None, ao_capturar_antes=None, ao_capturar_depois=None, contas=True):
    """Aplica o alvo num cluster descartavel com dados. `semear(dsn)` cria dados extras no estado antes;
    `ao_capturar_antes(conn)` / `ao_capturar_depois(conn)` rodam logo antes e logo depois da migration (ex.: a
    conferencia 'antes'/'depois' que se faria no remoto). contas=False: sem os dados do MOBILE-CONTAS-1.
    Devolve {'antes', 'depois', 'mudancas', 'falhas', 'colunas'}."""
    sys.path.insert(0, str(RAIZ))
    from tests.supabase_local import ClusterLocal, encontrar_pg_bin
    pg_bin = encontrar_pg_bin()
    if not pg_bin:
        raise SystemExit('binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')
    with tempfile.TemporaryDirectory(prefix='cf-conferencia-') as tmp:
        with ClusterLocal(pg_bin, Path(tmp)) as cluster:
            colunas, _, caminho = preparar_antes(cluster, alvo, contas)
            if semear:
                semear(cluster.dsn())
            conn = cluster.conectar()
            try:
                with conn.cursor() as cur:
                    antes = capturar(cur)
                    if ao_capturar_antes:
                        ao_capturar_antes(conn)
                    cur.execute(caminho.read_text(encoding='utf-8'))
                    if ao_capturar_depois:
                        ao_capturar_depois(conn)
                    depois = capturar(cur, colunas)
                    falhas = [f'conteudo alterado: {t}' for t in conferir_dados(antes, depois)]
                    falhas += valores_fora_do_padrao(cur, colunas)
                    falhas += [f for f in diferencas(depois, depois) if f.startswith('tabelas do public com privilegio')]
            finally:
                conn.close()
    return {'antes': antes, 'depois': depois, 'mudancas': mudancas(antes, depois), 'falhas': falhas,
            'colunas': colunas}


# ---------------------------------------------------------------------------
# Conferencia de um banco (remoto, ou local nos testes) contra o esperado
# ---------------------------------------------------------------------------

def conferir_banco(cur, alvo, modo, saida, esperado, exigir_historico=True):
    """modo 'antes': o banco tem de bater com o esperado sem o alvo; grava impressao digital e definicoes.
    modo 'depois': bater com o esperado com o alvo, conteudo igual ao 'antes' e colunas novas so no padrao."""
    falhas = []
    caminho = arquivo_alvo(alvo)
    try:
        cur.execute('select version from supabase_migrations.schema_migrations order by 1')
        versoes = [r[0] for r in cur.fetchall()]
        locais = sorted(p.name.split('_', 1)[0] for p in MIGRATIONS.glob('*.sql'))
        pendentes = [v for v in locais if v not in versoes]
        print(f'migrations: locais {len(locais)} | aplicadas {len(versoes)} | pendentes {pendentes} | '
              f'so no banco {[v for v in versoes if v not in locais]}')
        if pendentes != ([alvo] if modo == 'antes' else []) or any(v not in locais for v in versoes):
            falhas.append('historico de migrations inesperado')
    except Exception:  # noqa: BLE001 — banco local de teste nao tem o historico do Supabase
        cur.connection.rollback()
        if exigir_historico:
            falhas.append('historico de migrations indisponivel')
    real = capturar(cur, esperado['colunas'] if modo == 'depois' else None)
    falhas += diferencas(real, esperado[modo])
    saida.mkdir(parents=True, exist_ok=True)
    digital = saida / f'conferencia_{alvo}_antes.json'
    if modo == 'antes':
        trocadas = sorted(n for n in esperado['antes']['funcoes']
                          if n not in esperado['depois']['funcoes']
                          or esperado['antes']['funcoes'][n] != esperado['depois']['funcoes'][n])
        definicoes = []
        for nome in trocadas:
            cur.execute("select pg_get_functiondef(p.oid) from pg_proc p where p.pronamespace = "
                        "'financeiro'::regnamespace and p.proname || '(' || pg_get_function_identity_arguments(p.oid) "
                        "|| ')' = %s", (nome,))
            linha = cur.fetchone()
            if linha:
                definicoes.append(linha[0])
        (saida / f'conferencia_{alvo}_definicoes_antes.sql').write_text('\n\n'.join(definicoes), encoding='utf-8')
        digital.write_text(json.dumps(real), encoding='utf-8')
        print(f'antes: {len(real["tabelas"])} tabelas e {len(real["funcoes"])} funcoes capturadas; '
              f'{len(definicoes)} definicoes atuais salvas (funcoes que o alvo troca)')
    else:
        antes = json.loads(digital.read_text(encoding='utf-8'))
        falhas += [f'conteudo alterado: {t}' for t in conferir_dados(antes, real)]
        falhas += valores_fora_do_padrao(cur, esperado['colunas'])
        print('mudancas observadas no banco:')
        for linha in mudancas(antes, real):
            print(f'  {linha}')
    print(f'{caminho.name} [{modo}]:', 'OK' if not falhas else 'FALHAS')
    for f in falhas:
        print(f'  - {f}')
    return falhas


def projeto_da_url(url):
    """Ref do projeto pelo usuario do pooler (postgres.<ref>); recusa o proibido e o que nao for o de teste."""
    usuario = urlsplit(url).username or ''
    ref = usuario.split('.', 1)[1] if usuario.startswith('postgres.') else ''
    if not ref or ref in PROJETOS_PROIBIDOS or any(p in url for p in PROJETOS_PROIBIDOS) \
            or not ref.startswith(PREFIXO_AUTORIZADO):
        raise SystemExit('projeto diferente do autorizado no .env.staging: nada foi feito')
    return ref


def conectar_remoto():
    import psycopg2
    from dotenv import dotenv_values
    url = dotenv_values(RAIZ / '.env.staging', encoding='utf-8-sig').get('DATABASE_URL') or ''
    ref = projeto_da_url(url)
    conn = psycopg2.connect(url, connect_timeout=15)
    conn.set_session(readonly=True)
    with conn.cursor() as cur:
        cur.execute("set statement_timeout = '60s'")
    print(f'conectado (somente leitura) ao projeto <{ref[:6]}…>')
    return conn


def main():
    parser = argparse.ArgumentParser(description='Conferencia somente leitura de uma migration do Supabase.')
    parser.add_argument('--alvo', required=True, help='versao da migration (ex.: 20261030090000)')
    parser.add_argument('modo', choices=('local', 'antes', 'depois'))
    parser.add_argument('--saida', help='pasta FORA do repositorio para a impressao digital (antes/depois)')
    args = parser.parse_args()
    esperado = conferencia_local(args.alvo)
    print(f'esperado ({arquivo_alvo(args.alvo).name}), montado em cluster descartavel:')
    for linha in esperado['mudancas']:
        print(f'  {linha}')
    if args.modo == 'local':
        print('dados e colunas novas no cluster:', 'OK' if not esperado['falhas'] else esperado['falhas'])
        sys.exit(1 if esperado['falhas'] else 0)
    if not args.saida or Path(args.saida).resolve().is_relative_to(RAIZ):
        raise SystemExit('--saida obrigatoria e fora do repositorio')
    conn = conectar_remoto()
    try:
        with conn.cursor() as cur:
            falhas = conferir_banco(cur, args.alvo, args.modo, Path(args.saida), esperado)
    finally:
        conn.rollback()
        conn.close()
    sys.exit(1 if falhas else 0)


if __name__ == '__main__':
    main()
