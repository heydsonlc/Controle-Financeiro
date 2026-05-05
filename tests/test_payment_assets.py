from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel_path):
    return (ROOT / rel_path).read_text(encoding="utf-8")


def test_payment_helper_files_exist():
    assert (ROOT / "frontend/static/js/formas_pagamento.js").exists()
    assert (ROOT / "frontend/static/css/formas_pagamento.css").exists()


def test_base_loads_payment_assets_before_page_scripts():
    base = read("frontend/templates/base.html")
    css_ref = "css/formas_pagamento.css"
    js_ref = "js/formas_pagamento.js"

    assert css_ref in base
    assert js_ref in base
    assert base.index(js_ref) < base.index("{% block extra_js %}")


def test_helper_contains_required_aliases():
    helper = read("frontend/static/js/formas_pagamento.js")

    for alias in [
        "pagamento instantâneo",
        "transferência pix",
        "cartão de crédito",
        "cartão de débito",
        "linha digitável",
        "em espécie",
        "transferência bancária",
        "débito automático",
    ]:
        assert alias in helper


def test_helper_uses_only_local_icon_paths():
    helper = read("frontend/static/js/formas_pagamento.js")
    styles = read("frontend/static/css/formas_pagamento.css")

    assert "http://" not in helper
    assert "https://" not in helper
    assert "http://" not in styles
    assert "https://" not in styles
    assert "/static/img/" in helper


def test_expected_local_icon_assets_are_mapped():
    helper = read("frontend/static/js/formas_pagamento.js")

    expected_assets = [
        "logo_pix.png",
        "icone_dinheiro.jpg",
        "icone_boleto.jpg",
        "logo_bandeira_cartao_visa.png",
        "trasnferencia_icone.jpg",
    ]

    for asset in expected_assets:
        assert asset in helper
        assert (ROOT / "frontend/static/img" / asset).exists()


def test_payment_fallback_is_defined():
    helper = read("frontend/static/js/formas_pagamento.js")
    styles = read("frontend/static/css/formas_pagamento.css")

    assert "iconeFallback" in helper
    assert "payment-method--fallback" in helper
    assert ".payment-method--fallback" in styles
    assert "payment-method--default" in helper


def test_despesas_uses_payment_helper():
    despesas = read("frontend/static/js/despesas.js")

    assert "FormasPagamentoUI.renderFormaPagamento" in despesas
    assert "despesa-payment-method" in despesas


def test_lancamentos_or_recorrencias_use_payment_helper():
    lancamentos = read("frontend/static/js/lancamentos.js")
    recorrencias = read("frontend/static/js/recorrencias.js")

    assert "FormasPagamentoUI.renderFormaPagamento" in lancamentos
    assert "FormasPagamentoUI.renderFormaPagamento" in recorrencias
    assert "lancamento-payment-method" in lancamentos
    assert "recorrencia-payment-method" in recorrencias


def test_mobilidade_uses_payment_helper_without_payload_changes():
    veiculos = read("frontend/static/js/veiculos.js")

    assert "renderFormaPagamentoMobilidade" in veiculos
    assert "mobilidade-payment-method" in veiculos
    assert "meio_pagamento" in veiculos
