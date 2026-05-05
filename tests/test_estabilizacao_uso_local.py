from datetime import date
from decimal import Decimal

import pytest

from backend.app import create_app
from backend.models import IrComprovante, db
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
    assert response.status_code == 200, response.get_data(as_text=True)
    return perfil


def _nomes(payload):
    return {item.get('nome') for item in payload.get('data', [])}


def _criar_comprovante(app, perfil_id):
    with app.app_context():
        comprovante = IrComprovante(
            perfil_financeiro_id=perfil_id,
            ano_calendario=2026,
            data_documento=date(2026, 5, 5),
            prestador_nome='Fornecedor Empresa ESTAB',
            prestador_cpf_cnpj='00000000000191',
            valor=Decimal('345.67'),
            status='VALIDADO',
            hash_arquivo='hash-estab-empresa-20260505',
            observacoes='Documento fiscal usado na estabilizacao local.',
        )
        db.session.add(comprovante)
        db.session.commit()
        return comprovante.id


def test_fluxos_centrais_respeitam_isolamento_apos_troca_de_perfil(client, app):
    empresa = _trocar_perfil(client, 'Empresa')

    categoria_empresa = client.post('/api/categorias', json={
        'nome': 'ESTAB Empresa Operacional',
        'descricao': 'Categoria criada na rodada de estabilizacao',
        'cor': '#2563eb',
    })
    assert categoria_empresa.status_code == 201, categoria_empresa.get_data(as_text=True)
    categoria_empresa_id = categoria_empresa.get_json()['data']['id']

    conta_empresa = client.post('/api/contas', json={
        'nome': 'ESTAB Conta Empresa',
        'instituicao': 'Banco Teste Empresa',
        'tipo': 'Conta Corrente',
        'saldo_inicial': 1000,
    })
    assert conta_empresa.status_code == 201, conta_empresa.get_data(as_text=True)
    conta_empresa_id = conta_empresa.get_json()['data']['id']

    despesa_empresa = client.post('/api/despesas/', json={
        'nome': 'ESTAB Despesa Empresa',
        'valor': 123.45,
        'categoria_id': categoria_empresa_id,
        'data_vencimento': '2026-05-20',
        'meio_pagamento': 'pix',
        'recorrente': False,
    })
    assert despesa_empresa.status_code == 201, despesa_empresa.get_data(as_text=True)

    bem_empresa = client.post('/api/patrimonio/bens', json={
        'nome': 'ESTAB Notebook Empresa',
        'codigo': 'ESTAB-NB-001',
        'categoria': 'Informatica',
        'data_aquisicao': '2026-05-05',
        'valor_aquisicao': 6490.0,
        'vida_util_meses': 36,
    })
    assert bem_empresa.status_code == 201, bem_empresa.get_data(as_text=True)
    bem_empresa_id = bem_empresa.get_json()['data']['id']

    comprovante_empresa_id = _criar_comprovante(app, empresa['id'])

    assert 'ESTAB Empresa Operacional' in _nomes(client.get('/api/categorias').get_json())
    assert 'ESTAB Conta Empresa' in _nomes(client.get('/api/contas').get_json())
    assert 'ESTAB Despesa Empresa' in _nomes(client.get('/api/despesas/').get_json())
    assert 'ESTAB Notebook Empresa' in _nomes(client.get('/api/patrimonio/bens').get_json())
    assert client.get('/api/ir/comprovantes?ano=2026').get_json()['total'] == 1

    _trocar_perfil(client, 'Pessoal')
    categoria_pessoal = client.post('/api/categorias', json={
        'nome': 'ESTAB Pessoal Residencial',
        'descricao': 'Categoria pessoal criada na rodada de estabilizacao',
        'cor': '#16a34a',
    })
    assert categoria_pessoal.status_code == 201, categoria_pessoal.get_data(as_text=True)

    categorias_pessoal = _nomes(client.get('/api/categorias').get_json())
    contas_pessoal = _nomes(client.get('/api/contas').get_json())
    despesas_pessoal = _nomes(client.get('/api/despesas/').get_json())

    assert 'ESTAB Pessoal Residencial' in categorias_pessoal
    assert 'ESTAB Empresa Operacional' not in categorias_pessoal
    assert 'ESTAB Conta Empresa' not in contas_pessoal
    assert 'ESTAB Despesa Empresa' not in despesas_pessoal
    assert client.get('/api/ir/comprovantes?ano=2026').get_json()['total'] == 0
    assert client.get(f'/api/ir/comprovantes/{comprovante_empresa_id}').status_code == 404
    assert client.get('/api/patrimonio/bens').get_json()['data'] == []
    assert client.get(f'/api/patrimonio/bens/{bem_empresa_id}').status_code == 403
    assert client.get(f'/api/contas/{conta_empresa_id}').status_code == 404

    _trocar_perfil(client, 'Empresa')
    categorias_empresa = _nomes(client.get('/api/categorias').get_json())
    contas_empresa = _nomes(client.get('/api/contas').get_json())
    despesas_empresa = _nomes(client.get('/api/despesas/').get_json())

    assert 'ESTAB Empresa Operacional' in categorias_empresa
    assert 'ESTAB Pessoal Residencial' not in categorias_empresa
    assert 'ESTAB Conta Empresa' in contas_empresa
    assert 'ESTAB Despesa Empresa' in despesas_empresa
    assert client.get('/api/ir/comprovantes?ano=2026').get_json()['total'] == 1
    assert client.get(f'/api/patrimonio/bens/{bem_empresa_id}').status_code == 200
