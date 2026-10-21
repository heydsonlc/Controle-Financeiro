"""
AUTH-REAL-1 — mesmos testes E2E do MVP contra o Supabase REAL do Controle Financeiro.

Diferente de run_e2e.py, nada e simulado: Supabase Auth, Data API e banco sao os
do projeto (nunca o da Calculadora Judicial). Localmente so ha um servidor
estatico em 127.0.0.1 entregando web/dist com a CSP real do _headers.

Recusa rodar se (verificacoes somente leitura):
- o cadastro publico do Auth estiver ligado (disable_signup precisa ser true);
- a Data API nao expuser `financeiro` ou ainda expuser `public`;
- a migration PERFIS-1 nao estiver aplicada (funcoes de perfil ausentes);
- faltarem as contas de teste no ambiente.

Contas de teste (ficticias, criadas pelo usuario no painel do Supabase), por ambiente ou
no arquivo local .env.e2e-real (fora do Git):
    CF_EMAIL_A, CF_SENHA_A, CF_EMAIL_B, CF_SENHA_B
Dados ficticios: scripts/supabase_mvp_seed_teste.py.

Uso (da raiz do repositorio):
    venv\\Scripts\\python.exe web\\tests\\e2e\\run_e2e_real.py
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
WEB = RAIZ / 'web'
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_e2e import criar_handler, ler_headers  # noqa: E402
from tests.supabase_local import porta_livre  # noqa: E402
from verificar_exposicao_supabase import PROJETO, PROJETOS_PROIBIDOS, chave_publica_via_cli  # noqa: E402

CONTAS = ('CF_EMAIL_A', 'CF_SENHA_A', 'CF_EMAIL_B', 'CF_SENHA_B')


def _get(url, chave, perfil=None):
    req = urllib.request.Request(url)
    req.add_header('apikey', chave)
    if perfil:
        req.add_header('Accept-Profile', perfil)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b'null')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'null')


def verificar_pre_requisitos(origem, chave):
    problemas = []
    _, config = _get(f'{origem}/auth/v1/settings', chave)
    if not (isinstance(config, dict) and config.get('disable_signup') is True):
        problemas.append('cadastro publico do Supabase Auth esta LIGADO (desligue "Allow new users to sign up")')

    _, erro = _get(f'{origem}/rest/v1/categorias?limit=0', chave, perfil='schema_inexistente_sondagem')
    # A lista de schemas expostos vem no `hint` (PGRST106), as vezes na `message`.
    mensagem = ' '.join(str(erro.get(k) or '') for k in ('message', 'hint')) if isinstance(erro, dict) else ''
    expostos = mensagem.split('exposed:')[-1].replace(' ', '').split(',') if 'exposed:' in mensagem else []
    if 'financeiro' not in expostos:
        problemas.append(f'schema financeiro nao esta exposto na Data API (expostos: {expostos or "?"})')
    if 'public' in expostos:
        problemas.append('schema public voltou a ser exposto na Data API')

    # As funcoes de cada etapa precisam existir no projeto (404 PGRST202 = migration nao aplicada).
    for funcao, corpo, migration in (
        ('meus_perfis', b'{}', 'PERFIS-1 (20261021090000_financeiro_perfis_acesso)'),
        ('contas_do_mes', b'{"p_perfil_id": 0, "p_mes": "2026-01-01"}', 'MOBILE-CONTAS-1 (20261022090000_financeiro_contas_do_mes)'),
    ):
        req = urllib.request.Request(f'{origem}/rest/v1/rpc/{funcao}', method='POST', data=corpo)
        for nome, valor in (('apikey', chave), ('Content-Type', 'application/json'), ('Content-Profile', 'financeiro')):
            req.add_header(nome, valor)
        try:
            status_rpc = urllib.request.urlopen(req, timeout=20).status
        except urllib.error.HTTPError as exc:
            status_rpc = exc.code
        if status_rpc == 404:
            problemas.append(f'migration {migration} nao aplicada no projeto')

    faltando = [nome for nome in CONTAS if not os.getenv(nome)]
    if faltando:
        problemas.append(f'variaveis de ambiente ausentes: {", ".join(faltando)}')
    return problemas


def main():
    if PROJETO in PROJETOS_PROIBIDOS:
        raise SystemExit('Projeto proibido.')
    origem = f'https://{PROJETO}.supabase.co'
    # Contas de teste: variaveis de ambiente ou o arquivo local .env.e2e-real
    # (ignorado pelo Git pela regra .env.*). Nunca no codigo nem no chat.
    from dotenv import load_dotenv
    load_dotenv(RAIZ / '.env.e2e-real', override=False, encoding='utf-8-sig')
    chave, _ = chave_publica_via_cli()

    problemas = verificar_pre_requisitos(origem, chave)
    if problemas:
        print('E2E_REAL_BLOQUEADO:')
        for item in problemas:
            print('  -', item)
        return 2

    node = shutil.which('node') or 'node'
    env_build = {**os.environ, 'SUPABASE_URL': origem, 'SUPABASE_PUBLISHABLE_KEY': chave}
    subprocess.run([node, 'scripts/build.mjs'], cwd=WEB, env=env_build, check=True)
    dist = WEB / 'dist'

    porta = porta_livre()
    base = f'http://127.0.0.1:{porta}'
    ThreadingHTTPServer.request_queue_size = 64
    ThreadingHTTPServer.daemon_threads = True
    # Mesmo servidor estatico do ambiente isolado; aqui os endpoints /auth e /rest
    # nao sao usados, porque o config.js aponta direto para o projeto real.
    servidor = ThreadingHTTPServer(('127.0.0.1', porta), criar_handler(dist, None, None, ler_headers(dist)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    print(f'E2E_REAL_PRONTO {base} -> {PROJETO[:6]}…', flush=True)
    try:
        npx = shutil.which('npx') or 'npx'
        env = {**os.environ, 'CF_WEB_BASE_URL': base}
        return subprocess.run([npx, 'playwright', 'test', '-c', 'playwright.config.mjs', *sys.argv[1:]],
                              cwd=WEB, env=env).returncode
    finally:
        servidor.shutdown()


if __name__ == '__main__':
    sys.exit(main())
