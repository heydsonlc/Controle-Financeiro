from datetime import date

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
from backend.services.cartao_service import CartaoService
from backend.services.categoria_cartao_service import CategoriaCartaoService
from backend.services.despesa_prevista_service import confirmar
from backend.services.importacao_cartao_service import ImportacaoCartaoService
from backend.routes.importacao_cartao import bp as importacao_cartao_bp
from backend.routes.recorrencias import recorrencias_bp
from backend.routes.despesas import gerar_execucao_despesa_recorrente


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(importacao_cartao_bp)
    app.register_blueprint(recorrencias_bp, url_prefix='/api/recorrencias')

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
    db.session.add(ConfigAgregador(
        item_despesa_id=cartao.id,
        dia_fechamento=25,
        dia_vencimento=5,
    ))
    db.session.commit()
    return categoria, categoria_extra, cartao


def _categoria_cartao(nome='Mobilidade'):
    categoria = CategoriaCartaoService.criar_categoria(nome=nome, cor='#2563eb')
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


def _linha_importacao(categoria_id, categoria_cartao_id=None):
    linha = {
        'data_compra': '2026-05-01',
        'descricao': 'Posto Teste',
        'valor': '120.00',
        'parcela': '1/1',
        'categoria_id': categoria_id,
    }
    if categoria_cartao_id:
        linha['categoria_cartao_id'] = categoria_cartao_id
    return linha


def test_importacao_resolve_categoria_cartao_por_categoria_id(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)

    resultado = ImportacaoCartaoService.processar_linhas_mapeadas(
        [_linha_importacao(categoria.id)],
        cartao.id,
        date(2026, 5, 1),
    )

    assert resultado['linhas_invalidas'] == []
    assert resultado['lancamentos'][0]['categoria_cartao_id'] == categoria_cartao.id


def test_resolucao_operacional_service_retorna_categoria_cartao_com_limite(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)

    resultado = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
        cartao_id=cartao.id,
        categoria_id=categoria.id,
    )

    assert resultado['categoria_cartao_id'] == categoria_cartao.id
    assert resultado['categoria_cartao_nome'] == categoria_cartao.nome
    assert resultado['origem'] == 'mapa_categoria_despesa'
    assert resultado['vinculada_ao_cartao'] is True


def test_importacao_preserva_categoria_cartao_manual(app_context):
    categoria, _extra, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, categoria, _categoria_cartao('Mobilidade'))
    casa = _categoria_cartao('Casa')
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(cartao.id, casa.id, limite_mensal=500)
    db.session.commit()

    resultado = ImportacaoCartaoService.processar_linhas_mapeadas(
        [_linha_importacao(categoria.id, categoria_cartao_id=casa.id)],
        cartao.id,
        date(2026, 5, 1),
    )

    assert resultado['linhas_invalidas'] == []
    assert mobilidade.id != casa.id
    assert resultado['lancamentos'][0]['categoria_cartao_id'] == casa.id


def test_importacao_sem_mapa_nao_quebra(app_context):
    categoria, _extra, cartao = _base_cartao()

    resultado = ImportacaoCartaoService.processar_linhas_mapeadas(
        [_linha_importacao(categoria.id)],
        cartao.id,
        date(2026, 5, 1),
    )

    assert resultado['linhas_invalidas'] == []
    assert resultado['lancamentos'][0]['categoria_cartao_id'] is None


def test_importacao_endpoint_processa_sem_item_agregado_e_persiste_categoria_cartao(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)

    with app_context.test_client() as client:
        response = client.post('/api/importacao-cartao/processar', json={
            'cartao_id': cartao.id,
            'competencia': '2026-05-01',
            'linhas': [_linha_importacao(categoria.id)],
        })

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['inseridos'] == 1

    lancamento = LancamentoAgregado.query.one()
    assert lancamento.item_agregado_id is None
    assert lancamento.categoria_cartao_id == categoria_cartao.id


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
    })

    assert lancamento.categoria_cartao_id == categoria_cartao.id
    assert lancamento.item_agregado_id is None


def test_lancamento_manual_sem_categoria_cartao_configurada_nao_quebra(app_context):
    categoria, _extra, cartao = _base_cartao()

    lancamento, _fatura = CartaoService.adicionar_lancamento({
        'cartao_id': cartao.id,
        'categoria_id': categoria.id,
        'descricao': 'Posto sem mapa',
        'valor': 120,
        'data_compra': date(2026, 5, 1),
        'mes_fatura': date(2026, 5, 1),
    })

    assert lancamento.categoria_cartao_id is None
    assert lancamento.item_agregado_id is None


def test_lancamento_manual_categoria_cartao_nao_vinculada_nao_quebra(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _categoria_cartao('Mobilidade')
    CategoriaCartaoService.vincular_categoria_despesa(categoria_cartao.id, categoria.id)
    db.session.commit()

    lancamento, _fatura = CartaoService.adicionar_lancamento({
        'cartao_id': cartao.id,
        'categoria_id': categoria.id,
        'descricao': 'Posto sem limite',
        'valor': 120,
        'data_compra': date(2026, 5, 1),
        'mes_fatura': date(2026, 5, 1),
    })

    assert lancamento.categoria_cartao_id is None
    assert lancamento.item_agregado_id is None


def test_despesa_prevista_confirmada_com_cartao_grava_categoria_cartao_id(app_context):
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


def test_recorrencia_manual_cartao_repassa_categoria_cartao_id(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)
    recorrencia = ItemDespesa(
        nome='Assinatura Auto',
        valor=90,
        data_vencimento=date(2026, 5, 1),
        categoria_id=categoria.id,
        recorrente=True,
        tipo_recorrencia='mensal',
        mes_competencia='2026-05',
        tipo='Simples',
        meio_pagamento='cartao',
        cartao_id=cartao.id,
        categoria_cartao_id=categoria_cartao.id,
    )
    db.session.add(recorrencia)
    db.session.commit()

    lancamentos = gerar_execucao_despesa_recorrente(
        recorrencia.id,
        meses_futuros=1,
        mes_referencia=date(2026, 5, 1),
    )
    db.session.commit()

    assert len(lancamentos) == 1
    assert lancamentos[0].categoria_cartao_id == categoria_cartao.id


def test_recorrencia_criada_via_api_resolve_categoria_cartao_sem_manual(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)

    with app_context.test_client() as client:
        response = client.post('/api/recorrencias', json={
            'nome': 'Combustivel recorrente',
            'valor': '90.00',
            'categoria_id': categoria.id,
            'data_vencimento': '2026-05-01',
            'tipo_recorrencia': 'mensal',
            'meio_pagamento': 'cartao',
            'cartao_id': cartao.id,
        })

    assert response.status_code == 201
    data = response.get_json()
    assert data['success'] is True
    assert data['data']['categoria_cartao_id'] == categoria_cartao.id

    recorrencia = ItemDespesa.query.filter_by(nome='Combustivel recorrente').one()
    lancamento = LancamentoAgregado.query.filter_by(item_despesa_id=recorrencia.id).one()
    assert recorrencia.item_agregado_id is None
    assert recorrencia.categoria_cartao_id == categoria_cartao.id
    assert lancamento.item_agregado_id is None
    assert lancamento.categoria_cartao_id == categoria_cartao.id


def test_ausencia_categoria_cartao_nao_impede_confirmacao(app_context):
    categoria, _extra, cartao = _base_cartao()
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
    assert lancamento.categoria_cartao_id is None


def test_categoria_cartao_nao_vinculada_gera_aviso_service(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _categoria_cartao('Mobilidade')
    CategoriaCartaoService.vincular_categoria_despesa(categoria_cartao.id, categoria.id)
    db.session.commit()

    resultado = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
        cartao_id=cartao.id,
        categoria_id=categoria.id,
    )

    assert resultado['categoria_cartao_id'] is None
    assert resultado['origem'] == 'categoria_cartao_nao_vinculada'
    assert resultado['vinculada_ao_cartao'] is False


def test_item_agregado_nao_e_obrigatorio_nos_fluxos_novos(app_context):
    categoria, _extra, cartao = _base_cartao()
    categoria_cartao = _mapear_e_vincular(cartao, categoria)

    lancamento, _fatura = CartaoService.adicionar_lancamento({
        'cartao_id': cartao.id,
        'categoria_id': categoria.id,
        'categoria_cartao_id': categoria_cartao.id,
        'descricao': 'Sem legado',
        'valor': 80,
        'data_compra': date(2026, 5, 1),
        'mes_fatura': date(2026, 5, 1),
    })

    assert lancamento.item_agregado_id is None
    assert lancamento.categoria_cartao_id == categoria_cartao.id


def test_escolha_manual_prevalece_sobre_resolucao_automatica(app_context):
    categoria, _extra, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, categoria, _categoria_cartao('Mobilidade'))
    alimentacao = _categoria_cartao('Alimentacao')
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(cartao.id, alimentacao.id, limite_mensal=700)
    db.session.commit()

    lancamento, _fatura = CartaoService.adicionar_lancamento({
        'cartao_id': cartao.id,
        'categoria_id': categoria.id,
        'categoria_cartao_id': alimentacao.id,
        'descricao': 'Manual vence',
        'valor': 50,
        'data_compra': date(2026, 5, 1),
        'mes_fatura': date(2026, 5, 1),
    })

    assert mobilidade.id != alimentacao.id
    assert lancamento.categoria_cartao_id == alimentacao.id
    assert CategoriaCartao.query.count() == 2
