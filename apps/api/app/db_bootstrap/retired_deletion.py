"""Executable deletion support for retired legacy database tables."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3


RETIRED_TABLES = (
    "_codex_write_test",
    "report_data_mapping",
    "report_account",
    "budget_report_display_item",
    "driver_account_mapping",
    "driver_product",
    "driver_indicator",
    "driver_category",
    "control_item_subject_mapping",
    "forecast_line_binding",
    "forecast_workbench_layout",
    "assumption_value",
    "assumption_rule_template",
    "assumption_parameter",
    "scenario_catalog",
    "chart_template",
    "smart_report_definition",
    "pivot_aggregate_rule",
    "dept_product_mapping",
    "dept_name_alias",
    "expense_execution_monthly",
    "product_budget_component",
    "product_budget_component_template",
    "product_budget_config_package",
    "product_budget_component__official",
    "product_type",
)

RETIRED_EXPENSE_SYNC_META_KEYS = (
    "actual_import",
)


@dataclass(frozen=True)
class RetiredDeletionResult:
    db_path: Path
    deleted_tables: tuple[str, ...]
    missing_tables: tuple[str, ...]
    backup_path: Path | None


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def existing_retired_tables(db_path: Path) -> tuple[str, ...]:
    if not db_path.exists():
        return ()
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    existing = {str(row[0]) for row in rows}
    return tuple(table for table in RETIRED_TABLES if table in existing)


def drop_retired_tables(conn: sqlite3.Connection) -> tuple[str, ...]:
    """Drop retired tables from an open connection without creating a backup."""
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    existing = {str(row[0]) for row in rows}
    deleted = tuple(table for table in RETIRED_TABLES if table in existing)

    foreign_keys_row = conn.execute("PRAGMA foreign_keys").fetchone()
    foreign_keys_enabled = bool(foreign_keys_row and int(foreign_keys_row[0] or 0))
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for table in deleted:
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        if "expense_sync_meta" in existing and RETIRED_EXPENSE_SYNC_META_KEYS:
            placeholders = ",".join("?" for _ in RETIRED_EXPENSE_SYNC_META_KEYS)
            conn.execute(
                f"DELETE FROM expense_sync_meta WHERE sync_key IN ({placeholders})",
                RETIRED_EXPENSE_SYNC_META_KEYS,
            )
    finally:
        if foreign_keys_enabled:
            conn.execute("PRAGMA foreign_keys = ON")
    return deleted


def backup_database(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / f"{db_path.stem}_before_retired_delete_{_timestamp()}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def delete_retired_tables(
    db_path: Path,
    *,
    backup_root: Path,
    dry_run: bool = False,
) -> RetiredDeletionResult:
    existing = existing_retired_tables(db_path)
    missing = tuple(table for table in RETIRED_TABLES if table not in set(existing))
    if dry_run or not existing:
        return RetiredDeletionResult(
            db_path=db_path,
            deleted_tables=existing,
            missing_tables=missing,
            backup_path=None,
        )

    backup_path = backup_database(db_path, backup_root)
    conn = sqlite3.connect(db_path)
    try:
        drop_retired_tables(conn)
        conn.commit()
    finally:
        conn.close()
    return RetiredDeletionResult(
        db_path=db_path,
        deleted_tables=existing,
        missing_tables=missing,
        backup_path=backup_path,
    )
