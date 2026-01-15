"""
Migration: Adicionar campos de ESTADO SOBERANO ao Financiamento

Campos adicionados:
- saldo_devedor_atual: Saldo devedor ATUAL (fonte de verdade)
- numero_parcela_base: Última parcela consolidada
- data_base: Data do saldo atual
- amortizacao_mensal_atual: Amortização mensal ATUAL
- regime_pos_amortizacao: Regime após amortização ('REDUZIR_PARCELA' ou 'REDUZIR_PRAZO')
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import db, Financiamento

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("MIGRATION: Adicionar Estado Soberano ao Financiamento")
    print("="*80)

    # Adicionar colunas
    with db.engine.connect() as conn:
        try:
            # saldo_devedor_atual
            conn.execute(db.text(
                "ALTER TABLE financiamento ADD COLUMN saldo_devedor_atual NUMERIC(12, 2)"
            ))
            print("✅ Coluna 'saldo_devedor_atual' adicionada")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  Coluna 'saldo_devedor_atual' já existe")
            else:
                raise

        try:
            # numero_parcela_base
            conn.execute(db.text(
                "ALTER TABLE financiamento ADD COLUMN numero_parcela_base INTEGER DEFAULT 0"
            ))
            print("✅ Coluna 'numero_parcela_base' adicionada")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  Coluna 'numero_parcela_base' já existe")
            else:
                raise

        try:
            # data_base
            conn.execute(db.text(
                "ALTER TABLE financiamento ADD COLUMN data_base DATE"
            ))
            print("✅ Coluna 'data_base' adicionada")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  Coluna 'data_base' já existe")
            else:
                raise

        try:
            # amortizacao_mensal_atual
            conn.execute(db.text(
                "ALTER TABLE financiamento ADD COLUMN amortizacao_mensal_atual NUMERIC(12, 2)"
            ))
            print("✅ Coluna 'amortizacao_mensal_atual' adicionada")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  Coluna 'amortizacao_mensal_atual' já existe")
            else:
                raise

        try:
            # regime_pos_amortizacao
            conn.execute(db.text(
                "ALTER TABLE financiamento ADD COLUMN regime_pos_amortizacao VARCHAR(20)"
            ))
            print("✅ Coluna 'regime_pos_amortizacao' adicionada")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  Coluna 'regime_pos_amortizacao' já existe")
            else:
                raise

        conn.commit()

    # Inicializar estado soberano para financiamentos existentes
    print("\n" + "="*80)
    print("Inicializando estado soberano para financiamentos existentes")
    print("="*80)

    financiamentos = Financiamento.query.all()
    for fin in financiamentos:
        # Inicializar saldo_devedor_atual = valor_financiado
        fin.saldo_devedor_atual = fin.valor_financiado
        fin.numero_parcela_base = 0
        fin.data_base = fin.data_primeira_parcela

        # Calcular amortização mensal original (SAC)
        if fin.sistema_amortizacao == 'SAC':
            fin.amortizacao_mensal_atual = fin.valor_financiado / fin.prazo_total_meses

        print(f"  ✅ Financiamento '{fin.nome}' (ID={fin.id}) inicializado")
        print(f"     Saldo: R$ {fin.saldo_devedor_atual:,.2f}")
        print(f"     Amortização mensal: R$ {fin.amortizacao_mensal_atual:,.2f}")

    db.session.commit()

    print("\n" + "="*80)
    print("MIGRATION CONCLUÍDA COM SUCESSO!")
    print("="*80)
    print("✅ Colunas adicionadas")
    print("✅ Estado soberano inicializado")
    print("\n")
