"""Master-data context loader for expense actual import parsing."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
import re
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
from app.services.bi_ai_manage_department import (
    build_bi_mapping_manage_departments_index,
    build_effective_manage_department_by_subject,
    normalize_manage_department_subject_label,
)
from app.services.bi_ai_subject_mapping import (
    _attach_manage_departments,
    ensure_bi_ai_subject_mapping_seeded,
)
from app.services.department_expense_contracts import DEPT_OWNER_LEVEL
from app.services.expense_actual_import_parser import (
    GOVERNANCE_OWNER_ALIASES,
    FrameworkContext,
    normalize_key,
    remember_bi_mapping,
    strip_leading_code,
)


class ExpenseActualImportContextError(ValueError):
    """Raised when current master data cannot support expense actual import."""


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return re.sub(r"\s+", " ", text)


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


def _mysql_sql(sql: str) -> str:
    return sql.replace("?", "%s")


async def _table_exists(db_path: Path, table_name: str) -> bool:
    if _uses_mysql_path(db_path):
        row = await get_pool().fetch_one(
            """
            SELECT 1 AS exists_flag
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
            LIMIT 1
            """,
            (table_name,),
        )
        return bool(row)
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return bool(row)


async def _fetch_all_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_all(_mysql_sql(sql), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, params).fetchall()


async def _load_budget_subject_catalog_manage_rows_for_path(db_path: Path) -> list[dict[str, Any]]:
    rows = await _fetch_all_for_path(
        db_path,
        """
        SELECT id, parent_id, subject_name, manage_department
        FROM budget_subject_catalog
        ORDER BY sort_order, id
        """,
    )
    return [
        {
            "id": int(_row_value(row, "id", 0)),
            "parent_id": int(_row_value(row, "parent_id", 1))
            if _row_value(row, "parent_id", 1) is not None
            else None,
            "subject_name": _text(_row_value(row, "subject_name", 2)),
            "manage_department": _text(_row_value(row, "manage_department", 3)) or None,
        }
        for row in rows
    ]


async def _load_all_expense_departments_for_path(db_path: Path) -> list[str]:
    if _uses_mysql_path(db_path):
        columns = await get_pool().fetch_all(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'dept_account'
            """
        )
        column_names = {_text(_row_value(row, "COLUMN_NAME", 0)) for row in columns}
        order_clause = "entity_name, dept_name" if "entity_name" in column_names else "dept_name"
        rows = await get_pool().fetch_all(
            f"""
            SELECT dept_name
            FROM dept_account
            WHERE level = %s
            ORDER BY {order_clause}
            """,
            (DEPT_OWNER_LEVEL,),
        )
        departments: list[str] = []
        seen: set[str] = set()
        for row in rows:
            department = _text(_row_value(row, "dept_name", 0))
            if not department or department in seen:
                continue
            seen.add(department)
            departments.append(department)
        return departments

    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        columns = {str(row[1]) for row in db.execute('PRAGMA table_info("dept_account")').fetchall()}
        if not columns:
            return []
        order_clause = "entity_name, dept_name" if "entity_name" in columns else "dept_name"
        rows = db.execute(
            f"""
            SELECT dept_name
            FROM dept_account
            WHERE level = ?
            ORDER BY {order_clause}
            """,
            (DEPT_OWNER_LEVEL,),
        ).fetchall()
    departments: list[str] = []
    seen: set[str] = set()
    for row in rows:
        department = _text(_row_value(row, "dept_name", 0))
        if not department or department in seen:
            continue
        seen.add(department)
        departments.append(department)
    return departments


async def _load_bi_ai_subject_mapping_rows_for_path(db_path: Path) -> list[dict[str, Any]]:
    rows = await _fetch_all_for_path(
        db_path,
        """
        SELECT id, level5_code, level5_name, level6_code, level6_name,
               budget_release_caliber, fee_category, fee_major,
               manage_department_override, sort_order, source_file
        FROM bi_ai_subject_mapping
        ORDER BY sort_order, id
        """,
    )
    catalog_rows = (
        await _load_budget_subject_catalog_manage_rows_for_path(db_path)
        if await _table_exists(db_path, "budget_subject_catalog")
        else []
    )
    all_expense_departments = await _load_all_expense_departments_for_path(db_path)
    manage_by_subject = build_effective_manage_department_by_subject(catalog_rows)
    catalog_names = {
        normalize_manage_department_subject_label(_text(row.get("subject_name")))
        for row in catalog_rows
    }
    catalog_names.discard("")
    base_rows: list[dict[str, Any]] = [
        {
            "id": int(_row_value(row, "id", 0)),
            "level5_code": _text(_row_value(row, "level5_code", 1)),
            "level5_name": _text(_row_value(row, "level5_name", 2)),
            "level6_code": _text(_row_value(row, "level6_code", 3)),
            "level6_name": _text(_row_value(row, "level6_name", 4)),
            "budget_release_caliber": _text(_row_value(row, "budget_release_caliber", 5)),
            "fee_category": _text(_row_value(row, "fee_category", 6)),
            "fee_major": _text(_row_value(row, "fee_major", 7)),
            "manage_department_override": _text(_row_value(row, "manage_department_override", 8)),
            "sort_order": int(_row_value(row, "sort_order", 9) or 0),
            "source_file": _text(_row_value(row, "source_file", 10)),
        }
        for row in rows
    ]
    return _attach_manage_departments(
        base_rows,
        manage_by_subject,
        all_expense_departments,
        catalog_names=catalog_names,
    )


def _remember_owner_name(ctx: FrameworkContext, owner_name: str) -> None:
    normalized = _text(owner_name)
    if not normalized:
        return
    ctx.owner_alias_map[normalize_key(normalized)] = normalized
    ctx.owner_alias_map[normalize_key(strip_leading_code(normalized))] = normalized
    ctx.owner_names.add(normalized)


def _remember_subject_name(ctx: FrameworkContext, subject_name: str) -> None:
    normalized = _text(subject_name)
    if not normalized:
        return
    ctx.subject_alias_map[normalize_key(normalized)] = normalized
    ctx.subject_names.add(normalized)


async def _merge_framework_master_data(ctx: FrameworkContext, db_path: Path) -> None:
    if await _table_exists(db_path, "expense_framework_budget_department"):
        rows = await _fetch_all_for_path(
            db_path,
            """
            SELECT owner_name, budget_department
            FROM expense_framework_budget_department
            ORDER BY id
            """,
        )
        for row in rows:
            _remember_owner_name(ctx, _text(_row_value(row, "owner_name", 0)))
            _remember_owner_name(ctx, _text(_row_value(row, "budget_department", 1)))
    if await _table_exists(db_path, "expense_framework_product_department"):
        rows = await _fetch_all_for_path(
            db_path,
            """
            SELECT owner_name, product_department
            FROM expense_framework_product_department
            ORDER BY id
            """,
        )
        for row in rows:
            _remember_owner_name(ctx, _text(_row_value(row, "owner_name", 0)))
            _remember_owner_name(ctx, _text(_row_value(row, "product_department", 1)))
    if await _table_exists(db_path, "expense_framework_subject"):
        rows = await _fetch_all_for_path(
            db_path,
            """
            SELECT budget_subject
            FROM expense_framework_subject
            ORDER BY sort_order, budget_subject
            """,
        )
        for row in rows:
            _remember_subject_name(ctx, _text(_row_value(row, "budget_subject", 0)))


async def load_expense_actual_import_context(db_path: str | Path, repo_root: str | Path) -> FrameworkContext:
    ctx = FrameworkContext()
    db_path = Path(db_path)
    repo_root = Path(repo_root)
    if not _uses_mysql_path(db_path):
        await ensure_bi_ai_subject_mapping_seeded(db_path, repo_root)
    owner_rows = await _fetch_all_for_path(
        db_path,
        """
        SELECT DISTINCT COALESCE(NULLIF(TRIM(dept_name), ''), '') AS dept_name
        FROM dept_account
        WHERE level = ?
        ORDER BY dept_name
        """,
        (DEPT_OWNER_LEVEL,),
    )
    subject_rows = await _fetch_all_for_path(
        db_path,
        """
        SELECT subject_name
        FROM budget_subject_catalog
        GROUP BY subject_name
        ORDER BY MIN(sort_order), MIN(id)
        """,
    )
    bi_mapping_rows: list[tuple[str, ...]] = []
    if await _table_exists(db_path, "bi_ai_subject_mapping"):
        rows = await _fetch_all_for_path(
            db_path,
            """
            SELECT level5_code, level5_name, level6_code, level6_name,
                   budget_release_caliber, fee_category, fee_major
            FROM bi_ai_subject_mapping
            ORDER BY sort_order, id
            """,
        )
        bi_mapping_rows = [
            tuple(_text(_row_value(row, key, index)) for index, key in enumerate((
                "level5_code",
                "level5_name",
                "level6_code",
                "level6_name",
                "budget_release_caliber",
                "fee_category",
                "fee_major",
            )))
            for row in rows
        ]
    manage_dept_owner_rows: list[tuple[str, str]] = []
    if await _table_exists(db_path, "manage_dept_owner_mapping"):
        rows = await _fetch_all_for_path(
            db_path,
            "SELECT manage_department, owner_department FROM manage_dept_owner_mapping",
        )
        manage_dept_owner_rows = [
            (_text(_row_value(row, "manage_department", 0)), _text(_row_value(row, "owner_department", 1)))
            for row in rows
        ]
    catalog_rows = (
        await _load_budget_subject_catalog_manage_rows_for_path(db_path)
        if await _table_exists(db_path, "budget_subject_catalog")
        else []
    )

    for row in owner_rows:
        owner_name = _text(_row_value(row, "dept_name", 0))
        if owner_name:
            ctx.owner_alias_map[normalize_key(owner_name)] = owner_name
            ctx.owner_alias_map[normalize_key(strip_leading_code(owner_name))] = owner_name
            ctx.owner_names.add(owner_name)
    for subject_row in subject_rows:
        subject_name = _text(_row_value(subject_row, "subject_name", 0))
        if subject_name:
            ctx.subject_alias_map[normalize_key(subject_name)] = subject_name
            ctx.subject_names.add(subject_name)
    if not ctx.owner_names or not ctx.subject_names:
        raise ExpenseActualImportContextError("系统主数据未初始化，请先维护部门科目和部门预算科目。")
    for alias_name, canonical_name in GOVERNANCE_OWNER_ALIASES.items():
        ctx.owner_alias_map[normalize_key(alias_name)] = canonical_name
        ctx.owner_alias_map[normalize_key(strip_leading_code(alias_name))] = canonical_name
        ctx.owner_alias_map[normalize_key(canonical_name)] = canonical_name
        ctx.owner_names.add(canonical_name)
    for row in bi_mapping_rows:
        budget_subject = row[4]
        level6_code = row[2]
        if level6_code:
            ctx.bi_ai_subject_mapping_detail[normalize_key(level6_code)] = (row[6], row[5], budget_subject)
        for source_value in row[:5]:
            remember_bi_mapping(ctx, source_value, budget_subject)
    for manage_dept, owner_dept in manage_dept_owner_rows:
        if manage_dept and owner_dept:
            ctx.manage_dept_owner_map[normalize_key(manage_dept)] = owner_dept
            ctx.owner_dept_manage_map[normalize_key(owner_dept)] = manage_dept
    ctx.subject_manage_department = build_effective_manage_department_by_subject(catalog_rows)
    bi_rows = await _load_bi_ai_subject_mapping_rows_for_path(db_path)
    ctx.bi_mapping_manage_departments_by_caliber = build_bi_mapping_manage_departments_index(bi_rows)
    return ctx


async def load_expense_budget_entry_context(db_path: str | Path, repo_root: str | Path) -> FrameworkContext:
    """Budget entry import context: dept master data plus expense framework departments/subjects."""
    ctx = await load_expense_actual_import_context(db_path, repo_root)
    await _merge_framework_master_data(ctx, Path(db_path))
    return ctx
