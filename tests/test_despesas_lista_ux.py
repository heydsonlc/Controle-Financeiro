from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _header_block(js: str) -> str:
    marker = '<div class="despesas-grade-header">'
    start = js.index(marker)
    end = js.index("</div>\n    `];", start)
    return js[start:end]


def test_tabela_despesas_tem_nova_ordem_de_colunas():
    js = _read("frontend/static/js/despesas.js")
    header = _header_block(js)

    colunas = [
        "Nome da despesa",
        "Detalhe da despesa",
        "Forma de pagamento",
        "Status",
        "Vencimento",
        "Categoria da despesa",
        "Valor",
        "A&ccedil;&otilde;es",
    ]

    posicoes = [header.index(coluna) for coluna in colunas]
    assert posicoes == sorted(posicoes)
    assert "Compet&ecirc;ncia" not in header
    assert "<div>Tipo</div>" not in header


def test_linhas_usam_grid_unico_com_forma_status_e_acoes():
    js = _read("frontend/static/js/despesas.js")

    for classe in [
        "despesa-cell-nome",
        "despesa-cell-detalhe",
        "despesa-cell-forma-pagamento",
        "despesa-cell-status",
        "despesa-cell-vencimento",
        "despesa-cell-categoria",
        "despesa-cell-valor",
        "despesa-cell-acoes",
    ]:
        assert js.count(classe) >= 3

    assert "showLabel: true" in js
    assert "renderFormaPagamentoDespesa" in js
    assert "row-action-button" in js


def test_css_forca_linha_unica_e_conteudo_centralizado():
    css = _read("frontend/static/css/despesas.css")

    assert "grid-template-columns:" in css
    assert "minmax(210px, 22fr)" in css
    assert "minmax(90px, 6fr)" in css
    assert "white-space: nowrap" in css
    assert "overflow: hidden" in css
    assert "text-overflow: ellipsis" in css
    assert ".despesa-cell-valor" in css
    assert "justify-content: center" in css
    assert "text-align: center" in css

