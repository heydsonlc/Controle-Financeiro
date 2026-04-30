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
    'Ambiente development nao pode usar DATABASE_URL remota. '
    'Use PostgreSQL local ou remova DATABASE_URL para fallback SQLite.'
)


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


def _development_database_uri():
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

    # JSON
    JSON_AS_ASCII = False
    JSON_SORT_KEYS = False

    # CORS
    CORS_HEADERS = 'Content-Type'


class DevelopmentConfig(Config):
    """Configuracao de desenvolvimento (PostgreSQL local ou SQLite fallback)"""
    DEBUG = True
    TESTING = False
    SQLALCHEMY_ECHO = True  # Log SQL queries em desenvolvimento

    # PostgreSQL local via DATABASE_URL; SQLite local permanece fallback temporario.
    SQLALCHEMY_DATABASE_URI = SQLITE_FALLBACK_URI


class ProductionConfig(Config):
    """Configuração de produção (PostgreSQL)"""
    DEBUG = False
    TESTING = False

    # ProduÃ§Ã£o deve usar DATABASE_URL explÃ­cito via ambiente
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')


class TestingConfig(Config):
    """Configuração de testes"""
    TESTING = True
    DEBUG = True

    # SQLite em memória para testes rápidos
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


# Dicionário de configurações
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(env=None):
    """
    Retorna a configuração baseada no ambiente

    Args:
        env: Nome do ambiente ('development', 'production', 'testing')

    Returns:
        Classe de configuração apropriada
    """
    if env is None:
        env = os.getenv('FLASK_ENV', 'development')

    cfg = config.get(env, config['default'])

    if cfg is DevelopmentConfig:
        DevelopmentConfig.SQLALCHEMY_DATABASE_URI = _development_database_uri()

    # Hardening de produÃ§Ã£o: sem fallbacks inseguros
    if env == 'production':
        secret = os.getenv('SECRET_KEY')
        if not secret or secret.strip() in {'', 'dev-secret-key-change-me', 'dev-secret-key-local-123456'}:
            raise RuntimeError('SECRET_KEY de producao ausente ou insegura')

        db_url = os.getenv('DATABASE_URL')
        if not db_url or db_url.strip() == '':
            raise RuntimeError('DATABASE_URL de producao ausente')
        ProductionConfig.SQLALCHEMY_DATABASE_URI = db_url.strip()

    return cfg
