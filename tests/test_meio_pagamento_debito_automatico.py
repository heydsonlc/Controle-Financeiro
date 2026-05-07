from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import Categoria, Conta, ItemDespesa, db
from backend.routes.recorrencias import recorrencias_bp


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
    app.register_blueprint(recorrencias_bp, url_prefix='/api/recorrencias')

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


def test_template_expoe_debito_automatico_da(client):
    html = client.get('/recorrencias').get_data(as_text=True)

    assert '<option value="debito_automatico">D&eacute;bito Autom&aacute;tico / D.A.</option>' in html


def test_recorrencia_salva_debito_automatico_sem_interferir_na_geracao(client):
    categoria = Categoria(nome='Moradia', ativo=True)
    db.session.add(categoria)
    db.session.commit()

    response = client.post('/api/recorrencias', json={
        'nome': 'Internet recorrente',
        'valor': str(Decimal('120.00')),
        'categoria_id': categoria.id,
        'data_vencimento': '2026-05-10',
        'tipo_recorrencia': 'mensal',
        'meio_pagamento': 'debito_automatico',
    })
    data = response.get_json()

    assert response.status_code == 201
    assert data['data']['meio_pagamento'] == 'debito_automatico'

    item = ItemDespesa.query.filter_by(nome='Internet recorrente').one()
    contas = Conta.query.filter_by(item_despesa_id=item.id).all()
    assert item.meio_pagamento == 'debito_automatico'
    assert [conta.data_vencimento for conta in contas] == [date(2026, 5, 10)]
