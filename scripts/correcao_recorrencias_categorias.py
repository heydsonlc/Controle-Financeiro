"""REC-AUDIT-2: correcao controlada de categorias em recorrencias.

Uso:
    python scripts/correcao_recorrencias_categorias.py --dry-run
    python scripts/correcao_recorrencias_categorias.py --apply

O script e intencionalmente restrito ao ajuste autorizado:
- ItemDespesa recorrente id=46
- categoria destino "Serviços Domésticos"
- contas pendentes vinculadas, se a tabela `conta` tiver categoria_id

Em bancos antigos sem `conta.categoria_id`, a categoria das contas e derivada do
ItemDespesa, entao o script nao tenta usar coluna inexistente.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "gastos.db"
BACKUP_DIR = ROOT / "data" / "backups"

TARGET_ITEM_ID = 46
TARGET_CATEGORY_NAME = "Serviços Domésticos"
PAID_STATUSES = {"pago", "baixado", "realizado", "efetivado"}


@dataclass
class AuditResult:
    item: sqlite3.Row
    current_category: sqlite3.Row | None
    target_category: sqlite3.Row
    eligible_accounts: list[sqlite3.Row]
    blocked_accounts: list[sqlite3.Row]
    schema: dict[str, set[str]]
    pending_change: bool


def connect(db_path: Path, *, readonly: bool) -> sqlite3.Connection:
    if readonly:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def require_tables(conn: sqlite3.Connection) -> None:
    missing = [
        table
        for table in ("item_despesa", "categoria", "conta")
        if not table_exists(conn, table)
    ]
    if missing:
        raise RuntimeError(f"Tabelas obrigatorias ausentes: {', '.join(missing)}")


def load_schema(conn: sqlite3.Connection) -> dict[str, set[str]]:
    return {
        "item_despesa": columns(conn, "item_despesa"),
        "categoria": columns(conn, "categoria"),
        "conta": columns(conn, "conta"),
        "movimento_financeiro": columns(conn, "movimento_financeiro"),
    }


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def get_category_by_id(conn: sqlite3.Connection, categoria_id: int | None) -> sqlite3.Row | None:
    if categoria_id is None:
        return None
    return conn.execute(
        "SELECT id, nome, ativo FROM categoria WHERE id=?",
        (categoria_id,),
    ).fetchone()


def get_target_category(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        "SELECT id, nome, ativo FROM categoria WHERE nome=?",
        (TARGET_CATEGORY_NAME,),
    ).fetchone()
    if not row:
        raise RuntimeError(
            f"Categoria destino nao encontrada: {TARGET_CATEGORY_NAME}. "
            "Nenhuma categoria sera criada automaticamente."
        )
    if int(row["ativo"] or 0) != 1:
        raise RuntimeError(f"Categoria destino esta inativa: {TARGET_CATEGORY_NAME}")
    return row


def validate_manual_recurrence(item: sqlite3.Row, item_cols: set[str]) -> None:
    if not item:
        raise RuntimeError(f"Recorrencia id={TARGET_ITEM_ID} nao encontrada")
    if int(item["recorrente"] or 0) != 1:
        raise RuntimeError(f"Item id={TARGET_ITEM_ID} nao e recorrente")
    if (item["tipo"] or "") == "Agregador":
        raise RuntimeError(f"Item id={TARGET_ITEM_ID} e Agregador/cartao; bloqueado")

    origem_cols = [col for col in ("origem_tipo", "origem_id", "origem_contexto") if col in item_cols]
    if origem_cols and any(item[col] not in (None, "") for col in origem_cols):
        raise RuntimeError(
            f"Item id={TARGET_ITEM_ID} tem origem automatica preenchida; correcao manual bloqueada"
        )


def movement_condition(conn: sqlite3.Connection, mov_cols: set[str]) -> str:
    if table_exists(conn, "movimento_financeiro") and "conta_id" in mov_cols:
        return (
            " AND NOT EXISTS ("
            "SELECT 1 FROM movimento_financeiro mf WHERE mf.conta_id = c.id"
            ")"
        )
    return ""


def audit(conn: sqlite3.Connection) -> AuditResult:
    require_tables(conn)
    schema = load_schema(conn)

    item_cols = schema["item_despesa"]
    required_item_cols = {"id", "nome", "tipo", "categoria_id", "recorrente"}
    missing_item_cols = required_item_cols - item_cols
    if missing_item_cols:
        raise RuntimeError(f"Colunas obrigatorias ausentes em item_despesa: {sorted(missing_item_cols)}")

    item = conn.execute(
        "SELECT * FROM item_despesa WHERE id=?",
        (TARGET_ITEM_ID,),
    ).fetchone()
    validate_manual_recurrence(item, item_cols)

    current_category = get_category_by_id(conn, item["categoria_id"])
    target_category = get_target_category(conn)

    conta_cols = schema["conta"]
    required_conta_cols = {"id", "item_despesa_id", "status_pagamento", "data_pagamento"}
    missing_conta_cols = required_conta_cols - conta_cols
    if missing_conta_cols:
        raise RuntimeError(f"Colunas obrigatorias ausentes em conta: {sorted(missing_conta_cols)}")

    fatura_condition = ""
    if "is_fatura_cartao" in conta_cols:
        fatura_condition = " AND COALESCE(c.is_fatura_cartao, 0)=0"

    movement_sql = movement_condition(conn, schema["movimento_financeiro"])
    eligible_sql = (
        "SELECT c.* FROM conta c "
        "WHERE c.item_despesa_id=? "
        f"{fatura_condition} "
        "AND c.data_pagamento IS NULL "
        "AND LOWER(COALESCE(c.status_pagamento, '')) NOT IN "
        f"({','.join(['?'] * len(PAID_STATUSES))}) "
        f"{movement_sql} "
        "ORDER BY c.data_vencimento, c.id"
    )
    eligible_accounts = conn.execute(
        eligible_sql,
        (TARGET_ITEM_ID, *sorted(PAID_STATUSES)),
    ).fetchall()

    blocked_sql = (
        "SELECT c.* FROM conta c "
        "WHERE c.item_despesa_id=? "
        f"{fatura_condition} "
        "AND ("
        "c.data_pagamento IS NOT NULL "
        "OR LOWER(COALESCE(c.status_pagamento, '')) IN "
        f"({','.join(['?'] * len(PAID_STATUSES))})"
        ") "
        "ORDER BY c.data_vencimento, c.id"
    )
    blocked_accounts = conn.execute(
        blocked_sql,
        (TARGET_ITEM_ID, *sorted(PAID_STATUSES)),
    ).fetchall()

    pending_change = int(item["categoria_id"] or 0) != int(target_category["id"])
    return AuditResult(
        item=item,
        current_category=current_category,
        target_category=target_category,
        eligible_accounts=eligible_accounts,
        blocked_accounts=blocked_accounts,
        schema=schema,
        pending_change=pending_change,
    )


def print_schema_notes(result: AuditResult) -> None:
    missing = {
        "item_despesa": [
            col
            for col in ("categoria_cartao_id", "origem_tipo", "origem_id", "origem_contexto", "conta_bancaria_id")
            if col not in result.schema["item_despesa"]
        ],
        "categoria": [
            col
            for col in ("sistemica", "codigo_sistema", "modulo_origem", "bloquear_edicao", "bloquear_exclusao")
            if col not in result.schema["categoria"]
        ],
        "conta": ["categoria_id"] if "categoria_id" not in result.schema["conta"] else [],
    }
    print("Schema:")
    for table, cols in missing.items():
        if cols:
            print(f"- {table}: colunas recentes ausentes: {', '.join(cols)}")
        else:
            print(f"- {table}: OK para esta correcao")


def print_audit(result: AuditResult, *, mode: str) -> None:
    item = result.item
    current = result.current_category
    target = result.target_category
    print(f"Modo: {mode}")
    print(f"Recorrencia: id={item['id']} nome={item['nome']} valor={item['valor']}")
    print(f"Categoria atual: {current['nome'] if current else '(sem categoria)'} (id={item['categoria_id']})")
    print(f"Categoria destino: {target['nome']} (id={target['id']})")
    print(f"Contas pendentes elegiveis: {len(result.eligible_accounts)}")
    if result.eligible_accounts:
        primeiras = [
            str(row["data_vencimento"] if "data_vencimento" in row.keys() else row["id"])
            for row in result.eligible_accounts[:5]
        ]
        print(f"Primeiros vencimentos afetados: {', '.join(primeiras)}")
    print(f"Contas pagas/bloqueadas: {len(result.blocked_accounts)}")
    if "categoria_id" not in result.schema["conta"]:
        print("Observacao: conta.categoria_id nao existe; contas pendentes usam a categoria da recorrencia mestre.")
    if not result.pending_change:
        print("Resultado: nenhuma alteracao pendente para id=46.")


def create_backup(db_path: Path) -> Path:
    if not db_path.exists():
        raise RuntimeError(f"Banco nao encontrado: {db_path}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    backup_path = BACKUP_DIR / f"gastos_antes_rec_audit_2_{stamp}.db"
    shutil.copy2(db_path, backup_path)
    if not backup_path.exists() or backup_path.stat().st_size <= 0:
        raise RuntimeError("Falha ao criar backup obrigatorio")
    return backup_path


def apply_correction(db_path: Path) -> Path | None:
    backup_path: Path | None = None
    conn = connect(db_path, readonly=False)
    try:
        result = audit(conn)
        print_audit(result, mode="apply-validacao")
        print_schema_notes(result)

        if result.blocked_accounts:
            raise RuntimeError("Existem contas pagas/bloqueadas vinculadas; aplicacao abortada")
        if not result.pending_change:
            print("Nada a aplicar.")
            return None

        backup_path = create_backup(db_path)
        print(f"Backup criado: {backup_path}")

        conn.execute("BEGIN")
        result = audit(conn)
        if result.blocked_accounts:
            raise RuntimeError("Validacao transacional encontrou contas bloqueadas; rollback")
        if not result.pending_change:
            conn.rollback()
            print("Nada a aplicar apos revalidacao.")
            return backup_path

        conn.execute(
            "UPDATE item_despesa SET categoria_id=? WHERE id=?",
            (int(result.target_category["id"]), TARGET_ITEM_ID),
        )

        contas_atualizadas = 0
        if "categoria_id" in result.schema["conta"] and result.eligible_accounts:
            ids = [int(row["id"]) for row in result.eligible_accounts]
            placeholders = ",".join(["?"] * len(ids))
            conn.execute(
                f"UPDATE conta SET categoria_id=? WHERE id IN ({placeholders})",
                (int(result.target_category["id"]), *ids),
            )
            contas_atualizadas = len(ids)

        conn.commit()
        print(f"Aplicado: recorrencia id=46 atualizada; contas com categoria_id atualizadas={contas_atualizadas}")
        return backup_path
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="REC-AUDIT-2 correcao controlada de recorrencia.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Caminho do banco SQLite alvo.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria alterado sem gravar.")
    parser.add_argument("--apply", action="store_true", help="Aplica a correcao com backup e transacao.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    if args.apply and args.dry_run:
        raise SystemExit("Use apenas uma flag: --dry-run ou --apply")
    if not args.apply:
        args.dry_run = True

    if args.dry_run:
        conn = connect(db_path, readonly=True)
        try:
            result = audit(conn)
            print_audit(result, mode="dry-run")
            print_schema_notes(result)
            return 0
        finally:
            conn.close()

    backup = apply_correction(db_path)
    if backup:
        print(f"BACKUP={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
