"""
Testes CORE-ESTORNO-UI-1 — Interface de estorno de pagamento de parcela de
financiamento.

- Botão de estorno aparece na coluna de ações do cronograma para parcela paga
- Parcela pendente continua mostrando o botão de registrar pagamento (não estorno)
- Backend não expõe se o pagamento foi direto ou via despesa vinculada, então o
  botão aparece sempre que status='pago' — o backend bloqueia com mensagem clara
  quando a parcela foi paga via despesa vinculada (não inventar regra no frontend)
- Modal contém aviso correto e payload chama o endpoint certo
"""
from pathlib import Path


def _js():
    base_dir = Path(__file__).resolve().parents[1]
    return (base_dir / 'frontend' / 'static' / 'js' / 'financiamentos.js').read_text(encoding='utf-8')


def _html():
    base_dir = Path(__file__).resolve().parents[1]
    return (base_dir / 'frontend' / 'templates' / 'financiamentos.html').read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# Template: modal de estorno
# ---------------------------------------------------------------------------

def test_template_contem_modal_estorno_parcela():
    html = _html()

    assert 'modal-estornar-parcela' in html
    assert 'estornar-parcela-id' in html
    assert 'estornar-parcela-info' in html
    assert 'estornar-parcela-data' in html
    assert 'estornar-parcela-motivo' in html
    assert 'confirmarEstornoParcela' in html
    assert 'não apaga' in html
    assert 'crédito compensatório' in html
    assert 'reabrirá a parcela' in html


# ---------------------------------------------------------------------------
# JS: botão condicional na tabela de parcelas
# ---------------------------------------------------------------------------

def test_js_botao_estorno_aparece_apenas_para_parcela_paga():
    js = _js()

    inicio = js.index('function renderizarTabelaParcelas')
    fim = js.index('\n}\n', inicio)
    bloco = js[inicio:fim]

    assert 'abrirModalEstornoParcela' in bloco
    assert 'abrirModalPagamento' in bloco

    # A ordem no ternario deve ser: pago -> estorno, senao -> pagar
    pos_pago_check = bloco.index('const pago =')
    pos_estorno_btn = bloco.index('abrirModalEstornoParcela')
    pos_pagar_btn = bloco.index('abrirModalPagamento')
    assert pos_pago_check < pos_estorno_btn < pos_pagar_btn


def test_js_expoe_funcoes_de_estorno_parcela():
    js = _js()

    assert 'function abrirModalEstornoParcela' in js
    assert 'function confirmarEstornoParcela' in js
    assert '/parcelas/${parcelaId}/estornar-pagamento' in js


def test_js_confirmar_estorno_parcela_valida_data_e_motivo():
    js = _js()

    inicio = js.index('async function confirmarEstornoParcela(event)')
    fim = js.index('\n}\n', inicio)
    bloco = js[inicio:fim]

    assert 'Informe a data do estorno' in bloco
    assert 'Informe o motivo do estorno' in bloco
    assert 'btnSubmit.disabled = true' in bloco
    assert 'btnSubmit.disabled = false' in bloco
    assert "'Pagamento da parcela estornado com sucesso.'" in bloco


def test_js_estorno_recarrega_detalhe_apos_sucesso():
    js = _js()

    inicio = js.index('async function confirmarEstornoParcela(event)')
    fim = js.index('\n}\n', inicio)
    bloco = js[inicio:fim]

    assert 'verDetalhes(' in bloco
    assert "fecharModal('modal-estornar-parcela')" in bloco
