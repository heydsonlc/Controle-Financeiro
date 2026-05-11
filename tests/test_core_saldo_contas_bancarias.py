"""
Testes CORE-SALDO-1D — Conferência read-only de saldo bancário.

GET /api/contas/<id>/conferir-saldo
- Conta sem movimentos: saldo_calculado == saldo_inicial
- Conta com créditos e débitos: saldo_calculado correto
- Saldo consistente: consistente=True quando saldo_atual == saldo_calculado
- Saldo divergente: consistente=False quando saldo_atual foi alterado manualmente
- Conta inexistente: 404
- Read-only: saldo_atual e movimentos não são alterados pela conferência
"""
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import ContaBancaria, MovimentoFinanceiro, db
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
    app.register_blueprint(contas_bancarias_bp, url_prefix='/api/contas')

    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


def _conta(saldo_inicial=1000.0, saldo_atual=None):
    cb = ContaBancaria(
        nome='Conta Teste',
        instituicao='Banco',
        tipo='Conta Corrente',
        saldo_inicial=Decimal(str(saldo_inicial)),
        saldo_atual=Decimal(str(saldo_atual if saldo_atual is not None else saldo_inicial)),
        status='ATIVO',
    )
    db.session.add(cb)
    db.session.commit()
    return cb.id


def _movimento(conta_id, tipo, valor):
    mov = MovimentoFinanceiro(
        conta_bancaria_id=conta_id,
        tipo=tipo,
        valor=Decimal(str(valor)),
        descricao=f'{tipo} {valor}',
        data_movimento=date(2026, 5, 1),
        origem='MANUAL',
    )
    db.session.add(mov)
    db.session.commit()
    return mov.id


# ---------------------------------------------------------------------------
# 11.1 Conta sem movimentos
# ---------------------------------------------------------------------------

def test_conferencia_sem_movimentos(client):
    cb_id = _conta(saldo_inicial=1000.0)

    resp = client.get(f'/api/contas/{cb_id}/conferir-saldo')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    r = data['data']

    assert r['conta_id'] == cb_id
    assert r['saldo_inicial'] == 1000.0
    assert r['total_creditos'] == 0.0
    assert r['total_debitos'] == 0.0
    assert r['saldo_calculado'] == 1000.0
    assert r['quantidade_movimentos'] == 0


# ---------------------------------------------------------------------------
# 11.2 Conta com créditos e débitos
# ---------------------------------------------------------------------------

def test_conferencia_com_creditos_e_debitos(client):
    cb_id = _conta(saldo_inicial=1000.0, saldo_atual=1250.0)
    _movimento(cb_id, 'CREDITO', 500.0)
    _movimento(cb_id, 'DEBITO', 250.0)

    resp = client.get(f'/api/contas/{cb_id}/conferir-saldo')
    assert resp.status_code == 200
    r = resp.get_json()['data']

    assert r['saldo_inicial'] == 1000.0
    assert r['total_creditos'] == 500.0
    assert r['total_debitos'] == 250.0
    assert r['saldo_calculado'] == 1250.0
    assert r['quantidade_movimentos'] == 2


def test_conferencia_multiplos_movimentos(client):
    cb_id = _conta(saldo_inicial=500.0, saldo_atual=800.0)
    _movimento(cb_id, 'CREDITO', 200.0)
    _movimento(cb_id, 'CREDITO', 300.0)
    _movimento(cb_id, 'DEBITO', 100.0)
    _movimento(cb_id, 'DEBITO', 100.0)

    resp = client.get(f'/api/contas/{cb_id}/conferir-saldo')
    r = resp.get_json()['data']

    assert r['total_creditos'] == 500.0
    assert r['total_debitos'] == 200.0
    assert r['saldo_calculado'] == 800.0
    assert r['quantidade_movimentos'] == 4


# ---------------------------------------------------------------------------
# 11.3 Saldo consistente
# ---------------------------------------------------------------------------

def test_saldo_consistente_quando_igual(client):
    cb_id = _conta(saldo_inicial=1000.0, saldo_atual=1250.0)
    _movimento(cb_id, 'CREDITO', 500.0)
    _movimento(cb_id, 'DEBITO', 250.0)

    r = client.get(f'/api/contas/{cb_id}/conferir-saldo').get_json()['data']

    assert r['saldo_atual'] == 1250.0
    assert r['saldo_calculado'] == 1250.0
    assert r['divergencia'] == 0.0
    assert r['consistente'] is True


def test_saldo_consistente_sem_movimentos_e_igual_ao_inicial(client):
    cb_id = _conta(saldo_inicial=2000.0, saldo_atual=2000.0)

    r = client.get(f'/api/contas/{cb_id}/conferir-saldo').get_json()['data']

    assert r['consistente'] is True
    assert r['divergencia'] == 0.0


# ---------------------------------------------------------------------------
# 11.4 Saldo divergente
# ---------------------------------------------------------------------------

def test_saldo_divergente_quando_diferente(client):
    cb_id = _conta(saldo_inicial=1000.0, saldo_atual=9999.0)
    _movimento(cb_id, 'CREDITO', 500.0)
    _movimento(cb_id, 'DEBITO', 250.0)

    r = client.get(f'/api/contas/{cb_id}/conferir-saldo').get_json()['data']

    assert r['saldo_calculado'] == 1250.0
    assert r['saldo_atual'] == 9999.0
    assert abs(r['divergencia'] - 8749.0) < 0.01
    assert r['consistente'] is False


def test_saldo_divergente_negativo(client):
    cb_id = _conta(saldo_inicial=1000.0, saldo_atual=100.0)

    r = client.get(f'/api/contas/{cb_id}/conferir-saldo').get_json()['data']

    assert r['saldo_calculado'] == 1000.0
    assert r['divergencia'] == pytest.approx(-900.0, abs=0.01)
    assert r['consistente'] is False


def test_tolerancia_centavos_e_consistente(client):
    cb_id = _conta(saldo_inicial=1000.0, saldo_atual=1000.01)

    r = client.get(f'/api/contas/{cb_id}/conferir-saldo').get_json()['data']

    assert r['consistente'] is True


# ---------------------------------------------------------------------------
# 11.5 Conta inexistente
# ---------------------------------------------------------------------------

def test_conta_inexistente_retorna_404(client):
    resp = client.get('/api/contas/99999/conferir-saldo')
    assert resp.status_code == 404
    data = resp.get_json()
    assert data['success'] is False


# ---------------------------------------------------------------------------
# 11.6 Read-only — não altera saldo nem movimentos
# ---------------------------------------------------------------------------

def test_conferencia_nao_altera_saldo_atual(client):
    cb_id = _conta(saldo_inicial=1000.0, saldo_atual=9999.0)

    client.get(f'/api/contas/{cb_id}/conferir-saldo')

    cb = ContaBancaria.query.filter_by(id=cb_id).first()
    assert float(cb.saldo_atual) == 9999.0


def test_conferencia_nao_cria_movimentos(client):
    cb_id = _conta(saldo_inicial=1000.0)

    client.get(f'/api/contas/{cb_id}/conferir-saldo')

    total = MovimentoFinanceiro.query.filter_by(conta_bancaria_id=cb_id).count()
    assert total == 0


def test_conferencia_nao_altera_movimentos_existentes(client):
    cb_id = _conta(saldo_inicial=1000.0, saldo_atual=1500.0)
    mov_id = _movimento(cb_id, 'CREDITO', 500.0)

    client.get(f'/api/contas/{cb_id}/conferir-saldo')

    mov = MovimentoFinanceiro.query.filter_by(id=mov_id).first()
    assert float(mov.valor) == 500.0
    assert mov.tipo == 'CREDITO'


def test_multiplas_conferencias_nao_acumulam_efeitos(client):
    cb_id = _conta(saldo_inicial=1000.0, saldo_atual=1000.0)

    for _ in range(3):
        resp = client.get(f'/api/contas/{cb_id}/conferir-saldo')
        assert resp.status_code == 200
        r = resp.get_json()['data']
        assert r['quantidade_movimentos'] == 0
        assert r['saldo_calculado'] == 1000.0

    cb = ContaBancaria.query.filter_by(id=cb_id).first()
    assert float(cb.saldo_atual) == 1000.0


# ---------------------------------------------------------------------------
# Serviço direto
# ---------------------------------------------------------------------------

def test_service_conferir_saldo_retorna_dict(client):
    cb_id = _conta(saldo_inicial=500.0, saldo_atual=700.0)
    _movimento(cb_id, 'CREDITO', 300.0)
    _movimento(cb_id, 'DEBITO', 100.0)

    resultado = ContaBancariaService.conferir_saldo(cb_id)

    assert isinstance(resultado, dict)
    assert resultado['conta_id'] == cb_id
    assert resultado['saldo_calculado'] == 700.0
    assert resultado['consistente'] is True


def test_service_conferir_saldo_inexistente_retorna_none(client):
    resultado = ContaBancariaService.conferir_saldo(99999)
    assert resultado is None
