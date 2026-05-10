from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3

from app.db_paths import common_db_path, list_budget_database_files
from app.init_db import migrate_budget_data_product_code
from app.schemas import ProductScopeMigrationFileItem


def _parse_year_from_budget_filename(name: str) -> int | None:
    m = re.match(r"budget_(\d{4})\.db$", name)
    if not m:
        return None
    return int(m.group(1))


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _product_scope_table_exists(conn: sqlite3.Connection, alias: str) -> bool:
    sm = "sqlite_master" if alias == "main" else f"{alias}.sqlite_master"
    cur = conn.execute(
        f"SELECT 1 FROM {sm} WHERE type='table' AND name='budget_data'"
    )
    return cur.fetchone() is not None


def _product_type_codes_sync() -> list[str]:
    path = common_db_path()
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.execute("SELECT product_code FROM product_type ORDER BY product_code")
        return [str(r[0]) for r in cur.fetchall()]
    finally:
        conn.close()


def _ensure_legacy_budget_data_has_product_code(budget_path: Path) -> None:
    """Older budget_*.db files may have budget_data without product_code; migrate idempotently."""
    if not budget_path.exists():
        return
    migrate_budget_data_product_code(budget_path, common_db_path())


def preview_insert_single_to_all_rows(
    data_acct_code: str,
    old_pc: str,
) -> tuple[int, list[ProductScopeMigrationFileItem]]:
    code_u = data_acct_code.strip().upper()
    old = old_pc.strip().upper()
    products = _product_type_codes_sync()
    other = [p for p in products if p != old]
    files = list_budget_database_files()
    items: list[ProductScopeMigrationFileItem] = []
    total = 0
    for fp in files:
        if not fp.exists():
            continue
        _ensure_legacy_budget_data_has_product_code(fp)
        y = _parse_year_from_budget_filename(fp.name)
        conn = sqlite3.connect(str(fp))
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            if not _product_scope_table_exists(conn, "main"):
                items.append(
                    ProductScopeMigrationFileItem(
                        file_name=fp.name,
                        file_year=y,
                        rows_to_insert=0,
                        rows_to_delete=0,
                    )
                )
                continue
            cur = conn.execute(
                """
                SELECT DISTINCT version_id, period_id, budget_actual
                FROM budget_data
                WHERE data_acct_code = ? AND product_code = ?
                """,
                (code_u, old),
            )
            grid = cur.fetchall()
            n_ins = 0
            for q in other:
                for vid, pid, ba in grid:
                    cur = conn.execute(
                        """
                        SELECT 1 FROM budget_data
                        WHERE data_acct_code = ? AND product_code = ?
                          AND period_id = ? AND version_id = ? AND budget_actual = ?
                        """,
                        (code_u, q, pid, vid, ba),
                    )
                    if cur.fetchone():
                        continue
                    n_ins += 1
            total += n_ins
            items.append(
                ProductScopeMigrationFileItem(
                    file_name=fp.name,
                    file_year=y,
                    rows_to_insert=n_ins,
                    rows_to_delete=0,
                )
            )
        finally:
            conn.close()
    return total, items


def preview_delete_all_to_single_rows(
    data_acct_code: str,
    keep_pc: str,
) -> tuple[int, list[ProductScopeMigrationFileItem]]:
    code_u = data_acct_code.strip().upper()
    keep = keep_pc.strip().upper()
    files = list_budget_database_files()
    items: list[ProductScopeMigrationFileItem] = []
    total = 0
    for fp in files:
        if not fp.exists():
            continue
        _ensure_legacy_budget_data_has_product_code(fp)
        y = _parse_year_from_budget_filename(fp.name)
        conn = sqlite3.connect(str(fp))
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            if not _product_scope_table_exists(conn, "main"):
                items.append(
                    ProductScopeMigrationFileItem(
                        file_name=fp.name,
                        file_year=y,
                        rows_to_insert=0,
                        rows_to_delete=0,
                    )
                )
                continue
            cur = conn.execute(
                """
                SELECT COUNT(*) FROM budget_data
                WHERE data_acct_code = ? AND product_code != ?
                """,
                (code_u, keep),
            )
            n_del = int((cur.fetchone() or [0])[0] or 0)
            total += n_del
            items.append(
                ProductScopeMigrationFileItem(
                    file_name=fp.name,
                    file_year=y,
                    rows_to_insert=0,
                    rows_to_delete=n_del,
                )
            )
        finally:
            conn.close()
    return total, items


def migrate_single_to_all_budget_data(
    data_acct_code: str,
    old_pc: str,
) -> tuple[int, list[ProductScopeMigrationFileItem]]:
    code_u = data_acct_code.strip().upper()
    old = old_pc.strip().upper()
    products = _product_type_codes_sync()
    other = [p for p in products if p != old]
    files = list_budget_database_files()
    if not other or not files:
        return 0, []
    now = _iso_now()
    per_file: list[ProductScopeMigrationFileItem] = []
    total_ins = 0
    for fp in files:
        if not fp.exists():
            continue
        _ensure_legacy_budget_data_has_product_code(fp)
        y = _parse_year_from_budget_filename(fp.name)
        conn = sqlite3.connect(str(fp))
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            if not _product_scope_table_exists(conn, "main"):
                per_file.append(
                    ProductScopeMigrationFileItem(
                        file_name=fp.name,
                        file_year=y,
                        rows_to_insert=0,
                        rows_to_delete=0,
                    )
                )
                continue
            conn.execute("BEGIN")
            try:
                cur = conn.execute(
                    """
                    SELECT DISTINCT version_id, period_id, budget_actual
                    FROM budget_data
                    WHERE data_acct_code = ? AND product_code = ?
                    """,
                    (code_u, old),
                )
                grid = cur.fetchall()
                n_ins = 0
                for q in other:
                    for vid, pid, ba in grid:
                        cur = conn.execute(
                            """
                            SELECT 1 FROM budget_data
                            WHERE data_acct_code = ? AND product_code = ?
                              AND period_id = ? AND version_id = ? AND budget_actual = ?
                            """,
                            (code_u, q, pid, vid, ba),
                        )
                        if cur.fetchone():
                            continue
                        conn.execute(
                            """
                            INSERT INTO budget_data (
                              data_acct_code, product_code, period_id, budget_actual, version_id,
                              value, need_calc, create_time, update_time
                            ) VALUES (?,?,?,?,?,?,?,?,?)
                            """,
                            (code_u, q, pid, ba, vid, 0.0, 1, now, now),
                        )
                        n_ins += 1
                total_ins += n_ins
                per_file.append(
                    ProductScopeMigrationFileItem(
                        file_name=fp.name,
                        file_year=y,
                        rows_to_insert=n_ins,
                        rows_to_delete=0,
                    )
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()
    return total_ins, per_file


def migrate_all_to_single_budget_data(
    data_acct_code: str,
    keep_pc: str,
) -> tuple[int, list[ProductScopeMigrationFileItem]]:
    code_u = data_acct_code.strip().upper()
    keep = keep_pc.strip().upper()
    files = list_budget_database_files()
    if not files:
        return 0, []
    per_file: list[ProductScopeMigrationFileItem] = []
    total_del = 0
    for fp in files:
        if not fp.exists():
            continue
        _ensure_legacy_budget_data_has_product_code(fp)
        y = _parse_year_from_budget_filename(fp.name)
        conn = sqlite3.connect(str(fp))
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            if not _product_scope_table_exists(conn, "main"):
                per_file.append(
                    ProductScopeMigrationFileItem(
                        file_name=fp.name,
                        file_year=y,
                        rows_to_insert=0,
                        rows_to_delete=0,
                    )
                )
                continue
            try:
                conn.execute("BEGIN")
                cur = conn.execute(
                    """
                    SELECT COUNT(*) FROM budget_data
                    WHERE data_acct_code = ? AND product_code != ?
                    """,
                    (code_u, keep),
                )
                n_del = int((cur.fetchone() or [0])[0] or 0)
                conn.execute(
                    """
                    DELETE FROM budget_data
                    WHERE data_acct_code = ? AND product_code != ?
                    """,
                    (code_u, keep),
                )
                total_del += n_del
                per_file.append(
                    ProductScopeMigrationFileItem(
                        file_name=fp.name,
                        file_year=y,
                        rows_to_insert=0,
                        rows_to_delete=n_del,
                    )
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()
    return total_del, per_file
