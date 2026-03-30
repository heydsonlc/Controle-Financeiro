"""
Validar estado final após teste 4
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import db, Financiamento, FinanciamentoParcela, FinanciamentoSeguroVigencia
from decimal import Decimal

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("VALIDAÇÃO DO ESTADO FINAL")
    print("="*80)

    # Buscar financiamento ativo
    financiamento = Financiamento.query.filter_by(ativo=True).first()
    if not financiamento:
        print("\n[ERRO] Nenhum financiamento ativo encontrado!")
        exit(1)

    print(f"\n[1] Financiamento: {financiamento.nome} (ID={financiamento.id})")
    print(f"    Saldo soberano atual: R$ {financiamento.saldo_devedor_atual:,.2f}")
    print(f"    Amortização mensal atual: R$ {financiamento.amortizacao_mensal_atual:,.2f}")

    # Buscar primeira parcela pendente
    parcela = FinanciamentoParcela.query.filter_by(
        financiamento_id=financiamento.id,
        status='pendente'
    ).order_by(FinanciamentoParcela.numero_parcela).first()

    if parcela:
        print(f"\n[2] Primeira parcela pendente (#{parcela.numero_parcela}):")
        print(f"    Data vencimento: {parcela.data_vencimento}")
        print(f"    Amortização: R$ {parcela.valor_amortizacao:,.2f}")
        print(f"    Juros: R$ {parcela.valor_juros:,.2f}")
        print(f"    Seguro: R$ {parcela.valor_seguro:,.2f}")
        print(f"    Total: R$ {parcela.valor_previsto_total:,.2f}")

    # Buscar vigências
    vigencias = FinanciamentoSeguroVigencia.query.filter_by(
        financiamento_id=financiamento.id,
        vigencia_ativa=True
    ).order_by(FinanciamentoSeguroVigencia.competencia_inicio).all()

    print(f"\n[3] Vigências de seguro ativas: {len(vigencias)}")
    for v in vigencias:
        print(f"    - {v.competencia_inicio.strftime('%Y-%m')}: R$ {v.valor_mensal:,.2f} (saldo: R$ {v.saldo_devedor_vigencia:,.2f})")

    # Validações críticas
    print("\n" + "="*80)
    print("VALIDAÇÕES")
    print("="*80)

    sucesso = True

    # 1. Saldo deve ser R$ 250.000 (após amortização de R$ 50.000)
    saldo_esperado = Decimal('250000.00')
    diff = abs(financiamento.saldo_devedor_atual - saldo_esperado)
    if diff > Decimal('0.01'):
        print(f"\n[FALHA] Saldo incorreto!")
        print(f"        Esperado: R$ {saldo_esperado:,.2f}")
        print(f"        Obtido: R$ {financiamento.saldo_devedor_atual:,.2f}")
        sucesso = False
    else:
        print(f"\n[OK] Saldo soberano correto: R$ {financiamento.saldo_devedor_atual:,.2f}")

    # 2. Amortização mensal deve ser reduzida (era 833.33, agora deve ser ~694.44)
    # 250000 / 360 = 694.44
    amort_esperada = Decimal('694.44')
    diff_amort = abs(financiamento.amortizacao_mensal_atual - amort_esperada)
    if diff_amort > Decimal('1.00'):
        print(f"\n[FALHA] Amortização mensal incorreta!")
        print(f"        Esperada: ~R$ {amort_esperada:,.2f}")
        print(f"        Obtida: R$ {financiamento.amortizacao_mensal_atual:,.2f}")
        sucesso = False
    else:
        print(f"[OK] Amortização mensal correta: R$ {financiamento.amortizacao_mensal_atual:,.2f}")

    # 3. Verificar que última vigência tem saldo correto
    if vigencias:
        ultima_vigencia = vigencias[-1]
        if abs(ultima_vigencia.saldo_devedor_vigencia - financiamento.saldo_devedor_atual) > Decimal('0.01'):
            print(f"\n[FALHA] Vigência com saldo incorreto!")
            print(f"        Saldo soberano: R$ {financiamento.saldo_devedor_atual:,.2f}")
            print(f"        Saldo na vigência: R$ {ultima_vigencia.saldo_devedor_vigencia:,.2f}")
            sucesso = False
        else:
            print(f"[OK] Vigência com saldo soberano correto")

    # Resultado final
    print("\n" + "="*80)
    if sucesso:
        print("VALIDAÇÃO: SUCESSO ✅")
        print("="*80)
        print("\nTodos os valores estão corretos!")
        print("- Saldo soberano preservado após amortização e vigência")
        print("- Amortização mensal recalculada corretamente")
        print("- Vigências com saldo soberano correto")
    else:
        print("VALIDAÇÃO: FALHA ❌")
        print("="*80)
        print("\nAlguns valores estão incorretos. Verifique os logs acima.")

    print()
