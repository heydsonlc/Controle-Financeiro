from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pytest
from flask import Flask, render_template
from sqlalchemy import text

from backend.models import (
    db,
    Conta,
    Financiamento,
    FinanciamentoAjusteSaldo,
    FinanciamentoAmortizacaoExtra,
    FinanciamentoParcela,
    FinanciamentoSeguroFaixaMip,
    FinanciamentoSeguroVigencia,
    ItemDespesa,
)
from backend.routes.financiamentos import financiamentos_bp
from backend.routes.financiamento_seguro import bp as financiamento_seguro_bp


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
    app.register_blueprint(financiamento_seguro_bp)

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
        'indexador_saldo': None,
        'data_contrato': '2026-05-01',
        'data_primeira_parcela': '2026-06-01',
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


def _criar_item_despesa(nome='Item financiamento'):
    item = ItemDespesa(
        nome=nome,
        tipo='Financiamento',
        ativo=True,
        valor=0,
        recorrente=False,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _seguro_esperado(amortizacao, juros, fator_mip):
    valor = (Decimal(str(amortizacao)) * Decimal('0.0489')) + (Decimal(str(juros)) * Decimal(str(fator_mip)))
    return float(valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _parcela_financiamento(financiamento_id, numero):
    return FinanciamentoParcela.query.filter_by(
        financiamento_id=financiamento_id,
        numero_parcela=numero,
    ).first()


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


def test_seguro_modo_tem_prioridade_sobre_seguro_tipo_legado(client):
    payload = _payload_financiamento_estimado('Seguro Modo Oficial')
    payload['seguro_tipo'] = 'fixo'
    payload['seguro_percentual'] = 0.0006

    response = client.post('/api/financiamentos', json=payload)
    body = response.get_json()

    assert response.status_code == 201
    assert body['success'] is True
    assert body['data']['seguro_modo'] == 'estimado_dfi_mip'
    assert body['data']['seguro_tipo'] == 'fixo'

    parcela = FinanciamentoParcela.query.filter_by(
        financiamento_id=body['data']['id']
    ).order_by(FinanciamentoParcela.numero_parcela).first()
    assert float(parcela.valor_seguro) == _seguro_esperado(
        parcela.valor_amortizacao,
        parcela.valor_juros,
        0.04899,
    )


def test_seguro_tipo_legado_sem_seguro_modo_cai_para_fixo_manual(client):
    payload = _payload_financiamento('Seguro Legado Percentual')
    payload['seguro_tipo'] = 'percentual_saldo'
    payload['seguro_percentual'] = 0.0006

    response = client.post('/api/financiamentos', json=payload)
    body = response.get_json()

    assert response.status_code == 201
    assert body['success'] is True
    assert body['data']['seguro_modo'] == 'fixo'
    assert body['data']['seguro_tipo'] == 'percentual_saldo'

    parcela = FinanciamentoParcela.query.filter_by(
        financiamento_id=body['data']['id']
    ).order_by(FinanciamentoParcela.numero_parcela).first()
    assert float(parcela.valor_seguro) == 200.0


def test_rota_legada_seguros_usa_vigencia_manual_sem_taxa_percentual(client):
    criado = _criar_financiamento(client, 'Rota Legada Seguros')

    response = client.post(
        f'/api/financiamentos/{criado["id"]}/seguros',
        json={
            'competencia_inicio': '2027-01-01',
            'valor_mensal': 250.0,
            'saldo_devedor_vigencia': 1.0,
            'observacoes': 'Rota legada preservada',
        },
    )
    body = response.get_json()

    assert response.status_code == 201
    assert body['success'] is True
    assert body['data']['valor_mensal'] == 250.0
    assert body['data']['taxa_percentual'] is None
    assert body['data']['saldo_devedor_vigencia'] == criado['saldo_devedor_atual']

    response = client.get(f'/api/financiamentos/{criado["id"]}/seguros')
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert len(body['data']) == 2
    assert {vigencia['valor_mensal'] for vigencia in body['data']} == {200.0, 250.0}


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


def test_ajuste_saldo_menor_registra_e_recalcula_futuras(client):
    criado = _criar_financiamento(client)
    referencia = _parcela_financiamento(criado['id'], 10)
    anterior = _parcela_financiamento(criado['id'], 9)
    juros_original = float(referencia.valor_juros)
    amortizacao_anterior = float(anterior.valor_amortizacao)
    saldo_real = float(anterior.saldo_devedor_apos_pagamento) - 10000.0

    response = client.post(
        f'/api/financiamentos/{criado["id"]}/ajustar-saldo',
        json={
            'parcela_referencia_id': referencia.id,
            'numero_parcela': referencia.numero_parcela,
            'data_referencia': referencia.data_vencimento.isoformat(),
            'saldo_devedor_real': saldo_real,
            'tipo_ajuste': 'ajuste_saldo_real',
            'observacao': 'Saldo real informado pelo banco',
            'recalcular_parcelas_futuras': True,
        },
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert body['parcelas_recalculadas'] == 231
    assert FinanciamentoAjusteSaldo.query.filter_by(financiamento_id=criado['id']).count() == 1

    db.session.refresh(anterior)
    db.session.refresh(referencia)
    assert float(anterior.valor_amortizacao) == amortizacao_anterior
    assert float(referencia.valor_juros) < juros_original
    assert float(referencia.valor_seguro) == 200.0
    assert Conta.query.filter_by(financiamento_parcela_id=referencia.id).first().valor == referencia.valor_previsto_total


def test_ajuste_saldo_maior_aumenta_juros_futuros(client):
    criado = _criar_financiamento(client)
    referencia = _parcela_financiamento(criado['id'], 20)
    anterior = _parcela_financiamento(criado['id'], 19)
    juros_original = float(referencia.valor_juros)
    saldo_real = float(anterior.saldo_devedor_apos_pagamento) + 15000.0

    response = client.post(
        f'/api/financiamentos/{criado["id"]}/ajustar-saldo',
        json={
            'parcela_referencia_id': referencia.id,
            'saldo_devedor_real': saldo_real,
            'recalcular_parcelas_futuras': True,
        },
    )

    assert response.status_code == 200
    db.session.refresh(referencia)
    assert float(referencia.valor_juros) > juros_original


def test_ajuste_com_referencia_paga_preserva_parcela_paga_e_recalcula_proxima(client):
    criado = _criar_financiamento(client)
    parcela_paga = _parcela_financiamento(criado['id'], 1)
    parcela_futura = _parcela_financiamento(criado['id'], 2)

    pagamento = client.post(
        f'/api/financiamentos/parcelas/{parcela_paga.id}/pagar',
        json={
            'valor_pago': float(parcela_paga.valor_previsto_total),
            'data_pagamento': parcela_paga.data_vencimento.isoformat(),
        },
    )
    assert pagamento.status_code == 200

    valor_pago_original = float(parcela_paga.valor_pago)
    juros_futuro_original = float(parcela_futura.valor_juros)
    saldo_real = float(parcela_paga.saldo_devedor_apos_pagamento) - 8000.0

    response = client.post(
        f'/api/financiamentos/{criado["id"]}/ajustar-saldo',
        json={
            'parcela_referencia_id': parcela_paga.id,
            'saldo_devedor_real': saldo_real,
            'recalcular_parcelas_futuras': True,
        },
    )

    assert response.status_code == 200
    db.session.refresh(parcela_paga)
    db.session.refresh(parcela_futura)
    assert parcela_paga.status == 'pago'
    assert float(parcela_paga.valor_pago) == valor_pago_original
    assert float(parcela_futura.valor_juros) < juros_futuro_original


def test_ajuste_bloqueia_conta_futura_efetivada(client):
    criado = _criar_financiamento(client)
    referencia = _parcela_financiamento(criado['id'], 5)
    parcela_futura = _parcela_financiamento(criado['id'], 7)
    conta_futura = Conta.query.filter_by(financiamento_parcela_id=parcela_futura.id).first()
    conta_futura.status_pagamento = 'Pago'
    conta_futura.data_pagamento = parcela_futura.data_vencimento
    db.session.commit()

    response = client.post(
        f'/api/financiamentos/{criado["id"]}/ajustar-saldo',
        json={
            'parcela_referencia_id': referencia.id,
            'saldo_devedor_real': float(referencia.saldo_devedor_apos_pagamento),
            'recalcular_parcelas_futuras': True,
        },
    )
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert 'contas ja efetivadas' in body['error']
    assert FinanciamentoAjusteSaldo.query.filter_by(financiamento_id=criado['id']).count() == 0


def test_ajuste_saldo_recalcula_seguro_estimado_pelo_helper(client):
    criado = client.post('/api/financiamentos', json=_payload_financiamento_estimado()).get_json()['data']
    referencia = _parcela_financiamento(criado['id'], 3)
    anterior = _parcela_financiamento(criado['id'], 2)
    juros_original = float(referencia.valor_juros)
    seguro_original = float(referencia.valor_seguro)
    saldo_real = float(anterior.saldo_devedor_apos_pagamento) - 10000.0

    response = client.post(
        f'/api/financiamentos/{criado["id"]}/ajustar-saldo',
        json={
            'parcela_referencia_id': referencia.id,
            'saldo_devedor_real': saldo_real,
            'recalcular_parcelas_futuras': True,
        },
    )

    assert response.status_code == 200
    db.session.refresh(referencia)
    assert float(referencia.valor_juros) < juros_original
    assert float(referencia.valor_seguro) < seguro_original
    assert float(referencia.valor_seguro) == _seguro_esperado(
        referencia.valor_amortizacao,
        referencia.valor_juros,
        0.08593
    )


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


def test_excluir_financiamento_sem_execucao_remove_dependencias_pendentes(client):
    criado = _criar_financiamento(client)
    item_despesa_id = criado['item_despesa_id']
    parcelas = FinanciamentoParcela.query.filter_by(financiamento_id=criado['id']).all()
    parcela_ids = [parcela.id for parcela in parcelas]
    conta_ids = [
        conta.id for conta in Conta.query.filter(
            Conta.financiamento_parcela_id.in_(parcela_ids)
        ).all()
    ]

    assert parcelas
    assert conta_ids
    assert FinanciamentoSeguroVigencia.query.filter_by(financiamento_id=criado['id']).count() == 1

    response = client.delete(f'/api/financiamentos/{criado["id"]}')
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert db.session.get(Financiamento, criado['id']) is None
    assert FinanciamentoParcela.query.filter_by(financiamento_id=criado['id']).count() == 0
    assert FinanciamentoSeguroVigencia.query.filter_by(financiamento_id=criado['id']).count() == 0
    assert Conta.query.filter(Conta.id.in_(conta_ids)).count() == 0
    assert db.session.get(ItemDespesa, item_despesa_id) is not None


def test_excluir_financiamento_estimado_remove_faixas_mip(client):
    response = client.post('/api/financiamentos', json=_payload_financiamento_estimado('Financiamento Excluir Estimado'))
    criado = response.get_json()['data']

    assert FinanciamentoSeguroFaixaMip.query.filter_by(financiamento_id=criado['id']).count() == 8

    response = client.delete(f'/api/financiamentos/{criado["id"]}')
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert db.session.get(Financiamento, criado['id']) is None
    assert FinanciamentoSeguroFaixaMip.query.filter_by(financiamento_id=criado['id']).count() == 0


def test_excluir_financiamento_preserva_item_despesa_compartilhado_com_conta_avulsa(client):
    item = _criar_item_despesa('Item compartilhado')
    payload = _payload_financiamento('Financiamento Item Compartilhado')
    payload['item_despesa_id'] = item.id
    response = client.post('/api/financiamentos', json=payload)
    assert response.status_code == 201
    criado = response.get_json()['data']

    conta_avulsa = Conta(
        item_despesa_id=item.id,
        mes_referencia=date(2026, 6, 1),
        descricao='Despesa avulsa compartilhada',
        valor=Decimal('150.00'),
        data_vencimento=date(2026, 6, 10),
        status_pagamento='Pendente',
    )
    db.session.add(conta_avulsa)
    db.session.commit()

    parcelas = FinanciamentoParcela.query.filter_by(financiamento_id=criado['id']).all()
    parcela_ids = [parcela.id for parcela in parcelas]
    contas_financiamento = Conta.query.filter(Conta.financiamento_parcela_id.in_(parcela_ids)).all()
    assert contas_financiamento

    response = client.delete(f'/api/financiamentos/{criado["id"]}')
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert db.session.get(ItemDespesa, item.id) is not None
    assert db.session.get(Conta, conta_avulsa.id) is not None
    assert Conta.query.filter(Conta.financiamento_parcela_id.in_(parcela_ids)).count() == 0


def test_editar_financiamento_item_despesa_sem_execucao_sincroniza_contas_pendentes(client):
    item_a = _criar_item_despesa('Item A')
    item_b = _criar_item_despesa('Item B')
    payload = _payload_financiamento('Financiamento Troca Item')
    payload['item_despesa_id'] = item_a.id
    response = client.post('/api/financiamentos', json=payload)
    assert response.status_code == 201
    criado = response.get_json()['data']

    parcelas = FinanciamentoParcela.query.filter_by(financiamento_id=criado['id']).all()
    parcela_ids = [parcela.id for parcela in parcelas]
    assert Conta.query.filter(
        Conta.financiamento_parcela_id.in_(parcela_ids),
        Conta.item_despesa_id == item_a.id,
    ).count() == len(parcelas)

    response = client.put(
        f'/api/financiamentos/{criado["id"]}',
        json={'item_despesa_id': item_b.id},
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert db.session.get(Financiamento, criado['id']).item_despesa_id == item_b.id
    assert Conta.query.filter(
        Conta.financiamento_parcela_id.in_(parcela_ids),
        Conta.item_despesa_id == item_b.id,
    ).count() == len(parcelas)


def test_editar_financiamento_item_despesa_bloqueia_com_parcela_paga(client):
    item_a = _criar_item_despesa('Item pago A')
    item_b = _criar_item_despesa('Item pago B')
    payload = _payload_financiamento('Financiamento Item Pago')
    payload['item_despesa_id'] = item_a.id
    response = client.post('/api/financiamentos', json=payload)
    assert response.status_code == 201
    criado = response.get_json()['data']
    primeira = _parcela_financiamento(criado['id'], 1)

    pagamento = client.post(
        f'/api/financiamentos/parcelas/{primeira.id}/pagar',
        json={
            'valor_pago': float(primeira.valor_previsto_total),
            'data_pagamento': '2026-06-01',
        },
    )
    assert pagamento.status_code == 200

    response = client.put(
        f'/api/financiamentos/{criado["id"]}',
        json={'item_despesa_id': item_b.id},
    )
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert 'item de despesa' in body['error']
    assert db.session.get(Financiamento, criado['id']).item_despesa_id == item_a.id
    conta_paga = Conta.query.filter_by(financiamento_parcela_id=primeira.id).first()
    assert conta_paga.item_despesa_id == item_a.id


def test_editar_financiamento_item_despesa_bloqueia_com_amortizacao(client):
    item_a = _criar_item_despesa('Item amortizacao A')
    item_b = _criar_item_despesa('Item amortizacao B')
    payload = _payload_financiamento('Financiamento Item Amortizacao')
    payload['item_despesa_id'] = item_a.id
    response = client.post('/api/financiamentos', json=payload)
    assert response.status_code == 201
    criado = response.get_json()['data']

    amortizacao = client.post(
        f'/api/financiamentos/{criado["id"]}/amortizacao-extra',
        json={
            'data': '2026-07-01',
            'valor': 1000.0,
            'tipo': 'reduzir_parcela',
            'observacoes': 'Bloqueio troca item',
        },
    )
    assert amortizacao.status_code == 201

    response = client.put(
        f'/api/financiamentos/{criado["id"]}',
        json={'item_despesa_id': item_b.id},
    )
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert 'item de despesa' in body['error']
    assert db.session.get(Financiamento, criado['id']).item_despesa_id == item_a.id


def test_editar_financiamento_item_despesa_bloqueia_com_ajuste_saldo(client):
    item_a = _criar_item_despesa('Item ajuste A')
    item_b = _criar_item_despesa('Item ajuste B')
    payload = _payload_financiamento('Financiamento Item Ajuste')
    payload['item_despesa_id'] = item_a.id
    response = client.post('/api/financiamentos', json=payload)
    assert response.status_code == 201
    criado = response.get_json()['data']
    referencia = _parcela_financiamento(criado['id'], 3)

    ajuste = client.post(
        f'/api/financiamentos/{criado["id"]}/ajustar-saldo',
        json={
            'parcela_referencia_id': referencia.id,
            'numero_parcela': referencia.numero_parcela,
            'data_referencia': referencia.data_vencimento.isoformat(),
            'saldo_devedor_real': 300000.0,
            'tipo_ajuste': 'ajuste_saldo_real',
            'observacao': 'Bloqueio troca item',
            'recalcular_parcelas_futuras': True,
        },
    )
    assert ajuste.status_code == 200

    response = client.put(
        f'/api/financiamentos/{criado["id"]}',
        json={'item_despesa_id': item_b.id},
    )
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert 'item de despesa' in body['error']
    assert db.session.get(Financiamento, criado['id']).item_despesa_id == item_a.id


def test_financiamento_item_despesa_invalido_retorna_erro_claro(client):
    payload = _payload_financiamento('Financiamento Item Invalido')
    payload['item_despesa_id'] = 999999
    response = client.post('/api/financiamentos', json=payload)
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert 'Item de despesa invalido' in body['error']

    criado = _criar_financiamento(client, 'Financiamento Edita Item Invalido')
    response = client.put(
        f'/api/financiamentos/{criado["id"]}',
        json={'item_despesa_id': 999999},
    )
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert 'Item de despesa invalido' in body['error']


def test_excluir_financiamento_bloqueia_parcela_paga(client):
    criado = _criar_financiamento(client)
    primeira = _parcela_financiamento(criado['id'], 1)

    pagamento = client.post(
        f'/api/financiamentos/parcelas/{primeira.id}/pagar',
        json={
            'valor_pago': float(primeira.valor_previsto_total),
            'data_pagamento': '2026-06-01',
        },
    )
    assert pagamento.status_code == 200

    response = client.delete(f'/api/financiamentos/{criado["id"]}')
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert 'parcelas pagas' in body['message']
    assert db.session.get(Financiamento, criado['id']) is not None
    assert _parcela_financiamento(criado['id'], 1).status == 'pago'


def test_excluir_financiamento_bloqueia_conta_paga_vinculada(client):
    criado = _criar_financiamento(client)
    parcela = _parcela_financiamento(criado['id'], 2)
    conta = Conta.query.filter_by(financiamento_parcela_id=parcela.id).first()
    assert conta is not None

    conta.status_pagamento = 'Pago'
    conta.data_pagamento = date(2026, 7, 1)
    db.session.commit()

    response = client.delete(f'/api/financiamentos/{criado["id"]}')
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert 'movimentacoes financeiras vinculadas' in body['message']
    assert db.session.get(Financiamento, criado['id']) is not None
    assert db.session.get(Conta, conta.id) is not None


def test_excluir_financiamento_bloqueia_amortizacao_registrada(client):
    criado = _criar_financiamento(client)
    amortizacao = client.post(
        f'/api/financiamentos/{criado["id"]}/amortizacao-extra',
        json={
            'data': '2026-07-01',
            'valor': 1000.0,
            'tipo': 'reduzir_parcela',
            'observacoes': 'Bloqueio exclusao',
        },
    )
    assert amortizacao.status_code == 201

    response = client.delete(f'/api/financiamentos/{criado["id"]}')
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert db.session.get(Financiamento, criado['id']) is not None
    assert FinanciamentoAmortizacaoExtra.query.filter_by(financiamento_id=criado['id']).count() == 1


def test_excluir_financiamento_bloqueia_ajuste_saldo_registrado(client):
    criado = _criar_financiamento(client)
    referencia = _parcela_financiamento(criado['id'], 3)
    ajuste = client.post(
        f'/api/financiamentos/{criado["id"]}/ajustar-saldo',
        json={
            'parcela_referencia_id': referencia.id,
            'numero_parcela': referencia.numero_parcela,
            'data_referencia': referencia.data_vencimento.isoformat(),
            'saldo_devedor_real': 300000.0,
            'tipo_ajuste': 'ajuste_saldo_real',
            'observacao': 'Bloqueio exclusao',
            'recalcular_parcelas_futuras': True,
        },
    )
    assert ajuste.status_code == 200

    response = client.delete(f'/api/financiamentos/{criado["id"]}')
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert db.session.get(Financiamento, criado['id']) is not None
    assert FinanciamentoAjusteSaldo.query.filter_by(financiamento_id=criado['id']).count() == 1


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


def test_amortizacao_com_seguro_fixo_preserva_seguro_e_recalcula_futuras(client):
    criado = _criar_financiamento(client)
    anterior = _parcela_financiamento(criado['id'], 4)
    juros_original = float(anterior.valor_juros)
    total_original = float(anterior.valor_previsto_total)

    response = client.post(
        f'/api/financiamentos/{criado["id"]}/amortizacao-extra',
        json={
            'data': '2026-07-01',
            'valor': 10000.0,
            'tipo': 'reduzir_parcela',
            'observacoes': 'Amortizacao teste seguro fixo',
        },
    )
    body = response.get_json()

    assert response.status_code == 201
    assert body['success'] is True

    atualizada = _parcela_financiamento(criado['id'], 4)
    assert float(atualizada.valor_seguro) == 200.0
    assert float(atualizada.valor_juros) < juros_original
    assert float(atualizada.valor_previsto_total) < total_original

    conta = Conta.query.filter_by(financiamento_parcela_id=atualizada.id).first()
    assert conta is not None
    assert float(conta.valor) == float(atualizada.valor_previsto_total)


def test_amortizacao_com_seguro_estimado_recalcula_seguro_por_saldo_e_juros(client):
    response = client.post('/api/financiamentos', json=_payload_financiamento_estimado())
    criado = response.get_json()['data']
    referencia = _parcela_financiamento(criado['id'], 6)
    saldo_original = float(referencia.saldo_devedor_apos_pagamento)
    juros_original = float(referencia.valor_juros)
    seguro_original = float(referencia.valor_seguro)
    total_original = float(referencia.valor_previsto_total)

    response = client.post(
        f'/api/financiamentos/{criado["id"]}/amortizacao-extra',
        json={
            'data': '2030-03-01',
            'valor': 15000.0,
            'tipo': 'reduzir_parcela',
            'observacoes': 'Amortizacao teste seguro estimado',
        },
    )
    body = response.get_json()

    assert response.status_code == 201
    assert body['success'] is True

    atualizada = _parcela_financiamento(criado['id'], 6)
    assert float(atualizada.saldo_devedor_apos_pagamento) < saldo_original
    assert float(atualizada.valor_juros) < juros_original
    assert float(atualizada.valor_seguro) < seguro_original
    assert float(atualizada.valor_previsto_total) < total_original
    assert float(atualizada.valor_seguro) == _seguro_esperado(
        atualizada.valor_amortizacao,
        atualizada.valor_juros,
        Decimal('0.08593'),
    )


def test_amortizacao_estimado_respeita_mudanca_de_faixa_em_fevereiro(client):
    response = client.post('/api/financiamentos', json=_payload_financiamento_estimado('Financiamento Faixa'))
    criado = response.get_json()['data']

    response = client.post(
        f'/api/financiamentos/{criado["id"]}/amortizacao-extra',
        json={
            'data': '2030-01-01',
            'valor': 5000.0,
            'tipo': 'reduzir_parcela',
            'observacoes': 'Amortizacao antes da troca de faixa',
        },
    )
    body = response.get_json()

    assert response.status_code == 201
    assert body['success'] is True

    janeiro = _parcela_financiamento(criado['id'], 1)
    fevereiro = _parcela_financiamento(criado['id'], 2)

    assert float(janeiro.valor_seguro) == _seguro_esperado(
        janeiro.valor_amortizacao,
        janeiro.valor_juros,
        Decimal('0.04899'),
    )
    assert float(fevereiro.valor_seguro) == _seguro_esperado(
        fevereiro.valor_amortizacao,
        fevereiro.valor_juros,
        Decimal('0.08593'),
    )
    assert float(fevereiro.valor_seguro) > float(janeiro.valor_seguro)


def test_amortizacao_preserva_parcela_paga_anterior_ao_marco(client):
    criado = _criar_financiamento(client)
    parcela_paga = _parcela_financiamento(criado['id'], 1)
    valor_original = float(parcela_paga.valor_previsto_total)
    seguro_original = float(parcela_paga.valor_seguro)

    pagamento = client.post(
        f'/api/financiamentos/parcelas/{parcela_paga.id}/pagar',
        json={
            'valor_pago': valor_original,
            'data_pagamento': '2026-06-01',
        },
    )
    assert pagamento.status_code == 200

    futura = _parcela_financiamento(criado['id'], 4)
    juros_original_futura = float(futura.valor_juros)

    response = client.post(
        f'/api/financiamentos/{criado["id"]}/amortizacao-extra',
        json={
            'data': '2026-08-01',
            'valor': 10000.0,
            'tipo': 'reduzir_parcela',
            'observacoes': 'Amortizacao com historico pago',
        },
    )
    body = response.get_json()

    assert response.status_code == 201
    assert body['success'] is True

    parcela_paga = _parcela_financiamento(criado['id'], 1)
    futura = _parcela_financiamento(criado['id'], 4)
    assert parcela_paga.status == 'pago'
    assert float(parcela_paga.valor_previsto_total) == valor_original
    assert float(parcela_paga.valor_seguro) == seguro_original
    assert float(futura.valor_juros) < juros_original_futura


def test_amortizacao_bloqueia_conta_futura_efetivada(client):
    criado = _criar_financiamento(client)
    parcela = _parcela_financiamento(criado['id'], 4)
    conta = Conta.query.filter_by(financiamento_parcela_id=parcela.id).first()
    assert conta is not None

    conta.status_pagamento = 'Pago'
    conta.data_pagamento = date(2026, 9, 1)
    db.session.commit()

    juros_original = float(parcela.valor_juros)
    response = client.post(
        f'/api/financiamentos/{criado["id"]}/amortizacao-extra',
        json={
            'data': '2026-07-01',
            'valor': 10000.0,
            'tipo': 'reduzir_parcela',
            'observacoes': 'Deve bloquear conta paga',
        },
    )
    body = response.get_json()

    assert response.status_code == 400
    assert body['success'] is False
    assert 'contas ja efetivadas' in body['error']

    parcela = _parcela_financiamento(criado['id'], 4)
    conta = Conta.query.filter_by(financiamento_parcela_id=parcela.id).first()
    assert float(parcela.valor_juros) == juros_original
    assert conta.status_pagamento == 'Pago'
    assert conta.data_pagamento == date(2026, 9, 1)


def test_demonstrativo_anual_alimenta_extrato(client):
    criado = _criar_financiamento(client)

    response = client.get(f'/api/financiamentos/{criado["id"]}/demonstrativo-anual?ano=2026')
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    assert body['data']['ano'] == 2026
    assert body['data']['resumo_mensal']


def test_demonstrativo_anual_extrato_inclui_taxa_administrativa_na_composicao(client):
    payload = _payload_financiamento('Financiamento Extrato Taxa Adm')
    payload['taxa_administracao_fixa'] = 25.0
    response = client.post('/api/financiamentos', json=payload)
    assert response.status_code == 201
    criado = response.get_json()['data']

    response = client.get(f'/api/financiamentos/{criado["id"]}/demonstrativo-anual?ano=2026')
    body = response.get_json()

    assert response.status_code == 200
    assert body['success'] is True
    junho = body['data']['resumo_mensal']['6']
    assert junho['taxa_adm'] == 25.0
    assert junho['total_previsto'] == pytest.approx(
        junho['amortizacao'] + junho['juros'] + junho['seguro'] + junho['taxa_adm']
    )


def test_frontend_extrato_exibe_coluna_taxa_administrativa():
    base_dir = Path(__file__).resolve().parents[1]
    js = (base_dir / 'frontend' / 'static' / 'js' / 'financiamentos.js').read_text(encoding='utf-8')
    inicio = js.index('async function carregarDemonstrativo')
    fim = js.index('function abrirMenuMaisAcoes', inicio)
    trecho = js[inicio:fim]

    assert 'Taxa adm' in trecho
    assert 'linha.taxa_adm' in trecho
    assert 'fin-demo-row-extrato' in trecho


def test_template_nao_depende_de_modal_antigo_para_cadastro(client):
    response = client.get('/financiamentos')
    html = response.get_data(as_text=True)

    assert 'fin-form-view' in html
    assert 'modal-financiamento' not in html
    assert 'modal-detalhes' not in html


def test_frontend_oculta_acoes_incompletas_de_financiamento(client):
    base_dir = Path(__file__).resolve().parents[1]
    template = (base_dir / 'frontend' / 'templates' / 'financiamentos.html').read_text(encoding='utf-8')
    js = (base_dir / 'frontend' / 'static' / 'js' / 'financiamentos.js').read_text(encoding='utf-8')

    for texto in [
        'Gerar boleto de quitação',
        'Ver em tabela',
        'Filtros',
    ]:
        assert texto not in template

    assert 'data-tab="quitacao"' not in template

    for residuo in [
        'Gerenciar seguro habitacional',
        'abrirSeguroHabitacional',
        'registrarPendenciaQuitacao',
        'alternarModoTabela',
        'focarFiltroParcelas',
        'abrirQuitacao',
        'renderizarAbaQuitacao',
    ]:
        assert residuo not in js


def test_frontend_documentos_financiamento_tem_fluxo_real(client):
    response = client.get('/financiamentos')
    html = response.get_data(as_text=True)
    base_dir = Path(__file__).resolve().parents[1]
    js = (base_dir / 'frontend' / 'static' / 'js' / 'financiamentos.js').read_text(encoding='utf-8')

    assert 'data-tab="documentos"' in html
    assert 'Documentos' in html
    assert 'function renderizarAbaDocumentos' in js
    assert 'id="form-fin-doc"' in js
    assert 'name="arquivo"' in js
    assert 'Enviar documento' in js
    assert 'function carregarDocumentosFinanciamento' in js
    assert 'function baixarDocumentoFinanciamento' in js
    assert 'function excluirDocumentoFinanciamento' in js
    assert 'Conferir valores' in js
    assert 'modal-conferencia-caixa' in html
    assert 'A conferência não altera o cronograma' in html
    assert 'function salvarConferenciaCaixa' in js
    assert 'function carregarConferenciasCaixa' in js
    assert '/conferencias-caixa' in js
    assert '${API_BASE}/${financiamento.id}/documentos' in js
    assert 'FormData(form)' in js
    assert 'OCR' not in html
    assert 'leitura automática' not in html.lower()


def test_frontend_exclusao_financiamento_tem_botao_e_delete(client):
    response = client.get('/financiamentos')
    html = response.get_data(as_text=True)
    base_dir = Path(__file__).resolve().parents[1]
    js = (base_dir / 'frontend' / 'static' / 'js' / 'financiamentos.js').read_text(encoding='utf-8')
    inicio = js.index('async function tentarExcluirFinanciamento')
    fim = js.index('function abrirModal', inicio)
    trecho = js[inicio:fim]

    assert 'Excluir financiamento' in html
    assert 'tentarExcluirFinanciamento()' in html
    assert "method: 'DELETE'" in trecho
    assert 'mostrarView' in trecho
    assert 'carregarFinanciamentos' in trecho
    assert 'mostrarToast(error.message' in trecho


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
        'seguro_dfi_base',
        'seguro_data_nascimento_titular',
        'seguro_mes_reajuste_idade',
        'faixas_mip',
        'taxa_administracao_fixa',
        'regenerar_cronograma',
    ]:
        assert campo in trecho

    assert 'modo_calculo_financiamento:' not in trecho
    assert 'modo_taxa_mensal:' not in trecho
    assert 'caixa_sac_tr' not in trecho
    assert 'seguro_tipo:' not in trecho
    assert 'ajustarDataPrimeiraPorDia' in trecho


def test_frontend_payload_de_ajuste_saldo_envia_campos_obrigatorios():
    base_dir = Path(__file__).resolve().parents[1]
    js = (base_dir / 'frontend' / 'static' / 'js' / 'financiamentos.js').read_text(encoding='utf-8')
    trecho = js[js.index('async function salvarAjusteSaldo'):js.index('function simularAmortizacaoDetalhe')]

    for campo in [
        'parcela_referencia_id',
        'numero_parcela',
        'data_referencia',
        'saldo_devedor_real',
        'tipo_ajuste',
        'observacao',
        'recalcular_parcelas_futuras',
    ]:
        assert campo in trecho

    assert '/ajustar-saldo' in trecho


# ── FIN-QUIT-1: Simulação de quitação ────────────────────────────────────────

def test_simular_quitacao_retorna_estrutura_esperada(client):
    """Simulação básica: retorna campos obrigatórios sem alterar o banco."""
    fin = _criar_financiamento(client)
    fin_id = fin['id']

    # Garante que exista pelo menos uma parcela pendente
    parcela = FinanciamentoParcela.query.filter_by(financiamento_id=fin_id).first()
    assert parcela is not None

    data_quit = '2028-01-01'
    resp = client.post(f'/api/financiamentos/{fin_id}/simular-quitacao', json={
        'data_quitacao': data_quit,
    })
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['success'] is True

    d = body['data']
    for campo in [
        'financiamento_id',
        'financiamento_nome',
        'data_quitacao',
        'saldo_devedor_base',
        'saldo_devedor_estimado',
        'parcelas_restantes_total',
        'parcelas_futuras_consideradas',
        'juros_futuros_estimados',
        'seguros_futuros_estimados',
        'taxas_futuras_estimadas',
        'desconto_estimado',
        'economia_estimada',
        'valor_quitacao_estimado',
        'modo_calculo',
        'observacoes',
    ]:
        assert campo in d, f'Campo ausente: {campo}'

    assert isinstance(d['observacoes'], list)
    assert len(d['observacoes']) >= 1


def test_simular_quitacao_nao_altera_saldo_devedor(client):
    """Simulação não deve modificar o saldo_devedor_atual do financiamento."""
    fin = _criar_financiamento(client)
    fin_id = fin['id']
    saldo_antes = Financiamento.query.get(fin_id).saldo_devedor_atual

    client.post(f'/api/financiamentos/{fin_id}/simular-quitacao', json={
        'data_quitacao': '2030-01-01',
    })

    saldo_depois = Financiamento.query.get(fin_id).saldo_devedor_atual
    assert saldo_antes == saldo_depois


def test_simular_quitacao_nao_altera_status_parcelas(client):
    """Simulação não deve mudar o status de nenhuma parcela."""
    fin = _criar_financiamento(client)
    fin_id = fin['id']
    statuses_antes = {
        p.id: p.status
        for p in FinanciamentoParcela.query.filter_by(financiamento_id=fin_id).all()
    }

    client.post(f'/api/financiamentos/{fin_id}/simular-quitacao', json={
        'data_quitacao': '2030-01-01',
    })

    for p in FinanciamentoParcela.query.filter_by(financiamento_id=fin_id).all():
        assert p.status == statuses_antes[p.id], f'Status da parcela {p.id} foi alterado'


def test_simular_quitacao_usa_saldo_devedor_como_base(client):
    """Valor estimado deve ser baseado no saldo_devedor_atual, não na soma de parcelas."""
    fin = _criar_financiamento(client)
    fin_id = fin['id']
    financiamento = Financiamento.query.get(fin_id)
    saldo = financiamento.saldo_devedor_atual

    resp = client.post(f'/api/financiamentos/{fin_id}/simular-quitacao', json={
        'data_quitacao': '2030-01-01',
    })
    assert resp.status_code == 200
    d = resp.get_json()['data']

    # saldo_devedor_base deve ser igual ao saldo_devedor_atual do financiamento
    assert abs(d['saldo_devedor_base'] - float(saldo)) < 0.01

    # valor_quitacao_estimado <= saldo_devedor_estimado (desconto só reduz, não aumenta)
    assert d['valor_quitacao_estimado'] <= d['saldo_devedor_estimado'] + 0.01


def test_simular_quitacao_com_desconto_reduz_valor(client):
    """Desconto hipotético deve reduzir o valor estimado."""
    fin = _criar_financiamento(client)
    fin_id = fin['id']

    resp_sem = client.post(f'/api/financiamentos/{fin_id}/simular-quitacao', json={
        'data_quitacao': '2030-01-01',
    })
    resp_com = client.post(f'/api/financiamentos/{fin_id}/simular-quitacao', json={
        'data_quitacao': '2030-01-01',
        'desconto_banco_percentual': 20.0,
    })
    assert resp_sem.status_code == 200
    assert resp_com.status_code == 200

    sem = resp_sem.get_json()['data']
    com = resp_com.get_json()['data']

    # Com desconto, valor_quitacao_estimado deve ser <= sem desconto
    assert com['valor_quitacao_estimado'] <= sem['valor_quitacao_estimado']
    # desconto_estimado deve ser maior que zero quando há juros futuros e % > 0
    if sem['juros_futuros_estimados'] > 0:
        assert com['desconto_estimado'] > 0


def test_simular_quitacao_sem_data_retorna_400(client):
    """data_quitacao é obrigatória."""
    fin = _criar_financiamento(client)
    resp = client.post(f'/api/financiamentos/{fin["id"]}/simular-quitacao', json={})
    assert resp.status_code == 400


def test_simular_quitacao_financiamento_inexistente_retorna_erro(client):
    resp = client.post('/api/financiamentos/99999/simular-quitacao', json={
        'data_quitacao': '2030-01-01',
    })
    assert resp.status_code in (400, 404)
    assert resp.get_json()['success'] is False


def test_frontend_simular_quitacao_envia_payload_correto():
    """JS deve enviar data_quitacao e desconto_banco_percentual para a rota correta."""
    base_dir = Path(__file__).resolve().parents[1]
    js = (base_dir / 'frontend' / 'static' / 'js' / 'financiamentos.js').read_text(encoding='utf-8')

    assert 'async function simularQuitacao' in js
    trecho = js[js.index('async function simularQuitacao'):]
    # Delimita pelo próximo 'async function' ou 'function'
    import re
    m = re.search(r'\n(?:async )?function ', trecho[1:])
    if m:
        trecho = trecho[:m.start() + 1]

    assert 'simular-quitacao' in trecho
    assert 'data_quitacao' in trecho
    assert 'desconto_banco_percentual' in trecho
