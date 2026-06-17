from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.services.expense_forecast_rule_commands import ExpenseForecastRuleDeleteNotFound
from app.services.expense_forecast_rule_detail import ExpenseForecastRuleDetailNotFound
from app.services.expense_forecast_rule_simulation import ExpenseForecastRuleSimulationError


RuleSchemeCode = Literal["MANUAL", "RESIDUAL_ALLOC", "METRIC_EXPR"]
MetricSourcePriority = Literal["metric_first", "inline_first"]
ForecastValueSource = Literal["actual", "manual", "auto", "override", "unconfigured", "aggregate"]
VariableSourceType = Literal["metric_tree", "org_product_metric", "forecast_inline", "actual", "annual_field", "constant"]


class ExpenseForecastRuleParamItem(BaseModel):
    param_group: str = "common"
    param_key: str
    param_value: str | None = None
    value_type: str = "string"


class ExpenseForecastRuleVariableItem(BaseModel):
    variable_code: str
    variable_name: str | None = None
    source_type: VariableSourceType
    source_key: str | None = None
    source_subkey: str | None = None
    org_product_ref: str | None = None
    org_product_metric_code: str | None = None
    org_product_entity_code: str | None = None
    org_product_table_name: str | None = None
    default_value: float | None = None
    sort_order: int = 0
    org_product_refs: list[str] = Field(default_factory=list)


class ExpenseForecastRuleRow(BaseModel):
    id: int
    forecast_year: int
    forecast_version: str
    owner_name: str
    subject_id: int
    subject_name: str
    scheme_code: RuleSchemeCode
    enabled: bool = True
    allow_manual_override: bool = False
    auto_refresh_enabled: bool = True
    manual_recalc_enabled: bool = True
    metric_source_priority: MetricSourcePriority = "metric_first"
    effective_from_month: int = 1
    effective_to_month: int = 12
    priority: int = 100
    remark: str | None = None
    created_at: str
    updated_at: str
    params: list[ExpenseForecastRuleParamItem] = Field(default_factory=list)
    variables: list[ExpenseForecastRuleVariableItem] = Field(default_factory=list)


class ExpenseForecastRuleListResponse(BaseModel):
    items: list[ExpenseForecastRuleRow] = Field(default_factory=list)


class ExpenseForecastRuleSaveRequest(BaseModel):
    forecast_year: int
    forecast_version: str
    owner_name: str
    subject_id: int
    scheme_code: RuleSchemeCode
    enabled: bool = True
    allow_manual_override: bool = False
    auto_refresh_enabled: bool = True
    manual_recalc_enabled: bool = True
    metric_source_priority: MetricSourcePriority = "metric_first"
    effective_from_month: int = 1
    effective_to_month: int = 12
    priority: int = 100
    remark: str | None = None
    params: list[ExpenseForecastRuleParamItem] = Field(default_factory=list)
    variables: list[ExpenseForecastRuleVariableItem] = Field(default_factory=list)


class ExpenseForecastRuleCopyRequest(BaseModel):
    forecast_year: int
    source_version: str
    target_version: str


class ExpenseForecastRuleCopyResponse(BaseModel):
    copied_rules: int


class ExpenseForecastRuleImportPreviewItem(BaseModel):
    row_number: int
    owner_name: str
    subject_name: str
    scheme_code: str
    action: str
    message: str | None = None


class ExpenseForecastRuleImportPreviewResponse(BaseModel):
    file_name: str
    preview_count: int
    insertable_rules: int
    updatable_rules: int
    skipped_rules: int
    error_rules: int
    items: list[ExpenseForecastRuleImportPreviewItem] = Field(default_factory=list)


class ExpenseForecastRuleImportApplyResponse(BaseModel):
    file_name: str
    inserted_rules: int
    updated_rules: int
    skipped_rules: int
    error_rules: int


class ExpenseForecastRecalculateRequest(BaseModel):
    forecast_year: int
    forecast_version: str
    owner_name: str | None = None
    subject_id: int | None = None


class ExpenseForecastRecalculateResponse(BaseModel):
    recalculated_rules: int
    updated_cells: int


class ExpenseForecastTraceMonthItem(BaseModel):
    month: int
    final_value: float
    system_value: float | None = None
    override_value: float | None = None
    value_source: ForecastValueSource
    calc_basis_json: str | None = None


class ExpenseForecastRuleSimulateRequest(BaseModel):
    forecast_year: int
    forecast_version: str
    owner_name: str
    subject_id: int
    scheme_code: RuleSchemeCode
    metric_source_priority: MetricSourcePriority = "metric_first"
    effective_from_month: int = 1
    effective_to_month: int = 12
    params: list[ExpenseForecastRuleParamItem] = Field(default_factory=list)
    variables: list[ExpenseForecastRuleVariableItem] = Field(default_factory=list)


class ExpenseForecastRuleSimulateResponse(BaseModel):
    scheme_code: RuleSchemeCode
    months: list[ExpenseForecastTraceMonthItem] = Field(default_factory=list)


def register_expense_forecast_rule_routes(
    router: APIRouter,
    *,
    default_year: int,
    list_rules: Callable[..., Awaitable[list[dict[str, Any]]]],
    load_rule_detail: Callable[..., Awaitable[dict[str, Any]]],
    save_rule: Callable[..., Awaitable[ExpenseForecastRuleRow]],
    delete_rule: Callable[..., Awaitable[None]],
    recalculate_rules: Callable[..., Awaitable[tuple[int, int]]],
    simulate_rule: Callable[..., Awaitable[dict[str, Any]]],
    copy_rules: Callable[..., Awaitable[int]],
    download_rule_template: Callable[[], Any],
    preview_rule_import: Callable[..., Awaitable[Any]],
    apply_rule_import: Callable[..., Awaitable[Any]],
) -> None:
    async def _run_rule_import_upload_workflow(file: UploadFile, workflow: Callable[..., Awaitable[Any]]) -> Any:
        raw = await file.read()
        try:
            return await workflow(raw=raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/expense-forecast/rules", response_model=ExpenseForecastRuleListResponse)
    async def get_expense_forecast_rules(
        year: int = Query(default_year),
        forecast_version: str = Query(...),
        owner_name: str = Query(""),
        subject_id: int | None = Query(None),
    ):
        rows = await list_rules(
            year=year,
            forecast_version=forecast_version,
            owner_name=owner_name,
            subject_id=subject_id,
        )
        return ExpenseForecastRuleListResponse(
            items=[ExpenseForecastRuleRow.model_validate(row) for row in rows]
        )

    @router.get("/api/expense-forecast/rules/by-id/{rule_id}", response_model=ExpenseForecastRuleRow)
    async def get_expense_forecast_rule(rule_id: int):
        try:
            matched = await load_rule_detail(rule_id=rule_id)
        except ExpenseForecastRuleDetailNotFound as exc:
            raise HTTPException(status_code=404, detail="预测规则不存在") from exc
        return ExpenseForecastRuleRow.model_validate(matched)

    @router.post("/api/expense-forecast/rules", response_model=ExpenseForecastRuleRow)
    async def create_expense_forecast_rule(body: ExpenseForecastRuleSaveRequest):
        return await save_rule(body)

    @router.put("/api/expense-forecast/rules/{rule_id}", response_model=ExpenseForecastRuleRow)
    async def update_expense_forecast_rule(rule_id: int, body: ExpenseForecastRuleSaveRequest):
        return await save_rule(body, rule_id=rule_id)

    @router.delete("/api/expense-forecast/rules/{rule_id}")
    async def delete_expense_forecast_rule(rule_id: int):
        try:
            await delete_rule(rule_id=rule_id)
        except ExpenseForecastRuleDeleteNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/expense-forecast/rules/copy-from-version", response_model=ExpenseForecastRuleCopyResponse)
    async def copy_expense_forecast_rules_from_version(body: ExpenseForecastRuleCopyRequest):
        copied = await copy_rules(
            year=int(body.forecast_year),
            source_version=body.source_version,
            target_version=body.target_version,
        )
        return ExpenseForecastRuleCopyResponse(copied_rules=copied)

    @router.get("/api/expense-forecast/rules/template")
    async def download_expense_forecast_rule_template():
        return download_rule_template()

    @router.post("/api/expense-forecast/rules/import-preview", response_model=ExpenseForecastRuleImportPreviewResponse)
    async def preview_expense_forecast_rule_import(file: UploadFile = File(...)):
        preview = await _run_rule_import_upload_workflow(file, preview_rule_import)
        return ExpenseForecastRuleImportPreviewResponse(
            file_name=file.filename or "费用预测逻辑配置.xlsx",
            preview_count=preview.preview_count,
            insertable_rules=preview.insertable_rules,
            updatable_rules=preview.updatable_rules,
            skipped_rules=preview.skipped_rules,
            error_rules=preview.error_rules,
            items=[ExpenseForecastRuleImportPreviewItem.model_validate(item) for item in preview.items],
        )

    @router.post("/api/expense-forecast/rules/import-apply", response_model=ExpenseForecastRuleImportApplyResponse)
    async def apply_expense_forecast_rule_import(file: UploadFile = File(...)):
        result = await _run_rule_import_upload_workflow(file, apply_rule_import)
        return ExpenseForecastRuleImportApplyResponse(
            file_name=file.filename or "费用预测逻辑配置.xlsx",
            inserted_rules=result.inserted_rules,
            updated_rules=result.updated_rules,
            skipped_rules=result.skipped_rules,
            error_rules=result.error_rules,
        )

    @router.post("/api/expense-forecast/recalculate", response_model=ExpenseForecastRecalculateResponse)
    async def recalculate_expense_forecast(body: ExpenseForecastRecalculateRequest):
        recalculated, updated_cells = await recalculate_rules(
            year=int(body.forecast_year),
            forecast_version=body.forecast_version,
            owner_name=body.owner_name,
            subject_id=body.subject_id,
        )
        return ExpenseForecastRecalculateResponse(recalculated_rules=recalculated, updated_cells=updated_cells)

    @router.post("/api/expense-forecast/rules/simulate", response_model=ExpenseForecastRuleSimulateResponse)
    async def simulate_expense_forecast_rule(body: ExpenseForecastRuleSimulateRequest):
        try:
            result = await simulate_rule(rule=body.model_dump())
        except ExpenseForecastRuleSimulationError as exc:
            raise HTTPException(status_code=404, detail="预算科目不存在")
        return ExpenseForecastRuleSimulateResponse.model_validate(result)
