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


def ensure_sqlite_schema_compat() -> None:
    """
    Garante compatibilidade de schema em SQLite quando o banco existe
    mas nĂŁo estĂĄ sob controle do Alembic (ex: criado por create_all / seeds).
    """
    engine = db.engine
    if engine.dialect.name != 'sqlite':
        return

    with engine.begin() as conn:
        if not _sqlite_has_table(conn, 'veiculo_regra_manutencao_km'):
            return
        if not _sqlite_has_column(conn, 'veiculo_regra_manutencao_km', 'meses_intervalo'):
            conn.execute(text('ALTER TABLE veiculo_regra_manutencao_km ADD COLUMN meses_intervalo INTEGER'))
