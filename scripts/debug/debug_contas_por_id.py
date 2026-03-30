"""
Verificar contas por ID específico de ItemDespesa
"""
import sqlite3

DB_PATH = 'data/gastos.db'

def verificar_contas_por_ids():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # IDs das despesas Diarista encontradas anteriormente
    ids_diarista = [43, 44, 46, 47]

    for item_id in ids_diarista:
        print("=" * 80)
        print(f"CONTAS DA DESPESA ID {item_id}")
        print("=" * 80)

        # Buscar info da despesa
        cursor.execute("""
            SELECT nome, data_vencimento, tipo_recorrencia
            FROM item_despesa
            WHERE id = ?
        """, (item_id,))

        desp = cursor.fetchone()
        if desp:
            nome, data_venc, tipo_rec = desp
            print(f"Despesa: {nome}")
            print(f"Data Vencimento (referencia): {data_venc}")
            print(f"Tipo Recorrencia: {tipo_rec}")

        # Buscar TODAS as contas dessa despesa
        cursor.execute("""
            SELECT id, data_vencimento, mes_referencia, valor, status_pagamento
            FROM conta
            WHERE item_despesa_id = ?
            ORDER BY data_vencimento
        """, (item_id,))

        contas = cursor.fetchall()

        print(f"\nTotal de contas: {len(contas)}\n")

        if contas:
            # Agrupar por mês
            contas_por_mes = {}
            for conta in contas:
                conta_id, data_venc, mes_ref, valor, status = conta
                mes = data_venc[:7] if data_venc else 'N/A'  # YYYY-MM
                if mes not in contas_por_mes:
                    contas_por_mes[mes] = []
                contas_por_mes[mes].append((conta_id, data_venc, valor, status))

            print("Distribuicao por mes:")
            for mes in sorted(contas_por_mes.keys()):
                print(f"\n  {mes}: {len(contas_por_mes[mes])} conta(s)")
                for conta_id, data_venc, valor, status in contas_por_mes[mes][:3]:  # Mostrar apenas 3
                    print(f"    -> ID {conta_id}: {data_venc} | R$ {valor:.2f} | {status}")
                if len(contas_por_mes[mes]) > 3:
                    print(f"    ... e mais {len(contas_por_mes[mes]) - 3} conta(s)")
        else:
            print("[X] NENHUMA conta gerada para esta despesa!")

        print()

    conn.close()

if __name__ == '__main__':
    verificar_contas_por_ids()
