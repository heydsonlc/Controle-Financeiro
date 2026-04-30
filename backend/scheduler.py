"""
Agendador de Jobs Automáticos

Executa tarefas periódicas do sistema:
- Geração de faturas mensais de cartões
- Outros jobs futuros

Para usar:
1. Instalar: pip install APScheduler
2. Importar no app.py e iniciar: scheduler.start()
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit
import logging

logger = logging.getLogger(__name__)

# Inicializar scheduler
scheduler = BackgroundScheduler()

def job_gerar_faturas_mensais():
    """
    Job executado no 1º dia de cada mês às 00:01
    """
    try:
        try:
            from backend.app import create_app
            from backend.services.cartao_service import CartaoService
        except ImportError:
            from app import create_app
            from services.cartao_service import CartaoService

        app = create_app()
        with app.app_context():
            logger.info("Executando job: Geracao de faturas mensais")
            faturas = CartaoService.gerar_faturas_mes_atual()
            logger.info("Job de faturas concluido: %s fatura(s) gerada(s)", len(faturas))
    except Exception as e:
        logger.exception("Erro no job de geracao de faturas mensais: %s", e)

# Agendar jobs
scheduler.add_job(
    func=job_gerar_faturas_mensais,
    trigger=CronTrigger(day=1, hour=0, minute=1),  # Dia 1, 00:01
    id='gerar_faturas_mensais',
    name='Gerar faturas mensais de cartoes',
    replace_existing=True
)

# Garantir que o scheduler pare ao encerrar a aplicação
atexit.register(lambda: scheduler.shutdown())

# Função para iniciar o scheduler
def start_scheduler():
    """
    Inicia o scheduler de jobs

    Chamar no app.py após criar a aplicação Flask:

    from scheduler import start_scheduler
    start_scheduler()
    """
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler de jobs iniciado")
        logger.info("Job agendado: Gerar faturas mensais (dia 1, 00:01)")
