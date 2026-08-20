"""
Testes SEG-1 — Autenticacao global das rotas e APIs.

Usa create_app('testing') (app real, com todos os blueprints e o
before_request de protecao) em vez do padrao de app isolado por blueprint
usado no restante da suite, porque o gate de autenticacao vive em
create_app()/app.py, nao em blueprints individuais.

Cobertura:
- GET /despesas sem sessao -> redirect para /login?next=/despesas
- GET /api/despesas sem sessao -> 401 JSON (nunca HTML)
- GET /static/... sem sessao -> permitido
- GET /health sem sessao -> permitido
- GET /login sem sessao -> permitido (pagina publica)
- POST /login com credenciais corretas -> cria sessao e redireciona
- POST /login com senha errada -> 401, mensagem generica, sem sessao
- POST /login com e-mail inexistente -> mesma mensagem generica (nao revela)
- POST /login de usuario inativo -> bloqueado com a mesma mensagem generica
- POST /logout -> encerra a sessao (acesso subsequente volta a exigir login)
- Apos login, acesso a pagina e a API funciona normalmente
- password_hash nunca aparece em to_dict()/JSON
"""
from datetime import datetime

import pytest

from backend.app import create_app
from backend.models import Usuario, db


@pytest.fixture()
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def usuario_ativo(app):
    with app.app_context():
        usuario = Usuario(email='teste@exemplo.com', nome='Teste', ativo=True)
        usuario.definir_senha('senha-forte-123')
        db.session.add(usuario)
        db.session.commit()
        return usuario.id


@pytest.fixture()
def usuario_inativo(app):
    with app.app_context():
        usuario = Usuario(email='inativo@exemplo.com', nome='Inativo', ativo=False)
        usuario.definir_senha('senha-forte-123')
        db.session.add(usuario)
        db.session.commit()
        return usuario.id


def _login(client, email, senha, next_path=None):
    url = '/login' + (f'?next={next_path}' if next_path else '')
    return client.post(url, data={'email': email, 'senha': senha})


def test_get_despesas_sem_sessao_redireciona_para_login(app):
    with app.test_client() as c:
        r = c.get('/despesas')
        assert r.status_code == 302
        assert r.headers['Location'] == '/login?next=/despesas'


def test_get_api_despesas_sem_sessao_retorna_401_json(app):
    with app.test_client() as c:
        r = c.get('/api/despesas')
        assert r.status_code == 401
        assert r.content_type.startswith('application/json')
        payload = r.get_json()
        assert payload['success'] is False


def test_static_sem_sessao_e_permitido(app):
    with app.test_client() as c:
        r = c.get('/static/css/style.css')
        assert r.status_code == 200


def test_health_sem_sessao_e_permitido(app):
    with app.test_client() as c:
        r = c.get('/health')
        assert r.status_code == 200


def test_get_login_sem_sessao_e_permitido(app):
    with app.test_client() as c:
        r = c.get('/login')
        assert r.status_code == 200


def test_post_login_com_senha_correta_cria_sessao(app, usuario_ativo):
    with app.test_client() as c:
        r = _login(c, 'teste@exemplo.com', 'senha-forte-123')
        assert r.status_code == 302
        assert r.headers['Location'] == '/'


def test_rota_protegida_com_sessao_valida_retorna_200(app, usuario_ativo):
    with app.test_client() as c:
        _login(c, 'teste@exemplo.com', 'senha-forte-123')

        r = c.get('/despesas')
        assert r.status_code == 200

        r_api = c.get('/api/despesas/')
        assert r_api.status_code == 200


def test_post_login_respeita_next(app, usuario_ativo):
    with app.test_client() as c:
        r = _login(c, 'teste@exemplo.com', 'senha-forte-123', next_path='/receitas')
        assert r.status_code == 302
        assert r.headers['Location'] == '/receitas'


def test_post_login_com_senha_errada_retorna_401_e_nao_cria_sessao(app, usuario_ativo):
    with app.test_client() as c:
        r = _login(c, 'teste@exemplo.com', 'senha-errada')
        assert r.status_code == 401

        r2 = c.get('/despesas')
        assert r2.status_code == 302


def test_post_login_com_email_inexistente_retorna_mensagem_generica(app, usuario_ativo):
    with app.test_client() as c:
        r_email_errado = _login(c, 'naoexiste@exemplo.com', 'qualquer-coisa')
        r_senha_errada = _login(c, 'teste@exemplo.com', 'senha-errada')

        assert r_email_errado.status_code == r_senha_errada.status_code == 401
        assert r_email_errado.data == r_senha_errada.data


def test_post_login_usuario_inativo_e_bloqueado(app, usuario_inativo):
    with app.test_client() as c:
        r = _login(c, 'inativo@exemplo.com', 'senha-forte-123')
        assert r.status_code == 401

        r2 = c.get('/despesas')
        assert r2.status_code == 302


def test_post_logout_encerra_sessao(app, usuario_ativo):
    with app.test_client() as c:
        _login(c, 'teste@exemplo.com', 'senha-forte-123')
        assert c.get('/despesas').status_code == 200

        r = c.post('/logout')
        assert r.status_code == 302
        assert r.headers['Location'] == '/login'

        assert c.get('/despesas').status_code == 302


def test_login_ja_autenticado_redireciona_para_index(app, usuario_ativo):
    with app.test_client() as c:
        _login(c, 'teste@exemplo.com', 'senha-forte-123')
        r = c.get('/login')
        assert r.status_code == 302
        assert r.headers['Location'] == '/'


def test_usuario_to_dict_nunca_expoe_password_hash():
    usuario = Usuario(email='x@x.com', nome='X', ativo=True)
    usuario.definir_senha('qualquer-coisa')
    dados = usuario.to_dict()
    assert 'password_hash' not in dados
    assert 'senha' not in dados


def test_login_com_json_retorna_payload_json(app, usuario_ativo):
    with app.test_client() as c:
        r = c.post('/login', json={'email': 'teste@exemplo.com', 'senha': 'senha-forte-123'})
        assert r.status_code == 200
        payload = r.get_json()
        assert payload['success'] is True
        assert payload['data']['redirect'] == '/'


def test_login_com_json_credenciais_erradas_retorna_401_json(app, usuario_ativo):
    with app.test_client() as c:
        r = c.post('/login', json={'email': 'teste@exemplo.com', 'senha': 'errada'})
        assert r.status_code == 401
        assert r.content_type.startswith('application/json')
        payload = r.get_json()
        assert payload['success'] is False
