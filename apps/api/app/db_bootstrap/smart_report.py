"""Current Smart Report schema contract checks."""
from __future__ import annotations

import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat


SMART_REPORT_REQUIRED_COLUMNS = {
    "smart_report_template": {
        "template_id",
        "template_code",
        "template_name",
        "template_type",
        "file_path",
        "status",
        "version_no",
        "remark",
        "created_by",
        "created_at",
        "updated_at",
    },
    "smart_report_template_variable": {
        "variable_id",
        "template_id",
        "variable_key",
        "variable_name",
        "variable_type",
        "binding_config_json",
        "display_order",
        "created_at",
        "updated_at",
    },
    "smart_report_instance": {
        "instance_id",
        "template_id",
        "instance_name",
        "parameter_values_json",
        "text_values_json",
        "data_snapshot_json",
        "output_file_path",
        "generation_status",
        "error_message",
        "last_generated_at",
        "last_refresh_at",
        "created_at",
        "updated_at",
    },
}


SMART_REPORT_RETIRED_COLUMNS = {
    "smart_report_instance": {"report_id"},
}


SMART_REPORT_REQUIRED_SQL_MARKERS = {
    "smart_report_template": (
        "template_type TEXT NOT NULL DEFAULT 'analysis' CHECK (template_type IN ('analysis', 'report', 'summary', 'ppt'))",
    ),
    "smart_report_template_variable": (
        "variable_type TEXT NOT NULL CHECK (variable_type IN ('metric', 'formula', 'calc', 'parameter', 'text', 'table', 'chart', 'analysis'))",
        "UNIQUE (template_id, variable_key)",
    ),
    "smart_report_instance": (
        "generation_status TEXT NOT NULL DEFAULT 'pending' CHECK (generation_status IN ('pending', 'running', 'success', 'failed'))",
    ),
}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    }


def _table_sql(conn: sqlite3.Connection, table_name: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return str(row[0] or "") if row else ""


def _missing_sql_markers(table_sql: str, markers: tuple[str, ...]) -> list[str]:
    normalized_sql = " ".join(table_sql.split())
    return [marker for marker in markers if marker not in normalized_sql]


def ensure_smart_report_schema_sync(conn: sqlite3.Connection) -> None:
    """Reject old Smart Report physical tables instead of rebuilding them."""
    for table_name, required_columns in SMART_REPORT_REQUIRED_COLUMNS.items():
        columns = _table_columns(conn, table_name)
        if not columns:
            raise RuntimeError(f"智能报告表 {table_name} 不存在，系统不再自动迁移")
        retired = sorted(SMART_REPORT_RETIRED_COLUMNS.get(table_name, set()) & columns)
        if retired:
            raise RuntimeError(
                f"智能报告表 {table_name} 仍包含旧字段，系统不再自动迁移："
                + ", ".join(retired)
            )
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"智能报告表 {table_name} 缺少当前字段，系统不再自动迁移："
                + ", ".join(missing)
            )
        table_sql = _table_sql(conn, table_name)
        missing_markers = _missing_sql_markers(
            table_sql,
            SMART_REPORT_REQUIRED_SQL_MARKERS.get(table_name, ()),
        )
        if missing_markers:
            raise RuntimeError(
                f"智能报告表 {table_name} 缺少当前约束，系统不再自动迁移："
                + ", ".join(missing_markers)
            )

