"""
Job Mensal: Gerar Faturas Virtuais de Cartão

Este script deve ser executado automaticamente no 1º dia de cada mês
para garantir que todas as faturas dos cartões ativos sejam criadas.

Pode ser agendado via:
- Cron (Linux/Mac): 0 0 1 * * python backend/jobs/gerar_faturas_mensais.py
- Task Scheduler (Windows)
- APScheduler (Python)

Executar manualmente: python backend/jobs/gerar_faturas_mensais.py
"""
import sys
import os
from datetime import date

# Adicionar o diretório backend ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from backend.app import app
    from backend.models import db
    from backend.services.cartao_service import CartaoService
except ImportError:
    from app import app
    from models import db
    from services.cartao_service import CartaoService


def gerar_faturas():
    """
    Gera faturas virtuais para todos os cartões ativos no mês atual
    """
    with app.app_context():
        print("=" * 70)
        print(f" JOB: Geracao de Faturas Mensais - {date.today().strftime('%d/%m/%Y')}")
        print("=" * 70)
        print()

        try:
            # Gerar faturas
            faturas = CartaoService.gerar_faturas_mes_atual()

            print(f"OK - {len(faturas)} fatura(s) gerada(s) com sucesso!")
            print()

            # Exibir resumo
            for fatura in faturas:
                print(f"  - Cartao ID {fatura.item_despesa_id}: "
                      f"{fatura.descricao} | "
                      f"Planejado: R$ {float(fatura.valor_planejado):.2f}")

            print()
            print("=" * 70)
            print(" JOB CONCLUIDO COM SUCESSO")
            print("=" * 70)

        except Exception as e:
            print(f"ERRO ao gerar faturas: {str(e)}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == '__main__':
    gerar_faturas()
