"""
Checklist Mínimo: Verificar se SALDO SOBERANO está funcionando
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import db, Financiamento, FinanciamentoParcela
from decimal import Decimal

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("CHECKLIST: SALDO SOBERANO")
    print("="*80)

    # Buscar financiamento
    fin = Financiamento.query.first()
    if not fin:
        print("[ERRO] Nenhum financiamento encontrado!")
        exit(1)

    print(f"\nFinanciamento: {fin.nome} (ID={fin.id})")
    print("-" * 80)

    # 1. Verificar se campos de estado soberano existem
    print("\n[1] Verificando campos de estado soberano...")
    print(f"    saldo_devedor_atual: R$ {fin.saldo_devedor_atual:,.2f}" if fin.saldo_devedor_atual else "    [ERRO] saldo_devedor_atual = NULL")
    print(f"    numero_parcela_base: {fin.numero_parcela_base}" if fin.numero_parcela_base is not None else "    [ERRO] numero_parcela_base = NULL")
    print(f"    amortizacao_mensal_atual: R$ {fin.amortizacao_mensal_atual:,.2f}" if fin.amortizacao_mensal_atual else "    [ERRO] amortizacao_mensal_atual = NULL")
    print(f"    regime_pos_amortizacao: {fin.regime_pos_amortizacao or 'Nenhum (ainda não amortizou)'}")

    if not fin.saldo_devedor_atual:
        print("\n[ERRO] Estado soberano NÃO foi inicializado!")
        print("Execute: python aplicar_estado_soberano.py")
        exit(1)

    # 2. Verificar parcelas
    print("\n[2] Verificando parcelas...")
    total_parcelas = FinanciamentoParcela.query.filter_by(financiamento_id=fin.id).count()
    pagas = FinanciamentoParcela.query.filter_by(financiamento_id=fin.id, status='pago').count()
    pendentes = FinanciamentoParcela.query.filter_by(financiamento_id=fin.id, status='pendente').count()

    print(f"    Total: {total_parcelas} | Pagas: {pagas} | Pendentes: {pendentes}")

    # 3. Verificar primeira parcela pendente
    print("\n[3] Verificando primeira parcela pendente...")
    primeira_pendente = FinanciamentoParcela.query.filter_by(
        financiamento_id=fin.id,
        status='pendente'
    ).order_by(FinanciamentoParcela.numero_parcela).first()

    if primeira_pendente:
        print(f"    Parcela #{primeira_pendente.numero_parcela}")
        print(f"    Amortizacao: R$ {primeira_pendente.valor_amortizacao:,.2f}")
        print(f"    Juros: R$ {primeira_pendente.valor_juros:,.2f}")
        print(f"    Seguro: R$ {primeira_pendente.valor_seguro:,.2f}")
        print(f"    Total: R$ {primeira_pendente.valor_previsto_total:,.2f}")
        print(f"    Saldo apos: R$ {primeira_pendente.saldo_devedor_apos_pagamento:,.2f}")

        # Comparar amortização da parcela com amortização mensal atual
        diff_amort = abs(primeira_pendente.valor_amortizacao - fin.amortizacao_mensal_atual)
        if diff_amort > Decimal('0.01'):
            print(f"\n    [AVISO] Amortizacao da parcela (R$ {primeira_pendente.valor_amortizacao:,.2f}) != amortizacao_mensal_atual (R$ {fin.amortizacao_mensal_atual:,.2f})")
            print(f"    Diferenca: R$ {diff_amort:,.2f}")
    else:
        print("    [INFO] Nenhuma parcela pendente")

    # 4. Verificar consistência: saldo soberano vs parcela anterior à primeira pendente
    print("\n[4] Verificando consistência entre saldo soberano e parcelas...")
    if primeira_pendente and primeira_pendente.numero_parcela > 1:
        parcela_anterior = FinanciamentoParcela.query.filter_by(
            financiamento_id=fin.id,
            numero_parcela=primeira_pendente.numero_parcela - 1
        ).first()

        if parcela_anterior:
            saldo_parcela = parcela_anterior.saldo_devedor_apos_pagamento
            saldo_soberano = fin.saldo_devedor_atual

            print(f"    Saldo da parcela #{parcela_anterior.numero_parcela} (após pagamento): R$ {saldo_parcela:,.2f}")
            print(f"    Saldo soberano (financiamento): R$ {saldo_soberano:,.2f}")

            diff_saldo = abs(saldo_parcela - saldo_soberano)
            if diff_saldo > Decimal('0.01'):
                print(f"\n    [ERRO] SALDOS NÃO BATEM!")
                print(f"    Diferença: R$ {diff_saldo:,.2f}")
            else:
                print(f"\n    [OK] Saldos consistentes (diferença < R$ 0.01)")

    print("\n" + "="*80)
    print("FIM DO CHECKLIST")
    print("="*80 + "\n")
