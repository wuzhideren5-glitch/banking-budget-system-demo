from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter, Response

from app.schemas import BudgetSummaryExportPivotRequest


def build_budget_summary_export_router(
    *,
    export_budget_pivot_aggregate: Callable[..., Awaitable[Response]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/budget-summary/export-aggregate-pivot")
    async def export_budget_summary_aggregate_pivot(body: BudgetSummaryExportPivotRequest):
        return await export_budget_pivot_aggregate(
            body=body,
            output_filename="budget_pivot_aggregate_export.xlsx",
        )

    return router
