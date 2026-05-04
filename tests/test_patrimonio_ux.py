from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import ContaPatrimonio, db
from backend.routes.patrimonio import patrimonio_bp


@pytest.fixture()
def app_context():
    base_dir = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(base_dir / 'frontend' / 'templates'),
        static_folder=str(base_dir / 'frontend' / 'static'),
    )
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(patrimonio_bp, url_prefix='/api/patrimonio')

    @app.route('/patrimonio')
    def patrimonio_page():
        return render_template(
            'patrimonio.html',
            active_page='patrimonio',
            page_title='Patrimônio',
        )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


def _payload_caixinha(nome='Reserva UX', saldo=1000.0, meta=5000.0, cor='#2563eb'):
    return {
        'nome': nome,
        'tipo': 'Reserva',
        'saldo_inicial': saldo,
        'meta': meta,
        'cor': cor,
        'observacoes': 'Caixinha criada para teste UX',
    }


def _criar_caixinha(client, nome='Reserva UX', saldo=1000.0, meta=5000.0, cor='#2563eb'):
    response = client.post('/api/patrimonio/contas', json=_payload_caixinha(nome, saldo, meta, cor))
    assert response.status_code == 201
    body = response.get_json()
    assert body['success'] is True
    return body['data']


def test_rota_principal_renderiza_layout_ux(client):
    response = client.get('/patrimonio')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'module-actionbar' in html
    assert 'patrimonio-summary-grid' in html
    assert 'Patrim&ocirc;nio total' in html
    assert 'Caixinhas ativas' in html
    assert 'Meta consolidada' in html
    assert 'caixinhas-lista' in html
    assert 'patrimonio-composicao' in html
    assert '<h1' not in html


def test_modais_nova_caixinha_e_transferencia_preservam_ids(client):
    html = client.get('/patrimonio').get_data(as_text=True)

    assert 'id="modal-conta"' in html
    assert 'id="form-conta"' in html
    assert 'id="conta-nome"' in html
    assert 'id="conta-tipo"' in html
    assert 'id="conta-saldo-inicial"' in html
    assert 'id="conta-meta"' in html
    assert 'id="conta-obs"' in html
    assert 'Pr&eacute;via da caixinha' in html
    assert 'id="modal-transferencia"' in html
    assert 'id="form-transferencia"' in html
    assert 'id="transf-origem"' in html
    assert 'id="transf-destino"' in html
    assert 'id="transf-valor"' in html
    assert 'Resumo da transfer&ecirc;ncia' in html


def test_api_banco_vazio_nao_quebra(client):
    response = client.get('/api/patrimonio/contas')

    assert response.status_code == 200
    body = response.get_json()
    assert body['success'] is True
    assert body['data'] == []
    assert body['total_patrimonio'] == 0


def test_criar_caixinha_preserva_contrato_funcional(client):
    caixinha = _criar_caixinha(client)

    assert caixinha['nome'] == 'Reserva UX'
    assert caixinha['tipo'] == 'Reserva'
    assert caixinha['saldo_inicial'] == 1000.0
    assert caixinha['saldo_atual'] == 1000.0
    assert caixinha['meta'] == 5000.0
    assert caixinha['cor'] == '#2563eb'


def test_cards_resumo_calculam_total_caixinhas_e_metas(client, app_context):
    _criar_caixinha(client, nome='Reserva A', saldo=1200.0, meta=2000.0)
    _criar_caixinha(client, nome='Reserva B', saldo=800.0, meta=1000.0)

    response = client.get('/api/patrimonio/contas')
    body = response.get_json()

    assert body['success'] is True
    assert body['total'] == 2
    assert body['total_patrimonio'] == 2000.0
    with app_context.app_context():
        assert ContaPatrimonio.query.count() == 2


def test_transferencia_preserva_regra_de_saldo(client):
    origem = _criar_caixinha(client, nome='Origem UX', saldo=1000.0)
    destino = _criar_caixinha(client, nome='Destino UX', saldo=100.0)

    response = client.post('/api/patrimonio/transferencias', json={
        'conta_origem_id': origem['id'],
        'conta_destino_id': destino['id'],
        'valor': 250.0,
        'data_transferencia': '2026-05-04',
        'descricao': 'Transferencia UX',
    })

    assert response.status_code == 201
    body = response.get_json()
    assert body['success'] is True

    origem_atualizada = client.get(f"/api/patrimonio/contas/{origem['id']}").get_json()['data']
    destino_atualizado = client.get(f"/api/patrimonio/contas/{destino['id']}").get_json()['data']
    assert origem_atualizada['saldo_atual'] == 750.0
    assert destino_atualizado['saldo_atual'] == 350.0


def test_template_nao_expoe_subtitulo_local_redundante(client):
    html = client.get('/patrimonio').get_data(as_text=True)

    assert 'Gerencie seu patrimonio' not in html
    assert 'Vis&atilde;o geral' in html
    assert 'Nova caixinha' in html
    assert 'Transferir' in html
