"""
TESTE: Validar que GET /api/financiamentos/{id} retorna saldo soberano correto
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import db, Financiamento, FinanciamentoParcela
from backend.services.financiamento_service import FinanciamentoService
from decimal import Decimal
from datetime import date
import json

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("TESTE: API GET retorna saldo soberano correto")
    print("="*80)

    # Buscar financiamento ativo
    financiamento = Financiamento.query.filter_by(ativo=True).first()
    if not financiamento:
        print("\n[ERRO] Nenhum financiamento ativo encontrado!")
        exit(1)

    print(f"\n[1] Financiamento ID={financiamento.id}")
    print(f"    Saldo soberano no banco: R$ {financiamento.saldo_devedor_atual:,.2f}")

    # Simular chamada GET /api/financiamentos/{id}
    from backend.routes.financiamentos import financiamentos_bp

    with app.test_client() as client:
        response = client.get(f'/api/financiamentos/{financiamento.id}')
        data = response.get_json()

        if data['success']:
            saldo_api = data['data']['saldo_devedor_atual']
            print(f"\n[2] GET /api/financiamentos/{financiamento.id}")
            print(f"    Saldo retornado pela API: R$ {saldo_api:,.2f}")

            # Validação
            diff = abs(Decimal(str(saldo_api)) - financiamento.saldo_devedor_atual)

            print("\n" + "="*80)
            if diff < Decimal('0.01'):
                print("TESTE: SUCESSO")
                print("="*80)
                print("\nAPI retorna o saldo soberano correto!")
                print(f"Banco: R$ {financiamento.saldo_devedor_atual:,.2f}")
                print(f"API:   R$ {saldo_api:,.2f}")
            else:
                print("TESTE: FALHA")
                print("="*80)
                print("\nAPI está retornando saldo diferente do banco!")
                print(f"Banco: R$ {financiamento.saldo_devedor_atual:,.2f}")
                print(f"API:   R$ {saldo_api:,.2f}")
                print(f"Diferença: R$ {diff:,.2f}")
        else:
            print(f"\n[ERRO] API retornou erro: {data.get('error')}")

    print()
