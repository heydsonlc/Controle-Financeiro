"""
Testes CORE-ESTORNO-UI-1 — Interface de estorno de pagamento de fatura de cartão.

Fatura de cartão é a mesma tabela Conta (is_fatura_cartao=True), exibida e paga
na tela de Despesas (não em Cartões). O estorno reaproveita o modal existente
de CORE-ESTORNO-1, alternando textos conforme is_fatura_cartao.

- Botão de estorno aparece na coluna de ações de fatura paga
- Modal existe no template e é compartilhado entre despesa e fatura
- JS troca título/aviso conforme is_fatura_cartao
- Payload chama POST /api/despesas/<id>/estornar-pagamento (mesmo endpoint)
"""
from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import db
from backend.routes.despesas import despesas_bp


@pytest.fixture()
def client():
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
    app.register_blueprint(despesas_bp, url_prefix='/api/despesas')

    @app.route('/despesas')
    def despesas_page():
        return render_template('despesas.html', active_page='despesas', page_title='Despesas')

    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


def _js():
    base_dir = Path(__file__).resolve().parents[1]
    return (base_dir / 'frontend' / 'static' / 'js' / 'despesas.js').read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# Modal compartilhado (template)
# ---------------------------------------------------------------------------

def test_template_contem_modal_estorno_com_ids_dinamicos(client):
    html = client.get('/despesas').get_data(as_text=True)

    assert 'modal-estorno' in html
    assert 'estorno-titulo' in html
    assert 'estorno-label-item' in html
    assert 'estorno-aviso-texto' in html
    assert 'estorno-nome-despesa' in html
    assert 'estorno-data' in html
    assert 'estorno-motivo' in html
    assert 'confirmarEstorno' in html


# ---------------------------------------------------------------------------
# JS: botão na listagem de fatura + textos diferenciados
# ---------------------------------------------------------------------------

def test_js_botao_estorno_no_ramo_de_fatura():
    js = _js()

    # O bloco de acoes de fatura (isFaturaCartao ? ...) deve conter o botao de estorno
    inicio = js.index('const acoesHTML = isFaturaCartao ?')
    fim = js.index("` : (isAgrupado ? '' : `", inicio)
    bloco_fatura = js[inicio:fim]

    assert 'abrirModalEstorno' in bloco_fatura
    assert 'despesa.pago' in bloco_fatura


def test_js_modal_estorno_diferencia_fatura_de_despesa():
    js = _js()

    assert 'const ehFatura = despesa.is_fatura_cartao === true' in js
    assert 'Estornar Pagamento da Fatura' in js
    assert "'Fatura' : 'Despesa'" in js
    assert 'crédito compensatório' in js
    assert 'reabrirá a fatura' in js


def test_js_confirmar_estorno_usa_mesmo_endpoint():
    js = _js()

    assert '${API_URL}/${id}/estornar-pagamento' in js
    assert "'Pagamento da fatura estornado com sucesso.'" in js
    assert "'Pagamento estornado com sucesso.'" in js


def test_js_confirmar_estorno_valida_data_e_motivo():
    js = _js()

    inicio = js.index('async function confirmarEstorno(event)')
    fim = js.index('\n}\n', inicio)
    bloco = js[inicio:fim]

    assert 'Informe a data do estorno' in bloco
    assert 'Informe o motivo do estorno' in bloco
    assert 'btnSubmit.disabled = true' in bloco
    assert 'btnSubmit.disabled = false' in bloco
