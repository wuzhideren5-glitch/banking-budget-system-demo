from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.schemas import BudgetSummaryExportPivotRequest


def build_budget_summary_export_router(
    *,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
    export_budget_summary_from_template: Callable[..., Awaitable[StreamingResponse]],
    export_budget_summary_formula_tree_workbook: Callable[..., Awaitable[StreamingResponse]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/budget-summary/export-full-pivot")
    async def export_budget_summary_full_pivot(body: BudgetSummaryExportPivotRequest):
        return await export_budget_summary_from_template(
            body=body,
            output_filename="budget_summary_full_pivot.xlsx",
        )

    @router.post("/api/budget-summary/export-formula-workbook")
    async def export_budget_summary_formula_workbook(
        body: BudgetSummaryExportPivotRequest,
        version_id: int | None = Query(None),
    ):
        editable_budget_path, editable_year, editable_vid = await editable_context_provider()
        vid = int(version_id if version_id is not None else editable_vid)
        return await export_budget_summary_formula_tree_workbook(
            body,
            vid,
            editable_budget_path,
            editable_year,
        )

    return router
