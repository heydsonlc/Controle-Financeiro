"""
Verificar se existem contas de Diarista em fevereiro/2025
"""
import sqlite3

DB_PATH = 'data/gastos.db'

def verificar_contas_fevereiro():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("CONTAS DE DIARISTA EM FEVEREIRO/2025")
    print("=" * 80)

    # Buscar contas com data_vencimento em fevereiro/2025
    cursor.execute("""
        SELECT c.id, c.descricao, c.valor, c.data_vencimento, c.mes_referencia,
               c.status_pagamento, i.nome as item_nome, i.id as item_id
        FROM conta c
        LEFT JOIN item_despesa i ON c.item_despesa_id = i.id
        WHERE c.data_vencimento >= '2025-02-01'
          AND c.data_vencimento <= '2025-02-28'
          AND i.nome LIKE '%Diarista%'
        ORDER BY c.data_vencimento
    """)

    contas_fev = cursor.fetchall()

    if not contas_fev:
        print("\n[X] NENHUMA conta de Diarista encontrada em fevereiro/2025!")
        print("   -> Isso confirma que as contas NAO foram geradas")
        print("   -> O gap-filling nao esta funcionando")
    else:
        print(f"\n[OK] Encontradas {len(contas_fev)} conta(s) em fevereiro/2025:\n")
        for conta in contas_fev:
            conta_id, desc, valor, data_venc, mes_ref, status, item_nome, item_id = conta
            print(f"ID: {conta_id}")
            print(f"Descricao: {desc}")
            print(f"Valor: R$ {valor:.2f}")
            print(f"Data Vencimento: {data_venc}")
            print(f"Mes Referencia: {mes_ref}")
            print(f"Status: {status}")
            print(f"ItemDespesa: {item_nome} (ID: {item_id})")
            print("-" * 40)

    # Verificar total de contas por mês
    print("\n" + "=" * 80)
    print("DISTRIBUICAO DE CONTAS POR MES (todas as Diaristas)")
    print("=" * 80)

    cursor.execute("""
        SELECT strftime('%Y-%m', c.data_vencimento) as mes, COUNT(*) as total
        FROM conta c
        LEFT JOIN item_despesa i ON c.item_despesa_id = i.id
        WHERE i.nome LIKE '%Diarista%'
        GROUP BY mes
        ORDER BY mes
    """)

    meses = cursor.fetchall()

    if meses:
        print("\nDistribuicao:")
        for mes, total in meses:
            print(f"  {mes}: {total} conta(s)")
    else:
        print("\n[X] Nenhuma conta encontrada")

    conn.close()

if __name__ == '__main__':
    verificar_contas_fevereiro()
