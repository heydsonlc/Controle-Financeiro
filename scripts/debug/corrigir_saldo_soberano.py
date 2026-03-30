"""
Correção: Ajustar saldo soberano para refletir parcelas já pagas

O problema: Migration inicializou saldo_devedor_atual = valor_financiado,
mas financiamento já tinha parcelas pagas.

A solução: Buscar última parcela consolidada e usar seu saldo_devedor_apos_pagamento
como saldo soberano.
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import db, Financiamento, FinanciamentoParcela
from decimal import Decimal

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("CORREÇÃO: Ajustar Saldo Soberano")
    print("="*80)

    # Buscar todos os financiamentos
    financiamentos = Financiamento.query.all()

    for fin in financiamentos:
        print(f"\n[INFO] Processando financiamento: {fin.nome} (ID={fin.id})")
        print(f"       Saldo soberano ATUAL: R$ {fin.saldo_devedor_atual:,.2f}")

        # Buscar última parcela paga
        ultima_paga = FinanciamentoParcela.query.filter_by(
            financiamento_id=fin.id,
            status='pago'
        ).order_by(FinanciamentoParcela.numero_parcela.desc()).first()

        if ultima_paga:
            # Há parcelas pagas - usar saldo da última paga
            saldo_correto = ultima_paga.saldo_devedor_apos_pagamento
            print(f"       Última parcela paga: #{ultima_paga.numero_parcela}")
            print(f"       Saldo após pagamento: R$ {saldo_correto:,.2f}")

            # Verificar se precisa corrigir
            diff = abs(fin.saldo_devedor_atual - saldo_correto)
            if diff > Decimal('0.01'):
                print(f"\n       [CORRIGIR] Diferença detectada: R$ {diff:,.2f}")

                # Atualizar estado soberano
                fin.saldo_devedor_atual = saldo_correto
                fin.numero_parcela_base = ultima_paga.numero_parcela
                fin.data_base = ultima_paga.data_vencimento

                print(f"       [OK] Saldo soberano corrigido: R$ {saldo_correto:,.2f}")
                print(f"       [OK] Parcela base: #{ultima_paga.numero_parcela}")
                print(f"       [OK] Data base: {ultima_paga.data_vencimento}")
            else:
                print(f"       [OK] Saldo já está correto (diff < R$ 0.01)")
        else:
            # Nenhuma parcela paga - usar valor financiado
            print(f"       [INFO] Nenhuma parcela paga - mantendo valor_financiado")
            if fin.saldo_devedor_atual != fin.valor_financiado:
                fin.saldo_devedor_atual = fin.valor_financiado
                fin.numero_parcela_base = 0
                print(f"       [OK] Saldo corrigido para valor_financiado: R$ {fin.valor_financiado:,.2f}")

    # Commit das alterações
    db.session.commit()

    print("\n" + "="*80)
    print("CORREÇÃO CONCLUÍDA!")
    print("="*80)
    print("\nExecute 'python checklist_saldo_soberano.py' para validar\n")
