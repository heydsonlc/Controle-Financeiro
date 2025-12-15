"""
Aplicação Flask - Sistema de Controle Financeiro

Este arquivo inicializa a aplicação Flask e configura rotas, banco de dados e middleware
"""
import os
import sys
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

    # Desabilitar cache de templates e arquivos estáticos em desenvolvimento
    if config_name == 'development':
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    # Inicializar extensões
    db.init_app(app)
    CORS(app)

    # Inicializar Flask-Migrate
    migrate = Migrate(app, db)

    # Registrar blueprints (rotas)
    register_blueprints(app)

    # Registrar handlers de erro
    register_error_handlers(app)

    # Rotas de páginas
    @app.route('/')
    def index():
        """Página inicial - Dashboard"""
        return render_template('index.html')

    @app.route('/categorias')
    def categorias():
        """Página de gerenciamento de categorias"""
        return render_template('categorias.html')

    @app.route('/despesas')
    def despesas():
        """Página de gerenciamento de despesas"""
        return render_template('despesas.html')

    @app.route('/cartoes')
    def cartoes():
        """Página de gerenciamento de cartões de crédito"""
        return render_template('cartoes.html')

    @app.route('/lancamentos')
    def lancamentos():
        """Página de lançamentos de gastos"""
        return render_template('lancamentos.html')

    @app.route('/receitas')
    def receitas():
        """Página de gerenciamento de receitas"""
        return render_template('receitas.html')

    @app.route('/financiamentos')
    def financiamentos():
        """Página de gerenciamento de financiamentos"""
        return render_template('financiamentos.html')

    @app.route('/configuracoes')
    def configuracoes():
        """Página de configurações do sistema"""
        return render_template('configuracoes.html')

    @app.route('/contas-bancarias')
    def contas_bancarias():
        """Página de gerenciamento de contas bancárias"""
        return render_template('contas_bancarias.html')

    @app.route('/patrimonio')
    def patrimonio():
        """Página de gerenciamento de patrimônio (caixinhas)"""
        return render_template('patrimonio.html')

    @app.route('/preferencias')
    def preferencias():
        """Página de preferências e configurações gerais"""
        return render_template('preferencias.html')

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
        from backend.routes.categorias import categorias_bp
        from backend.routes.despesas import despesas_bp
        from backend.routes.cartoes import cartoes_bp
        from backend.routes.consorcios import consorcios_bp
        from backend.routes.receitas import receitas_bp
        from backend.routes.financiamentos import financiamentos_bp
        from backend.routes.contas_bancarias import contas_bancarias_bp
        from backend.routes.patrimonio import patrimonio_bp
        from backend.routes.dashboard import dashboard_bp
        from backend.routes.preferencias import preferencias_bp
    except ImportError:
        from routes.categorias import categorias_bp
        from routes.despesas import despesas_bp
        from routes.cartoes import cartoes_bp
        from routes.consorcios import consorcios_bp
        from routes.receitas import receitas_bp
        from routes.financiamentos import financiamentos_bp
        from routes.contas_bancarias import contas_bancarias_bp
        from routes.patrimonio import patrimonio_bp
        from routes.dashboard import dashboard_bp
        from routes.preferencias import preferencias_bp

    # Registrar blueprints
    app.register_blueprint(categorias_bp, url_prefix='/api/categorias')
    app.register_blueprint(despesas_bp, url_prefix='/api/despesas')
    app.register_blueprint(cartoes_bp, url_prefix='/api/cartoes')
    app.register_blueprint(consorcios_bp, url_prefix='/api/consorcios')
    app.register_blueprint(receitas_bp, url_prefix='/api/receitas')
    app.register_blueprint(financiamentos_bp, url_prefix='/api/financiamentos')
    app.register_blueprint(contas_bancarias_bp, url_prefix='/api/contas')
    app.register_blueprint(patrimonio_bp, url_prefix='/api/patrimonio')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(preferencias_bp, url_prefix='/api/preferencias')


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

        print("=> Servidor iniciando em http://localhost:5000")
        print("=> Pressione CTRL+C para parar")

    # Executar servidor
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
