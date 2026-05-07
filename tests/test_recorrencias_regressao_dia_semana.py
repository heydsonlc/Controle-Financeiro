from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import Conta, Categoria, ItemDespesa, db
from backend.routes.despesas import despesas_bp, gerar_contas_despesa_recorrente
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
    app.register_blueprint(despesas_bp)
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


def _categoria(nome='Psicologia'):
    categoria = Categoria(nome=nome, ativo=True)
    db.session.add(categoria)
    db.session.commit()
    return categoria


def _recorrencia(nome, tipo_recorrencia, data_vencimento, categoria=None):
    categoria = categoria or _categoria()
    item = ItemDespesa(
        nome=nome,
        descricao='Recorrencia de teste',
        valor=Decimal('250.00'),
        categoria_id=categoria.id,
        data_vencimento=data_vencimento,
        recorrente=True,
        tipo_recorrencia=tipo_recorrencia,
        tipo='Simples',
        ativo=True,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _datas_contas(item):
    return [
        conta.data_vencimento
        for conta in Conta.query.filter_by(item_despesa_id=item.id).order_by(Conta.data_vencimento.asc()).all()
    ]


def test_recorrencia_semanal_terca_gera_apenas_tercas(app_context):
    item = _recorrencia('Psicologa', 'semanal_1_2', date(2026, 5, 8))

    gerar_contas_despesa_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    datas = _datas_contas(item)
    assert datas == [
        date(2026, 5, 12),
        date(2026, 5, 19),
        date(2026, 5, 26),
    ]
    assert date(2026, 5, 13) not in datas
    assert date(2026, 5, 20) not in datas
    assert date(2026, 5, 27) not in datas


def test_recorrencia_a_cada_2_semanas_segunda_preserva_grade(app_context):
    item = _recorrencia('Diarista alternada', 'semanal_2_1', date(2026, 5, 8))

    gerar_contas_despesa_recorrente(item.id, meses_futuros=2, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    assert _datas_contas(item)[:4] == [
        date(2026, 5, 11),
        date(2026, 5, 25),
        date(2026, 6, 8),
        date(2026, 6, 22),
    ]


def test_recorrencia_semanal_nao_duplica_apos_geracao_repetida(app_context):
    item = _recorrencia('Psicologa', 'semanal_1_2', date(2026, 5, 8))

    gerar_contas_despesa_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    gerar_contas_despesa_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    datas = _datas_contas(item)
    assert datas == sorted(set(datas))
    assert len(datas) == 3


def test_recorrencia_corrige_ocorrencias_automaticas_pendentes_do_mapeamento_antigo(app_context):
    item = _recorrencia('Psicologa', 'semanal_1_2', date(2026, 5, 8))
    for data_errada in [date(2026, 5, 13), date(2026, 5, 20), date(2026, 5, 27)]:
        db.session.add(Conta(
            item_despesa_id=item.id,
            mes_referencia=data_errada.replace(day=1),
            descricao=f"Psicologa - {data_errada.strftime('%d/%m')}",
            valor=item.valor,
            data_vencimento=data_errada,
            status_pagamento='Pendente',
            observacoes=item.descricao,
            is_fatura_cartao=False,
        ))
    db.session.commit()

    gerar_contas_despesa_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    assert _datas_contas(item) == [
        date(2026, 5, 12),
        date(2026, 5, 19),
        date(2026, 5, 26),
    ]


def test_lista_despesas_nao_soma_ocorrencia_errada_e_corrigida_no_mes(client):
    item = _recorrencia('Psicologa', 'semanal_1_2', date(2026, 5, 8))
    db.session.add(Conta(
        item_despesa_id=item.id,
        mes_referencia=date(2026, 5, 1),
        descricao='Psicologa - 13/05',
        valor=item.valor,
        data_vencimento=date(2026, 5, 13),
        status_pagamento='Pendente',
        observacoes=item.descricao,
        is_fatura_cartao=False,
    ))
    db.session.commit()

    response = client.get('/api/despesas/?mes=2026-05')
    data = response.get_json()
    datas_maio = sorted(
        item['data_vencimento']
        for item in data['data']
        if item['nome'].startswith('Psicologa')
        and item['mes_competencia'] == '2026-05'
    )

    assert response.status_code == 200
    assert data['success'] is True
    assert datas_maio == ['2026-05-12', '2026-05-19', '2026-05-26']


def test_rotulo_a_cada_2_semanas_e_debito_automatico_preservados(client):
    html = client.get('/recorrencias').get_data(as_text=True)

    assert '<option value="quinzenal">A cada 2 semanas</option>' in html
    assert '<option value="debito_automatico">D&eacute;bito Autom&aacute;tico / D.A.</option>' in html
