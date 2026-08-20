"""
Testes CAT-GLOBAL-2: Categoria de Despesa é global (compartilhada entre perfis).
CategoriaCartao continua isolada por perfil.
"""
import pytest

from backend.app import create_app
from backend.models import (
    Categoria,
    CategoriaCartao,
    CategoriaCartaoDespesa,
    db,
)
from backend.services.perfil_financeiro_service import PerfilFinanceiroService
from backend.services.categoria_palavra_chave_service import CategoriaPalavraChaveService
from tests.conftest import autenticar_cliente_teste


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
    return autenticar_cliente_teste(app.test_client(), app)


def _perfis(client):
    return client.get('/api/perfis-financeiros').get_json()['perfis']


def _perfil(client, nome):
    return next(p for p in _perfis(client) if p['nome'] == nome)


def _trocar_perfil(client, nome):
    perfil = _perfil(client, nome)
    r = client.post('/api/perfis-financeiros/ativo', json={'perfil_id': perfil['id']})
    assert r.status_code == 200
    return perfil


def _criar_categoria(client, nome, **kwargs):
    payload = {'nome': nome, 'cor': '#2563eb', 'ativo': True}
    payload.update(kwargs)
    r = client.post('/api/categorias', json=payload)
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()['data']


def _criar_categoria_cartao(client, nome):
    r = client.post('/api/categorias-cartao', json={
        'nome': nome, 'cor': '#0ea5e9', 'ativo': True,
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()['data']


def _nomes_categorias(client):
    data = client.get('/api/categorias').get_json()
    itens = data if isinstance(data, list) else data.get('data', [])
    return {item['nome'] for item in itens}


def _nomes_categorias_cartao(client):
    data = client.get('/api/categorias-cartao').get_json()
    itens = data if isinstance(data, list) else data.get('data', [])
    return {item['nome'] for item in itens}


# ---------------------------------------------------------------------------
# Globalidade de Categoria de Despesa
# ---------------------------------------------------------------------------

def test_categoria_criada_em_pessoal_aparece_no_perfil_empresa(client):
    _trocar_perfil(client, 'Pessoal')
    _criar_categoria(client, 'Alimentacao Global')

    _trocar_perfil(client, 'Empresa')
    assert 'Alimentacao Global' in _nomes_categorias(client)


def test_categoria_criada_em_empresa_aparece_no_perfil_pessoal(client):
    _trocar_perfil(client, 'Empresa')
    _criar_categoria(client, 'Operacional Global')

    _trocar_perfil(client, 'Pessoal')
    assert 'Operacional Global' in _nomes_categorias(client)


def test_nome_de_categoria_despesa_e_unico_global(client):
    _trocar_perfil(client, 'Pessoal')
    _criar_categoria(client, 'Unica Global')

    _trocar_perfil(client, 'Empresa')
    dup = client.post('/api/categorias', json={'nome': 'Unica Global', 'cor': '#abc'})
    assert dup.status_code == 400


def test_endpoint_categoria_despesa_nao_filtra_por_perfil(client):
    _trocar_perfil(client, 'Pessoal')
    cat = _criar_categoria(client, 'Cat Detalhe Global')

    _trocar_perfil(client, 'Empresa')
    r = client.get(f"/api/categorias/{cat['id']}")
    assert r.status_code == 200
    assert r.get_json()['data']['nome'] == 'Cat Detalhe Global'


# ---------------------------------------------------------------------------
# CategoriaCartao continua isolada por perfil
# ---------------------------------------------------------------------------

def test_categoria_cartao_criada_em_pessoal_nao_aparece_na_empresa(client):
    _trocar_perfil(client, 'Pessoal')
    _criar_categoria_cartao(client, 'Lazer Pessoal')

    _trocar_perfil(client, 'Empresa')
    assert 'Lazer Pessoal' not in _nomes_categorias_cartao(client)


def test_endpoint_categoria_cartao_continua_filtrando_por_perfil(client):
    _trocar_perfil(client, 'Pessoal')
    _criar_categoria_cartao(client, 'Saude Pessoal')

    _trocar_perfil(client, 'Empresa')
    # CategoriaCartao criada no perfil Pessoal não aparece na listagem do perfil Empresa
    assert 'Saude Pessoal' not in _nomes_categorias_cartao(client)


# ---------------------------------------------------------------------------
# Vinculo CategoriaCartao ↔ Categoria de Despesa respeita perfil do cartão
# ---------------------------------------------------------------------------

def test_mesma_categoria_despesa_global_vincula_categoria_cartao_diferente_em_cada_perfil(client, app):
    cat_desp = _criar_categoria(client, 'Transporte Global')

    _trocar_perfil(client, 'Pessoal')
    cat_cartao_pessoal = _criar_categoria_cartao(client, 'Cartao Transporte Pessoal')
    r1 = client.post(
        f"/api/categorias-cartao/{cat_cartao_pessoal['id']}/despesas",
        json={'categoria_id': cat_desp['id']},
    )
    assert r1.status_code in (200, 201), r1.get_data(as_text=True)

    _trocar_perfil(client, 'Empresa')
    cat_cartao_empresa = _criar_categoria_cartao(client, 'Cartao Transporte Empresa')
    r2 = client.post(
        f"/api/categorias-cartao/{cat_cartao_empresa['id']}/despesas",
        json={'categoria_id': cat_desp['id']},
    )
    assert r2.status_code in (200, 201), r2.get_data(as_text=True)

    with app.app_context():
        vinculos = CategoriaCartaoDespesa.query.filter_by(categoria_id=cat_desp['id']).all()
        assert len(vinculos) == 2
        perfis = {v.categoria_cartao.perfil_financeiro_id for v in vinculos}
        assert len(perfis) == 2


# ---------------------------------------------------------------------------
# Palavras-chave globais
# ---------------------------------------------------------------------------

def test_palavras_chave_de_categoria_despesa_sao_globais(client, app):
    _trocar_perfil(client, 'Pessoal')
    cat = _criar_categoria(client, 'Supermercado Global')

    r = client.post(f"/api/categorias/{cat['id']}/palavras-chave", json={'palavra': 'mercado'})
    assert r.status_code == 201, r.get_data(as_text=True)

    _trocar_perfil(client, 'Empresa')
    with app.app_context():
        resultado = CategoriaPalavraChaveService.classificar_por_palavras_chave('compra mercado central')
    assert resultado['categoria_id'] == cat['id']
    assert resultado['origem'] == 'palavra_chave'


def test_importacao_por_palavra_chave_funciona_independente_do_perfil(client, app):
    _trocar_perfil(client, 'Empresa')
    cat = _criar_categoria(client, 'Farmacia Global')

    rp = client.post(f"/api/categorias/{cat['id']}/palavras-chave", json={'palavra': 'drogaria'})
    assert rp.status_code == 201, rp.get_data(as_text=True)

    _trocar_perfil(client, 'Pessoal')
    with app.app_context():
        resultado = CategoriaPalavraChaveService.classificar_por_palavras_chave('pagamento drogaria central')
    assert resultado['categoria_id'] == cat['id']
    assert resultado['ambigua'] is False
