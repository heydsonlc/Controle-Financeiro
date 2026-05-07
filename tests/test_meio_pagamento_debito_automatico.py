from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import Categoria, Conta, ContaBancaria, ItemDespesa, PerfilFinanceiro, db
from backend.routes.recorrencias import recorrencias_bp
from backend.services.perfil_financeiro_service import PerfilFinanceiroService


@pytest.fixture()
def app_context():
    base_dir = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(base_dir / 'frontend' / 'templates'),
        static_folder=str(base_dir / 'frontend' / 'static'),
    )
    app.config.update(
        TESTING=True,
        SECRET_KEY='test-secret',
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(recorrencias_bp, url_prefix='/api/recorrencias')

    @app.route('/recorrencias')
    def recorrencias_page():
        return render_template(
            'recorrencias.html',
            active_page='recorrencias',
            page_title='Recorrencias',
        )

    with app.app_context():
        db.create_all()
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


def _perfil(nome):
    return PerfilFinanceiro.query.filter_by(nome=nome).first()


def _ativar_perfil(client, nome):
    perfil = _perfil(nome)
    with client.session_transaction() as sess:
        sess['perfil_financeiro_id'] = perfil.id
    return perfil


def _conta_bancaria(perfil, nome='Conta DA'):
    conta = ContaBancaria(
        perfil_financeiro_id=perfil.id,
        nome=nome,
        instituicao='Banco Teste',
        tipo='Conta Corrente',
        saldo_inicial=Decimal('1000.00'),
        saldo_atual=Decimal('1000.00'),
        status='ATIVO',
    )
    db.session.add(conta)
    db.session.commit()
    return conta


def test_template_expoe_debito_automatico_da(client):
    html = client.get('/recorrencias').get_data(as_text=True)

    assert '<option value="debito_automatico">D&eacute;bito Autom&aacute;tico / D.A.</option>' in html
    assert 'id="conta-bancaria-id"' in html
    assert 'recorrencia-conta-bancaria' in html


def test_debito_automatico_sem_conta_retorna_erro_amigavel(client):
    _ativar_perfil(client, 'Pessoal')
    categoria = Categoria(nome='Moradia', ativo=True)
    db.session.add(categoria)
    db.session.commit()

    response = client.post('/api/recorrencias', json={
        'nome': 'Internet recorrente',
        'valor': str(Decimal('120.00')),
        'categoria_id': categoria.id,
        'data_vencimento': '2026-05-10',
        'tipo_recorrencia': 'mensal',
        'meio_pagamento': 'debito_automatico',
    })
    data = response.get_json()

    assert response.status_code == 400
    assert 'Conta banc' in data['error']
    assert ItemDespesa.query.filter_by(nome='Internet recorrente').count() == 0


def test_debito_automatico_com_conta_valida_salva_e_gera_conta_vinculada(client):
    perfil = _ativar_perfil(client, 'Pessoal')
    categoria = Categoria(nome='Moradia', ativo=True)
    db.session.add(categoria)
    db.session.commit()
    conta_bancaria = _conta_bancaria(perfil)

    response = client.post('/api/recorrencias', json={
        'nome': 'Internet recorrente',
        'valor': str(Decimal('120.00')),
        'categoria_id': categoria.id,
        'data_vencimento': '2026-05-10',
        'tipo_recorrencia': 'mensal',
        'meio_pagamento': 'debito_automatico',
        'conta_bancaria_id': conta_bancaria.id,
    })
    data = response.get_json()

    assert response.status_code == 201
    assert data['data']['meio_pagamento'] == 'debito_automatico'
    assert data['data']['conta_bancaria_id'] == conta_bancaria.id

    item = ItemDespesa.query.filter_by(nome='Internet recorrente').one()
    contas = Conta.query.filter_by(item_despesa_id=item.id).all()
    assert item.meio_pagamento == 'debito_automatico'
    assert item.conta_bancaria_id == conta_bancaria.id
    assert item.cartao_id is None
    assert item.categoria_cartao_id is None
    assert [conta.data_vencimento for conta in contas] == [date(2026, 5, 10)]
    assert contas[0].conta_bancaria_id == conta_bancaria.id
    assert contas[0].debito_automatico is True


def test_debito_automatico_bloqueia_conta_de_outro_perfil(client):
    empresa = _ativar_perfil(client, 'Empresa')
    conta_empresa = _conta_bancaria(empresa, 'Conta Empresa DA')
    _ativar_perfil(client, 'Pessoal')
    categoria = Categoria(nome='Moradia', ativo=True)
    db.session.add(categoria)
    db.session.commit()

    response = client.post('/api/recorrencias', json={
        'nome': 'Internet recorrente',
        'valor': str(Decimal('120.00')),
        'categoria_id': categoria.id,
        'data_vencimento': '2026-05-10',
        'tipo_recorrencia': 'mensal',
        'meio_pagamento': 'debito_automatico',
        'conta_bancaria_id': conta_empresa.id,
    })
    data = response.get_json()

    assert response.status_code == 400
    assert 'perfil financeiro ativo' in data['error']
    assert ItemDespesa.query.filter_by(nome='Internet recorrente').count() == 0


def test_debito_automatico_nao_exige_cartao_nem_aciona_categoria_cartao(client):
    perfil = _ativar_perfil(client, 'Pessoal')
    categoria = Categoria(nome='Moradia', ativo=True)
    cartao = ItemDespesa(
        perfil_financeiro_id=perfil.id,
        nome='Cartao Ignorado',
        tipo='Agregador',
        ativo=True,
        recorrente=True,
    )
    db.session.add_all([categoria, cartao])
    db.session.commit()
    conta_bancaria = _conta_bancaria(perfil)

    response = client.post('/api/recorrencias', json={
        'nome': 'Internet recorrente',
        'valor': str(Decimal('120.00')),
        'categoria_id': categoria.id,
        'data_vencimento': '2026-05-10',
        'tipo_recorrencia': 'mensal',
        'meio_pagamento': 'debito_automatico',
        'conta_bancaria_id': conta_bancaria.id,
        'cartao_id': cartao.id,
    })

    assert response.status_code == 201
    item = ItemDespesa.query.filter_by(nome='Internet recorrente').one()
    assert item.cartao_id is None
    assert item.categoria_cartao_id is None
