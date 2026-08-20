"""
Testes CARD-CVV-LOCK-1 — Bloqueio de visibilidade do CVV com desbloqueio por senha.

- API padrao (listagem, detalhe, to_dict) nunca expoe codigo_seguranca
- Revelacao exige senha de desbloqueio (POST /cartoes/<id>/codigo-seguranca)
- Falha fechada: sem CARTOES_CVV_MASTER_PASSWORD configurada, nunca revela
- Endpoint e POST (GET nao existe / 405)
- Cartao sem CVV cadastrado nao quebra e nao revela nada
"""
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import ConfigAgregador, ItemDespesa, db
from backend.routes.cartoes import cartoes_bp


@pytest.fixture()
def app_sem_senha():
    """App SEM CARTOES_CVV_MASTER_PASSWORD configurada — cenario de falha fechada."""
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    app.config['CARTOES_CVV_MASTER_PASSWORD'] = None
    db.init_app(app)
    app.register_blueprint(cartoes_bp)

    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def app_sem_senha_mas_com_secret_key():
    """Reproduz o cenario real do diagnostico: CARTOES_CVV_MASTER_PASSWORD
    ausente, mas SECRET_KEY presente com um valor previsivel (como o
    .env.local tinha antes da correcao). Retorna (app, client) porque o teste
    precisa de app_context proprio para criar dados antes de usar o client."""
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    app.config['CARTOES_CVV_MASTER_PASSWORD'] = None
    app.config['SECRET_KEY'] = 'segredo-do-flask-secret-key'
    db.init_app(app)
    app.register_blueprint(cartoes_bp)

    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield app, c
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def app_com_senha():
    """App COM CARTOES_CVV_MASTER_PASSWORD configurada — fluxo normal."""
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    app.config['CARTOES_CVV_MASTER_PASSWORD'] = 'senha-correta-teste'
    app.config['SECRET_KEY'] = 'nao-deve-funcionar-como-senha-cvv'
    db.init_app(app)
    app.register_blueprint(cartoes_bp)

    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


def _criar_cartao_com_cvv(codigo_seguranca='123', numero_cartao='1234 5678 9012 3456'):
    cartao = ItemDespesa(nome='Cartao Teste', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add(cartao)
    db.session.flush()
    config = ConfigAgregador(
        item_despesa_id=cartao.id,
        dia_fechamento=25,
        dia_vencimento=5,
        limite_credito=Decimal('5000.00'),
        numero_cartao=numero_cartao,
        codigo_seguranca=codigo_seguranca,
        tem_codigo=True,
    )
    db.session.add(config)
    db.session.commit()
    return cartao.id


def _criar_cartao_sem_cvv():
    cartao = ItemDespesa(nome='Cartao Sem CVV', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add(cartao)
    db.session.flush()
    config = ConfigAgregador(
        item_despesa_id=cartao.id,
        dia_fechamento=25,
        dia_vencimento=5,
        codigo_seguranca=None,
        tem_codigo=False,
    )
    db.session.add(config)
    db.session.commit()
    return cartao.id


# ---------------------------------------------------------------------------
# 13.1. API padrao nao expoe CVV
# ---------------------------------------------------------------------------

def test_listagem_nao_retorna_codigo_seguranca(app_com_senha):
    _criar_cartao_com_cvv()

    resp = app_com_senha.get('/api/cartoes')
    assert resp.status_code == 200
    body = resp.get_json()
    cartoes = body if isinstance(body, list) else body.get('data', [])
    assert len(cartoes) == 1
    config = cartoes[0]['config']
    assert 'codigo_seguranca' not in config
    assert 'cvv' not in config
    assert 'security_code' not in config


def test_listagem_retorna_possui_cvv(app_com_senha):
    _criar_cartao_com_cvv()

    resp = app_com_senha.get('/api/cartoes')
    body = resp.get_json()
    cartoes = body if isinstance(body, list) else body.get('data', [])
    assert cartoes[0]['config']['possui_cvv'] is True


def test_detalhe_cartao_nao_retorna_codigo_seguranca(app_com_senha):
    cartao_id = _criar_cartao_com_cvv()

    resp = app_com_senha.get(f'/api/cartoes/{cartao_id}')
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'codigo_seguranca' not in body['config']
    assert body['config']['possui_cvv'] is True


def test_to_dict_config_agregador_nao_expoe_cvv():
    """Teste direto do model, sem passar pelo HTTP."""
    from datetime import datetime
    config = ConfigAgregador(
        item_despesa_id=1, dia_fechamento=10, dia_vencimento=20,
        codigo_seguranca='999',
    )
    resultado = config.to_dict()
    assert 'codigo_seguranca' not in resultado
    assert 'cvv' not in resultado
    assert 'security_code' not in resultado
    assert resultado['possui_cvv'] is True


def test_to_dict_config_agregador_possui_cvv_false_sem_codigo():
    config = ConfigAgregador(
        item_despesa_id=1, dia_fechamento=10, dia_vencimento=20,
        codigo_seguranca=None,
    )
    resultado = config.to_dict()
    assert resultado['possui_cvv'] is False


# ---------------------------------------------------------------------------
# 13.2. Revelacao exige senha
# ---------------------------------------------------------------------------

def test_revelar_sem_senha_retorna_erro(app_com_senha):
    cartao_id = _criar_cartao_com_cvv()

    resp = app_com_senha.post(f'/api/cartoes/{cartao_id}/codigo-seguranca', json={})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body['success'] is False


def test_revelar_com_senha_vazia_retorna_erro(app_com_senha):
    cartao_id = _criar_cartao_com_cvv()

    resp = app_com_senha.post(f'/api/cartoes/{cartao_id}/codigo-seguranca', json={'senha': '   '})
    assert resp.status_code == 400


def test_revelar_com_senha_errada_retorna_erro(app_com_senha):
    cartao_id = _criar_cartao_com_cvv()

    resp = app_com_senha.post(f'/api/cartoes/{cartao_id}/codigo-seguranca', json={'senha': 'senha-errada'})
    assert resp.status_code == 401
    body = resp.get_json()
    assert body['success'] is False
    assert 'codigo_seguranca' not in str(body)


def test_revelar_com_secret_key_nao_funciona(app_sem_senha_mas_com_secret_key):
    """SECRET_KEY nunca deve servir como senha de desbloqueio de CVV, mesmo
    quando CARTOES_CVV_MASTER_PASSWORD nao esta configurada — cenario real do
    bug encontrado no diagnostico (fallback perigoso ja removido do codigo,
    este teste garante que nao volte)."""
    app, client = app_sem_senha_mas_com_secret_key
    with app.app_context():
        cartao_id = _criar_cartao_com_cvv()

    resp = client.post(
        f'/api/cartoes/{cartao_id}/codigo-seguranca',
        json={'senha': 'segredo-do-flask-secret-key'},
    )
    # Sem CARTOES_CVV_MASTER_PASSWORD configurada, deve falhar fechado (503),
    # nunca aceitar SECRET_KEY como substituto e nunca revelar o CVV.
    assert resp.status_code == 503
    assert resp.get_json()['success'] is False


def test_revelar_com_senha_correta_retorna_cvv(app_com_senha):
    cartao_id = _criar_cartao_com_cvv(codigo_seguranca='456')

    resp = app_com_senha.post(
        f'/api/cartoes/{cartao_id}/codigo-seguranca',
        json={'senha': 'senha-correta-teste'},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['data']['codigo_seguranca'] == '456'
    assert body['data']['expires_in_seconds'] == 30


def test_revelar_com_senha_correta_nao_faz_cache(app_com_senha):
    cartao_id = _criar_cartao_com_cvv()

    resp = app_com_senha.post(
        f'/api/cartoes/{cartao_id}/codigo-seguranca',
        json={'senha': 'senha-correta-teste'},
    )
    assert resp.headers.get('Cache-Control') == 'no-store'


# ---------------------------------------------------------------------------
# 13.3. Falha fechada
# ---------------------------------------------------------------------------

def test_sem_senha_mestre_configurada_retorna_503(app_sem_senha):
    cartao_id = _criar_cartao_com_cvv()

    resp = app_sem_senha.post(
        f'/api/cartoes/{cartao_id}/codigo-seguranca',
        json={'senha': 'qualquer-coisa'},
    )
    assert resp.status_code == 503
    body = resp.get_json()
    assert body['success'] is False
    assert 'codigo_seguranca' not in str(body)


def test_sem_senha_mestre_nao_vaza_cvv_mesmo_com_payload_correto(app_sem_senha):
    cartao_id = _criar_cartao_com_cvv(codigo_seguranca='789')

    resp = app_sem_senha.post(
        f'/api/cartoes/{cartao_id}/codigo-seguranca',
        json={'senha': '789'},
    )
    assert resp.status_code == 503
    assert '789' not in resp.get_data(as_text=True)


# ---------------------------------------------------------------------------
# 13.4. Nao aceitar GET
# ---------------------------------------------------------------------------

def test_get_no_endpoint_de_revelar_retorna_405(app_com_senha):
    cartao_id = _criar_cartao_com_cvv()

    resp = app_com_senha.get(f'/api/cartoes/{cartao_id}/codigo-seguranca')
    assert resp.status_code == 405


# ---------------------------------------------------------------------------
# 13.5. Cartao sem CVV
# ---------------------------------------------------------------------------

def test_cartao_sem_cvv_retorna_possui_cvv_false(app_com_senha):
    cartao_id = _criar_cartao_sem_cvv()

    resp = app_com_senha.get(f'/api/cartoes/{cartao_id}')
    body = resp.get_json()
    assert body['config']['possui_cvv'] is False


def test_revelar_cvv_de_cartao_sem_codigo_retorna_erro(app_com_senha):
    cartao_id = _criar_cartao_sem_cvv()

    resp = app_com_senha.post(
        f'/api/cartoes/{cartao_id}/codigo-seguranca',
        json={'senha': 'senha-correta-teste'},
    )
    assert resp.status_code == 404
    body = resp.get_json()
    assert body['success'] is False


def test_revelar_cvv_cartao_inexistente_retorna_404(app_com_senha):
    resp = app_com_senha.post(
        '/api/cartoes/99999/codigo-seguranca',
        json={'senha': 'senha-correta-teste'},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Nao logar CVV/senha (verificacao indireta via captura de log)
# ---------------------------------------------------------------------------

def test_erro_de_senha_nao_loga_valor_do_cvv(app_com_senha, caplog):
    cartao_id = _criar_cartao_com_cvv(codigo_seguranca='321')

    app_com_senha.post(
        f'/api/cartoes/{cartao_id}/codigo-seguranca',
        json={'senha': 'senha-errada'},
    )
    for record in caplog.records:
        assert '321' not in record.getMessage()
        assert 'senha-errada' not in record.getMessage()
