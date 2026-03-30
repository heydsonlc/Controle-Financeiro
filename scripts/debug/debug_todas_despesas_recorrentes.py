"""
Script para ver TODAS as despesas recorrentes no banco
"""
import sqlite3

DB_PATH = 'data/gastos.db'

def listar_todas_despesas_recorrentes():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("TODAS AS DESPESAS RECORRENTES NO BANCO")
    print("=" * 80)

    # Buscar todas as despesas com recorrente=True
    cursor.execute("""
        SELECT id, nome, valor, data_vencimento, recorrente, tipo_recorrencia,
               ativo, categoria_id, meio_pagamento, cartao_id, criado_em
        FROM item_despesa
        WHERE recorrente = 1
        ORDER BY id DESC
    """)

    despesas = cursor.fetchall()

    if not despesas:
        print("\n[X] NENHUMA despesa recorrente encontrada no banco!")
        print("   -> Isso confirma que a despesa 'Diarista' NAO foi salva como recorrente")
        return

    print(f"\n[INFO] Encontradas {len(despesas)} despesa(s) recorrente(s):\n")

    for desp in despesas:
        desp_id, nome, valor, data_venc, recorrente, tipo_rec, ativo, cat_id, meio_pag, cartao_id, criado_em = desp

        print(f"ID: {desp_id}")
        print(f"Nome: {nome}")
        print(f"Valor: R$ {valor:.2f}" if valor else "Valor: (vazio)")
        print(f"Data Vencimento: {data_venc}")
        print(f"Tipo Recorrencia: {tipo_rec}")
        print(f"Ativa: {ativo}")
        print(f"Meio Pagamento: {meio_pag}")
        print(f"Cartao ID: {cartao_id}")
        print(f"Criado em: {criado_em}")

        # Buscar Contas geradas
        cursor.execute("""
            SELECT id, data_vencimento, valor, mes_referencia, status_pagamento
            FROM conta
            WHERE item_despesa_id = ?
            ORDER BY data_vencimento DESC
            LIMIT 10
        """, (desp_id,))

        contas = cursor.fetchall()
        print(f"   [CONTAS] Contas geradas: {len(contas)}")
        if contas:
            for conta in contas:
                conta_id, data_venc_conta, valor_conta, mes_ref, status = conta
                print(f"      -> ID {conta_id}: Venc {data_venc_conta} | Ref: {mes_ref} | Status: {status}")

        print("-" * 80)

    conn.close()

if __name__ == '__main__':
    listar_todas_despesas_recorrentes()
