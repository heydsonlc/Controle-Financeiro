"""
Script para limpar TODOS os financiamentos do banco de dados
ATENCAO: Esta operacao e IRREVERSIVEL!

Uso:
    python limpar_financiamentos.py           # Pede confirmacao
    python limpar_financiamentos.py --force   # Executa sem confirmacao
"""
import sys
sys.path.insert(0, 'backend')

from backend.app import create_app
from backend.models import (
    db,
    Financiamento,
    FinanciamentoParcela,
    FinanciamentoSeguroVigencia,
    FinanciamentoAmortizacaoExtra,
    Conta,
    ItemDespesa
)

app = create_app()

with app.app_context():
    print("\n" + "="*80)
    print("LIMPEZA TOTAL DE FINANCIAMENTOS")
    print("="*80)

    # Contar registros antes
    print("\n[1] Contando registros ANTES da limpeza...")

    count_financiamentos = Financiamento.query.count()
    count_parcelas = FinanciamentoParcela.query.count()
    count_vigencias = FinanciamentoSeguroVigencia.query.count()
    count_amortizacoes = FinanciamentoAmortizacaoExtra.query.count()

    # Contar contas vinculadas a parcelas de financiamento
    count_contas_fin = Conta.query.filter(
        Conta.financiamento_parcela_id.isnot(None)
    ).count()

    print(f"    - Financiamentos: {count_financiamentos}")
    print(f"    - Parcelas: {count_parcelas}")
    print(f"    - Vigências de seguro: {count_vigencias}")
    print(f"    - Amortizações extras: {count_amortizacoes}")
    print(f"    - Contas vinculadas: {count_contas_fin}")

    total = (count_financiamentos + count_parcelas + count_vigencias +
             count_amortizacoes + count_contas_fin)

    if total == 0:
        print("\n[INFO] Banco já está limpo! Nenhum financiamento encontrado.")
        sys.exit(0)

    # Confirmação
    print("\n" + "="*80)
    print("ATENCAO: Esta operacao ira DELETAR PERMANENTEMENTE:")
    print(f"    - {count_financiamentos} financiamento(s)")
    print(f"    - {count_parcelas} parcela(s)")
    print(f"    - {count_vigencias} vigencia(s) de seguro")
    print(f"    - {count_amortizacoes} amortizacao(oes) extra(s)")
    print(f"    - {count_contas_fin} conta(s) vinculada(s)")
    print(f"    TOTAL: {total} registros")
    print("="*80)

    # Verificar se foi passado --force
    force_mode = '--force' in sys.argv

    if not force_mode:
        confirmacao = input("\nDigite 'LIMPAR' (em maiusculas) para confirmar: ")

        if confirmacao != "LIMPAR":
            print("\n[CANCELADO] Operacao cancelada pelo usuario.")
            sys.exit(0)
    else:
        print("\n[FORCE MODE] Executando sem confirmacao...")

    # Executar limpeza
    print("\n[2] Iniciando limpeza...")

    try:
        # Ordem de deleção (filhos antes de pais, respeitando FKs)

        # 1. Deletar contas vinculadas a parcelas de financiamento
        print("    [2.1] Deletando contas vinculadas a parcelas...")
        contas_deletadas = Conta.query.filter(
            Conta.financiamento_parcela_id.isnot(None)
        ).delete(synchronize_session=False)
        print(f"          OK {contas_deletadas} conta(s) deletada(s)")

        # 2. Deletar parcelas
        print("    [2.2] Deletando parcelas de financiamento...")
        parcelas_deletadas = FinanciamentoParcela.query.delete(synchronize_session=False)
        print(f"          OK {parcelas_deletadas} parcela(s) deletada(s)")

        # 3. Deletar vigências de seguro
        print("    [2.3] Deletando vigencias de seguro...")
        vigencias_deletadas = FinanciamentoSeguroVigencia.query.delete(synchronize_session=False)
        print(f"          OK {vigencias_deletadas} vigencia(s) deletada(s)")

        # 4. Deletar amortizações extras
        print("    [2.4] Deletando amortizacoes extraordinarias...")
        amortizacoes_deletadas = FinanciamentoAmortizacaoExtra.query.delete(synchronize_session=False)
        print(f"          OK {amortizacoes_deletadas} amortizacao(oes) deletada(s)")

        # 5. Buscar IDs de ItemDespesa vinculados a financiamentos (para deletar depois)
        print("    [2.5] Identificando ItemDespesa vinculados...")
        item_despesa_ids = [f.item_despesa_id for f in Financiamento.query.all() if f.item_despesa_id]
        print(f"          > {len(item_despesa_ids)} ItemDespesa para limpar")

        # 6. Deletar financiamentos
        print("    [2.6] Deletando financiamentos...")
        financiamentos_deletados = Financiamento.query.delete(synchronize_session=False)
        print(f"          OK {financiamentos_deletados} financiamento(s) deletado(s)")

        # 7. Deletar ItemDespesa orfaos (opcional, mas recomendado)
        if item_despesa_ids:
            print("    [2.7] Deletando ItemDespesa vinculados...")
            itens_deletados = ItemDespesa.query.filter(
                ItemDespesa.id.in_(item_despesa_ids)
            ).delete(synchronize_session=False)
            print(f"          OK {itens_deletados} ItemDespesa deletado(s)")

        # Commit
        db.session.commit()

        print("\n" + "="*80)
        print("LIMPEZA CONCLUIDA COM SUCESSO!")
        print("="*80)
        print(f"\nTotal de registros deletados: {total}")
        print("\nBanco de dados limpo. Voce pode criar novos financiamentos do zero.")

    except Exception as e:
        db.session.rollback()
        print("\n" + "="*80)
        print("ERRO NA LIMPEZA!")
        print("="*80)
        print(f"\nErro: {e}")
        print("\nNenhum registro foi deletado (rollback executado).")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print()
