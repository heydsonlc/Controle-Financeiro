"""
Configurações da aplicação por ambiente
"""
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

# Diretório base do projeto
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR_PADRAO = BASE_DIR / 'data'
SQLITE_FALLBACK_URI = f"sqlite:///{DATA_DIR_PADRAO / 'gastos.db'}"
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


def resolver_data_dir(ambiente):
    """DEPLOY-READY-FIN-1: raiz unica dos arquivos gravados em runtime.

    Uploads (logos, documentos de financiamento), area de trabalho do OCR,
    backups locais e o cenario ativo de mobilidade vivem abaixo de DATA_DIR.
    Sem DATA_DIR, mantem a pasta data/ do projeto (comportamento historico).
    Em production o filesystem do host e efemero sem disco persistente, entao
    DATA_DIR e obrigatorio — falha fechado para nao perder documentos.
    """
    bruto = (os.getenv('DATA_DIR') or '').strip()
    if not bruto:
        if ambiente == 'production':
            raise RuntimeError(
                'DATA_DIR ausente em production: aponte para o disco persistente '
                '(ex.: /var/data) para nao perder uploads a cada deploy.'
            )
        return DATA_DIR_PADRAO

    caminho = Path(bruto)
    if not caminho.is_absolute():
        raise RuntimeError('DATA_DIR deve ser um caminho absoluto.')
    return caminho


def aplicar_diretorios_dados(cfg, data_dir):
    """Deriva de DATA_DIR todos os diretorios gravaveis lidos pelos services."""
    cfg.DATA_DIR = data_dir
    cfg.UPLOAD_LOGOS_DIR = data_dir / 'uploads' / 'logos' / 'categorias'
    cfg.FINANCIAMENTO_DOCUMENTOS_DIR = data_dir / 'uploads' / 'financiamentos'
    cfg.OCR_BASE_DIR = data_dir / 'ocr'
    cfg.BACKUP_BASE_DIR = data_dir / 'backups'


def normalizar_database_url(database_url):
    """SQLAlchemy 2 nao aceita o esquema legado 'postgres://'."""
    valor = (database_url or '').strip()
    if valor.startswith('postgres://'):
        return 'postgresql://' + valor[len('postgres://'):]
    return valor


def opcoes_engine_remoto(database_url):
    """Opcoes do engine para PostgreSQL remoto (Supabase via pooler).

    - pool_pre_ping/pool_recycle: o pooler encerra conexoes ociosas.
    - pool pequeno: cada worker do gunicorn tem seu proprio pool, e o pooler
      do Supabase em modo sessao limita conexoes simultaneas por projeto.
    - sslmode=require quando a URL nao define sslmode explicitamente.
    """
    opcoes = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 3,
        'max_overflow': 2,
    }
    if 'sslmode=' not in (database_url or ''):
        opcoes['connect_args'] = {'sslmode': 'require'}
    return opcoes


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
    DATA_DIR = DATA_DIR_PADRAO
    UPLOAD_LOGOS_DIR = DATA_DIR_PADRAO / 'uploads' / 'logos' / 'categorias'
    MAX_LOGO_SIZE = 1024 * 1024

    # DEPLOY-READY-FIN-1: True apenas em staging/production (internet publica).
    # Liga verificacao de Origin, cabecalhos de seguranca/HSTS e bloqueia o
    # backup local via pg_dump/pg_restore. Local e testes ficam inalterados.
    AMBIENTE_HOSPEDADO = False
    SESSION_PERMANENTE = False

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


class HospedadoConfig(Config):
    """Base comum de staging/production (internet publica, HTTPS obrigatorio)."""
    DEBUG = False
    TESTING = False
    AMBIENTE_HOSPEDADO = True

    # Prefixo __Host-: exige Secure, Path=/ e proibe Domain, impedindo que
    # outros subdominios *.kortexbrasil.com sobrescrevam o cookie de sessao.
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_NAME = '__Host-financeiro_session'
    # Sessao expira apos 12h sem uso (renovada a cada requisicao).
    SESSION_PERMANENTE = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    # Limite global do corpo da requisicao (uploads); limites por arquivo
    # continuam nos services (logos 1 MB, documentos 10 MB).
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024

    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')


class StagingConfig(HospedadoConfig):
    """Configuracao de staging (PostgreSQL remoto, HTTPS esperado)"""


class ProductionConfig(HospedadoConfig):
    """Configuração de produção (PostgreSQL remoto, HTTPS obrigatório)"""


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

        db_url = normalizar_database_url(os.getenv('DATABASE_URL'))
        if not db_url:
            raise RuntimeError(f'DATABASE_URL de {env} ausente')
        cfg.SQLALCHEMY_DATABASE_URI = db_url
        if db_url.startswith('postgresql'):
            cfg.SQLALCHEMY_ENGINE_OPTIONS = opcoes_engine_remoto(db_url)

    aplicar_diretorios_dados(cfg, resolver_data_dir(env))

    return cfg
