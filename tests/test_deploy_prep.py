"""
Testes DEPLOY-PREP-1 — validacao de ambiente para deploy seguro.

Cobre:
- config local permite desenvolvimento (SECRET_KEY default, sem DATABASE_URL)
- staging/production bloqueiam SECRET_KEY fraca (ausente, curta, valor
  conhecido, com marcador de exemplo/dev/teste)
- staging/production exigem DATABASE_URL
- .env.example nao contem segredo real
- validar_cvv_master_password bloqueia senha fraca/ausente quando o
  recurso esta habilitado, e nao interfere quando nao ha CVV cadastrado
- SESSION_COOKIE_SECURE=True em staging/production, False em local
- SESSION_COOKIE_HTTPONLY=True em todos os ambientes
- /health nao exige login e nao expoe segredos
"""
import os

import pytest

from backend.app import create_app
from backend.config import (
    get_config,
    normalizar_nome_ambiente,
    resolver_app_env,
    validar_cvv_master_password,
    validar_secret_key,
)
from backend.models import db


# ---------------------------------------------------------------------------
# validar_secret_key
# ---------------------------------------------------------------------------

def test_secret_key_qualquer_valor_e_aceito_em_local():
    assert validar_secret_key('', 'local') is None
    assert validar_secret_key('dev-secret-key-local-123456', 'local') is None
    assert validar_secret_key(None, 'local') is None


def test_secret_key_ausente_e_bloqueada_em_production():
    erro = validar_secret_key('', 'production')
    assert erro is not None
    assert 'ausente' in erro.lower()


def test_secret_key_curta_e_bloqueada_em_production():
    chave_curta = 'a' * 20
    erro = validar_secret_key(chave_curta, 'production')
    assert erro is not None


def test_secret_key_valor_padrao_conhecido_e_bloqueado_em_production():
    erro = validar_secret_key('dev-secret-key-local-123456', 'production')
    assert erro is not None


def test_secret_key_com_marcador_fraco_e_bloqueada_em_staging():
    chave_com_marcador = 'esta-e-uma-chave-de-teste-bem-longa-mesmo-assim'
    erro = validar_secret_key(chave_com_marcador, 'staging')
    assert erro is not None


def test_secret_key_forte_e_aceita_em_production():
    chave_forte = 'x7K9mP2qR5vN8wZ3jL6hF1cB4dS0aXyEuT2Mn5pQ8rW'
    assert validar_secret_key(chave_forte, 'production') is None


# ---------------------------------------------------------------------------
# get_config — ambientes e sinonimos
# ---------------------------------------------------------------------------

def test_get_config_local_nao_exige_variaveis(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    cfg = get_config('local')
    assert cfg.__name__ == 'LocalConfig'


def test_get_config_development_e_sinonimo_de_local(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    cfg = get_config('development')
    assert cfg.__name__ == 'LocalConfig'


def test_get_config_production_sem_secret_key_falha(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@remote:5432/db')
    with pytest.raises(RuntimeError):
        get_config('production')


def test_get_config_production_sem_database_url_falha(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'x7K9mP2qR5vN8wZ3jL6hF1cB4dS0aXyEuT2Mn5pQ8rW')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(RuntimeError):
        get_config('production')


def test_get_config_staging_com_variaveis_fortes_funciona(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'x7K9mP2qR5vN8wZ3jL6hF1cB4dS0aXyEuT2Mn5pQ8rW')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@remote:5432/db')
    cfg = get_config('staging')
    assert cfg.__name__ == 'StagingConfig'
    assert cfg.SESSION_COOKIE_SECURE is True


def test_normalizar_nome_ambiente_aceita_sinonimos():
    assert normalizar_nome_ambiente('development') == 'local'
    assert normalizar_nome_ambiente('dev') == 'local'
    assert normalizar_nome_ambiente('production') == 'production'
    assert normalizar_nome_ambiente('') == ''


def test_resolver_app_env_prioriza_app_env_sobre_flask_env(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'staging')
    monkeypatch.setenv('FLASK_ENV', 'production')
    assert resolver_app_env() == 'staging'


def test_resolver_app_env_usa_flask_env_como_fallback(monkeypatch):
    monkeypatch.delenv('APP_ENV', raising=False)
    monkeypatch.setenv('FLASK_ENV', 'development')
    assert resolver_app_env() == 'local'


# ---------------------------------------------------------------------------
# Cookies de sessao
# ---------------------------------------------------------------------------

def test_session_cookie_secure_true_em_production(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'x7K9mP2qR5vN8wZ3jL6hF1cB4dS0aXyEuT2Mn5pQ8rW')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@remote:5432/db')
    cfg = get_config('production')
    assert cfg.SESSION_COOKIE_SECURE is True


def test_session_cookie_secure_false_em_local(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    cfg = get_config('local')
    assert cfg.SESSION_COOKIE_SECURE is False


def test_session_cookie_httponly_sempre_true_em_qualquer_ambiente(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    assert get_config('local').SESSION_COOKIE_HTTPONLY is True

    monkeypatch.setenv('SECRET_KEY', 'x7K9mP2qR5vN8wZ3jL6hF1cB4dS0aXyEuT2Mn5pQ8rW')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@remote:5432/db')
    assert get_config('production').SESSION_COOKIE_HTTPONLY is True


# ---------------------------------------------------------------------------
# validar_cvv_master_password
# ---------------------------------------------------------------------------

def test_cvv_senha_nao_exigida_em_local():
    assert validar_cvv_master_password('', 'local', cvv_habilitado=True) is None


def test_cvv_senha_nao_exigida_se_recurso_desabilitado():
    assert validar_cvv_master_password('', 'production', cvv_habilitado=False) is None


def test_cvv_senha_ausente_bloqueada_em_production_com_recurso_habilitado():
    erro = validar_cvv_master_password('', 'production', cvv_habilitado=True)
    assert erro is not None
    assert 'ausente' in erro.lower()


def test_cvv_senha_curta_bloqueada_em_production():
    erro = validar_cvv_master_password('abc123', 'production', cvv_habilitado=True)
    assert erro is not None


def test_cvv_senha_obvia_bloqueada_em_production():
    erro = validar_cvv_master_password('123456', 'production', cvv_habilitado=True)
    assert erro is not None


def test_cvv_senha_forte_aceita_em_production():
    erro = validar_cvv_master_password('uma-senha-bem-forte-e-longa-987', 'production', cvv_habilitado=True)
    assert erro is None


# ---------------------------------------------------------------------------
# .env.example nao contem segredo real
# ---------------------------------------------------------------------------

def test_env_example_nao_contem_segredo_real():
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env.example')
    with open(caminho, encoding='utf-8') as f:
        conteudo = f.read()

    # A senha local real usada neste projeto (nunca deve aparecer aqui).
    assert 'Hlc%40%400913' not in conteudo
    # SECRET_KEY do .env.example deve ser um placeholder, nao uma chave utilizavel.
    for linha in conteudo.splitlines():
        if linha.startswith('SECRET_KEY='):
            valor = linha.split('=', 1)[1].strip()
            assert validar_secret_key(valor, 'production') is not None, (
                'SECRET_KEY de .env.example parece uma chave forte real — deveria ser um placeholder fraco.'
            )


def test_env_example_nao_referencia_senha_de_banco_real():
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env.example')
    with open(caminho, encoding='utf-8') as f:
        conteudo = f.read()

    assert 'controle_financeiro:SUA_SENHA_LOCAL' in conteudo or 'usuario:senha' in conteudo


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@pytest.fixture()
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_healthcheck_nao_exige_login(app):
    with app.test_client() as c:
        r = c.get('/health')
        assert r.status_code == 200


def test_healthcheck_nao_expoe_segredos(app):
    with app.test_client() as c:
        r = c.get('/health')
        payload = r.get_json()

        assert 'secret_key' not in {k.lower() for k in payload.keys()}
        assert 'database_url' not in {k.lower() for k in payload.keys()}
        texto = str(payload)
        assert 'SECRET_KEY' not in texto
        assert 'postgresql://' not in texto


def test_healthcheck_reporta_status_e_database_connected(app):
    with app.test_client() as c:
        r = c.get('/health')
        payload = r.get_json()
        assert payload['status'] == 'ok'
        assert payload['database_connected'] is True
        assert payload['app_env'] == 'testing'
