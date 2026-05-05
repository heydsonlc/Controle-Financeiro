import pytest

from backend.app import create_app
from backend.models import (
    Categoria,
    CategoriaCartao,
    CategoriaCartaoDespesa,
    Conta,
    ContaBancaria,
    ItemDespesa,
    ItemReceita,
    LancamentoAgregado,
    PerfilFinanceiro,
    ReceitaRealizada,
    db,
)
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


def _perfis(client):
    return client.get('/api/perfis-financeiros').get_json()['perfis']


def _perfil(client, nome):
    return next(perfil for perfil in _perfis(client) if perfil['nome'] == nome)


def _trocar_perfil(client, nome):
    perfil = _perfil(client, nome)
    response = client.post('/api/perfis-financeiros/ativo', json={'perfil_id': perfil['id']})
    assert response.status_code == 200
    assert response.get_json()['perfil_ativo']['nome'] == nome
    return perfil


def _criar_categoria(client, nome):
    response = client.post('/api/categorias', json={
        'nome': nome,
        'descricao': f'{nome} descricao',
        'cor': '#2563eb',
        'icone': 'tag',
        'ativo': True,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()['data']


def _criar_categoria_cartao(client, nome):
    response = client.post('/api/categorias-cartao', json={
        'nome': nome,
        'descricao': f'{nome} descricao',
        'cor': '#0ea5e9',
        'icone': 'credit-card',
        'ativo': True,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()['data']


def _nomes(response):
    data = response.get_json()
    itens = data if isinstance(data, list) else data.get('data', [])
    return {item['nome'] for item in itens}


def test_categoria_criada_em_um_perfil_nao_aparece_no_outro(client):
    pessoal = _perfil(client, 'Pessoal')
    categoria_pessoal = _criar_categoria(client, 'Alimentacao CTX')

    _trocar_perfil(client, 'Empresa')
    assert 'Alimentacao CTX' not in _nomes(client.get('/api/categorias'))

    categoria_empresa = _criar_categoria(client, 'Alimentacao CTX')
    assert categoria_empresa['id'] != categoria_pessoal['id']

    with client.session_transaction() as sess:
        sess['perfil_financeiro_id'] = pessoal['id']

    response = client.get(f"/api/categorias/{categoria_empresa['id']}")
    assert response.status_code == 404
    assert 'Alimentacao CTX' in _nomes(client.get('/api/categorias'))


def test_conta_cartao_receita_despesa_e_recorrencia_sao_isolados_por_perfil(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    categoria = _criar_categoria(client, 'Empresa Operacional')

    conta_resp = client.post('/api/contas', json={
        'nome': 'Conta Empresa CTX',
        'instituicao': 'Banco Inter',
        'tipo': 'Conta Corrente',
        'saldo_inicial': 1000,
    })
    assert conta_resp.status_code == 201, conta_resp.get_data(as_text=True)
    conta = conta_resp.get_json()['data']

    cartao_resp = client.post('/api/cartoes', json={
        'nome': 'Cartao Empresa CTX',
        'categoria_id': categoria['id'],
        'dia_fechamento': 20,
        'dia_vencimento': 10,
        'limite_credito': 5000,
    })
    assert cartao_resp.status_code == 201, cartao_resp.get_data(as_text=True)
    cartao = cartao_resp.get_json()

    receita_resp = client.post('/api/receitas/itens', json={
        'nome': 'Receita Empresa CTX',
        'tipo': 'RENDA_EXTRA',
        'valor_base_mensal': 1200,
        'recorrente': False,
    })
    assert receita_resp.status_code == 201, receita_resp.get_data(as_text=True)
    receita = receita_resp.get_json()['data']

    despesa_resp = client.post('/api/despesas/', json={
        'nome': 'Despesa Empresa CTX',
        'valor': 180,
        'categoria_id': categoria['id'],
        'data_vencimento': '2026-05-10',
        'recorrente': False,
    })
    assert despesa_resp.status_code == 201, despesa_resp.get_data(as_text=True)
    despesa = despesa_resp.get_json()['data']

    recorrencia_resp = client.post('/api/recorrencias', json={
        'nome': 'Recorrencia Empresa CTX',
        'valor': 90,
        'categoria_id': categoria['id'],
        'data_vencimento': '2026-05-15',
        'frequencia': 'mensal',
    })
    assert recorrencia_resp.status_code == 201, recorrencia_resp.get_data(as_text=True)
    recorrencia = recorrencia_resp.get_json()['data']

    _trocar_perfil(client, 'Pessoal')

    assert 'Conta Empresa CTX' not in _nomes(client.get('/api/contas'))
    assert 'Cartao Empresa CTX' not in _nomes(client.get('/api/cartoes'))
    assert 'Receita Empresa CTX' not in _nomes(client.get('/api/receitas/itens'))
    assert 'Recorrencia Empresa CTX' not in _nomes(client.get('/api/recorrencias'))
    assert 'Despesa Empresa CTX' not in {
        item['nome'] for item in client.get('/api/despesas/').get_json().get('data', [])
    }

    assert client.get(f"/api/contas/{conta['id']}").status_code == 404
    assert client.get(f"/api/cartoes/{cartao['id']}").status_code == 404
    assert client.get(f"/api/receitas/itens/{receita['id']}").status_code == 404
    assert client.get(f"/api/despesas/{despesa['id']}").status_code == 404
    assert client.get(f"/api/recorrencias/{recorrencia['id']}").status_code == 404

    with app.app_context():
        perfil_id = empresa['id']
        assert ContaBancaria.query.get(conta['id']).perfil_financeiro_id == perfil_id
        assert ItemDespesa.query.get(cartao['id']).perfil_financeiro_id == perfil_id
        assert ItemReceita.query.get(receita['id']).perfil_financeiro_id == perfil_id


def test_vinculo_categoria_cartao_nao_permite_cruzar_perfis(client, app):
    categoria_pessoal = _criar_categoria(client, 'Categoria Pessoal CTX')

    _trocar_perfil(client, 'Empresa')
    categoria_cartao_empresa = _criar_categoria_cartao(client, 'Categoria Cartao Empresa CTX')

    response = client.post(
        f"/api/categorias-cartao/{categoria_cartao_empresa['id']}/despesas",
        json={'categoria_id': categoria_pessoal['id']},
    )

    assert response.status_code == 400
    assert response.get_json()['success'] is False
    with app.app_context():
        assert CategoriaCartaoDespesa.query.count() == 0


def test_lancamento_de_cartao_e_fatura_nao_vazam_entre_perfis(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    categoria = _criar_categoria(client, 'Cartao Despesa Empresa CTX')
    categoria_cartao = _criar_categoria_cartao(client, 'Categoria Fatura Empresa CTX')
    vinculo = client.post(
        f"/api/categorias-cartao/{categoria_cartao['id']}/despesas",
        json={'categoria_id': categoria['id']},
    )
    assert vinculo.status_code in (200, 201), vinculo.get_data(as_text=True)

    cartao_resp = client.post('/api/cartoes', json={
        'nome': 'Cartao Lancamento Empresa CTX',
        'categoria_id': categoria['id'],
        'dia_fechamento': 20,
        'dia_vencimento': 10,
    })
    assert cartao_resp.status_code == 201, cartao_resp.get_data(as_text=True)
    cartao = cartao_resp.get_json()

    lancamento_resp = client.post(f"/api/cartoes/{cartao['id']}/lancamentos", json={
        'descricao': 'Compra Empresa CTX',
        'valor': 250,
        'categoria_id': categoria['id'],
        'categoria_cartao_id': categoria_cartao['id'],
        'data_compra': '2026-05-03',
        'mes_fatura': '2026-05',
    })
    assert lancamento_resp.status_code == 201, lancamento_resp.get_data(as_text=True)
    lancamento = lancamento_resp.get_json()['lancamento']

    assert 'Compra Empresa CTX' in {
        item['descricao'] for item in client.get(f"/api/cartoes/{cartao['id']}/lancamentos").get_json()
    }

    _trocar_perfil(client, 'Pessoal')
    assert client.get(f"/api/cartoes/{cartao['id']}/lancamentos").status_code == 404

    with app.app_context():
        assert LancamentoAgregado.query.get(lancamento['id']).perfil_financeiro_id == empresa['id']
        assert Conta.query.filter_by(item_despesa_id=cartao['id']).first().perfil_financeiro_id == empresa['id']


def test_backfill_migration_conceitual_atribui_registros_existentes_ao_pessoal(app):
    with app.app_context():
        pessoal = PerfilFinanceiro.query.filter_by(nome='Pessoal').first()
        categoria = Categoria(nome='Sem Perfil Antigo', cor='#64748b', ativo=True)
        db.session.add(categoria)
        db.session.commit()

        assert categoria.perfil_financeiro_id is None

        Categoria.query.filter(Categoria.perfil_financeiro_id.is_(None)).update({
            'perfil_financeiro_id': pessoal.id
        })
        db.session.commit()

        assert Categoria.query.get(categoria.id).perfil_financeiro_id == pessoal.id
