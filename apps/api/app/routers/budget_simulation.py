"""模拟测算 Module：使用机构及产品指标读取基准值并生成测算结果。"""
from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from fastapi import APIRouter

from app.core.db_paths import common_db_path
from app.schemas import (
    SimulationBaselineRequestItem,
    SimulationBaselineRow,
    SimulationInputItem,
    SimulationResultRow,
)
from app.services.budget_simulation_export import build_budget_simulation_export_buffer
from app.services.budget_simulation_metrics import build_budget_simulation_baseline_rows
from app.services.budget_simulation_results import build_budget_simulation_result_rows
from app.services.export_common import excel_streaming_response


def build_budget_simulation_router(
    *,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
    get_year_period_months: Callable[[int], Awaitable[dict[int, int]]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/budget-simulation/baseline", response_model=list[SimulationBaselineRow])
    async def get_simulation_baseline(body: list[SimulationBaselineRequestItem]):
        budget_path, budget_year, version_id = await editable_context_provider()
        return await build_budget_simulation_baseline_rows(
            common_path=common_db_path(),
            budget_path=budget_path,
            version_id=version_id,
            period_month_map=await get_year_period_months(budget_year),
            body=body,
        )

    @router.post("/api/budget-simulation/result", response_model=list[SimulationResultRow])
    async def get_simulation_result(body: list[SimulationInputItem]):
        return await build_budget_simulation_result_rows(common_db_path(), body)

    @router.post("/api/budget-simulation/export")
    async def export_simulation_excel(body: list[SimulationInputItem]):
        budget_path, budget_year, version_id = await editable_context_provider()
        baseline_rows = await build_budget_simulation_baseline_rows(
            common_path=common_db_path(),
            budget_path=budget_path,
            version_id=version_id,
            period_month_map=await get_year_period_months(budget_year),
            body=[
                SimulationBaselineRequestItem(
                    indicator_code=item.indicator_code,
                    product_code=item.product_code,
                )
                for item in body
            ],
        )
        result_rows = await build_budget_simulation_result_rows(common_db_path(), body)
        bio, filename = build_budget_simulation_export_buffer(
            params=body,
            result_rows=result_rows,
            baseline_rows=baseline_rows,
        )
        return excel_streaming_response(
            bio,
            filename=filename,
            fallback_filename=filename,
        )

    return router
