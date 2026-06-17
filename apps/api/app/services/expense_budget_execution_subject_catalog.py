"""Budget-subject catalog read model for expense budget execution reports."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

from app.core.db_paths import common_db_path
from app.services.expense_budget_execution_framework import text


class BudgetSubjectCatalogError(ValueError):
    """Raised when the budget-subject catalog is unavailable."""


async def load_budget_subject_catalog_rows(
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    resolved_db_path = db_path or common_db_path()
    async with aiosqlite.connect(resolved_db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT id, parent_id, level_number, subject_name, manage_department, formula_text, sort_order
            FROM budget_subject_catalog
            ORDER BY sort_order, id
            """
        )
        rows = await cur.fetchall()
    if not rows:
        raise BudgetSubjectCatalogError("费用预算科目目录尚未初始化，请先在部门预算科目维护中同步或维护当前目录。")
    return [
        {
            "id": int(row[0]),
            "parent_id": int(row[1]) if row[1] is not None else None,
            "level_number": int(row[2] or 1),
            "level_label": f"{int(row[2] or 1)}级",
            "subject_name": text(row[3]),
            "manage_department": text(row[4]) or None,
            "formula_text": text(row[5]) or None,
            "sort_order": int(row[6] or 0),
        }
        for row in rows
    ]
