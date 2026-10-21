"""
FIN-RECORRENCIA-T1 — gerador unico de recorrencias por perfil financeiro.

A configuracao fica no banco (financeiro.gerador_recorrencia, alterada so por
administrador via financeiro.definir_gerador_recorrencia). Regras:
- sem a tabela (SQLite, banco sem a migration): comportamento legado, o Flask gera;
- perfil sem linha ou com gerador FLASK: o Flask gera (padrao; nada migra sozinho);
- perfil com gerador NOVO: o Flask NAO gera contas recorrentes, compras recorrentes
  de cartao nem faturas virtuais desse perfil;
- valor inesperado ou erro na verificacao: a geracao e bloqueada e o motivo e
  registrado no log (nunca deixa os dois motores ativos por acidente).

Consultas, pagamentos, edicoes e o cadastro de compras nao passam por aqui.

Concorrencia: no PostgreSQL, a verificacao toma a trava consultiva COMPARTILHADA
(20261023, perfil) ate o fim da transacao. A troca de gerador e a geracao do novo
motor tomam a mesma trava em modo EXCLUSIVO, entao uma troca espera a geracao em
andamento do Flask terminar e vice-versa.
"""
import logging

from sqlalchemy import text

try:
    from backend.models import PerfilFinanceiro, db
except ImportError:
    from models import PerfilFinanceiro, db

logger = logging.getLogger(__name__)

GERADOR_FLASK = 'FLASK'
GERADOR_NOVO = 'NOVO'
CHAVE_TRAVA = 20261023  # mesma chave de financeiro.gerar_mes e definir_gerador_recorrencia


def perfil_efetivo(perfil_id):
    """Perfil dono de um registro: NULL (legado) pertence ao "Pessoal"."""
    if perfil_id is not None:
        return perfil_id
    pessoal = PerfilFinanceiro.query.filter_by(nome='Pessoal').order_by(PerfilFinanceiro.id).first()
    return pessoal.id if pessoal else None


def flask_pode_gerar(perfil_id, contexto=''):
    """True se o Flask e o gerador de recorrencias/faturas do perfil."""
    try:
        if db.session.get_bind().dialect.name != 'postgresql':
            return True  # configuracao inexistente neste banco: comportamento legado

        # Savepoint: um erro aqui nao pode invalidar a transacao da requisicao.
        with db.session.begin_nested():
            existe = db.session.execute(
                text("select to_regclass('financeiro.gerador_recorrencia') is not null")
            ).scalar()
            if not existe:
                return True  # migration ainda nao aplicada: comportamento legado

            perfil = perfil_efetivo(perfil_id)
            if perfil is None:
                logger.error('FIN-RECORRENCIA-T1: perfil indefinido (%s); geracao bloqueada', contexto)
                return False
            db.session.execute(text('select pg_advisory_xact_lock_shared(:chave, :perfil)'),
                               {'chave': CHAVE_TRAVA, 'perfil': perfil})
            gerador = db.session.execute(
                text('select gerador from financeiro.gerador_recorrencia where perfil_financeiro_id = :perfil'),
                {'perfil': perfil},
            ).scalar()
    except Exception:
        logger.exception('FIN-RECORRENCIA-T1: falha ao verificar o gerador do perfil %s (%s); geracao bloqueada',
                         perfil_id, contexto)
        return False

    if gerador is None or gerador == GERADOR_FLASK:
        return True
    if gerador == GERADOR_NOVO:
        logger.info('FIN-RECORRENCIA-T1: perfil %s gerado pelo novo aplicativo; Flask nao gera (%s)', perfil, contexto)
        return False
    logger.error('FIN-RECORRENCIA-T1: gerador inesperado %r no perfil %s (%s); geracao bloqueada',
                 gerador, perfil, contexto)
    return False
