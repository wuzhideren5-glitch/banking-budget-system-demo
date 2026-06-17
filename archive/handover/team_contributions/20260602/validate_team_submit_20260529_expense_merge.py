#!/usr/bin/env python3
"""Validate or apply TeamSubmit_20260529 expense schema changes.

Default mode is non-destructive: copy common.db to var/output/merge_validation,
run the idempotent schema ensure on the copy, and report what would be present.

Use --apply only after the DB impact sheet is confirmed. Apply mode backs up the
live common.db before creating the BI-AI mapping table and expense-import columns.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.db_bootstrap.expense import ensure_expense_actual_import_schema_sync  # noqa: E402


EXPECTED_BATCH_COLUMNS = ("import_kind",)
EXPECTED_DETAIL_COLUMNS = (
    "import_kind",
    "data_date",
    "journal_name",
    "serial_no",
    "line_desc",
    "fee_major_mapped",
    "fee_category_mapped",
    "budget_release_caliber_mapped",
    "manage_department2",
    "special_control_tag",
)
BI_SOURCE_NAMES = ("BI科目匹配表.xlsx", "BI科目mapping.xlsx")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")]


def _source_candidates(repo_root: Path) -> list[Path]:
    roots = (
        repo_root,
        repo_root / "resources" / "business_inputs",
        repo_root / "resources" / "download_template",
    )
    return [root / name for root in roots for name in BI_SOURCE_NAMES]


def _existing_bi_sources(repo_root: Path) -> list[Path]:
    return [path for path in _source_candidates(repo_root) if path.exists()]


def _summarize(db_path: Path) -> dict[str, object]:
    conn = sqlite3.connect(db_path)
    try:
        tables = _table_names(conn)
        batch_columns = _columns(conn, "expense_actual_import_batch")
        detail_columns = _columns(conn, "expense_actual_detail_raw")
        bi_indexes = (
            list(conn.execute("PRAGMA index_list(bi_ai_subject_mapping)").fetchall())
            if "bi_ai_subject_mapping" in tables
            else []
        )
        fk_errors = list(conn.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        conn.close()

    return {
        "db_path": str(db_path),
        "has_bi_ai_subject_mapping": "bi_ai_subject_mapping" in tables,
        "batch_columns_present": [col for col in EXPECTED_BATCH_COLUMNS if col in batch_columns],
        "detail_columns_present": [col for col in EXPECTED_DETAIL_COLUMNS if col in detail_columns],
        "bi_ai_indexes": bi_indexes,
        "foreign_key_errors": fk_errors,
    }


def _run_schema_ensure(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_expense_actual_import_schema_sync(conn)
        conn.commit()
    finally:
        conn.close()


def _print_summary(title: str, summary: dict[str, object]) -> None:
    print(title)
    print(f"  db_path: {summary['db_path']}")
    print(f"  has_bi_ai_subject_mapping: {summary['has_bi_ai_subject_mapping']}")
    print(f"  batch_columns_present: {summary['batch_columns_present']}")
    print(f"  detail_columns_present: {summary['detail_columns_present']}")
    print(f"  bi_ai_indexes: {summary['bi_ai_indexes']}")
    print(f"  foreign_key_errors: {summary['foreign_key_errors']}")


def dry_run(repo_root: Path, common_db: Path) -> None:
    output_dir = repo_root / "var" / "output" / "merge_validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    copy_path = output_dir / f"common_team_submit_20260529_schema_dry_run_{_timestamp()}.db"
    shutil.copy2(common_db, copy_path)
    _run_schema_ensure(copy_path)
    _print_summary("[dry-run] schema result on copied DB", _summarize(copy_path))


def apply(repo_root: Path, common_db: Path) -> None:
    backup_dir = repo_root / "var" / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"common_before_team_submit_20260529_expense_schema_{_timestamp()}.db"
    shutil.copy2(common_db, backup_path)
    print(f"[apply] live DB backup: {backup_path}")
    _run_schema_ensure(common_db)
    _print_summary("[apply] schema result on live DB", _summarize(common_db))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--common-db", type=Path, default=REPO_ROOT / "var" / "data" / "common.db")
    parser.add_argument("--apply", action="store_true", help="Apply schema changes to the live common.db after backing it up.")
    args = parser.parse_args()

    common_db = args.common_db.resolve()
    if not common_db.exists():
        raise SystemExit(f"common.db not found: {common_db}")

    sources = _existing_bi_sources(REPO_ROOT)
    print(f"BI source files: {[str(path.relative_to(REPO_ROOT)) for path in sources] or 'MISSING'}")
    if args.apply:
        apply(REPO_ROOT, common_db)
    else:
        dry_run(REPO_ROOT, common_db)
        _print_summary("[live] current live DB state", _summarize(common_db))


if __name__ == "__main__":
    main()
