from __future__ import annotations

import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings
from app.db_paths import budget_db_path, common_db_path
from app.init_db import ensure_databases


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_all(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql, params)
    return list(cur.fetchall())


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_data_dictionary(common_conn: sqlite3.Connection) -> list[dict]:
    now = _now_iso()
    rows: list[dict] = []
    data_accounts = _fetch_all(
        common_conn,
        """
        SELECT data_acct_code, data_acct_name, value_type
        FROM data_account
        ORDER BY data_acct_code
        """,
    )
    for r in data_accounts:
        rows.append(
            {
                "entity_type": "data_account",
                "entity_code": r["data_acct_code"],
                "entity_name": r["data_acct_name"],
                "source_table": "data_account",
                "parent_code": "",
                "level": "",
                "value_type": r["value_type"] or "",
                "description": "",
                "status": "active",
                "last_verified_at": now,
            }
        )

    report_accounts = _fetch_all(
        common_conn,
        """
        SELECT report_acct_code, report_acct_name, parent_code, level
        FROM report_account
        ORDER BY report_acct_code
        """,
    )
    for r in report_accounts:
        rows.append(
            {
                "entity_type": "report_account",
                "entity_code": r["report_acct_code"],
                "entity_name": r["report_acct_name"],
                "source_table": "report_account",
                "parent_code": r["parent_code"] or "",
                "level": r["level"] or "",
                "value_type": "",
                "description": "",
                "status": "active",
                "last_verified_at": now,
            }
        )

    dept_accounts = _fetch_all(
        common_conn,
        """
        SELECT dept_code, dept_name, parent_code, level
        FROM dept_account
        ORDER BY dept_code
        """,
    )
    for r in dept_accounts:
        rows.append(
            {
                "entity_type": "dept_account",
                "entity_code": r["dept_code"],
                "entity_name": r["dept_name"],
                "source_table": "dept_account",
                "parent_code": r["parent_code"] or "",
                "level": r["level"] or "",
                "value_type": "",
                "description": "",
                "status": "active",
                "last_verified_at": now,
            }
        )

    products = _fetch_all(
        common_conn,
        """
        SELECT product_code, product_name
        FROM product_type
        ORDER BY product_code
        """,
    )
    for r in products:
        rows.append(
            {
                "entity_type": "product_type",
                "entity_code": r["product_code"],
                "entity_name": r["product_name"],
                "source_table": "product_type",
                "parent_code": "",
                "level": "",
                "value_type": "",
                "description": "",
                "status": "active",
                "last_verified_at": now,
            }
        )
    return rows


def _build_synonyms_seed(common_conn: sqlite3.Connection) -> list[dict]:
    rows: list[dict] = []
    for r in _fetch_all(
        common_conn,
        "SELECT dept_code, dept_name FROM dept_account ORDER BY dept_code",
    ):
        dept_name = r["dept_name"]
        rows.append(
            {
                "domain": "department",
                "term": dept_name,
                "normalized_type": "dept_account",
                "normalized_code": r["dept_code"],
                "normalized_name": dept_name,
                "confidence": "1.00",
                "requires_confirmation": "false",
                "notes": "exact_match",
            }
        )
        if dept_name.endswith("部") and len(dept_name) > 1:
            rows.append(
                {
                    "domain": "department",
                    "term": dept_name[:-1],
                    "normalized_type": "dept_account",
                    "normalized_code": r["dept_code"],
                    "normalized_name": dept_name,
                    "confidence": "0.88",
                    "requires_confirmation": "true",
                    "notes": "auto_alias_remove_suffix",
                }
            )

    for r in _fetch_all(
        common_conn,
        "SELECT product_code, product_name FROM product_type ORDER BY product_code",
    ):
        rows.append(
            {
                "domain": "product",
                "term": r["product_name"],
                "normalized_type": "product_type",
                "normalized_code": r["product_code"],
                "normalized_name": r["product_name"],
                "confidence": "1.00",
                "requires_confirmation": "false",
                "notes": "exact_match",
            }
        )

    for r in _fetch_all(
        common_conn,
        "SELECT data_acct_code, data_acct_name FROM data_account ORDER BY data_acct_code",
    ):
        rows.append(
            {
                "domain": "data_account",
                "term": r["data_acct_name"],
                "normalized_type": "data_account",
                "normalized_code": r["data_acct_code"],
                "normalized_name": r["data_acct_name"],
                "confidence": "1.00",
                "requires_confirmation": "false",
                "notes": "exact_match",
            }
        )
    return rows


def build_knowledge_base() -> None:
    ensure_databases()

    repo_root = BACKEND_ROOT.parent
    kb_root = repo_root / "knowledge_base"
    common_path = common_db_path()
    budget_path = budget_db_path(settings.budget_year)

    with sqlite3.connect(common_path) as common_conn, sqlite3.connect(budget_path) as budget_conn:
        data_dictionary_rows = _build_data_dictionary(common_conn)

        _write_csv(
            kb_root / "01_data_semantics" / "data_dictionary_seed.csv",
            [
                "entity_type",
                "entity_code",
                "entity_name",
                "source_table",
                "parent_code",
                "level",
                "value_type",
                "description",
                "status",
                "last_verified_at",
            ],
            data_dictionary_rows,
        )

        report_mapping_rows = _fetch_all(
            common_conn,
            """
            SELECT report_acct_code, data_acct_code
            FROM report_data_mapping
            ORDER BY report_acct_code, data_acct_code
            """,
        )
        _write_csv(
            kb_root / "01_data_semantics" / "report_data_mapping_seed.csv",
            ["report_acct_code", "data_acct_code"],
            [dict(r) for r in report_mapping_rows],
        )

        dept_mapping_rows = _fetch_all(
            common_conn,
            """
            SELECT dept_code, product_code
            FROM dept_product_mapping
            ORDER BY dept_code, product_code
            """,
        )
        _write_csv(
            kb_root / "01_data_semantics" / "dept_product_mapping_seed.csv",
            ["dept_code", "product_code"],
            [dict(r) for r in dept_mapping_rows],
        )

        period_rows = _fetch_all(
            common_conn,
            """
            SELECT period_id, year, month, quarter, year_month, days
            FROM period
            ORDER BY period_id
            """,
        )
        _write_csv(
            kb_root / "01_data_semantics" / "period_seed.csv",
            ["period_id", "year", "month", "quarter", "year_month", "days"],
            [dict(r) for r in period_rows],
        )

        synonyms_rows = _build_synonyms_seed(common_conn)
        _write_csv(
            kb_root / "04_term_synonyms" / "synonyms_seed.csv",
            [
                "domain",
                "term",
                "normalized_type",
                "normalized_code",
                "normalized_name",
                "confidence",
                "requires_confirmation",
                "notes",
            ],
            synonyms_rows,
        )

        version_rows = _fetch_all(
            budget_conn,
            "SELECT version_id, version_name, version_date_time FROM version ORDER BY version_id",
        )
        _write_csv(
            kb_root / "01_data_semantics" / "version_seed.csv",
            ["version_id", "version_name", "version_date_time"],
            [dict(r) for r in version_rows],
        )

        counts = {
            "generated_at": _now_iso(),
            "source_db": {
                "common_db_path": str(common_path),
                "budget_db_path": str(budget_path),
            },
            "table_counts": {
                "data_account": len(_fetch_all(common_conn, "SELECT data_acct_code FROM data_account")),
                "report_account": len(_fetch_all(common_conn, "SELECT report_acct_code FROM report_account")),
                "dept_account": len(_fetch_all(common_conn, "SELECT dept_code FROM dept_account")),
                "product_type": len(_fetch_all(common_conn, "SELECT product_code FROM product_type")),
                "report_data_mapping": len(report_mapping_rows),
                "dept_product_mapping": len(dept_mapping_rows),
                "period": len(period_rows),
                "version": len(version_rows),
            },
            "notes": [
                "Seed files are generated from current SQLite data snapshot.",
                "If core master-data tables are empty, please import business dictionaries first.",
            ],
        }
        _write_json(kb_root / "generated" / "kb_build_report.json", counts)

    print("Knowledge base seed build completed.")
    print("Output root:", kb_root)
    print("Report:", kb_root / "generated" / "kb_build_report.json")


if __name__ == "__main__":
    build_knowledge_base()
