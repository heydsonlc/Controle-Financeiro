from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pytest
from flask import Flask, render_template
from sqlalchemy import text

from backend.models import db, Conta, Financiamento, FinanciamentoParcela, FinanciamentoSeguroFaixaMip
from backend.routes.financiamentos import financiamentos_bp


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
    app.register_blueprint(financiamentos_bp, url_prefix='/api/financiamentos')

    @app.route('/financiamentos')
    def financiamentos_page():
        return render_template(
            'financiamentos.html',
            active_page='financiamentos',
            page_title='Financiamentos',
        )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


@pytest.fixture()
def sqlite_foreign_keys(app_context):
    db.session.execute(text('PRAGMA foreign_keys=ON'))
    db.session.commit()
    yield
    db.session.rollback()
    db.session.execute(text('PRAGMA foreign_keys=OFF'))
    db.session.commit()


def _payload_financiamento(nome='Financiamento UX'):
    return {
        'nome': nome,
        'produto': 'SFH',
        'sistema_amortizacao': 'SAC',
        'valor_financiado': 350000.0,
        'prazo_total_meses': 240,
        'taxa_juros_nominal_anual': 9.5,
        'indexador_saldo': 'TR',
        'data_contrato': '2026-05-01',
        'data_primeira_parcela': '2026-06-01',
        'seguro_tipo': 'fixo',
        'valor_seguro_mensal': 200.0,
        'taxa_administracao_fixa': 0.0,
        'vigencias_seguro': [
            {
                'competencia_inicio': '2026-06-01',
                'valor_mensal': 200.0,
                'observacoes': 'Vigencia inicial do teste UX',
            }
        ],
    }


def _faixas_mip_padrao():
    return [
        {'idade_inicio': 0, 'idade_fim': 45, 'fator_mip': 0.03187},
        {'idade_inicio': 46, 'idade_fim': 50, 'fator_mip': 0.04899},
        {'idade_inicio': 51, 'idade_fim': 55, 'fator_mip': 0.08593},
        {'idade_inicio': 56, 'idade_fim': 60, 'fator_mip': 0.16077},
        {'idade_inicio': 61, 'idade_fim': 65, 'fator_mip': 0.31887},
        {'idade_inicio': 66, 'idade_fim': 70, 'fator_mip': 0.34932},
        {'idade_inicio': 71, 'idade_fim': 75, 'fator_mip': 0.49795},
        {'idade_inicio': 76, 'idade_fim': 80, 'fator_mip': 0.57099},
    ]


def _payload_financiamento_estimado(nome='Financiamento Seguro Estimado'):
    payload = _payload_financiamento(nome)
    payload.update({
        'valor_financiado': 120000.0,
        'prazo_total_meses': 24,
        'taxa_juros_nominal_anual': 12.0,
        'data_contrato': '2029-12-01',
        'data_primeira_parcela': '2030-01-21',
        'valor_seguro_mensal': 0.0,
        'seguro_modo': 'estimado_dfi_mip',
        'seguro_fator_dfi': 0.0489,
        'seguro_data_nascimento_titular': '1979-02-01',
        'seguro_mes_reajuste_idade': 2,
        'faixas_mip': _faixas_mip_padrao(),
    })
    payload.pop('vigencias_seguro', None)
    return payload


def _criar_financiamento(client, nome='Financiamento UX'):
    response = client.post('/api/financiamentos', json=_payload_financiamento(nome))
    assert response.status_code == 201
    body = response.get_json()
    assert body['success'] is True
    return body['data']


def _seguro_esperado(amortizacao, juros, fator_mip):
    valor = (Decimal(str(amortizacao)) * Decimal('0.0489')) + (Decimal(str(juros)) * Decimal(str(fator_mip)))
    return float(valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def test_rota_principal_renderiza_layout_ux(client):
    response = client.get('/financiamentos')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Financiamentos' in html
    assert 'Novo financiamento' in html
    assert 'Contratos de financiamento' in html
    assert 'Resumo e simulação' in html
    assert 'Simular amortização' in html


def test_api_listagem_banco_vazio_nao_quebra(client):
    response = client.get('/api/financiamentos?ativo=true')

    assert response.status_code == 200
    body = response.get_json()
    assert body['success'] is True
    assert body['data'] == []


def test_cadastro_aceita_payload_minimo_e_gera_cronograma(client):
    criado = _criar_financiamento(client)

    assert criado['nome'] == 'Financiamento UX'
    assert criado['produto'] == 'SFH'
    assert criado['saldo_devedor_atual'] == 350000.0

    financiamento = Financiamento.query.get(criado['id'])
    parcelas = FinanciamentoParcela.query.filter_by(financiamento_id=financiamento.id).all()
    assert financiamento.sistema_amortizacao == 'SAC'
    assert len(parcelas) == 240
    assert financiamento.seguro_modo == 'fixo'
    assert float(parcelas[0].valor_seguro) == 200.0


def test_cards_resumo_usam_total_financiado_e_saldo_devedor(client):
    criado = _criar_financiamento(client)

    response = client.get('/api/financiamentos?ativo=true')
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert len(body['data']) == 1
    assert body['data'][0]['id'] == criado['id']
    assert body['data'][0]['valor_financiado'] == 350000.0
    assert body['data'][0]['saldo_devedor_atual'] == 350000.0
    assert body['data'][0]['parcelas_pagas'] == 0
    assert body['data'][0]['total_parcelas'] == 240


def test_detalhe_retorna_cronograma_para_tela_operacional(client):
    criado = _criar_financiamento(client)

    response = client.get(f'/api/financiamentos/{criado["id"]}')
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert len(body['data']['parcelas']) == 240
    primeira = body['data']['parcelas'][0]
    assert primeira['numero_parcela'] == 1
    assert primeira['status'] == 'pendente'
    assert primeira['valor_previsto_total'] > 0


def test_seguro_estimado_dfi_mip_calcula_e_muda_por_faixa_etaria(client):
    response = client.post('/api/financiamentos', json=_payload_financiamento_estimado())
    body = response.get_json()

    assert response.status_code == 201
    assert body['success'] is True
    assert body['data']['seguro_modo'] == 'estimado_dfi_mip'

    detalhe = client.get(f'/api/financiamentos/{body["data"]["id"]}').get_json()['data']
    parcelas = detalhe['parcelas']
    janeiro = parcelas[0]
    fevereiro = parcelas[1]
    marco = parcelas[2]

    assert janeiro['data_vencimento'] == '2030-01-21'
    assert fevereiro['data_vencimento'] == '2030-02-21'
    assert janeiro['valor_seguro'] == _seguro_esperado(
        janeiro['valor_amortizacao'],
        janeiro['valor_juros'],
        0.04899
    )
    assert fevereiro['valor_seguro'] == _seguro_esperado(
        fevereiro['valor_amortizacao'],
        fevereiro['valor_juros'],
        0.08593
    )
    assert fevereiro['valor_juros'] < janeiro['valor_juros']
    assert fevereiro['valor_seguro'] > janeiro['valor_seguro']
    assert marco['valor_seguro'] < fevereiro['valor_seguro']

    idades_inicio = {
        faixa.idade_inicio
        for faixa in FinanciamentoSeguroFaixaMip.query.filter_by(
            financiamento_id=body['data']['id']
        ).all()
    }
    assert idades_inicio == {0, 46, 51, 56, 61, 66, 71, 76}


def test_edicao_regenera_cronograma_com_seguro_estimado(client):
    criado = client.post('/api/financiamentos', json=_payload_financiamento_estimado()).get_json()['data']
    parcela_original = FinanciamentoParcela.query.filter_by(
        financiamento_id=criado['id']
    ).order_by(FinanciamentoParcela.numero_parcela).first()
    seguro_original = float(parcela_original.valor_seguro)

    payload = _payload_financiamento_estimado('Financiamento Seguro Recalculado')
    payload.update({
        'valor_financiado': 180000.0,
        'prazo_total_meses': 36,
        'regenerar_cronograma': True,
    })

    response = client.put(f'/api/financiamentos/{criado["id"]}', json=payload)
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True

    detalhe = client.get(f'/api/financiamentos/{criado["id"]}').get_json()['data']
    primeira = detalhe['parcelas'][0]
    assert detalhe['valor_financiado'] == 180000.0
    assert detalhe['total_parcelas'] == 36
    assert primeira['valor_seguro'] != seguro_original
    assert primeira['valor_seguro'] == _seguro_esperado(
        primeira['valor_amortizacao'],
        primeira['valor_juros'],
        0.04899
    )


def test_edicao_estrutural_sem_parcela_paga_persiste_e_regenera_cronograma(client, sqlite_foreign_keys):
    criado = _criar_financiamento(client)
    parcela_antiga = FinanciamentoParcela.query.filter_by(financiamento_id=criado['id']).order_by(
        FinanciamentoParcela.numero_parcela
    ).first()
    assert parcela_antiga.conta_id is not None
    assert Conta.query.count() == 240

    payload = {
        'nome': 'Financiamento Corrigido',
        'produto': 'Habitacional',
        'sistema_amortizacao': 'PRICE',
        'valor_financiado': 250000.0,
        'prazo_total_meses': 36,
        'taxa_juros_nominal_anual': 8.25,
        'indexador_saldo': 'IPCA',
        'data_contrato': '2024-05-05',
        'data_primeira_parcela': '2024-06-05',
        'seguro_tipo': 'fixo',
        'valor_seguro_mensal': 150.0,
        'taxa_administracao_fixa': 10.0,
        'ativo': True,
        'regenerar_cronograma': True,
    }

    response = client.put(f'/api/financiamentos/{criado["id"]}', json=payload)
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True

    detalhe = client.get(f'/api/financiamentos/{criado["id"]}').get_json()['data']
    assert detalhe['nome'] == 'Financiamento Corrigido'
    assert detalhe['produto'] == 'Habitacional'
    assert detalhe['sistema_amortizacao'] == 'PRICE'
    assert detalhe['valor_financiado'] == 250000.0
    assert detalhe['prazo_total_meses'] == 36
    assert detalhe['taxa_juros_nominal_anual'] == 8.25
    assert detalhe['indexador_saldo'] == 'IPCA'
    assert detalhe['data_contrato'] == '2024-05-05'
    assert detalhe['data_primeira_parcela'] == '2024-06-05'
    assert detalhe['valor_seguro_mensal'] == 150.0
    assert detalhe['taxa_administracao_fixa'] == 10.0
    assert detalhe['total_parcelas'] == 36
    assert detalhe['parcelas'][0]['data_vencimento'] == '2024-06-05'
    assert detalhe['parcelas'][0]['status'] == 'pendente'

    parcelas_regeneradas = FinanciamentoParcela.query.filter_by(financiamento_id=criado['id']).all()
    ids_regenerados = [p.id for p in parcelas_regeneradas]
    contas_regeneradas = Conta.query.all()
    assert len(parcelas_regeneradas) == 36
    assert all(p.conta_id is not None for p in parcelas_regeneradas)
    assert len(contas_regeneradas) == 36
    assert {c.financiamento_parcela_id for c in contas_regeneradas} == set(ids_regenerados)


def test_registrar_pagamento_mantem_status_da_parcela(client):
    criado = _criar_financiamento(client)
    parcela = FinanciamentoParcela.query.filter_by(financiamento_id=criado['id']).order_by(
        FinanciamentoParcela.numero_parcela
    ).first()

    response = client.post(
        f'/api/financiamentos/parcelas/{parcela.id}/pagar',
        json={
            'valor_pago': float(parcela.valor_previsto_total),
            'data_pagamento': '2026-06-01',
        },
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    db.session.refresh(parcela)
    assert parcela.status == 'pago'


def test_edicao_estrutural_com_parcela_paga_bloqueia_sem_alteracao_parcial(client):
    criado = _criar_financiamento(client)
    parcela = FinanciamentoParcela.query.filter_by(financiamento_id=criado['id']).order_by(
        FinanciamentoParcela.numero_parcela
    ).first()

    pagamento = client.post(
        f'/api/financiamentos/parcelas/{parcela.id}/pagar',
        json={
            'valor_pago': float(parcela.valor_previsto_total),
            'data_pagamento': '2026-06-01',
        },
    )
    assert pagamento.status_code == 200

    response = client.put(
        f'/api/financiamentos/{criado["id"]}',
        json={
            'nome': 'Tentativa bloqueada',
            'produto': 'SFH',
            'sistema_amortizacao': 'PRICE',
            'valor_financiado': 250000.0,
            'prazo_total_meses': 120,
            'taxa_juros_nominal_anual': 7.5,
            'indexador_saldo': 'IPCA',
            'data_contrato': '2024-05-05',
            'data_primeira_parcela': '2024-06-05',
            'seguro_tipo': 'fixo',
            'valor_seguro_mensal': 150.0,
            'taxa_administracao_fixa': 10.0,
            'ativo': True,
            'regenerar_cronograma': True,
        },
    )
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert 'parcelas pagas ou vinculadas a pagamentos' in body['error']

    detalhe = client.get(f'/api/financiamentos/{criado["id"]}').get_json()['data']
    assert detalhe['nome'] == 'Financiamento UX'
    assert detalhe['sistema_amortizacao'] == 'SAC'
    assert detalhe['valor_financiado'] == 350000.0
    assert detalhe['prazo_total_meses'] == 240
    assert detalhe['data_contrato'] == '2026-05-01'
    assert detalhe['data_primeira_parcela'] == '2026-06-01'
    assert detalhe['total_parcelas'] == 240
    assert detalhe['parcelas'][0]['status'] == 'pago'


def test_regenerar_parcelas_bloqueia_quando_existe_parcela_paga(client):
    criado = _criar_financiamento(client)
    parcela = FinanciamentoParcela.query.filter_by(financiamento_id=criado['id']).order_by(
        FinanciamentoParcela.numero_parcela
    ).first()

    pagamento = client.post(
        f'/api/financiamentos/parcelas/{parcela.id}/pagar',
        json={
            'valor_pago': float(parcela.valor_previsto_total),
            'data_pagamento': '2026-06-01',
        },
    )
    assert pagamento.status_code == 200

    response = client.post(f'/api/financiamentos/{criado["id"]}/regenerar-parcelas', json={})
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert 'parcelas pagas ou vinculadas a pagamentos' in body['error']

    parcelas = FinanciamentoParcela.query.filter_by(financiamento_id=criado['id']).order_by(
        FinanciamentoParcela.numero_parcela
    ).all()
    assert len(parcelas) == 240
    assert parcelas[0].status == 'pago'


def test_amortizacao_existente_retorna_estrutura_sem_alterar_formula(client):
    criado = _criar_financiamento(client)

    response = client.post(
        f'/api/financiamentos/{criado["id"]}/amortizacao-extra',
        json={
            'data': '2026-07-01',
            'valor': 1000.0,
            'tipo': 'reduzir_prazo',
            'observacoes': 'Teste UX',
        },
    )
    body = response.get_json()

    assert response.status_code == 201
    assert body['success'] is True
    assert body['data']['valor'] == 1000.0
    assert body['data']['tipo'] == 'reduzir_prazo'


def test_demonstrativo_anual_alimenta_extrato(client):
    criado = _criar_financiamento(client)

    response = client.get(f'/api/financiamentos/{criado["id"]}/demonstrativo-anual?ano=2026')
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert body['data']['ano'] == 2026
    assert body['data']['resumo_mensal']


def test_template_nao_depende_de_modal_antigo_para_cadastro(client):
    response = client.get('/financiamentos')
    html = response.get_data(as_text=True)

    assert 'fin-form-view' in html
    assert 'modal-financiamento' not in html
    assert 'modal-detalhes' not in html


def test_frontend_payload_de_financiamento_envia_campos_estruturais_e_flag_cronograma():
    base_dir = Path(__file__).resolve().parents[1]
    js = (base_dir / 'frontend' / 'static' / 'js' / 'financiamentos.js').read_text(encoding='utf-8')
    trecho = js[js.index('function coletarDadosFormulario'):js.index('async function verDetalhes')]

    for campo in [
        'data_contrato',
        'data_primeira_parcela',
        'prazo_total_meses',
        'taxa_juros_nominal_anual',
        'valor_financiado',
        'sistema_amortizacao',
        'indexador_saldo',
        'valor_seguro_mensal',
        'seguro_modo',
        'seguro_fator_dfi',
        'seguro_data_nascimento_titular',
        'seguro_mes_reajuste_idade',
        'faixas_mip',
        'taxa_administracao_fixa',
        'regenerar_cronograma',
    ]:
        assert campo in trecho

    assert 'ajustarDataPrimeiraPorDia' in trecho
