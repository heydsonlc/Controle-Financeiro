from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import Categoria, CategoriaPalavraChave, db
from backend.routes.categorias import categorias_bp, categorias_cartao_bp
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
        UPLOAD_LOGOS_DIR=str(base_dir / 'tmp' / 'logos-test'),
    )
    db.init_app(app)
    app.register_blueprint(categorias_bp, url_prefix='/api/categorias')
    app.register_blueprint(categorias_cartao_bp, url_prefix='/api/categorias-cartao')

    @app.route('/categorias')
    def categorias_page():
        return render_template('categorias.html', active_page='categorias', page_title='Categorias')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _categoria(nome='Combustivel'):
    categoria = Categoria(nome=nome, descricao='Abastecimento', ativo=True)
    db.session.add(categoria)
    db.session.commit()
    return categoria


def test_cria_lista_e_normaliza_palavra_chave(app_context):
    categoria = _categoria()

    with app_context.test_client() as client:
        response = client.post(
            f'/api/categorias/{categoria.id}/palavras-chave',
            json={'palavra': '  Posto   Shell  '},
        )
        assert response.status_code == 201
        assert response.get_json()['data']['palavra'] == 'posto shell'

        lista = client.get(f'/api/categorias/{categoria.id}/palavras-chave')
        data = lista.get_json()

    assert lista.status_code == 200
    assert data['total'] == 1
    assert data['data'][0]['palavra'] == 'posto shell'


def test_impede_duplicidade_na_mesma_categoria(app_context):
    categoria = _categoria()

    with app_context.test_client() as client:
        primeira = client.post(f'/api/categorias/{categoria.id}/palavras-chave', json={'palavra': 'shell'})
        duplicada = client.post(f'/api/categorias/{categoria.id}/palavras-chave', json={'palavra': ' Shell '})

    assert primeira.status_code == 201
    assert duplicada.status_code == 400
    assert CategoriaPalavraChave.query.filter_by(categoria_id=categoria.id, palavra='shell', ativo=True).count() == 1


def test_remove_palavra_chave_por_soft_delete(app_context):
    categoria = _categoria()

    with app_context.test_client() as client:
        criada = client.post(f'/api/categorias/{categoria.id}/palavras-chave', json={'palavra': 'ipiranga'})
        palavra_id = criada.get_json()['data']['id']
        removida = client.delete(f'/api/categorias/{categoria.id}/palavras-chave/{palavra_id}')
        lista = client.get(f'/api/categorias/{categoria.id}/palavras-chave')

    assert removida.status_code == 200
    assert removida.get_json()['data']['ativo'] is False
    assert lista.get_json()['total'] == 0
    assert CategoriaPalavraChave.query.get(palavra_id).ativo is False


def test_lista_categorias_inclui_contagem_de_palavras(app_context):
    categoria = _categoria()
    with app_context.test_client() as client:
        client.post(f'/api/categorias/{categoria.id}/palavras-chave', json={'palavra': 'petrobras'})
        response = client.get('/api/categorias')

    item = response.get_json()['data'][0]
    assert item['palavras_chave_count'] == 1


def test_template_contem_bloco_palavras_chave_e_cards_laterais(app_context):
    with app_context.test_client() as client:
        response = client.get('/categorias')
        html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'categoria-despesa-detalhe' in html
    assert 'Palavras-chave de classifica' in html
    assert 'Categorias com palavras-chave' in html
    assert 'Categorias do Cart&atilde;o' in html


def test_categoria_do_cartao_continua_funcionando(app_context):
    categoria = _categoria()
    categoria_cartao = CategoriaCartaoService.criar_categoria(nome='Mobilidade', cor='#2563eb')
    db.session.commit()

    with app_context.test_client() as client:
        response = client.post(
            f'/api/categorias-cartao/{categoria_cartao.id}/despesas',
            json={'categoria_id': categoria.id},
        )

    assert response.status_code == 201
    assert response.get_json()['data']['categoria_id'] == categoria.id
