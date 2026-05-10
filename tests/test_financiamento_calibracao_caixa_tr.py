from datetime import date
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path

from dateutil.relativedelta import relativedelta
import pytest
from flask import Flask

from backend.models import db, FinanciamentoParcela, IndiceTRMensal
from backend.routes.financiamentos import financiamentos_bp


getcontext().prec = 34

CENTAVO = Decimal('0.01')
VALOR_FINANCIADO = Decimal('500000.00')
PRAZO_MESES = 420
DATA_INICIO = date(2024, 5, 5)
TAXA_NOMINAL_ANUAL = Decimal('0.0938')
TAXA_MENSAL_NOMINAL = TAXA_NOMINAL_ANUAL / Decimal('12')
TAXA_ADMINISTRATIVA = Decimal('25.00')
FATOR_DFI = Decimal('0.0489')
FATOR_MIP_ATE_45 = Decimal('0.03187')
FATOR_MIP_46_50 = Decimal('0.04899')
MES_REAJUSTE_MIP_CAIXA = 3

# Valor calibrado contra o saldo devedor teorico em 05/05/2026.
AMORTIZACAO_EXTRAORDINARIA = Decimal('216670.00')

# TR mensal extraida de tr.pdf. Armazenada como fator decimal:
# 0,16% = 0.0016.
TR_MENSAL = {
    '2024-05': Decimal('0.0008'),
    '2024-06': Decimal('0.0003'),
    '2024-07': Decimal('0.0007'),
    '2024-08': Decimal('0.0007'),
    '2024-09': Decimal('0.0006'),
    '2024-10': Decimal('0.0009'),
    '2024-11': Decimal('0.0006'),
    '2024-12': Decimal('0.0008'),
    '2025-01': Decimal('0.0016'),
    '2025-02': Decimal('0.0013'),
    '2025-03': Decimal('0.0010'),
    '2025-04': Decimal('0.0016'),
    '2025-05': Decimal('0.0017'),
    '2025-06': Decimal('0.0016'),
    '2025-07': Decimal('0.0017'),
    '2025-08': Decimal('0.0017'),
    '2025-09': Decimal('0.0017'),
    '2025-10': Decimal('0.0017'),
    '2025-11': Decimal('0.0016'),
    '2025-12': Decimal('0.0017'),
    '2026-01': Decimal('0.0017'),
    '2026-02': Decimal('0.0012'),
    '2026-03': Decimal('0.0017'),
    '2026-04': Decimal('0.0016'),
    '2026-05': Decimal('0.0016'),
    '2026-06': Decimal('0.0000'),
}

VALORES_REAIS_2025 = {
    '2025-01': {'amortizacao': Decimal('1203.31'), 'juros': Decimal('3873.73'), 'seguro': Decimal('182.06'), 'taxa': Decimal('25.00'), 'total': Decimal('5284.04')},
    '2025-02': {'amortizacao': Decimal('1205.34'), 'juros': Decimal('3870.86'), 'seguro': Decimal('182.07'), 'taxa': Decimal('25.00'), 'total': Decimal('5283.29')},
    '2025-03': {'amortizacao': Decimal('1206.23'), 'juros': Decimal('3864.27'), 'seguro': Decimal('248.07'), 'taxa': Decimal('25.00'), 'total': Decimal('5343.58')},
    '2025-04': {'amortizacao': Decimal('1208.31'), 'juros': Decimal('3861.51'), 'seguro': Decimal('248.02'), 'taxa': Decimal('25.00'), 'total': Decimal('5342.86')},
    '2025-05': {'amortizacao': Decimal('1209.21'), 'juros': Decimal('3854.93'), 'seguro': Decimal('247.74'), 'taxa': Decimal('25.00'), 'total': Decimal('5336.82')},
    '2025-06': {'amortizacao': Decimal('1211.33'), 'juros': Decimal('3852.21'), 'seguro': Decimal('247.70'), 'taxa': Decimal('25.00'), 'total': Decimal('5336.26')},
    '2025-07': {'amortizacao': Decimal('1213.41'), 'juros': Decimal('3849.34'), 'seguro': Decimal('247.65'), 'taxa': Decimal('25.00'), 'total': Decimal('5335.44')},
    '2025-08': {'amortizacao': Decimal('675.65'), 'juros': Decimal('2138.11'), 'seguro': Decimal('163.43'), 'taxa': Decimal('25.00'), 'total': Decimal('3002.21')},
    '2025-09': {'amortizacao': Decimal('676.84'), 'juros': Decimal('2136.58'), 'seguro': Decimal('163.45'), 'taxa': Decimal('25.00'), 'total': Decimal('3001.81')},
    '2025-10': {'amortizacao': Decimal('678.00'), 'juros': Decimal('2134.97'), 'seguro': Decimal('163.47'), 'taxa': Decimal('25.00'), 'total': Decimal('3001.47')},
    '2025-11': {'amortizacao': Decimal('679.18'), 'juros': Decimal('2133.38'), 'seguro': Decimal('163.50'), 'taxa': Decimal('25.00'), 'total': Decimal('3001.08')},
    '2025-12': {'amortizacao': Decimal('680.35'), 'juros': Decimal('2131.73'), 'seguro': Decimal('163.52'), 'taxa': Decimal('25.00'), 'total': Decimal('3000.54')},
}

EVOLUCAO_REAL = {
    '2026-01': {'amortizacao_juros': Decimal('2811.38'), 'seguro': Decimal('163.51'), 'taxa': Decimal('25.00'), 'total': Decimal('2999.92')},
    '2026-02': {'amortizacao_juros': Decimal('2810.98'), 'seguro': Decimal('163.56'), 'taxa': Decimal('25.00'), 'total': Decimal('2999.55')},
    '2026-03': {'amortizacao_juros': Decimal('2809.08'), 'seguro': Decimal('163.49'), 'taxa': Decimal('25.00'), 'total': Decimal('2997.59')},
    '2026-04': {'amortizacao_juros': Decimal('2808.54'), 'seguro': Decimal('163.50'), 'taxa': Decimal('25.00'), 'total': Decimal('2996.98')},
    '2026-05': {'amortizacao_juros': Decimal('2806.86'), 'seguro': Decimal('163.46'), 'taxa': Decimal('25.00'), 'total': Decimal('2995.33')},
    '2026-06': {'amortizacao_juros': Decimal('2806.35'), 'seguro': Decimal('163.48'), 'taxa': Decimal('25.00'), 'total': Decimal('2994.83')},
}

SALDO_DEVEDOR_TEO_PDF_2026_05 = Decimal('270800.85')


def _moeda(valor):
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _competencia(data_referencia):
    return f'{data_referencia.year}-{data_referencia.month:02d}'


def _fator_mip(data_vencimento):
    idade = data_vencimento.year - 1979
    if data_vencimento < date(data_vencimento.year, MES_REAJUSTE_MIP_CAIXA, 1):
        idade -= 1
    return FATOR_MIP_ATE_45 if idade <= 45 else FATOR_MIP_46_50


def _simular_caixa_sac_tr(corrigir_quota_amortizacao=True):
    """
    Simulador isolado para calibracao, sem dependencia do motor atual.

    Hipotese registrada:
    - taxa mensal = nominal / 12;
    - saldo corrigido pela TR do mes;
    - quota de amortizacao corrigida pela TR;
    - DFI baseado na base original/segurada;
    - amortizacao extra apos a parcela de julho/2025.
    """
    saldo = VALOR_FINANCIADO
    data_vencimento = DATA_INICIO
    amortizacao_original = VALOR_FINANCIADO / Decimal(str(PRAZO_MESES))
    quota_amortizacao = amortizacao_original
    amortizacao_extra_aplicada = False
    parcelas = {}

    for numero_parcela in range(1, PRAZO_MESES + 1):
        if not amortizacao_extra_aplicada and data_vencimento > date(2025, 7, 5):
            saldo -= AMORTIZACAO_EXTRAORDINARIA
            parcelas_restantes = PRAZO_MESES - numero_parcela + 1
            quota_amortizacao = saldo / Decimal(str(parcelas_restantes))
            amortizacao_extra_aplicada = True

        tr_mes = TR_MENSAL.get(_competencia(data_vencimento), Decimal('0'))
        if corrigir_quota_amortizacao:
            quota_amortizacao *= Decimal('1') + tr_mes

        saldo_corrigido = saldo * (Decimal('1') + tr_mes)
        juros = saldo_corrigido * TAXA_MENSAL_NOMINAL
        dfi = amortizacao_original * FATOR_DFI
        mip = juros * _fator_mip(data_vencimento)
        seguro = dfi + mip
        total = quota_amortizacao + juros + seguro + TAXA_ADMINISTRATIVA
        saldo_final = saldo_corrigido - quota_amortizacao

        parcelas[_competencia(data_vencimento)] = {
            'numero_parcela': numero_parcela,
            'amortizacao': _moeda(quota_amortizacao),
            'juros': _moeda(juros),
            'amortizacao_juros': _moeda(quota_amortizacao + juros),
            'seguro': _moeda(seguro),
            'taxa': TAXA_ADMINISTRATIVA,
            'total': _moeda(total),
            'saldo': _moeda(saldo_final),
        }

        saldo = saldo_final
        data_vencimento += relativedelta(months=1)

    return parcelas


def _erro(valor_simulado, valor_real):
    return abs(Decimal(valor_simulado) - Decimal(valor_real))


def _mae(parcelas, competencias, campo, dados_reais):
    total = sum(_erro(parcelas[competencia][campo], dados_reais[competencia][campo]) for competencia in competencias)
    return _moeda(total / Decimal(str(len(competencias))))


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

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


def _popular_tr_no_banco(skip_competencia=None, completar_futuro=True):
    valores = dict(TR_MENSAL)
    if completar_futuro:
        competencia = date(2026, 7, 1)
        while competencia <= date(2060, 12, 1):
            valores.setdefault(_competencia(competencia), Decimal('0.0000'))
            competencia += relativedelta(months=1)

    for competencia, valor in valores.items():
        if competencia == skip_competencia:
            continue
        ano, mes = [int(parte) for parte in competencia.split('-')]
        db.session.add(IndiceTRMensal(
            ano=ano,
            mes=mes,
            competencia=competencia,
            valor_decimal=valor,
            fonte='BACEN',
        ))
    db.session.commit()


def _payload_motor_caixa_tr(prazo=PRAZO_MESES):
    return {
        'nome': 'Financiamento CAIXA calibracao TR',
        'produto': 'SFH',
        'sistema_amortizacao': 'SAC',
        'modo_calculo_financiamento': 'caixa_sac_tr',
        'modo_taxa_mensal': 'nominal_dividida_12',
        'valor_financiado': float(VALOR_FINANCIADO),
        'prazo_total_meses': prazo,
        'taxa_juros_nominal_anual': 9.38,
        'indexador_saldo': 'TR',
        'data_contrato': DATA_INICIO.strftime('%Y-%m-%d'),
        'data_primeira_parcela': DATA_INICIO.strftime('%Y-%m-%d'),
        'seguro_modo': 'estimado_dfi_mip',
        'seguro_fator_dfi': float(FATOR_DFI),
        'seguro_dfi_base': float(VALOR_FINANCIADO / Decimal(str(PRAZO_MESES))),
        'seguro_data_nascimento_titular': '1979-02-01',
        'seguro_mes_reajuste_idade': MES_REAJUSTE_MIP_CAIXA,
        'valor_seguro_mensal': 0,
        'taxa_administracao_fixa': float(TAXA_ADMINISTRATIVA),
        'faixas_mip': [
            {'idade_inicio': 0, 'idade_fim': 45, 'fator_mip': float(FATOR_MIP_ATE_45)},
            {'idade_inicio': 46, 'idade_fim': 50, 'fator_mip': float(FATOR_MIP_46_50)},
            {'idade_inicio': 51, 'idade_fim': 55, 'fator_mip': 0.08593},
            {'idade_inicio': 56, 'idade_fim': 60, 'fator_mip': 0.16077},
            {'idade_inicio': 61, 'idade_fim': 65, 'fator_mip': 0.31887},
            {'idade_inicio': 66, 'idade_fim': 70, 'fator_mip': 0.34932},
            {'idade_inicio': 71, 'idade_fim': 75, 'fator_mip': 0.49795},
            {'idade_inicio': 76, 'idade_fim': 80, 'fator_mip': 0.57099},
        ],
    }


def _criar_motor_caixa_tr_com_amortizacao(client):
    _popular_tr_no_banco(completar_futuro=True)
    response = client.post('/api/financiamentos', json=_payload_motor_caixa_tr())
    assert response.status_code == 201, response.get_json()
    financiamento_id = response.get_json()['data']['id']

    parcelas_pre_amortizacao = FinanciamentoParcela.query.filter(
        FinanciamentoParcela.financiamento_id == financiamento_id,
        FinanciamentoParcela.data_vencimento <= date(2025, 7, 5),
    ).order_by(FinanciamentoParcela.numero_parcela).all()

    for parcela in parcelas_pre_amortizacao:
        response = client.post(
            f'/api/financiamentos/parcelas/{parcela.id}/pagar',
            json={
                'valor_pago': float(parcela.valor_previsto_total),
                'data_pagamento': parcela.data_vencimento.strftime('%Y-%m-%d'),
            },
        )
        assert response.status_code == 200, response.get_json()

    response = client.post(
        f'/api/financiamentos/{financiamento_id}/amortizacao-extra',
        json={
            'data': '2025-07-06',
            'valor': float(AMORTIZACAO_EXTRAORDINARIA),
            'tipo': 'reduzir_parcela',
            'observacoes': 'Amortizacao calibrada pelos demonstrativos CAIXA',
        },
    )
    assert response.status_code == 201, response.get_json()
    return financiamento_id


def _parcelas_por_competencia(financiamento_id):
    parcelas = FinanciamentoParcela.query.filter_by(
        financiamento_id=financiamento_id
    ).order_by(FinanciamentoParcela.numero_parcela).all()
    return {
        _competencia(parcela.data_vencimento): {
            'amortizacao': _moeda(parcela.valor_amortizacao),
            'juros': _moeda(parcela.valor_juros),
            'amortizacao_juros': _moeda(parcela.valor_amortizacao + parcela.valor_juros),
            'seguro': _moeda(parcela.valor_seguro),
            'taxa': _moeda(parcela.valor_taxa_adm),
            'total': _moeda(parcela.valor_previsto_total),
            'saldo': _moeda(parcela.saldo_devedor_apos_pagamento),
        }
        for parcela in parcelas
    }


def test_dados_reais_2025_fecham_com_total_pago():
    for competencia, real in VALORES_REAIS_2025.items():
        componentes = real['amortizacao'] + real['juros'] + real['seguro'] + real['taxa']
        assert _erro(componentes, real['total']) <= Decimal('0.10'), competencia


def test_tr_fixture_carrega_indices_obrigatorios():
    assert TR_MENSAL['2025-01'] == Decimal('0.0016')
    assert TR_MENSAL['2025-08'] == Decimal('0.0017')
    assert TR_MENSAL['2026-05'] == Decimal('0.0016')


def test_simulacao_pre_amortizacao_caixa_tr_aproxima_janeiro_a_julho_2025():
    parcelas = _simular_caixa_sac_tr()
    competencias = ['2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07']

    for competencia in competencias:
        simulado = parcelas[competencia]
        real = VALORES_REAIS_2025[competencia]
        assert _erro(simulado['amortizacao'], real['amortizacao']) <= Decimal('5.00'), competencia
        assert _erro(simulado['juros'], real['juros']) <= Decimal('15.00'), competencia
        assert _erro(simulado['seguro'], real['seguro']) <= Decimal('5.00'), competencia
        assert _erro(simulado['total'], real['total']) <= Decimal('25.00'), competencia


def test_simulacao_pos_amortizacao_caixa_tr_aproxima_agosto_a_dezembro_2025():
    parcelas = _simular_caixa_sac_tr()
    competencias = ['2025-08', '2025-09', '2025-10', '2025-11', '2025-12']

    for competencia in competencias:
        simulado = parcelas[competencia]
        real = VALORES_REAIS_2025[competencia]
        assert _erro(simulado['amortizacao'], real['amortizacao']) <= Decimal('5.00'), competencia
        assert _erro(simulado['juros'], real['juros']) <= Decimal('5.00'), competencia
        assert _erro(simulado['seguro'], real['seguro']) <= Decimal('5.00'), competencia
        assert _erro(simulado['total'], real['total']) <= Decimal('15.00'), competencia


def test_marco_agosto_2025_reproduz_queda_apos_amortizacao_extraordinaria():
    agosto = _simular_caixa_sac_tr()['2025-08']

    assert _erro(agosto['amortizacao'], Decimal('675.65')) <= Decimal('2.00')
    assert _erro(agosto['juros'], Decimal('2138.11')) <= Decimal('2.00')
    assert _erro(agosto['seguro'], Decimal('163.43')) <= Decimal('2.00')
    assert _erro(agosto['total'], Decimal('3002.21')) <= Decimal('5.00')


def test_saldo_maio_2026_fica_proximo_do_demonstrativo_de_evolucao():
    maio = _simular_caixa_sac_tr()['2026-05']

    assert _erro(maio['saldo'], SALDO_DEVEDOR_TEO_PDF_2026_05) <= Decimal('100.00')
    assert _erro(maio['saldo'], SALDO_DEVEDOR_TEO_PDF_2026_05) == Decimal('3.06')


def test_prestacao_aberta_junho_2026_fica_dentro_da_tolerancia():
    junho = _simular_caixa_sac_tr()['2026-06']
    real = EVOLUCAO_REAL['2026-06']

    assert _erro(junho['amortizacao_juros'], real['amortizacao_juros']) <= Decimal('10.00')
    assert _erro(junho['seguro'], real['seguro']) <= Decimal('5.00')
    assert _erro(junho['total'], real['total']) <= Decimal('15.00')


def test_quota_de_amortizacao_corrigida_por_tr_melhora_o_modelo():
    modelo_corrigido = _simular_caixa_sac_tr(corrigir_quota_amortizacao=True)
    modelo_somente_saldo = _simular_caixa_sac_tr(corrigir_quota_amortizacao=False)
    competencias = list(VALORES_REAIS_2025.keys())

    mae_corrigido = _mae(modelo_corrigido, competencias, 'total', VALORES_REAIS_2025)
    mae_somente_saldo = _mae(modelo_somente_saldo, competencias, 'total', VALORES_REAIS_2025)

    assert mae_corrigido <= Decimal('12.00')
    assert mae_corrigido < mae_somente_saldo


def test_modelo_indice_tr_mensal_registra_competencias_obrigatorias(app_context):
    _popular_tr_no_banco(completar_futuro=False)

    assert IndiceTRMensal.query.filter_by(competencia='2025-01').one().valor_decimal == Decimal('0.00160000')
    assert IndiceTRMensal.query.filter_by(competencia='2025-08').one().valor_decimal == Decimal('0.00170000')
    assert IndiceTRMensal.query.filter_by(competencia='2026-05').one().valor_decimal == Decimal('0.00160000')
    assert 'uq_indice_tr_mensal_competencia' in {
        constraint.name for constraint in IndiceTRMensal.__table__.constraints
    }


def test_motor_real_caixa_sac_tr_aproxima_janeiro_a_julho_2025(client):
    financiamento_id = _criar_motor_caixa_tr_com_amortizacao(client)
    parcelas = _parcelas_por_competencia(financiamento_id)

    for competencia in ['2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07']:
        simulado = parcelas[competencia]
        real = VALORES_REAIS_2025[competencia]
        assert _erro(simulado['amortizacao'], real['amortizacao']) <= Decimal('5.00'), competencia
        assert _erro(simulado['juros'], real['juros']) <= Decimal('15.00'), competencia
        assert _erro(simulado['seguro'], real['seguro']) <= Decimal('5.00'), competencia
        assert _erro(simulado['total'], real['total']) <= Decimal('25.00'), competencia


def test_motor_real_caixa_sac_tr_aproxima_pos_amortizacao_e_saldo_maio_2026(client):
    financiamento_id = _criar_motor_caixa_tr_com_amortizacao(client)
    parcelas = _parcelas_por_competencia(financiamento_id)

    for competencia in ['2025-08', '2025-09', '2025-10', '2025-11', '2025-12']:
        simulado = parcelas[competencia]
        real = VALORES_REAIS_2025[competencia]
        assert _erro(simulado['amortizacao'], real['amortizacao']) <= Decimal('5.00'), competencia
        assert _erro(simulado['juros'], real['juros']) <= Decimal('5.00'), competencia
        assert _erro(simulado['seguro'], real['seguro']) <= Decimal('5.00'), competencia
        assert _erro(simulado['total'], real['total']) <= Decimal('15.00'), competencia

    assert _erro(parcelas['2025-08']['seguro'], Decimal('163.43')) <= Decimal('5.00')
    assert _erro(parcelas['2026-05']['saldo'], SALDO_DEVEDOR_TEO_PDF_2026_05) <= Decimal('100.00')
    assert _erro(parcelas['2026-06']['total'], EVOLUCAO_REAL['2026-06']['total']) <= Decimal('15.00')


def test_motor_real_caixa_sac_tr_falha_quando_falta_tr(client):
    _popular_tr_no_banco(skip_competencia='2025-08', completar_futuro=True)

    response = client.post('/api/financiamentos', json=_payload_motor_caixa_tr(prazo=20))
    assert response.status_code == 400
    assert 'Nao ha TR cadastrada para a competencia 2025-08' in response.get_json()['error']
