from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest

from backend.app import create_app
from backend.models import (
    Categoria,
    ContaPatrimonio,
    Financiamento,
    FinanciamentoParcela,
    IrComprovante,
    MobilidadeAssinatura,
    PerfilFinanceiro,
    Veiculo,
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
    assert response.status_code == 200, response.get_data(as_text=True)
    return perfil


def _nomes_from_response(response):
    payload = response.get_json()
    itens = payload if isinstance(payload, list) else payload.get('data', [])
    return {item.get('nome') for item in itens}


def _criar_categoria(client, nome='Mobilidade'):
    response = client.post('/api/categorias', json={
        'nome': nome,
        'descricao': f'{nome} contexto',
        'cor': '#2563eb',
        'icone': 'car',
        'ativo': True,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()['data']


def test_caixinha_empresa_nao_aparece_no_pessoal_e_transferencia_cruzada_bloqueia(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    conta_empresa = client.post('/api/patrimonio/contas', json={
        'nome': 'Reserva Empresa CTX4',
        'tipo': 'Corrente',
        'saldo_inicial': 1000,
    })
    assert conta_empresa.status_code == 201, conta_empresa.get_data(as_text=True)
    conta_empresa = conta_empresa.get_json()['data']

    _trocar_perfil(client, 'Pessoal')
    conta_pessoal = client.post('/api/patrimonio/contas', json={
        'nome': 'Reserva Pessoal CTX4',
        'tipo': 'Corrente',
        'saldo_inicial': 1000,
    })
    assert conta_pessoal.status_code == 201, conta_pessoal.get_data(as_text=True)
    conta_pessoal = conta_pessoal.get_json()['data']

    assert 'Reserva Empresa CTX4' not in _nomes_from_response(client.get('/api/patrimonio/contas'))
    assert client.get(f"/api/patrimonio/contas/{conta_empresa['id']}").status_code == 404

    tentativa = client.post('/api/patrimonio/transferencias', json={
        'conta_origem_id': conta_pessoal['id'],
        'conta_destino_id': conta_empresa['id'],
        'valor': 100,
        'data_transferencia': '2026-05-04',
    })
    assert tentativa.status_code == 404

    with app.app_context():
        assert ContaPatrimonio.query.get(conta_empresa['id']).perfil_financeiro_id == empresa['id']


def test_financiamento_e_parcela_respeitam_perfil_ativo(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        financiamento = Financiamento(
            perfil_financeiro_id=empresa['id'],
            nome='Financiamento Empresa CTX4',
            sistema_amortizacao='SAC',
            valor_financiado=Decimal('10000'),
            prazo_total_meses=12,
            prazo_remanescente_meses=12,
            taxa_juros_nominal_anual=Decimal('8'),
            taxa_juros_mensal=Decimal('0.006'),
            data_contrato=date(2026, 1, 1),
            data_primeira_parcela=date(2026, 2, 1),
            ativo=True,
        )
        db.session.add(financiamento)
        db.session.flush()
        parcela = FinanciamentoParcela(
            perfil_financeiro_id=empresa['id'],
            financiamento_id=financiamento.id,
            numero_parcela=1,
            data_vencimento=date(2026, 2, 1),
            valor_amortizacao=Decimal('800'),
            valor_juros=Decimal('80'),
            valor_previsto_total=Decimal('880'),
            status='pendente',
        )
        db.session.add(parcela)
        db.session.commit()
        financiamento_id = financiamento.id
        parcela_id = parcela.id

    assert 'Financiamento Empresa CTX4' in _nomes_from_response(client.get('/api/financiamentos'))
    _trocar_perfil(client, 'Pessoal')
    assert 'Financiamento Empresa CTX4' not in _nomes_from_response(client.get('/api/financiamentos'))

    with app.app_context():
        assert FinanciamentoParcela.query.get(parcela_id).perfil_financeiro_id == empresa['id']
        assert Financiamento.query.get(financiamento_id).perfil_financeiro_id == empresa['id']


def test_veiculo_e_mobilidade_sao_independentes_por_perfil(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    _criar_categoria(client, 'Mobilidade')

    veiculo_resp = client.post('/api/veiculos', json={
        'nome': 'Carro Empresa CTX4',
        'tipo': 'carro',
        'combustivel': 'gasolina',
        'autonomia_km_l': 10,
        'status': 'SIMULADO',
        'meses_futuros': 1,
    })
    assert veiculo_resp.status_code == 201, veiculo_resp.get_data(as_text=True)
    veiculo = veiculo_resp.get_json()['data']

    assinatura_resp = client.post('/api/veiculos/mobilidade/assinaturas', json={
        'nome': 'Assinatura Empresa CTX4',
        'valor_mensal': 1200,
    })
    assert assinatura_resp.status_code == 201, assinatura_resp.get_data(as_text=True)
    assinatura = assinatura_resp.get_json()['data']

    ativar_resp = client.post('/api/veiculos/mobilidade/ativar', json={
        'confirmado': True,
        'tipo_modalidade': 'ASSINATURA',
        'origem_id': assinatura['id'],
        'criar_recorrencia': False,
    })
    assert ativar_resp.status_code == 200, ativar_resp.get_data(as_text=True)
    assert client.get('/api/veiculos/mobilidade/ativo').get_json()['data']['tipo_modalidade'] == 'ASSINATURA'

    _trocar_perfil(client, 'Pessoal')
    assert 'Carro Empresa CTX4' not in _nomes_from_response(client.get('/api/veiculos'))
    assert 'Assinatura Empresa CTX4' not in _nomes_from_response(client.get('/api/veiculos/mobilidade/assinaturas'))
    assert client.get('/api/veiculos/mobilidade/ativo').get_json()['data'] is None
    assert client.get(f"/api/veiculos/{veiculo['id']}").status_code == 404

    with app.app_context():
        assert Veiculo.query.get(veiculo['id']).perfil_financeiro_id == empresa['id']
        assert MobilidadeAssinatura.query.get(assinatura['id']).perfil_financeiro_id == empresa['id']


def test_upload_ir_empresa_nao_aparece_no_pessoal_e_id_de_outro_perfil_retorna_404(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    payload = {
        'ano_calendario': '2026',
        'arquivo': (BytesIO(b'\x89PNG\r\n\x1a\nCTX4'), 'comprovante_ctx4.png'),
    }
    response = client.post('/api/ir/comprovantes/upload', data=payload, content_type='multipart/form-data')
    assert response.status_code == 200, response.get_data(as_text=True)
    comprovante = response.get_json()['data'][0]['data']['comprovante']

    assert client.get('/api/ir/comprovantes?ano=2026').get_json()['total'] == 1
    _trocar_perfil(client, 'Pessoal')
    assert client.get('/api/ir/comprovantes?ano=2026').get_json()['total'] == 0
    assert client.get(f"/api/ir/comprovantes/{comprovante['id']}").status_code == 404

    with app.app_context():
        assert IrComprovante.query.get(comprovante['id']).perfil_financeiro_id == empresa['id']


def test_importacao_cartao_lista_apenas_categorias_do_perfil_ativo(client):
    _trocar_perfil(client, 'Empresa')
    _criar_categoria(client, 'Categoria Importacao Empresa CTX4')
    assert 'Categoria Importacao Empresa CTX4' in {
        item['nome'] for item in client.get('/api/importacao-cartao/categorias').get_json()['categorias']
    }

    _trocar_perfil(client, 'Pessoal')
    assert 'Categoria Importacao Empresa CTX4' not in {
        item['nome'] for item in client.get('/api/importacao-cartao/categorias').get_json()['categorias']
    }


def test_backfill_conceitual_modulos_avancados_para_pessoal(app):
    with app.app_context():
        pessoal = PerfilFinanceiro.query.filter_by(nome='Pessoal').first()
        conta = ContaPatrimonio(nome='Legado CTX4', saldo_inicial=0, saldo_atual=0, ativo=True)
        db.session.add(conta)
        db.session.commit()

        assert conta.perfil_financeiro_id is None

        ContaPatrimonio.query.filter(ContaPatrimonio.perfil_financeiro_id.is_(None)).update({
            'perfil_financeiro_id': pessoal.id
        })
        db.session.commit()

        assert ContaPatrimonio.query.get(conta.id).perfil_financeiro_id == pessoal.id
