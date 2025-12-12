"""
Script de teste para validar o sistema de faturas virtuais de cartão de crédito
Testa orçamento, criação de faturas, consumo de orçamento, pagamento e alertas
"""
import requests
import json
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

API_BASE_CARTOES = 'http://localhost:5000/api/cartoes'
API_BASE_DESPESAS = 'http://localhost:5000/api/despesas'

def formatar_moeda(valor):
    """Formata valor como moeda BR"""
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def test_criar_cartao_com_orcamentos():
    """Teste 1: Criar cartão com orçamentos por categoria"""
    print("\n" + "="*80)
    print("TESTE 1: Criar cartão com orçamentos por categoria")
    print("="*80)

    # Criar cartão de crédito
    dados_cartao = {
        "nome": "Nubank - Teste Virtual Invoice",
        "tipo": "Agregador",
        "categoria_id": 1,  # Ajustar conforme sua base
        "dia_fechamento": 15,
        "dia_vencimento": 25,
        "limite_total": 5000.00
    }

    try:
        response = requests.post(API_BASE_CARTOES, json=dados_cartao)
        result = response.json()

        if not result.get('success'):
            print(f"✗ Erro ao criar cartão: {result.get('error')}")
            return None

        cartao_id = result['data']['id']
        print(f"✓ Cartão criado com sucesso! ID: {cartao_id}")
        print(f"  Nome: {result['data']['nome']}")

        # Criar 3 categorias de orçamento
        categorias_orcamento = [
            {"nome": "Alimentação", "valor_teto": 1500.00},
            {"nome": "Transporte", "valor_teto": 800.00},
            {"nome": "Lazer", "valor_teto": 500.00}
        ]

        itens_agregados = []

        for cat in categorias_orcamento:
            # Criar item agregado (categoria do cartão)
            dados_item = {
                "nome": cat["nome"],
                "valor_teto": cat["valor_teto"]
            }

            resp_item = requests.post(f"{API_BASE_CARTOES}/{cartao_id}/itens", json=dados_item)
            res_item = resp_item.json()

            if res_item.get('success'):
                item_id = res_item['data']['id']
                itens_agregados.append(item_id)
                print(f"  ✓ Categoria '{cat['nome']}' criada - Orçamento: {formatar_moeda(cat['valor_teto'])}")

        print(f"\n  Total orçado: {formatar_moeda(sum([c['valor_teto'] for c in categorias_orcamento]))}")

        return {
            'cartao_id': cartao_id,
            'itens_agregados': itens_agregados,
            'orcamento_total': sum([c['valor_teto'] for c in categorias_orcamento])
        }

    except Exception as e:
        print(f"✗ Exceção: {str(e)}")
        return None


def test_adicionar_lancamentos(cartao_info):
    """Teste 2: Adicionar lançamentos e verificar criação automática de fatura"""
    print("\n" + "="*80)
    print("TESTE 2: Adicionar lançamentos e verificar criação automática de fatura")
    print("="*80)

    if not cartao_info:
        print("✗ Cartão não foi criado no teste anterior")
        return None

    cartao_id = cartao_info['cartao_id']
    itens_agregados = cartao_info['itens_agregados']

    # Mês de fatura: próximo mês
    hoje = date.today()
    mes_fatura = (hoje + relativedelta(months=1)).replace(day=1)

    print(f"\nCompetência da fatura: {mes_fatura.strftime('%m/%Y')}")

    # Criar 5 lançamentos distribuídos nas categorias
    lancamentos = [
        {"item_agregado_id": itens_agregados[0], "descricao": "Supermercado XYZ", "valor": 450.00},
        {"item_agregado_id": itens_agregados[0], "descricao": "Padaria ABC", "valor": 120.00},
        {"item_agregado_id": itens_agregados[1], "descricao": "Uber", "valor": 65.00},
        {"item_agregado_id": itens_agregados[1], "descricao": "Gasolina", "valor": 200.00},
        {"item_agregado_id": itens_agregados[2], "descricao": "Cinema", "valor": 80.00}
    ]

    total_gasto = sum([l['valor'] for l in lancamentos])

    print(f"\nAdicionando {len(lancamentos)} lançamentos:")

    for lanc in lancamentos:
        dados_lancamento = {
            "item_agregado_id": lanc['item_agregado_id'],
            "descricao": lanc['descricao'],
            "valor": lanc['valor'],
            "data_compra": hoje.isoformat(),
            "mes_fatura": mes_fatura.isoformat(),
            "categoria_id": 1  # Categoria real da despesa
        }

        try:
            idx = itens_agregados.index(lanc['item_agregado_id'])
            resp = requests.post(
                f"{API_BASE_CARTOES}/itens/{lanc['item_agregado_id']}/lancamentos",
                json=dados_lancamento
            )
            result = resp.json()

            if result.get('success'):
                print(f"  ✓ {lanc['descricao']}: {formatar_moeda(lanc['valor'])}")
            else:
                print(f"  ✗ Erro ao criar lançamento: {result.get('error')}")
        except Exception as e:
            print(f"  ✗ Exceção ao criar lançamento: {str(e)}")

    print(f"\n  Total gasto: {formatar_moeda(total_gasto)}")
    print(f"  Orçamento total: {formatar_moeda(cartao_info['orcamento_total'])}")

    # Buscar fatura gerada automaticamente
    print("\nVerificando se fatura foi criada automaticamente...")

    try:
        # Listar todas as despesas e procurar pela fatura
        resp_despesas = requests.get(API_BASE_DESPESAS)
        result_despesas = resp_despesas.json()

        if result_despesas.get('success'):
            faturas = [
                d for d in result_despesas['data']
                if d.get('is_fatura_cartao') and d.get('cartao_id') == cartao_id
            ]

            if faturas:
                fatura = faturas[0]
                print(f"  ✓ Fatura encontrada! ID: {fatura['id']}")
                print(f"    Valor Planejado: {formatar_moeda(fatura['valor_planejado'])}")
                print(f"    Valor Executado: {formatar_moeda(fatura['valor_executado'])}")
                print(f"    Valor Exibido: {formatar_moeda(fatura['valor'])} (mostra planejado pois está pendente)")
                print(f"    Status: {fatura['status_pagamento']}")
                print(f"    Estouro: {'SIM' if fatura['estouro_orcamento'] else 'NÃO'}")

                # Validar valores
                if abs(fatura['valor_planejado'] - cartao_info['orcamento_total']) < 0.01:
                    print(f"\n  ✓ Valor planejado correto!")
                else:
                    print(f"\n  ✗ Valor planejado incorreto! Esperado: {formatar_moeda(cartao_info['orcamento_total'])}")

                if abs(fatura['valor_executado'] - total_gasto) < 0.01:
                    print(f"  ✓ Valor executado correto!")
                else:
                    print(f"  ✗ Valor executado incorreto! Esperado: {formatar_moeda(total_gasto)}")

                return fatura['id']
            else:
                print("  ✗ Fatura não encontrada!")
                return None
        else:
            print(f"  ✗ Erro ao listar despesas: {result_despesas.get('error')}")
            return None

    except Exception as e:
        print(f"  ✗ Exceção ao buscar fatura: {str(e)}")
        return None


def test_pagar_fatura(fatura_id, orcamento_total, total_gasto):
    """Teste 3: Pagar fatura e verificar substituição planejado → executado"""
    print("\n" + "="*80)
    print("TESTE 3: Pagar fatura e verificar substituição planejado → executado")
    print("="*80)

    if not fatura_id:
        print("✗ Fatura não foi encontrada no teste anterior")
        return False

    # Buscar fatura antes do pagamento
    try:
        resp_antes = requests.get(f"{API_BASE_DESPESAS}/{fatura_id}")
        result_antes = resp_antes.json()

        if not result_antes.get('success'):
            print(f"✗ Erro ao buscar fatura: {result_antes.get('error')}")
            return False

        fatura_antes = result_antes['data']

        print(f"\nAntes do pagamento:")
        print(f"  Valor exibido: {formatar_moeda(fatura_antes['valor'])} (planejado)")
        print(f"  Status: {fatura_antes['status_pagamento']}")

        # Pagar fatura
        dados_pagamento = {
            "data_pagamento": date.today().isoformat()
        }

        resp_pagar = requests.post(f"{API_BASE_DESPESAS}/{fatura_id}/pagar", json=dados_pagamento)
        result_pagar = resp_pagar.json()

        if not result_pagar.get('success'):
            print(f"\n✗ Erro ao pagar fatura: {result_pagar.get('error')}")
            return False

        print(f"\n✓ Fatura paga com sucesso!")

        # Buscar fatura depois do pagamento
        resp_depois = requests.get(f"{API_BASE_DESPESAS}/{fatura_id}")
        result_depois = resp_depois.json()

        if not result_depois.get('success'):
            print(f"✗ Erro ao buscar fatura após pagamento: {result_depois.get('error')}")
            return False

        fatura_depois = result_depois['data']

        print(f"\nDepois do pagamento:")
        print(f"  Valor exibido: {formatar_moeda(fatura_depois['valor'])} (executado)")
        print(f"  Status: {fatura_depois['status_pagamento']}")
        print(f"  Data pagamento: {fatura_depois.get('data_pagamento', 'N/A')}")

        # Validar mudança de planejado para executado
        if fatura_depois['status_pagamento'] == 'Pago':
            print(f"\n  ✓ Status atualizado para 'Pago'!")
        else:
            print(f"\n  ✗ Status não foi atualizado! Status: {fatura_depois['status_pagamento']}")
            return False

        # Verificar se o valor mudou de planejado para executado
        if abs(fatura_antes['valor'] - orcamento_total) < 0.01 and abs(fatura_depois['valor'] - total_gasto) < 0.01:
            print(f"  ✓ Valor substituído corretamente!")
            print(f"    Antes (planejado): {formatar_moeda(fatura_antes['valor'])}")
            print(f"    Depois (executado): {formatar_moeda(fatura_depois['valor'])}")
            return True
        else:
            print(f"  ✗ Valor não foi substituído corretamente!")
            print(f"    Esperado antes: {formatar_moeda(orcamento_total)}")
            print(f"    Real antes: {formatar_moeda(fatura_antes['valor'])}")
            print(f"    Esperado depois: {formatar_moeda(total_gasto)}")
            print(f"    Real depois: {formatar_moeda(fatura_depois['valor'])}")
            return False

    except Exception as e:
        print(f"✗ Exceção: {str(e)}")
        return False


def test_estouro_orcamento(cartao_info):
    """Teste 4: Verificar detecção de estouro de orçamento"""
    print("\n" + "="*80)
    print("TESTE 4: Verificar detecção de estouro de orçamento")
    print("="*80)

    if not cartao_info:
        print("✗ Cartão não foi criado")
        return False

    cartao_id = cartao_info['cartao_id']
    itens_agregados = cartao_info['itens_agregados']

    # Criar lançamento que estoura orçamento
    # Categoria 0 (Alimentação) tem orçamento de R$ 1500
    # Vamos adicionar R$ 2000

    hoje = date.today()
    mes_fatura_futuro = (hoje + relativedelta(months=2)).replace(day=1)

    print(f"\nAdicionando lançamento que estoura orçamento da categoria Alimentação...")
    print(f"  Orçamento: R$ 1.500,00")
    print(f"  Lançamento: R$ 2.000,00")

    dados_lancamento = {
        "item_agregado_id": itens_agregados[0],  # Alimentação
        "descricao": "Compra grande - ESTOURO",
        "valor": 2000.00,
        "data_compra": hoje.isoformat(),
        "mes_fatura": mes_fatura_futuro.isoformat(),
        "categoria_id": 1
    }

    try:
        resp = requests.post(
            f"{API_BASE_CARTOES}/itens/{itens_agregados[0]}/lancamentos",
            json=dados_lancamento
        )
        result = resp.json()

        if not result.get('success'):
            print(f"  ✗ Erro ao criar lançamento: {result.get('error')}")
            return False

        print(f"  ✓ Lançamento criado!")

        # Verificar se fatura tem flag de estouro
        fatura_info = result.get('fatura', {})

        if fatura_info.get('estouro_orcamento'):
            print(f"\n  ✓ Estouro detectado corretamente!")
            print(f"    Planejado: {formatar_moeda(fatura_info.get('valor_planejado', 0))}")
            print(f"    Executado: {formatar_moeda(fatura_info.get('valor_executado', 0))}")
            return True
        else:
            print(f"\n  ✗ Estouro NÃO foi detectado!")
            print(f"    Planejado: {formatar_moeda(fatura_info.get('valor_planejado', 0))}")
            print(f"    Executado: {formatar_moeda(fatura_info.get('valor_executado', 0))}")
            return False

    except Exception as e:
        print(f"  ✗ Exceção: {str(e)}")
        return False


def main():
    print("\n" + "="*80)
    print(" TESTES DE FATURAS VIRTUAIS DE CARTÃO DE CRÉDITO")
    print("="*80)
    print("\nVERIFIQUE SE O SERVIDOR ESTÁ RODANDO EM http://localhost:5000")
    input("Pressione ENTER para continuar...")

    # Teste 1: Criar cartão com orçamentos
    cartao_info = test_criar_cartao_com_orcamentos()

    if not cartao_info:
        print("\n" + "="*80)
        print(" ✗✗✗ TESTE 1 FALHOU - ABORTANDO ✗✗✗")
        print("="*80 + "\n")
        return

    # Teste 2: Adicionar lançamentos e verificar fatura
    total_gasto = 915.00  # Soma dos lançamentos do teste 2
    fatura_id = test_adicionar_lancamentos(cartao_info)

    if not fatura_id:
        print("\n" + "="*80)
        print(" ✗✗✗ TESTE 2 FALHOU - ABORTANDO ✗✗✗")
        print("="*80 + "\n")
        return

    # Teste 3: Pagar fatura
    sucesso_pagamento = test_pagar_fatura(fatura_id, cartao_info['orcamento_total'], total_gasto)

    # Teste 4: Estouro de orçamento
    sucesso_estouro = test_estouro_orcamento(cartao_info)

    # Resumo final
    print("\n" + "="*80)
    print(" RESUMO DOS TESTES")
    print("="*80)
    print(f"  Teste 1 - Criação de cartão e orçamentos: {'✓ PASSOU' if cartao_info else '✗ FALHOU'}")
    print(f"  Teste 2 - Lançamentos e fatura automática: {'✓ PASSOU' if fatura_id else '✗ FALHOU'}")
    print(f"  Teste 3 - Pagamento (planejado → executado): {'✓ PASSOU' if sucesso_pagamento else '✗ FALHOU'}")
    print(f"  Teste 4 - Detecção de estouro de orçamento: {'✓ PASSOU' if sucesso_estouro else '✗ FALHOU'}")

    if cartao_info and fatura_id and sucesso_pagamento and sucesso_estouro:
        print("\n ✓✓✓ TODOS OS TESTES PASSARAM! ✓✓✓")
    else:
        print("\n ✗✗✗ ALGUNS TESTES FALHARAM! ✗✗✗")

    print("="*80 + "\n")


if __name__ == '__main__':
    main()
