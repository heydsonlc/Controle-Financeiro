"""
Testes CARD-CVV-LOCK-1 + FIN-PRE-PRODUCAO-1 (2.3) — dados sensiveis de cartao no Flask.

- API padrao (listagem, detalhe, criacao, edicao, to_dict) nunca expoe o CVV e devolve o numero mascarado (so o final)
- A consulta do CVV foi desativada: o endpoint de revelar responde 410, com ou sem senha configurada (GET: 405)
- O CVV nao e mais cadastrado: criacao e edicao com CVV sao recusadas, sem gravar nada
- Os dados antigos guardados nao mudam: a edicao nao apaga o CVV e o numero mascarado nao substitui o guardado
- Nenhum log com CVV ou numero
"""
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import ConfigAgregador, ItemDespesa, db, mascarar_numero_cartao
from backend.routes.cartoes import cartoes_bp

MASCARA = '••••'


def _app(senha):
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', SQLALCHEMY_TRACK_MODIFICATIONS=False)
    app.config['CARTOES_CVV_MASTER_PASSWORD'] = senha
    app.config['SECRET_KEY'] = 'nao-deve-funcionar-como-senha-cvv'
    db.init_app(app)
    app.register_blueprint(cartoes_bp)
    return app


@pytest.fixture(params=['senha-correta-teste', None], ids=['com_senha_mestre', 'sem_senha_mestre'])
def cliente(request):
    app = _app(request.param)
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
    db.session.add(ConfigAgregador(item_despesa_id=cartao.id, dia_fechamento=25, dia_vencimento=5,
                                   limite_credito=Decimal('5000.00'), numero_cartao=numero_cartao,
                                   codigo_seguranca=codigo_seguranca, tem_codigo=True))
    db.session.commit()
    return cartao.id


def _guardado(cartao_id):
    db.session.expire_all()
    config = ConfigAgregador.query.filter_by(item_despesa_id=cartao_id).one()
    return config.numero_cartao, config.codigo_seguranca


def _lista(resp):
    body = resp.get_json()
    return body if isinstance(body, list) else body.get('data', [])


# --- API padrao: sem CVV, numero mascarado ---------------------------------------------------------------------

def test_listagem_e_detalhe_sem_cvv_e_com_numero_mascarado(cliente):
    cartao_id = _criar_cartao_com_cvv()
    config = _lista(cliente.get('/api/cartoes'))[0]['config']
    detalhe = cliente.get(f'/api/cartoes/{cartao_id}').get_json()['config']
    for c in (config, detalhe):
        assert {'codigo_seguranca', 'cvv', 'security_code'}.isdisjoint(c)
        assert c['numero_cartao'] == f'{MASCARA} 3456'
        assert c['possui_cvv'] is False  # a tela nao oferece revelar
    assert '1234 5678' not in cliente.get('/api/cartoes').get_data(as_text=True)


def test_to_dict_sem_cvv_e_numero_mascarado():
    config = ConfigAgregador(item_despesa_id=1, dia_fechamento=10, dia_vencimento=20, codigo_seguranca='999',
                             numero_cartao='5555666677778888')
    resultado = config.to_dict()
    assert {'codigo_seguranca', 'cvv', 'security_code'}.isdisjoint(resultado)
    assert resultado['numero_cartao'] == f'{MASCARA} 8888' and resultado['possui_cvv'] is False


def test_mascara_do_numero():
    assert mascarar_numero_cartao('1234-5678-9012-3456') == f'{MASCARA} 3456'
    assert mascarar_numero_cartao(None) is None and mascarar_numero_cartao('12') is None
    assert mascarar_numero_cartao(f'{MASCARA} 3456') == f'{MASCARA} 3456'


# --- Consulta do CVV desativada ----------------------------------------------------------------------------------

def test_revelar_responde_410_sem_revelar(cliente):
    cartao_id = _criar_cartao_com_cvv(codigo_seguranca='456')
    for corpo in ({}, {'senha': 'senha-correta-teste'}, {'senha': 'nao-deve-funcionar-como-senha-cvv'}, {'senha': '456'}):
        resp = cliente.post(f'/api/cartoes/{cartao_id}/codigo-seguranca', json=corpo)
        assert resp.status_code == 410
        assert resp.get_json()['success'] is False
        assert '456' not in resp.get_data(as_text=True)
    assert cliente.post('/api/cartoes/99999/codigo-seguranca', json={'senha': 'x'}).status_code == 410


def test_get_no_endpoint_de_revelar_retorna_405(cliente):
    cartao_id = _criar_cartao_com_cvv()
    assert cliente.get(f'/api/cartoes/{cartao_id}/codigo-seguranca').status_code == 405


# --- CVV nao e mais cadastrado; dados antigos preservados ---------------------------------------------------------

def test_criar_com_cvv_recusado_sem_gravar(cliente):
    resp = cliente.post('/api/cartoes', json={'nome': 'Novo', 'dia_fechamento': 1, 'dia_vencimento': 10, 'codigo_seguranca': '321'})
    assert resp.status_code == 400 and 'nao e mais armazenado' in resp.get_json()['error']
    assert ConfigAgregador.query.count() == 0


def test_criar_sem_cvv_grava_sem_cvv(cliente):
    resp = cliente.post('/api/cartoes', json={'nome': 'Novo', 'dia_fechamento': 1, 'dia_vencimento': 10, 'codigo_seguranca': '',
                                              'numero_cartao': '4111 1111 1111 1111'})
    assert resp.status_code == 201
    assert resp.get_json()['config']['numero_cartao'] == f'{MASCARA} 1111'
    assert ConfigAgregador.query.one().codigo_seguranca is None


def test_editar_com_cvv_recusado_e_cvv_antigo_preservado(cliente):
    cartao_id = _criar_cartao_com_cvv(codigo_seguranca='777')
    resp = cliente.put(f'/api/cartoes/{cartao_id}', json={'nome': 'Outro', 'codigo_seguranca': '888'})
    assert resp.status_code == 400
    assert _guardado(cartao_id) == ('1234 5678 9012 3456', '777')
    # Edicao normal (a tela envia codigo_seguranca vazio e o numero mascarado que recebeu): nada sensivel muda.
    resp = cliente.put(f'/api/cartoes/{cartao_id}', json={'nome': 'Outro', 'codigo_seguranca': None,
                                                          'numero_cartao': f'{MASCARA} 3456'})
    assert resp.status_code == 200 and resp.get_json()['nome'] == 'Outro'
    assert _guardado(cartao_id) == ('1234 5678 9012 3456', '777')


def test_editar_com_numero_novo_completo_continua_aceito(cliente):
    cartao_id = _criar_cartao_com_cvv()
    resp = cliente.put(f'/api/cartoes/{cartao_id}', json={'numero_cartao': '5500 0000 0000 0004'})
    assert resp.status_code == 200 and resp.get_json()['config']['numero_cartao'] == f'{MASCARA} 0004'
    assert _guardado(cartao_id)[0] == '5500 0000 0000 0004'


def test_nenhum_log_com_cvv_ou_numero(cliente, caplog):
    cartao_id = _criar_cartao_com_cvv(codigo_seguranca='321')
    cliente.post(f'/api/cartoes/{cartao_id}/codigo-seguranca', json={'senha': 'senha-errada'})
    cliente.put(f'/api/cartoes/{cartao_id}', json={'codigo_seguranca': '654'})
    for record in caplog.records:
        assert '321' not in record.getMessage() and '654' not in record.getMessage()
        assert '5678' not in record.getMessage()
