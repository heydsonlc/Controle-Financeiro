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
import logging
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

logger = logging.getLogger(__name__)


def gerar_faturas():
    """
    Gera faturas virtuais para todos os cartões ativos no mês atual
    """
    with app.app_context():
        logger.info("=" * 70)
        logger.info("JOB: Geracao de Faturas Mensais - %s", date.today().strftime('%d/%m/%Y'))
        logger.info("=" * 70)

        try:
            # Gerar faturas
            faturas = CartaoService.gerar_faturas_mes_atual()

            logger.info("OK - %s fatura(s) gerada(s) com sucesso", len(faturas))

            # Exibir resumo
            for fatura in faturas:
                logger.info(
                    "Cartao ID %s: %s | Planejado: R$ %.2f",
                    fatura.item_despesa_id,
                    fatura.descricao,
                    float(fatura.valor_planejado)
                )

            logger.info("=" * 70)
            logger.info("JOB CONCLUIDO COM SUCESSO")
            logger.info("=" * 70)

        except Exception as e:
            logger.exception("ERRO ao gerar faturas: %s", e)
            sys.exit(1)


if __name__ == '__main__':
    gerar_faturas()
