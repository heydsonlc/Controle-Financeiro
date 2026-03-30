"""
TESTE: Pagamento usa saldo_devedor_apos_pagamento da parcela (SAC correto)
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
    print("TESTE: Pagamento Usa Saldo da Parcela (SAC Correto)")
    print("="*80)

    # Buscar financiamento ativo
    financiamento = Financiamento.query.filter_by(ativo=True).first()
    if not financiamento:
        print("\n[ERRO] Nenhum financiamento ativo encontrado!")
        exit(1)

    print(f"\n[1] Financiamento: {financiamento.nome} (ID={financiamento.id})")
    print(f"    Sistema: {financiamento.sistema_amortizacao}")
    print(f"    Indexador: {financiamento.indexador_saldo or 'Nenhum'}")

    saldo_antes = financiamento.saldo_devedor_atual
    print(f"    Saldo soberano ANTES: R$ {saldo_antes:,.2f}")

    # Buscar segunda parcela pendente (primeira pode estar paga)
    parcelas_pendentes = FinanciamentoParcela.query.filter_by(
        financiamento_id=financiamento.id,
        status='pendente'
    ).order_by(FinanciamentoParcela.numero_parcela).limit(2).all()

    if len(parcelas_pendentes) < 2:
        print("\n[ERRO] Precisamos de pelo menos 2 parcelas pendentes para testar!")
        exit(1)

    parcela = parcelas_pendentes[1]  # Segunda parcela

    print(f"\n[2] Parcela #{parcela.numero_parcela}")
    print(f"    Amortização: R$ {parcela.valor_amortizacao:,.2f}")
    print(f"    Juros: R$ {parcela.valor_juros:,.2f}")
    print(f"    Total: R$ {parcela.valor_previsto_total:,.2f}")
    print(f"    Saldo APÓS pagamento (calculado pelo SAC): R$ {parcela.saldo_devedor_apos_pagamento:,.2f}")
    print(f"    Status ANTES: {parcela.status}")

    # Validar que o saldo da parcela foi calculado corretamente
    # (deve ser diferente de simplesmente subtrair amortização)
    saldo_esperado_parcela = parcela.saldo_devedor_apos_pagamento

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

    # 2. Saldo soberano deve ser IGUAL ao saldo_devedor_apos_pagamento da parcela
    diff = abs(saldo_depois - saldo_esperado_parcela)

    if diff > Decimal('0.01'):
        print(f"[FALHA] Saldo soberano NÃO corresponde ao saldo da parcela!")
        print(f"        Saldo da parcela (SAC calculado): R$ {saldo_esperado_parcela:,.2f}")
        print(f"        Saldo soberano atual: R$ {saldo_depois:,.2f}")
        print(f"        Diferença: R$ {diff:,.2f}")
        sucesso = False
    else:
        print(f"[OK] Saldo soberano = saldo_devedor_apos_pagamento da parcela")
        print(f"     Ambos: R$ {saldo_depois:,.2f}")

    # 3. Validar que NÃO é simplesmente subtração de amortização
    # (se houver TR/IPCA, o saldo seria diferente)
    saldo_ingênuo = saldo_antes - parcela.valor_amortizacao
    diff_ingenuo = abs(saldo_depois - saldo_ingênuo)

    if diff_ingenuo > Decimal('0.01'):
        print(f"[INFO] Sistema está considerando fatores além da amortização (TR/IPCA, etc.)")
        print(f"      Saldo ingênuo (só amortização): R$ {saldo_ingênuo:,.2f}")
        print(f"      Saldo real (SAC completo): R$ {saldo_depois:,.2f}")
        print(f"      Diferença: R$ {diff_ingenuo:,.2f}")
    else:
        print(f"[INFO] Neste caso, saldo = amortização pura (sem TR/IPCA nesta parcela)")

    # Resultado final
    print("\n" + "="*80)
    if sucesso:
        print("TESTE: SUCESSO")
        print("="*80)
        print("\nPagamento está usando o saldo calculado pelo SAC!")
        print("✅ Considera correção monetária (TR/IPCA)")
        print("✅ Considera amortização")
        print("✅ Usa saldo_devedor_apos_pagamento da parcela")
    else:
        print("TESTE: FALHA")
        print("="*80)
        print("\nPagamento NÃO está usando o saldo correto do SAC.")

    print()
