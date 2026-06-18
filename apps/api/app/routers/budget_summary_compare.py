from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import APIRouter

from app.core.config import settings
from app.core.database import get_pool
from app.core.db_paths import compare_db_path
from app.db_bootstrap.budget_version import ensure_budget_version_schema_sync
from app.schemas import (
    BudgetSummaryAggregateRequest,
    BudgetSummaryRowDto,
    CompareSummaryRowDto,
    CompareSyncLatestStatus,
)
from app.services.pivot_aggregate import list_budget_pivot_aggregate_rows, list_compare_pivot_aggregate_rows


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
    return candidate.name == "common.db" or candidate.name == "compare.db" or (
        candidate.name.startswith("budget_") and candidate.suffix == ".db"
    )


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _budget_year_from_path(path: Path | str) -> int | None:
    stem = Path(path).stem
    if not stem.startswith("budget_"):
        return None
    suffix = stem.removeprefix("budget_")
    return int(suffix) if suffix.isdigit() else None


async def load_budget_version_month_map(budget_path: Path | str) -> dict[int, int]:
    if _uses_mysql_path(budget_path):
        budget_year = _budget_year_from_path(budget_path)
        if budget_year is None:
            rows = await get_pool().fetch_all("SELECT version_id, current_month FROM version")
        else:
            rows = await get_pool().fetch_all(
                "SELECT version_id, current_month FROM version WHERE budget_year = %s",
                (budget_year,),
            )
        return {int(row["version_id"]): int(row["current_month"]) for row in rows}
    return _load_budget_version_month_map_sqlite(Path(budget_path))


def _load_budget_version_month_map_sqlite(budget_path: Path) -> dict[int, int]:
    with sqlite3.connect(budget_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        ensure_budget_version_schema_sync(db)
        rows = db.execute("SELECT version_id, current_month FROM version").fetchall()
    return {int(row[0]): int(row[1]) for row in rows}


async def load_compare_sync_latest_status(path: Path | str | None = None) -> CompareSyncLatestStatus:
    compare_path = path or compare_db_path()
    if _uses_mysql_path(compare_path):
        row = await get_pool().fetch_one(
            """
            SELECT job_id, start_time, end_time, trigger_source, status, message
            FROM compare_sync_job_log
            ORDER BY job_id DESC
            LIMIT 1
            """
        )
        return _compare_sync_status_from_row(row)
    return _load_compare_sync_latest_status_sqlite(Path(compare_path))


def _load_compare_sync_latest_status_sqlite(path: Path) -> CompareSyncLatestStatus:
    if not path.exists():
        return CompareSyncLatestStatus()
    with sqlite3.connect(path) as cdb:
        cdb.execute("PRAGMA foreign_keys = ON")
        row = cdb.execute(
            """
            SELECT job_id, start_time, end_time, trigger_source, status, message
            FROM compare_sync_job_log
            ORDER BY job_id DESC
            LIMIT 1
            """
        ).fetchone()
    return _compare_sync_status_from_row(row)


def _compare_sync_status_from_row(row: Any) -> CompareSyncLatestStatus:
    if not row:
        return CompareSyncLatestStatus()
    return CompareSyncLatestStatus(
        job_id=int(_row_value(row, "job_id", 0)),
        start_time=str(_row_value(row, "start_time", 1)) if _row_value(row, "start_time", 1) is not None else None,
        end_time=str(_row_value(row, "end_time", 2)) if _row_value(row, "end_time", 2) is not None else None,
        trigger_source=str(_row_value(row, "trigger_source", 3))
        if _row_value(row, "trigger_source", 3) is not None
        else None,
        status=str(_row_value(row, "status", 4)) if _row_value(row, "status", 4) is not None else None,
        message=str(_row_value(row, "message", 5)) if _row_value(row, "message", 5) is not None else None,
    )


def build_budget_summary_compare_router(
    *,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/budget-summary/aggregate", response_model=list[BudgetSummaryRowDto])
    async def list_budget_summary_aggregate(body: BudgetSummaryAggregateRequest):
        editable_budget_path, _editable_year, _editable_vid = await editable_context_provider()
        version_month_map = await load_budget_version_month_map(editable_budget_path)
        return await list_budget_pivot_aggregate_rows(
            budget_path=editable_budget_path,
            body=body,
            current_month_by_version=version_month_map,
        )

    @router.post("/api/compare-summary/aggregate", response_model=list[CompareSummaryRowDto])
    async def list_compare_summary_aggregate(body: BudgetSummaryAggregateRequest):
        return await list_compare_pivot_aggregate_rows(body)

    @router.get("/api/compare-summary/sync/latest", response_model=CompareSyncLatestStatus)
    async def get_compare_summary_sync_latest():
        return await load_compare_sync_latest_status()

    return router
