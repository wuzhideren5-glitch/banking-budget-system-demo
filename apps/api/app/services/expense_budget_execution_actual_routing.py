"""Route imported actual rows to report subjects by budget release caliber."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import aiosqlite

from app.core.db_paths import common_db_path
from app.services.expense_budget_execution_budget_rollup import normalize_budget_subject_name
from app.services.expense_budget_execution_framework import text

OUTSOURCE_SUBJECT = "外包服务费"
DAILY_OUTSOURCE_SUBJECT = "日常外包服务费"
IT_OUTSOURCE_SUBJECT = "IT外包服务费"


def route_actual_subject_by_caliber(subject_name: str, budget_release_caliber_mapped: Any) -> str:
    """Split shared outsource actuals so daily / IT / operating portions stay separate."""
    subject = normalize_budget_subject_name(subject_name)
    if subject != OUTSOURCE_SUBJECT:
        return subject
    caliber_raw = text(budget_release_caliber_mapped)
    if caliber_raw == DAILY_OUTSOURCE_SUBJECT:
        return DAILY_OUTSOURCE_SUBJECT
    if caliber_raw == IT_OUTSOURCE_SUBJECT:
        return IT_OUTSOURCE_SUBJECT
    return subject


def _parse_month(value: Any) -> int | None:
    raw_text = text(value)
    if not raw_text:
        return None
    import re

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


async def load_fee_major_monthly_totals(
    *,
    import_kind: str = "current_year_actual",
) -> tuple[dict[str, list[float]], str]:
    """Load month arrays keyed by imported fee_major_mapped."""
    monthly_totals: dict[str, list[float]] = defaultdict(lambda: [0.0] * 12)
    source = "费用执行明细导入（尚未初始化）"
    async with aiosqlite.connect(common_db_path()) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='expense_actual_detail_raw'"
        )
        if not await cur.fetchone():
            return {}, source
        cur = await db.execute(
            """
            SELECT fee_major_mapped, period_ym, amount
            FROM expense_actual_detail_raw
            WHERE COALESCE(import_kind, '') = ?
              AND TRIM(COALESCE(fee_major_mapped, '')) <> ''
            ORDER BY fee_major_mapped, period_ym
            """,
            (import_kind,),
        )
        rows = await cur.fetchall()
        batch_cur = await db.execute(
            """
            SELECT file_name, created_at
            FROM expense_actual_import_batch
            WHERE import_kind = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (import_kind,),
        )
        batch_row = await batch_cur.fetchone()
    if batch_row:
        file_name, created_at = batch_row
        source = f"费用执行明细导入（来源 {text(file_name) or '-'}，导入时间 {text(created_at) or '-'}）"
    for fee_major, period_ym, amount in rows:
        fee_major_name = text(fee_major)
        month_idx = _parse_month(period_ym)
        if not fee_major_name or month_idx is None:
            continue
        monthly_totals[fee_major_name][month_idx - 1] += round(float(amount or 0.0), 2)
    return (
        {key: [round(value, 2) for value in values] for key, values in monthly_totals.items()},
        source,
    )


def fee_major_cumulative_total(
    fee_major_monthly_totals: dict[str, list[float]],
    fee_major_name: str,
    current_month: int,
) -> float:
    values = fee_major_monthly_totals.get(fee_major_name, [0.0] * 12)
    return round(sum(float(values[idx] if idx < current_month else 0.0) for idx in range(12)), 2)
