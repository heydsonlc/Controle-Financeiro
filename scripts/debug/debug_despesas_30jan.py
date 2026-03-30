"""
Buscar despesas com vencimento em 30/01/2025
"""
import sqlite3

DB_PATH = 'data/gastos.db'

def buscar_despesas_30jan():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("DESPESAS COM VENCIMENTO EM 30/01/2025")
    print("=" * 80)

    # Buscar todas as ItemDespesa com vencimento em 30/01/2025
    cursor.execute("""
        SELECT id, nome, valor, data_vencimento, recorrente, tipo_recorrencia,
               tipo, ativo, meio_pagamento, criado_em
        FROM item_despesa
        WHERE data_vencimento = '2025-01-30'
        ORDER BY id DESC
    """)

    despesas = cursor.fetchall()

    if not despesas:
        print("\n[X] NENHUMA despesa com vencimento em 30/01/2025 encontrada!")
        print("   -> Isso confirma que a despesa MENSAL nao foi salva no banco")
        print("   -> Verifique se houve erro ao criar a despesa")
    else:
        print(f"\n[INFO] Encontradas {len(despesas)} despesa(s):\n")
        for desp in despesas:
            desp_id, nome, valor, data_venc, recorrente, tipo_rec, tipo, ativo, meio_pag, criado_em = desp
            print(f"ID: {desp_id}")
            print(f"Nome: {nome}")
            print(f"Valor: R$ {valor:.2f}" if valor else "Valor: (vazio)")
            print(f"Data Vencimento: {data_venc}")
            print(f"Recorrente: {recorrente} [OK]" if recorrente else f"Recorrente: {recorrente} [X]")
            print(f"Tipo Recorrencia: {tipo_rec}")
            print(f"Tipo: {tipo}")
            print(f"Ativa: {ativo}")
            print(f"Meio Pagamento: {meio_pag}")
            print(f"Criado em: {criado_em}")
            print("-" * 80)

    # Verificar contas com vencimento em 30/01
    print("\n" + "=" * 80)
    print("CONTAS COM VENCIMENTO EM 30/01/2025")
    print("=" * 80)

    cursor.execute("""
        SELECT c.id, c.descricao, c.valor, c.mes_referencia, c.status_pagamento,
               i.nome as nome_item, i.id as item_id
        FROM conta c
        LEFT JOIN item_despesa i ON c.item_despesa_id = i.id
        WHERE c.data_vencimento = '2025-01-30'
        ORDER BY c.id DESC
    """)

    contas = cursor.fetchall()

    if not contas:
        print("\n[X] NENHUMA conta com vencimento em 30/01/2025")
    else:
        print(f"\n[INFO] Encontradas {len(contas)} conta(s):\n")
        for conta in contas:
            conta_id, desc, valor, mes_ref, status, nome_item, item_id = conta
            print(f"Conta ID: {conta_id}")
            print(f"Descricao: {desc}")
            print(f"Valor: R$ {valor:.2f}")
            print(f"Mes Ref: {mes_ref}")
            print(f"Status: {status}")
            print(f"ItemDespesa: {nome_item} (ID: {item_id})")
            print("-" * 40)

    conn.close()

if __name__ == '__main__':
    buscar_despesas_30jan()
