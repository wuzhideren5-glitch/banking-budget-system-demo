from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter, Response

from app.schemas import BudgetSummaryExportPivotRequest


def build_compare_summary_export_router(
    *,
    export_compare_pivot_aggregate_callable: Callable[[BudgetSummaryExportPivotRequest], Awaitable[Response]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/compare-summary/export-aggregate-pivot")
    async def export_compare_summary_aggregate_pivot(body: BudgetSummaryExportPivotRequest):
        return await export_compare_pivot_aggregate_callable(body)

    return router
