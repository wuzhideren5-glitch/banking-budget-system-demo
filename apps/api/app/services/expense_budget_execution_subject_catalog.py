"""Budget-subject catalog read model for expense budget execution reports."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
from app.core.db_paths import common_db_path


class BudgetSubjectCatalogError(ValueError):
    """Raised when the budget-subject catalog is unavailable."""


def _uses_mysql_path(path: Path | str) -> bool:
    candidate = Path(path).expanduser().resolve(strict=False)
    data_dir = Path(settings.data_dir).expanduser().resolve(strict=False)
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    return True


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def text_value(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _format_catalog_rows(rows: list[Any]) -> list[dict[str, Any]]:
    if not rows:
        raise BudgetSubjectCatalogError("费用预算科目目录尚未初始化，请先在部门预算科目维护中同步或维护当前目录。")
    return [
        {
            "id": int(_row_value(row, "id", 0)),
            "parent_id": (
                int(_row_value(row, "parent_id", 1)) if _row_value(row, "parent_id", 1) is not None else None
            ),
            "level_number": int(_row_value(row, "level_number", 2) or 1),
            "level_label": f"{int(_row_value(row, 'level_number', 2) or 1)}级",
            "subject_name": text_value(_row_value(row, "subject_name", 3)),
            "manage_department": text_value(_row_value(row, "manage_department", 4)) or None,
            "formula_text": text_value(_row_value(row, "formula_text", 5)) or None,
            "sort_order": int(_row_value(row, "sort_order", 6) or 0),
        }
        for row in rows
    ]


async def load_budget_subject_catalog_rows(
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    resolved_db_path = db_path or common_db_path()
    if _uses_mysql_path(resolved_db_path):
        rows = await get_pool().fetch_all(
            """
            SELECT id, parent_id, level_number, subject_name, manage_department, formula_text, sort_order
            FROM budget_subject_catalog
            ORDER BY sort_order, id
            """
        )
        return _format_catalog_rows(rows)
    with sqlite3.connect(resolved_db_path) as db:
        cur = db.execute(
            """
            SELECT id, parent_id, level_number, subject_name, manage_department, formula_text, sort_order
            FROM budget_subject_catalog
            ORDER BY sort_order, id
            """
        )
        return _format_catalog_rows(cur.fetchall())
