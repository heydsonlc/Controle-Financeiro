from pathlib import Path

import pytest
from flask import Flask, render_template


@pytest.fixture()
def app_context():
    base_dir = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(base_dir / 'frontend' / 'templates'),
        static_folder=str(base_dir / 'frontend' / 'static'),
    )
    app.config.update(TESTING=True)

    @app.route('/lancamentos')
    def lancamentos_page():
        return render_template(
            'lancamentos.html',
            active_page='lancamentos',
            page_title='Lançamentos',
        )

    yield app


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


def test_rota_principal_lancamentos_renderiza(client):
    response = client.get('/lancamentos')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Lançamentos' in html or 'Lan&ccedil;amentos' in html
    assert 'module-actionbar' in html


def test_template_contem_action_bar_filtros_e_busca(client):
    html = client.get('/lancamentos').get_data(as_text=True)

    for campo in [
        'filtro-tipo',
        'filtro-mes',
        'filtro-cartao',
        'filtro-categoria',
        'filtro-status',
        'filtro-busca',
    ]:
        assert campo in html

    assert 'Atualizar' in html
    assert 'Filtros' in html
    assert 'Novo lan&ccedil;amento' in html


def test_template_contem_painel_inline_novo_lancamento(client):
    html = client.get('/lancamentos').get_data(as_text=True)

    assert 'painel-novo-lancamento' in html
    assert 'form-lancamento' in html
    assert '<div id="modal-lancamento"' not in html

    for campo in [
        'lancamento-tipo',
        'lancamento-descricao',
        'lancamento-valor',
        'lancamento-data',
        'lancamento-parcelas',
        'lancamento-mes-fatura',
        'lancamento-observacoes',
    ]:
        assert campo in html


def test_template_contem_blocos_operacionais(client):
    html = client.get('/lancamentos').get_data(as_text=True)

    assert 'lanc-summary-grid' in html
    assert 'Entradas no m&ecirc;s' in html
    assert 'Sa&iacute;das no m&ecirc;s' in html
    assert 'Pendentes' in html
    assert 'Confirmados' in html
    assert 'Saldo do per&iacute;odo' in html
    assert 'lista-receitas-pendentes' in html
    assert 'lista-lancamentos' in html
    assert 'Composi&ccedil;&atilde;o por tipo' in html
    assert 'Resumo do per&iacute;odo' in html


def test_template_preserva_modal_confirmar_receita(client):
    html = client.get('/lancamentos').get_data(as_text=True)

    assert 'modal-confirmar-receita' in html
    assert 'form-confirmar-receita' in html
    assert 'confirmarRecebimento(event)' in html


def test_template_preserva_handlers_existentes_de_salvar_e_filtros(client):
    html = client.get('/lancamentos').get_data(as_text=True)

    assert 'salvarLancamento(event)' in html
    assert 'alternarTipoLancamento()' in html
    assert 'carregarCategoriasPorCartao()' in html
    assert 'abrirModalLancamento()' in html
    assert 'cancelarLancamentoInline()' in html
