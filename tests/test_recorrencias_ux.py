from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import (
    db,
    Categoria,
    ConfigAgregador,
    ItemDespesa,
)
from backend.routes.consorcios import consorcios_bp
from backend.routes.recorrencias import recorrencias_bp
from backend.services.categoria_cartao_service import CategoriaCartaoService


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


def _categoria(nome='Moradia'):
    categoria = Categoria(nome=nome, ativo=True)
    db.session.add(categoria)
    db.session.commit()
    return categoria


def _base_cartao():
    categoria = _categoria('Mobilidade')
    cartao = ItemDespesa(nome='Cartao Teste', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add(cartao)
    db.session.flush()
    db.session.add(ConfigAgregador(
        item_despesa_id=cartao.id,
        dia_fechamento=25,
        dia_vencimento=5,
    ))
    db.session.commit()
    return categoria, cartao


def _categoria_cartao_vinculada(cartao, categoria):
    categoria_cartao = CategoriaCartaoService.criar_categoria(nome='Mobilidade', cor='#2563eb')
    db.session.commit()
    CategoriaCartaoService.vincular_categoria_despesa(categoria_cartao.id, categoria.id)
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(
        cartao.id,
        categoria_cartao.id,
        limite_mensal='2000.00',
    )
    db.session.commit()
    return categoria_cartao


def test_rota_principal_recorrencias_renderiza(client):
    response = client.get('/recorrencias')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Recorrencias' in html
    assert 'module-actionbar' in html


def test_template_contem_action_bar_e_filtros(client):
    html = client.get('/recorrencias').get_data(as_text=True)

    for campo in [
        'filtro-tipo',
        'filtro-status',
        'filtro-frequencia',
        'filtro-categoria',
        'filtro-busca',
    ]:
        assert campo in html

    assert 'Atualizar' in html
    assert 'Filtros' in html
    assert 'Nova recorrencia' in html


def test_template_contem_cards_agenda_lista_e_painel_inline(client):
    html = client.get('/recorrencias').get_data(as_text=True)

    assert 'recorrencias-kpi-grid' in html
    assert 'Recorrencias ativas' in html
    assert 'Valor mensal previsto' in html
    assert 'Proxima geracao' in html
    assert 'Categorias usadas' in html
    assert 'Agenda do periodo' in html
    assert 'agenda-periodo' in html
    assert 'Recorrencias cadastradas' in html
    assert 'recorrencias-lista' in html
    assert 'secao-formulario' in html
    assert 'Nova recorrencia' in html
    assert 'Composicao das recorrencias' in html


def test_painel_nova_recorrencia_preserva_campos_e_handlers(client):
    html = client.get('/recorrencias').get_data(as_text=True)

    assert 'salvarRecorrencia(event)' in html
    assert 'alternarTipoCadastro()' in html
    assert 'alternarMeioPagamento()' in html
    assert 'carregarCategoriasCartaoSelecionado()' in html

    for campo in [
        'tipo-cadastro',
        'nome',
        'categoria-id',
        'valor',
        'data-vencimento',
        'frequencia',
        'dia-semana',
        'meio-pagamento',
        'cartao-id',
        'categoria-cartao-id',
        'recorrencia-ativa',
        'observacoes',
    ]:
        assert campo in html


def test_banco_vazio_nao_quebra_listagem_api(client):
    response = client.get('/api/recorrencias?status=todas')
    data = response.get_json()

    assert response.status_code == 200
    assert data['success'] is True
    assert data['data'] == []
    assert data['total'] == 0


def test_salvar_recorrencia_continua_funcionando(client):
    categoria = _categoria()

    response = client.post('/api/recorrencias', json={
        'nome': 'Aluguel mensal',
        'descricao': 'Apartamento',
        'valor': '1800.00',
        'categoria_id': categoria.id,
        'data_vencimento': '2026-05-24',
        'tipo_recorrencia': 'mensal',
    })
    data = response.get_json()

    assert response.status_code == 201
    assert data['success'] is True
    assert data['data']['nome'] == 'Aluguel mensal'
    assert data['data']['frequencia'] == 'mensal'


def test_recorrencia_com_cartao_preserva_categoria_cartao_sem_item_agregado(client):
    categoria, cartao = _base_cartao()
    categoria_cartao = _categoria_cartao_vinculada(cartao, categoria)

    response = client.post('/api/recorrencias', json={
        'nome': 'Combustivel recorrente',
        'descricao': 'Abastecimento mensal',
        'valor': '300.00',
        'categoria_id': categoria.id,
        'data_vencimento': '2026-05-10',
        'tipo_recorrencia': 'mensal',
        'meio_pagamento': 'cartao',
        'cartao_id': cartao.id,
        'categoria_cartao_id': categoria_cartao.id,
    })
    data = response.get_json()

    assert response.status_code == 201
    assert data['data']['categoria_cartao_id'] == categoria_cartao.id

    recorrencia = ItemDespesa.query.filter_by(nome='Combustivel recorrente').one()
    assert recorrencia.item_agregado_id is None
    assert recorrencia.categoria_cartao_id == categoria_cartao.id
