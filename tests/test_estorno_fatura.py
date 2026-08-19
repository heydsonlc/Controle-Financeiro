"""
Testes CORE-ESTORNO-3 — Estorno de pagamento de fatura de cartao.

POST /api/despesas/<id>/estornar-pagamento (rota unificada: fatura e despesa
sao a mesma tabela Conta; is_fatura_cartao=True usa origem=ESTORNO_FATURA)

- Fatura paga pode ser estornada
- Movimento original DEBITO e preservado
- Movimento compensatorio CREDITO e criado com origem=ESTORNO_FATURA
- Saldo bancario e recomposto
- Fatura volta para pendente
- Motivo/data obrigatorios
- Fatura aberta (nao paga) nao pode ser estornada
- Fatura paga sem movimento nao pode ser estornada
- Estorno duplicado e bloqueado
- Lancamentos da fatura nao sao alterados (nao ha o que alterar aqui: nenhum
  campo de lancamento_agregado/compra_id/categoria_cartao_id e tocado)
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


def _conta_bancaria(saldo=Decimal('5000.00')):
    cb = ContaBancaria(
        nome='Conta Teste', instituicao='Banco', tipo='Conta Corrente',
        saldo_inicial=saldo, saldo_atual=saldo, status='ATIVO',
    )
    db.session.add(cb)
    db.session.commit()
    return cb.id


def _cartao():
    item = ItemDespesa(nome='Cartao Teste', tipo='Agregador', ativo=True)
    db.session.add(item)
    db.session.commit()
    return item.id


def _fatura(cartao_id, status='ABERTA', status_pagamento='Pendente', cb_id=None):
    fatura = Conta(
        item_despesa_id=cartao_id,
        mes_referencia=date(2026, 5, 1),
        descricao='Fatura Cartao Teste',
        valor=Decimal('3000.00'),
        data_vencimento=date(2026, 5, 10),
        status_pagamento=status_pagamento,
        is_fatura_cartao=True,
        valor_executado=Decimal('3000.00'),
        cartao_competencia=date(2026, 5, 1),
        status_fatura=status,
        conta_bancaria_id=cb_id,
    )
    db.session.add(fatura)
    db.session.commit()
    return fatura.id


def _pagar_fatura_direto(fatura_id, cb_id, valor=Decimal('3000.00')):
    """Simula o pagamento (via CartaoService.pagar_fatura) criando o movimento
    DEBITO original e marcando a fatura como paga, sem depender da montagem
    completa de ConfigAgregador/lancamentos."""
    from backend.services.conta_bancaria_service import ContaBancariaService

    fatura = Conta.query.get(fatura_id)
    ContaBancariaService.criar_movimento(
        cb_id, tipo='DEBITO', valor=valor,
        descricao=f'Pagamento fatura cartao - {fatura.descricao}',
        data_movimento=date(2026, 5, 10), origem='FATURA',
        fatura_id=fatura_id, conta_id=fatura_id,
    )
    fatura.conta_bancaria_id = cb_id
    fatura.status_pagamento = 'Pago'
    fatura.data_pagamento = date(2026, 5, 10)
    db.session.commit()
    return fatura_id


# ---------------------------------------------------------------------------
# 1. Fatura paga pode ser estornada
# ---------------------------------------------------------------------------

def test_estorno_fatura_paga_cria_movimento_credito(client):
    cb_id = _conta_bancaria()
    cartao_id = _cartao()
    f_id = _fatura(cartao_id)
    _pagar_fatura_direto(f_id, cb_id)

    resp = client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Pagamento por engano',
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['status_pagamento'] == 'Pendente'
    assert data['data']['valor_estornado'] == 3000.0

    mov_estorno = MovimentoFinanceiro.query.filter_by(
        conta_id=f_id, origem='ESTORNO_FATURA',
    ).first()
    assert mov_estorno is not None
    assert mov_estorno.tipo == 'CREDITO'
    assert float(mov_estorno.valor) == 3000.0


def test_estorno_fatura_preserva_movimento_original(client):
    cb_id = _conta_bancaria()
    cartao_id = _cartao()
    f_id = _fatura(cartao_id)
    _pagar_fatura_direto(f_id, cb_id)

    client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    mov_original = MovimentoFinanceiro.query.filter_by(
        conta_id=f_id, origem='FATURA', tipo='DEBITO',
    ).first()
    assert mov_original is not None
    assert float(mov_original.valor) == 3000.0


def test_estorno_fatura_volta_para_pendente(client):
    cb_id = _conta_bancaria()
    cartao_id = _cartao()
    f_id = _fatura(cartao_id)
    _pagar_fatura_direto(f_id, cb_id)

    client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    fatura = Conta.query.get(f_id)
    assert fatura.status_pagamento == 'Pendente'
    assert fatura.data_pagamento is None


def test_estorno_fatura_saldo_compensado(client):
    cb_id = _conta_bancaria(Decimal('5000.00'))
    cartao_id = _cartao()
    f_id = _fatura(cartao_id)
    _pagar_fatura_direto(f_id, cb_id)

    saldo_apos_pagamento = float(ContaBancaria.query.get(cb_id).saldo_atual)
    assert saldo_apos_pagamento == 2000.0

    client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    saldo_apos_estorno = float(ContaBancaria.query.get(cb_id).saldo_atual)
    assert saldo_apos_estorno == 5000.0


# ---------------------------------------------------------------------------
# 2/3. Motivo e data obrigatorios
# ---------------------------------------------------------------------------

def test_estorno_fatura_sem_motivo_retorna_400(client):
    cb_id = _conta_bancaria()
    cartao_id = _cartao()
    f_id = _fatura(cartao_id)
    _pagar_fatura_direto(f_id, cb_id)

    resp = client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11',
    })
    assert resp.status_code == 400


def test_estorno_fatura_sem_data_retorna_400(client):
    cb_id = _conta_bancaria()
    cartao_id = _cartao()
    f_id = _fatura(cartao_id)
    _pagar_fatura_direto(f_id, cb_id)

    resp = client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'motivo': 'Engano',
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. Fatura aberta nao pode ser estornada
# ---------------------------------------------------------------------------

def test_estorno_fatura_aberta_retorna_409(client):
    cartao_id = _cartao()
    f_id = _fatura(cartao_id, status_pagamento='Pendente')

    resp = client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 409


def test_estorno_fatura_aberta_nao_cria_movimento(client):
    cartao_id = _cartao()
    f_id = _fatura(cartao_id, status_pagamento='Pendente')

    client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    assert MovimentoFinanceiro.query.filter_by(conta_id=f_id).count() == 0


# ---------------------------------------------------------------------------
# 5. Fatura paga sem movimento
# ---------------------------------------------------------------------------

def test_estorno_fatura_sem_movimento_retorna_422(client):
    cartao_id = _cartao()
    f_id = _fatura(cartao_id, status_pagamento='Pago')

    resp = client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 6. Estorno duplicado
# ---------------------------------------------------------------------------

def test_estorno_fatura_duplicado_retorna_409(client):
    cb_id = _conta_bancaria()
    cartao_id = _cartao()
    f_id = _fatura(cartao_id)
    _pagar_fatura_direto(f_id, cb_id)

    client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Primeiro',
    })
    _pagar_fatura_direto(f_id, cb_id)
    resp = client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-12', 'motivo': 'Segundo',
    })
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 7. Lancamentos da fatura nao sao alterados
# ---------------------------------------------------------------------------

def test_estorno_fatura_nao_altera_valor_executado(client):
    cb_id = _conta_bancaria()
    cartao_id = _cartao()
    f_id = _fatura(cartao_id)
    _pagar_fatura_direto(f_id, cb_id)

    valor_executado_antes = float(Conta.query.get(f_id).valor_executado)

    client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    valor_executado_depois = float(Conta.query.get(f_id).valor_executado)
    assert valor_executado_antes == valor_executado_depois


def test_estorno_fatura_nao_altera_status_fatura(client):
    cb_id = _conta_bancaria()
    cartao_id = _cartao()
    f_id = _fatura(cartao_id, status='FECHADA')
    _pagar_fatura_direto(f_id, cb_id)

    client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    fatura = Conta.query.get(f_id)
    assert fatura.status_fatura == 'FECHADA'


# ---------------------------------------------------------------------------
# 8. Conferencia de saldo
# ---------------------------------------------------------------------------

def test_conferencia_saldo_consistente_apos_estorno_fatura(client):
    cb_id = _conta_bancaria(Decimal('5000.00'))
    cartao_id = _cartao()
    f_id = _fatura(cartao_id)
    _pagar_fatura_direto(f_id, cb_id)

    client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    resp = client.get(f'/api/contas/{cb_id}/conferir-saldo')
    r = resp.get_json()['data']
    assert r['consistente'] is True
    assert r['divergencia'] == 0.0


# ---------------------------------------------------------------------------
# 9. Atomicidade: falha apos criar movimento, antes do commit
# ---------------------------------------------------------------------------

def test_estorno_fatura_rollback_em_falha_preserva_estado(client, monkeypatch):
    cb_id = _conta_bancaria(Decimal('5000.00'))
    cartao_id = _cartao()
    f_id = _fatura(cartao_id)
    _pagar_fatura_direto(f_id, cb_id)

    saldo_apos_pagamento = float(ContaBancaria.query.get(cb_id).saldo_atual)

    original_commit = db.session.commit

    def _commit_falha(*args, **kwargs):
        raise RuntimeError('Falha simulada antes do commit')

    monkeypatch.setattr(db.session, 'commit', _commit_falha)

    resp = client.post(f'/api/despesas/{f_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 500

    monkeypatch.setattr(db.session, 'commit', original_commit)

    assert MovimentoFinanceiro.query.filter_by(
        conta_id=f_id, origem='ESTORNO_FATURA',
    ).count() == 0
    fatura = Conta.query.get(f_id)
    assert fatura.status_pagamento == 'Pago'
    assert float(ContaBancaria.query.get(cb_id).saldo_atual) == saldo_apos_pagamento
