"""
FIN-RELATORIOS-CONFIG-1 (FIN-BLOCO-B-1, B2) — backup e restauracao verificavel do banco do novo aplicativo (PostgreSQL /
Supabase), sem dependencia nova (pg_dump/pg_restore do PostgreSQL instalado).

  exportar  --dsn-env VAR --saida PASTA   pg_dump dos esquemas public e financeiro (formato custom) + arquivo separado
                                          so com os documentos (public.ir_comprovante_arquivo) + os dados de auth.users
                                          (as tabelas apontam para eles) + manifesto (SHA-256, tamanho, linhas por
                                          tabela). Le o banco, nunca grava nele.
  verificar --manifesto ARQ               confere os SHA-256 dos arquivos do manifesto.
  restaurar --manifesto ARQ --dsn-env VAR restaura SO num banco vazio (sem tabelas em public/financeiro; recusa um banco
                                          existente) e confere as linhas por tabela com o manifesto.

A conexao vem sempre de uma variavel de ambiente (--dsn-env) e nunca e impressa. Restauracao sobre banco existente e
recusada; restaurar no Supabase de teste ou de producao exige autorizacao especifica (FIN-BLOCO-C-1, C4).
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ESQUEMAS = ('public', 'financeiro')
TABELA_DOCUMENTOS = 'public.ir_comprovante_arquivo'


def _ferramenta(nome):
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


def exportar(args):
    dsn = _dsn(args.dsn_env)
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    banco = pasta / f'banco_{carimbo}.dump'
    documentos = pasta / f'documentos_{carimbo}.dump'
    usuarios = pasta / f'usuarios_{carimbo}.dump'
    pg_dump = _ferramenta('pg_dump')
    comuns = ['--format=custom', '--no-owner', '--no-privileges']
    subprocess.run([pg_dump, *comuns, *[f'--schema={e}' for e in ESQUEMAS], f'--file={banco}', f'--dbname={dsn}'],
                   check=True, capture_output=True)
    subprocess.run([pg_dump, *comuns, '--data-only', f'--table={TABELA_DOCUMENTOS}', f'--file={documentos}', f'--dbname={dsn}'],
                   check=True, capture_output=True)
    # Contas de login (auth.users): user_id das tabelas financeiras aponta para elas; sem elas a restauracao falha.
    subprocess.run([pg_dump, *comuns, '--data-only', '--table=auth.users', f'--file={usuarios}', f'--dbname={dsn}'],
                   check=True, capture_output=True)
    manifesto = {
        'gerado_em': dt.datetime.now().isoformat(timespec='seconds'), 'esquemas': list(ESQUEMAS),
        'arquivos': {p.name: {'sha256': _sha256(p), 'bytes': p.stat().st_size} for p in (banco, documentos, usuarios)},
        'banco': banco.name, 'documentos': documentos.name, 'usuarios': usuarios.name, 'linhas': _linhas_por_tabela(dsn),
    }
    caminho = pasta / f'manifesto_{carimbo}.json'
    caminho.write_text(json.dumps(manifesto, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'Backup gravado: {banco.name}, {documentos.name}, {caminho.name} '
          f'({sum(manifesto["linhas"].values())} linhas em {len(manifesto["linhas"])} tabelas)')
    return caminho


def verificar(args):
    caminho = Path(args.manifesto)
    manifesto = json.loads(caminho.read_text(encoding='utf-8'))
    erros = [nome for nome, d in manifesto['arquivos'].items() if _sha256(caminho.parent / nome) != d['sha256']]
    if erros:
        raise SystemExit(f'Arquivos alterados ou corrompidos: {", ".join(erros)}')
    print('Backup integro (SHA-256 conferidos).')
    return manifesto


def restaurar(args):
    manifesto = verificar(args)
    dsn = _dsn(args.dsn_env)
    import psycopg2
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("select count(*) from information_schema.tables where table_schema = any(%s)", (list(ESQUEMAS),))
            if cur.fetchone()[0]:
                raise SystemExit('Destino nao esta vazio (ha tabelas em public/financeiro): restauracao recusada. '
                                 'Restaure so num banco novo e vazio.')
    finally:
        conn.close()
    pg_restore = _ferramenta('pg_restore')
    pasta = Path(args.manifesto).parent
    # 1o as contas de login (o destino ja tem auth.users: Supabase novo ou o shim local), depois o banco.
    r = subprocess.run([pg_restore, '--no-owner', '--no-privileges', '--data-only', '--exit-on-error', f'--dbname={dsn}',
                        str(pasta / manifesto['usuarios'])], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('pg_restore (auth.users) falhou: ' + (r.stderr or '')[-1500:])
    arquivo = pasta / manifesto['banco']
    r = subprocess.run([pg_restore, '--no-owner', '--no-privileges', f'--dbname={dsn}', str(arquivo)],
                       capture_output=True, text=True)
    # Num banco novo o esquema public ja existe (PostgreSQL 15+): esse e o unico erro aceito.
    erros = [l for l in (r.stderr or '').splitlines() if 'error:' in l.lower()
             and 'schema "public" already exists' not in l and 'errors ignored on restore' not in l]
    if erros:
        raise SystemExit('pg_restore falhou: ' + ' | '.join(erros)[-1500:])
    restauradas = _linhas_por_tabela(dsn)
    divergentes = {t: (n, restauradas.get(t)) for t, n in manifesto['linhas'].items() if restauradas.get(t) != n}
    if divergentes:
        raise SystemExit(f'Linhas divergentes depois da restauracao: {divergentes}')
    print(f'Restauracao conferida: {len(restauradas)} tabelas, mesmas linhas do backup.')


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
