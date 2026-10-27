"""
FIN-CATEGORIAS-RECORRENCIAS-2 — escritor unico do catalogo global de categorias de despesa.

O catalogo (categoria e categoria_palavra_chave) e um so para todos os perfis. Quem o escreve fica no banco
(financeiro.catalogo_categorias, alterada so por administrador via financeiro.definir_escritor_catalogo). Regras:
- sem a tabela (SQLite, banco sem a migration 20261125090000): comportamento legado, o Flask escreve;
- sem linha ou com escritor FLASK: o Flask escreve (padrao; nada muda sozinho);
- escritor NOVO: as escritas do catalogo pelo Flask sao recusadas (409 CATALOGO_NOVO, nada gravado); consultas continuam;
- valor inesperado ou erro na verificacao: a escrita e bloqueada e o motivo vai para o log.

Concorrencia: no PostgreSQL, a verificacao toma a trava consultiva COMPARTILHADA (20261125, 0) ate o fim da transacao;
a troca de escritor e as escritas do novo aplicativo tomam a mesma trava em modo EXCLUSIVO.
"""
import logging

from sqlalchemy import text

try:
    from backend.models import db
except ImportError:
    from models import db

logger = logging.getLogger(__name__)

CHAVE_TRAVA = 20261125  # mesma chave de financeiro.exigir_escrita_catalogo e definir_escritor_catalogo


def flask_pode_escrever_catalogo(contexto=''):
    """True se o Flask e o escritor do catalogo global de categorias."""
    try:
        if db.session.get_bind().dialect.name != 'postgresql':
            return True  # configuracao inexistente neste banco: comportamento legado

        # Savepoint: um erro aqui nao pode invalidar a transacao da requisicao.
        with db.session.begin_nested():
            existe = db.session.execute(text("select to_regclass('financeiro.catalogo_categorias') is not null")).scalar()
            if not existe:
                return True  # migration ainda nao aplicada: comportamento legado
            db.session.execute(text('select pg_advisory_xact_lock_shared(:chave, 0)'), {'chave': CHAVE_TRAVA})
            escritor = db.session.execute(text('select escritor from financeiro.catalogo_categorias')).scalar()
    except Exception:
        logger.exception('FIN-CATEGORIAS-RECORRENCIAS-2: falha ao verificar o escritor do catalogo (%s); escrita bloqueada',
                         contexto)
        return False

    if escritor is None or escritor == 'FLASK':
        return True
    if escritor == 'NOVO':
        logger.info('FIN-CATEGORIAS-RECORRENCIAS-2: catalogo administrado pelo novo aplicativo; Flask nao grava (%s)',
                    contexto)
        return False
    logger.error('FIN-CATEGORIAS-RECORRENCIAS-2: escritor inesperado %r do catalogo (%s); escrita bloqueada', escritor, contexto)
    return False


def registrar_guarda_catalogo(blueprint):
    """Recusa as escritas do blueprint (POST/PUT/PATCH/DELETE) quando o catalogo e do novo aplicativo."""
    from flask import jsonify, request

    @blueprint.before_request
    def _escritor_do_catalogo():
        if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return None
        if flask_pode_escrever_catalogo(f'escrita {request.endpoint}'):
            return None
        db.session.rollback()
        return jsonify({'success': False, 'codigo': 'CATALOGO_NOVO',
                        'error': 'Categorias de despesa: o catalogo e administrado pelo novo aplicativo. Nada foi gravado.'}), 409

    return _escritor_do_catalogo
