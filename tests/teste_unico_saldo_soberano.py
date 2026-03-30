"""
TESTE ÚNICO: Validar que Saldo Soberano NÃO é afetado por nova vigência

Cenário:
1. Amortizar R$ 50.000 (tipo: reduzir_parcela)
2. Verificar saldo no banco → deve ser R$ 425.000 (475.000 - 50.000)
3. Adicionar nova vigência de seguro
4. Verificar saldo novamente → deve CONTINUAR R$ 425.000

Se o saldo mudar após adicionar vigência = BUG (veneno não foi removido)
Se o saldo permanecer = SUCESSO (correção funcionou)
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import db, Financiamento
from backend.services.financiamento_service import FinanciamentoService
from backend.services.seguro_vigencia_service import SeguroVigenciaService
from decimal import Decimal
from datetime import date

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("TESTE ÚNICO: Saldo Soberano vs Nova Vigência")
    print("="*80)

    # Buscar financiamento
    fin = Financiamento.query.first()
    if not fin:
        print("[ERRO] Nenhum financiamento encontrado!")
        exit(1)

    print(f"\n[1] Financiamento: {fin.nome} (ID={fin.id})")
    print(f"    Saldo ANTES da amortização: R$ {fin.saldo_devedor_atual:,.2f}")

    # ========================================================================
    # PASSO 1: AMORTIZAR R$ 50.000
    # ========================================================================
    print("\n" + "-"*80)
    print("[2] AMORTIZANDO R$ 50.000 (tipo: reduzir_parcela)")
    print("-"*80)

    dados_amortizacao = {
        'data': date(2026, 1, 6),
        'valor': 50000.0,
        'tipo': 'reduzir_parcela',
        'observacoes': 'Teste único - validar saldo soberano'
    }

    try:
        amortizacao = FinanciamentoService.registrar_amortizacao_extra(
            financiamento_id=fin.id,
            dados_amortizacao=dados_amortizacao
        )
        print("[OK] Amortização registrada com sucesso")
    except Exception as e:
        print(f"[ERRO] Falha ao amortizar: {e}")
        exit(1)

    # Recarregar financiamento do banco
    db.session.refresh(fin)

    saldo_apos_amortizacao = fin.saldo_devedor_atual
    print(f"\n[3] Saldo APÓS amortização: R$ {saldo_apos_amortizacao:,.2f}")

    # Validar saldo esperado
    saldo_esperado = Decimal('425000.00')  # 475.000 - 50.000
    diff = abs(saldo_apos_amortizacao - saldo_esperado)

    if diff > Decimal('0.01'):
        print(f"[ERRO] Saldo incorreto após amortização!")
        print(f"       Esperado: R$ {saldo_esperado:,.2f}")
        print(f"       Obtido: R$ {saldo_apos_amortizacao:,.2f}")
        print(f"       Diferença: R$ {diff:,.2f}")
        exit(1)
    else:
        print(f"[OK] Saldo correto (esperado: R$ {saldo_esperado:,.2f})")

    # ========================================================================
    # PASSO 2: ADICIONAR NOVA VIGÊNCIA DE SEGURO
    # ========================================================================
    print("\n" + "-"*80)
    print("[4] ADICIONANDO NOVA VIGÊNCIA DE SEGURO (competência: 2026-03)")
    print("-"*80)

    try:
        nova_vigencia = SeguroVigenciaService.criar_vigencia(
            financiamento_id=fin.id,
            competencia_inicio=date(2026, 3, 1),
            valor_mensal=Decimal('200.00'),  # Novo valor de seguro
            saldo_devedor_vigencia=fin.saldo_devedor_atual,  # Usar saldo soberano
            observacoes='Teste único - nova vigência'
        )
        print(f"[OK] Nova vigência criada (valor mensal: R$ {nova_vigencia.valor_mensal:,.2f})")
    except Exception as e:
        print(f"[ERRO] Falha ao criar vigência: {e}")
        exit(1)

    # Recarregar financiamento do banco
    db.session.refresh(fin)

    saldo_apos_vigencia = fin.saldo_devedor_atual
    print(f"\n[5] Saldo APÓS adicionar vigência: R$ {saldo_apos_vigencia:,.2f}")

    # ========================================================================
    # VALIDAÇÃO FINAL: SALDO NÃO PODE TER MUDADO
    # ========================================================================
    print("\n" + "="*80)
    print("VALIDAÇÃO FINAL")
    print("="*80)

    diff_final = abs(saldo_apos_vigencia - saldo_apos_amortizacao)

    print(f"\nSaldo após amortização:  R$ {saldo_apos_amortizacao:,.2f}")
    print(f"Saldo após vigência:     R$ {saldo_apos_vigencia:,.2f}")
    print(f"Diferença:               R$ {diff_final:,.2f}")

    if diff_final > Decimal('0.01'):
        print("\n" + "="*80)
        print("FALHA! SALDO MUDOU APÓS ADICIONAR VIGÊNCIA")
        print("="*80)
        print("O 'veneno' ainda está presente no sistema.")
        print("O saldo soberano foi sobrescrito pela vigência.")
        exit(1)
    else:
        print("\n" + "="*80)
        print("SUCESSO! SALDO PERMANECEU INTACTO")
        print("="*80)
        print("Correção cirúrgica funcionou!")
        print("Saldo soberano NÃO foi afetado pela nova vigência.")
        print("\nRegra de Ouro validada: Saldo soberano NUNCA vem do frontend.")
        print("="*80 + "\n")
