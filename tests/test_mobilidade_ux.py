from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app import create_app
from backend.models import (
    CartaoCategoriaLimite,
    Categoria,
    CategoriaCartao,
    CategoriaCartaoDespesa,
    ConfigAgregador,
    DespesaPrevista,
    ItemDespesa,
    PerfilFinanceiro,
    Veiculo,
    db,
)
from backend.services.perfil_financeiro_service import PERFIL_SESSION_KEY, PerfilFinanceiroService
from backend.services.veiculo_service import calcular_total_mensal_estimado_veiculo
from tests.conftest import autenticar_cliente_teste


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return autenticar_cliente_teste(app.test_client(), app)


def _perfil(nome):
    return PerfilFinanceiro.query.filter_by(nome=nome).first()


def test_rota_veiculos_renderiza_com_nome_visual_mobilidade(client):
    response = client.get("/veiculos")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<span>Mobilidade</span>" in html
    assert "Comparador de Mobilidade" in html
    assert "Cadastro de Modalidades" in html
    assert 'href="/veiculos"' in html


def test_menu_exibe_mobilidade_sem_renomear_rota(client):
    html = client.get("/veiculos").get_data(as_text=True)

    assert '<a href="/veiculos"' in html
    assert '<span class="app-nav-text">Mobilidade</span>' in html
    assert '<span class="app-nav-text">Veículos</span>' not in html


def test_cards_de_comparacao_usam_imagem_local_ou_fallback():
    js = (ROOT / "frontend/static/js/veiculos.js").read_text(encoding="utf-8")

    assert "comp-card-image" in js
    assert "mobility-image-fallback" in js
    assert "renderImagemModalidade(c)" in js
    assert "http://" not in js
    assert "https://" not in js


def test_imagens_proprias_de_assinatura_e_app_estao_mapeadas():
    js = (ROOT / "frontend/static/js/veiculos.js").read_text(encoding="utf-8")

    assert (ROOT / "frontend/static/img/transporte_por_assinatura.png").exists()
    assert (ROOT / "frontend/static/img/Transporte_por_App.png").exists()
    assert "transporte_por_assinatura.png" in js
    assert "Transporte_por_App.png" in js


def test_total_mensal_soma_componentes_e_nao_fica_zero():
    veiculo = Veiculo(
        nome="Honda City",
        tipo="carro",
        combustivel="gasolina",
        autonomia_km_l=Decimal("12.0"),
        status="ATIVO",
        data_inicio=date(2026, 5, 1),
        combustivel_valor_mensal=Decimal("630.00"),
        seguro_valor=Decimal("1900.00"),
        ipva_valor=Decimal("1540.00"),
        licenciamento_valor=Decimal("130.00"),
    )

    total = calcular_total_mensal_estimado_veiculo(veiculo)

    assert total > 0
    assert float(total) == pytest.approx(927.50, abs=0.01)


def test_api_veiculos_expoe_total_mensal_estimado(client, app):
    with app.app_context():
        pessoal = _perfil("Pessoal")
        veiculo = Veiculo(
            perfil_financeiro_id=pessoal.id,
            nome="Honda City",
            tipo="carro",
            combustivel="gasolina",
            autonomia_km_l=Decimal("12.0"),
            status="ATIVO",
            data_inicio=date(2026, 5, 1),
            combustivel_valor_mensal=Decimal("630.00"),
            seguro_valor=Decimal("1900.00"),
            ipva_valor=Decimal("1540.00"),
            licenciamento_valor=Decimal("130.00"),
        )
        db.session.add(veiculo)
        db.session.commit()

    response = client.get("/api/veiculos")
    data = response.get_json()

    assert response.status_code == 200
    assert data["success"] is True
    assert data["data"][0]["total_mensal_estimado"] == pytest.approx(927.50, abs=0.01)
    assert data["data"][0]["resumo_mensal_estimado"]["combustivel_mensal"] == pytest.approx(630.00)


def test_modal_confirmacao_contem_campos_esperados(client):
    html = client.get("/veiculos").get_data(as_text=True)

    assert "Confirmar despesa prevista" in html
    assert "confirmar-meio" in html
    assert "Conta ou cartão" in html
    assert "confirmar-categoria-cartao-id" in html
    assert "confirmar-data-vencimento" in html
    assert "confirmar-observacao" in html
    assert "Confirmar e gerar lançamento" in html


def test_categoria_do_cartao_preservada_ao_confirmar_prevista(client, app):
    with app.app_context():
        pessoal = _perfil("Pessoal")
        cat = Categoria(nome="Mobilidade", cor="#1e40af", ativo=True, perfil_financeiro_id=pessoal.id)
        cartao = ItemDespesa(
            nome="Cartão Mobilidade",
            tipo="Agregador",
            ativo=True,
            recorrente=True,
            perfil_financeiro_id=pessoal.id,
        )
        cc = CategoriaCartao(nome="Mobilidade CC", cor="#0088cc", ativo=True, perfil_financeiro_id=pessoal.id)
        db.session.add_all([cat, cartao, cc])
        db.session.flush()
        db.session.add(ConfigAgregador(item_despesa_id=cartao.id, dia_fechamento=25, dia_vencimento=5))
        db.session.add(CategoriaCartaoDespesa(
            categoria_id=cat.id,
            categoria_cartao_id=cc.id,
            ativo=True,
            perfil_financeiro_id=pessoal.id,
        ))
        db.session.add(CartaoCategoriaLimite(
            cartao_id=cartao.id,
            categoria_cartao_id=cc.id,
            limite_mensal=Decimal("2000.00"),
            ativo=True,
            perfil_financeiro_id=pessoal.id,
        ))
        desp = DespesaPrevista(
            perfil_financeiro_id=pessoal.id,
            origem_tipo="VEICULO",
            origem_id=1,
            categoria_id=cat.id,
            data_prevista=date(2026, 5, 1),
            data_original_prevista=date(2026, 5, 1),
            data_atual_prevista=date(2026, 5, 1),
            valor_previsto=Decimal("130.00"),
            status="PREVISTA",
            metadata_json='{"tipo_evento":"LICENCIAMENTO"}',
        )
        db.session.add(desp)
        db.session.commit()
        desp_id = desp.id
        cartao_id = cartao.id
        cat_id = cat.id
        cc_id = cc.id
        perfil_id = pessoal.id

    with client.session_transaction() as sess:
        sess[PERFIL_SESSION_KEY] = perfil_id

    response = client.post(
        f"/api/despesas-previstas/{desp_id}/confirmar",
        json={
            "meio_pagamento": "cartao",
            "cartao_id": cartao_id,
            "categoria_id": cat_id,
            "categoria_cartao_id": cc_id,
            "data_vencimento": "2026-05-10",
        },
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["success"] is True
    assert data["data"]["entidade_criada"]["categoria_cartao_id"] == cc_id


def test_perfil_financeiro_isola_veiculos_por_empresa(client, app):
    with app.app_context():
        pessoal = _perfil("Pessoal")
        empresa = _perfil("Empresa")
        db.session.add_all([
            Veiculo(
                perfil_financeiro_id=pessoal.id,
                nome="Carro Pessoal",
                tipo="carro",
                combustivel="gasolina",
                autonomia_km_l=Decimal("12"),
                status="SIMULADO",
            ),
            Veiculo(
                perfil_financeiro_id=empresa.id,
                nome="Carro Empresa",
                tipo="carro",
                combustivel="gasolina",
                autonomia_km_l=Decimal("11"),
                status="SIMULADO",
            ),
        ])
        db.session.commit()
        pessoal_id = pessoal.id
        empresa_id = empresa.id

    with client.session_transaction() as sess:
        sess[PERFIL_SESSION_KEY] = pessoal_id
    pessoal_data = client.get("/api/veiculos").get_json()["data"]

    with client.session_transaction() as sess:
        sess[PERFIL_SESSION_KEY] = empresa_id
    empresa_data = client.get("/api/veiculos").get_json()["data"]

    assert [v["nome"] for v in pessoal_data] == ["Carro Pessoal"]
    assert [v["nome"] for v in empresa_data] == ["Carro Empresa"]


def test_smoke_assets_e_componentes_mobilidade():
    template = (ROOT / "frontend/templates/veiculos.html").read_text(encoding="utf-8")
    css = (ROOT / "frontend/static/css/veiculos.css").read_text(encoding="utf-8")

    assert "comp-detalhe-selecionado" in template
    assert "conf-subtab-assinatura" in template
    assert "modal-assinatura" in template
    assert ".comp-detalhe-selecionado" in css
    assert ".conf-item-thumb" in css
