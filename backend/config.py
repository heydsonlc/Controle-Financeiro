"""
Configurações da aplicação por ambiente
"""
import os
from pathlib import Path

# Diretório base do projeto
BASE_DIR = Path(__file__).resolve().parent.parent


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
    """Configuração de desenvolvimento (SQLite local)"""
    DEBUG = True
    TESTING = False
    SQLALCHEMY_ECHO = True  # Log SQL queries em desenvolvimento

    # SQLite local - caminho absoluto
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'data' / 'gastos.db'}"


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

    # Hardening de produÃ§Ã£o: sem fallbacks inseguros
    if env == 'production':
        secret = os.getenv('SECRET_KEY')
        if not secret or secret.strip() in {'', 'dev-secret-key-change-me', 'dev-secret-key-local-123456'}:
            raise RuntimeError('SECRET_KEY de producao ausente ou insegura')

        db_url = os.getenv('DATABASE_URL')
        if not db_url or db_url.strip() == '':
            raise RuntimeError('DATABASE_URL de producao ausente')

    return cfg
