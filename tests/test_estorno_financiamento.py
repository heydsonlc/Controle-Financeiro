"""
Testes CORE-ESTORNO-4 — Estorno de pagamento direto de parcela de financiamento.

POST /api/financiamentos/parcelas/<id>/estornar-pagamento
- Parcela paga diretamente pode ser estornada
- Movimento original DEBITO e preservado
- Movimento compensatorio CREDITO e criado com origem=ESTORNO_FINANCIAMENTO
- Saldo bancario e recomposto
- Parcela volta para pendente
- saldo_devedor_atual e recomposto
- Motivo/data obrigatorios
- Parcela pendente nao pode ser estornada
- Parcela sem movimento nao pode ser estornada
- Estorno duplicado e bloqueado
- Parcela com despesa vinculada paga bloqueia estorno direto
- So a parcela paga mais recente pode ser estornada (protege cadeia de saldo)
"""
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import (
    Conta,
    ContaBancaria,
    Financiamento,
    FinanciamentoParcela,
    ItemDespesa,
    MovimentoFinanceiro,
    db,
)
from backend.routes.financiamentos import financiamentos_bp
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
    app.register_blueprint(financiamentos_bp, url_prefix='/api/financiamentos')
    app.register_blueprint(contas_bancarias_bp, url_prefix='/api/contas')

    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


def _financiamento(valor_financiado=Decimal('100000.00')):
    fin = Financiamento(
        nome='Financiamento Teste',
        sistema_amortizacao='SAC',
        valor_financiado=valor_financiado,
        prazo_total_meses=360,
        prazo_remanescente_meses=360,
        taxa_juros_nominal_anual=Decimal('8.0000'),
        taxa_juros_mensal=Decimal('0.006434'),
        data_contrato=date(2025, 1, 1),
        data_primeira_parcela=date(2025, 2, 1),
        saldo_devedor_atual=valor_financiado,
    )
    db.session.add(fin)
    db.session.flush()
    return fin.id


def _parcela(financiamento_id, numero, valor_previsto=1500.0, saldo_devedor_apos=None):
    parcela = FinanciamentoParcela(
        financiamento_id=financiamento_id,
        numero_parcela=numero,
        data_vencimento=date(2026, 4 + numero, 1),
        valor_amortizacao=Decimal('800.00'),
        valor_juros=Decimal('500.00'),
        valor_previsto_total=Decimal(str(valor_previsto)),
        status='pendente',
        saldo_devedor_apos_pagamento=Decimal(str(saldo_devedor_apos)) if saldo_devedor_apos is not None else None,
    )
    db.session.add(parcela)
    db.session.flush()
    return parcela.id


def _conta_bancaria(status='ATIVO', saldo=10000.0):
    cb = ContaBancaria(
        nome='Corrente', instituicao='Banco', tipo='Conta Corrente',
        saldo_inicial=Decimal(str(saldo)), saldo_atual=Decimal(str(saldo)), status=status,
    )
    db.session.add(cb)
    db.session.flush()
    return cb.id


def _pagar_direto(client, parcela_id, cb_id, data='2026-05-10'):
    resp = client.post(f'/api/financiamentos/parcelas/{parcela_id}/pagar', json={
        'conta_bancaria_id': cb_id, 'data_pagamento': data,
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return parcela_id


# ---------------------------------------------------------------------------
# 1. Parcela paga diretamente pode ser estornada
# ---------------------------------------------------------------------------

def test_estorno_basico_cria_movimento_credito(client):
    fin_id = _financiamento()
    parcela_id = _parcela(fin_id, 1, valor_previsto=1300.0)
    cb_id = _conta_bancaria(saldo=5000.0)
    db.session.commit()
    _pagar_direto(client, parcela_id, cb_id)

    resp = client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Pagamento por engano',
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['valor_estornado'] == 1300.0
    assert data['data']['status'] == 'pendente'

    mov_estorno = MovimentoFinanceiro.query.filter_by(
        financiamento_parcela_id=parcela_id, origem='ESTORNO_FINANCIAMENTO',
    ).first()
    assert mov_estorno is not None
    assert mov_estorno.tipo == 'CREDITO'
    assert float(mov_estorno.valor) == 1300.0


def test_estorno_preserva_movimento_original(client):
    fin_id = _financiamento()
    parcela_id = _parcela(fin_id, 1, valor_previsto=1300.0)
    cb_id = _conta_bancaria()
    db.session.commit()
    _pagar_direto(client, parcela_id, cb_id)

    client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    mov_original = MovimentoFinanceiro.query.filter_by(
        financiamento_parcela_id=parcela_id, origem='FINANCIAMENTO', tipo='DEBITO',
    ).first()
    assert mov_original is not None
    assert float(mov_original.valor) == 1300.0


def test_estorno_parcela_volta_para_pendente(client):
    fin_id = _financiamento()
    parcela_id = _parcela(fin_id, 1, valor_previsto=1300.0)
    cb_id = _conta_bancaria()
    db.session.commit()
    _pagar_direto(client, parcela_id, cb_id)

    client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    parcela = FinanciamentoParcela.query.get(parcela_id)
    assert parcela.status == 'pendente'
    assert float(parcela.valor_pago) == 0.0


def test_estorno_saldo_bancario_compensado(client):
    fin_id = _financiamento()
    parcela_id = _parcela(fin_id, 1, valor_previsto=1300.0)
    cb_id = _conta_bancaria(saldo=5000.0)
    db.session.commit()
    _pagar_direto(client, parcela_id, cb_id)

    saldo_apos_pagamento = float(ContaBancaria.query.get(cb_id).saldo_atual)
    assert saldo_apos_pagamento == 3700.0

    client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    saldo_apos_estorno = float(ContaBancaria.query.get(cb_id).saldo_atual)
    assert saldo_apos_estorno == 5000.0


def test_estorno_recompoe_saldo_devedor_primeira_parcela(client):
    fin_id = _financiamento(valor_financiado=Decimal('100000.00'))
    parcela_id = _parcela(fin_id, 1, valor_previsto=1300.0, saldo_devedor_apos=99200.00)
    cb_id = _conta_bancaria()
    db.session.commit()
    _pagar_direto(client, parcela_id, cb_id)

    financiamento = Financiamento.query.get(fin_id)
    assert float(financiamento.saldo_devedor_atual) == 99200.00

    resp = client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 200

    financiamento = Financiamento.query.get(fin_id)
    assert float(financiamento.saldo_devedor_atual) == 100000.00


def test_estorno_recompoe_saldo_devedor_com_parcela_anterior(client):
    fin_id = _financiamento(valor_financiado=Decimal('100000.00'))
    _parcela(fin_id, 1, valor_previsto=1300.0, saldo_devedor_apos=99200.00)
    parcela2_id = _parcela(fin_id, 2, valor_previsto=1300.0, saldo_devedor_apos=98400.00)
    cb_id = _conta_bancaria()
    db.session.commit()
    _pagar_direto(client, parcela2_id, cb_id)

    client.post(f'/api/financiamentos/parcelas/{parcela2_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    financiamento = Financiamento.query.get(fin_id)
    assert float(financiamento.saldo_devedor_atual) == 99200.00


# ---------------------------------------------------------------------------
# 2/3. Motivo e data obrigatorios
# ---------------------------------------------------------------------------

def test_estorno_sem_motivo_retorna_400(client):
    fin_id = _financiamento()
    parcela_id = _parcela(fin_id, 1)
    cb_id = _conta_bancaria()
    db.session.commit()
    _pagar_direto(client, parcela_id, cb_id)

    resp = client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11',
    })
    assert resp.status_code == 400


def test_estorno_sem_data_retorna_400(client):
    fin_id = _financiamento()
    parcela_id = _parcela(fin_id, 1)
    cb_id = _conta_bancaria()
    db.session.commit()
    _pagar_direto(client, parcela_id, cb_id)

    resp = client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'motivo': 'Engano',
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. Parcela pendente nao pode ser estornada
# ---------------------------------------------------------------------------

def test_estorno_parcela_pendente_retorna_409(client):
    fin_id = _financiamento()
    parcela_id = _parcela(fin_id, 1)
    db.session.commit()

    resp = client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 5. Parcela sem movimento
# ---------------------------------------------------------------------------

def test_estorno_parcela_sem_movimento_retorna_422(client):
    fin_id = _financiamento()
    parcela_id = _parcela(fin_id, 1)
    parcela = FinanciamentoParcela.query.get(parcela_id)
    parcela.status = 'pago'
    parcela.valor_pago = Decimal('1500.00')
    db.session.commit()

    resp = client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 6. Estorno duplicado
# ---------------------------------------------------------------------------

def test_estorno_duplicado_retorna_409(client):
    fin_id = _financiamento()
    parcela_id = _parcela(fin_id, 1, valor_previsto=1300.0)
    cb_id = _conta_bancaria(saldo=10000.0)
    db.session.commit()
    _pagar_direto(client, parcela_id, cb_id)

    client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Primeiro',
    })
    _pagar_direto(client, parcela_id, cb_id, data='2026-05-12')
    resp = client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-13', 'motivo': 'Segundo',
    })
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 7. Parcela com despesa vinculada paga bloqueia estorno direto
# ---------------------------------------------------------------------------

def test_estorno_parcela_com_despesa_vinculada_paga_retorna_409(client):
    fin_id = _financiamento()
    parcela_id = _parcela(fin_id, 1, valor_previsto=1500.0)

    item = ItemDespesa(nome='Item Fin', tipo='Simples', ativo=True)
    db.session.add(item)
    db.session.flush()

    despesa = Conta(
        item_despesa_id=item.id,
        mes_referencia=date(2026, 5, 1),
        data_vencimento=date(2026, 5, 10),
        descricao='Parcela via despesa',
        valor=Decimal('1500.00'),
        status_pagamento='Pago',
        data_pagamento=date(2026, 5, 10),
        financiamento_parcela_id=parcela_id,
    )
    db.session.add(despesa)

    parcela = FinanciamentoParcela.query.get(parcela_id)
    parcela.status = 'pago'
    parcela.valor_pago = Decimal('1500.00')
    db.session.commit()

    resp = client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 409
    assert 'despesa' in resp.get_json()['error'].lower()


def test_estorno_parcela_com_despesa_vinculada_nao_cria_movimento(client):
    fin_id = _financiamento()
    parcela_id = _parcela(fin_id, 1, valor_previsto=1500.0)

    item = ItemDespesa(nome='Item Fin', tipo='Simples', ativo=True)
    db.session.add(item)
    db.session.flush()

    despesa = Conta(
        item_despesa_id=item.id,
        mes_referencia=date(2026, 5, 1),
        data_vencimento=date(2026, 5, 10),
        descricao='Parcela via despesa',
        valor=Decimal('1500.00'),
        status_pagamento='Pago',
        data_pagamento=date(2026, 5, 10),
        financiamento_parcela_id=parcela_id,
    )
    db.session.add(despesa)
    parcela = FinanciamentoParcela.query.get(parcela_id)
    parcela.status = 'pago'
    db.session.commit()

    client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    assert MovimentoFinanceiro.query.filter_by(
        financiamento_parcela_id=parcela_id, origem='ESTORNO_FINANCIAMENTO',
    ).count() == 0


# ---------------------------------------------------------------------------
# 8. So a parcela paga mais recente pode ser estornada
# ---------------------------------------------------------------------------

def test_estorno_parcela_com_parcela_posterior_paga_e_bloqueado(client):
    fin_id = _financiamento()
    parcela1_id = _parcela(fin_id, 1, valor_previsto=1300.0)
    parcela2_id = _parcela(fin_id, 2, valor_previsto=1300.0)
    cb_id = _conta_bancaria(saldo=10000.0)
    db.session.commit()
    _pagar_direto(client, parcela1_id, cb_id, data='2026-05-10')
    _pagar_direto(client, parcela2_id, cb_id, data='2026-06-10')

    resp = client.post(f'/api/financiamentos/parcelas/{parcela1_id}/estornar-pagamento', json={
        'data_estorno': '2026-06-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 409


def test_estorno_parcela_mais_recente_e_permitido(client):
    fin_id = _financiamento()
    parcela1_id = _parcela(fin_id, 1, valor_previsto=1300.0)
    parcela2_id = _parcela(fin_id, 2, valor_previsto=1300.0)
    cb_id = _conta_bancaria(saldo=10000.0)
    db.session.commit()
    _pagar_direto(client, parcela1_id, cb_id, data='2026-05-10')
    _pagar_direto(client, parcela2_id, cb_id, data='2026-06-10')

    resp = client.post(f'/api/financiamentos/parcelas/{parcela2_id}/estornar-pagamento', json={
        'data_estorno': '2026-06-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 9. Conferencia de saldo apos estorno
# ---------------------------------------------------------------------------

def test_conferencia_saldo_consistente_apos_estorno(client):
    fin_id = _financiamento()
    parcela_id = _parcela(fin_id, 1, valor_previsto=1300.0)
    cb_id = _conta_bancaria(saldo=5000.0)
    db.session.commit()
    _pagar_direto(client, parcela_id, cb_id)

    client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    resp = client.get(f'/api/contas/{cb_id}/conferir-saldo')
    r = resp.get_json()['data']
    assert r['consistente'] is True
    assert r['divergencia'] == 0.0


# ---------------------------------------------------------------------------
# 10. Parcela inexistente
# ---------------------------------------------------------------------------

def test_estorno_parcela_inexistente_retorna_404(client):
    resp = client.post('/api/financiamentos/parcelas/99999/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 11. Atomicidade: falha apos criar movimento, antes do commit
# ---------------------------------------------------------------------------

def test_estorno_rollback_em_falha_preserva_estado(client, monkeypatch):
    fin_id = _financiamento(valor_financiado=Decimal('100000.00'))
    parcela_id = _parcela(fin_id, 1, valor_previsto=1300.0, saldo_devedor_apos=99200.00)
    cb_id = _conta_bancaria(saldo=5000.0)
    db.session.commit()
    _pagar_direto(client, parcela_id, cb_id)

    saldo_apos_pagamento = float(ContaBancaria.query.get(cb_id).saldo_atual)
    saldo_devedor_apos_pagamento = float(Financiamento.query.get(fin_id).saldo_devedor_atual)

    original_commit = db.session.commit

    def _commit_falha(*args, **kwargs):
        raise RuntimeError('Falha simulada antes do commit')

    monkeypatch.setattr(db.session, 'commit', _commit_falha)

    resp = client.post(f'/api/financiamentos/parcelas/{parcela_id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 500

    monkeypatch.setattr(db.session, 'commit', original_commit)

    assert MovimentoFinanceiro.query.filter_by(
        financiamento_parcela_id=parcela_id, origem='ESTORNO_FINANCIAMENTO',
    ).count() == 0
    parcela = FinanciamentoParcela.query.get(parcela_id)
    assert parcela.status == 'pago'
    assert float(ContaBancaria.query.get(cb_id).saldo_atual) == saldo_apos_pagamento
    assert float(Financiamento.query.get(fin_id).saldo_devedor_atual) == saldo_devedor_apos_pagamento
