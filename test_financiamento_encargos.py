"""
Script de teste para validar o sistema de financiamentos com encargos
Testa criação, edição e recálculo de parcelas
"""
import requests
import json
from datetime import date, timedelta

API_BASE = 'http://localhost:5000/api/financiamentos'

def formatar_moeda(valor):
    """Formata valor como moeda BR"""
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def test_criar_financiamento():
    """Teste 1: Criar financiamento com taxa adm e seguro"""
    print("\n" + "="*70)
    print("TESTE 1: Criar financiamento com taxa adm e seguro")
    print("="*70)

    dados = {
        "nome": "Apartamento - Teste Encargos",
        "produto": "SFH",
        "sistema_amortizacao": "SAC",
        "valor_financiado": 300000.00,
        "prazo_total_meses": 360,
        "taxa_juros_nominal_anual": 8.5,
        "data_contrato": "2025-01-01",
        "data_primeira_parcela": "2025-02-01",
        # Seguro variável (percentual sobre saldo)
        "seguro_tipo": "percentual_saldo",
        "seguro_percentual": 0.0006,  # 0,06%
        # Taxa de administração fixa
        "taxa_administracao_fixa": 25.00  # R$ 25/mês
    }

    try:
        response = requests.post(API_BASE, json=dados)
        result = response.json()

        if result.get('success'):
            print("✓ Financiamento criado com sucesso!")
            fin_id = result['data']['id']
            print(f"  ID: {fin_id}")
            print(f"  Nome: {result['data']['nome']}")
            print(f"  Taxa Adm: {formatar_moeda(result['data']['taxa_administracao_fixa'])}")
            print(f"  Seguro: {result['data']['seguro_percentual']*100:.2f}% sobre saldo")

            # Buscar detalhes com parcelas
            det_response = requests.get(f"{API_BASE}/{fin_id}")
            det_result = det_response.json()

            if det_result.get('success'):
                parcelas = det_result['data']['parcelas']
                print(f"\n  Total de parcelas geradas: {len(parcelas)}")

                # Verificar primeiras 3 parcelas
                print("\n  Primeiras 3 parcelas:")
                print(f"  {'Nº':<5} {'Amort.':<12} {'Juros':<12} {'Seguro':<12} {'Taxa Adm':<12} {'Total':<12}")
                print("  " + "-"*70)

                for p in parcelas[:3]:
                    print(f"  {p['numero_parcela']:<5} "
                          f"{formatar_moeda(p['valor_amortizacao']):<12} "
                          f"{formatar_moeda(p['valor_juros']):<12} "
                          f"{formatar_moeda(p['valor_seguro']):<12} "
                          f"{formatar_moeda(p['valor_taxa_adm']):<12} "
                          f"{formatar_moeda(p['valor_previsto_total']):<12}")

                # Validar que seguro e taxa adm não estão zerados
                parcela_1 = parcelas[0]
                if parcela_1['valor_seguro'] > 0 and parcela_1['valor_taxa_adm'] > 0:
                    print("\n  ✓ Seguro e Taxa Administrativa estão sendo aplicados corretamente!")
                    return fin_id
                else:
                    print("\n  ✗ ERRO: Seguro ou Taxa Adm estão zerados!")
                    print(f"    Seguro: {parcela_1['valor_seguro']}")
                    print(f"    Taxa Adm: {parcela_1['valor_taxa_adm']}")
                    return None
            else:
                print(f"  ✗ Erro ao buscar detalhes: {det_result.get('error')}")
                return None
        else:
            print(f"✗ Erro ao criar financiamento: {result.get('error')}")
            return None

    except Exception as e:
        print(f"✗ Exceção: {str(e)}")
        return None

def test_editar_financiamento(fin_id):
    """Teste 2: Editar financiamento e verificar recálculo"""
    print("\n" + "="*70)
    print("TESTE 2: Editar financiamento e verificar recálculo de parcelas")
    print("="*70)

    # Pegar valores antes da edição
    before_response = requests.get(f"{API_BASE}/{fin_id}")
    before_result = before_response.json()
    parcela_antes = before_result['data']['parcelas'][0]

    print("\nAntes da edição:")
    print(f"  Parcela 1 - Seguro: {formatar_moeda(parcela_antes['valor_seguro'])}")
    print(f"  Parcela 1 - Taxa Adm: {formatar_moeda(parcela_antes['valor_taxa_adm'])}")
    print(f"  Parcela 1 - Total: {formatar_moeda(parcela_antes['valor_previsto_total'])}")

    # Editar: aumentar taxa de administração
    dados_edicao = {
        "taxa_administracao_fixa": 50.00  # Dobrar de R$ 25 para R$ 50
    }

    try:
        response = requests.put(f"{API_BASE}/{fin_id}", json=dados_edicao)
        result = response.json()

        if result.get('success'):
            print("\n✓ Financiamento editado com sucesso!")

            # Buscar parcelas atualizadas
            after_response = requests.get(f"{API_BASE}/{fin_id}")
            after_result = after_response.json()
            parcela_depois = after_result['data']['parcelas'][0]

            print("\nDepois da edição:")
            print(f"  Parcela 1 - Seguro: {formatar_moeda(parcela_depois['valor_seguro'])}")
            print(f"  Parcela 1 - Taxa Adm: {formatar_moeda(parcela_depois['valor_taxa_adm'])}")
            print(f"  Parcela 1 - Total: {formatar_moeda(parcela_depois['valor_previsto_total'])}")

            # Validar recálculo
            if parcela_depois['valor_taxa_adm'] == 50.00:
                print("\n  ✓ Taxa de administração foi atualizada corretamente!")
                diferenca_total = parcela_depois['valor_previsto_total'] - parcela_antes['valor_previsto_total']
                print(f"  Diferença no total da parcela: {formatar_moeda(diferenca_total)}")
                if abs(diferenca_total - 25.00) < 0.01:  # Aumentou R$ 25
                    print("  ✓ Recálculo correto!")
                    return True
                else:
                    print(f"  ✗ Diferença esperada: R$ 25,00 | Diferença real: {formatar_moeda(diferenca_total)}")
                    return False
            else:
                print(f"\n  ✗ Taxa de administração não foi atualizada!")
                print(f"    Esperado: R$ 50,00 | Real: {formatar_moeda(parcela_depois['valor_taxa_adm'])}")
                return False
        else:
            print(f"✗ Erro ao editar: {result.get('error')}")
            return False

    except Exception as e:
        print(f"✗ Exceção: {str(e)}")
        return False

def main():
    print("\n" + "="*70)
    print(" TESTES DE FINANCIAMENTO - ENCARGOS E RECÁLCULO")
    print("="*70)
    print("\nVERIFIQUE SE O SERVIDOR ESTÁ RODANDO EM http://localhost:5000")
    input("Pressione ENTER para continuar...")

    # Teste 1: Criar
    fin_id = test_criar_financiamento()

    if fin_id:
        # Teste 2: Editar e recalcular
        sucesso = test_editar_financiamento(fin_id)

        print("\n" + "="*70)
        if sucesso:
            print(" ✓✓✓ TODOS OS TESTES PASSARAM! ✓✓✓")
        else:
            print(" ✗✗✗ ALGUNS TESTES FALHARAM! ✗✗✗")
        print("="*70 + "\n")
    else:
        print("\n" + "="*70)
        print(" ✗✗✗ TESTE DE CRIAÇÃO FALHOU - ABORTANDO ✗✗✗")
        print("="*70 + "\n")

if __name__ == '__main__':
    main()
