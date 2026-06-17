"""Database read context for expense forecast views and imports."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

import aiosqlite

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


async def load_expense_forecast_scope_rows(db_path: Path) -> list[tuple[str, str, str]]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT DISTINCT
                COALESCE(NULLIF(TRIM(child.entity_name), ''), '微众银行') AS entity_name,
                COALESCE(NULLIF(TRIM(parent.dept_name), ''), '') AS group_name,
                COALESCE(NULLIF(TRIM(child.dept_name), ''), '') AS owner_name
            FROM dept_account child
            LEFT JOIN dept_account parent
              ON parent.dept_code = child.parent_code
            WHERE child.level = ?
            ORDER BY entity_name, group_name, owner_name
            """,
            (DEPT_OWNER_LEVEL,),
        )
        rows = await cur.fetchall()
    return [(_text(row[0]), _text(row[1]), _text(row[2])) for row in rows]


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


async def load_expense_forecast_budget_subject_rows(db_path: Path) -> list[dict[str, Any]]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT c.id, c.parent_id, c.level_number, c.subject_name, c.manage_department, c.formula_text, c.sort_order,
                   EXISTS(SELECT 1 FROM budget_subject_catalog child WHERE child.parent_id = c.id) AS has_children
            FROM budget_subject_catalog c
            ORDER BY COALESCE(c.parent_id, 0), c.sort_order, c.id
            """
        )
        rows = await cur.fetchall()
    return [
        {
            "id": int(row[0]),
            "parent_id": int(row[1]) if row[1] is not None else None,
            "level_number": int(row[2]),
            "subject_name": _text(row[3]),
            "manage_department": _text(row[4]) or None,
            "formula_text": _text(row[5]) or None,
            "sort_order": int(row[6] or 0),
            "is_leaf": not bool(row[7]),
        }
        for row in rows
    ]


async def load_expense_forecast_manage_department_map(db_path: Path) -> dict[str, str]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT subject_name, manage_department
            FROM budget_subject_catalog
            ORDER BY sort_order, id
            """
        )
        rows = await cur.fetchall()
    return {_text(row[0]): _text(row[1]) for row in rows}


def normalize_expense_forecast_manage_department(raw_manage_department: str) -> str:
    value = _text(raw_manage_department)
    if not value or value == "使用部门":
        return ""
    return MANAGE_DEPARTMENT_ALIASES.get(value, value)


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


async def load_expense_forecast_actual_map(
    db_path: Path,
    *,
    year: int,
    owner_names: list[str],
) -> dict[tuple[str, str, int], float]:
    if not owner_names:
        return {}
    placeholders = ",".join("?" for _ in owner_names)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            f"""
            SELECT owner_name_mapped, budget_subject_mapped, CAST(substr(period_ym, 6, 2) AS INTEGER) AS month, SUM(amount)
            FROM expense_actual_detail_raw
            WHERE owner_matched = 1
              AND subject_matched = 1
              AND import_kind = 'current_year_actual'
              AND substr(period_ym, 1, 4) = ?
              AND owner_name_mapped IN ({placeholders})
            GROUP BY owner_name_mapped, budget_subject_mapped, CAST(substr(period_ym, 6, 2) AS INTEGER)
            """,
            (str(year), *owner_names),
        )
        rows = await cur.fetchall()
        if rows:
            return {
                (_text(row[0]), _text(row[1]), int(row[2])): float(row[3] or 0)
                for row in rows
                if 1 <= int(row[2] or 0) <= 12
            }

    return {}


async def load_expense_forecast_actual_cutoff_month(
    db_path: Path,
    *,
    year: int,
) -> int:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT MAX(CAST(substr(period_ym, 6, 2) AS INTEGER))
            FROM expense_actual_detail_raw
            WHERE import_kind = 'current_year_actual'
              AND owner_matched = 1
              AND subject_matched = 1
              AND substr(period_ym, 1, 4) = ?
              AND CAST(substr(period_ym, 6, 2) AS INTEGER) BETWEEN 1 AND 12
            """,
            (str(year),),
        )
        row = await cur.fetchone()
    value = int(row[0] or 0) if row and row[0] is not None else 0
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
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            f"""
            SELECT scope_value, subject_id, month, forecast_value
            FROM expense_forecast_entry
            WHERE forecast_year = ? AND forecast_version = ? AND scope_type = 'owner'
              AND scope_value IN ({placeholders})
            """,
            (year, forecast_version, *owner_names),
        )
        rows = await cur.fetchall()
    return {
        (_text(row[0]), int(row[1]), int(row[2])): float(row[3] or 0)
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
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            f"""
            SELECT scope_value, subject_id, field_name, field_value
            FROM expense_forecast_annual_entry
            WHERE forecast_year = ? AND forecast_version = ? AND scope_type = 'owner'
              AND scope_value IN ({placeholders})
            """,
            (year, forecast_version, *owner_names),
        )
        rows = await cur.fetchall()
    return {
        (_text(row[0]), int(row[1]), _text(row[2])): float(row[3] or 0)
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
    if not owner_names or not budget_db_path.exists():
        return {}
    owner_name_set = {_text(item) for item in owner_names if _text(item)}
    owner_map = product_department_owner_map or {}
    async with aiosqlite.connect(budget_db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute("SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1")
        version_row = await cur.fetchone()
        if not version_row:
            return {}
        version_id = int(version_row[0])
        cur = await db.execute(
            """
            SELECT product_code_name, data_code_name, value
            FROM budget_summary
            WHERE version_id = ? AND budget_actual = 0
            """,
            (version_id,),
        )
        rows = await cur.fetchall()
    result: dict[tuple[str, str], float] = defaultdict(float)
    for product_code_name, data_code_name, value in rows:
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
