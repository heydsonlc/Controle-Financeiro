"""
DEPLOY-PREP-1: valida se as variaveis de ambiente estao adequadas para o
ambiente indicado (APP_ENV / FLASK_ENV), sem imprimir nenhum valor real.

Uso:
    venv/Scripts/python.exe scripts/check_deploy_env.py

Le o ambiente da mesma forma que a aplicacao (APP_ENV, com FLASK_ENV como
fallback). Retorna exit code 0 se tudo estiver adequado, 1 caso contrario.
Nunca imprime SECRET_KEY, DATABASE_URL, CARTOES_CVV_MASTER_PASSWORD ou
qualquer outro segredo — so relata "ausente"/"presente"/"fraco"/"forte".
"""
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Mesma ordem de carregamento que backend/app.py: .env.local so tem efeito
# se as variaveis ainda nao estiverem definidas no processo (nunca sobrescreve
# o que staging/production ja injetou via variavel de ambiente real).
load_dotenv('.env.local', encoding='utf-8-sig')

from backend.config import (
    resolver_app_env,
    resolver_data_dir,
    validar_cvv_master_password,
    validar_secret_key,
)


def _cvv_esta_habilitado():
    """Verifica se existe algum cartao com CVV cadastrado no banco atual.

    Retorna None se nao for possivel verificar (ex.: banco inacessivel ou
    tabela ainda nao migrada) — nesse caso o chamador trata como
    'nao verificavel' em vez de assumir false negativo.
    """
    try:
        from backend.app import create_app
        from backend.models import ConfigAgregador, db

        app = create_app()
        with app.app_context():
            existe = db.session.query(
                ConfigAgregador.query.filter(
                    ConfigAgregador.codigo_seguranca.isnot(None)
                ).exists()
            ).scalar()
            return bool(existe)
    except Exception:
        return None


def main():
    ambiente = resolver_app_env()
    problemas = []
    avisos = []

    print(f'Ambiente detectado: {ambiente}')
    print('-' * 50)

    # SECRET_KEY
    secret_key = os.getenv('SECRET_KEY')
    erro_secret = validar_secret_key(secret_key, ambiente)
    if erro_secret:
        problemas.append(erro_secret)
        print('SECRET_KEY: INADEQUADA')
    elif ambiente in {'staging', 'production'}:
        print('SECRET_KEY: adequada (presente, forte)')
    else:
        print(f'SECRET_KEY: {"presente" if secret_key else "ausente (default local sera usado)"}')

    # DATABASE_URL
    database_url = os.getenv('DATABASE_URL')
    if ambiente in {'staging', 'production'} and not database_url:
        problemas.append(f'DATABASE_URL ausente em ambiente {ambiente}.')
        print('DATABASE_URL: AUSENTE')
    elif database_url:
        usa_postgres = database_url.strip().lower().startswith(('postgresql://', 'postgres://', 'postgresql+psycopg2://'))
        print(f'DATABASE_URL: presente ({"PostgreSQL" if usa_postgres else "outro dialeto"})')
        if ambiente in {'staging', 'production'} and not usa_postgres:
            avisos.append('DATABASE_URL em staging/production nao parece PostgreSQL.')
        # DEPLOY-READY-FIN-1: o host direto do Supabase so tem IPv6 e o Render
        # nao abre conexoes de saida IPv6 — usar o Session pooler.
        host = (urlparse(database_url.strip()).hostname or '').lower()
        if ambiente in {'staging', 'production'} and host.startswith('db.') and host.endswith('.supabase.co'):
            problemas.append(
                'DATABASE_URL usa o host direto do Supabase (somente IPv6); '
                'use a connection string do Session pooler (aws-*.pooler.supabase.com).'
            )
            print('DATABASE_URL: host direto do Supabase (INADEQUADO para o Render)')
    else:
        print('DATABASE_URL: ausente (fallback SQLite local sera usado)')

    # DATA_DIR (DEPLOY-READY-FIN-1): uploads precisam de disco persistente
    try:
        data_dir = resolver_data_dir(ambiente)
        origem = 'DATA_DIR' if (os.getenv('DATA_DIR') or '').strip() else 'padrao data/ do projeto'
        print(f'DATA_DIR: {origem}')
        if ambiente == 'staging' and origem != 'DATA_DIR':
            avisos.append('DATA_DIR nao definido em staging: uploads somem a cada deploy/reinicio.')
        elif ambiente in {'staging', 'production'} and not data_dir.exists():
            avisos.append('DATA_DIR definido, mas o diretorio nao existe neste host (disco montado?).')
    except RuntimeError as exc:
        problemas.append(str(exc))
        print('DATA_DIR: INADEQUADO')

    # CARTOES_CVV_MASTER_PASSWORD
    cvv_senha = os.getenv('CARTOES_CVV_MASTER_PASSWORD')
    cvv_habilitado = _cvv_esta_habilitado()
    if cvv_habilitado is None:
        avisos.append('Nao foi possivel verificar se ha cartoes com CVV cadastrado (banco inacessivel ou nao migrado).')
        print('CARTOES_CVV_MASTER_PASSWORD: verificacao de uso indisponivel')
    else:
        erro_cvv = validar_cvv_master_password(cvv_senha, ambiente, cvv_habilitado)
        if erro_cvv:
            problemas.append(erro_cvv)
            print('CARTOES_CVV_MASTER_PASSWORD: INADEQUADA')
        elif cvv_habilitado:
            print('CARTOES_CVV_MASTER_PASSWORD: adequada (ha cartao com CVV cadastrado)')
        else:
            print('CARTOES_CVV_MASTER_PASSWORD: nao necessaria (nenhum cartao com CVV cadastrado)')

    # FLASK_DEBUG nunca deve ficar ligado fora de local
    flask_debug = (os.getenv('FLASK_DEBUG') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
    if ambiente in {'staging', 'production'} and flask_debug:
        problemas.append(f'FLASK_DEBUG esta ativado em ambiente {ambiente}.')
        print('FLASK_DEBUG: ATIVADO (inadequado)')
    else:
        print(f'FLASK_DEBUG: {"ativado" if flask_debug else "desativado"}')

    print('-' * 50)

    if avisos:
        print('Avisos:')
        for aviso in avisos:
            print(f'  - {aviso}')

    if problemas:
        print(f'\n{len(problemas)} problema(s) encontrado(s):')
        for problema in problemas:
            print(f'  - {problema}')
        sys.exit(1)

    print('\nAmbiente adequado.')
    sys.exit(0)


if __name__ == '__main__':
    main()
