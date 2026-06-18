"""Actual-source loading for expense budget execution reports."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
from app.core.db_paths import common_db_path
from app.services.expense_budget_execution_actual_routing import route_actual_subject_by_caliber
from app.services.expense_budget_execution_framework import (
    FrameworkContext,
    canonical_owner_name,
    canonical_subject,
    default_entity_name,
    default_group_name,
    text,
)


class ExpenseActualError(ValueError):
    """Raised when fee actual rows cannot be parsed or loaded."""


ActualMap = dict[tuple[str, str], list[float]]


@dataclass(frozen=True)
class LoadedActualRows:
    actual_by_entity: ActualMap
    actual_by_group: ActualMap
    actual_by_owner: ActualMap
    source_mode: str
    source_description: str
    actual_by_subject: dict[str, list[float]] = field(default_factory=dict)


def _new_month_values() -> list[float]:
    return [0.0] * 12


def _parse_month(value: Any) -> int | None:
    raw_text = text(value)
    if not raw_text:
        return None
    tokens = re.findall(r"\d{1,2}", raw_text)
    for token in reversed(tokens):
        month = int(token)
        if 1 <= month <= 12:
            return month
    try:
        month = int(float(raw_text))
        return month if 1 <= month <= 12 else None
    except (TypeError, ValueError):
        return None


def _empty_actual_maps() -> tuple[ActualMap, ActualMap, ActualMap]:
    return defaultdict(_new_month_values), defaultdict(_new_month_values), defaultdict(_new_month_values)


def _add_actual(
    *,
    ctx: FrameworkContext,
    actual_by_entity: ActualMap,
    actual_by_group: ActualMap,
    actual_by_owner: ActualMap,
    owner_name: str,
    budget_subject: str,
    month_idx: int,
    amount: float,
) -> None:
    entity_name = ctx.owner_to_entity.get(owner_name, default_entity_name())
    group_name = ctx.owner_to_group.get(owner_name, default_group_name(entity_name))
    actual_by_entity[(entity_name, budget_subject)][month_idx - 1] += amount
    actual_by_owner[(owner_name, budget_subject)][month_idx - 1] += amount
    actual_by_group[(group_name, budget_subject)][month_idx - 1] += amount


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    keys = getattr(row, "keys", None)
    if callable(keys) and key in keys():
        return row[key]
    return row[index]


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


def _mysql_sql(sql: str) -> str:
    return sql.replace("?", "%s")


async def _fetch_all_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_all(_mysql_sql(sql), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, params).fetchall()


async def _fetch_one_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> Any:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_one(_mysql_sql(sql), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, params).fetchone()


def _actual_source_description(batch_row: Any | None) -> str:
    if not batch_row:
        return "费用执行明细导入（当前本年实际明细）"
    file_name = _row_value(batch_row, "file_name", 0)
    created_at = _row_value(batch_row, "created_at", 1)
    row_count = _row_value(batch_row, "total_rows", 2)
    return (
        f"费用执行明细导入（最近导入时间 {text(created_at) or '-'}"
        f"，来源 {text(file_name) or '费用执行明细导入'}，行数 {int(row_count or 0)}）"
    )


async def load_actual_rows(ctx: FrameworkContext) -> LoadedActualRows:
    db_path = common_db_path()
    raw_detail_rows = await _fetch_all_for_path(
        db_path,
        """
        SELECT owner_name_mapped, budget_subject_mapped, budget_release_caliber_mapped, period_ym, amount
        FROM expense_actual_detail_raw
        WHERE owner_matched = 1
          AND subject_matched = 1
          AND import_kind = 'current_year_actual'
        ORDER BY owner_name_mapped, budget_subject_mapped, period_ym
        """,
    )
    latest_batch = await _fetch_one_for_path(
        db_path,
        """
        SELECT file_name, created_at, total_rows
        FROM expense_actual_import_batch
        WHERE import_kind = 'current_year_actual'
        ORDER BY id DESC
        LIMIT 1
        """,
    )
    if raw_detail_rows:
        actual_by_entity, actual_by_group, actual_by_owner = _empty_actual_maps()
        actual_by_subject: dict[str, list[float]] = defaultdict(_new_month_values)
        for row in raw_detail_rows:
            owner_name = _row_value(row, "owner_name_mapped", 0)
            budget_subject = _row_value(row, "budget_subject_mapped", 1)
            budget_release_caliber = _row_value(row, "budget_release_caliber_mapped", 2)
            period_ym = _row_value(row, "period_ym", 3)
            amount = _row_value(row, "amount", 4)
            owner = canonical_owner_name(text(owner_name), ctx)
            subject = canonical_subject(text(budget_subject), ctx)
            subject = route_actual_subject_by_caliber(subject, budget_release_caliber)
            month_idx = _parse_month(period_ym)
            if not owner or not subject or month_idx is None or month_idx < 1 or month_idx > 12:
                continue
            numeric = round(float(amount or 0.0), 2)
            _add_actual(
                ctx=ctx,
                actual_by_entity=actual_by_entity,
                actual_by_group=actual_by_group,
                actual_by_owner=actual_by_owner,
                owner_name=owner,
                budget_subject=subject,
                month_idx=month_idx,
                amount=numeric,
            )
            actual_by_subject[subject][month_idx - 1] += numeric
        source_desc = _actual_source_description(latest_batch)
        return LoadedActualRows(
            actual_by_entity,
            actual_by_group,
            actual_by_owner,
            "internal",
            source_desc,
            {key: [round(item, 2) for item in values] for key, values in actual_by_subject.items()},
        )

    raise ExpenseActualError("费用执行实际尚未初始化到数据库，请在“费用执行明细导入”中导入本年实际明细。")
