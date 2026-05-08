from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CARTOES_JS_PATH = ROOT / 'frontend' / 'static' / 'js' / 'cartoes.js'
CARTOES_TEMPLATE_PATH = ROOT / 'frontend' / 'templates' / 'cartoes.html'
CARTOES_CSS_PATH = ROOT / 'frontend' / 'static' / 'css' / 'cartoes.css'
CARTOES_ROUTE_PATH = ROOT / 'backend' / 'routes' / 'cartoes.py'
CARTOES_SERVICE_PATH = ROOT / 'backend' / 'services' / 'cartao_service.py'


def _trecho(texto, inicio, fim):
    start = texto.index(inicio)
    end = texto.index(fim, start)
    return texto[start:end]


def test_ui_diferencia_edicao_individual_de_gestao_de_parcelamento():
    js = CARTOES_JS_PATH.read_text(encoding='utf-8')
    html = CARTOES_TEMPLATE_PATH.read_text(encoding='utf-8')

    assert 'data-action="editar-lancamento"' in js
    assert 'data-action="excluir-lancamento"' in js
    assert 'function lancamentoTemParcelamentoGerenciavel' in js
    assert 'Number(lancamento.parcelas_total || lancamento.total_parcelas || 1) > 1 && Boolean(lancamento.compra_id)' in js
    assert 'data-action="gerenciar-parcelamento"' in js
    assert 'Gerenciar parcelamento' in js
    assert 'modal-editar-lancamento' in html
    assert 'Esta edi&ccedil;&atilde;o altera <strong>apenas este lan&ccedil;amento</strong>' in html


def test_modal_de_gestao_lista_parcelas_e_nao_exibe_categoria_cartao():
    html = CARTOES_TEMPLATE_PATH.read_text(encoding='utf-8')
    js = CARTOES_JS_PATH.read_text(encoding='utf-8')
    css = CARTOES_CSS_PATH.read_text(encoding='utf-8')
    modal = _trecho(html, '<div id="modal-gerenciar-parcelamento"', '{% endblock %}')

    assert 'Gerenciar parcelamento' in modal
    assert 'parcelamento-gestao-resumo' in modal
    assert 'parcelamento-gestao-parcelas' in modal
    for coluna in ['Parcela', 'Compet&ecirc;ncia/Fatura', 'Data', 'Valor', 'Status', 'Observa&ccedil;&atilde;o']:
        assert coluna in modal
    assert 'Categoria da Despesa' in modal
    assert 'Categoria do Cart&atilde;o' not in modal
    assert 'Categoria do Cartão' not in modal
    assert 'Cancelar parcelas futuras' in modal
    assert 'Salvar altera&ccedil;&otilde;es futuras' in modal
    assert 'function abrirModalGerenciarParcelamento' in js
    assert 'function preencherModalGerenciarParcelamento' in js
    assert '.parcelamento-gestao-table' in css


def test_backend_expõe_endpoints_e_agrupa_por_compra_id_sem_migration():
    route = CARTOES_ROUTE_PATH.read_text(encoding='utf-8')
    service = CARTOES_SERVICE_PATH.read_text(encoding='utf-8')

    assert "@cartoes_bp.route('/lancamentos/<int:lancamento_id>/parcelamento', methods=['GET'])" in route
    assert "@cartoes_bp.route('/lancamentos/<int:lancamento_id>/parcelamento/futuras', methods=['PUT'])" in route
    assert "@cartoes_bp.route('/lancamentos/<int:lancamento_id>/parcelamento/cancelar-futuras', methods=['POST'])" in route
    assert 'def consultar_parcelamento_lancamento' in service
    assert 'def atualizar_parcelas_futuras' in service
    assert 'def cancelar_parcelas_futuras' in service
    assert 'LancamentoAgregado.compra_id == lancamento.compra_id' in service
    assert "'compra_id': lancamento.compra_id" in service
    assert 'Parcelamento sem identificador de compra' in service
    assert 'create_table' not in service
    assert 'op.create_table' not in service


def test_edicao_e_cancelamento_afetam_somente_futuras_e_recarregam_fatura():
    js = CARTOES_JS_PATH.read_text(encoding='utf-8')
    service = CARTOES_SERVICE_PATH.read_text(encoding='utf-8')

    assert 'lancamento.mes_fatura > base.mes_fatura' in service
    assert "CartaoService._status_parcela_parcelamento(lancamento, base) == 'futura'" in service
    assert 'CategoriaCartaoService.resolver_categoria_cartao_para_lancamento' in service
    assert 'db.session.delete(parcela)' in service
    assert 'CartaoService.recalcular_fatura(base.cartao_id, competencia)' in service
    assert 'function salvarParcelasFuturas' in js
    assert 'function cancelarParcelasFuturas' in js
    assert 'Esta aÃ§Ã£o afetarÃ¡ apenas as parcelas futuras deste parcelamento' in js
    assert 'await carregarFaturaSelecionada()' in js
    assert 'renderizarDetalheCartao()' in js
