from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from flask import Flask

from backend.models import db, Financiamento, FinanciamentoParcela, IndiceTRMensal
from backend.routes.indexadores import indexadores_bp


@pytest.fixture()
def app_context():
    base_dir = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(base_dir / 'frontend' / 'templates'),
        static_folder=str(base_dir / 'frontend' / 'static'),
    )
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(indexadores_bp)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


def _criar_tr(competencia='2026-06', valor=Decimal('0.0016')):
    ano, mes = [int(parte) for parte in competencia.split('-')]
    indice = IndiceTRMensal(
        ano=ano,
        mes=mes,
        competencia=competencia,
        valor_decimal=valor,
        fonte='BACEN',
    )
    db.session.add(indice)
    db.session.commit()
    return indice


def _criar_financiamento_sac_tr_com_parcela(competencia='2026-06'):
    ano, mes = [int(parte) for parte in competencia.split('-')]
    financiamento = Financiamento(
        nome='Financiamento SAC TR',
        produto='SFH',
        sistema_amortizacao='SAC',
        valor_financiado=Decimal('100000.00'),
        prazo_total_meses=120,
        prazo_remanescente_meses=120,
        taxa_juros_nominal_anual=Decimal('9.3800'),
        taxa_juros_mensal=Decimal('0.007816'),
        indexador_saldo='TR',
        data_contrato=date(2026, 1, 1),
        data_primeira_parcela=date(ano, mes, 5),
        taxa_administracao_fixa=Decimal('25.00'),
        ativo=True,
    )
    db.session.add(financiamento)
    db.session.flush()

    parcela = FinanciamentoParcela(
        financiamento_id=financiamento.id,
        numero_parcela=1,
        data_vencimento=date(ano, mes, 5),
        valor_amortizacao=Decimal('1000.00'),
        valor_juros=Decimal('700.00'),
        valor_seguro=Decimal('150.00'),
        valor_taxa_adm=Decimal('25.00'),
        valor_previsto_total=Decimal('1875.00'),
        saldo_devedor_apos_pagamento=Decimal('99000.00'),
        status='pendente',
    )
    db.session.add(parcela)
    db.session.commit()
    return financiamento


def test_criar_e_listar_tr_oficial_converte_percentual_para_decimal(client):
    response = client.post('/api/indexadores/tr', json={
        'competencia': '2026-06',
        'valor_percentual': '0,16',
        'fonte': 'BACEN',
    })
    body = response.get_json()

    assert response.status_code == 201
    assert body['success'] is True
    assert body['data']['competencia'] == '2026-06'
    assert body['data']['valor_decimal'] == 0.0016
    assert body['data']['valor_percentual'] == 0.16

    response = client.get('/api/indexadores/tr?ano=2026')
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert len(body['items']) == 1
    assert body['items'][0]['competencia'] == '2026-06'


@pytest.mark.parametrize('competencia', ['2026-13', '2026/06', '06/2026', 'abc'])
def test_criar_tr_bloqueia_competencia_invalida(client, competencia):
    response = client.post('/api/indexadores/tr', json={
        'competencia': competencia,
        'valor_percentual': '0,16',
    })

    assert response.status_code == 400
    assert response.get_json()['success'] is False


def test_criar_tr_bloqueia_valor_negativo_e_duplicidade(client):
    response = client.post('/api/indexadores/tr', json={
        'competencia': '2026-06',
        'valor_percentual': '-0,16',
    })
    assert response.status_code == 400
    assert 'não pode ser negativo' in response.get_json()['error']

    _criar_tr('2026-06')
    response = client.post('/api/indexadores/tr', json={
        'competencia': '2026-06',
        'valor_percentual': '0,17',
    })
    assert response.status_code == 400
    assert 'já cadastrada' in response.get_json()['error']


def test_importar_tr_por_texto_csv_com_virgula_e_ponto_decimal(client):
    response = client.post('/api/indexadores/tr/importar', json={
        'texto': '2026-06;0,15\n2026-07,0.16\n2026-08;0.17',
        'fonte': 'BACEN',
        'sobrescrever': False,
    })
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert body['criados'] == 3
    assert body['atualizados'] == 0
    assert body['ignorados'] == 0
    assert body['erros'] == []
    assert IndiceTRMensal.query.filter_by(competencia='2026-06').one().valor_decimal == Decimal('0.00150000')
    assert IndiceTRMensal.query.filter_by(competencia='2026-07').one().valor_decimal == Decimal('0.00160000')
    assert IndiceTRMensal.query.filter_by(competencia='2026-08').one().valor_decimal == Decimal('0.00170000')


def test_importar_tr_nao_sobrescreve_sem_flag_e_sobrescreve_com_flag(client):
    _criar_tr('2026-06', Decimal('0.0015'))

    response = client.post('/api/indexadores/tr/importar', json={
        'texto': '2026-06;0,20\n2026-07;0,16',
        'sobrescrever': False,
    })
    body = response.get_json()

    assert response.status_code == 200
    assert body['criados'] == 1
    assert body['atualizados'] == 0
    assert body['ignorados'] == 1
    assert IndiceTRMensal.query.filter_by(competencia='2026-06').one().valor_decimal == Decimal('0.00150000')

    response = client.post('/api/indexadores/tr/importar', json={
        'texto': '2026-06;0,20',
        'sobrescrever': True,
    })
    body = response.get_json()

    assert response.status_code == 200
    assert body['criados'] == 0
    assert body['atualizados'] == 1
    assert body['ignorados'] == 0
    assert IndiceTRMensal.query.filter_by(competencia='2026-06').one().valor_decimal == Decimal('0.00200000')


def test_editar_tr_bloqueia_quando_competencia_ja_esta_em_cronograma_sac_tr(client):
    _criar_tr('2026-06')
    _criar_financiamento_sac_tr_com_parcela('2026-06')

    response = client.put('/api/indexadores/tr/2026-06', json={
        'valor_percentual': '0,17',
    })
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert 'já é usada em parcelas de financiamento SAC/TR' in body['error']
    assert IndiceTRMensal.query.filter_by(competencia='2026-06').one().valor_decimal == Decimal('0.00160000')


def test_editar_tr_permite_competencia_nao_usada(client):
    _criar_tr('2026-06')

    response = client.put('/api/indexadores/tr/2026-06', json={
        'valor_percentual': '0,17',
        'fonte': 'BACEN',
    })
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert body['data']['valor_decimal'] == 0.0017


def test_listar_competencias_faltantes(client):
    _criar_tr('2026-06')
    _criar_tr('2026-08')

    response = client.get('/api/indexadores/tr/faltantes?inicio=2026-06&fim=2026-09')
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert body['faltantes'] == ['2026-07', '2026-09']


def test_frontend_indexadores_tem_secao_tr_oficial_e_payloads():
    base_dir = Path(__file__).resolve().parents[1]
    html = (base_dir / 'frontend' / 'templates' / 'indexadores.html').read_text(encoding='utf-8')
    js = (base_dir / 'frontend' / 'static' / 'js' / 'indexadores.js').read_text(encoding='utf-8')

    assert 'TR para financiamentos SAC/TR' in html
    assert 'Esta TR é usada pelo motor de financiamentos SAC + TR' in html
    assert '/api/indexadores/tr' in js
    assert '/api/indexadores/tr/importar' in js
    assert 'competencia' in js
    assert 'valor_percentual' in js
    assert 'texto' in js
    assert 'sobrescrever' in js
