from datetime import date

import pytest
from flask import Flask

from backend.models import (
    db,
    Categoria,
    CategoriaCartao,
    ConfigAgregador,
    ItemDespesa,
    LancamentoAgregado,
)
from backend.routes.cartoes import cartoes_bp
from backend.services.cartao_service import CartaoService
from backend.services.categoria_cartao_service import CategoriaCartaoService


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

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _cartao():
    cartao = ItemDespesa(nome='Cartao Teste', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add(cartao)
    db.session.flush()
    db.session.add(ConfigAgregador(
        item_despesa_id=cartao.id,
        dia_fechamento=25,
        dia_vencimento=5,
    ))
    db.session.commit()
    return cartao


def _categoria(nome):
    categoria = Categoria(nome=nome, ativo=True)
    db.session.add(categoria)
    db.session.commit()
    return categoria


def _categoria_cartao(nome, cor='#2563eb'):
    categoria = CategoriaCartaoService.criar_categoria(nome=nome, cor=cor)
    db.session.commit()
    return categoria


def _vincular(cartao, categoria, categoria_cartao, limite='2000.00'):
    CategoriaCartaoService.vincular_categoria_despesa(categoria_cartao.id, categoria.id)
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(
        cartao.id,
        categoria_cartao.id,
        limite_mensal=limite,
    )
    db.session.commit()
    return categoria_cartao


def _lancamento(cartao, categoria, valor, categoria_cartao=None, descricao='Lancamento Teste'):
    lancamento = LancamentoAgregado(
        cartao_id=cartao.id,
        categoria_id=categoria.id,
        categoria_cartao_id=categoria_cartao.id if categoria_cartao else None,
        descricao=descricao,
        valor=valor,
        data_compra=date(2026, 5, 10),
        mes_fatura=date(2026, 5, 1),
        numero_parcela=1,
        total_parcelas=1,
    )
    db.session.add(lancamento)
    db.session.commit()
    return lancamento


def _grupo(resumo, nome):
    return next(item for item in resumo['categorias'] if item['categoria_cartao_nome'] == nome)


def test_categoria_vinculada_com_limite_e_lancamento_calcula_consumo(app_context):
    cartao = _cartao()
    combustivel = _categoria('Combustivel')
    mobilidade = _vincular(cartao, combustivel, _categoria_cartao('Mobilidade'), limite='2000.00')
    _lancamento(cartao, combustivel, 500, mobilidade)

    resumo = CartaoService.obter_resumo_fatura_por_categoria_cartao(cartao.id, '2026-05')
    grupo = _grupo(resumo, 'Mobilidade')

    assert grupo['limite_mensal'] == 2000.0
    assert grupo['gasto_atual'] == 500.0
    assert grupo['disponivel'] == 1500.0
    assert grupo['percentual'] == 25.0
    assert grupo['status'] == 'Normal'
    assert grupo['quantidade_lancamentos'] == 1
    assert LancamentoAgregado.query.one().item_agregado_id is None


def test_categoria_vinculada_sem_lancamento_aparece_com_gasto_zero(app_context):
    cartao = _cartao()
    casa = _categoria('Casa Despesa')
    categoria_cartao = _vincular(cartao, casa, _categoria_cartao('Casa'), limite='800.00')

    resumo = CartaoService.obter_resumo_fatura_por_categoria_cartao(cartao.id, '2026-05')
    grupo = _grupo(resumo, categoria_cartao.nome)

    assert grupo['gasto_atual'] == 0.0
    assert grupo['disponivel'] == 800.0
    assert grupo['percentual'] == 0
    assert grupo['status'] == 'Normal'


def test_lancamento_sem_categoria_cartao_aparece_em_grupo_proprio(app_context):
    cartao = _cartao()
    combustivel = _categoria('Combustivel')
    _lancamento(cartao, combustivel, 120, categoria_cartao=None)

    resumo = CartaoService.obter_resumo_fatura_por_categoria_cartao(cartao.id, '2026-05')
    grupo = _grupo(resumo, 'Sem Categoria do Cartao')

    assert grupo['sem_categoria'] is True
    assert grupo['gasto_atual'] == 120.0
    assert grupo['limite_mensal'] is None
    assert grupo['disponivel'] is None
    assert grupo['percentual'] is None
    assert grupo['status'] == 'Revisar'
    assert resumo['total_sem_categoria_cartao'] == 120.0


def test_categoria_cartao_nao_vinculada_gera_grupo_com_aviso(app_context):
    cartao = _cartao()
    farmacia = _categoria('Farmacia')
    saude = _categoria_cartao('Saude')
    _lancamento(cartao, farmacia, 90, saude)

    resumo = CartaoService.obter_resumo_fatura_por_categoria_cartao(cartao.id, '2026-05')
    grupo = _grupo(resumo, 'Saude')

    assert grupo['categoria_cartao_id'] == saude.id
    assert grupo['vinculada_ao_cartao'] is False
    assert grupo['categoria_sem_limite'] is True
    assert grupo['status'] == 'Revisar'
    assert grupo['avisos'] == ['Categoria sem limite neste cartao.']


def test_totais_da_fatura_somam_com_e_sem_categoria(app_context):
    cartao = _cartao()
    combustivel = _categoria('Combustivel')
    mercado = _categoria('Mercado')
    farmacia = _categoria('Farmacia')
    mobilidade = _vincular(cartao, combustivel, _categoria_cartao('Mobilidade'), limite='2000.00')
    saude = _categoria_cartao('Saude')
    _lancamento(cartao, combustivel, 250, mobilidade)
    _lancamento(cartao, mercado, 60, None)
    _lancamento(cartao, farmacia, 40, saude)

    resumo = CartaoService.obter_resumo_fatura_por_categoria_cartao(cartao.id, '2026-05')

    assert resumo['total_fatura'] == 350.0
    assert resumo['total_com_categoria'] == 290.0
    assert resumo['total_sem_categoria_cartao'] == 60.0
    assert resumo['limite_total'] == 2000.0
    assert resumo['disponivel_total'] == 1750.0
    assert resumo['percentual_total'] == 12.5


def test_status_normal_atencao_e_estourado(app_context):
    cartao = _cartao()
    normal = _vincular(cartao, _categoria('Normal Despesa'), _categoria_cartao('Normal'), limite='100.00')
    atencao = _vincular(cartao, _categoria('Atencao Despesa'), _categoria_cartao('Atencao'), limite='100.00')
    estourado = _vincular(cartao, _categoria('Estourado Despesa'), _categoria_cartao('Estourado'), limite='100.00')
    _lancamento(cartao, normal.despesas_vinculadas.first().categoria, 80, normal)
    _lancamento(cartao, atencao.despesas_vinculadas.first().categoria, 90, atencao)
    _lancamento(cartao, estourado.despesas_vinculadas.first().categoria, 120, estourado)

    resumo = CartaoService.obter_resumo_fatura_por_categoria_cartao(cartao.id, '2026-05')

    assert _grupo(resumo, 'Normal')['status'] == 'Normal'
    assert _grupo(resumo, 'Atencao')['status'] == 'Atencao'
    assert _grupo(resumo, 'Estourado')['status'] == 'Estourado'


def test_endpoint_lancamentos_filtra_por_categoria_cartao(app_context):
    cartao = _cartao()
    combustivel = _categoria('Combustivel')
    mercado = _categoria('Mercado')
    mobilidade = _vincular(cartao, combustivel, _categoria_cartao('Mobilidade'), limite='2000.00')
    alimentacao = _vincular(cartao, mercado, _categoria_cartao('Alimentacao'), limite='1000.00')
    _lancamento(cartao, combustivel, 100, mobilidade, descricao='Posto')
    _lancamento(cartao, mercado, 200, alimentacao, descricao='Mercado')

    with app_context.test_client() as client:
        response = client.get(
            f'/api/cartoes/{cartao.id}/fatura-lancamentos?mes_referencia=2026-05&categoria_cartao_id={mobilidade.id}'
        )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert len(data['lancamentos']) == 1
    assert data['lancamentos'][0]['descricao'] == 'Posto'
    assert data['lancamentos'][0]['categoria_cartao_id'] == mobilidade.id
    assert data['lancamentos'][0]['status_classificacao'] == 'classificado'


def test_endpoint_lancamentos_filtra_sem_categoria(app_context):
    cartao = _cartao()
    combustivel = _categoria('Combustivel')
    mobilidade = _vincular(cartao, combustivel, _categoria_cartao('Mobilidade'), limite='2000.00')
    _lancamento(cartao, combustivel, 100, mobilidade, descricao='Posto')
    _lancamento(cartao, combustivel, 50, None, descricao='Sem categoria')

    with app_context.test_client() as client:
        response = client.get(
            f'/api/cartoes/{cartao.id}/fatura-lancamentos?mes_referencia=2026-05&categoria_cartao_id=sem_categoria'
        )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert len(data['lancamentos']) == 1
    assert data['lancamentos'][0]['descricao'] == 'Sem categoria'
    assert data['lancamentos'][0]['categoria_cartao_id'] is None
    assert data['lancamentos'][0]['status_classificacao'] == 'sem_categoria_cartao'


def test_endpoint_resumo_fatura_retorna_estrutura_esperada(app_context):
    cartao = _cartao()
    combustivel = _categoria('Combustivel')
    mobilidade = _vincular(cartao, combustivel, _categoria_cartao('Mobilidade'), limite='2000.00')
    _lancamento(cartao, combustivel, 500, mobilidade)

    with app_context.test_client() as client:
        response = client.get(f'/api/cartoes/{cartao.id}/fatura-categorias?mes_referencia=2026-05')

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['data']['total_fatura'] == 500.0
    assert data['data']['categorias'][0]['categoria_cartao_nome'] == 'Mobilidade'
    assert data['data']['categorias'][0]['gasto_atual'] == 500.0
