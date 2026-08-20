import json
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import db, Categoria, DespesaPrevista, ItemDespesa, Veiculo, VeiculoRegraManutencaoKm
from backend.routes.categorias import categorias_bp
from backend.routes.veiculos import veiculos_bp
from backend.services.categoria_default import (
    CATEGORIAS_SISTEMICAS_MOBILIDADE,
    MOB_APP,
    MOB_ASSINATURA,
    MOB_COMBUSTIVEL,
    MOB_PNEUS,
    MOB_SEGURO_VEICULAR,
    MOB_TRIBUTOS_VEICULARES,
    MOB_USO_VEICULO,
    garantir_categorias_sistemicas_mobilidade,
    obter_categoria_sistemica_id,
)
from backend.services.mobilidade_service import (
    criar_assinatura,
    criar_recorrencia_assinatura,
    criar_recorrencia_combustivel,
    criar_recorrencia_transporte_app,
)
from backend.services.transporte_app_service import TransporteAppConfig, gerar_projecoes_transporte_app
from backend.services.veiculo_financiamento_service import _categoria_padrao_financiamento_id
from backend.services.veiculo_service import aplicar_defaults_categorias_veiculo, gerar_projecoes_mvp
from tests.conftest import autenticar_cliente_teste


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(categorias_bp, url_prefix='/api/categorias')
    app.register_blueprint(veiculos_bp, url_prefix='/api/veiculos')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return autenticar_cliente_teste(app_context.test_client(), app_context)


def _codigo(categoria_id):
    return Categoria.query.get(categoria_id).codigo_sistema


def _tipo_evento(despesa):
    return (json.loads(despesa.metadata_json or '{}') or {}).get('tipo_evento')


def test_seed_categorias_sistemicas_mobilidade_sem_categoria_generica(app_context):
    categorias = garantir_categorias_sistemicas_mobilidade()
    db.session.commit()

    assert len(categorias) == len(CATEGORIAS_SISTEMICAS_MOBILIDADE)
    assert Categoria.query.filter_by(nome='Mobilidade').first() is None

    for codigo in CATEGORIAS_SISTEMICAS_MOBILIDADE:
        categoria = Categoria.query.filter_by(codigo_sistema=codigo).first()
        assert categoria is not None
        assert categoria.sistemica is True
        assert categoria.modulo_origem == 'mobilidade'
        assert categoria.bloquear_edicao is True
        assert categoria.bloquear_exclusao is True
        assert categoria.ativo is True


def test_categoria_sistemica_bloqueia_edicao_inativacao_e_exclusao(client, app_context):
    categoria_id = obter_categoria_sistemica_id(MOB_COMBUSTIVEL)
    db.session.commit()

    editar = client.put(f'/api/categorias/{categoria_id}', json={'nome': 'Outro nome'})
    inativar = client.put(f'/api/categorias/{categoria_id}', json={'ativo': False})
    excluir = client.delete(f'/api/categorias/{categoria_id}')

    assert editar.status_code == 400
    assert 'sistêmica' in editar.get_json()['error']
    assert inativar.status_code == 400
    assert excluir.status_code == 400
    assert 'sistêmica' in excluir.get_json()['error']
    assert Categoria.query.get(categoria_id).ativo is True


def test_projecoes_veiculo_usam_categorias_sistemicas_granulares(app_context):
    veiculo = Veiculo(
        nome='Honda City',
        tipo='carro',
        combustivel='gasolina',
        autonomia_km_l=Decimal('12.0'),
        status='ATIVO',
        data_inicio=date(2026, 6, 1),
        combustivel_valor_mensal=Decimal('600.00'),
        ipva_mes=6,
        ipva_valor=Decimal('1600.00'),
        seguro_mes=6,
        seguro_valor=Decimal('2200.00'),
        licenciamento_mes=6,
        licenciamento_valor=Decimal('180.00'),
    )
    db.session.add(veiculo)
    db.session.flush()

    aplicar_defaults_categorias_veiculo(veiculo)
    gerar_projecoes_mvp(veiculo, meses_futuros=2)
    db.session.flush()

    assert _codigo(veiculo.categoria_combustivel_id) == MOB_COMBUSTIVEL
    assert _codigo(veiculo.ipva_categoria_id) == MOB_TRIBUTOS_VEICULARES
    assert _codigo(veiculo.licenciamento_categoria_id) == MOB_TRIBUTOS_VEICULARES
    assert _codigo(veiculo.seguro_categoria_id) == MOB_SEGURO_VEICULAR

    por_tipo = {_tipo_evento(d): d for d in DespesaPrevista.query.all()}
    assert _codigo(por_tipo['COMBUSTIVEL'].categoria_id) == MOB_COMBUSTIVEL
    assert _codigo(por_tipo['IPVA'].categoria_id) == MOB_TRIBUTOS_VEICULARES
    assert _codigo(por_tipo['LICENCIAMENTO'].categoria_id) == MOB_TRIBUTOS_VEICULARES
    assert _codigo(por_tipo['SEGURO'].categoria_id) == MOB_SEGURO_VEICULAR


def test_manutencao_por_km_mapeia_pneus_para_categoria_sistemica(client, app_context):
    veiculo = Veiculo(
        nome='Carro Pneus',
        tipo='carro',
        combustivel='gasolina',
        autonomia_km_l=Decimal('10.0'),
        status='ATIVO',
        data_inicio=date(2026, 6, 1),
        combustivel_valor_mensal=Decimal('500.00'),
        preco_medio_combustivel=Decimal('5.00'),
    )
    db.session.add(veiculo)
    db.session.commit()

    response = client.post(
        f'/api/veiculos/{veiculo.id}/regras-km',
        json={
            'tipo_evento': 'TROCA_PNEUS',
            'intervalo_km': 40000,
            'custo_estimado': '2400.00',
        },
    )
    assert response.status_code == 201
    regra_id = response.get_json()['data']['id']
    regra = VeiculoRegraManutencaoKm.query.get(regra_id)
    assert _codigo(regra.categoria_id) == MOB_PNEUS

    gerar = client.post(f'/api/veiculos/{veiculo.id}/manutencoes-km/gerar', json={'regra_id': regra_id})
    assert gerar.status_code == 201
    despesa_id = gerar.get_json()['data']['id']
    assert _codigo(DespesaPrevista.query.get(despesa_id).categoria_id) == MOB_PNEUS


def test_recorrencias_mobilidade_nao_dependem_de_categoria_mobilidade(app_context):
    veiculo = Veiculo(
        nome='Corolla',
        tipo='carro',
        combustivel='gasolina',
        autonomia_km_l=Decimal('12.0'),
        status='ATIVO',
        data_inicio=date(2026, 6, 1),
        combustivel_valor_mensal=Decimal('700.00'),
    )
    db.session.add(veiculo)
    db.session.flush()

    rec_comb, _ = criar_recorrencia_combustivel(veiculo, 'pix', None, None, None)
    rec_app, _ = criar_recorrencia_transporte_app(1, 'Casa-Trabalho', Decimal('450.00'), 'pix', None, None, None)
    assinatura = criar_assinatura({'nome': 'Assinatura SUV', 'valor_mensal': '2100.00'})
    rec_ass, _ = criar_recorrencia_assinatura(assinatura, 'pix', None, None)
    db.session.flush()

    assert Categoria.query.filter_by(nome='Mobilidade').first() is None
    assert _codigo(rec_comb.categoria_id) == MOB_COMBUSTIVEL
    assert _codigo(rec_app.categoria_id) == MOB_APP
    assert _codigo(assinatura.categoria_id) == MOB_ASSINATURA
    assert _codigo(rec_ass.categoria_id) == MOB_ASSINATURA
    assert ItemDespesa.query.filter(ItemDespesa.categoria_id.is_(None)).count() == 0


def test_projecoes_transporte_app_usam_categoria_sistemica_app(app_context):
    config = TransporteAppConfig(
        nome='Casa-Trabalho',
        km_mensal_estimado=Decimal('120.0'),
        preco_medio_por_km=Decimal('3.50'),
        perfis=[],
        corridas_mes=None,
        km_medio_por_corrida=None,
    )

    despesas = gerar_projecoes_transporte_app(1, config, meses_futuros=2)
    db.session.flush()

    assert despesas
    assert Categoria.query.filter_by(nome='Mobilidade').first() is None
    assert { _codigo(d.categoria_id) for d in despesas } == {MOB_APP}


def test_mapeamento_financiamento_veicular_nao_cai_em_combustivel(app_context):
    assert _codigo(_categoria_padrao_financiamento_id()) == MOB_USO_VEICULO
