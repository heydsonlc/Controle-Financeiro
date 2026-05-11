"""
Testes CORE-BAIXA-1: segurança transacional da baixa/pagamento de despesas.
"""
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import (
    Categoria,
    ContaBancaria,
    Conta,
    ItemDespesa,
    MovimentoFinanceiro,
    db,
)
from backend.routes.despesas import despesas_bp
from backend.routes.contas_bancarias import contas_bancarias_bp


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(despesas_bp, url_prefix='/api/despesas')
    app.register_blueprint(contas_bancarias_bp, url_prefix='/api/contas')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _criar_base(saldo_inicial=500.0):
    categoria = Categoria(nome='Alimentacao', ativo=True)
    item = ItemDespesa(nome='Supermercado', tipo='Simples', ativo=True)
    conta_bancaria = ContaBancaria(
        nome='Conta Corrente',
        instituicao='Banco Teste',
        tipo='Conta Corrente',
        saldo_inicial=Decimal(str(saldo_inicial)),
        saldo_atual=Decimal(str(saldo_inicial)),
        status='ATIVO',
    )
    db.session.add_all([categoria, item, conta_bancaria])
    db.session.flush()

    conta = Conta(
        item_despesa_id=item.id,
        mes_referencia=date(2026, 5, 1),
        descricao='Compras supermercado',
        valor=Decimal('150.00'),
        data_vencimento=date(2026, 5, 10),
        status_pagamento='Pendente',
    )
    db.session.add(conta)
    db.session.commit()
    return categoria, item, conta_bancaria, conta


# ---------------------------------------------------------------------------
# 8.1. Baixa sem conta bancária
# ---------------------------------------------------------------------------

def test_baixa_sem_conta_bancaria_retorna_400(app_context):
    _categoria, _item, _cb, conta = _criar_base()

    with app_context.test_client() as client:
        resp = client.post(f'/api/despesas/{conta.id}/pagar', json={
            'data_pagamento': '2026-05-10',
        })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'conta bancária' in data['error'].lower() or 'conta banc' in data['error'].lower()


def test_baixa_sem_conta_bancaria_nao_altera_despesa(app_context):
    _categoria, _item, _cb, conta = _criar_base()

    with app_context.test_client() as client:
        client.post(f'/api/despesas/{conta.id}/pagar', json={'data_pagamento': '2026-05-10'})

    db.session.refresh(conta)
    assert conta.status_pagamento == 'Pendente'
    assert conta.data_pagamento is None


def test_baixa_sem_conta_bancaria_nao_cria_movimento(app_context):
    _categoria, _item, _cb, conta = _criar_base()

    with app_context.test_client() as client:
        client.post(f'/api/despesas/{conta.id}/pagar', json={'data_pagamento': '2026-05-10'})

    assert MovimentoFinanceiro.query.count() == 0


# ---------------------------------------------------------------------------
# 8.2. Conta inexistente
# ---------------------------------------------------------------------------

def test_baixa_conta_inexistente_retorna_404(app_context):
    _categoria, _item, _cb, conta = _criar_base()

    with app_context.test_client() as client:
        resp = client.post(f'/api/despesas/{conta.id}/pagar', json={
            'data_pagamento': '2026-05-10',
            'conta_bancaria_id': 99999,
        })

    assert resp.status_code == 404
    assert resp.get_json()['success'] is False


def test_baixa_conta_inexistente_nao_altera_despesa(app_context):
    _categoria, _item, _cb, conta = _criar_base()

    with app_context.test_client() as client:
        client.post(f'/api/despesas/{conta.id}/pagar', json={
            'data_pagamento': '2026-05-10',
            'conta_bancaria_id': 99999,
        })

    db.session.refresh(conta)
    assert conta.status_pagamento == 'Pendente'


def test_baixa_conta_inativa_retorna_400(app_context):
    _categoria, _item, cb, conta = _criar_base()
    cb.status = 'INATIVO'
    db.session.commit()

    with app_context.test_client() as client:
        resp = client.post(f'/api/despesas/{conta.id}/pagar', json={
            'data_pagamento': '2026-05-10',
            'conta_bancaria_id': cb.id,
        })

    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


# ---------------------------------------------------------------------------
# 8.3. Baixa normal
# ---------------------------------------------------------------------------

def test_baixa_normal_marca_despesa_como_paga(app_context):
    _categoria, _item, cb, conta = _criar_base(saldo_inicial=500.0)

    with app_context.test_client() as client:
        resp = client.post(f'/api/despesas/{conta.id}/pagar', json={
            'data_pagamento': '2026-05-10',
            'conta_bancaria_id': cb.id,
        })

    assert resp.status_code == 200
    db.session.refresh(conta)
    assert conta.status_pagamento == 'Pago'
    assert conta.data_pagamento == date(2026, 5, 10)
    assert conta.conta_bancaria_id == cb.id


def test_baixa_normal_cria_um_movimento_debito(app_context):
    _categoria, _item, cb, conta = _criar_base(saldo_inicial=500.0)

    with app_context.test_client() as client:
        client.post(f'/api/despesas/{conta.id}/pagar', json={
            'data_pagamento': '2026-05-10',
            'conta_bancaria_id': cb.id,
        })

    movimentos = MovimentoFinanceiro.query.filter_by(conta_bancaria_id=cb.id).all()
    assert len(movimentos) == 1
    mov = movimentos[0]
    assert mov.tipo == 'DEBITO'
    assert mov.valor == Decimal('150.00')
    assert mov.origem == 'DESPESA'
    assert mov.conta_id == conta.id
    assert mov.conta_bancaria_id == cb.id


def test_baixa_normal_debita_saldo_uma_unica_vez(app_context):
    _categoria, _item, cb, conta = _criar_base(saldo_inicial=500.0)

    with app_context.test_client() as client:
        client.post(f'/api/despesas/{conta.id}/pagar', json={
            'data_pagamento': '2026-05-10',
            'conta_bancaria_id': cb.id,
        })

    db.session.refresh(cb)
    assert cb.saldo_atual == Decimal('350.00')  # 500 - 150


def test_baixa_normal_movimento_conta_id_nao_e_nulo(app_context):
    _categoria, _item, cb, conta = _criar_base(saldo_inicial=500.0)

    with app_context.test_client() as client:
        client.post(f'/api/despesas/{conta.id}/pagar', json={
            'data_pagamento': '2026-05-10',
            'conta_bancaria_id': cb.id,
        })

    mov = MovimentoFinanceiro.query.filter_by(conta_bancaria_id=cb.id).first()
    assert mov is not None
    assert mov.conta_bancaria_id is not None
    assert mov.conta_bancaria_id == cb.id


# ---------------------------------------------------------------------------
# 8.4. Baixa duplicada
# ---------------------------------------------------------------------------

def test_baixa_duplicada_retorna_409(app_context):
    _categoria, _item, cb, conta = _criar_base(saldo_inicial=500.0)

    with app_context.test_client() as client:
        client.post(f'/api/despesas/{conta.id}/pagar', json={
            'data_pagamento': '2026-05-10',
            'conta_bancaria_id': cb.id,
        })
        resp2 = client.post(f'/api/despesas/{conta.id}/pagar', json={
            'data_pagamento': '2026-05-10',
            'conta_bancaria_id': cb.id,
        })

    assert resp2.status_code == 409
    assert resp2.get_json()['success'] is False
    assert 'já foi paga' in resp2.get_json()['error'].lower()


def test_baixa_duplicada_nao_cria_segundo_movimento(app_context):
    _categoria, _item, cb, conta = _criar_base(saldo_inicial=500.0)

    with app_context.test_client() as client:
        client.post(f'/api/despesas/{conta.id}/pagar', json={
            'conta_bancaria_id': cb.id,
            'data_pagamento': '2026-05-10',
        })
        client.post(f'/api/despesas/{conta.id}/pagar', json={
            'conta_bancaria_id': cb.id,
            'data_pagamento': '2026-05-10',
        })

    assert MovimentoFinanceiro.query.count() == 1


def test_baixa_duplicada_nao_debita_saldo_duas_vezes(app_context):
    _categoria, _item, cb, conta = _criar_base(saldo_inicial=500.0)

    with app_context.test_client() as client:
        client.post(f'/api/despesas/{conta.id}/pagar', json={
            'conta_bancaria_id': cb.id,
            'data_pagamento': '2026-05-10',
        })
        client.post(f'/api/despesas/{conta.id}/pagar', json={
            'conta_bancaria_id': cb.id,
            'data_pagamento': '2026-05-11',
        })

    db.session.refresh(cb)
    assert cb.saldo_atual == Decimal('350.00')  # 500 - 150 (uma única vez)


# ---------------------------------------------------------------------------
# 8.6. Movimento com conta_bancaria_id obrigatório
# ---------------------------------------------------------------------------

def test_movimento_gerado_tem_conta_bancaria_id_preenchido(app_context):
    _categoria, _item, cb, conta = _criar_base(saldo_inicial=1000.0)

    with app_context.test_client() as client:
        client.post(f'/api/despesas/{conta.id}/pagar', json={
            'conta_bancaria_id': cb.id,
            'data_pagamento': '2026-05-10',
        })

    mov = MovimentoFinanceiro.query.one()
    assert mov.conta_bancaria_id is not None
    assert mov.conta_bancaria_id == cb.id


# ---------------------------------------------------------------------------
# Integridade geral
# ---------------------------------------------------------------------------

def test_despesa_nao_encontrada_retorna_404(app_context):
    _criar_base()

    with app_context.test_client() as client:
        resp = client.post('/api/despesas/99999/pagar', json={
            'conta_bancaria_id': 1,
            'data_pagamento': '2026-05-10',
        })

    assert resp.status_code == 404


def test_data_pagamento_invalida_retorna_400(app_context):
    _categoria, _item, cb, conta = _criar_base()

    with app_context.test_client() as client:
        resp = client.post(f'/api/despesas/{conta.id}/pagar', json={
            'conta_bancaria_id': cb.id,
            'data_pagamento': '10/05/2026',  # formato errado
        })

    assert resp.status_code == 400


def test_valor_pago_customizado_altera_valor_da_despesa(app_context):
    _categoria, _item, cb, conta = _criar_base(saldo_inicial=500.0)

    with app_context.test_client() as client:
        resp = client.post(f'/api/despesas/{conta.id}/pagar', json={
            'conta_bancaria_id': cb.id,
            'data_pagamento': '2026-05-10',
            'valor_pago': 145.00,
        })

    assert resp.status_code == 200
    db.session.refresh(conta)
    assert float(conta.valor) == 145.00
    db.session.refresh(cb)
    assert cb.saldo_atual == Decimal('355.00')  # 500 - 145
