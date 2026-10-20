"""
SEC-SUPABASE-PUBLIC-1 — verifica, pela Data API, o que o papel anonimo alcanca.

Projeto: o do Controle Financeiro, lido do .env.staging local (fora do Git).
Recusa o da Calculadora Judicial.

Usa SOMENTE a chave publica (publishable ou anon legada), que e exatamente o
que um terceiro teria. Ela vem de SUPABASE_PUBLISHABLE_KEY ou, com --via-cli,
da Supabase CLI ja autenticada; nesse caso as chaves privilegiadas sao
descartadas em memoria. Nenhuma chave e impressa.

Sondagens sem efeito sobre dados:
- lista de schemas expostos (erro proposital de Accept-Profile);
- quantidade de rotas do OpenAPI por schema;
- leitura com limit=0 (nao retorna linhas);
- escrita com filtro impossivel (id=eq.-1: zero linhas afetadas, se aceita).

Uso:
    venv\\Scripts\\python.exe scripts\\verificar_exposicao_supabase.py --via-cli
Saida: relatorio + exit 0 se `public` estiver bloqueado para anon, 1 caso contrario.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJETOS_PROIBIDOS = {'dshqjhyymtpxpxuntzbz'}  # Calculadora Judicial / Portal Kortex


def _projeto_do_ambiente():
    """Ref do projeto do Controle Financeiro, lido do .env.staging local (fora do Git).

    O usuario do Session pooler e `postgres.<ref>`; assim o ref nunca fica no repositorio.
    """
    from urllib.parse import urlsplit
    from dotenv import dotenv_values
    url = dotenv_values(os.path.join(ROOT, '.env.staging'), encoding='utf-8-sig').get('DATABASE_URL') or ''
    usuario = urlsplit(url).username or ''
    if not usuario.startswith('postgres.'):
        raise SystemExit('Nao foi possivel obter o projeto do .env.staging (esperado usuario postgres.<ref>).')
    return usuario.split('.', 1)[1]


PROJETO = os.getenv('CF_SUPABASE_PROJECT_REF') or _projeto_do_ambiente()
BASE = f'https://{PROJETO}.supabase.co/rest/v1'
TABELAS_REPRESENTATIVAS = ['usuario', 'config_agregador', 'conta_bancaria', 'categoria', 'alembic_version']


def chave_publica_via_cli():
    cli = shutil.which('supabase')
    if not cli:
        raise SystemExit('Supabase CLI nao encontrada.')
    saida = subprocess.run([cli, 'projects', 'api-keys', '--project-ref', PROJETO, '-o', 'json'],
                           capture_output=True, text=True, timeout=60)
    if saida.returncode != 0:
        raise SystemExit('Falha ao consultar a CLI (sem detalhes, para nao expor saida).')
    chaves = json.loads(saida.stdout)
    publicas = [c for c in chaves if str(c.get('type', '')).lower() == 'publishable'
                or str(c.get('name', '')).lower() == 'anon']
    del chaves, saida  # descarta chaves privilegiadas
    publicas.sort(key=lambda c: 0 if str(c.get('type', '')).lower() == 'publishable' else 1)
    if not publicas or not publicas[0].get('api_key'):
        raise SystemExit('Nenhuma chave publica encontrada.')
    return publicas[0]['api_key'], publicas[0].get('type') or publicas[0].get('name')


def requisicao(chave, metodo, caminho, perfil='public', corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(BASE + caminho, method=metodo, data=dados)
    req.add_header('apikey', chave)
    req.add_header('Accept-Profile' if metodo == 'GET' else 'Content-Profile', perfil)
    req.add_header('Prefer', 'return=minimal')
    if dados is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def mensagem(corpo):
    try:
        dados = json.loads(corpo or b'{}')
        if isinstance(dados, dict):
            return f"{dados.get('code', '')} {dados.get('message', '')} {dados.get('hint') or ''}".strip()[:220]
        return f'{len(dados)} linha(s)'
    except json.JSONDecodeError:
        return '(corpo nao JSON)'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--via-cli', action='store_true')
    parser.add_argument('--com-escrita', action='store_true',
                        help='inclui PATCH/DELETE com filtro impossivel (id=eq.-1)')
    args = parser.parse_args()

    if PROJETO in PROJETOS_PROIBIDOS:
        raise SystemExit('Projeto proibido.')
    if args.via_cli:
        chave, tipo = chave_publica_via_cli()
    else:
        chave, tipo = os.getenv('SUPABASE_PUBLISHABLE_KEY', ''), 'env'
        if not chave or chave.startswith('sb_secret_'):
            raise SystemExit('Defina SUPABASE_PUBLISHABLE_KEY (chave publica) ou use --via-cli.')

    print(f'Projeto: {PROJETO[:6]}… | chave usada: publica ({tipo}), nao impressa')

    # A raiz (OpenAPI) exige chave secreta; o erro de schema numa rota de tabela
    # (PGRST106) devolve a lista de schemas expostos sem tocar em dados.
    status, corpo = requisicao(chave, 'GET', '/alembic_version?limit=0', perfil='schema_inexistente_sondagem')
    print(f'Schemas expostos (resposta da API): HTTP {status} {mensagem(corpo)}')

    exposto = False

    for tabela in TABELAS_REPRESENTATIVAS:
        status, corpo = requisicao(chave, 'GET', f'/{tabela}?select=*&limit=0')
        acessivel = status == 200
        exposto |= acessivel
        print(f'GET  public.{tabela:<16} limit=0 -> HTTP {status} {"ACESSIVEL" if acessivel else "bloqueado"} | {mensagem(corpo)}')

    if args.com_escrita:
        for tabela in ('usuario', 'categoria'):
            for metodo, corpo_req in (('PATCH', {'id': -1}), ('DELETE', None)):
                status, corpo = requisicao(chave, metodo, f'/{tabela}?id=eq.-1', corpo=corpo_req)
                aceita = status in (200, 204)
                exposto |= aceita
                print(f'{metodo:<6} public.{tabela:<16} id=eq.-1 -> HTTP {status} {"ACEITA" if aceita else "bloqueada"} | {mensagem(corpo)}')

    print('RESULTADO:', 'EXPOSTO' if exposto else 'public BLOQUEADO para anonimo')
    return 1 if exposto else 0


if __name__ == '__main__':
    sys.exit(main())
