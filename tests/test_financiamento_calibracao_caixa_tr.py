from datetime import date
from decimal import Decimal, ROUND_HALF_UP, getcontext

from dateutil.relativedelta import relativedelta


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
