from __future__ import annotations

from sqlalchemy import text

try:
    from backend.models import db
except ImportError:
    from models import db


def _sqlite_has_column(conn, table: str, column: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info('{table}')")).fetchall()
    cols = {r[1] for r in rows}  # (cid, name, type, notnull, dflt_value, pk)
    return column in cols


def _sqlite_has_table(conn, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {'name': table},
    ).fetchone()
    return bool(row and row[0] == table)


def _sqlite_has_index(conn, index: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='index' AND name=:name"),
        {'name': index},
    ).fetchone()
    return bool(row and row[0] == index)


def ensure_sqlite_schema_compat() -> None:
    """
    Garante compatibilidade de schema em SQLite quando o banco existe
    mas nĂŁo estĂĄ sob controle do Alembic (ex: criado por create_all / seeds).
    """
    engine = db.engine
    if engine.dialect.name != 'sqlite':
        return

    with engine.begin() as conn:
        # =====================================================================
        # Veículos
        # =====================================================================
        if _sqlite_has_table(conn, 'veiculo_regra_manutencao_km'):
            if not _sqlite_has_column(conn, 'veiculo_regra_manutencao_km', 'meses_intervalo'):
                conn.execute(text('ALTER TABLE veiculo_regra_manutencao_km ADD COLUMN meses_intervalo INTEGER'))

        # =====================================================================
        # Contas Bancárias / Movimentos Financeiros
        # =====================================================================
        if _sqlite_has_table(conn, 'movimento_financeiro'):
            if not _sqlite_has_column(conn, 'movimento_financeiro', 'origem'):
                conn.execute(text("ALTER TABLE movimento_financeiro ADD COLUMN origem VARCHAR(20) DEFAULT 'MANUAL'"))
            if not _sqlite_has_column(conn, 'movimento_financeiro', 'ajustavel'):
                conn.execute(text('ALTER TABLE movimento_financeiro ADD COLUMN ajustavel BOOLEAN DEFAULT 0'))
            if not _sqlite_has_column(conn, 'movimento_financeiro', 'receita_realizada_id'):
                conn.execute(text('ALTER TABLE movimento_financeiro ADD COLUMN receita_realizada_id INTEGER'))
            if not _sqlite_has_column(conn, 'movimento_financeiro', 'conta_id'):
                conn.execute(text('ALTER TABLE movimento_financeiro ADD COLUMN conta_id INTEGER'))
            if not _sqlite_has_column(conn, 'movimento_financeiro', 'transferencia_id'):
                conn.execute(text('ALTER TABLE movimento_financeiro ADD COLUMN transferencia_id VARCHAR(36)'))

        if _sqlite_has_table(conn, 'item_receita'):
            if not _sqlite_has_column(conn, 'item_receita', 'conta_bancaria_id'):
                conn.execute(text('ALTER TABLE item_receita ADD COLUMN conta_bancaria_id INTEGER'))

        if _sqlite_has_table(conn, 'receita_realizada'):
            if not _sqlite_has_column(conn, 'receita_realizada', 'conta_bancaria_id'):
                conn.execute(text('ALTER TABLE receita_realizada ADD COLUMN conta_bancaria_id INTEGER'))

        if _sqlite_has_table(conn, 'conta'):
            if not _sqlite_has_column(conn, 'conta', 'conta_bancaria_id'):
                conn.execute(text('ALTER TABLE conta ADD COLUMN conta_bancaria_id INTEGER'))

        if _sqlite_has_table(conn, 'contrato_consorcio'):
            if not _sqlite_has_column(conn, 'contrato_consorcio', 'perfil_financeiro_id'):
                conn.execute(text('ALTER TABLE contrato_consorcio ADD COLUMN perfil_financeiro_id INTEGER'))
            if not _sqlite_has_index(conn, 'ix_contrato_consorcio_perfil_financeiro_id'):
                conn.execute(text(
                    'CREATE INDEX ix_contrato_consorcio_perfil_financeiro_id '
                    'ON contrato_consorcio (perfil_financeiro_id)'
                ))
            if _sqlite_has_table(conn, 'perfil_financeiro'):
                pessoal_id = conn.execute(
                    text("SELECT id FROM perfil_financeiro WHERE nome = 'Pessoal' ORDER BY id LIMIT 1")
                ).scalar()
                if pessoal_id:
                    conn.execute(
                        text(
                            'UPDATE contrato_consorcio '
                            'SET perfil_financeiro_id = :perfil_id '
                            'WHERE perfil_financeiro_id IS NULL'
                        ),
                        {'perfil_id': pessoal_id},
                    )
