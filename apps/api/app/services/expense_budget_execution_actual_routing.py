"""Route imported actual rows to report subjects by budget release caliber."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
from app.core.db_paths import common_db_path
from app.services.expense_budget_execution_budget_rollup import normalize_budget_subject_name

OUTSOURCE_SUBJECT = "外包服务费"
DAILY_OUTSOURCE_SUBJECT = "日常外包服务费"
IT_OUTSOURCE_SUBJECT = "IT外包服务费"


def text_value(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _uses_mysql_path(path: Path | str) -> bool:
    candidate = Path(path).expanduser().resolve(strict=False)
    temp_root = Path(tempfile.gettempdir()).expanduser().resolve(strict=False)
    try:
        candidate.relative_to(temp_root)
        return False
    except ValueError:
        pass
    data_dir = Path(settings.data_dir).expanduser().resolve(strict=False)
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    return candidate.name == "common.db"


async def _mysql_table_exists(table_name: str) -> bool:
    value = await get_pool().fetch_val(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return bool(value)


def route_actual_subject_by_caliber(subject_name: str, budget_release_caliber_mapped: Any) -> str:
    """Split shared outsource actuals so daily / IT / operating portions stay separate."""
    subject = normalize_budget_subject_name(subject_name)
    if subject != OUTSOURCE_SUBJECT:
        return subject
    caliber_raw = text_value(budget_release_caliber_mapped)
    if caliber_raw == DAILY_OUTSOURCE_SUBJECT:
        return DAILY_OUTSOURCE_SUBJECT
    if caliber_raw == IT_OUTSOURCE_SUBJECT:
        return IT_OUTSOURCE_SUBJECT
    return subject


def _parse_month(value: Any) -> int | None:
    raw_text = text_value(value)
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


async def load_fee_major_monthly_totals(
    *,
    import_kind: str = "current_year_actual",
) -> tuple[dict[str, list[float]], str]:
    """Load month arrays keyed by imported fee_major_mapped."""
    monthly_totals: dict[str, list[float]] = defaultdict(lambda: [0.0] * 12)
    source = "费用执行明细导入（尚未初始化）"
    db_path = common_db_path()
    if _uses_mysql_path(db_path):
        if not await _mysql_table_exists("expense_actual_detail_raw"):
            return {}, source
        rows = await get_pool().fetch_all(
            """
            SELECT fee_major_mapped, period_ym, amount
            FROM expense_actual_detail_raw
            WHERE COALESCE(import_kind, '') = %s
              AND TRIM(COALESCE(fee_major_mapped, '')) <> ''
            ORDER BY fee_major_mapped, period_ym
            """,
            (import_kind,),
        )
        batch_row = await get_pool().fetch_one(
            """
            SELECT file_name, created_at
            FROM expense_actual_import_batch
            WHERE import_kind = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (import_kind,),
        )
    else:
        with sqlite3.connect(db_path) as db:
            cur = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='expense_actual_detail_raw'"
            )
            if not cur.fetchone():
                return {}, source
            cur = db.execute(
                """
                SELECT fee_major_mapped, period_ym, amount
                FROM expense_actual_detail_raw
                WHERE COALESCE(import_kind, '') = ?
                  AND TRIM(COALESCE(fee_major_mapped, '')) <> ''
                ORDER BY fee_major_mapped, period_ym
                """,
                (import_kind,),
            )
            rows = cur.fetchall()
            batch_cur = db.execute(
                """
                SELECT file_name, created_at
                FROM expense_actual_import_batch
                WHERE import_kind = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (import_kind,),
            )
            batch_row = batch_cur.fetchone()
    if batch_row:
        file_name = _row_value(batch_row, "file_name", 0)
        created_at = _row_value(batch_row, "created_at", 1)
        source = f"费用执行明细导入（来源 {text_value(file_name) or '-'}，导入时间 {text_value(created_at) or '-'}）"
    for row in rows:
        fee_major = _row_value(row, "fee_major_mapped", 0)
        period_ym = _row_value(row, "period_ym", 1)
        amount = _row_value(row, "amount", 2)
        fee_major_name = text_value(fee_major)
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
