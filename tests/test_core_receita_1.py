"""
Testes CORE-RECEITA-1: fluxo protegido de recebimento de receitas.

- POST /realizadas exige conta bancaria e cria receita + movimento em transacao
- Bloqueio de duplicidade: receita ja com movimento nao pode ser recebida de novo
- PUT comum nao pode alterar valor/conta/data de receita com movimento vinculado
- DELETE bloqueia receita com movimento financeiro vinculado
- Conferencia de saldo fica consistente apos recebimento
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
from backend.services.conta_bancaria_service import ContaBancariaService


@pytest.fixture()
def app_context():
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
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


def _criar_conta(saldo=0.0, status='ATIVO'):
    conta = ContaBancaria(
        nome='Conta Teste',
        instituicao='Banco',
        tipo='Conta Corrente',
        saldo_inicial=Decimal(str(saldo)),
        saldo_atual=Decimal(str(saldo)),
        status=status,
    )
    db.session.add(conta)
    db.session.commit()
    return conta


def _criar_fonte(item_receita_id=None, conta_bancaria_id=None):
    item = ItemReceita(
        nome='Salario',
        tipo='SALARIO_FIXO',
        ativo=True,
        recorrente=False,
        conta_bancaria_id=conta_bancaria_id,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _payload_recebimento(item_id, conta_id, valor=1000.0, data='2026-05-05', competencia='2026-05-01'):
    return {
        'item_receita_id': item_id,
        'data_recebimento': data,
        'valor_recebido': valor,
        'competencia': competencia,
        'conta_bancaria_id': conta_id,
        'descricao': 'Recebimento teste',
    }


# ---------------------------------------------------------------------------
# 11.1 Recebimento basico
# ---------------------------------------------------------------------------

def test_recebimento_basico_cria_movimento_credito(client):
    conta = _criar_conta(saldo=500.0)
    item = _criar_fonte()

    resp = client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id, valor=1000.0))

    assert resp.status_code == 201
    body = resp.get_json()
    assert body['success'] is True

    mov = MovimentoFinanceiro.query.filter_by(receita_realizada_id=body['data']['id'], origem='RECEITA').first()
    assert mov is not None
    assert mov.tipo == 'CREDITO'
    assert float(mov.valor) == 1000.0


def test_recebimento_basico_marca_receita_recebida(client):
    conta = _criar_conta()
    item = _criar_fonte()

    resp = client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id))
    body = resp.get_json()

    receita = ReceitaRealizada.query.get(body['data']['id'])
    assert receita is not None
    assert receita.conta_bancaria_id == conta.id


def test_recebimento_basico_aumenta_saldo(client):
    conta = _criar_conta(saldo=500.0)
    item = _criar_fonte()

    client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id, valor=1000.0))

    db.session.refresh(conta)
    assert float(conta.saldo_atual) == 1500.0


# ---------------------------------------------------------------------------
# 11.2 Conta bancaria obrigatoria
# ---------------------------------------------------------------------------

def test_receber_sem_conta_bancaria_retorna_400(client):
    item = _criar_fonte()

    resp = client.post('/api/receitas/realizadas', json={
        'item_receita_id': item.id,
        'data_recebimento': '2026-05-05',
        'valor_recebido': 1000.0,
        'competencia': '2026-05-01',
    })

    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_receber_sem_conta_bancaria_nao_cria_nada(client):
    item = _criar_fonte()

    client.post('/api/receitas/realizadas', json={
        'item_receita_id': item.id,
        'data_recebimento': '2026-05-05',
        'valor_recebido': 1000.0,
        'competencia': '2026-05-01',
    })

    assert ReceitaRealizada.query.count() == 0
    assert MovimentoFinanceiro.query.count() == 0


def test_receber_com_conta_inativa_retorna_erro(client):
    conta = _criar_conta(status='INATIVO')
    item = _criar_fonte()

    resp = client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id))

    assert resp.status_code == 400
    assert ReceitaRealizada.query.count() == 0


# ---------------------------------------------------------------------------
# 11.3 Duplicidade
# ---------------------------------------------------------------------------

def test_segundo_recebimento_da_mesma_receita_via_put_e_bloqueado(client):
    """Apos receber, tentar 'receber de novo' via PUT (mudando conta/valor) deve ser bloqueado."""
    conta = _criar_conta()
    conta2 = _criar_conta()
    item = _criar_fonte()

    resp = client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id, valor=1000.0))
    receita_id = resp.get_json()['data']['id']

    resp2 = client.put(f'/api/receitas/realizadas/{receita_id}', json={
        'item_receita_id': item.id,
        'data_recebimento': '2026-05-05',
        'valor_recebido': 1000.0,
        'competencia': '2026-05-01',
        'conta_bancaria_id': conta2.id,
    })

    assert resp2.status_code == 400
    assert MovimentoFinanceiro.query.filter_by(receita_realizada_id=receita_id, origem='RECEITA').count() == 1


def test_apenas_um_movimento_apos_tentativa_de_duplicidade(client):
    conta = _criar_conta()
    item = _criar_fonte()

    resp = client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id, valor=1000.0))
    receita_id = resp.get_json()['data']['id']

    client.put(f'/api/receitas/realizadas/{receita_id}', json={
        'valor_recebido': 2000.0,
    })

    assert MovimentoFinanceiro.query.filter_by(receita_realizada_id=receita_id).count() == 1


# ---------------------------------------------------------------------------
# 11.4 PUT nao realiza receita indevidamente / 11.6 PUT nao altera valor
# ---------------------------------------------------------------------------

def test_put_altera_valor_de_receita_com_movimento_e_bloqueado(client):
    conta = _criar_conta()
    item = _criar_fonte()
    resp = client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id, valor=1000.0))
    receita_id = resp.get_json()['data']['id']

    resp2 = client.put(f'/api/receitas/realizadas/{receita_id}', json={'valor_recebido': 5000.0})

    assert resp2.status_code == 400
    db.session.refresh(ReceitaRealizada.query.get(receita_id))
    assert float(ReceitaRealizada.query.get(receita_id).valor_recebido) == 1000.0


def test_put_altera_data_recebimento_de_receita_com_movimento_e_bloqueado(client):
    conta = _criar_conta()
    item = _criar_fonte()
    resp = client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id))
    receita_id = resp.get_json()['data']['id']

    resp2 = client.put(f'/api/receitas/realizadas/{receita_id}', json={'data_recebimento': '2026-06-01'})

    assert resp2.status_code == 400


def test_put_campos_neutros_continua_permitido(client):
    """Descricao/observacoes podem ser editadas mesmo com movimento vinculado."""
    conta = _criar_conta()
    item = _criar_fonte()
    resp = client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id))
    receita_id = resp.get_json()['data']['id']

    resp2 = client.put(f'/api/receitas/realizadas/{receita_id}', json={
        'valor_recebido': 1000.0,
        'data_recebimento': '2026-05-05',
        'conta_bancaria_id': conta.id,
        'descricao': 'Descricao atualizada',
    })

    assert resp2.status_code == 200
    assert resp2.get_json()['data']['descricao'] == 'Descricao atualizada'


# ---------------------------------------------------------------------------
# 11.5 PUT nao desfaz recebimento
# ---------------------------------------------------------------------------

def test_put_nao_remove_conta_bancaria_de_receita_recebida(client):
    conta = _criar_conta()
    item = _criar_fonte()
    resp = client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id))
    receita_id = resp.get_json()['data']['id']

    resp2 = client.put(f'/api/receitas/realizadas/{receita_id}', json={'conta_bancaria_id': None})

    assert resp2.status_code == 400
    assert ReceitaRealizada.query.get(receita_id).conta_bancaria_id == conta.id


# ---------------------------------------------------------------------------
# 11.7 / 11.8 DELETE bloqueia receita com movimento
# ---------------------------------------------------------------------------

def test_delete_receita_com_movimento_retorna_409(client):
    conta = _criar_conta()
    item = _criar_fonte()
    resp = client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id))
    receita_id = resp.get_json()['data']['id']

    resp2 = client.delete(f'/api/receitas/realizadas/{receita_id}')

    assert resp2.status_code == 409
    assert resp2.get_json()['success'] is False


def test_delete_receita_com_movimento_preserva_movimento_e_saldo(client):
    conta = _criar_conta(saldo=500.0)
    item = _criar_fonte()
    resp = client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id, valor=1000.0))
    receita_id = resp.get_json()['data']['id']

    client.delete(f'/api/receitas/realizadas/{receita_id}')

    assert ReceitaRealizada.query.get(receita_id) is not None
    assert MovimentoFinanceiro.query.filter_by(receita_realizada_id=receita_id).count() == 1
    db.session.refresh(conta)
    assert float(conta.saldo_atual) == 1500.0


def test_delete_receita_sem_movimento_funciona(client):
    """Receita 'pendente de confirmacao' (sem movimento) ainda pode ser excluida."""
    item = _criar_fonte()
    receita = ReceitaRealizada(
        item_receita_id=item.id,
        data_recebimento=date(2026, 5, 5),
        valor_recebido=Decimal('500.00'),
        mes_referencia=date(2026, 5, 1),
        descricao='Pendente',
    )
    db.session.add(receita)
    db.session.commit()
    receita_id = receita.id

    resp = client.delete(f'/api/receitas/realizadas/{receita_id}')

    assert resp.status_code == 200
    assert ReceitaRealizada.query.get(receita_id) is None


def test_delete_receita_inexistente_retorna_404(client):
    resp = client.delete('/api/receitas/realizadas/99999')
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 11.10 Conferencia de saldo
# ---------------------------------------------------------------------------

def test_conferencia_saldo_consistente_apos_recebimento(client):
    conta = _criar_conta(saldo=500.0)
    item = _criar_fonte()

    client.post('/api/receitas/realizadas', json=_payload_recebimento(item.id, conta.id, valor=1000.0))

    resp = client.get(f'/api/contas/{conta.id}/conferir-saldo')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['data']['consistente'] is True
