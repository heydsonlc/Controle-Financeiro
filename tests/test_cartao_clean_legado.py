from datetime import date
from pathlib import Path

import pytest
from flask import Flask

from backend.models import (
    db,
    Categoria,
    ConfigAgregador,
    DespesaPrevista,
    ItemAgregado,
    ItemDespesa,
    LancamentoAgregado,
    OrcamentoAgregado,
)
from backend.routes.cartoes import cartoes_bp
from backend.routes.categorias import categorias_cartao_bp
from backend.routes.dashboard import dashboard_bp
from backend.routes.importacao_cartao import bp as importacao_cartao_bp
from backend.routes.recorrencias import recorrencias_bp
from backend.services.categoria_cartao_service import CategoriaCartaoService
from backend.services.despesa_prevista_service import confirmar


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(importacao_cartao_bp)
    app.register_blueprint(cartoes_bp)
    app.register_blueprint(recorrencias_bp, url_prefix='/api/recorrencias')
    app.register_blueprint(categorias_cartao_bp, url_prefix='/api/categorias-cartao')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _base_cartao():
    categoria = Categoria(nome='Combustivel', ativo=True)
    categoria_extra = Categoria(nome='Seguro', ativo=True)
    cartao = ItemDespesa(nome='Cartao Teste', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add_all([categoria, categoria_extra, cartao])
    db.session.flush()
    db.session.add(ConfigAgregador(
        item_despesa_id=cartao.id,
        dia_fechamento=25,
        dia_vencimento=5,
    ))
    db.session.commit()
    return categoria, categoria_extra, cartao


def _categoria_cartao(nome='Mobilidade'):
    categoria = CategoriaCartaoService.criar_categoria(nome=nome, cor='#2563eb')
    db.session.commit()
    return categoria


def _mapear_e_vincular(cartao, categoria, categoria_cartao=None, limite='2000.00'):
    categoria_cartao = categoria_cartao or _categoria_cartao()
    CategoriaCartaoService.vincular_categoria_despesa(categoria_cartao.id, categoria.id)
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(
        cartao.id,
        categoria_cartao.id,
        limite_mensal=limite,
    )
    db.session.commit()
    return categoria_cartao


def _linha_importacao(categoria_id, categoria_cartao_id=None):
    linha = {
        'data_compra': '2026-05-01',
        'descricao': 'Posto Teste',
        'valor': '120.00',
        'parcela': '1/1',
        'categoria_id': categoria_id,
    }
    if categoria_cartao_id:
        linha['categoria_cartao_id'] = categoria_cartao_id
    return linha


def test_importacao_nao_exige_item_agregado_id(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)

    with app_context.test_client() as client:
        response = client.post('/api/importacao-cartao/processar', json={
            'cartao_id': cartao.id,
            'competencia': '2026-05-01',
            'linhas': [_linha_importacao(categoria.id)],
        })

    assert response.status_code == 200
    lancamento = LancamentoAgregado.query.one()
    assert lancamento.item_agregado_id is None
    assert lancamento.categoria_cartao_id == categoria_cartao.id


def test_lancamento_manual_no_cartao_usa_categoria_cartao_sem_item_agregado(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)

    with app_context.test_client() as client:
        response = client.post(f'/api/cartoes/{cartao.id}/lancamentos', json={
            'categoria_id': categoria.id,
            'categoria_cartao_id': categoria_cartao.id,
            'descricao': 'Posto Teste',
            'valor': 150,
            'data_compra': '2026-05-01',
            'mes_fatura': '2026-05',
        })

    assert response.status_code == 201
    lancamento = LancamentoAgregado.query.one()
    assert lancamento.item_agregado_id is None
    assert lancamento.categoria_cartao_id == categoria_cartao.id


def test_recorrencia_paga_no_cartao_nao_grava_item_agregado(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)

    with app_context.test_client() as client:
        response = client.post('/api/recorrencias', json={
            'nome': 'Combustivel recorrente',
            'valor': '90.00',
            'categoria_id': categoria.id,
            'data_vencimento': '2026-05-01',
            'tipo_recorrencia': 'mensal',
            'meio_pagamento': 'cartao',
            'cartao_id': cartao.id,
        })

    assert response.status_code == 201
    recorrencia = ItemDespesa.query.filter_by(nome='Combustivel recorrente').one()
    lancamento = LancamentoAgregado.query.filter_by(item_despesa_id=recorrencia.id).one()
    assert recorrencia.item_agregado_id is None
    assert recorrencia.categoria_cartao_id == categoria_cartao.id
    assert lancamento.item_agregado_id is None
    assert lancamento.categoria_cartao_id == categoria_cartao.id


def test_despesa_prevista_confirmada_com_cartao_nao_grava_item_agregado(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)
    despesa = DespesaPrevista(
        origem_tipo='TESTE',
        origem_id=1,
        categoria_id=categoria.id,
        data_prevista=date(2026, 5, 1),
        data_original_prevista=date(2026, 5, 1),
        data_atual_prevista=date(2026, 5, 1),
        valor_previsto=100,
        status='PREVISTA',
    )
    db.session.add(despesa)
    db.session.commit()

    _despesa, entidade = confirmar(
        despesa.id,
        {
            'meio_pagamento': 'cartao',
            'cartao_id': cartao.id,
            'categoria_id': categoria.id,
            'data_vencimento': '2026-05-01',
        },
    )
    db.session.commit()

    lancamento = LancamentoAgregado.query.get(entidade['id'])
    assert lancamento.item_agregado_id is None
    assert lancamento.categoria_cartao_id == categoria_cartao.id


def test_fatura_usa_categoria_cartao_id(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria, limite='500.00')
    db.session.add(LancamentoAgregado(
        cartao_id=cartao.id,
        categoria_id=categoria.id,
        categoria_cartao_id=categoria_cartao.id,
        descricao='Posto Teste',
        valor=125,
        data_compra=date(2026, 5, 1),
        mes_fatura=date(2026, 5, 1),
    ))
    db.session.commit()

    with app_context.test_client() as client:
        response = client.get(f'/api/cartoes/{cartao.id}/fatura-categorias?mes_referencia=2026-05')

    assert response.status_code == 200
    categoria_fatura = response.get_json()['data']['categorias'][0]
    assert categoria_fatura['categoria_cartao_id'] == categoria_cartao.id
    assert categoria_fatura['gasto_atual'] == 125.0
    assert categoria_fatura['limite_mensal'] == 500.0


def test_dashboard_usa_cartao_categoria_limite_sem_orcamento_agregado(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria, limite='1000.00')
    item_legado = ItemAgregado(
        item_despesa_id=cartao.id,
        nome='Legado',
        ativo=True,
    )
    db.session.add(item_legado)
    db.session.flush()
    db.session.add(OrcamentoAgregado(
        item_agregado_id=item_legado.id,
        mes_referencia=date(2026, 5, 1),
        valor_teto=9999,
        vigencia_inicio=date(2026, 5, 1),
        ativo=True,
    ))
    db.session.add(LancamentoAgregado(
        cartao_id=cartao.id,
        categoria_id=categoria.id,
        categoria_cartao_id=categoria_cartao.id,
        descricao='Posto Teste',
        valor=300,
        data_compra=date(2026, 5, 1),
        mes_fatura=date(2026, 5, 1),
    ))
    db.session.commit()

    with app_context.test_client() as client:
        response = client.get('/api/dashboard/resumo?mes_referencia=2026-05')

    assert response.status_code == 200
    consumo = response.get_json()['data']['categorias_cartao'][0]
    assert consumo['categoria_cartao_id'] == categoria_cartao.id
    assert consumo['limite'] == 1000.0
    assert consumo['gasto'] == 300.0


def test_endpoint_novo_categoria_cartao_continua_respondendo(app_context):
    _categoria_cartao('Mobilidade')

    with app_context.test_client() as client:
        response = client.get('/api/categorias-cartao')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['data'][0]['nome'] == 'Mobilidade'


def test_templates_principais_nao_exibem_rotulos_legados():
    raiz = Path(__file__).resolve().parents[1]
    templates = [
        'cartoes.html',
        'importar_cartao.html',
        'despesas.html',
        'recorrencias.html',
        'veiculos.html',
        'lancamentos.html',
        'index.html',
    ]

    for nome in templates:
        html = (raiz / 'frontend' / 'templates' / nome).read_text(encoding='utf-8').lower()
        assert 'item agregado' not in html
        assert 'categoria interna' not in html
