"""
Testes CORE-ESTORNO-2 — Estorno de receita realizada.

POST /api/receitas/realizadas/<id>/estornar
- Estorno basico cria movimento de debito compensatorio, preserva o original
- Estorno exige motivo (400)
- Estorno exige data_estorno (400)
- Receita sem movimento (pendente de confirmacao) nao pode ser estornada (422)
- Estorno duplicado e bloqueado (409)
- Saldo bancario compensado apos estorno
- Conferencia de saldo permanece consistente
- Rollback em falha preserva tudo
"""
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import (
    ContaBancaria,
    ItemReceita,
    MovimentoFinanceiro,
    ReceitaRealizada,
    db,
)
from backend.routes.receitas import receitas_bp
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
    app.register_blueprint(receitas_bp, url_prefix='/api/receitas')
    app.register_blueprint(contas_bancarias_bp, url_prefix='/api/contas')

    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


def _conta_bancaria(saldo=Decimal('1000.00')):
    cb = ContaBancaria(
        nome='Conta Teste', instituicao='Banco', tipo='Conta Corrente',
        saldo_inicial=saldo, saldo_atual=saldo, status='ATIVO',
    )
    db.session.add(cb)
    db.session.commit()
    return cb.id


def _item_receita():
    item = ItemReceita(nome='Fonte Teste', tipo='OUTROS', ativo=True, recorrente=False)
    db.session.add(item)
    db.session.commit()
    return item.id


def _receber(client, item_id, cb_id, valor=1000.0, data='2026-05-05'):
    resp = client.post('/api/receitas/realizadas', json={
        'item_receita_id': item_id,
        'data_recebimento': data,
        'valor_recebido': valor,
        'competencia': '2026-05-01',
        'conta_bancaria_id': cb_id,
    })
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()['data']['id']


# ---------------------------------------------------------------------------
# 1. Estorno basico
# ---------------------------------------------------------------------------

def test_estorno_basico_cria_movimento_debito(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_receita()
    r_id = _receber(client, item_id, cb_id, valor=1000.0)

    resp = client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': 'Recebimento por engano',
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['valor_estornado'] == 1000.0

    mov_estorno = MovimentoFinanceiro.query.filter_by(
        receita_realizada_id=r_id, origem='ESTORNO_RECEITA',
    ).first()
    assert mov_estorno is not None
    assert mov_estorno.tipo == 'DEBITO'
    assert float(mov_estorno.valor) == 1000.0


def test_estorno_preserva_movimento_original(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_receita()
    r_id = _receber(client, item_id, cb_id, valor=1000.0)

    client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    mov_original = MovimentoFinanceiro.query.filter_by(
        receita_realizada_id=r_id, origem='RECEITA',
    ).first()
    assert mov_original is not None
    assert mov_original.tipo == 'CREDITO'
    assert float(mov_original.valor) == 1000.0

    receita = ReceitaRealizada.query.get(r_id)
    assert receita is not None


def test_estorno_registra_motivo_em_observacoes(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_receita()
    r_id = _receber(client, item_id, cb_id)

    client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': 'Teste motivo receita',
    })

    receita = ReceitaRealizada.query.get(r_id)
    assert 'ESTORNO' in (receita.observacoes or '')
    assert 'Teste motivo receita' in (receita.observacoes or '')


def test_estorno_saldo_compensado(client):
    cb_id = _conta_bancaria(Decimal('500.00'))
    item_id = _item_receita()
    r_id = _receber(client, item_id, cb_id, valor=1000.0)

    saldo_apos_recebimento = float(ContaBancaria.query.get(cb_id).saldo_atual)
    assert saldo_apos_recebimento == 1500.0

    client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    saldo_apos_estorno = float(ContaBancaria.query.get(cb_id).saldo_atual)
    assert saldo_apos_estorno == 500.0


# ---------------------------------------------------------------------------
# 2/3. Motivo e data obrigatorios
# ---------------------------------------------------------------------------

def test_estorno_sem_motivo_retorna_400(client):
    cb_id = _conta_bancaria()
    item_id = _item_receita()
    r_id = _receber(client, item_id, cb_id)

    resp = client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-11',
    })
    assert resp.status_code == 400


def test_estorno_motivo_vazio_retorna_400(client):
    cb_id = _conta_bancaria()
    item_id = _item_receita()
    r_id = _receber(client, item_id, cb_id)

    resp = client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': '   ',
    })
    assert resp.status_code == 400


def test_estorno_sem_data_retorna_400(client):
    cb_id = _conta_bancaria()
    item_id = _item_receita()
    r_id = _receber(client, item_id, cb_id)

    resp = client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'motivo': 'Engano',
    })
    assert resp.status_code == 400


def test_estorno_data_invalida_retorna_400(client):
    cb_id = _conta_bancaria()
    item_id = _item_receita()
    r_id = _receber(client, item_id, cb_id)

    resp = client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': 'nao-e-data', 'motivo': 'Engano',
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. Receita sem movimento (pendente de confirmacao) nao pode ser estornada
# ---------------------------------------------------------------------------

def test_estorno_receita_sem_movimento_retorna_422(client):
    item_id = _item_receita()
    receita = ReceitaRealizada(
        item_receita_id=item_id,
        data_recebimento=date(2026, 5, 5),
        valor_recebido=Decimal('500.00'),
        mes_referencia=date(2026, 5, 1),
        descricao='Pendente de confirmacao',
    )
    db.session.add(receita)
    db.session.commit()
    r_id = receita.id

    resp = client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 422


def test_estorno_receita_sem_movimento_nao_altera_receita(client):
    item_id = _item_receita()
    receita = ReceitaRealizada(
        item_receita_id=item_id,
        data_recebimento=date(2026, 5, 5),
        valor_recebido=Decimal('500.00'),
        mes_referencia=date(2026, 5, 1),
        descricao='Pendente',
    )
    db.session.add(receita)
    db.session.commit()
    r_id = receita.id

    client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    receita_after = ReceitaRealizada.query.get(r_id)
    assert receita_after.observacoes in (None, '')


# ---------------------------------------------------------------------------
# 5. Estorno duplicado
# ---------------------------------------------------------------------------

def test_estorno_duplicado_retorna_409(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_receita()
    r_id = _receber(client, item_id, cb_id)

    client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': 'Primeiro',
    })
    resp = client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-12', 'motivo': 'Segundo',
    })
    assert resp.status_code == 409


def test_estorno_duplicado_nao_cria_segundo_movimento(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_receita()
    r_id = _receber(client, item_id, cb_id)

    client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': 'Primeiro',
    })
    client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-12', 'motivo': 'Segundo',
    })

    total = MovimentoFinanceiro.query.filter_by(
        receita_realizada_id=r_id, origem='ESTORNO_RECEITA',
    ).count()
    assert total == 1


# ---------------------------------------------------------------------------
# 6. Conferencia de saldo apos estorno
# ---------------------------------------------------------------------------

def test_conferencia_saldo_consistente_apos_estorno(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_receita()
    r_id = _receber(client, item_id, cb_id, valor=500.0)

    client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    resp = client.get(f'/api/contas/{cb_id}/conferir-saldo')
    assert resp.status_code == 200
    r = resp.get_json()['data']
    assert r['consistente'] is True
    assert r['divergencia'] == 0.0
    assert r['saldo_calculado'] == 1000.0


# ---------------------------------------------------------------------------
# 7. Receita inexistente
# ---------------------------------------------------------------------------

def test_estorno_receita_inexistente_retorna_404(client):
    resp = client.post('/api/receitas/realizadas/99999/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. Atomicidade: falha apos observacao setada, antes do commit
# ---------------------------------------------------------------------------

def test_estorno_rollback_em_falha_preserva_estado(client, monkeypatch):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item_id = _item_receita()
    r_id = _receber(client, item_id, cb_id, valor=1000.0)

    saldo_apos_recebimento = float(ContaBancaria.query.get(cb_id).saldo_atual)
    assert saldo_apos_recebimento == 2000.0

    original_commit = db.session.commit

    def _commit_falha(*args, **kwargs):
        raise RuntimeError('Falha simulada antes do commit')

    monkeypatch.setattr(db.session, 'commit', _commit_falha)

    resp = client.post(f'/api/receitas/realizadas/{r_id}/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 500

    monkeypatch.setattr(db.session, 'commit', original_commit)

    assert MovimentoFinanceiro.query.filter_by(
        receita_realizada_id=r_id, origem='ESTORNO_RECEITA',
    ).count() == 0
    assert float(ContaBancaria.query.get(cb_id).saldo_atual) == saldo_apos_recebimento
