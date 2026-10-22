"""
FIN-PAGAMENTO-TRAVA-1 — travas das operacoes financeiras (pagamento, estorno, baixa, edicao).

Problema: as rotas liam a conta (situacao e valor), conferiam e so depois gravavam, sem trava.
Duas transacoes simultaneas conferiam o mesmo estado antigo (conta paga por um valor com
movimento de outro, pagamento duplo, estorno duplo, saldo recalculado com dados velhos).

Disciplina (todos os caminhos que alteram a mesma linha seguem a mesma ordem):
  1. conta financeira (despesa ou fatura) — varias, em ordem crescente de id;
  2. compras do cartao (pela fatura travada);
  3. conta bancaria (em criar_movimento; transferencia trava as duas em ordem de id);
  4. movimento (insercao).
A trava vale ate o commit/rollback da transacao. Depois de travar, o estado e RELIDO do banco
(populate_existing): nunca se usa situacao ou valor lidos antes.

PostgreSQL: SELECT ... FOR UPDATE com lock_timeout (sem espera indefinida); deadlock, timeout
ou falha de serializacao viram ConflitoConcorrente (erro controlado, sem gravar nada).
SQLite: FOR UPDATE nao existe e o pysqlite le fora de transacao; um UPDATE neutro (id = id)
na linha toma a trava de escrita do banco antes da releitura, serializando os escritores
(espera limitada pelo timeout do driver; "database is locked" vira ConflitoConcorrente).
"""
from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.exc import DBAPIError, OperationalError

try:
    from backend.models import db
except ImportError:
    from models import db

TEMPO_MAXIMO_TRAVA = '10s'
MENSAGEM_CONFLITO = 'Outra operacao financeira esta em andamento neste registro. Nada foi gravado; tente novamente.'
_CODIGOS_CONFLITO = {'55P03', '40P01', '40001'}  # lock_timeout, deadlock, serialization_failure


class ConflitoConcorrente(Exception):
    """Trava nao obtida a tempo ou conflito detectado pelo banco; a transacao foi desfeita."""


def _dialeto():
    return db.session.get_bind().dialect.name


def travar(modelo, ids):
    """Trava as linhas de `modelo` (em ordem de id) e devolve as instancias relidas do banco.

    Chamar ANTES de alterar as instancias: a releitura descarta alteracoes pendentes nelas.
    """
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return []
    coluna_id = modelo.__table__.c.id
    if _dialeto() == 'postgresql':
        db.session.execute(text(f"SET LOCAL lock_timeout = '{TEMPO_MAXIMO_TRAVA}'"))
        consulta = modelo.query.filter(coluna_id.in_(ids)).order_by(coluna_id).with_for_update(of=modelo)
    else:
        # SQL literal: um update() do Core aplicaria os onupdate (ex.: updated_at) e mudaria dados.
        neutro = text(f'UPDATE {modelo.__table__.name} SET id = id WHERE id IN :ids').bindparams(
            bindparam('ids', expanding=True))
        db.session.execute(neutro, {'ids': ids})
        consulta = modelo.query.filter(coluna_id.in_(ids)).order_by(coluna_id)
    return consulta.populate_existing().all()


def travar_um(modelo, id_):
    linhas = travar(modelo, [id_])
    return linhas[0] if linhas else None


def eh_conflito(exc):
    """Erro de concorrencia do banco (trava, deadlock, serializacao) — nao e defeito de dados."""
    if isinstance(exc, ConflitoConcorrente):
        return True
    if isinstance(exc, DBAPIError):
        original = getattr(exc, 'orig', None)
        if getattr(original, 'pgcode', None) in _CODIGOS_CONFLITO:
            return True
        if isinstance(exc, OperationalError) and 'database is locked' in str(original):
            return True
    return False
