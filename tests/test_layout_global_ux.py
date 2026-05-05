import pytest

from backend.app import create_app
from backend.models import db
from backend.services.perfil_financeiro_service import PerfilFinanceiroService


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


MAIN_PAGES = [
    "/",
    "/despesas",
    "/receitas",
    "/lancamentos",
    "/recorrencias",
    "/contas-bancarias",
    "/cartoes",
    "/categorias",
    "/financiamentos",
    "/patrimonio",
    "/veiculos",
    "/importar-cartao",
    "/imposto-renda",
    "/configuracoes",
    "/ajuda",
]


@pytest.mark.parametrize("path", MAIN_PAGES)
def test_paginas_principais_renderizam_com_moldura_global(client, path):
    response = client.get(path)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="app-topbar"' in html
    assert 'class="app-page-frame"' in html


def test_topbar_contem_manual_perfil_e_sino_na_ordem_aprovada(client):
    html = client.get("/").get_data(as_text=True)

    manual_index = html.index('aria-label="Ajuda e Manual"')
    perfil_index = html.index('id="perfil-financeiro-switcher"')
    sino_index = html.index('aria-label="Alertas"')

    assert manual_index < perfil_index < sino_index


def test_actionbar_e_conteudo_compartilham_shell_global(client):
    html = client.get("/imposto-renda").get_data(as_text=True)

    assert 'class="app-actionbar-region"' in html
    assert 'class="module-actionbar ir-actionbar"' in html
    assert 'class="app-page-frame"' in html
    assert html.index('class="app-actionbar-region"') < html.index('class="app-page-frame"')


def test_base_contem_botao_manual_seletor_perfil_e_sino(client):
    html = client.get("/ajuda").get_data(as_text=True)

    assert 'href="/ajuda"' in html
    assert 'title="Ajuda e Manual"' in html
    assert 'perfil-financeiro-switcher' in html
    assert 'aria-label="Alertas"' in html


def test_preferencias_continua_tratada(client):
    response = client.get("/preferencias")

    assert response.status_code in {301, 302, 308}
    assert response.headers["Location"].endswith("/configuracoes#preferencias-gerais")


def test_layout_css_define_largura_actionbar_e_frame_global():
    css = open("frontend/static/css/layout.css", encoding="utf-8").read()

    assert "--app-page-max-width: 1680px" in css
    assert ".app-page-frame" in css
    assert "flex-wrap: nowrap" in css
    assert "overflow-x: auto" in css
