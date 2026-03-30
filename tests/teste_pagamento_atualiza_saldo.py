"""
TESTE: Pagamento de parcela atualiza saldo soberano
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import db, Financiamento, FinanciamentoParcela
from backend.services.financiamento_service import FinanciamentoService
from decimal import Decimal
from datetime import date

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("TESTE: Pagamento de Parcela Atualiza Saldo Soberano")
    print("="*80)

    # Buscar financiamento ativo
    financiamento = Financiamento.query.filter_by(ativo=True).first()
    if not financiamento:
        print("\n[ERRO] Nenhum financiamento ativo encontrado!")
        exit(1)

    print(f"\n[1] Financiamento: {financiamento.nome} (ID={financiamento.id})")

    saldo_antes = financiamento.saldo_devedor_atual
    print(f"    Saldo soberano ANTES: R$ {saldo_antes:,.2f}")

    # Buscar primeira parcela pendente
    parcela = FinanciamentoParcela.query.filter_by(
        financiamento_id=financiamento.id,
        status='pendente'
    ).order_by(FinanciamentoParcela.numero_parcela).first()

    if not parcela:
        print("\n[ERRO] Nenhuma parcela pendente encontrada!")
        exit(1)

    print(f"\n[2] Parcela #{parcela.numero_parcela}")
    print(f"    Amortização: R$ {parcela.valor_amortizacao:,.2f}")
    print(f"    Juros: R$ {parcela.valor_juros:,.2f}")
    print(f"    Total: R$ {parcela.valor_previsto_total:,.2f}")
    print(f"    Status ANTES: {parcela.status}")

    # PAGAR PARCELA
    print("\n" + "-"*80)
    print("[3] PAGANDO PARCELA...")
    print("-"*80)

    try:
        FinanciamentoService.registrar_pagamento_parcela(
            parcela_id=parcela.id,
            valor_pago=float(parcela.valor_previsto_total),
            data_pagamento=date.today()
        )
        print("[OK] Parcela paga com sucesso")
    except Exception as e:
        print(f"[ERRO] Falha ao pagar parcela: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

    # Recarregar do banco
    db.session.refresh(parcela)
    db.session.refresh(financiamento)

    saldo_depois = financiamento.saldo_devedor_atual

    print(f"\n[4] Estado DEPOIS do pagamento:")
    print(f"    Parcela.status: {parcela.status}")
    print(f"    Saldo soberano DEPOIS: R$ {saldo_depois:,.2f}")

    # VALIDAÇÃO
    print("\n" + "="*80)
    print("VALIDAÇÃO")
    print("="*80)

    sucesso = True

    # 1. Parcela deve estar paga
    if parcela.status != 'pago':
        print(f"\n[FALHA] Parcela não foi marcada como paga! Status: {parcela.status}")
        sucesso = False
    else:
        print(f"\n[OK] Parcela marcada como paga")

    # 2. Saldo deve ter reduzido pela amortização
    saldo_esperado = saldo_antes - parcela.valor_amortizacao
    diff = abs(saldo_depois - saldo_esperado)

    if diff > Decimal('0.01'):
        print(f"[FALHA] Saldo não foi atualizado corretamente!")
        print(f"        Saldo ANTES: R$ {saldo_antes:,.2f}")
        print(f"        Amortização: R$ {parcela.valor_amortizacao:,.2f}")
        print(f"        Saldo ESPERADO: R$ {saldo_esperado:,.2f}")
        print(f"        Saldo OBTIDO: R$ {saldo_depois:,.2f}")
        print(f"        Diferença: R$ {diff:,.2f}")
        sucesso = False
    else:
        print(f"[OK] Saldo soberano atualizado corretamente")
        print(f"     R$ {saldo_antes:,.2f} - R$ {parcela.valor_amortizacao:,.2f} = R$ {saldo_depois:,.2f}")

    # Resultado final
    print("\n" + "="*80)
    if sucesso:
        print("TESTE: SUCESSO")
        print("="*80)
        print("\nPagamento de parcela está atualizando o saldo soberano!")
    else:
        print("TESTE: FALHA")
        print("="*80)
        print("\nPagamento NÃO está atualizando o saldo corretamente.")

    print()
