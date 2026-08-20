"""
DEPLOY-HOST-1: smoke test minimo contra uma URL de staging publicada
(ex.: Render). Nao testa login com senha real por padrao -- so os
comportamentos de seguranca que nao dependem de credencial (healthcheck,
redirect de pagina protegida, 401 de API).

Uso:
    set BASE_URL=https://controle-financeiro-staging.onrender.com
    venv\\Scripts\\python.exe scripts\\smoke_staging.py

Login real (opcional, so roda se ambas as env vars locais nao
versionadas estiverem definidas -- nunca imprime a senha):
    set BASE_URL=https://...
    set SMOKE_ADMIN_EMAIL=seu@email.com
    set SMOKE_ADMIN_SENHA=...
    venv\\Scripts\\python.exe scripts\\smoke_staging.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from urllib.parse import urlencode


class _SemRedirect(urllib.request.HTTPRedirectHandler):
    """Impede seguir redirects automaticamente, para inspecionar status/Location."""

    def redirect_request(self, *args, **kwargs):
        return None


def _cliente_com_cookies():
    jar = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), _SemRedirect())


def _get(opener, url, timeout=15):
    req = urllib.request.Request(url, method='GET')
    try:
        resp = opener.open(req, timeout=timeout)
        return resp.getcode(), resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def _post_form(opener, url, dados, timeout=15):
    body = urlencode(dados).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        resp = opener.open(req, timeout=timeout)
        return resp.getcode(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)


def main():
    base_url = os.environ.get('BASE_URL', '').rstrip('/')
    if not base_url:
        print('BASE_URL nao definida.')
        sys.exit(1)

    resultados = []

    def registrar(nome, ok, detalhe=''):
        resultados.append((nome, ok))
        print(f'{"OK" if ok else "FALHOU"}: {nome} {detalhe}'.strip())

    opener = _cliente_com_cookies()

    # 1. GET /health
    status, body, _ = _get(opener, f'{base_url}/health')
    ok_health = False
    try:
        payload = json.loads(body)
        ok_health = status == 200 and payload.get('database_connected') is True
        registrar('GET /health', ok_health, json.dumps(payload))
    except Exception:
        registrar('GET /health', False, f'status={status}, corpo nao-JSON')

    if not ok_health:
        print('\nHealthcheck falhou -- interrompendo antes de seguir para os demais testes.')
        sys.exit(1)

    # 2. Pagina protegida sem sessao -> redirect para /login
    status, _, headers = _get(opener, f'{base_url}/despesas')
    location = headers.get('Location', '')
    registrar(
        'GET /despesas sem sessao -> redirect /login',
        status in (301, 302, 303, 307, 308) and '/login' in location,
        f'status={status} location={location}',
    )

    # 3. API sem sessao -> 401 JSON
    status, body, headers = _get(opener, f'{base_url}/api/despesas/')
    content_type = headers.get('Content-Type', '')
    ok_401 = status == 401 and 'application/json' in content_type
    registrar('GET /api/despesas/ sem sessao -> 401 JSON', ok_401, f'status={status} content-type={content_type}')

    # 4. GET /login -> 200
    status, _, _ = _get(opener, f'{base_url}/login')
    registrar('GET /login', status == 200, f'status={status}')

    # 5. Login opcional (so roda se credenciais locais estiverem definidas)
    email = os.environ.get('SMOKE_ADMIN_EMAIL')
    senha = os.environ.get('SMOKE_ADMIN_SENHA')
    if email and senha:
        status, headers_login = _post_form(opener, f'{base_url}/login', {'email': email, 'senha': senha})
        location_login = headers_login.get('Location', '')
        login_ok = status == 302 and '/login' not in location_login
        registrar('POST /login com credenciais', login_ok, f'status={status} location={location_login}')
    else:
        print('SKIP: login com credenciais (SMOKE_ADMIN_EMAIL/SMOKE_ADMIN_SENHA nao definidos)')

    print('\n=== RESUMO ===')
    for nome, ok in resultados:
        print(f'[{"OK" if ok else "FALHOU"}] {nome}')

    falhas = [n for n, ok in resultados if not ok]
    sys.exit(1 if falhas else 0)


if __name__ == '__main__':
    main()
