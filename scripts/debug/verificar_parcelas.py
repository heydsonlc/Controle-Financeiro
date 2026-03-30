"""
Verificar parcelas específicas para validar recálculo
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import db, Financiamento, FinanciamentoParcela

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("VERIFICAÇÃO DE PARCELAS")
    print("="*80)

    financiamento = Financiamento.query.filter_by(ativo=True).first()
    if not financiamento:
        print("\n[ERRO] Nenhum financiamento ativo encontrado!")
        exit(1)

    print(f"\n[1] Financiamento: {financiamento.nome}")
    print(f"    Saldo soberano: R$ {financiamento.saldo_devedor_atual:,.2f}")
    print(f"    Amortização mensal: R$ {financiamento.amortizacao_mensal_atual:,.2f}")

    # Buscar parcelas em diferentes períodos
    parcelas_ids = [1, 20, 40, 240]  # 2024, 2025, 2026, 2043

    for num in parcelas_ids:
        parcela = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento.id,
            numero_parcela=num
        ).first()

        if parcela:
            print(f"\n[Parcela #{parcela.numero_parcela}] {parcela.data_vencimento}")
            print(f"    Amortização: R$ {parcela.valor_amortizacao:,.2f}")
            print(f"    Juros: R$ {parcela.valor_juros:,.2f}")
            print(f"    Seguro: R$ {parcela.valor_seguro:,.2f}")
            print(f"    Total: R$ {parcela.valor_previsto_total:,.2f}")
            print(f"    Saldo após: R$ {parcela.saldo_devedor_apos_pagamento:,.2f}")

    print("\n" + "="*80)
    print()
