from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

import app.core.aiosqlite_compat as aiosqlite
from fastapi import APIRouter

from app.db_bootstrap.budget_version import ensure_budget_version_schema
from app.core.db_paths import compare_db_path
from app.schemas import (
    BudgetSummaryAggregateRequest,
    BudgetSummaryRowDto,
    CompareSummaryRowDto,
    CompareSyncLatestStatus,
)
from app.services.pivot_aggregate import list_budget_pivot_aggregate_rows, list_compare_pivot_aggregate_rows


def build_budget_summary_compare_router(
    *,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/budget-summary/aggregate", response_model=list[BudgetSummaryRowDto])
    async def list_budget_summary_aggregate(body: BudgetSummaryAggregateRequest):
        editable_budget_path, _editable_year, _editable_vid = await editable_context_provider()
        async with aiosqlite.connect(editable_budget_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await ensure_budget_version_schema(db)
            cur_ver = await db.execute("SELECT version_id, current_month FROM version")
            version_month_map = {int(r[0]): int(r[1]) for r in await cur_ver.fetchall()}
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
        path = compare_db_path()
        if not path.exists():
            return CompareSyncLatestStatus()
        async with aiosqlite.connect(path) as cdb:
            await cdb.execute("PRAGMA foreign_keys = ON")
            cur = await cdb.execute(
                """
                SELECT job_id, start_time, end_time, trigger_source, status, message
                FROM compare_sync_job_log
                ORDER BY job_id DESC
                LIMIT 1
                """
            )
            row = await cur.fetchone()
        if not row:
            return CompareSyncLatestStatus()
        return CompareSyncLatestStatus(
            job_id=int(row[0]),
            start_time=str(row[1]) if row[1] is not None else None,
            end_time=str(row[2]) if row[2] is not None else None,
            trigger_source=str(row[3]) if row[3] is not None else None,
            status=str(row[4]) if row[4] is not None else None,
            message=str(row[5]) if row[5] is not None else None,
        )

    return router
