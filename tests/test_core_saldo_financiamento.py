"""
Testes CORE-SALDO-1C:
POST /financiamentos/parcelas/<id>/pagar
- Requer conta_bancaria_id (400 sem ele)
- Cria MovimentoFinanceiro DEBITO com origem=FINANCIAMENTO
- Bloqueia pagamento duplicado (409)
- Bloqueia parcela inexistente (404)
- Bloqueia conta bancária inexistente (404)
- Bloqueia conta bancária inativa (400)
- Bloqueia parcela com despesa vinculada pendente (409)
- registrar_pagamento_parcela com commit=False não persiste sozinho
"""
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import (
    ContaBancaria,
    Conta,
    Financiamento,
    FinanciamentoParcela,
    ItemDespesa,
    MovimentoFinanceiro,
    db,
)
from backend.routes.financiamentos import financiamentos_bp
from backend.routes.contas_bancarias import contas_bancarias_bp
from backend.services.financiamento_service import FinanciamentoService


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(financiamentos_bp, url_prefix='/api/financiamentos')
    app.register_blueprint(contas_bancarias_bp, url_prefix='/api/contas')

    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def ctx():
    """App context apenas, sem client, para testes de service."""
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _financiamento_e_parcela(valor_previsto=1500.0):
    """Retorna (financiamento_id, parcela_id). Requer app_context ativo."""
    fin = Financiamento(
        nome='Financiamento Teste',
        sistema_amortizacao='SAC',
        valor_financiado=Decimal('100000.00'),
        prazo_total_meses=360,
        prazo_remanescente_meses=360,
        taxa_juros_nominal_anual=Decimal('8.0000'),
        taxa_juros_mensal=Decimal('0.006434'),
        data_contrato=date(2025, 1, 1),
        data_primeira_parcela=date(2025, 2, 1),
    )
    db.session.add(fin)
    db.session.flush()

    parcela = FinanciamentoParcela(
        financiamento_id=fin.id,
        numero_parcela=1,
        data_vencimento=date(2026, 5, 1),
        valor_amortizacao=Decimal('800.00'),
        valor_juros=Decimal('500.00'),
        valor_previsto_total=Decimal(str(valor_previsto)),
        status='pendente',
    )
    db.session.add(parcela)
    db.session.flush()
    return fin.id, parcela.id


def _conta_bancaria(status='ATIVO', saldo=5000.0):
    """Retorna conta_bancaria_id. Requer app_context ativo."""
    cb = ContaBancaria(
        nome='Corrente',
        instituicao='Banco',
        tipo='Conta Corrente',
        saldo_inicial=Decimal(str(saldo)),
        saldo_atual=Decimal(str(saldo)),
        status=status,
    )
    db.session.add(cb)
    db.session.flush()
    return cb.id


# ---------------------------------------------------------------------------
# Casos de erro de validação
# ---------------------------------------------------------------------------

def test_sem_conta_bancaria_retorna_400(client):
    _, parcela_id = _financiamento_e_parcela()
    db.session.commit()

    resp = client.post(
        f'/api/financiamentos/parcelas/{parcela_id}/pagar',
        json={'data_pagamento': '2026-05-10'},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'conta' in data['error'].lower()


def test_sem_data_pagamento_retorna_400(client):
    _, parcela_id = _financiamento_e_parcela()
    cb_id = _conta_bancaria()
    db.session.commit()

    resp = client.post(
        f'/api/financiamentos/parcelas/{parcela_id}/pagar',
        json={'conta_bancaria_id': cb_id},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


def test_data_pagamento_formato_invalido_retorna_400(client):
    _, parcela_id = _financiamento_e_parcela()
    cb_id = _conta_bancaria()
    db.session.commit()

    resp = client.post(
        f'/api/financiamentos/parcelas/{parcela_id}/pagar',
        json={'conta_bancaria_id': cb_id, 'data_pagamento': '10/05/2026'},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


def test_parcela_inexistente_retorna_404(client):
    cb_id = _conta_bancaria()
    db.session.commit()

    resp = client.post(
        '/api/financiamentos/parcelas/99999/pagar',
        json={'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10'},
    )
    assert resp.status_code == 404
    data = resp.get_json()
    assert data['success'] is False


def test_conta_bancaria_inexistente_retorna_404(client):
    _, parcela_id = _financiamento_e_parcela()
    db.session.commit()

    resp = client.post(
        f'/api/financiamentos/parcelas/{parcela_id}/pagar',
        json={'conta_bancaria_id': 99999, 'data_pagamento': '2026-05-10'},
    )
    assert resp.status_code == 404
    data = resp.get_json()
    assert data['success'] is False


def test_conta_bancaria_inativa_retorna_400(client):
    _, parcela_id = _financiamento_e_parcela()
    cb_id = _conta_bancaria(status='INATIVO')
    db.session.commit()

    resp = client.post(
        f'/api/financiamentos/parcelas/{parcela_id}/pagar',
        json={'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10'},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'inativa' in data['error'].lower()


# ---------------------------------------------------------------------------
# Pagamento com despesa vinculada pendente
# ---------------------------------------------------------------------------

def test_parcela_com_despesa_vinculada_pendente_retorna_409(client):
    _, parcela_id = _financiamento_e_parcela()
    cb_id = _conta_bancaria()

    item = ItemDespesa(nome='Item Fin', tipo='Simples', ativo=True)
    db.session.add(item)
    db.session.flush()

    despesa = Conta(
        item_despesa_id=item.id,
        mes_referencia=date(2026, 5, 1),
        data_vencimento=date(2026, 5, 10),
        descricao='Parcela vinculada',
        valor=Decimal('1500.00'),
        status_pagamento='Pendente',
        financiamento_parcela_id=parcela_id,
    )
    db.session.add(despesa)
    db.session.commit()

    resp = client.post(
        f'/api/financiamentos/parcelas/{parcela_id}/pagar',
        json={'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10'},
    )
    assert resp.status_code == 409
    data = resp.get_json()
    assert data['success'] is False
    assert 'despesa' in data['error'].lower()


# ---------------------------------------------------------------------------
# Pagamento bem-sucedido
# ---------------------------------------------------------------------------

def test_pagamento_normal_cria_movimento_debito(client):
    _, parcela_id = _financiamento_e_parcela(valor_previsto=1300.0)
    cb_id = _conta_bancaria(saldo=5000.0)
    db.session.commit()

    resp = client.post(
        f'/api/financiamentos/parcelas/{parcela_id}/pagar',
        json={'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10'},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()
    assert data['success'] is True

    parcela_db = FinanciamentoParcela.query.filter_by(id=parcela_id).first()
    assert parcela_db.status == 'pago'

    mov = MovimentoFinanceiro.query.filter_by(
        conta_bancaria_id=cb_id,
        financiamento_parcela_id=parcela_id,
    ).first()
    assert mov is not None
    assert mov.tipo == 'DEBITO'
    assert mov.origem == 'FINANCIAMENTO'
    assert Decimal(str(mov.valor)) == Decimal('1300.00')

    cb_db = ContaBancaria.query.filter_by(id=cb_id).first()
    assert Decimal(str(cb_db.saldo_atual)) == Decimal('3700.00')


def test_pagamento_atualiza_saldo_conta(client):
    _, parcela_id = _financiamento_e_parcela(valor_previsto=500.0)
    cb_id = _conta_bancaria(saldo=2000.0)
    db.session.commit()

    resp = client.post(
        f'/api/financiamentos/parcelas/{parcela_id}/pagar',
        json={'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10'},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    cb_db = ContaBancaria.query.filter_by(id=cb_id).first()
    assert Decimal(str(cb_db.saldo_atual)) == Decimal('1500.00')


# ---------------------------------------------------------------------------
# Pagamento duplicado (idempotência / bloqueio)
# ---------------------------------------------------------------------------

def test_pagamento_duplicado_retorna_409(client):
    _, parcela_id = _financiamento_e_parcela()
    cb_id = _conta_bancaria(saldo=10000.0)
    db.session.commit()

    payload = {'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10'}

    resp1 = client.post(f'/api/financiamentos/parcelas/{parcela_id}/pagar', json=payload)
    assert resp1.status_code == 200, resp1.get_data(as_text=True)

    resp2 = client.post(f'/api/financiamentos/parcelas/{parcela_id}/pagar', json=payload)
    assert resp2.status_code == 409
    data = resp2.get_json()
    assert data['success'] is False


def test_pagamento_duplicado_nao_cria_segundo_movimento(client):
    _, parcela_id = _financiamento_e_parcela()
    cb_id = _conta_bancaria(saldo=10000.0)
    db.session.commit()

    payload = {'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10'}
    client.post(f'/api/financiamentos/parcelas/{parcela_id}/pagar', json=payload)
    client.post(f'/api/financiamentos/parcelas/{parcela_id}/pagar', json=payload)

    total = MovimentoFinanceiro.query.filter_by(
        conta_bancaria_id=cb_id,
        financiamento_parcela_id=parcela_id,
    ).count()
    assert total == 1


# ---------------------------------------------------------------------------
# registrar_pagamento_parcela com commit=False
# ---------------------------------------------------------------------------

def test_registrar_pagamento_commit_false_nao_persiste(ctx):
    with ctx.app_context():
        _, parcela_id = _financiamento_e_parcela()
        db.session.commit()

        FinanciamentoService.registrar_pagamento_parcela(
            parcela_id,
            Decimal('1300.00'),
            date(2026, 5, 10),
            commit=False,
        )
        db.session.rollback()

        parcela_db = FinanciamentoParcela.query.filter_by(id=parcela_id).first()
        assert parcela_db.status == 'pendente'


def test_registrar_pagamento_commit_true_persiste(ctx):
    with ctx.app_context():
        _, parcela_id = _financiamento_e_parcela()
        db.session.commit()

        FinanciamentoService.registrar_pagamento_parcela(
            parcela_id,
            Decimal('1300.00'),
            date(2026, 5, 10),
            commit=True,
        )

        parcela_db = FinanciamentoParcela.query.filter_by(id=parcela_id).first()
        assert parcela_db.status == 'pago'


def test_registrar_pagamento_duplicado_via_service_levanta_erro(ctx):
    with ctx.app_context():
        _, parcela_id = _financiamento_e_parcela()
        db.session.commit()

        FinanciamentoService.registrar_pagamento_parcela(
            parcela_id,
            Decimal('1300.00'),
            date(2026, 5, 10),
            commit=True,
        )

        with pytest.raises(ValueError, match='ja foi paga'):
            FinanciamentoService.registrar_pagamento_parcela(
                parcela_id,
                Decimal('1300.00'),
                date(2026, 5, 10),
                commit=True,
            )
