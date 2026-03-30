"""
TESTE 4: Vigência após Amortização (BUG PRINCIPAL)

Cenário (teste definitivo):
1. Amortizar R$ 50.000 (tipo: reduzir_parcela)
2. Verificar saldo soberano no banco → deve reduzir
3. Verificar valor das parcelas → deve reduzir
4. Adicionar nova vigência de seguro via endpoint correto
5. Verificar que:
   - Saldo soberano NÃO mudou
   - Amortização NÃO mudou
   - Juros NÃO mudaram
   - Apenas valor_seguro mudou

Se saldo/amortização/juros mudarem = BUG ainda existe
Se apenas seguro mudar = SUCESSO (correção funcionou)
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import db, Financiamento, FinanciamentoParcela
from backend.services.financiamento_service import FinanciamentoService
from backend.services.seguro_vigencia_service import SeguroVigenciaService
from decimal import Decimal
from datetime import date

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("TESTE 4: Vigência após Amortização (BUG PRINCIPAL)")
    print("="*80)

    # Buscar financiamento ativo
    financiamento = Financiamento.query.filter_by(ativo=True).first()
    if not financiamento:
        print("\n[ERRO] Nenhum financiamento ativo encontrado!")
        exit(1)

    print(f"\n[1] Financiamento: {financiamento.nome} (ID={financiamento.id})")
    print(f"    Saldo ANTES da amortização: R$ {financiamento.saldo_devedor_atual:,.2f}")

    # Buscar primeira parcela pendente para referência
    parcela_ref_antes = FinanciamentoParcela.query.filter_by(
        financiamento_id=financiamento.id,
        status='pendente'
    ).order_by(FinanciamentoParcela.numero_parcela).first()

    if not parcela_ref_antes:
        print("\n[ERRO] Nenhuma parcela pendente encontrada!")
        exit(1)

    print(f"\n[2] Parcela de referência ANTES da amortização:")
    print(f"    Número: {parcela_ref_antes.numero_parcela}")
    print(f"    Amortização: R$ {parcela_ref_antes.valor_amortizacao:,.2f}")
    print(f"    Juros: R$ {parcela_ref_antes.valor_juros:,.2f}")
    print(f"    Seguro: R$ {parcela_ref_antes.valor_seguro:,.2f}")
    print(f"    Total: R$ {parcela_ref_antes.valor_previsto_total:,.2f}")

    # ========================================================================
    # PASSO 1: AMORTIZAR R$ 50.000
    # ========================================================================
    print("\n" + "-"*80)
    print("[3] AMORTIZANDO R$ 50.000 (tipo: reduzir_parcela)")
    print("-"*80)

    valor_amortizacao = Decimal('50000.00')
    saldo_antes_amortizacao = financiamento.saldo_devedor_atual

    dados_amortizacao = {
        'data': date.today(),
        'valor': float(valor_amortizacao),
        'tipo': 'reduzir_parcela',
        'observacoes': 'Teste 4 - validar vigência não afeta estrutura'
    }

    try:
        FinanciamentoService.registrar_amortizacao_extra(
            financiamento_id=financiamento.id,
            dados_amortizacao=dados_amortizacao
        )
        print("[OK] Amortização registrada com sucesso")
    except Exception as e:
        print(f"[ERRO] Falha ao amortizar: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

    # Recarregar do banco
    db.session.refresh(financiamento)

    saldo_apos_amortizacao = financiamento.saldo_devedor_atual
    print(f"\n[4] Saldo APÓS amortização: R$ {saldo_apos_amortizacao:,.2f}")

    # Validar que saldo reduziu
    saldo_esperado = saldo_antes_amortizacao - valor_amortizacao
    diff_saldo = abs(saldo_apos_amortizacao - saldo_esperado)

    if diff_saldo > Decimal('0.01'):
        print(f"[ERRO] Saldo incorreto após amortização!")
        print(f"       Esperado: R$ {saldo_esperado:,.2f}")
        print(f"       Obtido: R$ {saldo_apos_amortizacao:,.2f}")
        exit(1)
    else:
        print(f"[OK] Saldo correto (redução de R$ {valor_amortizacao:,.2f})")

    # Buscar mesma parcela após amortização
    parcela_ref_apos_amort = FinanciamentoParcela.query.filter_by(
        financiamento_id=financiamento.id,
        numero_parcela=parcela_ref_antes.numero_parcela,
        status='pendente'
    ).first()

    print(f"\n[5] Parcela #{parcela_ref_apos_amort.numero_parcela} APÓS amortização:")
    print(f"    Amortização: R$ {parcela_ref_apos_amort.valor_amortizacao:,.2f}")
    print(f"    Juros: R$ {parcela_ref_apos_amort.valor_juros:,.2f}")
    print(f"    Seguro: R$ {parcela_ref_apos_amort.valor_seguro:,.2f}")
    print(f"    Total: R$ {parcela_ref_apos_amort.valor_previsto_total:,.2f}")

    # Armazenar valores para comparação depois da vigência
    amort_apos_amortizacao = parcela_ref_apos_amort.valor_amortizacao
    juros_apos_amortizacao = parcela_ref_apos_amort.valor_juros
    seguro_apos_amortizacao = parcela_ref_apos_amort.valor_seguro

    # ========================================================================
    # PASSO 2: ADICIONAR NOVA VIGÊNCIA (via endpoint correto)
    # ========================================================================
    print("\n" + "-"*80)
    print("[6] ADICIONANDO NOVA VIGÊNCIA via endpoint correto")
    print("-"*80)

    # Determinar competência futura
    from dateutil.relativedelta import relativedelta
    competencia_vigencia = date.today() + relativedelta(months=2)
    competencia_vigencia = competencia_vigencia.replace(day=1)

    print(f"    Competência: {competencia_vigencia.strftime('%Y-%m')}")
    print(f"    Novo valor seguro: R$ 250,00")

    try:
        # Usar SEMPRE o saldo soberano (NUNCA vindo do frontend)
        nova_vigencia = SeguroVigenciaService.criar_vigencia(
            financiamento_id=financiamento.id,
            competencia_inicio=competencia_vigencia,
            valor_mensal=Decimal('250.00'),
            saldo_devedor_vigencia=financiamento.saldo_devedor_atual,  # SOBERANO
            observacoes='Teste 4 - nova vigência'
        )
        print(f"[OK] Vigência criada (ID={nova_vigencia.id})")

        # Recalcular SEGURO-ONLY
        parcelas_atualizadas = FinanciamentoService.recalcular_seguro_parcelas_futuras(
            financiamento_id=financiamento.id,
            a_partir_de=competencia_vigencia
        )
        print(f"[OK] Recálculo seguro-only: {parcelas_atualizadas} parcelas atualizadas")

    except Exception as e:
        print(f"[ERRO] Falha ao criar vigência: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

    # Recarregar do banco
    db.session.refresh(financiamento)
    db.session.refresh(parcela_ref_apos_amort)

    saldo_apos_vigencia = financiamento.saldo_devedor_atual

    print(f"\n[7] Estado APÓS adicionar vigência:")
    print(f"    Saldo soberano: R$ {saldo_apos_vigencia:,.2f}")

    print(f"\n[8] Parcela #{parcela_ref_apos_amort.numero_parcela} APÓS vigência:")
    print(f"    Amortização: R$ {parcela_ref_apos_amort.valor_amortizacao:,.2f}")
    print(f"    Juros: R$ {parcela_ref_apos_amort.valor_juros:,.2f}")
    print(f"    Seguro: R$ {parcela_ref_apos_amort.valor_seguro:,.2f}")
    print(f"    Total: R$ {parcela_ref_apos_amort.valor_previsto_total:,.2f}")

    # ========================================================================
    # VALIDAÇÃO CRÍTICA
    # ========================================================================
    print("\n" + "="*80)
    print("VALIDAÇÃO CRÍTICA")
    print("="*80)

    sucesso = True

    # 1. Saldo soberano NÃO pode ter mudado
    diff_saldo_final = abs(saldo_apos_vigencia - saldo_apos_amortizacao)
    if diff_saldo_final > Decimal('0.01'):
        print(f"\n[FALHA] SALDO MUDOU após adicionar vigência!")
        print(f"        Após amortização: R$ {saldo_apos_amortizacao:,.2f}")
        print(f"        Após vigência: R$ {saldo_apos_vigencia:,.2f}")
        print(f"        Diferença: R$ {diff_saldo_final:,.2f}")
        print("\n        O 'VENENO' AINDA ESTÁ PRESENTE!")
        sucesso = False
    else:
        print(f"\n[OK] Saldo soberano permaneceu intacto: R$ {saldo_apos_vigencia:,.2f}")

    # 2. Amortização NÃO pode ter mudado
    diff_amort = abs(parcela_ref_apos_amort.valor_amortizacao - amort_apos_amortizacao)
    if diff_amort > Decimal('0.01'):
        print(f"\n[FALHA] AMORTIZAÇÃO mudou após vigência!")
        print(f"        Antes: R$ {amort_apos_amortizacao:,.2f}")
        print(f"        Depois: R$ {parcela_ref_apos_amort.valor_amortizacao:,.2f}")
        sucesso = False
    else:
        print(f"[OK] Amortização não mudou: R$ {parcela_ref_apos_amort.valor_amortizacao:,.2f}")

    # 3. Juros NÃO podem ter mudado
    diff_juros = abs(parcela_ref_apos_amort.valor_juros - juros_apos_amortizacao)
    if diff_juros > Decimal('0.01'):
        print(f"\n[FALHA] JUROS mudaram após vigência!")
        print(f"        Antes: R$ {juros_apos_amortizacao:,.2f}")
        print(f"        Depois: R$ {parcela_ref_apos_amort.valor_juros:,.2f}")
        sucesso = False
    else:
        print(f"[OK] Juros não mudaram: R$ {parcela_ref_apos_amort.valor_juros:,.2f}")

    # 4. Seguro PODE ter mudado (normal, se parcela está em nova vigência)
    # Vamos apenas reportar, não é critério de falha
    diff_seguro = abs(parcela_ref_apos_amort.valor_seguro - seguro_apos_amortizacao)
    if diff_seguro > Decimal('0.01'):
        print(f"[INFO] Seguro mudou (esperado se parcela está na nova vigência):")
        print(f"       Antes: R$ {seguro_apos_amortizacao:,.2f}")
        print(f"       Depois: R$ {parcela_ref_apos_amort.valor_seguro:,.2f}")
    else:
        print(f"[INFO] Seguro não mudou: R$ {parcela_ref_apos_amort.valor_seguro:,.2f}")

    # Resultado final
    print("\n" + "="*80)
    if sucesso:
        print("TESTE 4: SUCESSO")
        print("="*80)
        print("\nCORREÇÃO FUNCIONOU PERFEITAMENTE!")
        print("\nRegra de Ouro validada:")
        print("- Saldo soberano NÃO foi afetado pela vigência")
        print("- Amortização permaneceu inalterada")
        print("- Juros permaneceram inalterados")
        print("- Apenas seguro foi recalculado (se aplicável)")
        print("\nO 'VENENO' foi removido com sucesso!")
    else:
        print("TESTE 4: FALHA")
        print("="*80)
        print("\nO BUG AINDA EXISTE!")
        print("Vigência alterou valores estruturais (saldo/amortização/juros).")
        print("Verifique se o endpoint correto foi usado e se saldo_devedor_vigencia")
        print("não está vindo do frontend.")

    print()
