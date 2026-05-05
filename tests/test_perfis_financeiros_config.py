import pytest

from backend.app import create_app
from backend.models import Categoria, PerfilFinanceiro, db
from backend.services.perfil_financeiro_service import PerfilFinanceiroService


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
    return app.test_client()


def _perfil(client, nome):
    perfis = client.get('/api/perfis-financeiros/config').get_json()['perfis']
    return next(perfil for perfil in perfis if perfil['nome'] == nome)


def test_config_retorna_ativos_e_inativos(client):
    client.get('/api/perfis-financeiros')
    empresa = _perfil(client, 'Empresa')
    response = client.post(f"/api/perfis-financeiros/{empresa['id']}/inativar")

    config = client.get('/api/perfis-financeiros/config')
    nomes = {perfil['nome']: perfil for perfil in config.get_json()['perfis']}

    assert response.status_code == 200
    assert config.status_code == 200
    assert nomes['Pessoal']['ativo'] is True
    assert nomes['Empresa']['ativo'] is False


def test_criar_e_editar_perfil_financeiro(client):
    criado = client.post('/api/perfis-financeiros', json={
        'nome': 'Investimentos',
        'tipo': 'OUTRO',
        'documento': 'CTX-01',
        'cor': '#7c3aed',
        'avatar': 'IV',
        'ativo': True,
    })
    perfil_id = criado.get_json()['perfil']['id']

    editado = client.put(f'/api/perfis-financeiros/{perfil_id}', json={
        'nome': 'Holding',
        'tipo': 'EMPRESA',
        'documento': '12.345.678/0001-00',
        'cor': '#0f766e',
        'avatar': 'HO',
        'ativo': True,
    })

    data = editado.get_json()['perfil']
    assert criado.status_code == 201
    assert editado.status_code == 200
    assert data['nome'] == 'Holding'
    assert data['tipo'] == 'EMPRESA'
    assert data['documento'] == '12.345.678/0001-00'
    assert data['cor'] == '#0f766e'


def test_inativar_reativar_e_topbar_nao_lista_inativos(client):
    empresa = _perfil(client, 'Empresa')

    inativado = client.post(f"/api/perfis-financeiros/{empresa['id']}/inativar")
    topbar = client.get('/api/perfis-financeiros').get_json()['perfis']
    reativado = client.post(f"/api/perfis-financeiros/{empresa['id']}/reativar")

    assert inativado.status_code == 200
    assert 'Empresa' not in {perfil['nome'] for perfil in topbar}
    assert reativado.status_code == 200
    assert reativado.get_json()['perfil']['ativo'] is True


def test_definir_perfil_padrao_mantem_apenas_um_padrao(client):
    empresa = _perfil(client, 'Empresa')
    response = client.post(f"/api/perfis-financeiros/{empresa['id']}/padrao")

    perfis = client.get('/api/perfis-financeiros/config').get_json()['perfis']
    padroes = [perfil for perfil in perfis if perfil['padrao']]

    assert response.status_code == 200
    assert len(padroes) == 1
    assert padroes[0]['nome'] == 'Empresa'


def test_nao_permite_trocar_para_perfil_inativo(client):
    empresa = _perfil(client, 'Empresa')
    client.post(f"/api/perfis-financeiros/{empresa['id']}/inativar")

    response = client.post('/api/perfis-financeiros/ativo', json={'perfil_id': empresa['id']})

    assert response.status_code == 404
    assert response.get_json()['code'] == 'PERFIL_FINANCEIRO_INVALIDO'


def test_nao_deixa_sistema_sem_perfil_ativo(client):
    empresa = _perfil(client, 'Empresa')
    client.post(f"/api/perfis-financeiros/{empresa['id']}/inativar")
    pessoal = _perfil(client, 'Pessoal')

    response = client.post(f"/api/perfis-financeiros/{pessoal['id']}/inativar")

    assert response.status_code == 400
    assert 'unico perfil ativo' in response.get_json()['error']


def test_bloqueia_inativar_perfil_ativo(client):
    empresa = _perfil(client, 'Empresa')
    client.post('/api/perfis-financeiros/ativo', json={'perfil_id': empresa['id']})

    response = client.post(f"/api/perfis-financeiros/{empresa['id']}/inativar")

    assert response.status_code == 400
    assert 'Selecione outro perfil' in response.get_json()['error']


def test_perfil_padrao_usado_quando_sessao_vazia(app):
    with app.app_context():
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        empresa = PerfilFinanceiro.query.filter_by(nome='Empresa').first()
        PerfilFinanceiroService.definir_perfil_padrao(empresa.id)
        db.session.commit()

    with app.test_client() as client:
        response = client.get('/api/perfis-financeiros/ativo')

    assert response.status_code == 200
    assert response.get_json()['perfil_ativo']['nome'] == 'Empresa'


def test_inativar_perfil_nao_apaga_dados_financeiros(client, app):
    with app.app_context():
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        empresa = PerfilFinanceiro.query.filter_by(nome='Empresa').first()
        categoria = Categoria(nome='Empresa Categoria', ativo=True, perfil_financeiro_id=empresa.id)
        db.session.add(categoria)
        db.session.commit()
        categoria_id = categoria.id
        empresa_id = empresa.id

    response = client.post(f'/api/perfis-financeiros/{empresa_id}/inativar')

    with app.app_context():
        categoria = Categoria.query.get(categoria_id)

    assert response.status_code == 200
    assert categoria is not None
    assert categoria.perfil_financeiro_id == empresa_id
