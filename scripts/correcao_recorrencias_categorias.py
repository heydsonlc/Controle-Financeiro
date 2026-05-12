"""REC-AUDIT-3: correção controlada de categorias em recorrências.

Uso:
    python scripts/correcao_recorrencias_categorias.py --dry-run
    python scripts/correcao_recorrencias_categorias.py --apply

O script é intencionalmente restrito aos ajustes autorizados:
- ItemDespesa recorrente id=43: Refeições e Delivery -> Serviços Domésticos
- ItemDespesa recorrente id=44: Atividades Extra-Curriculares -> Serviços Domésticos
- ItemDespesa recorrente id=47: Refeições e Delivery -> Serviços Domésticos

Em bancos sem `conta.categoria_id`, a categoria das contas é derivada do
ItemDespesa; nesse caso o script altera apenas a recorrência mestre.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "gastos.db"
BACKUP_DIR = ROOT / "data" / "backups"

PAID_STATUSES = {"pago", "baixado", "realizado", "efetivado"}


@dataclass(frozen=True)
class Correction:
    item_id: int
    expected_current_category: str
    target_category: str = "Serviços Domésticos"


@dataclass
class AuditResult:
    correction: Correction
    item: sqlite3.Row
    current_category: sqlite3.Row | None
    target_category: sqlite3.Row
    eligible_accounts: list[sqlite3.Row]
    blocked_accounts: list[sqlite3.Row]
    movement_count: int
    card_launch_count: int
    paid_invoice_count: int
    schema: dict[str, set[str]]
    pending_change: bool


TARGET_CORRECTIONS = (
    Correction(43, "Refeições e Delivery"),
    Correction(44, "Atividades Extra-Curriculares"),
    Correction(47, "Refeições e Delivery"),
)


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
        raise RuntimeError(f"Tabelas obrigatórias ausentes: {', '.join(missing)}")


def load_schema(conn: sqlite3.Connection) -> dict[str, set[str]]:
    return {
        "item_despesa": columns(conn, "item_despesa"),
        "categoria": columns(conn, "categoria"),
        "conta": columns(conn, "conta"),
        "movimento_financeiro": columns(conn, "movimento_financeiro"),
        "lancamento_agregado": columns(conn, "lancamento_agregado"),
    }


def get_category_by_id(conn: sqlite3.Connection, categoria_id: int | None) -> sqlite3.Row | None:
    if categoria_id is None:
        return None
    return conn.execute(
        "SELECT id, nome, ativo FROM categoria WHERE id=?",
        (categoria_id,),
    ).fetchone()


def get_category_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT id, nome, ativo FROM categoria WHERE nome=?",
        (name,),
    ).fetchone()
    if not row:
        raise RuntimeError(
            f"Categoria destino não encontrada: {name}. "
            "Nenhuma categoria será criada automaticamente."
        )
    if int(row["ativo"] or 0) != 1:
        raise RuntimeError(f"Categoria destino está inativa: {name}")
    return row


def validate_manual_recurrence(
    correction: Correction,
    item: sqlite3.Row | None,
    item_cols: set[str],
) -> None:
    if not item:
        raise RuntimeError(f"Recorrência id={correction.item_id} não encontrada")
    if int(item["recorrente"] or 0) != 1:
        raise RuntimeError(f"Item id={correction.item_id} não é recorrente")
    if (item["tipo"] or "") == "Agregador":
        raise RuntimeError(f"Item id={correction.item_id} é Agregador/cartão; bloqueado")

    origem_cols = [col for col in ("origem_tipo", "origem_id", "origem_contexto") if col in item_cols]
    if origem_cols and any(item[col] not in (None, "") for col in origem_cols):
        raise RuntimeError(
            f"Item id={correction.item_id} tem origem automática preenchida; correção manual bloqueada"
        )


def count_movements_for_accounts(
    conn: sqlite3.Connection,
    account_ids: list[int],
    mov_cols: set[str],
) -> int:
    if not account_ids or not table_exists(conn, "movimento_financeiro") or "conta_id" not in mov_cols:
        return 0
    placeholders = ",".join(["?"] * len(account_ids))
    row = conn.execute(
        f"SELECT COUNT(*) AS total FROM movimento_financeiro WHERE conta_id IN ({placeholders})",
        account_ids,
    ).fetchone()
    return int(row["total"] or 0)


def count_card_launches(conn: sqlite3.Connection, correction: Correction, lanc_cols: set[str]) -> int:
    if not table_exists(conn, "lancamento_agregado") or "item_despesa_id" not in lanc_cols:
        return 0
    row = conn.execute(
        "SELECT COUNT(*) AS total FROM lancamento_agregado WHERE item_despesa_id=?",
        (correction.item_id,),
    ).fetchone()
    return int(row["total"] or 0)


def count_paid_invoices(accounts: list[sqlite3.Row], conta_cols: set[str]) -> int:
    if "is_fatura_cartao" not in conta_cols:
        return 0
    total = 0
    for row in accounts:
        is_invoice = int(row["is_fatura_cartao"] or 0) == 1
        status_invoice = str(row["status_fatura"] or "").lower() if "status_fatura" in conta_cols else ""
        if is_invoice and status_invoice in {"paga", "pago", "fechada_paga"}:
            total += 1
    return total


def audit_one(
    conn: sqlite3.Connection,
    correction: Correction,
    schema: dict[str, set[str]],
) -> AuditResult:
    item_cols = schema["item_despesa"]
    required_item_cols = {"id", "nome", "tipo", "categoria_id", "recorrente"}
    missing_item_cols = required_item_cols - item_cols
    if missing_item_cols:
        raise RuntimeError(f"Colunas obrigatórias ausentes em item_despesa: {sorted(missing_item_cols)}")

    item = conn.execute(
        "SELECT * FROM item_despesa WHERE id=?",
        (correction.item_id,),
    ).fetchone()
    validate_manual_recurrence(correction, item, item_cols)

    current_category = get_category_by_id(conn, item["categoria_id"])
    target_category = get_category_by_name(conn, correction.target_category)
    current_name = current_category["nome"] if current_category else None
    target_id = int(target_category["id"])
    current_id = int(item["categoria_id"] or 0)

    if current_id != target_id and current_name != correction.expected_current_category:
        raise RuntimeError(
            f"Item id={correction.item_id} está com categoria inesperada: "
            f"{current_name or '(sem categoria)'}. Esperado para correção: "
            f"{correction.expected_current_category}."
        )

    conta_cols = schema["conta"]
    required_conta_cols = {"id", "item_despesa_id", "status_pagamento", "data_pagamento"}
    missing_conta_cols = required_conta_cols - conta_cols
    if missing_conta_cols:
        raise RuntimeError(f"Colunas obrigatórias ausentes em conta: {sorted(missing_conta_cols)}")

    all_accounts = conn.execute(
        "SELECT * FROM conta WHERE item_despesa_id=? ORDER BY data_vencimento, id",
        (correction.item_id,),
    ).fetchall()
    eligible_accounts: list[sqlite3.Row] = []
    blocked_accounts: list[sqlite3.Row] = []

    for account in all_accounts:
        status = str(account["status_pagamento"] or "").lower()
        has_payment = account["data_pagamento"] not in (None, "")
        is_paid = has_payment or status in PAID_STATUSES
        if is_paid:
            blocked_accounts.append(account)
        else:
            eligible_accounts.append(account)

    movement_count = count_movements_for_accounts(
        conn,
        [int(row["id"]) for row in all_accounts],
        schema["movimento_financeiro"],
    )
    card_launch_count = count_card_launches(conn, correction, schema["lancamento_agregado"])
    paid_invoice_count = count_paid_invoices(all_accounts, conta_cols)

    pending_change = current_id != target_id
    return AuditResult(
        correction=correction,
        item=item,
        current_category=current_category,
        target_category=target_category,
        eligible_accounts=eligible_accounts,
        blocked_accounts=blocked_accounts,
        movement_count=movement_count,
        card_launch_count=card_launch_count,
        paid_invoice_count=paid_invoice_count,
        schema=schema,
        pending_change=pending_change,
    )


def audit_all(conn: sqlite3.Connection) -> list[AuditResult]:
    require_tables(conn)
    schema = load_schema(conn)
    return [audit_one(conn, correction, schema) for correction in TARGET_CORRECTIONS]


def print_schema_notes(results: list[AuditResult]) -> None:
    if not results:
        return
    schema = results[0].schema
    missing = {
        "item_despesa": [
            col
            for col in ("categoria_cartao_id", "origem_tipo", "origem_id", "origem_contexto")
            if col not in schema["item_despesa"]
        ],
        "categoria": [
            col
            for col in ("sistemica", "codigo_sistema", "modulo_origem", "bloquear_edicao", "bloquear_exclusao")
            if col not in schema["categoria"]
        ],
        "conta": ["categoria_id"] if "categoria_id" not in schema["conta"] else [],
    }
    print("Schema:")
    for table, cols in missing.items():
        if cols:
            print(f"- {table}: colunas ausentes para contexto amplo: {', '.join(cols)}")
        else:
            print(f"- {table}: OK para esta correção")


def print_audit(results: list[AuditResult], *, mode: str) -> None:
    print(f"Modo: {mode}")
    pending_total = 0
    for result in results:
        item = result.item
        current = result.current_category
        target = result.target_category
        pending_total += int(result.pending_change)
        print("")
        print(f"Recorrência: id={item['id']} nome={item['nome']} valor={item['valor']}")
        print(f"Categoria atual: {current['nome'] if current else '(sem categoria)'} (id={item['categoria_id']})")
        print(f"Categoria destino: {target['nome']} (id={target['id']})")
        print(f"Contas pendentes elegíveis: {len(result.eligible_accounts)}")
        if result.eligible_accounts:
            primeiras = [
                str(row["data_vencimento"] if "data_vencimento" in row.keys() else row["id"])
                for row in result.eligible_accounts[:5]
            ]
            print(f"Primeiros vencimentos afetados: {', '.join(primeiras)}")
        print(f"Contas pagas/bloqueadas: {len(result.blocked_accounts)}")
        print(f"Movimentos financeiros vinculados: {result.movement_count}")
        print(f"Lançamentos de cartão vinculados: {result.card_launch_count}")
        print(f"Faturas pagas vinculadas: {result.paid_invoice_count}")
        if "categoria_id" not in result.schema["conta"]:
            print("Observação: conta.categoria_id não existe; contas usam a categoria da recorrência mestre.")
        if not result.pending_change:
            print(f"Resultado: nenhuma alteração pendente para id={item['id']}.")
    print("")
    print(f"Total de recorrências com alteração pendente: {pending_total}")


def create_backup(db_path: Path) -> Path:
    if not db_path.exists():
        raise RuntimeError(f"Banco não encontrado: {db_path}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    backup_path = BACKUP_DIR / f"gastos_antes_rec_audit_3_{stamp}.db"
    shutil.copy2(db_path, backup_path)
    if not backup_path.exists() or backup_path.stat().st_size <= 0:
        raise RuntimeError("Falha ao criar backup obrigatório")
    return backup_path


def validate_apply_allowed(results: list[AuditResult]) -> None:
    for result in results:
        if result.blocked_accounts:
            raise RuntimeError(
                f"Item id={result.correction.item_id} tem contas pagas/bloqueadas vinculadas; aplicação abortada"
            )
        if result.movement_count:
            raise RuntimeError(
                f"Item id={result.correction.item_id} tem movimento financeiro vinculado; aplicação abortada"
            )
        if result.card_launch_count:
            raise RuntimeError(
                f"Item id={result.correction.item_id} tem lançamento de cartão vinculado; aplicação abortada"
            )
        if result.paid_invoice_count:
            raise RuntimeError(
                f"Item id={result.correction.item_id} tem fatura paga vinculada; aplicação abortada"
            )


def apply_corrections(db_path: Path) -> Path | None:
    conn = connect(db_path, readonly=False)
    try:
        results = audit_all(conn)
        print_audit(results, mode="apply-validação")
        print_schema_notes(results)
        validate_apply_allowed(results)

        pending = [result for result in results if result.pending_change]
        if not pending:
            print("Nada a aplicar.")
            return None

        backup_path = create_backup(db_path)
        print(f"Backup criado: {backup_path}")

        conn.execute("BEGIN")
        results = audit_all(conn)
        validate_apply_allowed(results)
        pending = [result for result in results if result.pending_change]
        if not pending:
            conn.rollback()
            print("Nada a aplicar após revalidação.")
            return backup_path

        contas_atualizadas = 0
        for result in pending:
            conn.execute(
                "UPDATE item_despesa SET categoria_id=? WHERE id=?",
                (int(result.target_category["id"]), result.correction.item_id),
            )

            if "categoria_id" in result.schema["conta"] and result.eligible_accounts:
                ids = [int(row["id"]) for row in result.eligible_accounts]
                placeholders = ",".join(["?"] * len(ids))
                conn.execute(
                    f"UPDATE conta SET categoria_id=? WHERE id IN ({placeholders})",
                    (int(result.target_category["id"]), *ids),
                )
                contas_atualizadas += len(ids)

        conn.commit()
        ids = ", ".join(str(result.correction.item_id) for result in pending)
        print(f"Aplicado: recorrências atualizadas: {ids}; contas com categoria_id atualizadas={contas_atualizadas}")
        return backup_path
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="REC-AUDIT-3 correção controlada de recorrências.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Caminho do banco SQLite alvo.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria alterado sem gravar.")
    parser.add_argument("--apply", action="store_true", help="Aplica a correção com backup e transação.")
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
            results = audit_all(conn)
            print_audit(results, mode="dry-run")
            print_schema_notes(results)
            return 0
        finally:
            conn.close()

    backup = apply_corrections(db_path)
    if backup:
        print(f"BACKUP={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
