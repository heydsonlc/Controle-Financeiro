"""
Testes CORE-ESTORNO-1 — Estorno de pagamento de despesa.

POST /api/despesas/<id>/estornar-pagamento
- Estorno básico cria movimento de crédito e reabre despesa
- Estorno exige motivo (400)
- Estorno exige data_estorno (400)
- Estorno de despesa pendente é bloqueado (409)
- Estorno duplicado é bloqueado (409)
- Movimento original ausente retorna erro (422)
- Saldo bancário compensado após estorno
- Conferência de saldo permanece consistente
- Rollback em falha: despesa continua paga, saldo não muda
"""
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import (
    Conta,
    ContaBancaria,
    ItemDespesa,
    MovimentoFinanceiro,
    db,
)
from backend.routes.despesas import despesas_bp
from backend.routes.contas_bancarias import contas_bancarias_bp
from backend.services.conta_bancaria_service import ContaBancariaService


@pytest.fixture()
def client():
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
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


def _conta_bancaria(saldo=Decimal('1000.00')):
    cb = ContaBancaria(
        nome='Conta Teste',
        instituicao='Banco',
        tipo='Conta Corrente',
        saldo_inicial=saldo,
        saldo_atual=saldo,
        status='ATIVO',
    )
    db.session.add(cb)
    db.session.commit()
    return cb.id


def _item_despesa():
    item = ItemDespesa(nome='Despesa Teste', tipo='Simples', ativo=True)
    db.session.add(item)
    db.session.commit()
    return item.id


def _despesa(item_id, status='Pendente', cb_id=None):
    conta = Conta(
        item_despesa_id=item_id,
        mes_referencia=date(2026, 5, 1),
        descricao='Despesa Teste',
        valor=Decimal('100.00'),
        data_vencimento=date(2026, 5, 1),
        status_pagamento=status,
        conta_bancaria_id=cb_id,
    )
    db.session.add(conta)
    db.session.commit()
    return conta.id


def _pagar(client, despesa_id, cb_id):
    """Paga uma despesa pelo fluxo oficial e retorna o id da despesa."""
    resp = client.post(
        f'/api/despesas/{despesa_id}/pagar',
        json={'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10'},
    )
    assert resp.status_code == 200, resp.get_json()
    return despesa_id


# ---------------------------------------------------------------------------
# 1. Estorno básico
# ---------------------------------------------------------------------------

def test_estorno_basico_cria_movimento_credito(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_despesa()
    d_id = _despesa(item_id)
    _pagar(client, d_id, cb_id)

    resp = client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': 'Pagamento por engano'},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['status_pagamento'] == 'Pendente'
    assert data['data']['valor_estornado'] == 100.0

    mov_estorno = MovimentoFinanceiro.query.filter_by(
        conta_id=d_id, origem='ESTORNO_DESPESA'
    ).first()
    assert mov_estorno is not None
    assert mov_estorno.tipo == 'CREDITO'
    assert float(mov_estorno.valor) == 100.0


def test_estorno_reabre_despesa_como_pendente(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_despesa()
    d_id = _despesa(item_id)
    _pagar(client, d_id, cb_id)

    client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': 'Engano'},
    )

    conta = Conta.query.get(d_id)
    assert conta.status_pagamento == 'Pendente'
    assert conta.data_pagamento is None


def test_estorno_saldo_compensado(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_despesa()
    d_id = _despesa(item_id)
    _pagar(client, d_id, cb_id)

    saldo_apos_pagamento = float(ContaBancaria.query.get(cb_id).saldo_atual)
    assert saldo_apos_pagamento == 900.0

    client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': 'Engano'},
    )

    saldo_apos_estorno = float(ContaBancaria.query.get(cb_id).saldo_atual)
    assert saldo_apos_estorno == 1000.0


def test_estorno_registra_motivo_em_observacoes(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_despesa()
    d_id = _despesa(item_id)
    _pagar(client, d_id, cb_id)

    client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': 'Teste motivo'},
    )

    conta = Conta.query.get(d_id)
    assert 'ESTORNO' in (conta.observacoes or '')
    assert 'Teste motivo' in (conta.observacoes or '')


# ---------------------------------------------------------------------------
# 2. Estorno exige motivo
# ---------------------------------------------------------------------------

def test_estorno_sem_motivo_retorna_400(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_despesa()
    d_id = _despesa(item_id)
    _pagar(client, d_id, cb_id)

    resp = client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11'},
    )
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_estorno_motivo_vazio_retorna_400(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_despesa()
    d_id = _despesa(item_id)
    _pagar(client, d_id, cb_id)

    resp = client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': '   '},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Estorno exige data
# ---------------------------------------------------------------------------

def test_estorno_sem_data_retorna_400(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_despesa()
    d_id = _despesa(item_id)
    _pagar(client, d_id, cb_id)

    resp = client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'motivo': 'Engano'},
    )
    assert resp.status_code == 400


def test_estorno_data_invalida_retorna_400(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_despesa()
    d_id = _despesa(item_id)
    _pagar(client, d_id, cb_id)

    resp = client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': 'nao-e-data', 'motivo': 'Engano'},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. Estorno de despesa pendente é bloqueado
# ---------------------------------------------------------------------------

def test_estorno_despesa_pendente_retorna_409(client):
    item_id = _item_despesa()
    d_id = _despesa(item_id, status='Pendente')

    resp = client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': 'Engano'},
    )
    assert resp.status_code == 409
    assert resp.get_json()['success'] is False


def test_estorno_despesa_pendente_nao_cria_movimento(client):
    item_id = _item_despesa()
    d_id = _despesa(item_id, status='Pendente')

    client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': 'Engano'},
    )

    total = MovimentoFinanceiro.query.filter_by(conta_id=d_id).count()
    assert total == 0


# ---------------------------------------------------------------------------
# 5. Estorno duplicado é bloqueado
# ---------------------------------------------------------------------------

def test_estorno_duplicado_retorna_409(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_despesa()
    d_id = _despesa(item_id)
    _pagar(client, d_id, cb_id)

    client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': 'Primeiro estorno'},
    )

    # Segunda tentativa de estorno (despesa já está pendente novamente,
    # mas o movimento de estorno já existe → 409)
    _pagar(client, d_id, cb_id)
    resp = client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-12', 'motivo': 'Segundo estorno'},
    )
    assert resp.status_code == 409


def test_estorno_duplicado_nao_cria_segundo_movimento(client):
    cb_id = _conta_bancaria(Decimal('2000.00'))
    item_id = _item_despesa()
    d_id = _despesa(item_id)
    _pagar(client, d_id, cb_id)
    client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': 'Primeiro'},
    )
    _pagar(client, d_id, cb_id)
    client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-12', 'motivo': 'Segundo'},
    )

    total_estornos = MovimentoFinanceiro.query.filter_by(
        conta_id=d_id, origem='ESTORNO_DESPESA'
    ).count()
    assert total_estornos == 1


# ---------------------------------------------------------------------------
# 6. Movimento original ausente
# ---------------------------------------------------------------------------

def test_estorno_sem_movimento_original_retorna_422(client):
    item_id = _item_despesa()
    # Cria despesa com status pago mas sem movimento financeiro
    conta = Conta(
        item_despesa_id=item_id,
        mes_referencia=date(2026, 5, 1),
        descricao='Sem movimento',
        valor=Decimal('50.00'),
        data_vencimento=date(2026, 5, 1),
        status_pagamento='Pago',
        data_pagamento=date(2026, 5, 1),
    )
    db.session.add(conta)
    db.session.commit()
    d_id = conta.id

    resp = client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': 'Engano'},
    )
    assert resp.status_code == 422
    assert resp.get_json()['success'] is False


def test_estorno_sem_movimento_nao_altera_despesa(client):
    item_id = _item_despesa()
    conta = Conta(
        item_despesa_id=item_id,
        mes_referencia=date(2026, 5, 1),
        descricao='Sem movimento',
        valor=Decimal('50.00'),
        data_vencimento=date(2026, 5, 1),
        status_pagamento='Pago',
        data_pagamento=date(2026, 5, 1),
    )
    db.session.add(conta)
    db.session.commit()
    d_id = conta.id

    client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': 'Engano'},
    )

    conta_after = Conta.query.get(d_id)
    assert conta_after.status_pagamento == 'Pago'


# ---------------------------------------------------------------------------
# 7. Conferência de saldo após estorno
# ---------------------------------------------------------------------------

def test_conferencia_saldo_consistente_apos_estorno(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_despesa()
    d_id = _despesa(item_id)
    _pagar(client, d_id, cb_id)

    client.post(
        f'/api/despesas/{d_id}/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': 'Engano'},
    )

    resp = client.get(f'/api/contas/{cb_id}/conferir-saldo')
    assert resp.status_code == 200
    r = resp.get_json()['data']
    assert r['consistente'] is True
    assert r['divergencia'] == 0.0
    assert r['saldo_calculado'] == 1000.0


# ---------------------------------------------------------------------------
# 8. Despesa inexistente
# ---------------------------------------------------------------------------

def test_estorno_despesa_inexistente_retorna_404(client):
    resp = client.post(
        '/api/despesas/99999/estornar-pagamento',
        json={'data_estorno': '2026-05-11', 'motivo': 'Engano'},
    )
    assert resp.status_code == 404
    assert resp.get_json()['success'] is False
