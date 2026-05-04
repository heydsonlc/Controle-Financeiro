"""
Aplicação Flask - Sistema de Controle Financeiro

Este arquivo inicializa a aplicação Flask e configura rotas, banco de dados e middleware
"""
import os
import sys
import logging
from pathlib import Path
from flask import Flask, jsonify, render_template
from flask_cors import CORS
from flask_migrate import Migrate
from dotenv import load_dotenv

# Adicionar diretório raiz ao path se necessário
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from backend.config import get_config
    from backend.models import db
except ImportError:
    from config import get_config
    from models import db

# Carregar variáveis de ambiente
load_dotenv('.env.local')  # Para desenvolvimento


def _parse_bool_env(value, default=False):
    """Converte flags simples de ambiente para boolean."""
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _cors_origins_from_env():
    """Retorna origens CORS permitidas; por padrao, apenas origens locais."""
    raw_origins = os.getenv('CORS_ORIGINS')
    if raw_origins:
        origins = [origin.strip() for origin in raw_origins.split(',') if origin.strip()]
        if origins:
            return origins

    return [
        'http://localhost:5000',
        'http://127.0.0.1:5000',
    ]


def create_app(config_name=None):
    """
    Factory para criar a aplicação Flask

    Args:
        config_name: Nome da configuração ('development', 'production', 'testing')

    Returns:
        app: Instância configurada do Flask
    """
    app = Flask(__name__,
                template_folder='../frontend/templates',
                static_folder='../frontend/static')

    # Configuração baseada no ambiente
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app.config.from_object(get_config(config_name))

    # Logging mÃ­nimo coerente por ambiente
    if not logging.getLogger().handlers:
        level = logging.INFO
        if config_name in {'development', 'testing'}:
            level = logging.DEBUG
        logging.basicConfig(
            level=level,
            format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        )

    # Garantir encoding UTF-8 para JSON
    app.config['JSON_AS_ASCII'] = False
    app.config['JSON_SORT_KEYS'] = False

    # Desabilitar cache de templates e arquivos estáticos em desenvolvimento
    if config_name == 'development':
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    # Inicializar extensões
    db.init_app(app)
    CORS(app, origins=_cors_origins_from_env())

    # Inicializar Flask-Migrate
    migrate = Migrate(app, db)

    # Compatibilidade de schema (SQLite): alguns ambientes usam DB criado fora do Alembic.
    try:
        from backend.services.sqlite_schema_compat import ensure_sqlite_schema_compat
    except ImportError:
        from services.sqlite_schema_compat import ensure_sqlite_schema_compat
    with app.app_context():
        ensure_sqlite_schema_compat()

    # Registrar blueprints (rotas)
    register_blueprints(app)

    # Registrar handlers de erro
    register_error_handlers(app)

    # Middleware para garantir UTF-8 em todas as respostas
    @app.after_request
    def add_charset_to_content_type(response):
        """Adiciona charset UTF-8 explicitamente no Content-Type de todas as respostas"""
        if response.content_type and 'charset' not in response.content_type:
            response.content_type = f'{response.content_type}; charset=utf-8'
        return response

    # Rotas de páginas
    @app.route('/')
    def index():
        """Página inicial - Dashboard"""
        return render_template('index.html', active_page='dashboard', page_title='Dashboard Financeiro')

    @app.route('/categorias')
    def categorias():
        """Página de gerenciamento de categorias"""
        return render_template('categorias.html', active_page='categorias', page_title='Categorias')

    @app.route('/despesas')
    def despesas():
        """Página de gerenciamento de despesas"""
        return render_template('despesas.html', active_page='despesas', page_title='Gerenciamento de Despesas')

    @app.route('/recorrencias')
    def recorrencias():
        """Pagina de gerenciamento de cadastros recorrentes"""
        return render_template('recorrencias.html', active_page='recorrencias', page_title='Recorrencias')

    @app.route('/cartoes')
    def cartoes():
        """Página de gerenciamento de cartões de crédito"""
        return render_template('cartoes.html', active_page='cartoes', page_title='Cartões')

    @app.route('/lancamentos')
    def lancamentos():
        """Página de lançamentos de gastos"""
        return render_template('lancamentos.html', active_page='lancamentos', page_title='Lançamentos')

    @app.route('/receitas')
    def receitas():
        """Página de gerenciamento de receitas"""
        return render_template('receitas.html', active_page='receitas', page_title='Gerenciamento de Receitas')

    @app.route('/financiamentos')
    def financiamentos():
        """Página de gerenciamento de financiamentos"""
        return render_template('financiamentos.html', active_page='financiamentos', page_title='Financiamentos')

    @app.route('/financiamentos/seguro')
    def financiamento_seguro():
        """Página de gerenciamento de vigências de seguro habitacional"""
        return render_template('financiamento_seguro.html')

    @app.route('/configuracoes')
    def configuracoes():
        """Página de configurações do sistema"""
        return render_template('configuracoes.html', active_page='configuracoes', page_title='Configurações')

    @app.route('/contas-bancarias')
    def contas_bancarias():
        """Página de gerenciamento de contas bancárias"""
        return render_template('contas_bancarias.html', active_page='contas_bancarias', page_title='Contas Bancárias')

    @app.route('/patrimonio')
    def patrimonio():
        """Página de gerenciamento de patrimônio (caixinhas)"""
        return render_template('patrimonio.html', active_page='patrimonio', page_title='Patrimônio')

    @app.route('/preferencias')
    def preferencias():
        """Página de preferências e configurações gerais"""
        return render_template('preferencias.html', active_page='preferencias', page_title='Preferências')

    @app.route('/importar-cartao')
    def importar_cartao():
        """Página de importação de fatura de cartão (CSV)"""
        return render_template('importar_cartao.html', active_page='importar_cartao', page_title='Importar Cartão')

    @app.route('/imposto-renda')
    def imposto_renda():
        """Pagina de comprovantes do Imposto de Renda"""
        return render_template('imposto_renda.html', active_page='imposto_renda', page_title='Imposto de Renda')

    @app.route('/veiculos')
    def veiculos():
        return render_template('veiculos.html', active_page='veiculos', page_title='Veículos')

    @app.route('/health')
    def health():
        """Health check para monitoramento"""
        return jsonify({
            'status': 'ok',
            'environment': config_name,
            'database': 'connected'
        })

    return app


def register_blueprints(app):
    """
    Registra os blueprints (módulos de rotas)

    Args:
        app: Instância do Flask
    """
    # Importar blueprints aqui para evitar importação circular
    try:
        from backend.routes.categorias import categorias_bp, categorias_cartao_bp
        from backend.routes.despesas import despesas_bp
        from backend.routes.recorrencias import recorrencias_bp
        from backend.routes.cartoes import cartoes_bp
        from backend.routes.consorcios import consorcios_bp
        from backend.routes.receitas import receitas_bp
        from backend.routes.financiamentos import financiamentos_bp
        from backend.routes.financiamento_seguro import bp as financiamento_seguro_bp
        from backend.routes.contas_bancarias import contas_bancarias_bp
        from backend.routes.patrimonio import patrimonio_bp
        from backend.routes.dashboard import dashboard_bp
        from backend.routes.preferencias import preferencias_bp
        from backend.routes.importacao_cartao import bp as importacao_cartao_bp
        from backend.routes.indexadores import indexadores_bp
        from backend.routes.veiculos import veiculos_bp
        from backend.routes.despesas_previstas import despesas_previstas_bp
        from backend.routes.mobilidade_app import mobilidade_app_bp
        from backend.routes.ir import ir_bp
    except ImportError:
        from routes.categorias import categorias_bp, categorias_cartao_bp
        from routes.despesas import despesas_bp
        from routes.recorrencias import recorrencias_bp
        from routes.cartoes import cartoes_bp
        from routes.consorcios import consorcios_bp
        from routes.receitas import receitas_bp
        from routes.financiamentos import financiamentos_bp
        from routes.financiamento_seguro import bp as financiamento_seguro_bp
        from routes.contas_bancarias import contas_bancarias_bp
        from routes.patrimonio import patrimonio_bp
        from routes.dashboard import dashboard_bp
        from routes.preferencias import preferencias_bp
        from routes.importacao_cartao import bp as importacao_cartao_bp
        from routes.indexadores import indexadores_bp
        from routes.veiculos import veiculos_bp
        from routes.despesas_previstas import despesas_previstas_bp
        from routes.mobilidade_app import mobilidade_app_bp
        from routes.ir import ir_bp

    # Registrar blueprints
    app.register_blueprint(categorias_bp, url_prefix='/api/categorias')
    app.register_blueprint(categorias_cartao_bp, url_prefix='/api/categorias-cartao')
    app.register_blueprint(despesas_bp, url_prefix='/api/despesas')
    app.register_blueprint(recorrencias_bp, url_prefix='/api/recorrencias')
    app.register_blueprint(cartoes_bp, url_prefix='/api/cartoes')
    app.register_blueprint(consorcios_bp, url_prefix='/api/consorcios')
    app.register_blueprint(receitas_bp, url_prefix='/api/receitas')
    app.register_blueprint(financiamentos_bp, url_prefix='/api/financiamentos')
    app.register_blueprint(financiamento_seguro_bp)  # Já tem url_prefix no blueprint
    app.register_blueprint(contas_bancarias_bp, url_prefix='/api/contas')
    app.register_blueprint(patrimonio_bp, url_prefix='/api/patrimonio')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(preferencias_bp, url_prefix='/api/preferencias')
    app.register_blueprint(importacao_cartao_bp)  # Já tem url_prefix no blueprint
    app.register_blueprint(indexadores_bp)  # Indexadores (TR, IPCA, etc.)
    app.register_blueprint(veiculos_bp, url_prefix='/api/veiculos')
    app.register_blueprint(despesas_previstas_bp, url_prefix='/api/despesas-previstas')
    app.register_blueprint(mobilidade_app_bp, url_prefix='/api/mobilidade-app')
    app.register_blueprint(ir_bp, url_prefix='/api/ir')


def register_error_handlers(app):
    """
    Registra handlers para tratamento de erros

    Args:
        app: Instância do Flask
    """

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Recurso não encontrado'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({'error': 'Erro interno do servidor'}), 500

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({'error': 'Requisição inválida'}), 400


# Criar instância da aplicação
app = create_app()


if __name__ == '__main__':
    # Criar tabelas se não existirem
    with app.app_context():
        db.create_all()
        print("=> Tabelas do banco de dados criadas/verificadas com sucesso!")

        # Iniciar scheduler de jobs automáticos (faturas mensais, etc.)
        # Comentado temporariamente - requer instalação do apscheduler
        # try:
        #     from backend.scheduler import start_scheduler
        #     start_scheduler()
        # except ImportError:
        #     from scheduler import start_scheduler
        #     start_scheduler()

        flask_host = os.getenv('FLASK_HOST', '127.0.0.1')
        flask_port = int(os.getenv('FLASK_PORT', '5000'))
        flask_debug = _parse_bool_env(
            os.getenv('FLASK_DEBUG'),
            default=False
        )

        print(f"=> Servidor iniciando em http://{flask_host}:{flask_port}")
        print(f"=> Ambiente: {os.getenv('FLASK_ENV', 'development')}")
        print(f"=> Debug: {'ativado' if flask_debug else 'desativado'}")
        print("=> Pressione CTRL+C para parar")

    # Executar servidor
    app.run(
        host=flask_host,
        port=flask_port,
        debug=flask_debug
    )
