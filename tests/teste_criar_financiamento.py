"""
TESTE: Criar financiamento para validar correção
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import db
from datetime import date

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("TESTE: Criar Financiamento")
    print("="*80)

    dados = {
        'nome': 'Financiamento Teste',
        'produto': 'Imóvel',
        'sistema_amortizacao': 'SAC',
        'valor_financiado': 300000.00,
        'prazo_total_meses': 360,
        'taxa_juros_nominal_anual': 8.5,
        'data_contrato': '2024-05-01',
        'data_primeira_parcela': '2024-06-01',
        'vigencias_seguro': [
            {
                'competencia_inicio': '2024-05-01',  # Formato YYYY-MM-DD (como frontend envia)
                'valor_mensal': 200.00,
                'observacoes': 'Vigência inicial'
            }
        ]
    }

    try:
        from backend.services.financiamento_service import FinanciamentoService

        print(f"\n[1] Tentando criar financiamento: {dados['nome']}")
        print(f"    Valor financiado: R$ {dados['valor_financiado']:,.2f}")
        print(f"    Prazo: {dados['prazo_total_meses']} meses")
        print(f"    Vigência seguro: {dados['vigencias_seguro'][0]['competencia_inicio']}")

        financiamento = FinanciamentoService.criar_financiamento(dados)

        print(f"\n[2] ✅ Financiamento criado com sucesso!")
        print(f"    ID: {financiamento.id}")
        print(f"    Nome: {financiamento.nome}")
        print(f"    Saldo soberano: R$ {financiamento.saldo_devedor_atual:,.2f}")
        print(f"    Ativo: {financiamento.ativo}")

        # Contar parcelas geradas
        from backend.models import FinanciamentoParcela
        parcelas = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento.id
        ).count()

        print(f"\n[3] Parcelas geradas: {parcelas}")

        print("\n" + "="*80)
        print("TESTE: SUCESSO")
        print("="*80)
        print("\nA correção do date parsing funcionou!")
        print("Agora você pode criar financiamentos pelo frontend.")

    except Exception as e:
        print(f"\n[ERRO] Falha ao criar financiamento: {e}")
        import traceback
        traceback.print_exc()

        print("\n" + "="*80)
        print("TESTE: FALHA")
        print("="*80)

    print()
