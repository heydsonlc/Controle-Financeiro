"""
Testes DEPLOY-READY-FIN-1 — prontidao para publicacao em financeiro.kortexbrasil.com.

Cobre:
- DATA_DIR centraliza os diretorios gravaveis (uploads, OCR, backups) e e
  obrigatorio em production (disco persistente)
- DATABASE_URL remota: normalizacao postgres:// -> postgresql://, SSL exigido
  e pool pequeno compativel com o pooler do Supabase
- ambiente hospedado: cookie __Host-, sessao com expiracao, limite de upload
- cabecalhos de seguranca apenas em ambiente hospedado (local intacto)
- verificacao de Origin em requisicoes de escrita (CSRF entre subdominios)
- backup/restauracao via pg_dump/pg_restore bloqueados em ambiente hospedado
- render.yaml: runtime/regiao/disco/variaveis sensiveis sem valor
"""
from pathlib import Path

import pytest

from backend.app import create_app
from backend.config import (
    BASE_DIR,
    get_config,
    normalizar_database_url,
    opcoes_engine_remoto,
    resolver_data_dir,
)
from backend.models import db
from tests.conftest import autenticar_cliente_teste


ROOT = Path(__file__).resolve().parent.parent
SECRET_FORTE = 'x7K9mP2qR5vN8wZ3jL6hF1cB4dS0aXyEuT2Mn5pQ8rW'
URL_REMOTA = 'postgresql://user:pass@remote.example:5432/db'


@pytest.fixture()
def env_hospedado(monkeypatch, tmp_path):
    monkeypatch.setenv('SECRET_KEY', SECRET_FORTE)
    monkeypatch.setenv('DATABASE_URL', URL_REMOTA)
    monkeypatch.setenv('DATA_DIR', str(tmp_path / 'persistente'))
    return tmp_path / 'persistente'


@pytest.fixture()
def app_hospedado(tmp_path):
    """App de teste (SQLite em memoria) com o comportamento de ambiente hospedado ligado."""
    app = create_app('testing')
    app.config['AMBIENTE_HOSPEDADO'] = True
    app.config['BACKUP_BASE_DIR'] = tmp_path / 'backups'
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


# ---------------------------------------------------------------------------
# DATA_DIR
# ---------------------------------------------------------------------------

def test_data_dir_padrao_continua_sendo_pasta_data_do_projeto(monkeypatch):
    monkeypatch.delenv('DATA_DIR', raising=False)
    assert resolver_data_dir('local') == BASE_DIR / 'data'
    assert resolver_data_dir('staging') == BASE_DIR / 'data'


def test_data_dir_obrigatorio_em_production(monkeypatch):
    monkeypatch.delenv('DATA_DIR', raising=False)
    with pytest.raises(RuntimeError, match='DATA_DIR'):
        resolver_data_dir('production')


def test_data_dir_relativo_e_recusado(monkeypatch):
    monkeypatch.setenv('DATA_DIR', 'dados/relativos')
    with pytest.raises(RuntimeError, match='absoluto'):
        resolver_data_dir('staging')


def test_diretorios_gravaveis_derivam_de_data_dir(env_hospedado):
    cfg = get_config('production')
    assert Path(cfg.DATA_DIR) == env_hospedado
    assert Path(cfg.UPLOAD_LOGOS_DIR) == env_hospedado / 'uploads' / 'logos' / 'categorias'
    assert Path(cfg.FINANCIAMENTO_DOCUMENTOS_DIR) == env_hospedado / 'uploads' / 'financiamentos'
    assert Path(cfg.OCR_BASE_DIR) == env_hospedado / 'ocr'
    assert Path(cfg.BACKUP_BASE_DIR) == env_hospedado / 'backups'


def test_cenario_ativo_mobilidade_grava_em_data_dir(tmp_path):
    app = create_app('testing')
    app.config['DATA_DIR'] = tmp_path
    with app.app_context():
        db.create_all()
        client = autenticar_cliente_teste(app.test_client(), app)
        resposta = client.post('/api/veiculos/cenario-ativo', json={'cenario': 'teste'})
        assert resposta.status_code == 200
        assert (tmp_path / 'mobilidade_cenario_ativo.json').exists()
        db.session.remove()
        db.drop_all()


# ---------------------------------------------------------------------------
# Banco remoto (Supabase)
# ---------------------------------------------------------------------------

def test_database_url_postgres_legado_e_normalizada():
    assert normalizar_database_url('postgres://u:p@h:5432/db') == 'postgresql://u:p@h:5432/db'
    assert normalizar_database_url(URL_REMOTA) == URL_REMOTA


def test_opcoes_engine_remoto_exigem_ssl_e_pool_pequeno():
    opcoes = opcoes_engine_remoto(URL_REMOTA)
    assert opcoes['pool_pre_ping'] is True
    assert opcoes['connect_args'] == {'sslmode': 'require'}
    assert opcoes['pool_size'] + opcoes['max_overflow'] <= 5


def test_opcoes_engine_remoto_respeita_sslmode_explicito():
    opcoes = opcoes_engine_remoto(URL_REMOTA + '?sslmode=verify-full')
    assert 'connect_args' not in opcoes


def test_staging_aplica_opcoes_engine_e_normalizacao(monkeypatch, env_hospedado):
    monkeypatch.setenv('DATABASE_URL', 'postgres://user:pass@remote.example:5432/db')
    cfg = get_config('staging')
    assert cfg.SQLALCHEMY_DATABASE_URI.startswith('postgresql://')
    assert cfg.SQLALCHEMY_ENGINE_OPTIONS['connect_args'] == {'sslmode': 'require'}


# ---------------------------------------------------------------------------
# Sessao e limites em ambiente hospedado
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('ambiente', ['staging', 'production'])
def test_ambiente_hospedado_endurece_sessao(env_hospedado, ambiente):
    cfg = get_config(ambiente)
    assert cfg.AMBIENTE_HOSPEDADO is True
    assert cfg.SESSION_COOKIE_NAME.startswith('__Host-')
    assert cfg.SESSION_COOKIE_SECURE is True
    assert cfg.SESSION_PERMANENTE is True
    assert cfg.PERMANENT_SESSION_LIFETIME.total_seconds() <= 12 * 3600
    assert cfg.MAX_CONTENT_LENGTH is not None


def test_ambiente_local_mantem_comportamento_anterior(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    cfg = get_config('local')
    assert cfg.AMBIENTE_HOSPEDADO is False
    assert cfg.SESSION_PERMANENTE is False
    assert not getattr(cfg, 'SESSION_COOKIE_NAME', 'session').startswith('__Host-')


def test_login_em_ambiente_hospedado_cria_sessao_permanente(app_hospedado):
    app_hospedado.config['SESSION_PERMANENTE'] = True
    client = autenticar_cliente_teste(app_hospedado.test_client(), app_hospedado)
    with client.session_transaction() as sessao:
        assert sessao.permanent is True


# ---------------------------------------------------------------------------
# Cabecalhos de seguranca
# ---------------------------------------------------------------------------

def test_cabecalhos_de_seguranca_em_ambiente_hospedado(app_hospedado):
    resposta = app_hospedado.test_client().get('/health')
    assert resposta.headers['X-Content-Type-Options'] == 'nosniff'
    assert resposta.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert resposta.headers['Referrer-Policy'] == 'same-origin'
    hsts = resposta.headers['Strict-Transport-Security']
    assert 'max-age=' in hsts
    # Nunca afetar outros subdominios Kortex (portal, site institucional).
    assert 'includeSubDomains' not in hsts


def test_cabecalhos_de_seguranca_ausentes_em_local():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        resposta = app.test_client().get('/health')
        assert 'Strict-Transport-Security' not in resposta.headers
        assert 'X-Content-Type-Options' not in resposta.headers
        db.session.remove()
        db.drop_all()


# ---------------------------------------------------------------------------
# Verificacao de Origin (CSRF entre subdominios *.kortexbrasil.com)
# ---------------------------------------------------------------------------

def test_escrita_com_origin_de_outro_subdominio_e_bloqueada(app_hospedado):
    client = autenticar_cliente_teste(app_hospedado.test_client(), app_hospedado)
    resposta = client.post(
        '/api/categorias',
        json={'nome': 'X'},
        headers={'Origin': 'https://portal.kortexbrasil.com'},
    )
    assert resposta.status_code == 403


def test_login_com_origin_externa_e_bloqueado(app_hospedado):
    resposta = app_hospedado.test_client().post(
        '/login',
        data={'email': 'a@b.c', 'senha': 'x'},
        headers={'Origin': 'https://atacante.example'},
    )
    assert resposta.status_code == 403


def test_origin_null_e_bloqueada(app_hospedado):
    resposta = app_hospedado.test_client().post('/logout', headers={'Origin': 'null'})
    assert resposta.status_code == 403


def test_escrita_same_origin_e_permitida(app_hospedado):
    client = autenticar_cliente_teste(app_hospedado.test_client(), app_hospedado)
    resposta = client.post('/logout', headers={'Origin': 'http://localhost'})
    assert resposta.status_code == 302


def test_referer_same_origin_e_aceito_quando_origin_ausente(app_hospedado):
    resposta = app_hospedado.test_client().post(
        '/logout', headers={'Referer': 'http://localhost/configuracoes'}
    )
    assert resposta.status_code == 302


def test_get_nao_passa_pela_verificacao_de_origin(app_hospedado):
    resposta = app_hospedado.test_client().get(
        '/health', headers={'Origin': 'https://atacante.example'}
    )
    assert resposta.status_code == 200


def test_verificacao_de_origin_desligada_em_local():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        resposta = app.test_client().post('/logout', headers={'Origin': 'https://atacante.example'})
        assert resposta.status_code == 302
        db.session.remove()
        db.drop_all()


# ---------------------------------------------------------------------------
# Backup local (pg_dump/pg_restore) indisponivel em ambiente hospedado
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('rota', [
    '/api/backup/executar',
    '/api/backup/restaurar',
    '/api/backup/testar-restauracao',
    '/api/backup/ferramentas/configurar',
    '/api/backup/ferramentas/autodetectar',
])
def test_operacoes_de_backup_local_bloqueadas_em_ambiente_hospedado(app_hospedado, rota):
    client = autenticar_cliente_teste(app_hospedado.test_client(), app_hospedado)
    resposta = client.post(rota, json={'pg_dump_path': '/bin/sh'})
    assert resposta.status_code == 403
    assert resposta.get_json()['success'] is False


def test_status_de_backup_continua_disponivel_em_ambiente_hospedado(app_hospedado):
    client = autenticar_cliente_teste(app_hospedado.test_client(), app_hospedado)
    assert client.get('/api/backup/status').status_code == 200


# ---------------------------------------------------------------------------
# render.yaml
# ---------------------------------------------------------------------------

def _render_yaml():
    return (ROOT / 'render.yaml').read_text(encoding='utf-8')


def test_render_yaml_usa_runtime_e_versao_python_explicita():
    conteudo = _render_yaml()
    assert 'runtime: python' in conteudo
    assert 'env: python' not in conteudo
    assert 'key: PYTHON_VERSION' in conteudo


def test_render_yaml_monta_disco_persistente_em_data_dir():
    conteudo = _render_yaml()
    assert 'mountPath: /var/data' in conteudo
    assert 'key: DATA_DIR' in conteudo
    assert 'value: /var/data' in conteudo


def test_render_yaml_variaveis_sensiveis_sem_valor():
    conteudo = _render_yaml()
    for chave in ('SECRET_KEY', 'DATABASE_URL', 'CARTOES_CVV_MASTER_PASSWORD'):
        bloco = conteudo.split(f'key: {chave}', 1)
        assert len(bloco) == 2, f'{chave} ausente do render.yaml'
        proxima_linha = bloco[1].strip().splitlines()[0]
        assert proxima_linha.strip() == 'sync: false', f'{chave} deve usar sync: false'


def test_render_yaml_cors_restrito_ao_dominio_financeiro():
    conteudo = _render_yaml()
    assert 'https://financeiro.kortexbrasil.com' in conteudo
    assert "'*'" not in conteudo and '"*"' not in conteudo


def test_env_example_documenta_data_dir():
    conteudo = (ROOT / '.env.example').read_text(encoding='utf-8')
    assert 'DATA_DIR' in conteudo
