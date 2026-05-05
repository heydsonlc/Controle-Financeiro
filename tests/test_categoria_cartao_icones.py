from datetime import date
from pathlib import Path

import pytest
from flask import Flask

from backend.models import (
    db,
    CartaoCategoriaLimite,
    Categoria,
    CategoriaCartao,
    ConfigAgregador,
    ItemDespesa,
    LancamentoAgregado,
)
from backend.routes.categorias import categorias_cartao_bp
from backend.routes.dashboard import dashboard_bp


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'frontend' / 'static' / 'js' / 'categoria_cartao_icones.js'
CATEGORIAS_JS = ROOT / 'frontend' / 'static' / 'js' / 'categorias.js'
DASHBOARD_JS = ROOT / 'frontend' / 'static' / 'js' / 'dashboard.js'
CATEGORIAS_HTML = ROOT / 'frontend' / 'templates' / 'categorias.html'
DASHBOARD_HTML = ROOT / 'frontend' / 'templates' / 'index.html'
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
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(categorias_cartao_bp, url_prefix='/api/categorias-cartao')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _read(path):
    return path.read_text(encoding='utf-8')


def test_helper_de_categoria_cartao_existe_e_usa_assets_locais():
    helper = _read(HELPER)

    assert 'window.CategoriaCartaoIconesUI' in helper
    assert 'listarIconesCategoriaCartao' in helper
    assert 'resolverIconeCategoriaCartao' in helper
    assert 'renderIconeCategoriaCartao' in helper
    assert '/static/img/' in helper
    assert 'http://' not in helper
    assert 'https://' not in helper


def test_arquivos_locais_de_categoria_cartao_estao_mapeados():
    helper = _read(HELPER)
    arquivos = [
        'categoria_cartao_educacao.jpg',
        'categoria_cartao_saude2.jpg',
        'categoria_cartão_farmácia.png',
        'categoria_cartão_inteligenciaArtificial.png',
        'categoria_cartão_mobilidade.png',
        'categoria_cartão_padaria.png',
        'categoria_cartão_saude.png',
        'categoria_cartão_supermercado.png',
        'categoria_cartão_verdurao.png',
    ]

    for arquivo in arquivos:
        assert arquivo in helper
        assert (IMG_DIR / arquivo).exists()


def test_categoria_de_despesa_continua_usando_catalogo_antigo():
    html = _read(CATEGORIAS_HTML)
    js = _read(CATEGORIAS_JS)

    assert 'icone-picker-grid' in html
    assert 'function montarSeletorIcones' in js
    assert 'getIconKeys()' in js
    assert 'renderIcon(key' in js


def test_categoria_do_cartao_usa_lista_propria_de_icones():
    js = _read(CATEGORIAS_JS)
    inicio = js.index('function montarOpcoesIconeCartao')
    fim = js.index('function montarGradeIconesCartao')
    corpo = js[inicio:fim]

    assert 'CategoriaCartaoIconesUI' in corpo
    assert 'listarIconesCategoriaCartao' in corpo
    assert 'getIconKeys' not in corpo
    assert 'cartao-icone-picker-grid' in js


def test_templates_carregam_helper_antes_dos_scripts_de_pagina():
    categorias_html = _read(CATEGORIAS_HTML)
    dashboard_html = _read(DASHBOARD_HTML)

    assert categorias_html.index('categoria_cartao_icones.js') < categorias_html.index('categorias.js')
    assert dashboard_html.index('categoria_cartao_icones.js') < dashboard_html.index('dashboard.js')


def test_categoria_cartao_salva_e_retorna_icone_selecionado(app_context):
    with app_context.test_client() as client:
        response = client.post('/api/categorias-cartao', json={
            'nome': 'Mobilidade',
            'cor': '#2563eb',
            'icone': 'mobilidade',
            'ativo': True,
        })

        assert response.status_code == 201
        assert response.get_json()['data']['icone'] == 'mobilidade'

        lista = client.get('/api/categorias-cartao')
        assert lista.status_code == 200
        assert lista.get_json()['data'][0]['icone'] == 'mobilidade'


def test_dashboard_payload_retorna_icone_da_categoria_do_cartao(app_context):
    categoria = Categoria(nome='Combustivel', icone='fuel', ativo=True)
    categoria_cartao = CategoriaCartao(nome='Mobilidade', cor='#2563eb', icone='mobilidade', ativo=True)
    cartao = ItemDespesa(nome='Cartao Teste', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add_all([categoria, categoria_cartao, cartao])
    db.session.flush()
    db.session.add(ConfigAgregador(item_despesa_id=cartao.id, dia_fechamento=25, dia_vencimento=10))
    db.session.add(CartaoCategoriaLimite(cartao_id=cartao.id, categoria_cartao_id=categoria_cartao.id, limite_mensal=1000, ativo=True))
    db.session.add(LancamentoAgregado(
        cartao_id=cartao.id,
        categoria_id=categoria.id,
        categoria_cartao_id=categoria_cartao.id,
        descricao='Posto Teste',
        valor=250,
        data_compra=date.today(),
        mes_fatura=date.today().replace(day=1),
    ))
    db.session.commit()

    with app_context.test_client() as client:
        response = client.get('/api/dashboard/resumo')

    item = response.get_json()['data']['categorias_cartao'][0]
    assert item['nome'] == 'Mobilidade'
    assert item['icone'] == 'mobilidade'


def test_dashboard_renderiza_icone_da_categoria_cartao_sem_icone_despesa():
    js = _read(DASHBOARD_JS)
    inicio = js.index('function renderCategoriasCartao')
    fim = js.index('function renderProximosVencimentos')
    corpo = js[inicio:fim]

    assert 'CategoriaCartaoIconesUI.renderIconeCategoriaCartao' in corpo
    assert 'renderCategoryVisual' not in corpo
    assert 'dashboard-categoria-cartao-icon' in corpo


def test_fallback_para_icone_ausente_esta_previsto():
    helper = _read(HELPER)

    assert 'categoria-cartao-default' in helper
    assert 'categoria-cartao-icon--fallback' in helper
    assert "renderIcon('credit-card'" in helper
