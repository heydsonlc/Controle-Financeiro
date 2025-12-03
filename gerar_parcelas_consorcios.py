"""Script para gerar parcelas (Contas) dos consorcios ativos"""
import sys
from pathlib import Path
from datetime import date
from dateutil.relativedelta import relativedelta
from decimal import Decimal

sys.path.insert(0, str(Path.cwd()))

from backend.app import app
from backend.models import db, ContratoConsorcio, Conta, ItemDespesa

def gerar_contas_consorcio(consorcio):
    """
    Gera registros de Conta para cada parcela do consorcio
    """
    print(f"\n  Gerando parcelas para: {consorcio.nome}")

    # Buscar o item de despesa associado
    item_despesa = ItemDespesa.query.get(consorcio.item_despesa_id)
    if not item_despesa:
        print(f"    ERRO: ItemDespesa {consorcio.item_despesa_id} nao encontrado")
        return 0

    print(f"    Item Despesa: {item_despesa.nome}")
    print(f"    Numero de parcelas: {consorcio.numero_parcelas}")
    print(f"    Valor inicial: R$ {consorcio.valor_inicial:.2f}")
    print(f"    Tipo reajuste: {consorcio.tipo_reajuste}")
    print(f"    Valor reajuste: R$ {consorcio.valor_reajuste:.2f}")

    # Calcular parcelas
    mes_atual = consorcio.mes_inicio
    valor_parcela_base = Decimal(str(consorcio.valor_inicial))
    contas_criadas = 0

    for i in range(consorcio.numero_parcelas):
        numero_parcela = i + 1

        # Calcular valor ajustado
        valor_ajustado = valor_parcela_base

        if consorcio.tipo_reajuste == 'percentual' and consorcio.valor_reajuste > 0:
            # Reajuste percentual: valor_base * (1 + taxa%)^mes
            fator_reajuste = Decimal(str((1 + (consorcio.valor_reajuste / 100)) ** i))
            valor_ajustado = valor_parcela_base * fator_reajuste
        elif consorcio.tipo_reajuste == 'fixo' and consorcio.valor_reajuste > 0:
            # Reajuste fixo: valor_base + (reajuste * mes)
            valor_ajustado = valor_parcela_base + (Decimal(str(consorcio.valor_reajuste)) * i)

        # Data de vencimento (dia 5 do mes)
        data_vencimento = mes_atual.replace(day=5) if mes_atual.day > 5 else mes_atual

        # Verificar se ja existe conta para esta parcela
        conta_existente = Conta.query.filter(
            Conta.item_despesa_id == consorcio.item_despesa_id,
            Conta.descricao.like(f'%{consorcio.nome}%Parcela {numero_parcela}/%')
        ).first()

        if conta_existente:
            print(f"      Parcela {numero_parcela}: JA EXISTE")
        else:
            # Criar nova conta
            nova_conta = Conta(
                item_despesa_id=consorcio.item_despesa_id,
                mes_referencia=mes_atual.replace(day=1),
                descricao=f'{consorcio.nome} - Parcela {numero_parcela}/{consorcio.numero_parcelas}',
                valor=valor_ajustado,
                data_vencimento=data_vencimento,
                status_pagamento='Pendente',
                numero_parcela=numero_parcela,
                total_parcelas=consorcio.numero_parcelas,
                observacoes=f'Consorcio {consorcio.tipo_reajuste} - Valor base: R$ {valor_parcela_base:.2f}'
            )

            db.session.add(nova_conta)
            contas_criadas += 1
            print(f"      Parcela {numero_parcela}: R$ {valor_ajustado:.2f} - Venc: {data_vencimento} [CRIADA]")

        # Proximo mes
        mes_atual = mes_atual + relativedelta(months=1)

    return contas_criadas


print("=== GERACAO DE PARCELAS DE CONSORCIOS ===\n")

with app.app_context():
    # Buscar consorcios ativos
    consorcios = ContratoConsorcio.query.filter_by(ativo=True).all()
    print(f"Consorcios ativos encontrados: {len(consorcios)}\n")

    if not consorcios:
        print("Nenhum consorcio ativo para processar.")
        sys.exit(0)

    total_contas_criadas = 0

    for consorcio in consorcios:
        contas_criadas = gerar_contas_consorcio(consorcio)
        total_contas_criadas += contas_criadas

    if total_contas_criadas > 0:
        print(f"\n=== SALVANDO NO BANCO ===")
        db.session.commit()
        print(f"[OK] {total_contas_criadas} contas criadas com sucesso!")
    else:
        print(f"\n[INFO] Nenhuma conta nova foi criada (todas ja existiam).")

    # Verificar resultado
    print(f"\n=== VERIFICACAO FINAL ===")
    total_contas = Conta.query.count()
    print(f"Total de contas no banco: {total_contas}")

    # Contas de dezembro/2025
    from sqlalchemy import extract
    contas_dez = Conta.query.filter(
        extract('month', Conta.data_vencimento) == 12,
        extract('year', Conta.data_vencimento) == 2025
    ).all()

    print(f"Contas em Dezembro/2025: {len(contas_dez)}")
    for conta in contas_dez:
        print(f"  - {conta.descricao}: R$ {conta.valor:.2f} ({conta.status_pagamento})")
