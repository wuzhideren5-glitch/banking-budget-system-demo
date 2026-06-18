"""Database read context for expense forecast views and imports."""
from __future__ import annotations

from collections import defaultdict
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Literal

from app.core.config import settings
from app.core.database import get_pool
from app.services.department_expense_contracts import DEPT_OWNER_LEVEL

ScopeType = Literal["entity", "group", "owner"]

MANAGE_DEPARTMENT_ALIASES = {
    "科技管理部": "科技业务",
    "董事会办公室": "公司治理部",
    "监事会办公室": "公司治理部",
}


class ExpenseForecastDataContextError(ValueError):
    """Raised when current expense forecast data cannot satisfy a request."""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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
    return candidate.name == "common.db" or (candidate.name.startswith("budget_") and candidate.suffix == ".db")


def _budget_year_from_path(path: Path | str) -> int | None:
    stem = Path(path).stem
    if not stem.startswith("budget_"):
        return None
    suffix = stem.removeprefix("budget_")
    return int(suffix) if suffix.isdigit() else None


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


async def load_expense_forecast_scope_rows(db_path: Path) -> list[tuple[str, str, str]]:
    sql = """
        SELECT DISTINCT
            COALESCE(NULLIF(TRIM(child.entity_name), ''), '微众银行') AS entity_name,
            COALESCE(NULLIF(TRIM(parent.dept_name), ''), '') AS group_name,
            COALESCE(NULLIF(TRIM(child.dept_name), ''), '') AS owner_name
        FROM dept_account child
        LEFT JOIN dept_account parent
          ON parent.dept_code = child.parent_code
        WHERE child.level = ?
        ORDER BY entity_name, group_name, owner_name
        """
    if _uses_mysql_path(db_path):
        rows = await get_pool().fetch_all(sql.replace("?", "%s"), (DEPT_OWNER_LEVEL,))
    else:
        with sqlite3.connect(db_path) as db:
            db.execute("PRAGMA foreign_keys = ON")
            rows = db.execute(sql, (DEPT_OWNER_LEVEL,)).fetchall()
    return [
        (_text(_row_value(row, "entity_name", 0)), _text(_row_value(row, "group_name", 1)), _text(_row_value(row, "owner_name", 2)))
        for row in rows
    ]


def _budget_subject_row_from_db(row: Any) -> dict[str, Any]:
    return {
        "id": int(_row_value(row, "id", 0)),
        "parent_id": int(_row_value(row, "parent_id", 1)) if _row_value(row, "parent_id", 1) is not None else None,
        "level_number": int(_row_value(row, "level_number", 2)),
        "subject_name": _text(_row_value(row, "subject_name", 3)),
        "manage_department": _text(_row_value(row, "manage_department", 4)) or None,
        "formula_text": _text(_row_value(row, "formula_text", 5)) or None,
        "sort_order": int(_row_value(row, "sort_order", 6) or 0),
        "is_leaf": not bool(_row_value(row, "has_children", 7)),
    }


async def load_expense_forecast_budget_subject_rows(db_path: Path) -> list[dict[str, Any]]:
    sql = """
        SELECT c.id, c.parent_id, c.level_number, c.subject_name, c.manage_department, c.formula_text, c.sort_order,
               EXISTS(SELECT 1 FROM budget_subject_catalog child WHERE child.parent_id = c.id) AS has_children
        FROM budget_subject_catalog c
        ORDER BY COALESCE(c.parent_id, 0), c.sort_order, c.id
        """
    if _uses_mysql_path(db_path):
        rows = await get_pool().fetch_all(sql)
    else:
        with sqlite3.connect(db_path) as db:
            db.execute("PRAGMA foreign_keys = ON")
            rows = db.execute(sql).fetchall()
    return [_budget_subject_row_from_db(row) for row in rows]


async def load_expense_forecast_manage_department_map(db_path: Path) -> dict[str, str]:
    sql = """
        SELECT subject_name, manage_department
        FROM budget_subject_catalog
        ORDER BY sort_order, id
        """
    if _uses_mysql_path(db_path):
        rows = await get_pool().fetch_all(sql)
    else:
        with sqlite3.connect(db_path) as db:
            db.execute("PRAGMA foreign_keys = ON")
            rows = db.execute(sql).fetchall()
    return {
        _text(_row_value(row, "subject_name", 0)): _text(_row_value(row, "manage_department", 1))
        for row in rows
    }


def normalize_expense_forecast_manage_department(raw_manage_department: str) -> str:
    value = _text(raw_manage_department)
    if not value or value == "使用部门":
        return ""
    return MANAGE_DEPARTMENT_ALIASES.get(value, value)


async def _fetch_all_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_all(sql.replace("?", "%s"), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, params).fetchall()


async def _fetch_one_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> Any:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_one(sql.replace("?", "%s"), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, params).fetchone()


async def _latest_budget_version_id(budget_db_path: Path) -> int | None:
    if _uses_mysql_path(budget_db_path):
        budget_year = _budget_year_from_path(budget_db_path)
        if budget_year is None:
            row = await get_pool().fetch_one("SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1")
        else:
            row = await get_pool().fetch_one(
                """
                SELECT version_id
                FROM version
                WHERE budget_year = %s
                ORDER BY version_id DESC
                LIMIT 1
                """,
                (budget_year,),
            )
    else:
        row = await _fetch_one_for_path(budget_db_path, "SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1")
    value = _row_value(row, "version_id", 0) if row else None
    return int(value) if value is not None else None


async def load_expense_forecast_actual_map(
    db_path: Path,
    *,
    year: int,
    owner_names: list[str],
) -> dict[tuple[str, str, int], float]:
    if not owner_names:
        return {}
    placeholders = ",".join("?" for _ in owner_names)
    rows = await _fetch_all_for_path(
        db_path,
        f"""
        SELECT owner_name_mapped, budget_subject_mapped, CAST(SUBSTR(period_ym, 6, 2) AS UNSIGNED) AS month, SUM(amount) AS amount
        FROM expense_actual_detail_raw
        WHERE owner_matched = 1
          AND subject_matched = 1
          AND import_kind = 'current_year_actual'
          AND substr(period_ym, 1, 4) = ?
          AND owner_name_mapped IN ({placeholders})
        GROUP BY owner_name_mapped, budget_subject_mapped, CAST(SUBSTR(period_ym, 6, 2) AS UNSIGNED)
        """,
        (str(year), *owner_names),
    )
    if rows:
        return {
            (
                _text(_row_value(row, "owner_name_mapped", 0)),
                _text(_row_value(row, "budget_subject_mapped", 1)),
                int(_row_value(row, "month", 2)),
            ): float(_row_value(row, "amount", 3) or 0)
            for row in rows
            if 1 <= int(_row_value(row, "month", 2) or 0) <= 12
        }

    return {}


async def load_expense_forecast_actual_cutoff_month(
    db_path: Path,
    *,
    year: int,
) -> int:
    row = await _fetch_one_for_path(
        db_path,
        """
        SELECT MAX(CAST(SUBSTR(period_ym, 6, 2) AS UNSIGNED)) AS cutoff_month
        FROM expense_actual_detail_raw
        WHERE import_kind = 'current_year_actual'
          AND owner_matched = 1
          AND subject_matched = 1
          AND SUBSTR(period_ym, 1, 4) = ?
          AND CAST(SUBSTR(period_ym, 6, 2) AS UNSIGNED) BETWEEN 1 AND 12
        """,
        (str(year),),
    )
    value = int(_row_value(row, "cutoff_month", 0) or 0) if row and _row_value(row, "cutoff_month", 0) is not None else 0
    return max(0, min(12, value))


async def load_expense_forecast_forecast_map(
    db_path: Path,
    *,
    year: int,
    forecast_version: str,
    owner_names: list[str],
) -> dict[tuple[str, int, int], float]:
    if not owner_names:
        return {}
    placeholders = ",".join("?" for _ in owner_names)
    rows = await _fetch_all_for_path(
        db_path,
        f"""
        SELECT scope_value, subject_id, month, forecast_value
        FROM expense_forecast_entry
        WHERE forecast_year = ? AND forecast_version = ? AND scope_type = 'owner'
          AND scope_value IN ({placeholders})
        """,
        (year, forecast_version, *owner_names),
    )
    return {
        (_text(_row_value(row, "scope_value", 0)), int(_row_value(row, "subject_id", 1)), int(_row_value(row, "month", 2))): float(
            _row_value(row, "forecast_value", 3) or 0
        )
        for row in rows
    }


async def load_expense_forecast_annual_input_map(
    db_path: Path,
    *,
    year: int,
    forecast_version: str,
    owner_names: list[str],
) -> dict[tuple[str, int, str], float]:
    if not owner_names:
        return {}
    placeholders = ",".join("?" for _ in owner_names)
    rows = await _fetch_all_for_path(
        db_path,
        f"""
        SELECT scope_value, subject_id, field_name, field_value
        FROM expense_forecast_annual_entry
        WHERE forecast_year = ? AND forecast_version = ? AND scope_type = 'owner'
          AND scope_value IN ({placeholders})
        """,
        (year, forecast_version, *owner_names),
    )
    return {
        (_text(_row_value(row, "scope_value", 0)), int(_row_value(row, "subject_id", 1)), _text(_row_value(row, "field_name", 2))): float(
            _row_value(row, "field_value", 3) or 0
        )
        for row in rows
    }


async def load_expense_forecast_product_department_owner_map() -> dict[str, str]:
    # 产品部门映射已取消，预算侧默认直接用 product_code_name 前缀识别费用归属部门。
    return {}


async def load_expense_forecast_annual_budget_map(
    budget_db_path: Path,
    *,
    owner_names: list[str],
    product_department_owner_map: dict[str, str] | None = None,
) -> dict[tuple[str, str], float]:
    if not owner_names or (not _uses_mysql_path(budget_db_path) and not budget_db_path.exists()):
        return {}
    version_id = await _latest_budget_version_id(budget_db_path)
    if version_id is None:
        return {}
    owner_name_set = {_text(item) for item in owner_names if _text(item)}
    owner_map = product_department_owner_map or {}
    if _uses_mysql_path(budget_db_path):
        budget_year = _budget_year_from_path(budget_db_path)
        filters = ["version_id = %s", "budget_actual = 0"]
        args: list[Any] = [version_id]
        if budget_year is not None:
            filters.append("budget_year = %s")
            args.append(budget_year)
        rows = await get_pool().fetch_all(
            """
            SELECT product_code_name, data_code_name, value
            FROM budget_summary
            WHERE __FILTERS__
            """.replace("__FILTERS__", " AND ".join(filters)),
            tuple(args),
        )
    else:
        rows = await _fetch_all_for_path(
            budget_db_path,
            """
            SELECT product_code_name, data_code_name, value
            FROM budget_summary
            WHERE version_id = ? AND budget_actual = 0
            """,
            (version_id,),
        )
    result: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        product_code_name = _row_value(row, "product_code_name", 0)
        data_code_name = _row_value(row, "data_code_name", 1)
        value = _row_value(row, "value", 2)
        product_department = _text(product_code_name).split("-", 1)[0].strip() if _text(product_code_name) else ""
        owner_name = owner_map.get(product_department, product_department)
        if owner_name not in owner_name_set:
            continue
        budget_subject = _text(data_code_name)
        if not budget_subject:
            continue
        parts = budget_subject.split(" ", 1)
        if len(parts) == 2:
            budget_subject = _text(parts[1])
        result[(owner_name, budget_subject)] += float(value or 0)
    return {(owner, subject): round(amount, 2) for (owner, subject), amount in result.items()}


def resolve_expense_forecast_scope_owners(
    scope_rows: list[tuple[str, str, str]],
    *,
    scope_type: ScopeType,
    scope_value: str,
) -> list[str]:
    owners: list[str] = []
    value = _text(scope_value)
    for entity_name, group_name, owner_name in scope_rows:
        if scope_type == "entity" and entity_name == value and owner_name and owner_name not in owners:
            owners.append(owner_name)
        elif scope_type == "group" and group_name == value and owner_name and owner_name not in owners:
            owners.append(owner_name)
        elif scope_type == "owner" and owner_name == value and owner_name not in owners:
            owners.append(owner_name)
    if not owners:
        raise ExpenseForecastDataContextError("当前编制口径下没有可用的费用归属部门")
    return owners


def build_expense_forecast_effective_manage_departments(
    subject_rows: list[dict[str, Any]],
    manage_department_map: dict[str, str],
) -> tuple[dict[int, str], dict[str, list[str]]]:
    row_by_id = {row["id"]: row for row in subject_rows}
    children_by_parent: dict[int | None, list[int]] = defaultdict(list)
    for row in subject_rows:
        children_by_parent[row["parent_id"]].append(int(row["id"]))

    effective_by_id: dict[int, str] = {}
    effective_by_name: dict[str, list[str]] = defaultdict(list)

    def _walk(node_id: int, inherited_department: str) -> None:
        row = row_by_id[node_id]
        current_department = (
            normalize_expense_forecast_manage_department(manage_department_map.get(row["subject_name"], ""))
            or inherited_department
        )
        effective_by_id[node_id] = current_department
        if current_department and current_department not in effective_by_name[row["subject_name"]]:
            effective_by_name[row["subject_name"]].append(current_department)
        for child_id in children_by_parent.get(node_id, []):
            _walk(child_id, current_department)

    for root_id in children_by_parent.get(None, []):
        _walk(root_id, "")
    return effective_by_id, effective_by_name


def build_expense_forecast_subject_lookup(
    subject_rows: list[dict[str, Any]],
) -> tuple[dict[int, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_id = {int(row["id"]): row for row in subject_rows}
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in subject_rows:
        by_name[_text(row["subject_name"])].append(row)
    return by_id, by_name
