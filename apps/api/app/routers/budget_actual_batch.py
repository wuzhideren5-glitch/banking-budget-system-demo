from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, computed_field, field_validator

from app.schemas import BudgetFactVersionOption
from app.services.budget_actual_batch import (
    BudgetActualBatchPlanRequest,
    BudgetActualBatchProductNotFound,
    BudgetActualBatchVersionNotFound,
    list_budget_actual_batch_history as list_budget_actual_batch_history_service,
    preview_budget_actual_batch_command,
    run_budget_actual_batch_command,
)
from app.services.budget_fact_versions import load_budget_fact_version_options_from_path


class BudgetActualBatchRequest(BaseModel):
    product_code: str = "ALL"
    version_id: int | None = None
    budget_actuals: list[int] = Field(default_factory=lambda: [0, 1])
    run_formula: bool = True
    rebuild_summary: bool = True
    sync_compare: bool = True
    rebuild_aggregate: bool = True

    @field_validator("product_code")
    @classmethod
    def normalize_product_code(cls, value: str) -> str:
        code = value.strip().upper()
        return code or "ALL"

    @field_validator("budget_actuals")
    @classmethod
    def normalize_budget_actuals(cls, value: list[int]) -> list[int]:
        cleaned: list[int] = []
        for item in value:
            if int(item) not in (0, 1):
                raise ValueError("budget_actuals 只允许 0（预算数）或 1（实际数）")
            if int(item) not in cleaned:
                cleaned.append(int(item))
        if not cleaned:
            raise ValueError("至少选择一个数据类型")
        return cleaned


class MetricRollupAuditItemDto(BaseModel):
    node_code: str
    target_data_acct_code: str
    scope_code: str
    method: str
    budget_actual: int
    period_count: int
    cell_count: int
    source_count: int
    source_codes: list[str] = Field(default_factory=list)
    formula: str | None = None

    @computed_field
    @property
    def target_metric_code(self) -> str:
        return self.target_data_acct_code

    @computed_field
    @property
    def source_metric_codes(self) -> list[str]:
        return self.source_codes


class BudgetActualBatchResponse(BaseModel):
    mode: str
    budget_year: int
    version_id: int
    product_code: str
    product_count: int
    data_account_count: int
    formula_task_count: int
    formula_cell_count: int
    manual_override_cell_count: int
    metric_rollup_task_count: int = 0
    metric_rollup_cell_count: int = 0
    metric_rollup_cells_written: int = 0
    metric_rollup_audit_items: list[MetricRollupAuditItemDto] = Field(default_factory=list)
    metric_rollup_audit_truncated: bool = False
    formula_rows_recalculated: int = 0
    summary_rows_rebuilt: int = 0
    budget_aggregate_rows_rebuilt: int = 0
    compare_rows_inserted: int = 0
    compare_aggregate_rows_rebuilt: int = 0
    selected_compare_versions: int = 0
    warnings: list[str] = Field(default_factory=list)
    message: str = ""

    @computed_field
    @property
    def metric_count(self) -> int:
        return self.data_account_count


class BudgetActualBatchHistoryItem(BaseModel):
    log_id: int
    create_time: str
    user_id: str | None = None
    version_id: int | None = None
    budget_year: int | None = None
    product_code: str = ""
    product_count: int = 0
    budget_actuals: list[int] = Field(default_factory=list)
    run_formula: bool = False
    rebuild_summary: bool = False
    sync_compare: bool = False
    rebuild_aggregate: bool = False
    data_account_count: int = 0
    formula_task_count: int = 0
    formula_cell_count: int = 0
    manual_override_cell_count: int = 0
    metric_rollup_task_count: int = 0
    metric_rollup_cell_count: int = 0
    metric_rollup_cells_written: int = 0
    formula_rows_recalculated: int = 0
    summary_rows_rebuilt: int = 0
    budget_aggregate_rows_rebuilt: int = 0
    compare_rows_inserted: int = 0
    compare_aggregate_rows_rebuilt: int = 0
    selected_compare_versions: int = 0
    affected_rows: int = 0

    @computed_field
    @property
    def metric_count(self) -> int:
        return self.data_account_count


def _plan_request(body: BudgetActualBatchRequest) -> BudgetActualBatchPlanRequest:
    return BudgetActualBatchPlanRequest(
        product_code=body.product_code,
        version_id=body.version_id,
        budget_actuals=body.budget_actuals,
        run_formula=body.run_formula,
        rebuild_summary=body.rebuild_summary,
        sync_compare=body.sync_compare,
        rebuild_aggregate=body.rebuild_aggregate,
    )


def _response_model(result: Any) -> BudgetActualBatchResponse:
    return BudgetActualBatchResponse(**asdict(result))


def _batch_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, BudgetActualBatchVersionNotFound):
        return HTTPException(status_code=400, detail=f"版本 {exc.version_id} 不存在")
    if isinstance(exc, BudgetActualBatchProductNotFound):
        return HTTPException(status_code=404, detail=f"机构及产品不存在：{exc.product_code}")
    return HTTPException(status_code=400, detail=str(exc))


def build_budget_actual_batch_router(
    *,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
    formula_rows_for_product: Callable[..., Awaitable[list[tuple[str, str]]]],
    recalculate_product_formula_rows: Callable[..., Awaitable[int]],
    estimate_metric_tree_rollups: Callable[..., Awaitable[Any]],
    rebuild_metric_tree_rollups: Callable[..., Awaitable[Any]],
    rebuild_budget_summary_for_version: Callable[[int, Path | None], Awaitable[int]],
    sync_compare_budget_summary: Callable[..., Awaitable[Any]],
    set_budget_refresh_time: Callable[[Path, str], Awaitable[None]],
    iso_now: Callable[[], str],
    write_operation_log: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/budget-actual-batch/versions", response_model=list[BudgetFactVersionOption])
    async def list_budget_actual_batch_versions():
        editable_budget_path, _editable_year, _editable_vid = await editable_context_provider()
        return await load_budget_fact_version_options_from_path(editable_budget_path)

    @router.post("/api/budget-actual-batch/preview", response_model=BudgetActualBatchResponse)
    async def preview_budget_actual_batch(body: BudgetActualBatchRequest):
        try:
            result = await preview_budget_actual_batch_command(
                _plan_request(body),
                editable_context_provider=editable_context_provider,
                formula_rows_for_product=formula_rows_for_product,
                estimate_metric_tree_rollups=estimate_metric_tree_rollups,
            )
        except (BudgetActualBatchProductNotFound, BudgetActualBatchVersionNotFound, ValueError) as exc:
            raise _batch_http_exception(exc) from exc
        return _response_model(result)

    @router.get("/api/budget-actual-batch/history", response_model=list[BudgetActualBatchHistoryItem])
    async def list_budget_actual_batch_history(limit: int = Query(30, ge=1, le=200)):
        rows = await list_budget_actual_batch_history_service(limit=int(limit))
        return [BudgetActualBatchHistoryItem(**asdict(row)) for row in rows]

    @router.post("/api/budget-actual-batch/run", response_model=BudgetActualBatchResponse)
    async def run_budget_actual_batch(body: BudgetActualBatchRequest):
        try:
            result = await run_budget_actual_batch_command(
                _plan_request(body),
                editable_context_provider=editable_context_provider,
                formula_rows_for_product=formula_rows_for_product,
                estimate_metric_tree_rollups=estimate_metric_tree_rollups,
                recalculate_product_formula_rows=recalculate_product_formula_rows,
                rebuild_metric_tree_rollups=rebuild_metric_tree_rollups,
                rebuild_budget_summary_for_version=rebuild_budget_summary_for_version,
                sync_compare_budget_summary=sync_compare_budget_summary,
                set_budget_refresh_time=set_budget_refresh_time,
                iso_now=iso_now,
                write_operation_log=write_operation_log,
            )
        except (BudgetActualBatchProductNotFound, BudgetActualBatchVersionNotFound, ValueError) as exc:
            raise _batch_http_exception(exc) from exc
        return _response_model(result)

    return router
