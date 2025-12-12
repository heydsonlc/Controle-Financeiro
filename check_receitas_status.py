"""Script para verificar status das receitas realizadas e orçamentos"""
from backend.models import db, ReceitaRealizada, ReceitaOrcamento, ItemReceita
from backend.app import app
from datetime import datetime

with app.app_context():
    print("=" * 80)
    print("RECEITAS REALIZADAS")
    print("=" * 80)

    realizadas = ReceitaRealizada.query.all()
    if realizadas:
        for r in realizadas:
            item = ItemReceita.query.get(r.item_receita_id)
            print(f"\nID: {r.id}")
            print(f"  Item Receita: {item.nome if item else 'N/A'} (ID: {r.item_receita_id})")
            print(f"  Valor Recebido: R$ {r.valor_recebido}")
            print(f"  Data Recebimento: {r.data_recebimento}")
            print(f"  Mês Referência: {r.mes_referencia}")
            print(f"  Orçamento ID: {r.orcamento_id}")
            print(f"  Descrição: {r.descricao}")
    else:
        print("Nenhuma receita realizada encontrada")

    print(f"\nTotal: {len(realizadas)} receitas realizadas")

    print("\n" + "=" * 80)
    print("ORÇAMENTOS DE RECEITAS")
    print("=" * 80)

    # Pegar mês atual
    hoje = datetime.now()
    mes_atual = f"{hoje.year}-{hoje.month:02d}-01"

    orcamentos = ReceitaOrcamento.query.filter_by(mes_referencia=mes_atual).all()
    if orcamentos:
        for o in orcamentos:
            item = ItemReceita.query.get(o.item_receita_id)
            print(f"\nID: {o.id}")
            print(f"  Item Receita: {item.nome if item else 'N/A'} (ID: {o.item_receita_id})")
            print(f"  Valor Esperado: R$ {o.valor_esperado}")
            print(f"  Mês Referência: {o.mes_referencia}")
    else:
        print(f"Nenhum orçamento encontrado para {mes_atual}")

    print(f"\nTotal orçamentos do mês atual: {len(orcamentos)}")

    print("\n" + "=" * 80)
    print("VERIFICAÇÃO DE RELACIONAMENTO")
    print("=" * 80)

    if realizadas:
        for r in realizadas:
            if r.orcamento_id:
                orc = ReceitaOrcamento.query.get(r.orcamento_id)
                if orc:
                    print(f"\n✓ Receita Realizada #{r.id} está vinculada ao Orçamento #{r.orcamento_id}")
                    print(f"  Valor Realizado: R$ {r.valor_recebido} (Previsto: R$ {orc.valor_esperado})")
                else:
                    print(f"\n✗ ERRO: Receita Realizada #{r.id} aponta para Orçamento #{r.orcamento_id} que não existe!")
            else:
                print(f"\n⚠ Receita Realizada #{r.id} NÃO está vinculada a nenhum orçamento")
