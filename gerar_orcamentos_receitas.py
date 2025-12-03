"""Script para gerar orçamentos de receitas recorrentes"""
import sys
from pathlib import Path
from datetime import date
from decimal import Decimal

sys.path.insert(0, str(Path.cwd()))

from backend.app import app
from backend.models import db, ItemReceita, ReceitaOrcamento

def gerar_orcamento_mes(item_receita, mes_referencia):
    """
    Gera ReceitaOrcamento para um ItemReceita em um mês específico
    """
    # Verificar se já existe orçamento para este item neste mês
    orcamento_existente = ReceitaOrcamento.query.filter(
        ReceitaOrcamento.item_receita_id == item_receita.id,
        ReceitaOrcamento.mes_referencia == mes_referencia
    ).first()

    if orcamento_existente:
        print(f"    {mes_referencia.strftime('%m/%Y')}: JA EXISTE (R$ {orcamento_existente.valor_esperado:.2f})")
        return 0

    # Criar novo orçamento
    novo_orcamento = ReceitaOrcamento(
        item_receita_id=item_receita.id,
        mes_referencia=mes_referencia,
        valor_esperado=item_receita.valor_base_mensal,
        periodicidade='MENSAL_FIXA',
        observacoes=f'Gerado automaticamente para {item_receita.nome}'
    )

    db.session.add(novo_orcamento)
    print(f"    {mes_referencia.strftime('%m/%Y')}: R$ {item_receita.valor_base_mensal:.2f} [CRIADO]")
    return 1


print("=== GERACAO DE ORCAMENTOS DE RECEITAS ===\n")

with app.app_context():
    # Buscar ItemReceita ativos com valor_base_mensal definido
    receitas = ItemReceita.query.filter(
        ItemReceita.ativo == True,
        ItemReceita.valor_base_mensal != None,
        ItemReceita.valor_base_mensal > 0
    ).all()

    print(f"Receitas recorrentes encontradas: {len(receitas)}\n")

    if not receitas:
        print("Nenhuma receita recorrente encontrada.")
        print("\nDica: Cadastre receitas com valor_base_mensal > 0 para gera-las automaticamente.")
        sys.exit(0)

    # Mes atual
    hoje = date.today()
    mes_referencia = date(hoje.year, hoje.month, 1)

    print(f"Gerando orcamentos para: {mes_referencia.strftime('%B/%Y')}\n")

    total_orcamentos_criados = 0

    for receita in receitas:
        print(f"  {receita.nome}")
        print(f"    Tipo: {receita.tipo}")
        print(f"    Valor base mensal: R$ {receita.valor_base_mensal:.2f}")

        orcamentos_criados = gerar_orcamento_mes(receita, mes_referencia)
        total_orcamentos_criados += orcamentos_criados

    if total_orcamentos_criados > 0:
        print(f"\n=== SALVANDO NO BANCO ===")
        db.session.commit()
        print(f"[OK] {total_orcamentos_criados} orcamentos criados com sucesso!")
    else:
        print(f"\n[INFO] Nenhum orcamento novo foi criado (todos ja existiam).")

    # Verificar resultado
    print(f"\n=== VERIFICACAO FINAL ===")
    total_orcamentos = ReceitaOrcamento.query.filter(
        ReceitaOrcamento.mes_referencia == mes_referencia
    ).count()
    print(f"Total de orcamentos em {mes_referencia.strftime('%m/%Y')}: {total_orcamentos}")

    if total_orcamentos > 0:
        orcamentos = ReceitaOrcamento.query.filter(
            ReceitaOrcamento.mes_referencia == mes_referencia
        ).all()

        soma_total = sum(float(o.valor_esperado) for o in orcamentos)
        print(f"Valor total esperado: R$ {soma_total:.2f}\n")

        print("Orcamentos criados:")
        for orc in orcamentos:
            print(f"  - {orc.item_receita.nome}: R$ {orc.valor_esperado:.2f}")
