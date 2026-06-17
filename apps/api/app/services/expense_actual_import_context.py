"""Master-data context loader for expense actual import parsing."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import app.core.aiosqlite_compat as aiosqlite
from app.services.bi_ai_manage_department import (
    build_bi_mapping_manage_departments_index,
    build_effective_manage_department_by_subject,
    load_budget_subject_catalog_manage_rows,
)
from app.services.bi_ai_subject_mapping import (
    ensure_bi_ai_subject_mapping_seeded,
    query_bi_ai_subject_mapping_rows,
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


async def _table_exists(db: aiosqlite.Connection, table_name: str) -> bool:
    cur = await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return bool(await cur.fetchone())


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


async def _merge_framework_master_data(ctx: FrameworkContext, db: aiosqlite.Connection) -> None:
    if await _table_exists(db, "expense_framework_budget_department"):
        cur = await db.execute(
            """
            SELECT owner_name, budget_department
            FROM expense_framework_budget_department
            ORDER BY id
            """
        )
        for owner_name, budget_department in await cur.fetchall():
            _remember_owner_name(ctx, _text(owner_name))
            _remember_owner_name(ctx, _text(budget_department))
    if await _table_exists(db, "expense_framework_product_department"):
        cur = await db.execute(
            """
            SELECT owner_name, product_department
            FROM expense_framework_product_department
            ORDER BY id
            """
        )
        for owner_name, product_department in await cur.fetchall():
            _remember_owner_name(ctx, _text(owner_name))
            _remember_owner_name(ctx, _text(product_department))
    if await _table_exists(db, "expense_framework_subject"):
        cur = await db.execute(
            """
            SELECT budget_subject
            FROM expense_framework_subject
            ORDER BY sort_order, budget_subject
            """
        )
        for row in await cur.fetchall():
            _remember_subject_name(ctx, _text(row[0]))


async def load_expense_actual_import_context(db_path: str | Path, repo_root: str | Path) -> FrameworkContext:
    ctx = FrameworkContext()
    db_path = Path(db_path)
    repo_root = Path(repo_root)
    await ensure_bi_ai_subject_mapping_seeded(db_path, repo_root)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT DISTINCT COALESCE(NULLIF(TRIM(dept_name), ''), '')
            FROM dept_account
            WHERE level = ?
            ORDER BY dept_name
            """,
            (DEPT_OWNER_LEVEL,),
        )
        owner_rows = await cur.fetchall()
        cur = await db.execute(
            """
            SELECT DISTINCT subject_name
            FROM budget_subject_catalog
            ORDER BY sort_order, id
            """
        )
        subject_rows = await cur.fetchall()
        bi_mapping_rows: list[tuple[str, ...]] = []
        if await _table_exists(db, "bi_ai_subject_mapping"):
            cur = await db.execute(
                """
                SELECT level5_code, level5_name, level6_code, level6_name,
                       budget_release_caliber, fee_category, fee_major
                FROM bi_ai_subject_mapping
                ORDER BY sort_order, id
                """
            )
            bi_mapping_rows = [tuple(_text(value) for value in row) for row in await cur.fetchall()]
        manage_dept_owner_rows: list[tuple[str, str]] = []
        if await _table_exists(db, "manage_dept_owner_mapping"):
            cur = await db.execute(
                "SELECT manage_department, owner_department FROM manage_dept_owner_mapping"
            )
            manage_dept_owner_rows = [(_text(row[0]), _text(row[1])) for row in await cur.fetchall()]
        catalog_rows = (
            await load_budget_subject_catalog_manage_rows(db)
            if await _table_exists(db, "budget_subject_catalog")
            else []
        )

    for row in owner_rows:
        owner_name = _text(row[0])
        if owner_name:
            ctx.owner_alias_map[normalize_key(owner_name)] = owner_name
            ctx.owner_alias_map[normalize_key(strip_leading_code(owner_name))] = owner_name
            ctx.owner_names.add(owner_name)
    for subject_row in subject_rows:
        subject_name = _text(subject_row[0])
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
    bi_rows = await query_bi_ai_subject_mapping_rows(db_path, repo_root)
    ctx.bi_mapping_manage_departments_by_caliber = build_bi_mapping_manage_departments_index(bi_rows)
    return ctx


async def load_expense_budget_entry_context(db_path: str | Path, repo_root: str | Path) -> FrameworkContext:
    """Budget entry import context: dept master data plus expense framework departments/subjects."""
    ctx = await load_expense_actual_import_context(db_path, repo_root)
    async with aiosqlite.connect(Path(db_path)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await _merge_framework_master_data(ctx, db)
    return ctx
