"""Schema readiness adapter for expense forecast private tables."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
from app.db_bootstrap.expense import ensure_expense_forecast_schema_sync


REQUIRED_TABLES: dict[str, set[str]] = {
    "expense_forecast_entry": {
        "forecast_year",
        "forecast_version",
        "scope_type",
        "scope_value",
        "subject_id",
        "month",
        "forecast_value",
    },
    "expense_forecast_annual_entry": {
        "forecast_year",
        "forecast_version",
        "scope_type",
        "scope_value",
        "subject_id",
        "field_name",
        "field_value",
    },
    "expense_forecast_rule": {
        "forecast_year",
        "forecast_version",
        "owner_name",
        "subject_id",
        "scheme_code",
        "metric_source_priority",
    },
    "expense_forecast_rule_param": {"rule_id", "param_group", "param_key", "param_value", "value_type"},
    "expense_forecast_rule_variable": {"rule_id", "variable_code", "source_type", "source_key"},
    "expense_forecast_calc_result": {
        "forecast_year",
        "forecast_version",
        "owner_name",
        "subject_id",
        "month",
        "calc_value",
    },
    "expense_forecast_override": {
        "forecast_year",
        "forecast_version",
        "owner_name",
        "subject_id",
        "month",
        "system_value",
        "override_value",
    },
}

OLD_SOURCE_PRIORITY_TOKEN = "driver_" + "source_priority"
OLD_EXPR_TOKEN = "driver_" + "expr"
OLD_FIRST_TOKEN = "driver_" + "first"
OLD_MODULE_TOKEN = "driver_" + "module"


def _uses_mysql_path(path: Path | str) -> bool:
    try:
        candidate = Path(path).expanduser().resolve()
    except TypeError:
        return False
    temp_root = Path(tempfile.gettempdir()).expanduser().resolve()
    try:
        candidate.relative_to(temp_root)
        return False
    except ValueError:
        pass
    data_dir = Path(settings.data_dir).expanduser().resolve()
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    return candidate.name == "common.db"


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


async def _table_columns_mysql(table_name: str) -> set[str]:
    rows = await get_pool().fetch_all(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        """,
        (table_name,),
    )
    return {str(_row_value(row, "COLUMN_NAME", 0)) for row in rows}


async def _table_sql_mysql(table_name: str) -> str:
    try:
        row = await get_pool().fetch_one(f"SHOW CREATE TABLE `{table_name}`")
    except Exception:
        return ""
    if not row:
        return ""
    if isinstance(row, dict):
        return str(row.get("Create Table") or row.get("Create View") or "")
    return str(row[1] or "")


async def _assert_current_mysql_contract() -> None:
    for table_name, required_columns in REQUIRED_TABLES.items():
        columns = await _table_columns_mysql(table_name)
        if not columns:
            raise RuntimeError(f"费用预测私有表 {table_name} 不存在，系统不再自动迁移")
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"费用预测私有表 {table_name} 缺少当前字段，系统不再自动迁移：" + ", ".join(missing)
            )

    rule_columns = await _table_columns_mysql("expense_forecast_rule")
    rule_sql = (await _table_sql_mysql("expense_forecast_rule")).lower()
    if (
        "metric_source_priority" not in rule_columns
        or OLD_SOURCE_PRIORITY_TOKEN in rule_columns
        or OLD_EXPR_TOKEN in rule_sql
        or OLD_FIRST_TOKEN in rule_sql
    ):
        raise RuntimeError("费用预测规则发现旧 driver 合同，系统不再自动迁移")

    driver_param = await get_pool().fetch_one(
        "SELECT 1 FROM expense_forecast_rule_param WHERE param_group = %s LIMIT 1",
        ("driver",),
    )
    if driver_param:
        raise RuntimeError("费用预测规则参数发现旧 driver 参数组，系统不再自动迁移")

    variable_sql = (await _table_sql_mysql("expense_forecast_rule_variable")).lower()
    if OLD_MODULE_TOKEN in variable_sql:
        raise RuntimeError("费用预测规则变量发现旧 driver 来源，系统不再自动迁移")


async def ensure_expense_forecast_schema_ready(db_path: str | Path) -> None:
    path = Path(db_path)
    if _uses_mysql_path(path):
        await _assert_current_mysql_contract()
        return

    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        try:
            ensure_expense_forecast_schema_sync(db)
        except Exception as exc:
            raise RuntimeError("费用预测私有表发现旧 driver 合同，系统不再自动迁移") from exc
        db.commit()
