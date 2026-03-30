"""
TESTE 1: Inativação remove contas futuras

Cenário:
1. Buscar financiamento ativo com parcelas pendentes
2. Contar quantas contas (despesas) de parcelas pendentes existem
3. Inativar financiamento
4. Verificar que contas pendentes foram removidas
5. Verificar que contas pagas permanecem (histórico imutável)
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import db, Financiamento, FinanciamentoParcela, Conta
from backend.services.financiamento_service import FinanciamentoService

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("TESTE 1: Inativação Remove Contas Futuras")
    print("="*80)

    # Buscar financiamento ativo
    financiamento = Financiamento.query.filter_by(ativo=True).first()
    if not financiamento:
        print("\n[ERRO] Nenhum financiamento ativo encontrado!")
        exit(1)

    print(f"\n[1] Financiamento: {financiamento.nome} (ID={financiamento.id})")
    print(f"    Ativo: {financiamento.ativo}")

    # Contar parcelas
    total_parcelas = FinanciamentoParcela.query.filter_by(
        financiamento_id=financiamento.id
    ).count()

    parcelas_pagas = FinanciamentoParcela.query.filter_by(
        financiamento_id=financiamento.id,
        status='pago'
    ).count()

    parcelas_pendentes = FinanciamentoParcela.query.filter_by(
        financiamento_id=financiamento.id,
        status='pendente'
    ).count()

    print(f"\n[2] Parcelas:")
    print(f"    Total: {total_parcelas}")
    print(f"    Pagas: {parcelas_pagas}")
    print(f"    Pendentes: {parcelas_pendentes}")

    # Contar contas ANTES da inativação
    parcelas_pendentes_ids = [
        p.id for p in FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento.id,
            status='pendente'
        ).all()
    ]

    contas_pendentes_antes = Conta.query.filter(
        Conta.financiamento_parcela_id.in_(parcelas_pendentes_ids)
    ).count() if parcelas_pendentes_ids else 0

    parcelas_pagas_ids = [
        p.id for p in FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento.id,
            status='pago'
        ).all()
    ]

    contas_pagas_antes = Conta.query.filter(
        Conta.financiamento_parcela_id.in_(parcelas_pagas_ids)
    ).count() if parcelas_pagas_ids else 0

    print(f"\n[3] Contas (Despesas) ANTES da inativação:")
    print(f"    Contas de parcelas PENDENTES: {contas_pendentes_antes}")
    print(f"    Contas de parcelas PAGAS: {contas_pagas_antes}")

    # INATIVAR FINANCIAMENTO
    print("\n" + "-"*80)
    print("[4] INATIVANDO FINANCIAMENTO...")
    print("-"*80)

    try:
        FinanciamentoService.inativar_financiamento(financiamento.id)
        print("[OK] Financiamento inativado com sucesso")
    except Exception as e:
        print(f"[ERRO] Falha ao inativar: {e}")
        exit(1)

    # Recarregar do banco
    db.session.refresh(financiamento)

    # Contar contas DEPOIS da inativação
    contas_pendentes_depois = Conta.query.filter(
        Conta.financiamento_parcela_id.in_(parcelas_pendentes_ids)
    ).count() if parcelas_pendentes_ids else 0

    contas_pagas_depois = Conta.query.filter(
        Conta.financiamento_parcela_id.in_(parcelas_pagas_ids)
    ).count() if parcelas_pagas_ids else 0

    print(f"\n[5] Contas (Despesas) DEPOIS da inativação:")
    print(f"    Contas de parcelas PENDENTES: {contas_pendentes_depois}")
    print(f"    Contas de parcelas PAGAS: {contas_pagas_depois}")

    # VALIDAÇÃO
    print("\n" + "="*80)
    print("VALIDAÇÃO")
    print("="*80)

    sucesso = True

    # Verificar que financiamento está inativo
    if financiamento.ativo:
        print("\n[FALHA] Financiamento ainda está ativo!")
        sucesso = False
    else:
        print("\n[OK] Financiamento marcado como inativo")

    # Verificar que contas pendentes foram removidas
    if contas_pendentes_depois > 0:
        print(f"[FALHA] Ainda existem {contas_pendentes_depois} contas pendentes!")
        sucesso = False
    else:
        print(f"[OK] Todas as {contas_pendentes_antes} contas pendentes foram removidas")

    # Verificar que contas pagas permanecem (histórico imutável)
    if contas_pagas_depois != contas_pagas_antes:
        print(f"[FALHA] Contas pagas foram alteradas! Antes: {contas_pagas_antes}, Depois: {contas_pagas_depois}")
        sucesso = False
    else:
        print(f"[OK] Histórico preservado: {contas_pagas_depois} contas pagas permanecem")

    # Resultado final
    print("\n" + "="*80)
    if sucesso:
        print("TESTE 1: SUCESSO")
        print("="*80)
        print("\nInativação funcionou corretamente:")
        print("- Financiamento marcado como inativo")
        print("- Contas futuras (pendentes) removidas")
        print("- Histórico (contas pagas) preservado")
    else:
        print("TESTE 1: FALHA")
        print("="*80)
        print("\nAlgumas validações falharam. Verifique os logs acima.")

    print()
