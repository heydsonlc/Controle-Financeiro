"""
Testes DEPLOY-HOST-1 — validacao de preparacao para hospedagem (Render).

Cobre:
- backend.app expõe `app` no nivel do modulo, compativel com
  `gunicorn backend.app:app`
- gunicorn esta instalavel/importavel (presente em requirements.txt)
- render.yaml nao contem segredos (SECRET_KEY, DATABASE_URL, senha)
- render.yaml aponta para o healthcheck correto e nao habilita
  autoDeploy sem intencao explicita
- runtime.txt existe e usa uma versao de Python plausivel
- staging (via StagingConfig) continua exigindo SECRET_KEY forte e
  DATABASE_URL, e mantendo SESSION_COOKIE_SECURE=True (regressao do
  DEPLOY-PREP-1, relevante aqui porque e a config que o Render usa)
"""
import os
import re

import pytest

from backend.config import get_config


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_app_module_expõe_variavel_app_compativel_com_gunicorn():
    from backend.app import app
    from flask import Flask

    assert isinstance(app, Flask)


def test_gunicorn_esta_em_requirements():
    caminho = os.path.join(ROOT, 'requirements.txt')
    with open(caminho, encoding='utf-8') as f:
        conteudo = f.read()
    assert re.search(r'^gunicorn', conteudo, re.MULTILINE), 'gunicorn nao encontrado em requirements.txt'


def test_gunicorn_e_importavel():
    import gunicorn  # noqa: F401


def test_render_yaml_existe_e_nao_contem_segredos():
    caminho = os.path.join(ROOT, 'render.yaml')
    assert os.path.exists(caminho), 'render.yaml nao encontrado'

    with open(caminho, encoding='utf-8') as f:
        conteudo = f.read()

    marcadores_proibidos = [
        'postgresql://',
        'postgres://',
        re.compile(r'SECRET_KEY:\s*[\'"]?[A-Za-z0-9_\-]{20,}'),
    ]
    for marcador in marcadores_proibidos:
        if isinstance(marcador, str):
            assert marcador not in conteudo, f'render.yaml contem marcador proibido: {marcador}'
        else:
            assert not marcador.search(conteudo), f'render.yaml contem um valor que parece SECRET_KEY real'


def test_render_yaml_aponta_para_healthcheck_correto():
    caminho = os.path.join(ROOT, 'render.yaml')
    with open(caminho, encoding='utf-8') as f:
        conteudo = f.read()
    assert 'healthCheckPath: /health' in conteudo


def test_render_yaml_start_command_usa_gunicorn():
    caminho = os.path.join(ROOT, 'render.yaml')
    with open(caminho, encoding='utf-8') as f:
        conteudo = f.read()
    assert 'gunicorn' in conteudo
    assert 'backend.app:app' in conteudo or 'backend.app:create_app()' in conteudo


def test_render_yaml_autodeploy_desligado_por_padrao():
    caminho = os.path.join(ROOT, 'render.yaml')
    with open(caminho, encoding='utf-8') as f:
        conteudo = f.read()
    assert 'autoDeploy: false' in conteudo


def test_runtime_txt_existe_com_versao_plausivel():
    caminho = os.path.join(ROOT, 'runtime.txt')
    assert os.path.exists(caminho), 'runtime.txt nao encontrado'
    with open(caminho, encoding='utf-8') as f:
        conteudo = f.read().strip()
    assert re.match(r'^python-3\.(9|1[0-9])(\.\d+)?$', conteudo), f'versao de runtime.txt inesperada: {conteudo}'


def test_staging_config_continua_exigindo_secret_key_forte(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@remote:5432/db')
    with pytest.raises(RuntimeError):
        get_config('staging')


def test_staging_config_session_cookie_secure_true(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'x7K9mP2qR5vN8wZ3jL6hF1cB4dS0aXyEuT2Mn5pQ8rW')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@remote:5432/db')
    cfg = get_config('staging')
    assert cfg.SESSION_COOKIE_SECURE is True


def test_sqlalchemy_echo_desligado_em_staging(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'x7K9mP2qR5vN8wZ3jL6hF1cB4dS0aXyEuT2Mn5pQ8rW')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@remote:5432/db')
    cfg = get_config('staging')
    assert cfg.SQLALCHEMY_ECHO is False
