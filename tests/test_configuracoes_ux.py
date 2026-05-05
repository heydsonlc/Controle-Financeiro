import pytest

from backend.app import create_app
from backend.models import db
from backend.services.perfil_financeiro_service import PerfilFinanceiroService


@pytest.fixture()
def app():
    app = create_app('testing')
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


def test_configuracoes_renderiza_central_unificada(client):
    response = client.get('/configuracoes')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'Configurações e Preferências' in html
    assert 'config-shell' in html
    assert 'Perfis Financeiros' in html
    assert 'Preferências Gerais' in html
    assert 'Documentos Fiscais' in html


def test_configuracoes_contem_menu_formulario_e_painel_ajuda(client):
    html = client.get('/configuracoes').get_data(as_text=True)

    assert 'data-config-section-target="perfis-financeiros"' in html
    assert 'data-config-section-target="preferencias-gerais"' in html
    assert 'id="config-profile-form"' in html
    assert 'id="config-profile-nome"' in html
    assert 'id="config-profile-save"' in html
    assert 'id="config-help-content"' in html


def test_configuracoes_contem_preferencias_antigas_preservadas(client):
    html = client.get('/configuracoes').get_data(as_text=True)

    assert 'id="nome_usuario"' in html
    assert 'id="renda_principal"' in html
    assert 'id="mes_inicio_planejamento"' in html
    assert 'id="dia_fechamento_mes"' in html
    assert 'id="cor_principal"' in html
    assert 'id="ajustar_competencia_automatico"' in html


def test_api_de_perfis_consumivel_pela_tela(client):
    response = client.get('/api/perfis-financeiros/config')
    data = response.get_json()

    assert response.status_code == 200
    assert {'Pessoal', 'Empresa'}.issubset({perfil['nome'] for perfil in data['perfis']})
    assert data['perfil_ativo']['nome'] == 'Pessoal'


def test_preferencias_redireciona_para_secao_da_central(client):
    response = client.get('/preferencias')

    assert response.status_code in {301, 302, 308}
    assert response.headers['Location'].endswith('/configuracoes#preferencias-gerais')


def test_botoes_placeholders_e_topbar_continuam_presentes(client):
    html = client.get('/configuracoes').get_data(as_text=True)

    assert 'data-config-placeholder="Importar configurações"' in html
    assert 'data-config-placeholder="Exportar configurações"' in html
    assert 'perfil-financeiro-switcher' in html
    assert 'contexto_financeiro.js' in html
    assert 'configuracoes.js' in html
