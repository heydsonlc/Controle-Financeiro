from pathlib import Path

import pytest
from flask import Flask

from backend.models import (
    db,
    CartaoCategoriaLimite,
    CategoriaCartao,
    ConfigAgregador,
    ItemDespesa,
)
from backend.routes.dashboard import dashboard_bp
from backend.services.perfil_financeiro_service import PERFIL_SESSION_KEY, PerfilFinanceiroService


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS = ROOT / 'frontend' / 'static' / 'js' / 'dashboard.js'
DASHBOARD_CSS = ROOT / 'frontend' / 'static' / 'css' / 'dashboard.css'
INDEX_HTML = ROOT / 'frontend' / 'templates' / 'index.html'
IMG_DIR = ROOT / 'frontend' / 'static' / 'img'


@pytest.fixture()
def app_context():
    app = Flask(
        __name__,
        template_folder=str(ROOT / 'frontend' / 'templates'),
        static_folder=str(ROOT / 'frontend' / 'static'),
    )
    app.config.update(
        TESTING=True,
        SECRET_KEY='dashboard-refinamentos',
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')

    with app.app_context():
        db.create_all()
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _read(path):
    return path.read_text(encoding='utf-8')


def test_cartoes_e_limites_tem_estrutura_de_bandeira():
    js = _read(DASHBOARD_JS)
    css = _read(DASHBOARD_CSS)

    assert 'renderBandeiraCartao(cartao)' in js
    assert 'card-brand' in js
    assert '.card-brand' in css
    assert '.card-name-main' in css


def test_visa_mastercard_elo_resolvem_por_assets_locais_ou_fallback():
    js = _read(DASHBOARD_JS)
    assets = [
        'logo_bandeira_cartao_visa.png',
        'logo_marterCard.png',
        'elo.png',
    ]

    for asset in assets:
        assert asset in js
        assert (IMG_DIR / asset).exists()

    assert 'card-brand--fallback' in js
    assert 'http://' not in js
    assert 'https://' not in js


def test_consumo_categoria_cartao_renderiza_icone_proprio():
    js = _read(DASHBOARD_JS)
    css = _read(DASHBOARD_CSS)

    assert 'CategoriaCartaoIconesUI.renderIconeCategoriaCartao' in js
    assert 'dashboard-categoria-cartao-icon' in js
    assert '.dashboard-categoria-cartao-icon' in css
    assert 'renderCategoryVisual' not in js[js.index('function renderCategoriasCartao'):js.index('function renderProximosVencimentos')]


def test_linha_total_do_consumo_nao_recebe_icone():
    js = _read(DASHBOARD_JS)
    trecho = js[js.index('category-total-row') - 180:js.index('category-total-row') + 260]

    assert 'category-total-row' in trecho
    assert 'dashboard-categoria-cartao-icon' not in trecho


def test_resumo_mobilidade_limita_dois_cenarios():
    js = _read(DASHBOARD_JS)

    assert 'function montarCenariosMobilidade' in js
    assert 'modalidades.slice(0, 2)' in js
    assert 'return cenarios.slice(0, 2)' in js


def test_links_auxiliares_usam_classe_global_do_dashboard():
    html = _read(INDEX_HTML)
    css = _read(DASHBOARD_CSS)

    assert html.count('dashboard-card__footer-link') >= 5  # painel mobilidade removido
    assert '.dashboard-card__footer-link' in css
    assert 'align-self: flex-end' in css
    assert 'margin-top: auto' in css


def test_dashboard_nao_usa_url_externa_para_assets():
    conteudo = _read(DASHBOARD_JS) + _read(INDEX_HTML)

    assert 'http://' not in conteudo
    assert 'https://' not in conteudo


def test_dashboard_continua_respeitando_perfil_ativo(app_context):
    with app_context.app_context():
        perfis = PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        pessoal = next(perfil for perfil in perfis if perfil.nome == 'Pessoal')
        empresa = next(perfil for perfil in perfis if perfil.nome == 'Empresa')
        pessoal_id = pessoal.id
        empresa_id = empresa.id

        cat_pessoal = CategoriaCartao(nome='Pessoal Card', icone='mobilidade', perfil_financeiro_id=pessoal_id, ativo=True)
        cat_empresa = CategoriaCartao(nome='Empresa Card', icone='supermercado', perfil_financeiro_id=empresa_id, ativo=True)
        cartao_pessoal = ItemDespesa(nome='Visa Pessoal', tipo='Agregador', perfil_financeiro_id=pessoal_id, ativo=True, recorrente=True)
        cartao_empresa = ItemDespesa(nome='Elo Empresa', tipo='Agregador', perfil_financeiro_id=empresa_id, ativo=True, recorrente=True)
        db.session.add_all([cat_pessoal, cat_empresa, cartao_pessoal, cartao_empresa])
        db.session.flush()
        db.session.add_all([
            ConfigAgregador(item_despesa_id=cartao_pessoal.id, dia_fechamento=25, dia_vencimento=10, numero_cartao='1111222233334444'),
            ConfigAgregador(item_despesa_id=cartao_empresa.id, dia_fechamento=25, dia_vencimento=10, numero_cartao='5555666677778888'),
            CartaoCategoriaLimite(cartao_id=cartao_pessoal.id, categoria_cartao_id=cat_pessoal.id, limite_mensal=500, perfil_financeiro_id=pessoal_id, ativo=True),
            CartaoCategoriaLimite(cartao_id=cartao_empresa.id, categoria_cartao_id=cat_empresa.id, limite_mensal=900, perfil_financeiro_id=empresa_id, ativo=True),
        ])
        db.session.commit()

    with app_context.test_client() as client:
        with client.session_transaction() as sess:
            sess[PERFIL_SESSION_KEY] = pessoal_id
        pessoal_data = client.get('/api/dashboard/resumo').get_json()['data']

        with client.session_transaction() as sess:
            sess[PERFIL_SESSION_KEY] = empresa_id
        empresa_data = client.get('/api/dashboard/resumo').get_json()['data']

    assert [item['nome'] for item in pessoal_data['cartoes_limites']['itens']] == ['Visa Pessoal']
    assert [item['nome'] for item in empresa_data['cartoes_limites']['itens']] == ['Elo Empresa']
    assert pessoal_data['categorias_cartao'][0]['nome'] == 'Pessoal Card'
    assert empresa_data['categorias_cartao'][0]['nome'] == 'Empresa Card'
