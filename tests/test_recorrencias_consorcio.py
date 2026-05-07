from datetime import date
from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import (
    Categoria,
    Conta,
    ContratoConsorcio,
    ItemDespesa,
    ReceitaRealizada,
    db,
)
from backend.routes.consorcios import consorcios_bp


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
    app.register_blueprint(consorcios_bp)

    @app.route('/recorrencias')
    def recorrencias_page():
        return render_template(
            'recorrencias.html',
            active_page='recorrencias',
            page_title='Recorrencias',
        )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


def _categoria():
    categoria = Categoria(nome='Consorcio Teste', ativo=True)
    db.session.add(categoria)
    db.session.commit()
    return categoria


def _payload(categoria_id, **overrides):
    payload = {
        'nome': 'Consorcio Teste',
        'valor_inicial': 500,
        'categoria_id': categoria_id,
        'numero_parcelas': 10,
        'mes_inicio': '2026-01-01',
        'tipo_reajuste': 'fixo',
        'valor_reajuste': 20,
        'mes_contemplacao': '2026-03-01',
        'valor_premio': 1,
        'observacoes': 'teste automatizado',
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize('mes_inicio', [1, '01', '2026-01', '2026-01-01'])
def test_salvar_consorcio_aceita_formatos_de_mes_inicio(client, mes_inicio):
    categoria = _categoria()

    response = client.post('/api/consorcios/', json=_payload(categoria.id, mes_inicio=mes_inicio))
    data = response.get_json()

    assert response.status_code == 201
    assert data['success'] is True
    assert data['data']['mes_inicio'] == '2026-01-01'


def test_mes_inicio_invalido_retorna_erro_amigavel(client):
    categoria = _categoria()

    response = client.post('/api/consorcios/', json=_payload(categoria.id, mes_inicio=13))
    data = response.get_json()

    assert response.status_code == 400
    assert data['success'] is False
    assert 'Mes de inicio invalido' in data['error']


def test_mes_contemplacao_antes_do_inicio_retorna_erro(client):
    categoria = _categoria()

    response = client.post(
        '/api/consorcios/',
        json=_payload(categoria.id, mes_inicio='2026-03', mes_contemplacao='2026-01'),
    )
    data = response.get_json()

    assert response.status_code == 400
    assert 'Mes de contemplacao deve estar dentro do periodo do consorcio' in data['error']


def test_mes_contemplacao_fora_das_parcelas_retorna_erro(client):
    categoria = _categoria()

    response = client.post(
        '/api/consorcios/',
        json=_payload(categoria.id, numero_parcelas=2, mes_contemplacao='2026-03'),
    )
    data = response.get_json()

    assert response.status_code == 400
    assert 'Mes de contemplacao deve estar dentro do periodo do consorcio' in data['error']


def test_premio_fixo_e_receita_sao_calculados_pela_posicao(client):
    categoria = _categoria()

    response = client.post('/api/consorcios/', json=_payload(categoria.id))
    data = response.get_json()

    assert response.status_code == 201
    assert data['data']['valor_premio'] == 5400.0
    assert data['receita_gerada'] is True

    parcelas = ItemDespesa.query.order_by(ItemDespesa.data_vencimento).all()
    assert len(parcelas) == 10
    assert float(parcelas[2].valor) == 540.0

    conta_terceira = Conta.query.filter_by(item_despesa_id=parcelas[2].id).first()
    assert conta_terceira is not None
    assert float(conta_terceira.valor) == 540.0

    receita = ReceitaRealizada.query.one()
    assert float(receita.valor_recebido) == 5400.0
    assert receita.data_recebimento == date(2026, 3, 1)
    assert receita.mes_referencia == date(2026, 3, 1)


def test_premio_percentual_usa_juros_simples_e_nao_composto(client):
    categoria = _categoria()

    response = client.post(
        '/api/consorcios/',
        json=_payload(
            categoria.id,
            tipo_reajuste='percentual',
            valor_reajuste=2,
            valor_premio=999999,
        ),
    )
    data = response.get_json()

    assert response.status_code == 201
    assert data['data']['valor_premio'] == 5200.0

    parcelas = ItemDespesa.query.order_by(ItemDespesa.data_vencimento).all()
    assert float(parcelas[2].valor) == 520.0


def test_backend_recalcula_premio_e_ignora_valor_divergente(client):
    categoria = _categoria()

    response = client.post('/api/consorcios/', json=_payload(categoria.id, valor_premio=123456))
    data = response.get_json()

    assert response.status_code == 201
    assert data['data']['valor_premio'] == 5400.0

    consorcio = ContratoConsorcio.query.one()
    assert float(consorcio.valor_premio) == 5400.0


def test_template_indica_premio_automatico_readonly(client):
    html = client.get('/recorrencias').get_data(as_text=True)

    assert 'id="valor-premio"' in html
    assert 'readonly' in html
    assert 'Calculado automaticamente pela parcela da contemplacao' in html

