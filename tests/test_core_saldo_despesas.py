"""
Testes CORE-SALDO-1A/1B:
- 1A: DELETE /despesas/<id> bloqueado para despesas pagas ou com movimento
- 1B: PUT /despesas/<id> bloqueado quando payload tenta marcar como pago
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


def _base(saldo=500.0):
    cat = Categoria(nome='Teste', ativo=True)
    item = ItemDespesa(nome='Item Teste', tipo='Simples', ativo=True)
    cb = ContaBancaria(
        nome='Corrente',
        instituicao='Banco',
        tipo='Conta Corrente',
        saldo_inicial=Decimal(str(saldo)),
        saldo_atual=Decimal(str(saldo)),
        status='ATIVO',
    )
    db.session.add_all([cat, item, cb])
    db.session.flush()

    conta = Conta(
        item_despesa_id=item.id,
        mes_referencia=date(2026, 5, 1),
        descricao='Despesa Teste',
        valor=Decimal('100.00'),
        data_vencimento=date(2026, 5, 10),
        status_pagamento='Pendente',
    )
    db.session.add(conta)
    db.session.commit()
    return cat, item, cb, conta


def _pagar(client, conta, cb):
    return client.post(f'/api/despesas/{conta.id}/pagar', json={
        'conta_bancaria_id': cb.id,
        'data_pagamento': '2026-05-10',
    })


# ---------------------------------------------------------------------------
# CORE-SALDO-1B: PUT não pode pagar
# ---------------------------------------------------------------------------

def test_put_com_pago_true_retorna_400(app_context):
    _, _, _, conta = _base()
    with app_context.test_client() as c:
        resp = c.put(f'/api/despesas/{conta.id}', json={'pago': True})
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_put_com_pago_true_nao_muda_status(app_context):
    _, _, _, conta = _base()
    with app_context.test_client() as c:
        c.put(f'/api/despesas/{conta.id}', json={'pago': True})
    db.session.refresh(conta)
    assert conta.status_pagamento == 'Pendente'


def test_put_com_pago_true_nao_cria_movimento(app_context):
    _, _, _, conta = _base()
    with app_context.test_client() as c:
        c.put(f'/api/despesas/{conta.id}', json={'pago': True})
    assert MovimentoFinanceiro.query.count() == 0


def test_put_com_data_pagamento_retorna_400(app_context):
    _, _, _, conta = _base()
    with app_context.test_client() as c:
        resp = c.put(f'/api/despesas/{conta.id}', json={'data_pagamento': '2026-05-10'})
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_put_com_data_pagamento_nao_marca_como_pago(app_context):
    _, _, _, conta = _base()
    with app_context.test_client() as c:
        c.put(f'/api/despesas/{conta.id}', json={'data_pagamento': '2026-05-10'})
    db.session.refresh(conta)
    assert conta.status_pagamento == 'Pendente'
    assert conta.data_pagamento is None


def test_put_com_valor_pago_retorna_400(app_context):
    _, _, _, conta = _base()
    with app_context.test_client() as c:
        resp = c.put(f'/api/despesas/{conta.id}', json={'valor_pago': 90.0})
    assert resp.status_code == 400


def test_put_com_status_pagamento_pago_retorna_400(app_context):
    _, _, _, conta = _base()
    with app_context.test_client() as c:
        resp = c.put(f'/api/despesas/{conta.id}', json={'status_pagamento': 'Pago'})
    assert resp.status_code == 400


def test_put_normal_sem_campos_pagamento_funciona(app_context):
    _, _, _, conta = _base()
    with app_context.test_client() as c:
        resp = c.put(f'/api/despesas/{conta.id}', json={'descricao': 'Nova descricao'})
    assert resp.status_code == 200
    db.session.refresh(conta)
    assert conta.descricao == 'Nova descricao'
    assert conta.status_pagamento == 'Pendente'


def test_put_pago_false_nao_e_bloqueado(app_context):
    """pago=False não é tentativa de pagamento — deve passar (desfazer estado pendente)."""
    _, _, _, conta = _base()
    with app_context.test_client() as c:
        resp = c.put(f'/api/despesas/{conta.id}', json={'pago': False})
    # pago=False não dispara o bloqueio (valor não é perigoso)
    assert resp.status_code == 200


def test_put_data_pagamento_nula_nao_e_bloqueada(app_context):
    """data_pagamento=null/'' não é tentativa de pagamento."""
    _, _, _, conta = _base()
    with app_context.test_client() as c:
        resp = c.put(f'/api/despesas/{conta.id}', json={'data_pagamento': ''})
    assert resp.status_code == 200


def test_put_nao_altera_saldo_bancario(app_context):
    _, _, cb, conta = _base(saldo=500.0)
    with app_context.test_client() as c:
        c.put(f'/api/despesas/{conta.id}', json={'pago': True})
    db.session.refresh(cb)
    assert cb.saldo_atual == Decimal('500.00')


# ---------------------------------------------------------------------------
# CORE-SALDO-1A: DELETE bloqueado para despesa paga
# ---------------------------------------------------------------------------

def test_delete_despesa_paga_retorna_409(app_context):
    _, _, cb, conta = _base()
    with app_context.test_client() as c:
        _pagar(c, conta, cb)
        resp = c.delete(f'/api/despesas/{conta.id}')
    assert resp.status_code == 409
    assert resp.get_json()['success'] is False


def test_delete_despesa_paga_nao_remove_registro(app_context):
    _, _, cb, conta = _base()
    conta_id = conta.id
    with app_context.test_client() as c:
        _pagar(c, conta, cb)
        c.delete(f'/api/despesas/{conta.id}')
    assert Conta.query.get(conta_id) is not None


def test_delete_despesa_paga_preserva_movimento(app_context):
    _, _, cb, conta = _base()
    with app_context.test_client() as c:
        _pagar(c, conta, cb)
        c.delete(f'/api/despesas/{conta.id}')
    assert MovimentoFinanceiro.query.filter_by(conta_id=conta.id).count() == 1


def test_delete_despesa_paga_preserva_saldo(app_context):
    _, _, cb, conta = _base(saldo=500.0)
    with app_context.test_client() as c:
        _pagar(c, conta, cb)
        c.delete(f'/api/despesas/{conta.id}')
    db.session.refresh(cb)
    assert cb.saldo_atual == Decimal('400.00')  # 500 - 100, mantido


def test_delete_despesa_com_movimento_retorna_409(app_context):
    """Despesa com movimento vinculado (mesmo sem status 'Pago') não pode ser excluída."""
    _, _, cb, conta = _base()
    # Injetar movimento órfão diretamente (sem passar pelo fluxo de baixa)
    mov = MovimentoFinanceiro(
        conta_bancaria_id=cb.id,
        tipo='DEBITO',
        valor=Decimal('100.00'),
        descricao='Movimento manual',
        data_movimento=date(2026, 5, 10),
        origem='DESPESA',
        conta_id=conta.id,
    )
    db.session.add(mov)
    db.session.commit()

    with app_context.test_client() as c:
        resp = c.delete(f'/api/despesas/{conta.id}')
    assert resp.status_code == 409


def test_delete_despesa_pendente_sem_movimento_funciona(app_context):
    _, _, _, conta = _base()
    conta_id = conta.id
    with app_context.test_client() as c:
        resp = c.delete(f'/api/despesas/{conta.id}')
    assert resp.status_code == 200
    assert Conta.query.get(conta_id) is None


def test_delete_despesa_inexistente_retorna_404(app_context):
    _base()
    with app_context.test_client() as c:
        resp = c.delete('/api/despesas/99999')
    assert resp.status_code == 404
