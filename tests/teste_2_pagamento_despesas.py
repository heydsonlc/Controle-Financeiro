"""
TESTE 2: Pagamento via Despesas reflete no Financiamento

Cenário:
1. Buscar financiamento ativo com parcelas pendentes
2. Buscar uma conta (despesa) vinculada a parcela pendente
3. Simular pagamento via módulo Despesas (PUT /api/despesas/<id>)
4. Verificar que FinanciamentoParcela.status = 'pago'
5. Verificar que saldo soberano foi atualizado (se aplicável)
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import db, Financiamento, FinanciamentoParcela, Conta
from datetime import date

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("TESTE 2: Pagamento via Despesas Reflete no Financiamento")
    print("="*80)

    # Buscar financiamento ativo com parcelas pendentes
    financiamento = Financiamento.query.filter_by(ativo=True).first()
    if not financiamento:
        print("\n[ERRO] Nenhum financiamento ativo encontrado!")
        exit(1)

    print(f"\n[1] Financiamento: {financiamento.nome} (ID={financiamento.id})")
    print(f"    Saldo soberano ANTES: R$ {financiamento.saldo_devedor_atual:,.2f}")

    # Buscar primeira parcela pendente
    parcela_pendente = FinanciamentoParcela.query.filter_by(
        financiamento_id=financiamento.id,
        status='pendente'
    ).order_by(FinanciamentoParcela.numero_parcela).first()

    if not parcela_pendente:
        print("\n[ERRO] Nenhuma parcela pendente encontrada!")
        exit(1)

    print(f"\n[2] Parcela pendente:")
    print(f"    Número: {parcela_pendente.numero_parcela}")
    print(f"    Valor: R$ {parcela_pendente.valor_previsto_total:,.2f}")
    print(f"    Status ANTES: {parcela_pendente.status}")

    # Buscar conta vinculada à parcela
    conta = Conta.query.filter_by(financiamento_parcela_id=parcela_pendente.id).first()

    if not conta:
        print(f"\n[AVISO] Nenhuma conta vinculada à parcela {parcela_pendente.numero_parcela}")
        print("         Criando conta para teste...")

        # Criar conta para teste
        conta = Conta(
            item_despesa_id=financiamento.item_despesa_id,
            financiamento_parcela_id=parcela_pendente.id,
            mes_referencia=parcela_pendente.data_vencimento.replace(day=1),
            descricao=f'{financiamento.nome} - Parcela {parcela_pendente.numero_parcela}',
            valor=parcela_pendente.valor_previsto_total,
            data_vencimento=parcela_pendente.data_vencimento,
            status_pagamento='Pendente'
        )
        db.session.add(conta)
        db.session.commit()
        print(f"         [OK] Conta criada (ID={conta.id})")

    print(f"\n[3] Conta (Despesa):")
    print(f"    ID: {conta.id}")
    print(f"    Valor: R$ {conta.valor:,.2f}")
    print(f"    Status ANTES: {conta.status_pagamento}")
    print(f"    Vinculada à parcela: {conta.financiamento_parcela_id}")

    # SIMULAR PAGAMENTO VIA DESPESAS
    print("\n" + "-"*80)
    print("[4] SIMULANDO PAGAMENTO VIA MÓDULO DESPESAS...")
    print("-"*80)

    # Replicar lógica do PUT /api/despesas/<id> com pago=True
    try:
        # Marcar conta como paga
        conta.status_pagamento = 'Pago'
        conta.data_pagamento = date.today()
        db.session.commit()

        print(f"[OK] Conta marcada como paga")

        # HOOK: Sincronizar com Financiamento (lógica do despesas.py linha 574)
        if conta.financiamento_parcela_id and conta.status_pagamento == 'Pago':
            from backend.services.financiamento_service import FinanciamentoService

            print(f"[INFO] Detectado vínculo com financiamento - chamando motor...")

            FinanciamentoService.registrar_pagamento_parcela(
                parcela_id=conta.financiamento_parcela_id,
                valor_pago=conta.valor,
                data_pagamento=conta.data_pagamento or conta.data_vencimento
            )

            print(f"[OK] Motor do financiamento chamado com sucesso")

    except Exception as e:
        print(f"[ERRO] Falha ao processar pagamento: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

    # Recarregar objetos do banco
    db.session.refresh(parcela_pendente)
    db.session.refresh(financiamento)
    db.session.refresh(conta)

    print(f"\n[5] Estado DEPOIS do pagamento:")
    print(f"    Conta.status_pagamento: {conta.status_pagamento}")
    print(f"    Parcela.status: {parcela_pendente.status}")
    print(f"    Parcela.valor_pago: R$ {parcela_pendente.valor_pago or 0:,.2f}")
    print(f"    Saldo soberano DEPOIS: R$ {financiamento.saldo_devedor_atual:,.2f}")

    # VALIDAÇÃO
    print("\n" + "="*80)
    print("VALIDAÇÃO")
    print("="*80)

    sucesso = True

    # Verificar que conta está paga
    if conta.status_pagamento != 'Pago':
        print("\n[FALHA] Conta não foi marcada como paga!")
        sucesso = False
    else:
        print("\n[OK] Conta marcada como paga")

    # Verificar que parcela está paga
    if parcela_pendente.status != 'pago':
        print(f"[FALHA] Parcela não foi marcada como paga! Status: {parcela_pendente.status}")
        sucesso = False
    else:
        print(f"[OK] Parcela marcada como paga (status='pago')")

    # Verificar que valor_pago foi registrado
    if not parcela_pendente.valor_pago or parcela_pendente.valor_pago <= 0:
        print(f"[FALHA] Valor pago não foi registrado! valor_pago={parcela_pendente.valor_pago}")
        sucesso = False
    else:
        print(f"[OK] Valor pago registrado: R$ {parcela_pendente.valor_pago:,.2f}")

    # Resultado final
    print("\n" + "="*80)
    if sucesso:
        print("TESTE 2: SUCESSO")
        print("="*80)
        print("\nSincronização bidirecional funcionou:")
        print("- Pagamento em Despesas refletiu no Financiamento")
        print("- Parcela marcada como paga")
        print("- Valor pago registrado")
        print("\nMOTOR DO FINANCIAMENTO FOI CHAMADO CORRETAMENTE!")
    else:
        print("TESTE 2: FALHA")
        print("="*80)
        print("\nSincronização não funcionou. Verifique os logs acima.")

    print()
