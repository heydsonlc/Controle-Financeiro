import pytest

from backend.app import create_app
from backend.models import db
from tests.conftest import autenticar_cliente_teste


@pytest.fixture()
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return autenticar_cliente_teste(app.test_client(), app)


def test_ajuda_renderiza(client):
    response = client.get('/ajuda')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'Central de Ajuda e Manual de Uso' in html
    assert 'help-shell' in html


def test_menu_lateral_contem_ajuda_e_manual(client):
    html = client.get('/ajuda').get_data(as_text=True)

    assert 'Ajuda e Manual' in html
    assert 'active_page == &#39;ajuda&#39;' not in html
    assert 'href="/ajuda"' in html


def test_tela_contem_busca_cards_e_navegacao(client):
    html = client.get('/ajuda').get_data(as_text=True)

    assert 'Buscar no manual' in html
    assert 'Comece por aqui' in html
    assert 'Conceitos essenciais' in html
    assert 'Navegação do Manual' in html
    assert 'help-nav-list' in html


def test_artigo_categoria_cartao_existe_no_js():
    js = open('frontend/static/js/ajuda.js', encoding='utf-8').read()

    assert 'Categoria do Cartão: projeção, realizado e limites' in js
    assert 'Categoria de Despesa' in js
    assert 'Categoria do Cartão' in js
    assert 'Lançamentos sem Categoria do Cartão' in js


def test_videos_faq_e_ultimos_acessos_existem(client):
    html = client.get('/ajuda').get_data(as_text=True)
    js = open('frontend/static/js/ajuda.js', encoding='utf-8').read()

    assert 'Vídeos rápidos' in html
    assert 'Perguntas frequentes' in html
    assert 'Últimos acessos' in html
    assert 'Entendendo a Categoria do Cartão' in js
    assert 'Vídeo demonstrativo será disponibilizado em etapa futura.' in html


def test_topbar_ou_menu_manual_existe(client):
    html = client.get('/').get_data(as_text=True)

    assert 'aria-label="Ajuda e Manual"' in html
    assert 'Ajuda e Manual' in html


def test_manual_redireciona_para_ajuda(client):
    response = client.get('/manual')

    assert response.status_code in {301, 302, 308}
    assert response.headers['Location'].endswith('/ajuda')


def test_nao_ha_dependencia_externa_para_videos():
    html = open('frontend/templates/ajuda.html', encoding='utf-8').read()
    js = open('frontend/static/js/ajuda.js', encoding='utf-8').read()

    assert 'youtube.com' not in html.lower()
    assert 'youtube.com' not in js.lower()
    assert 'http://' not in js.lower()
    assert 'https://' not in js.lower()
