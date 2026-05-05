from datetime import date
from pathlib import Path

import pytest
from flask import Flask

from backend.models import (
    db,
    Categoria,
    CategoriaCartao,
    ConfigAgregador,
    DespesaPrevista,
    ItemDespesa,
    LancamentoAgregado,
)
from backend.routes.cartoes import cartoes_bp
from backend.routes.despesas import despesas_bp
from backend.routes.recorrencias import recorrencias_bp
from backend.services.categoria_cartao_service import CategoriaCartaoService
from backend.services.despesa_prevista_service import confirmar


ROOT = Path(__file__).resolve().parents[1]


def read(rel_path):
    return (ROOT / rel_path).read_text(encoding="utf-8")


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(cartoes_bp, url_prefix="/api/cartoes")
    app.register_blueprint(despesas_bp, url_prefix="/api/despesas")
    app.register_blueprint(recorrencias_bp, url_prefix="/api/recorrencias")

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _base_cartao():
    categoria = Categoria(nome="Combustivel", ativo=True)
    cartao = ItemDespesa(nome="Cartao Operacional", tipo="Agregador", ativo=True, recorrente=True)
    db.session.add_all([categoria, cartao])
    db.session.flush()
    db.session.add(ConfigAgregador(item_despesa_id=cartao.id, dia_fechamento=25, dia_vencimento=5))
    db.session.commit()
    return categoria, cartao


def _categoria_cartao(nome):
    categoria = CategoriaCartao(nome=nome, cor="#2563eb", ativo=True)
    db.session.add(categoria)
    db.session.flush()
    return categoria


def _mapear_e_vincular(cartao, categoria, nome="Mobilidade"):
    categoria_cartao = _categoria_cartao(nome)
    CategoriaCartaoService.vincular_categoria_despesa(categoria_cartao.id, categoria.id)
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(
        cartao.id,
        categoria_cartao.id,
        limite_mensal="2000.00",
    )
    db.session.commit()
    return categoria_cartao


def _categoria_cartao_extra_no_cartao(cartao, nome="Casa"):
    categoria_cartao = _categoria_cartao(nome)
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(cartao.id, categoria_cartao.id, limite_mensal="500.00")
    db.session.commit()
    return categoria_cartao


def test_lancamento_com_cartao_nao_exige_categoria_cartao_manual(app_context):
    categoria, cartao = _base_cartao()

    with app_context.test_client() as client:
        response = client.post(f"/api/cartoes/{cartao.id}/lancamentos", json={
            "categoria_id": categoria.id,
            "descricao": "Posto sem mapa",
            "valor": "120.00",
            "data_compra": "2026-05-01",
            "mes_fatura": "2026-05",
        })

    assert response.status_code == 201
    lancamento = LancamentoAgregado.query.one()
    assert lancamento.categoria_cartao_id is None
    assert lancamento.item_agregado_id is None


def test_lancamento_com_categoria_vinculada_resolve_categoria_cartao(app_context):
    categoria, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)

    with app_context.test_client() as client:
        response = client.post(f"/api/cartoes/{cartao.id}/lancamentos", json={
            "categoria_id": categoria.id,
            "descricao": "Posto com mapa",
            "valor": "120.00",
            "data_compra": "2026-05-01",
            "mes_fatura": "2026-05",
        })

    assert response.status_code == 201
    lancamento = LancamentoAgregado.query.one()
    assert lancamento.categoria_cartao_id == categoria_cartao.id


def test_lancamento_operacional_ignora_categoria_cartao_manual(app_context):
    categoria, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, categoria, "Mobilidade")
    casa = _categoria_cartao_extra_no_cartao(cartao, "Casa")

    with app_context.test_client() as client:
        response = client.post(f"/api/cartoes/{cartao.id}/lancamentos", json={
            "categoria_id": categoria.id,
            "categoria_cartao_id": casa.id,
            "descricao": "Manual ignorado",
            "valor": "80.00",
            "data_compra": "2026-05-01",
            "mes_fatura": "2026-05",
        })

    assert response.status_code == 201
    lancamento = LancamentoAgregado.query.one()
    assert lancamento.categoria_cartao_id == mobilidade.id


def test_recorrencia_com_cartao_resolve_categoria_cartao_automaticamente(app_context):
    categoria, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, categoria, "Mobilidade")
    casa = _categoria_cartao_extra_no_cartao(cartao, "Casa")

    with app_context.test_client() as client:
        response = client.post("/api/recorrencias/", json={
            "nome": "Combustivel recorrente",
            "valor": "300.00",
            "categoria_id": categoria.id,
            "data_vencimento": "2026-05-10",
            "tipo_recorrencia": "mensal",
            "meio_pagamento": "cartao",
            "cartao_id": cartao.id,
            "categoria_cartao_id": casa.id,
        })

    assert response.status_code == 201
    data = response.get_json()
    assert data["data"]["categoria_cartao_id"] == mobilidade.id


def test_mobilidade_efetivacao_resolve_categoria_cartao_automaticamente(app_context):
    categoria, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, categoria, "Mobilidade")
    casa = _categoria_cartao_extra_no_cartao(cartao, "Casa")
    prevista = DespesaPrevista(
        origem_tipo="VEICULO",
        origem_id=1,
        categoria_id=categoria.id,
        data_prevista=date(2026, 5, 1),
        data_original_prevista=date(2026, 5, 1),
        data_atual_prevista=date(2026, 5, 1),
        valor_previsto=100,
        status="PREVISTA",
    )
    db.session.add(prevista)
    db.session.commit()

    _despesa, entidade = confirmar(prevista.id, {
        "meio_pagamento": "cartao",
        "cartao_id": cartao.id,
        "categoria_id": categoria.id,
        "categoria_cartao_id": casa.id,
        "data_vencimento": "2026-05-01",
    })
    db.session.commit()

    assert entidade["categoria_cartao_id"] == mobilidade.id


def test_templates_nao_exibem_select_manual_de_categoria_cartao_operacional():
    lancamentos = read("frontend/templates/lancamentos.html")
    recorrencias = read("frontend/templates/recorrencias.html")
    veiculos = read("frontend/templates/veiculos.html")

    assert '<select id="lancamento-categoria-cartao"' not in lancamentos
    assert '<select id="categoria-cartao-id"' not in recorrencias
    assert '<select id="confirmar-categoria-cartao-id"' not in veiculos
    assert '<select id="ativar-mob-categoria-cartao-id"' not in veiculos


def test_despesas_tem_coluna_e_filtro_de_forma_de_pagamento():
    despesas_html = read("frontend/templates/despesas.html")
    despesas_js = read("frontend/static/js/despesas.js")

    assert "filtro-forma-pagamento" in despesas_html
    assert "filtro-categoria" not in despesas_html
    assert "despesa-cell-forma-pagamento" in despesas_js
    assert "FormasPagamentoUI.renderFormaPagamento" in despesas_js


def test_api_despesas_expoe_meio_pagamento_para_filtro(app_context):
    categoria, _cartao = _base_cartao()

    with app_context.test_client() as client:
        response = client.post("/api/despesas/", json={
            "nome": "Despesa Pix",
            "valor": "25.50",
            "categoria_id": categoria.id,
            "data_vencimento": "2026-05-05",
            "pago": False,
            "recorrente": True,
            "tipo_recorrencia": "mensal",
            "meio_pagamento": "pix",
            "mes_competencia": "2026-05",
        })
        assert response.status_code == 201

        lista = client.get("/api/despesas/?mes_referencia=2026-05").get_json()

    assert lista["success"] is True
    assert lista["data"][0]["meio_pagamento"] == "pix"


def test_lancamentos_tem_acoes_no_cabecalho_do_painel():
    lancamentos = read("frontend/templates/lancamentos.html")

    assert "lanc-panel-actions" in lancamentos
    assert "form=\"form-lancamento\"" in lancamentos
    assert "Salvar lan&ccedil;amento</button>" not in lancamentos


def test_item_agregado_id_nao_volta_a_ser_exigido_no_fluxo_cartao(app_context):
    categoria, cartao = _base_cartao()
    _mapear_e_vincular(cartao, categoria)

    with app_context.test_client() as client:
        response = client.post(f"/api/cartoes/{cartao.id}/lancamentos", json={
            "categoria_id": categoria.id,
            "descricao": "Sem item agregado",
            "valor": "50.00",
            "data_compra": "2026-05-01",
            "mes_fatura": "2026-05",
        })

    assert response.status_code == 201
    assert LancamentoAgregado.query.one().item_agregado_id is None


def test_formas_pagamento_ui_usado_nas_telas_integradas():
    for rel_path in [
        "frontend/static/js/despesas.js",
        "frontend/static/js/lancamentos.js",
        "frontend/static/js/recorrencias.js",
        "frontend/static/js/veiculos.js",
    ]:
        assert "FormasPagamentoUI" in read(rel_path)
