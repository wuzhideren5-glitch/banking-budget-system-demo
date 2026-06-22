#!/usr/bin/env python3
"""SQLite → MySQL data migration script.

Usage:
    python -m apps.api.scripts.migrate_sqlite_to_mysql \\
        --dry-run \\
        --year 2025 --year 2026 \\
        --report var/output/sqlite_to_mysql_migration.md

    python -m apps.api.scripts.migrate_sqlite_to_mysql \\
        --resume \\
        --year 2025

    python -m apps.api.scripts.migrate_sqlite_to_mysql --verify-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable

import pymysql

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_sqlite_to_mysql")

# ── Configuration ──

# Source SQLite databases (relative to project root)
SOURCE_DBS: dict[str, Path] = {}

# Tables to migrate, grouped by source database
# Common tables (common.db) — no budget_year
COMMON_TABLES: list[str] = [
    "budget_output_display_item",
    "data_account_metric_node",
    "dept_account",
    "period",
    "smart_report_template",
    "smart_report_template_variable",
    "smart_report_calc_metric",
    "smart_report_blueprint",
    "smart_report_instance",
    "smart_report_job",
    "smart_ppt_scene",
    "smart_ppt_chart_config",
    "smart_ppt_instance",
    "operation_log",
    "users",
    "databases",
    "edit_show_version",
    "user_sessions",
    "feishu_user_binding",
    "expense_sync_meta",
    "expense_framework_budget_department",
    "expense_framework_product_department",
    "expense_framework_subject",
    "budget_subject_catalog",
    "manage_dept_owner_mapping",
    "expense_forecast_entry",
    "expense_forecast_annual_entry",
    "expense_forecast_rule",
    "expense_forecast_rule_param",
    "expense_forecast_rule_variable",
    "expense_forecast_calc_result",
    "expense_forecast_override",
    "expense_actual_import_batch",
    "expense_actual_detail_raw",
    "bi_ai_subject_mapping",
    "expense_budget_entry_batch",
    "expense_budget_entry",
    "intelligent_budget_tasks",
    "org_product_data_entry_draft",
    "org_product_data_entry_snapshot",
    "org_product_data_entry_snapshot_v2",
    "org_product_metric_table_catalog",
    "org_product_metric_table_payload",
    "org_product_output_snapshot_v1",
    "org_product_tree_snapshot",
]

# Annual tables (budget_YYYY.db) — need budget_year set
ANNUAL_TABLES: list[str] = [
    "version",
    "settings",
    "budget_data",
    "budget_summary",
    "budget_pivot_aggregate",
    "business_cost_income_item",
    "business_cost_income_indicator",
    "business_cost_income_source_mapping",
    "business_cost_income_value",
]

# Compare tables (compare.db) — have source_year
COMPARE_TABLES: list[str] = [
    "settings",
    "compare_budget_summary",
    "compare_pivot_aggregate",
    "compare_sync_job_log",
]

COMPARE_TARGET_TABLES: dict[str, str] = {
    "settings": "compare_settings",
}

# Tables that are sized for bulk INSERT (chunked)
BULK_TABLES: set[str] = {"budget_data", "budget_summary", "expense_actual_detail_raw"}

BULK_CHUNK_SIZE = 5000
GLOBAL_ID_MULTIPLIER = 1_000_000

# A live MySQL target may contain rows created after migration by bootstrap
# synchronization or user workflows.  For these tables, verification proves
# that every source row is still present and unchanged, while allowing target
# extras.
TARGET_SUPERSET_TABLES: set[str] = {
    "data_account_metric_node",
    "intelligent_budget_tasks",
    "user_sessions",
}

# Seeded defaults are refreshed at application startup, so updated_at is not a
# data-migration invariant for these tables.
VOLATILE_VERIFY_COLUMNS: dict[str, set[str]] = {
    "smart_ppt_scene": {"updated_at"},
    "smart_ppt_chart_config": {"updated_at"},
}

ANNUAL_ID_COLUMNS: dict[str, tuple[str, ...]] = {
    "version": ("version_id",),
    "settings": ("id",),
    "budget_data": ("id", "version_id"),
    "budget_summary": ("id", "version_id"),
    "budget_pivot_aggregate": ("id", "version_id"),
    "business_cost_income_item": ("id", "parent_id"),
    "business_cost_income_indicator": (
        "id",
        "parent_id",
        "numerator_item_id",
        "denominator_item_id",
    ),
    "business_cost_income_source_mapping": ("id", "item_id"),
    "business_cost_income_value": ("id", "item_id"),
}

# Tables to skip (system/legacy)
SKIP_TABLES: set[str] = {
    "sqlite_sequence",
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
    "budget_annual_aggregate",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _setting(env_file: dict[str, str], key: str, default: str) -> str:
    return os.environ.get(key) or env_file.get(key) or default


def _hash_row(row: tuple) -> str:
    """Compute a stable hash of a row for verification."""
    return hashlib.md5(
        "|".join(str(v) if v is not None else "NULL" for v in row).encode()
    ).hexdigest()[:16]


def _canonical_value(value: object) -> str:
    """Normalize SQLite/MySQL values so verification is about data, not drivers."""
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped[0] in "[{":
            try:
                parsed = json.loads(stripped)
            except Exception:
                return value
            return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _hash_rows(rows: Iterable[tuple]) -> str:
    digest = hashlib.sha256()
    for row in sorted(tuple(_canonical_value(v) for v in row) for row in rows):
        digest.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _quote_identifier(name: str) -> str:
    return f"`{name.replace('`', '``')}`"


def _global_id(budget_year: int, value: object) -> int | None:
    if value is None:
        return None
    raw = int(value)
    if raw <= 0:
        return raw
    return int(budget_year) * GLOBAL_ID_MULTIPLIER + raw


def _remap_columns(
    cols: list[str],
    row: tuple,
    *,
    budget_year: int,
    column_names: tuple[str, ...],
) -> tuple:
    values = list(row)
    index = {name: idx for idx, name in enumerate(cols)}
    for column_name in column_names:
        idx = index.get(column_name)
        if idx is not None and values[idx] is not None:
            values[idx] = _global_id(budget_year, values[idx])
    return tuple(values)


def _apply_annual_id_mapping(
    table: str,
    cols: list[str],
    rows: list[tuple],
    *,
    budget_year: int,
) -> list[tuple]:
    column_names = ANNUAL_ID_COLUMNS.get(table, ())
    if not column_names:
        return rows
    return [
        _remap_columns(cols, tuple(row), budget_year=budget_year, column_names=column_names)
        for row in rows
    ]


def _database_year_map(sqlite_conn: sqlite3.Connection) -> dict[int, int]:
    if not _sqlite_table_exists(sqlite_conn, "databases"):
        return {}
    return {
        int(row[0]): int(row[1])
        for row in sqlite_conn.execute("SELECT id, year FROM databases").fetchall()
        if row[0] is not None and row[1] is not None
    }


def _transform_edit_show_version_rows(
    sqlite_conn: sqlite3.Connection,
    cols: list[str],
    rows: list[tuple],
) -> list[tuple]:
    if "data_file_id" not in cols or "version_id" not in cols:
        return rows
    year_by_data_file_id = _database_year_map(sqlite_conn)
    data_file_idx = cols.index("data_file_id")
    version_idx = cols.index("version_id")
    transformed: list[tuple] = []
    for row in rows:
        values = list(row)
        budget_year = year_by_data_file_id.get(int(values[data_file_idx] or 0))
        if budget_year and values[version_idx] is not None:
            values[version_idx] = _global_id(budget_year, values[version_idx])
        transformed.append(tuple(values))
    return transformed


def _transform_compare_rows(table: str, cols: list[str], rows: list[tuple]) -> list[tuple]:
    if table not in {"compare_budget_summary", "compare_pivot_aggregate"}:
        return rows
    if "source_year" not in cols or "source_version_id" not in cols:
        return rows
    source_year_idx = cols.index("source_year")
    version_idx = cols.index("source_version_id")
    transformed: list[tuple] = []
    for row in rows:
        values = list(row)
        if values[source_year_idx] is not None and values[version_idx] is not None:
            values[version_idx] = _global_id(int(values[source_year_idx]), values[version_idx])
        transformed.append(tuple(values))
    return transformed


# ── MySQL Connection ──

class SyncDatabase:
    """Synchronous MySQL connection wrapper for migration scripts."""

    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.conn: pymysql.Connection | None = None
        self._params = dict(
            host=host, port=port, user=user, password=password,
            database=database, charset="utf8mb4", autocommit=False,
        )

    def __enter__(self):
        self.conn = pymysql.connect(**self._params)
        return self

    def __exit__(self, *args):
        if self.conn:
            self.conn.close()

    def execute(self, sql: str, params=()) -> pymysql.cursors.Cursor:
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur

    def execute_many(self, sql: str, rows: list[tuple]) -> None:
        with self.conn.cursor() as cur:
            cur.executemany(sql, rows)

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def truncate(self, table: str, *, budget_year: int | None = None) -> None:
        with self.conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            if budget_year is None:
                cur.execute(f"TRUNCATE TABLE `{table}`")
            else:
                cur.execute(f"DELETE FROM `{table}` WHERE `budget_year` = %s", (int(budget_year),))
            cur.execute("SET FOREIGN_KEY_CHECKS=1")

    def ensure_migration_schema(self) -> None:
        """Adjust legacy MySQL constraints that block single-database annual data."""
        with self.conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            self._add_column_if_missing(
                cur,
                "dept_account",
                "entity_name",
                "ALTER TABLE dept_account ADD COLUMN entity_name VARCHAR(255) NOT NULL DEFAULT '微众银行' AFTER dept_name",
            )
            cur.execute("ALTER TABLE dept_account MODIFY is_leaf TINYINT(1) NOT NULL DEFAULT 0")
            self._add_column_if_missing(
                cur,
                "expense_framework_budget_department",
                "entity_name",
                "ALTER TABLE expense_framework_budget_department ADD COLUMN entity_name VARCHAR(255) NOT NULL DEFAULT '' AFTER id",
            )
            self._add_column_if_missing(
                cur,
                "expense_framework_product_department",
                "entity_name",
                "ALTER TABLE expense_framework_product_department ADD COLUMN entity_name VARCHAR(255) NOT NULL DEFAULT '' AFTER id",
            )
            self._replace_check_constraint(
                cur,
                "smart_report_template_variable",
                "smart_report_template_variable_chk_1",
                "CHECK (variable_type IN ('metric', 'formula', 'calc', 'parameter', 'text', 'table', 'chart', 'analysis'))",
            )
            self._drop_index_if_exists(cur, "business_cost_income_item", "product_code")
            self._create_index_if_missing(
                cur,
                "business_cost_income_item",
                "uq_bci_item_year_product_section_name",
                "CREATE UNIQUE INDEX uq_bci_item_year_product_section_name "
                "ON business_cost_income_item(budget_year, product_code, section, name)",
            )
            self._drop_index_if_exists(cur, "business_cost_income_source_mapping", "item_id")
            self._create_index_if_missing(
                cur,
                "business_cost_income_source_mapping",
                "uq_bci_source_mapping_year_item_field_code",
                "CREATE UNIQUE INDEX uq_bci_source_mapping_year_item_field_code "
                "ON business_cost_income_source_mapping(budget_year, item_id, field, data_acct_code)",
            )
            self._drop_index_if_exists(cur, "business_cost_income_value", "year")
            self._create_index_if_missing(
                cur,
                "business_cost_income_value",
                "uq_bci_value_year_lookup",
                "CREATE UNIQUE INDEX uq_bci_value_year_lookup "
                "ON business_cost_income_value("
                "budget_year, year, month, entity_name, group_name, product_code, item_section, item_id, field"
                ")",
            )
            cur.execute("ALTER TABLE operation_log MODIFY target_table VARCHAR(255)")
            for column_name in (
                "parsed_target",
                "step_summary",
                "baseline_solution",
                "solutions",
                "negotiation_message",
                "negotiation_suggestions",
            ):
                cur.execute(f"ALTER TABLE intelligent_budget_tasks MODIFY `{column_name}` LONGTEXT")
            cur.execute("ALTER TABLE org_product_data_entry_snapshot MODIFY payload_json LONGTEXT")
            cur.execute("ALTER TABLE org_product_data_entry_snapshot_v2 MODIFY payload_json LONGTEXT")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS compare_settings (
                  id INT AUTO_INCREMENT PRIMARY KEY,
                  setting_key VARCHAR(255) NOT NULL UNIQUE,
                  setting_value TEXT NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
        self.commit()

    def _add_column_if_missing(
        self,
        cur: pymysql.cursors.Cursor,
        table: str,
        column_name: str,
        alter_sql: str,
    ) -> None:
        cur.execute(
            """
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            LIMIT 1
            """,
            (table, column_name),
        )
        if not cur.fetchone():
            cur.execute(alter_sql)

    def _replace_check_constraint(
        self,
        cur: pymysql.cursors.Cursor,
        table: str,
        constraint_name: str,
        check_sql: str,
    ) -> None:
        cur.execute(
            """
            SELECT 1
            FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND CONSTRAINT_NAME = %s
            LIMIT 1
            """,
            (constraint_name,),
        )
        if cur.fetchone():
            cur.execute(f"ALTER TABLE `{table}` DROP CHECK `{constraint_name}`")
        cur.execute(f"ALTER TABLE `{table}` ADD CONSTRAINT `{constraint_name}` {check_sql}")

    def _drop_index_if_exists(self, cur: pymysql.cursors.Cursor, table: str, index_name: str) -> None:
        cur.execute(
            """
            SELECT 1
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = %s
            LIMIT 1
            """,
            (table, index_name),
        )
        if cur.fetchone():
            cur.execute(f"DROP INDEX `{index_name}` ON `{table}`")

    def _create_index_if_missing(
        self,
        cur: pymysql.cursors.Cursor,
        table: str,
        index_name: str,
        ddl: str,
    ) -> None:
        cur.execute(
            """
            SELECT 1
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = %s
            LIMIT 1
            """,
            (table, index_name),
        )
        if not cur.fetchone():
            cur.execute(ddl)


class MigrationProgress:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, list[str]] = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text())
            except Exception:
                self.data = {}
        if "done" not in self.data:
            self.data["done"] = []

    def is_done(self, table_key: str) -> bool:
        return table_key in self.data["done"]

    def mark_done(self, table_key: str) -> None:
        self.data["done"].append(table_key)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))


class MigrationReport:
    def __init__(self):
        self.sections: list[str] = []
        self.source_count: dict[str, int] = {}
        self.target_count: dict[str, int] = {}
        self.errors: list[str] = []
        self.start_time = _iso_now()
        self.end_time = ""

    def add_section(self, title: str, body: str) -> None:
        self.sections.append(f"### {title}\n\n{body}\n")

    def finalize(self) -> None:
        self.end_time = _iso_now()

    def to_markdown(self) -> str:
        lines = [
            f"# SQLite → MySQL Migration Report",
            f"",
            f"**Start**: {self.start_time}",
            f"**End**: {self.end_time}",
            f"",
            f"## Summary",
            f"",
        ]
        for src, count in sorted(self.source_count.items()):
            tgt = self.target_count.get(src, 0)
            status = "✅" if count == tgt else "⚠️"
            lines.append(f"| {src} | {count} source | {tgt} target | {status} |")
        if self.errors:
            lines.append("")
            lines.append("## Errors")
            for e in self.errors:
                lines.append(f"- {e}")
        for s in self.sections:
            lines.append(s)
        return "\n".join(lines)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")


# ── Core Migration Logic ──

def _sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Return column names for a table in creation order."""
    return [
        str(r[1])
        for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
    ]


def _sqlite_primary_key_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    ordered = sorted((int(r[5]), str(r[1])) for r in rows if int(r[5] or 0) > 0)
    return [name for _, name in ordered]


def _mysql_ensure_columns(mysql: SyncDatabase, table: str, cols: list[str]) -> tuple[str, str]:
    """Return (column_list, placeholder_list) for INSERT."""
    col_list = ", ".join(f"`{c}`" for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))
    return col_list, placeholders


def _mysql_columns(mysql: SyncDatabase, table: str) -> set[str]:
    with mysql.conn.cursor() as cur:
        cur.execute(f"SHOW COLUMNS FROM `{table}`")
        return {str(row[0]) for row in cur.fetchall()}


def _prepare_source_rows_for_target(
    sqlite_conn: sqlite3.Connection,
    table: str,
    *,
    budget_year: int | None = None,
    row_transform: Callable[[list[str], list[tuple]], list[tuple]] | None = None,
) -> tuple[list[str], list[tuple], list[str]]:
    cols = _sqlite_columns(sqlite_conn, table)
    rows = [tuple(row) for row in sqlite_conn.execute(f'SELECT * FROM "{table}"').fetchall()]
    pk_cols = _sqlite_primary_key_columns(sqlite_conn, table)

    if budget_year is not None:
        rows = _apply_annual_id_mapping(table, cols, rows, budget_year=budget_year)
    if row_transform is not None:
        rows = row_transform(cols, rows)

    if budget_year is not None and "budget_year" not in cols:
        cols = ["budget_year"] + list(cols)
        rows = [(budget_year,) + row for row in rows]

    return cols, rows, pk_cols


def _fetch_target_rows(
    mysql: SyncDatabase,
    table: str,
    cols: list[str],
    *,
    budget_year: int | None = None,
) -> list[tuple]:
    select_cols = ", ".join(_quote_identifier(c) for c in cols)
    sql = f"SELECT {select_cols} FROM {_quote_identifier(table)}"
    params: tuple = ()
    if budget_year is not None and "budget_year" in cols:
        sql += " WHERE `budget_year` = %s"
        params = (int(budget_year),)
    with mysql.conn.cursor() as cur:
        cur.execute(sql, params)
        return [tuple(row) for row in cur.fetchall()]


def _project_key_set(cols: list[str], rows: list[tuple], key_cols: list[str]) -> set[tuple[str, ...]]:
    indexes = [cols.index(c) for c in key_cols if c in cols]
    if not indexes:
        return set()
    return {
        tuple(_canonical_value(row[idx]) for idx in indexes)
        for row in rows
    }


def _project_rows(cols: list[str], rows: list[tuple], selected_cols: list[str]) -> list[tuple]:
    indexes = [cols.index(c) for c in selected_cols]
    return [tuple(row[idx] for idx in indexes) for row in rows]


def _filter_rows_by_keys(
    cols: list[str],
    rows: list[tuple],
    key_cols: list[str],
    source_keys: set[tuple[str, ...]],
) -> list[tuple]:
    indexes = [cols.index(c) for c in key_cols if c in cols]
    if not indexes:
        return rows
    return [
        row
        for row in rows
        if tuple(_canonical_value(row[idx]) for idx in indexes) in source_keys
    ]


def _null_empty_differences(source_rows: list[tuple], target_rows: list[tuple]) -> int:
    source_nulls = sum(1 for row in source_rows for value in row if value is None)
    target_nulls = sum(1 for row in target_rows for value in row if value is None)
    source_empty = sum(1 for row in source_rows for value in row if value == "")
    target_empty = sum(1 for row in target_rows for value in row if value == "")
    return int(source_nulls != target_nulls or source_empty != target_empty)


def _migrate_table(
    sqlite_conn: sqlite3.Connection,
    mysql: SyncDatabase,
    table: str,
    *,
    dry_run: bool,
    truncate_target: bool,
    target_table: str | None = None,
    budget_year: int | None = None,
    row_transform: Callable[[list[str], list[tuple]], list[tuple]] | None = None,
) -> tuple[int, int]:
    """Migrate one table. Returns (source_rows, target_rows)."""
    if not _sqlite_table_exists(sqlite_conn, table):
        return 0, 0

    cols = _sqlite_columns(sqlite_conn, table)
    if not cols:
        return 0, 0

    # Read from SQLite
    cur = sqlite_conn.execute(f'SELECT * FROM "{table}"')
    rows = [tuple(row) for row in cur.fetchall()]
    source_count = len(rows)
    logger.info(f"  {table}: {source_count} rows read from SQLite")

    if dry_run:
        return source_count, 0

    if budget_year is not None:
        rows = _apply_annual_id_mapping(table, cols, rows, budget_year=budget_year)
    if row_transform is not None:
        rows = row_transform(cols, rows)

    # Prepare INSERT statement
    if budget_year is not None and "budget_year" not in cols:
        cols = ["budget_year"] + list(cols)
        rows = [(budget_year,) + row for row in rows]

    mysql_table = target_table or table
    col_list, ph_list = _mysql_ensure_columns(mysql, mysql_table, cols)

    if truncate_target:
        mysql.truncate(mysql_table, budget_year=budget_year)

    mysql.execute("SET FOREIGN_KEY_CHECKS=0")
    try:
        if table in BULK_TABLES and source_count > BULK_CHUNK_SIZE:
            for i in range(0, source_count, BULK_CHUNK_SIZE):
                chunk = rows[i : i + BULK_CHUNK_SIZE]
                mysql.execute_many(
                    f"INSERT INTO `{mysql_table}` ({col_list}) VALUES ({ph_list})", chunk
                )
                mysql.commit()
                logger.info(f"  {table}: chunk {i // BULK_CHUNK_SIZE + 1} inserted {len(chunk)} rows")
        else:
            mysql.execute_many(
                f"INSERT INTO `{mysql_table}` ({col_list}) VALUES ({ph_list})", rows
            )
            mysql.commit()
    finally:
        mysql.execute("SET FOREIGN_KEY_CHECKS=1")

    # Verify target count
    with mysql.conn.cursor() as cur:
        if budget_year is None:
            cur.execute(f"SELECT COUNT(*) FROM `{mysql_table}`")
        else:
            cur.execute(f"SELECT COUNT(*) FROM `{mysql_table}` WHERE `budget_year` = %s", (int(budget_year),))
        target_count = int(cur.fetchone()[0])

    logger.info(f"  {table}: {target_count} rows in MySQL (source: {source_count})")
    return source_count, target_count


def _verify_table(
    sqlite_conn: sqlite3.Connection,
    mysql: SyncDatabase,
    table: str,
    *,
    target_table: str | None = None,
    budget_year: int | None = None,
    row_transform: Callable[[list[str], list[tuple]], list[tuple]] | None = None,
) -> dict[str, object]:
    """Verify row count, primary-key set, full-row hash, and null/empty preservation."""
    result: dict[str, object] = {
        "source": 0,
        "target": 0,
        "schema_error": 0,
        "pk_error": 0,
        "hash_error": 0,
        "null_empty_error": 0,
        "source_hash": "",
        "target_hash": "",
        "missing_columns": [],
        "target_extra": 0,
        "ignored_columns": sorted(VOLATILE_VERIFY_COLUMNS.get(target_table or table, set())),
        "target_superset_allowed": target_table is None and table in TARGET_SUPERSET_TABLES,
    }
    if not _sqlite_table_exists(sqlite_conn, table):
        return result

    cols, source_rows, pk_cols = _prepare_source_rows_for_target(
        sqlite_conn,
        table,
        budget_year=budget_year,
        row_transform=row_transform,
    )
    result["source"] = len(source_rows)

    mysql_table = target_table or table
    ignored_columns = VOLATILE_VERIFY_COLUMNS.get(mysql_table, set())
    compare_cols = [c for c in cols if c not in ignored_columns]

    with mysql.conn.cursor() as cur:
        target_columns = _mysql_columns(mysql, mysql_table)
        missing_columns = [c for c in compare_cols if c not in target_columns]
        if missing_columns:
            result["target"] = -1
            result["schema_error"] = 1
            result["missing_columns"] = missing_columns
            return result
        if budget_year is None:
            cur.execute(f"SELECT COUNT(*) FROM `{mysql_table}`")
        else:
            if "budget_year" not in target_columns:
                result["target"] = -1
                result["schema_error"] = 1
                result["missing_columns"] = ["budget_year"]
                return result
            cur.execute(f"SELECT COUNT(*) FROM `{mysql_table}` WHERE `budget_year` = %s", (int(budget_year),))
        result["target"] = int(cur.fetchone()[0])

    source_compare_rows = _project_rows(cols, source_rows, compare_cols)
    target_rows = _fetch_target_rows(mysql, mysql_table, compare_cols, budget_year=budget_year)

    if result["target_superset_allowed"] and pk_cols:
        source_keys = _project_key_set(compare_cols, source_compare_rows, pk_cols)
        target_keys = _project_key_set(compare_cols, target_rows, pk_cols)
        result["target_extra"] = len(target_keys - source_keys)
        target_rows_for_hash = _filter_rows_by_keys(compare_cols, target_rows, pk_cols, source_keys)
    else:
        source_keys = _project_key_set(compare_cols, source_compare_rows, pk_cols) if pk_cols else set()
        target_keys = _project_key_set(compare_cols, target_rows, pk_cols) if pk_cols else set()
        target_rows_for_hash = target_rows

    source_hash = _hash_rows(source_compare_rows)
    target_hash = _hash_rows(target_rows_for_hash)
    result["source_hash"] = source_hash
    result["target_hash"] = target_hash
    result["hash_error"] = int(source_hash != target_hash)

    if pk_cols:
        missing_keys = source_keys - target_keys
        extra_keys = target_keys - source_keys
        result["pk_error"] = int(bool(missing_keys) or (bool(extra_keys) and not result["target_superset_allowed"]))
        if result["pk_error"]:
            result["source_pk_count"] = len(source_keys)
            result["target_pk_count"] = len(target_keys)
            result["missing_pk_count"] = len(missing_keys)
            result["extra_pk_count"] = len(extra_keys)

    result["null_empty_error"] = _null_empty_differences(source_compare_rows, target_rows_for_hash)
    return result


def _verification_status(counts: dict[str, object]) -> str:
    if counts.get("schema_error"):
        return "SCHEMA_ERROR"
    if counts.get("target_superset_allowed"):
        if int(counts["target"]) < int(counts["source"]):
            return "COUNT_MISMATCH"
    elif counts["source"] != counts["target"]:
        return "COUNT_MISMATCH"
    if counts.get("pk_error"):
        return "PK_MISMATCH"
    if counts.get("hash_error"):
        return "HASH_MISMATCH"
    if counts.get("null_empty_error"):
        return "NULL_EMPTY_MISMATCH"
    return "OK"


def _record_verification_errors(report: MigrationReport, table_key: str, counts: dict[str, object]) -> None:
    status = _verification_status(counts)
    if status == "OK":
        return
    if status == "SCHEMA_ERROR":
        report.errors.append(f"{table_key}: target schema mismatch, missing columns={counts.get('missing_columns')}")
    elif status == "COUNT_MISMATCH":
        report.errors.append(f"{table_key}: source={counts['source']} target={counts['target']} row-count mismatch")
    elif status == "PK_MISMATCH":
        report.errors.append(
            f"{table_key}: primary-key set mismatch "
            f"(source={counts.get('source_pk_count')} target={counts.get('target_pk_count')})"
        )
    elif status == "HASH_MISMATCH":
        report.errors.append(
            f"{table_key}: row hash mismatch "
            f"(source={counts.get('source_hash')} target={counts.get('target_hash')})"
        )
    elif status == "NULL_EMPTY_MISMATCH":
        report.errors.append(f"{table_key}: NULL/empty-string distribution mismatch")


# ── CLI ──

def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    env_file = _load_env_file(project_root / "apps" / "api" / ".env")

    parser = argparse.ArgumentParser(description="SQLite → MySQL data migration")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only, no writes")
    parser.add_argument("--resume", action="store_true", help="Skip already-migrated tables")
    parser.add_argument("--verify-only", action="store_true", help="Only verify row counts, no migration")
    parser.add_argument(
        "--only",
        choices=("all", "common", "budget", "compare", "year"),
        default="all",
        help="Limit migration/verification scope",
    )
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="Delete target rows before inserting. Required for a clean full migration.",
    )
    parser.add_argument("--year", type=int, action="append", dest="years", help="Budget years to migrate (repeatable)")
    parser.add_argument("--report", type=str, default="", help="Output report file path")
    parser.add_argument("--data-dir", type=str, default="var/data", help="SQLite data directory")
    parser.add_argument("--progress-file", type=str, default="var/output/migration_progress.json",
                        help="Progress tracking file")
    parser.add_argument("--mysql-host", default=_setting(env_file, "MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--mysql-port", type=int, default=int(_setting(env_file, "MYSQL_PORT", "3306")))
    parser.add_argument("--mysql-user", default=_setting(env_file, "MYSQL_USER", "root"))
    parser.add_argument("--mysql-password", default=_setting(env_file, "MYSQL_PASSWORD", ""))
    parser.add_argument("--mysql-database", default=_setting(env_file, "MYSQL_DATABASE", "banking_budget"))
    args = parser.parse_args()

    data_dir = project_root / args.data_dir
    years = args.years or [2025, 2026]

    # Locate source SQLite files
    common_path = data_dir / "common.db"
    compare_path = data_dir / "compare.db"
    if not common_path.exists():
        logger.error(f"common.db not found at {common_path}")
        sys.exit(1)

    report = MigrationReport()
    progress = MigrationProgress(Path(args.progress_file))

    mysql_params = dict(
        host=args.mysql_host, port=args.mysql_port,
        user=args.mysql_user, password=args.mysql_password,
        database=args.mysql_database,
    )

    if args.only in ("all", "common"):
        logger.info("=" * 60)
        logger.info("Phase 1: Common tables (common.db)")
        logger.info("=" * 60)
        sqlite_conn = sqlite3.connect(str(common_path))
        sqlite_conn.row_factory = sqlite3.Row
        try:
            with SyncDatabase(**mysql_params) as mysql:
                if not args.dry_run and not args.verify_only:
                    mysql.ensure_migration_schema()
                for table in COMMON_TABLES:
                    if table in SKIP_TABLES:
                        continue
                    table_key = f"common/{table}"
                    if args.resume and progress.is_done(table_key):
                        logger.info(f"  {table}: SKIP (already migrated)")
                        continue

                    if args.verify_only:
                        counts = _verify_table(
                            sqlite_conn,
                            mysql,
                            table,
                            row_transform=(
                                lambda cols, rows, conn=sqlite_conn: _transform_edit_show_version_rows(conn, cols, rows)
                            )
                            if table == "edit_show_version"
                            else None,
                        )
                        report.source_count[table_key] = counts["source"]
                        report.target_count[table_key] = counts["target"]
                        status = _verification_status(counts)
                        logger.info(
                            f"  {table}: source={counts['source']} target={counts['target']} "
                            f"hash={str(counts.get('target_hash', ''))[:12]} {status}"
                        )
                        _record_verification_errors(report, table_key, counts)
                        continue

                    src, tgt = _migrate_table(
                        sqlite_conn,
                        mysql,
                        table,
                        dry_run=args.dry_run,
                        truncate_target=args.truncate_target,
                        row_transform=(
                            lambda cols, rows, conn=sqlite_conn: _transform_edit_show_version_rows(conn, cols, rows)
                        )
                        if table == "edit_show_version"
                        else None,
                    )
                    report.source_count[table_key] = src
                    report.target_count[table_key] = tgt
                    if not args.dry_run:
                        counts = _verify_table(
                            sqlite_conn,
                            mysql,
                            table,
                            row_transform=(
                                lambda cols, rows, conn=sqlite_conn: _transform_edit_show_version_rows(conn, cols, rows)
                            )
                            if table == "edit_show_version"
                            else None,
                        )
                        status = _verification_status(counts)
                        logger.info(f"  {table}: post-migration verification {status}")
                        _record_verification_errors(report, table_key, counts)
                        if status == "OK":
                            progress.mark_done(table_key)
        finally:
            sqlite_conn.close()

    # ── Phase 2: Annual tables ──
    if args.only in ("all", "budget", "year"):
        for year in years:
            budget_path = data_dir / f"budget_{year}.db"
            if not budget_path.exists():
                logger.warning(f"budget_{year}.db not found, skipping")
                continue

            logger.info("=" * 60)
            logger.info(f"Phase 2: Annual tables for {year} (budget_{year}.db)")
            logger.info("=" * 60)
            sqlite_conn = sqlite3.connect(str(budget_path))
            sqlite_conn.row_factory = sqlite3.Row
            try:
                with SyncDatabase(**mysql_params) as mysql:
                    if not args.dry_run and not args.verify_only:
                        mysql.ensure_migration_schema()
                    for table in ANNUAL_TABLES:
                        if table in SKIP_TABLES:
                            continue
                        table_key = f"budget_{year}/{table}"
                        if args.resume and progress.is_done(table_key):
                            logger.info(f"  {table}: SKIP (already migrated)")
                            continue

                        if args.verify_only:
                            counts = _verify_table(sqlite_conn, mysql, table, budget_year=year)
                            report.source_count[table_key] = counts["source"]
                            report.target_count[table_key] = counts["target"]
                            status = _verification_status(counts)
                            logger.info(
                                f"  {table}: source={counts['source']} target={counts['target']} "
                                f"hash={str(counts.get('target_hash', ''))[:12]} {status}"
                            )
                            _record_verification_errors(report, table_key, counts)
                            continue

                        src, tgt = _migrate_table(
                            sqlite_conn,
                            mysql,
                            table,
                            dry_run=args.dry_run,
                            truncate_target=args.truncate_target,
                            budget_year=year,
                        )
                        report.source_count[table_key] = src
                        report.target_count[table_key] = tgt
                        if not args.dry_run:
                            counts = _verify_table(sqlite_conn, mysql, table, budget_year=year)
                            status = _verification_status(counts)
                            logger.info(f"  {table}: post-migration verification {status}")
                            _record_verification_errors(report, table_key, counts)
                            if status == "OK":
                                progress.mark_done(table_key)
            finally:
                sqlite_conn.close()

    # ── Phase 3: Compare tables ──
    if args.only in ("all", "compare") and compare_path.exists():
        logger.info("=" * 60)
        logger.info("Phase 3: Compare tables (compare.db)")
        logger.info("=" * 60)
        sqlite_conn = sqlite3.connect(str(compare_path))
        sqlite_conn.row_factory = sqlite3.Row
        try:
            with SyncDatabase(**mysql_params) as mysql:
                if not args.dry_run and not args.verify_only:
                    mysql.ensure_migration_schema()
                for table in COMPARE_TABLES:
                    if table in SKIP_TABLES:
                        continue
                    target_table = COMPARE_TARGET_TABLES.get(table, table)
                    table_key = f"compare/{table}->{target_table}" if target_table != table else f"compare/{table}"
                    if args.resume and progress.is_done(table_key):
                        logger.info(f"  {table}: SKIP (already migrated)")
                        continue

                    if args.verify_only:
                        counts = _verify_table(
                            sqlite_conn,
                            mysql,
                            table,
                            target_table=target_table,
                            row_transform=(
                                lambda cols, rows, current_table=table: _transform_compare_rows(current_table, cols, rows)
                            ),
                        )
                        report.source_count[table_key] = counts["source"]
                        report.target_count[table_key] = counts["target"]
                        status = _verification_status(counts)
                        logger.info(
                            f"  {table}: source={counts['source']} target={counts['target']} "
                            f"hash={str(counts.get('target_hash', ''))[:12]} {status}"
                        )
                        _record_verification_errors(report, table_key, counts)
                        continue

                    src, tgt = _migrate_table(
                        sqlite_conn,
                        mysql,
                        table,
                        dry_run=args.dry_run,
                        truncate_target=args.truncate_target,
                        target_table=target_table,
                        row_transform=(
                            lambda cols, rows, current_table=table: _transform_compare_rows(current_table, cols, rows)
                        ),
                    )
                    report.source_count[table_key] = src
                    report.target_count[table_key] = tgt
                    if not args.dry_run:
                        counts = _verify_table(
                            sqlite_conn,
                            mysql,
                            table,
                            target_table=target_table,
                            row_transform=(
                                lambda cols, rows, current_table=table: _transform_compare_rows(current_table, cols, rows)
                            ),
                        )
                        status = _verification_status(counts)
                        logger.info(f"  {table}: post-migration verification {status}")
                        _record_verification_errors(report, table_key, counts)
                        if status == "OK":
                            progress.mark_done(table_key)
        finally:
            sqlite_conn.close()

    report.finalize()

    # Write report
    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = project_root / report_path
        report.write(report_path)
        logger.info(f"Report written to {report_path}")
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = project_root / "var" / "output" / f"sqlite_to_mysql_migration_{timestamp}.md"
        report.write(report_path)
        logger.info(f"Report written to {report_path}")

    if report.errors:
        logger.warning(f"{len(report.errors)} errors during migration")
        for e in report.errors:
            logger.warning(f"  {e}")
        sys.exit(1)
    else:
        logger.info("Migration completed with no errors")


if __name__ == "__main__":
    main()
