"""
SUPABASE-DEPLOY-CONTROL-1 — aplicacao MANUAL e explicita das migrations de supabase/.

Unico caminho previsto para alterar a estrutura do banco do Controle Financeiro
depois que o "Deploy to production" da integracao GitHub for desligado.

Seguranca:
- projeto lido do .env.staging (usuario postgres.<ref> do pooler); recusa o da
  Calculadora Judicial;
- nunca imprime a connection string;
- `status` e `simular` so leem;
- `aplicar` exige --versoes com EXATAMENTE as versoes pendentes autorizadas: se o
  conjunto pendente for diferente (mais ou menos), nada e aplicado;
- usa uma copia temporaria de supabase/migrations com um config.toml minimo, sem
  criar supabase/config.toml no repositorio (que a integracao GitHub leria).

Uso:
    venv\\Scripts\\python.exe scripts\\supabase_migrations.py status
    venv\\Scripts\\python.exe scripts\\supabase_migrations.py simular
    venv\\Scripts\\python.exe scripts\\supabase_migrations.py aplicar --versoes 20261101090000
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
MIGRATIONS = RAIZ / 'supabase' / 'migrations'
PROJETOS_PROIBIDOS = {'dshqjhyymtpxpxuntzbz'}  # Calculadora Judicial / Portal Kortex


def _url():
    from dotenv import dotenv_values
    url = dotenv_values(RAIZ / '.env.staging', encoding='utf-8-sig').get('DATABASE_URL') or ''
    usuario = urlsplit(url).username or ''
    ref = usuario.split('.', 1)[1] if usuario.startswith('postgres.') else ''
    if not ref or ref in PROJETOS_PROIBIDOS:
        raise SystemExit('Projeto invalido ou proibido no .env.staging.')
    return url, ref


def _limpar(texto, url):
    texto = texto.replace(url, '<db-url>')
    return re.sub(r'postgres(ql)?://[^\s"]+', '<db-url>', texto)


def _versoes_locais():
    return sorted(p.name.split('_', 1)[0] for p in MIGRATIONS.glob('*.sql'))


def _versoes_remotas(url):
    import psycopg2
    conn = psycopg2.connect(url, connect_timeout=15)
    conn.set_session(readonly=True)
    try:
        with conn.cursor() as cur:
            cur.execute("select to_regclass('supabase_migrations.schema_migrations') is not null")
            if not cur.fetchone()[0]:
                return []
            cur.execute('select version from supabase_migrations.schema_migrations order by 1')
            return [linha[0] for linha in cur.fetchall()]
    finally:
        conn.close()


def _cli(url, *args):
    cli = shutil.which('supabase')
    if not cli:
        raise SystemExit('Supabase CLI nao encontrada.')
    with tempfile.TemporaryDirectory(prefix='cf-supa-mig-') as tmp:
        destino = Path(tmp) / 'supabase' / 'migrations'
        destino.mkdir(parents=True)
        for arquivo in MIGRATIONS.glob('*.sql'):
            shutil.copy2(arquivo, destino / arquivo.name)
        (Path(tmp) / 'supabase' / 'config.toml').write_text('project_id = "controle-financeiro"\n', encoding='utf-8')
        r = subprocess.run([cli, *args, '--db-url', url, '--workdir', tmp], capture_output=True, text=True,
                           timeout=300, input='')
    return r.returncode, _limpar(r.stdout + r.stderr, url)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='comando', required=True)
    sub.add_parser('status')
    sub.add_parser('simular')
    aplicar = sub.add_parser('aplicar')
    aplicar.add_argument('--versoes', required=True, help='versoes autorizadas, separadas por virgula')
    args = parser.parse_args()

    url, ref = _url()
    locais, remotas = _versoes_locais(), _versoes_remotas(url)
    pendentes = [v for v in locais if v not in remotas]
    so_no_remoto = [v for v in remotas if v not in locais]
    print(f'Projeto: {ref[:6]}… | locais: {len(locais)} | aplicadas no remoto: {len(remotas)}')
    print(f'Pendentes: {pendentes or "nenhuma"}')
    if so_no_remoto:
        print(f'ATENCAO: no remoto, mas nao no repositorio: {so_no_remoto}')

    if args.comando == 'status':
        return 0

    if args.comando == 'simular':
        codigo, saida = _cli(url, 'db', 'push', '--dry-run')
        print(saida.strip()[-1500:])
        return codigo

    autorizadas = sorted(v.strip() for v in args.versoes.split(',') if v.strip())
    if so_no_remoto:
        raise SystemExit('Historico remoto diverge do repositorio: nada aplicado.')
    if autorizadas != pendentes:
        raise SystemExit(f'Versoes autorizadas {autorizadas} != pendentes {pendentes}: nada aplicado.')
    codigo, saida = _cli(url, 'db', 'push')
    print(saida.strip()[-1500:])
    depois = _versoes_remotas(url)
    faltando = [v for v in autorizadas if v not in depois]
    print('Aplicadas agora:', [v for v in autorizadas if v in depois], '| faltando:', faltando or 'nenhuma')
    return 0 if codigo == 0 and not faltando else 1


if __name__ == '__main__':
    sys.exit(main())
