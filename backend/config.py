"""
Configurações da aplicação por ambiente
"""
import os
from pathlib import Path
from urllib.parse import urlparse

# Diretório base do projeto
BASE_DIR = Path(__file__).resolve().parent.parent
SQLITE_FALLBACK_URI = f"sqlite:///{BASE_DIR / 'data' / 'gastos.db'}"
DEVELOPMENT_REMOTE_DATABASE_ERROR = (
    'Ambiente local nao pode usar DATABASE_URL remota. '
    'Use PostgreSQL local ou remova DATABASE_URL para fallback SQLite.'
)

# DEPLOY-PREP-1: nomes de ambiente aceitos e seus sinonimos legados.
# APP_ENV e a variavel canonica (local/staging/production); FLASK_ENV
# continua funcionando como fallback para nao quebrar configuracao
# existente. 'development' e sinonimo legado de 'local'.
ENV_ALIASES = {
    'development': 'local',
    'dev': 'local',
    'test': 'testing',
}
VALORES_SECRET_KEY_FRACOS_CONHECIDOS = {
    'dev-secret-key-change-me',
    'dev-secret-key-local-123456',
    'dev-secret-key-change-in-production',
    'change-me-generate-a-strong-secret',
}
SECRET_KEY_TAMANHO_MINIMO = 32
SECRET_KEY_MARCADORES_FRACOS = ('dev', 'test', 'local', 'change', 'secret-key', 'senha', 'password', '123')


def normalizar_nome_ambiente(nome):
    """Resolve sinonimos legados (ex.: 'development' -> 'local')."""
    nome = (nome or '').strip().lower()
    return ENV_ALIASES.get(nome, nome)


def resolver_app_env():
    """APP_ENV e a variavel canonica; FLASK_ENV e aceito por compatibilidade."""
    bruto = os.getenv('APP_ENV') or os.getenv('FLASK_ENV') or 'local'
    return normalizar_nome_ambiente(bruto)


def validar_secret_key(secret_key, ambiente):
    """Retorna mensagem de erro se a SECRET_KEY for inadequada para o ambiente.

    Em 'local', qualquer valor (inclusive o default) e aceito. Em 'staging' e
    'production', a chave precisa ser explicita, longa e sem marcadores de
    valor de exemplo/desenvolvimento — falha fechado.
    """
    if ambiente not in {'staging', 'production'}:
        return None

    valor = (secret_key or '').strip()
    if not valor:
        return 'SECRET_KEY insegura para ambiente não local: ausente.'

    if valor in VALORES_SECRET_KEY_FRACOS_CONHECIDOS:
        return 'SECRET_KEY insegura para ambiente não local: valor padrão conhecido.'

    if len(valor) < SECRET_KEY_TAMANHO_MINIMO:
        return (
            f'SECRET_KEY insegura para ambiente não local: '
            f'tamanho menor que {SECRET_KEY_TAMANHO_MINIMO} caracteres.'
        )

    valor_lower = valor.lower()
    marcador_encontrado = next((m for m in SECRET_KEY_MARCADORES_FRACOS if m in valor_lower), None)
    if marcador_encontrado:
        return f'SECRET_KEY insegura para ambiente não local: contém marcador "{marcador_encontrado}".'

    return None


def validar_cvv_master_password(senha, ambiente, cvv_habilitado):
    """Retorna mensagem de erro se a senha de desbloqueio de CVV for inadequada.

    'cvv_habilitado' indica se existe algum cartao com CVV cadastrado (o
    recurso so precisa de senha configurada quando ha algo a proteger).
    Em local, pode ficar vazia (o endpoint falha fechado por conta propria).
    """
    if ambiente not in {'staging', 'production'} or not cvv_habilitado:
        return None

    valor = (senha or '').strip()
    if not valor:
        return 'CARTOES_CVV_MASTER_PASSWORD ausente em ambiente não local com cartão(ões) com CVV cadastrado.'

    if len(valor) < 12:
        return 'CARTOES_CVV_MASTER_PASSWORD insegura: tamanho menor que 12 caracteres.'

    valores_obvios = {'123456', 'senha', 'password', 'admin', 'trocar', 'mudar'}
    if valor.lower() in valores_obvios:
        return 'CARTOES_CVV_MASTER_PASSWORD insegura: valor óbvio.'

    return None


def _is_local_database_url(database_url):
    """Return True only for clearly local development database URLs."""
    raw_url = (database_url or '').strip()
    if not raw_url:
        return False

    lowered_url = raw_url.lower()
    blocked_markers = ('digitalocean', 'ondigitalocean', 'do-user')
    if any(marker in lowered_url for marker in blocked_markers):
        return False

    parsed = urlparse(raw_url)
    scheme = parsed.scheme.lower()

    if scheme == 'sqlite':
        return parsed.hostname is None

    if scheme in {'postgresql', 'postgres'}:
        if parsed.hostname is None:
            return parsed.netloc == ''

        hostname = parsed.hostname.strip('[]').lower()
        return hostname in {'localhost', '127.0.0.1', '::1'}

    return False


def _local_database_uri():
    database_url = os.getenv('DATABASE_URL')
    if not database_url or database_url.strip() == '':
        return SQLITE_FALLBACK_URI

    if not _is_local_database_url(database_url):
        raise RuntimeError(DEVELOPMENT_REMOTE_DATABASE_ERROR)

    return database_url.strip()


class Config:
    """Configuração base"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')
    CARTOES_CVV_MASTER_PASSWORD = os.getenv('CARTOES_CVV_MASTER_PASSWORD')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    UPLOAD_LOGOS_DIR = BASE_DIR / 'data' / 'uploads' / 'logos' / 'categorias'
    MAX_LOGO_SIZE = 1024 * 1024

    # JSON
    JSON_AS_ASCII = False
    JSON_SORT_KEYS = False

    # CORS
    CORS_HEADERS = 'Content-Type'

    # DEPLOY-PREP-1: cookie de sessao. HTTPONLY e SAMESITE valem em qualquer
    # ambiente; SECURE exige HTTPS (por isso so vai True em staging/production).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False


class LocalConfig(Config):
    """Configuracao local (PostgreSQL local ou SQLite fallback)"""
    DEBUG = True
    TESTING = False
    SQLALCHEMY_ECHO = True  # Log SQL queries em desenvolvimento local

    # PostgreSQL local via DATABASE_URL; SQLite local permanece fallback temporario.
    SQLALCHEMY_DATABASE_URI = SQLITE_FALLBACK_URI


class StagingConfig(Config):
    """Configuracao de staging (PostgreSQL remoto, HTTPS esperado)"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True

    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')


class ProductionConfig(Config):
    """Configuração de produção (PostgreSQL remoto, HTTPS obrigatório)"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True

    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')


class TestingConfig(Config):
    """Configuração de testes"""
    TESTING = True
    DEBUG = True

    # SQLite em memória para testes rápidos
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


# Dicionário de configurações. 'development' permanece como sinonimo de
# 'local' resolvido por normalizar_nome_ambiente() antes deste lookup.
config = {
    'local': LocalConfig,
    'staging': StagingConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': LocalConfig,
}


def get_config(env=None):
    """
    Retorna a configuração baseada no ambiente

    Args:
        env: Nome do ambiente ('local', 'staging', 'production', 'testing').
             Aceita tambem os sinonimos legados em ENV_ALIASES (ex.: 'development').

    Returns:
        Classe de configuração apropriada
    """
    if env is None:
        env = resolver_app_env()
    else:
        env = normalizar_nome_ambiente(env)

    cfg = config.get(env, config['default'])

    if cfg is LocalConfig:
        LocalConfig.SQLALCHEMY_DATABASE_URI = _local_database_uri()

    # Hardening de staging/producao: sem fallbacks inseguros, falha fechado.
    if env in {'staging', 'production'}:
        erro_secret = validar_secret_key(os.getenv('SECRET_KEY'), env)
        if erro_secret:
            raise RuntimeError(erro_secret)

        db_url = os.getenv('DATABASE_URL')
        if not db_url or db_url.strip() == '':
            raise RuntimeError(f'DATABASE_URL de {env} ausente')
        cfg.SQLALCHEMY_DATABASE_URI = db_url.strip()

    return cfg
