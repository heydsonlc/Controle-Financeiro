"""
Script de diagnóstico para verificar estado de despesas recorrentes
"""
import sqlite3
from datetime import datetime

DB_PATH = 'data/gastos.db'

def verificar_despesa_diarista():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("DIAGNÓSTICO: Despesa Recorrente 'Diarista'")
    print("=" * 80)

    # Buscar despesa principal (ItemDespesa)
    cursor.execute("""
        SELECT id, nome, valor, data_vencimento, recorrente, tipo_recorrencia,
               ativo, categoria_id, cartao_id, meio_pagamento
        FROM item_despesa
        WHERE nome LIKE '%Diarista%'
        ORDER BY id DESC
        LIMIT 5
    """)

    despesas = cursor.fetchall()

    if not despesas:
        print("[X] PROBLEMA: Nenhuma despesa com nome 'Diarista' encontrada!")
        print("   -> A despesa pode ter sido criada com outro nome")
        return

    print(f"\n[INFO] Encontradas {len(despesas)} despesa(s) com 'Diarista' no nome:\n")

    for desp in despesas:
        desp_id, nome, valor, data_venc, recorrente, tipo_rec, ativo, cat_id, cartao_id, meio_pag = desp

        print(f"ID: {desp_id}")
        print(f"Nome: {nome}")
        print(f"Valor: R$ {valor:.2f}" if valor else "Valor: (vazio)")
        print(f"Data Vencimento: {data_venc}")
        print(f"Recorrente: {recorrente} {'[OK]' if recorrente else '[X] PROBLEMA!'}")
        print(f"Tipo Recorrência: {tipo_rec}")
        print(f"Ativa: {ativo}")
        print(f"Categoria ID: {cat_id}")
        print(f"Cartão ID: {cartao_id}")
        print(f"Meio Pagamento: {meio_pag}")

        # Buscar Contas geradas (execuções da despesa recorrente)
        cursor.execute("""
            SELECT id, data_vencimento, valor, mes_referencia, status_pagamento, data_pagamento
            FROM conta
            WHERE item_despesa_id = ?
            ORDER BY data_vencimento
        """, (desp_id,))

        contas = cursor.fetchall()

        print(f"\n   [CONTAS] Contas geradas: {len(contas)}")
        if contas:
            for conta in contas:
                conta_id, data_venc_conta, valor_conta, mes_ref, status, data_pag = conta
                print(f"      -> ID {conta_id}: Venc {data_venc_conta} | Mês Ref: {mes_ref} | Status: {status}")
        else:
            print("      [WARNING]  NENHUMA conta gerada!")

        print("-" * 80)

    conn.close()

if __name__ == '__main__':
    verificar_despesa_diarista()
