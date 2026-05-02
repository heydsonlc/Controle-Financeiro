from datetime import date

import pytest
from flask import Flask

from backend.models import (
    db,
    CartaoCategoriaLimite,
    Categoria,
    CategoriaCartao,
    ConfigAgregador,
    DespesaPrevista,
    ItemDespesa,
    LancamentoAgregado,
)
from backend.routes.cartoes import cartoes_bp
from backend.routes.categorias import categorias_cartao_bp
from backend.services.cartao_service import CartaoService
from backend.services.categoria_cartao_service import CategoriaCartaoService
from backend.services.despesa_prevista_service import confirmar


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(cartoes_bp, url_prefix='/api/cartoes')
    app.register_blueprint(categorias_cartao_bp, url_prefix='/api/categorias-cartao')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _base_cartao():
    categoria = Categoria(nome='Combustivel', ativo=True)
    categoria_extra = Categoria(nome='IPVA', ativo=True)
    cartao = ItemDespesa(nome='Cartao Teste', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add_all([categoria, categoria_extra, cartao])
    db.session.flush()

    config = ConfigAgregador(
        item_despesa_id=cartao.id,
        dia_fechamento=25,
        dia_vencimento=5,
    )
    db.session.add(config)
    db.session.commit()
    return categoria, categoria_extra, cartao


def _categoria_cartao(nome='Mobilidade'):
    categoria = CategoriaCartaoService.criar_categoria(nome=nome, cor='#0088cc')
    db.session.commit()
    return categoria


def _mapear_e_vincular(cartao, categoria, categoria_cartao=None):
    categoria_cartao = categoria_cartao or _categoria_cartao()
    CategoriaCartaoService.vincular_categoria_despesa(categoria_cartao.id, categoria.id)
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(
        cartao.id,
        categoria_cartao.id,
        limite_mensal='2000.00',
    )
    db.session.commit()
    return categoria_cartao


def test_criar_categoria_cartao(app_context):
    categoria = CategoriaCartaoService.criar_categoria(nome='Mobilidade', descricao='Gastos de deslocamento')
    db.session.commit()

    assert categoria.id
    assert CategoriaCartao.query.filter_by(nome='Mobilidade').count() == 1


def test_vincular_categoria_despesa_a_categoria_cartao(app_context):
    categoria, _extra, _cartao = _base_cartao()
    categoria_cartao = _categoria_cartao()

    vinculo, criado = CategoriaCartaoService.vincular_categoria_despesa(categoria_cartao.id, categoria.id)
    db.session.commit()

    assert criado is True
    assert vinculo.categoria_id == categoria.id
    assert vinculo.categoria_cartao_id == categoria_cartao.id


def test_impede_categoria_despesa_em_duas_categorias_cartao_ativas(app_context):
    categoria, _extra, _cartao = _base_cartao()
    mobilidade = _categoria_cartao('Mobilidade')
    casa = _categoria_cartao('Casa')
    CategoriaCartaoService.vincular_categoria_despesa(mobilidade.id, categoria.id)
    db.session.commit()

    with pytest.raises(ValueError):
        CategoriaCartaoService.vincular_categoria_despesa(casa.id, categoria.id)


def test_resolver_categoria_cartao_por_categoria_despesa(app_context):
    categoria, _extra, _cartao = _base_cartao()
    categoria_cartao = _categoria_cartao()
    CategoriaCartaoService.vincular_categoria_despesa(categoria_cartao.id, categoria.id)
    db.session.commit()

    assert CategoriaCartaoService.resolver_categoria_cartao_por_categoria_despesa(categoria.id) == categoria_cartao.id


def test_resolver_categoria_cartao_inexistente_retorna_none(app_context):
    categoria, _extra, _cartao = _base_cartao()

    assert CategoriaCartaoService.resolver_categoria_cartao_por_categoria_despesa(categoria.id) is None


def test_vincular_categoria_cartao_ao_cartao_com_limite(app_context):
    _categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _categoria_cartao()

    limite, criado = CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(
        cartao.id,
        categoria_cartao.id,
        limite_mensal='1500.50',
    )
    db.session.commit()

    assert criado is True
    assert float(limite.limite_mensal) == 1500.50
    assert CartaoCategoriaLimite.query.count() == 1


def test_validar_categoria_cartao_disponivel_no_cartao(app_context):
    _categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _categoria_cartao()
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(cartao.id, categoria_cartao.id, limite_mensal=100)
    db.session.commit()

    assert CategoriaCartaoService.validar_categoria_cartao_disponivel_no_cartao(cartao.id, categoria_cartao.id) is True


def test_lancamento_manual_cartao_grava_categoria_cartao_id(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)

    lancamento, _fatura = CartaoService.adicionar_lancamento({
        'cartao_id': cartao.id,
        'categoria_id': categoria.id,
        'descricao': 'Posto Teste',
        'valor': 120,
        'data_compra': date(2026, 5, 1),
        'mes_fatura': date(2026, 5, 1),
        'total_parcelas': 1,
    })

    assert lancamento.categoria_cartao_id == categoria_cartao.id


def test_despesa_prevista_cartao_grava_categoria_cartao_id(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)
    despesa = DespesaPrevista(
        origem_tipo='VEICULO',
        origem_id=1,
        categoria_id=categoria.id,
        data_prevista=date(2026, 5, 1),
        data_original_prevista=date(2026, 5, 1),
        data_atual_prevista=date(2026, 5, 1),
        valor_previsto=100,
        status='PREVISTA',
    )
    db.session.add(despesa)
    db.session.commit()

    _despesa, entidade = confirmar(
        despesa.id,
        {
            'meio_pagamento': 'cartao',
            'cartao_id': cartao.id,
            'categoria_id': categoria.id,
            'data_vencimento': '2026-05-01',
        },
    )
    db.session.commit()

    lancamento = LancamentoAgregado.query.get(entidade['id'])
    assert lancamento.categoria_cartao_id == categoria_cartao.id
    assert entidade['categoria_cartao_id'] == categoria_cartao.id


def test_categoria_cartao_manual_prevalece_sobre_resolucao(app_context):
    categoria, _extra, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, categoria, _categoria_cartao('Mobilidade'))
    casa = _categoria_cartao('Casa')
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(cartao.id, casa.id, limite_mensal=500)
    db.session.commit()

    lancamento, _fatura = CartaoService.adicionar_lancamento({
        'cartao_id': cartao.id,
        'categoria_id': categoria.id,
        'categoria_cartao_id': casa.id,
        'descricao': 'Compra Manual',
        'valor': 50,
        'data_compra': date(2026, 5, 1),
        'mes_fatura': date(2026, 5, 1),
        'total_parcelas': 1,
    })

    assert mobilidade.id != casa.id
    assert lancamento.categoria_cartao_id == casa.id
