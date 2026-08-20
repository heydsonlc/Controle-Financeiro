import pytest

from backend.app import create_app
from backend.models import Categoria, PerfilFinanceiro, db
from backend.services.perfil_financeiro_service import PerfilFinanceiroService
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


def test_model_perfil_financeiro_cria_registro(app):
    with app.app_context():
        perfil = PerfilFinanceiro(nome='Teste', tipo='PESSOAL', cor='#2563eb', ativo=True)
        db.session.add(perfil)
        db.session.commit()

        assert perfil.id is not None
        assert perfil.to_dict()['nome'] == 'Teste'


def test_service_cria_perfis_iniciais_sem_duplicar(app):
    with app.app_context():
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()

        perfis = PerfilFinanceiro.query.order_by(PerfilFinanceiro.nome.asc()).all()
        nomes = [perfil.nome for perfil in perfis]

        assert nomes.count('Pessoal') == 1
        assert nomes.count('Empresa') == 1


def test_get_perfis_financeiros_retorna_lista_e_ativo(client):
    response = client.get('/api/perfis-financeiros')

    assert response.status_code == 200
    data = response.get_json()
    nomes = {perfil['nome'] for perfil in data['perfis']}

    assert {'Pessoal', 'Empresa'}.issubset(nomes)
    assert data['perfil_ativo']['nome'] == 'Pessoal'
    assert data['isolamento_dados_ativo'] is False


def test_get_perfil_ativo_retorna_pessoal_como_padrao(client):
    response = client.get('/api/perfis-financeiros/ativo')

    assert response.status_code == 200
    assert response.get_json()['perfil_ativo']['nome'] == 'Pessoal'


def test_post_troca_perfil_ativo_para_empresa_e_preserva_sessao(client):
    perfis = client.get('/api/perfis-financeiros').get_json()['perfis']
    empresa = next(perfil for perfil in perfis if perfil['nome'] == 'Empresa')

    response = client.post('/api/perfis-financeiros/ativo', json={'perfil_id': empresa['id']})
    assert response.status_code == 200
    assert response.get_json()['perfil_ativo']['nome'] == 'Empresa'

    ativo = client.get('/api/perfis-financeiros/ativo').get_json()['perfil_ativo']
    assert ativo['nome'] == 'Empresa'


def test_post_perfil_inexistente_retorna_erro_controlado(client):
    response = client.post('/api/perfis-financeiros/ativo', json={'perfil_id': 999999})

    assert response.status_code == 404
    assert response.get_json()['code'] == 'PERFIL_FINANCEIRO_INVALIDO'


def test_base_renderizada_contem_seletor_global(client):
    response = client.get('/')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'perfil-financeiro-switcher' in html
    assert 'contexto_financeiro.js' in html
    assert 'Configurar perfis' in html


def test_troca_de_perfil_nao_altera_dados_financeiros(client, app):
    with app.app_context():
        categoria = Categoria(nome='CTX Teste', descricao='controle', cor='#2563eb', ativo=True)
        db.session.add(categoria)
        db.session.commit()
        total_antes = Categoria.query.count()

    perfis = client.get('/api/perfis-financeiros').get_json()['perfis']
    empresa = next(perfil for perfil in perfis if perfil['nome'] == 'Empresa')
    response = client.post('/api/perfis-financeiros/ativo', json={'perfil_id': empresa['id']})

    with app.app_context():
        total_depois = Categoria.query.count()

    assert response.status_code == 200
    assert total_depois == total_antes
