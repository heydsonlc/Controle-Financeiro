from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import Categoria, Conta, ItemDespesa, db
from backend.routes.despesas import gerar_contas_despesa_recorrente


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_a_cada_2_semanas_segunda_gera_grade_correta(app_context):
    categoria = Categoria(nome='Servicos', ativo=True)
    db.session.add(categoria)
    db.session.flush()
    item = ItemDespesa(
        nome='Servico quinzenal',
        valor=Decimal('250.00'),
        categoria_id=categoria.id,
        data_vencimento=date(2026, 5, 8),
        recorrente=True,
        tipo_recorrencia='semanal_2_1',
        tipo='Simples',
        ativo=True,
    )
    db.session.add(item)
    db.session.commit()

    gerar_contas_despesa_recorrente(item.id, meses_futuros=2, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    datas = [
        conta.data_vencimento
        for conta in Conta.query.filter_by(item_despesa_id=item.id).order_by(Conta.data_vencimento.asc()).all()
    ]
    assert datas[:4] == [
        date(2026, 5, 11),
        date(2026, 5, 25),
        date(2026, 6, 8),
        date(2026, 6, 22),
    ]
    assert len(datas) == len(set(datas))
