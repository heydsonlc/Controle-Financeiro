from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_helper_global_carregado_no_base():
    base = read("frontend/templates/base.html")

    assert "css/instituicoes.css" in base
    assert "js/instituicoes.js" in base
    assert base.index("js/icons.js") < base.index("js/instituicoes.js")


def test_aliases_principais_presentes_no_helper():
    helper = read("frontend/static/js/instituicoes.js")

    for alias in [
        "caixa economica federal",
        "caixa econômica federal",
        "banco do brasil",
        "bb",
        "itau",
        "itaú",
        "santander",
        "nubank",
        "nu bank",
        "banco inter",
        "bradesco",
        "c6 bank",
        "mercado pago",
        "mercadopago",
        "picpay",
        "pic pay",
    ]:
        assert alias in helper


def test_assets_genericos_existem_sem_logos_reais():
    assets_dir = ROOT / "frontend/static/assets/instituicoes"
    assert (assets_dir / "default-bank.svg").is_file()
    assert (assets_dir / "default-card.svg").is_file()

    nomes = {path.name for path in assets_dir.iterdir() if path.is_file()}
    assert nomes == {"default-bank.svg", "default-card.svg"}


def test_sem_urls_externas_para_logos():
    arquivos = [
        "frontend/static/js/instituicoes.js",
        "frontend/static/css/instituicoes.css",
        "frontend/static/assets/instituicoes/default-bank.svg",
        "frontend/static/assets/instituicoes/default-card.svg",
    ]

    for arquivo in arquivos:
        conteudo = read(arquivo)
        sem_xmlns = conteudo.replace('xmlns="http://www.w3.org/2000/svg"', "")
        assert "http://" not in sem_xmlns
        assert "https://" not in sem_xmlns
        assert "//cdn" not in sem_xmlns.lower()


def test_contas_bancarias_renderiza_componente_institucional():
    js = read("frontend/static/js/contas_bancarias.js")
    template = read("frontend/templates/contas_bancarias.html")

    assert "renderizarInstituicaoConta" in js
    assert "window.InstituicoesUI" in js
    assert "preview-instituicao-logo" in js
    assert "preview-instituicao-logo" in template


def test_cartoes_renderiza_componente_institucional():
    js = read("frontend/static/js/cartoes.js")

    assert "obterInstituicaoCartao" in js
    assert "window.InstituicoesUI" in js
    assert "renderizarMarcaCartao(cartao, 'sm')" in js


def test_fallback_nome_vazio_e_desconhecido_documentado_no_helper():
    helper = read("frontend/static/js/instituicoes.js")

    assert "Instituicao nao informada" in helper
    assert "key: 'default'" in helper
    assert "default-bank.svg" in helper
    assert "default-card.svg" in helper
