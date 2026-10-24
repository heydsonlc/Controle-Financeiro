"""
CF-SUPABASE-REFACTOR-1 — ambiente E2E isolado e execucao do Playwright.

Sobe, so em 127.0.0.1 e com dados ficticios:
  1. cluster PostgreSQL descartavel com a migration real e RLS (tests/supabase_local.py);
  2. PostgREST (mesma camada REST do Supabase) com o mesmo segredo JWT;
  3. um servidor que entrega web/dist com os cabecalhos reais de _headers (CSP),
     faz proxy de /rest/v1 para o PostgREST e substitui os endpoints do Supabase Auth
     usados pelo supabase-js (/auth/v1/token, /auth/v1/user, /auth/v1/logout),
     emitindo JWTs reais. Esse substituto e a unica parte simulada.
  4. gancho so de teste POST /__e2e__/consolidar (FIN-CARTOES-FECHAMENTO-1): consolida, como o Flask, uma
     fatura de cartao do Perfil B neste banco descartavel (o novo aplicativo nao consolida faturas).
     Os specs que o usam sao pulados fora deste ambiente (CF_E2E_LOCAL).
Depois roda `playwright test` e derruba tudo, mesmo em caso de falha.

Uso (da raiz do repositorio):
  set POSTGREST_BIN=C:\\caminho\\postgrest.exe
  venv\\Scripts\\python.exe web\\tests\\e2e\\run_e2e.py            # roda os testes
  venv\\Scripts\\python.exe web\\tests\\e2e\\run_e2e.py --servir   # so sobe o ambiente
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
WEB = RAIZ / 'web'
sys.path.insert(0, str(RAIZ))

from tests.supabase_local import (  # noqa: E402
    PERFIS,
    USUARIO_A,
    USUARIO_B,
    ClusterLocal,
    PostgrestLocal,
    assinar_jwt,
    claims_usuario,
    encontrar_pg_bin,
    encontrar_postgrest,
    porta_livre,
    semear_cartoes_e2e,
    semear_receitas_e2e,
    semear_recorrencia_e2e,
)

CHAVE_PUBLICAVEL = 'sb_publishable_harness_local_somente_teste'
# Senhas ficticias, exclusivas deste ambiente descartavel.
CONTAS = {
    USUARIO_A['email']: {**USUARIO_A, 'senha': 'Senha-ficticia-A-2026'},
    USUARIO_B['email']: {**USUARIO_B, 'senha': 'Senha-ficticia-B-2026'},
}
HOP_BY_HOP = {'connection', 'keep-alive', 'transfer-encoding', 'content-length', 'server', 'date'}


def ler_headers(dist):
    """Cabecalhos de _headers (formato Cloudflare Pages, so o bloco '/*')."""
    cabecalhos = {}
    arquivo = dist / '_headers'
    if arquivo.exists():
        for linha in arquivo.read_text(encoding='utf-8').splitlines():
            if linha.startswith('  ') and ':' in linha:
                nome, valor = linha.strip().split(':', 1)
                cabecalhos[nome.strip()] = valor.strip()
    return cabecalhos


def verificar_jwt(token, segredo):
    try:
        cabecalho, corpo, assinatura = token.split('.')
        esperado = hmac.new(segredo.encode(), f'{cabecalho}.{corpo}'.encode(), hashlib.sha256).digest()
        recebido = base64.urlsafe_b64decode(assinatura + '=' * (-len(assinatura) % 4))
        if not hmac.compare_digest(esperado, recebido):
            return None
        claims = json.loads(base64.urlsafe_b64decode(corpo + '=' * (-len(corpo) % 4)))
        return claims if claims.get('exp', 0) > time.time() else None
    except (ValueError, json.JSONDecodeError):
        return None


def criar_handler(dist, postgrest_url, segredo, headers_seguranca, consolidar=None):
    refresh_tokens = {}
    trava = threading.Lock()

    def usuario_publico(conta):
        return {'id': conta['id'], 'aud': 'authenticated', 'role': 'authenticated', 'email': conta['email'],
                'app_metadata': {'provider': 'email', 'providers': ['email']}, 'user_metadata': {},
                'created_at': '2026-10-20T00:00:00Z'}

    def sessao(conta):
        claims = claims_usuario(conta)
        refresh = secrets.token_urlsafe(24)
        with trava:
            refresh_tokens[refresh] = conta
        return {'access_token': assinar_jwt(claims, segredo), 'token_type': 'bearer', 'expires_in': 3600,
                'expires_at': claims['exp'], 'refresh_token': refresh, 'user': usuario_publico(conta)}

    class Handler(SimpleHTTPRequestHandler):
        # MIME fixo: o registro do Windows pode mapear .js para text/plain, e com
        # nosniff o navegador recusaria os modulos (o Cloudflare Pages serve certo).
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript',
                          '.mjs': 'text/javascript', '.css': 'text/css', '.html': 'text/html'}
        # HTTP/1.1 com keep-alive: no HTTP/1.0 cada resposta fecha o socket, e no
        # Windows isso gerava ERR_CONNECTION_RESET em arquivos maiores (supabase.js).
        protocol_version = 'HTTP/1.1'

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(dist), **kwargs)

        def log_message(self, *args):
            pass

        def end_headers(self):
            if not self.path.startswith(('/auth/', '/rest/')):
                for nome, valor in headers_seguranca.items():
                    self.send_header(nome, valor)
            super().end_headers()

        def _json(self, status, corpo):
            dados = json.dumps(corpo).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def _corpo(self):
            return self._dados

        def _estatico(self):
            """Arquivo de dist/ lido inteiro e escrito de uma vez (robusto no Windows)."""
            caminho = Path(self.translate_path(self.path))
            if caminho.is_dir():
                caminho = caminho / 'index.html'
            try:
                caminho.resolve().relative_to(dist.resolve())
                dados = caminho.read_bytes()
            except (ValueError, OSError):
                return self._json(404, {'msg': 'nao encontrado'})
            self.send_response(200)
            self.send_header('Content-Type', self.guess_type(str(caminho)))
            self.send_header('Content-Length', str(len(dados)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(dados)

        def _apikey_ok(self):
            # O gateway do Supabase recusa requisicoes sem a chave do projeto.
            if self.headers.get('apikey') != CHAVE_PUBLICAVEL:
                self._json(401, {'message': 'No API key found in request'})
                return False
            return True

        # ---- Auth (substituto local do Supabase Auth) ----
        def _auth(self, metodo):
            if not self._apikey_ok():
                return
            rota, _, query = self.path.partition('?')
            if metodo == 'POST' and rota == '/auth/v1/token':
                dados = json.loads(self._corpo() or b'{}')
                if 'grant_type=password' in query:
                    conta = CONTAS.get(str(dados.get('email', '')).lower())
                    if not conta or not hmac.compare_digest(conta['senha'], str(dados.get('password', ''))):
                        return self._json(400, {'code': 400, 'error_code': 'invalid_credentials',
                                                'msg': 'Invalid login credentials'})
                    return self._json(200, sessao(conta))
                if 'grant_type=refresh_token' in query:
                    with trava:
                        conta = refresh_tokens.pop(str(dados.get('refresh_token', '')), None)
                    if not conta:
                        return self._json(400, {'code': 400, 'error_code': 'refresh_token_not_found',
                                                'msg': 'Invalid Refresh Token: Refresh Token Not Found'})
                    return self._json(200, sessao(conta))
            if metodo == 'GET' and rota == '/auth/v1/user':
                token = (self.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
                claims = verificar_jwt(token, segredo)
                conta = next((c for c in CONTAS.values() if claims and c['id'] == claims.get('sub')), None)
                if not conta:
                    return self._json(403, {'code': 403, 'error_code': 'bad_jwt',
                                            'msg': 'invalid JWT: unable to parse or verify signature'})
                return self._json(200, usuario_publico(conta))
            if metodo == 'POST' and rota == '/auth/v1/logout':
                self.send_response(204)
                self.end_headers()
                return
            self._json(404, {'msg': 'rota de auth nao simulada'})

        # ---- REST: proxy para o PostgREST real ----
        def _rest(self, metodo):
            if not self._apikey_ok():
                return
            destino = postgrest_url + self.path[len('/rest/v1'):]
            corpo = self._corpo() if metodo in ('POST', 'PATCH', 'PUT', 'DELETE') else None
            req = urllib.request.Request(destino, method=metodo, data=corpo)
            for nome in ('Authorization', 'Accept', 'Accept-Profile', 'Content-Profile', 'Content-Type',
                         'Prefer', 'Range'):
                if self.headers.get(nome):
                    req.add_header(nome, self.headers[nome])
            try:
                resposta = urllib.request.urlopen(req, timeout=15)
            except urllib.error.HTTPError as erro:
                resposta = erro
            dados = resposta.read()
            self.send_response(resposta.status if hasattr(resposta, 'status') else resposta.code)
            for nome, valor in resposta.headers.items():
                if nome.lower() not in HOP_BY_HOP:
                    self.send_header(nome, valor)
            self.send_header('Content-Length', str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        # ---- Gancho so de teste: consolida uma fatura do Perfil B (o novo aplicativo nao consolida) ----
        def _consolidar(self):
            try:
                pedido = json.loads(self._dados or b'{}')
                self._json(200, consolidar(str(pedido['cartao']), str(pedido['competencia'])))
            except (KeyError, ValueError) as exc:
                self._json(400, {'msg': str(exc)})

        def _despachar(self, metodo):
            # Le o corpo inteiro ANTES de responder: com keep-alive, bytes nao lidos
            # contaminariam a proxima requisicao da mesma conexao.
            tamanho = int(self.headers.get('Content-Length') or 0)
            self._dados = self.rfile.read(tamanho) if tamanho else b''
            if self.path.startswith('/auth/v1/'):
                return self._auth(metodo)
            if self.path.startswith('/rest/v1/'):
                return self._rest(metodo)
            if metodo == 'POST' and self.path == '/__e2e__/consolidar' and consolidar:
                return self._consolidar()
            if metodo == 'GET':
                return self._estatico()
            self._json(405, {'msg': 'metodo nao permitido'})

        def do_GET(self):
            self._despachar('GET')

        def do_POST(self):
            self._despachar('POST')

        def do_PATCH(self):
            self._despachar('PATCH')

        def do_DELETE(self):
            self._despachar('DELETE')

    return Handler


def construir_dist(origem):
    node = shutil.which('node') or 'node'
    env = {**os.environ, 'SUPABASE_URL': origem, 'SUPABASE_PUBLISHABLE_KEY': CHAVE_PUBLICAVEL}
    subprocess.run([node, 'scripts/build.mjs', '--local'], cwd=WEB, env=env, check=True)
    return WEB / 'dist'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--servir', action='store_true', help='so sobe o ambiente (Ctrl+C para sair)')
    args, extras = parser.parse_known_args()

    pg_bin, postgrest_bin = encontrar_pg_bin(), encontrar_postgrest()
    if not pg_bin or not postgrest_bin:
        print('E2E_SKIP: precisa dos binarios do PostgreSQL e de POSTGREST_BIN.')
        return 0

    porta = porta_livre()
    origem = f'http://127.0.0.1:{porta}'
    segredo = secrets.token_urlsafe(48)
    dist = construir_dist(origem)

    with tempfile.TemporaryDirectory(prefix='cf-e2e-') as tmp:
        with ClusterLocal(pg_bin, tmp) as cluster:
            cluster.preparar()
            conn = cluster.conectar()
            with conn.cursor() as cur:
                semear_recorrencia_e2e(cur)  # FIN-RECORRENCIA-1 (recorrencia.spec.mjs)
                semear_receitas_e2e(cur)  # FIN-RECEITAS-1 (receitas.spec.mjs)
                semear_cartoes_e2e(cur)  # FIN-CARTOES-1 (cartoes.spec.mjs)
            conn.close()

            def consolidar(cartao, competencia):
                """Como a consolidacao do Flask: FECHADA com valor_consolidado = executado (so Perfil B, ficticio)."""
                if not re.fullmatch(r'\d{4}-\d{2}-01', competencia):
                    raise ValueError('competencia deve ser AAAA-MM-01')
                conn = cluster.conectar()
                try:
                    with conn.cursor() as cur:
                        cur.execute("update public.conta c set status_fatura = 'FECHADA', "
                                    "valor_consolidado = c.valor_executado, data_consolidacao = now() "
                                    "from public.item_despesa i where c.item_despesa_id = i.id and c.is_fatura_cartao "
                                    "and i.nome = %s and i.perfil_financeiro_id = %s and c.cartao_competencia = %s "
                                    "returning c.id, c.valor_consolidado",
                                    (cartao, PERFIS['PERFIL_B']['id'], competencia))
                        linha = cur.fetchone()
                finally:
                    conn.close()
                if not linha:
                    raise ValueError('fatura nao encontrada')
                return {'fatura_id': linha[0], 'valor_consolidado': str(linha[1])}

            with PostgrestLocal(postgrest_bin, cluster, segredo, tmp) as postgrest:
                handler = criar_handler(dist, postgrest.url, segredo, ler_headers(dist), consolidar)
                # Fila de conexoes maior que o padrao (5): o Chrome abre ~6 em paralelo.
                ThreadingHTTPServer.request_queue_size = 64
                ThreadingHTTPServer.daemon_threads = True
                servidor = ThreadingHTTPServer(('127.0.0.1', porta), handler)
                threading.Thread(target=servidor.serve_forever, daemon=True).start()
                print(f'E2E_PRONTO {origem}', flush=True)
                try:
                    if args.servir:
                        while True:
                            time.sleep(1)
                    npx = shutil.which('npx') or 'npx'
                    env = {**os.environ, 'CF_WEB_BASE_URL': origem, 'CF_E2E_LOCAL': '1',
                           'CF_SENHA_A': CONTAS[USUARIO_A['email']]['senha'],
                           'CF_SENHA_B': CONTAS[USUARIO_B['email']]['senha']}
                    return subprocess.run([npx, 'playwright', 'test', '-c', 'playwright.config.mjs', *extras],
                                          cwd=WEB, env=env).returncode
                except KeyboardInterrupt:
                    return 0
                finally:
                    servidor.shutdown()


if __name__ == '__main__':
    sys.exit(main())
