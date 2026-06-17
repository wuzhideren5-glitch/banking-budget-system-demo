from __future__ import annotations

from datetime import datetime
import sqlite3
from typing import Any, Awaitable, Callable, Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.db_paths import budget_db_path, common_db_path
from app.routers.expense_forecast_rules import (
    ExpenseForecastRuleRow,
    ExpenseForecastRuleSaveRequest,
    ExpenseForecastTraceMonthItem,
    ForecastValueSource,
    RuleSchemeCode,
    register_expense_forecast_rule_routes,
)
from app.services.expense_forecast_export_workflow import (
    ExpenseForecastExportPlanError,
    build_expense_forecast_export_from_source,
    build_expense_forecast_group_export_from_source,
)
from app.services.expense_forecast_cell_commands import (
    ExpenseForecastCellWorkflowError,
    upsert_expense_forecast_cell_with_validation,
)
from app.services.expense_forecast_data_context import (
    ExpenseForecastDataContextError,
    build_expense_forecast_subject_lookup,
    load_expense_forecast_actual_cutoff_month,
    load_expense_forecast_actual_map,
    load_expense_forecast_annual_budget_map,
    load_expense_forecast_annual_input_map,
    load_expense_forecast_budget_subject_rows,
    load_expense_forecast_forecast_map,
    load_expense_forecast_manage_department_map,
    load_expense_forecast_product_department_owner_map,
    load_expense_forecast_scope_rows,
    resolve_expense_forecast_scope_owners,
)
from app.services.expense_forecast_import_apply import apply_expense_forecast_import_rows_with_recalculation
from app.services.expense_forecast_import_preview import (
    ExpenseForecastImportPreviewWorkflowError,
    build_expense_forecast_import_preview_from_source,
)
from app.services.expense_forecast_meta import (
    default_expense_forecast_version,
    load_expense_forecast_meta,
    load_expense_forecast_owner_group_options,
)
from app.services.expense_forecast_metric_sources import load_expense_forecast_metric_source_month_map
from app.services.expense_forecast_override_commands import (
    ExpenseForecastOverrideWorkflowError,
    delete_expense_forecast_override_with_restore,
    save_expense_forecast_override_with_rule_check,
)
from app.services.expense_forecast_recalculation import recalculate_expense_forecast_rules
from app.services.expense_forecast_recalculation_commands import save_expense_forecast_recalculation_results
from app.services.expense_forecast_rule_calculation import calculate_expense_forecast_rule_months
from app.services.expense_forecast_rule_commands import (
    delete_expense_forecast_rule_definition_or_raise,
    save_expense_forecast_rule_definition,
)
from app.services.expense_forecast_rule_copy import copy_expense_forecast_rules_from_version
from app.services.expense_forecast_rule_detail import load_expense_forecast_rule_detail
from app.services.expense_forecast_rule_import import build_expense_forecast_rule_template_workbook
from app.services.expense_forecast_rule_import_workflow import (
    apply_expense_forecast_rule_import_workbook,
    preview_expense_forecast_rule_import_workbook,
    resolve_org_product_variables,
)
from app.services.expense_forecast_rule_read_model import (
    build_enabled_expense_forecast_rule_map,
    load_expense_forecast_calc_result_map,
    load_expense_forecast_override_map,
    load_expense_forecast_rule_identity,
    load_expense_forecast_rule_rows,
)
from app.services.expense_forecast_rule_save import (
    ExpenseForecastRuleSaveError,
    save_expense_forecast_rule,
)
from app.services.expense_forecast_rule_simulation import (
    simulate_expense_forecast_rule as simulate_expense_forecast_rule_definition,
)
from app.services.expense_forecast_schema import ensure_expense_forecast_schema_ready
from app.services.expense_forecast_trace import build_expense_forecast_trace_read_model_from_source
from app.services.runtime_metric_refs import load_org_product_metric_refs_by_runtime_ref_code_sync
from app.services.expense_forecast_view_read_model import (
    ExpenseForecastViewReadModelError,
    build_expense_forecast_group_read_model,
    build_expense_forecast_scope_read_model,
    build_expense_forecast_subject_read_model,
)
from app.services.export_common import excel_streaming_response

ScopeType = Literal["entity", "group", "owner"]
ImportMode = Literal["append", "overwrite"]
MonthValueSource = Literal["actual", "forecast"]
EditableFieldName = Literal["month_forecast", "business_submission", "capital_advice"]
AnnualEntryFieldName = Literal["business_submission", "capital_advice"]
CompileMode = Literal["scope", "subject"]

ALL_OWNER_SCOPE_VALUE = "__ALL_OWNER_DEPARTMENTS__"


class ExpenseForecastScopeOption(BaseModel):
    value: str
    label: str


class ExpenseForecastOwnerGroupOption(BaseModel):
    group_value: str
    group_label: str
    owner_options: list[ExpenseForecastScopeOption] = Field(default_factory=list)


class ExpenseForecastLeafSubjectOption(BaseModel):
    id: int
    label: str


class ExpenseForecastMetaResponse(BaseModel):
    default_year: int
    default_version: str
    version_suggestions: list[str] = Field(default_factory=list)
    entity_options: list[ExpenseForecastScopeOption] = Field(default_factory=list)
    group_options: list[ExpenseForecastScopeOption] = Field(default_factory=list)
    owner_options: list[ExpenseForecastScopeOption] = Field(default_factory=list)
    owner_group_options: list[ExpenseForecastOwnerGroupOption] = Field(default_factory=list)
    leaf_subject_options: list[ExpenseForecastLeafSubjectOption] = Field(default_factory=list)


class ExpenseForecastMonthCell(BaseModel):
    month: int
    value: float
    source: MonthValueSource
    editable: bool = False
    rule_configured: bool = False
    rule_scheme: RuleSchemeCode | None = None
    value_source: ForecastValueSource = "manual"
    has_override: bool = False
    system_value: float | None = None
    override_value: float | None = None
    override_reason: str | None = None


class ExpenseForecastRow(BaseModel):
    id: int
    parent_id: int | None = None
    level_number: int
    subject_name: str
    formula_text: str | None = None
    sort_order: int = 0
    is_leaf: bool = False
    months: list[ExpenseForecastMonthCell] = Field(default_factory=list)
    total_value: float = 0
    annual_budget: float = 0
    forecast_budget_gap: float = 0
    budget_execution_rate: float | None = None
    business_submission: float = 0
    capital_advice: float = 0
    capital_advice_gap: float = 0
    business_submission_editable: bool = False
    capital_advice_editable: bool = False
    rule_configured: bool = False
    rule_scheme: RuleSchemeCode | None = None
    allow_manual_override: bool = False
    rule_id: int | None = None


class ExpenseForecastViewResponse(BaseModel):
    year: int
    forecast_version: str
    scope_type: ScopeType
    scope_value: str
    actual_cutoff_month: int = 0
    rows: list[ExpenseForecastRow] = Field(default_factory=list)


class ExpenseForecastGroupOwnerView(BaseModel):
    owner_name: str
    rows: list[ExpenseForecastRow] = Field(default_factory=list)


class ExpenseForecastGroupViewResponse(BaseModel):
    year: int
    forecast_version: str
    group_name: str
    actual_cutoff_month: int = 0
    owner_views: list[ExpenseForecastGroupOwnerView] = Field(default_factory=list)


class ExpenseForecastSubjectOwnerRow(BaseModel):
    owner_name: str
    subject_id: int
    subject_name: str
    months: list[ExpenseForecastMonthCell] = Field(default_factory=list)
    total_value: float = 0
    annual_budget: float = 0
    forecast_budget_gap: float = 0
    budget_execution_rate: float | None = None
    business_submission: float = 0
    capital_advice: float = 0
    capital_advice_gap: float = 0
    business_submission_editable: bool = False
    capital_advice_editable: bool = False
    rule_configured: bool = False
    rule_scheme: RuleSchemeCode | None = None
    allow_manual_override: bool = False
    rule_id: int | None = None


class ExpenseForecastSubjectViewResponse(BaseModel):
    year: int
    forecast_version: str
    scope_type: ScopeType
    scope_value: str
    actual_cutoff_month: int = 0
    subject_id: int
    subject_name: str
    rows: list[ExpenseForecastSubjectOwnerRow] = Field(default_factory=list)


class ExpenseForecastCellUpsertRequest(BaseModel):
    year: int
    forecast_version: str
    scope_type: ScopeType
    scope_value: str
    subject_id: int
    field_name: EditableFieldName = "month_forecast"
    month: int | None = None
    value: float
    override_reason: str | None = None


class ExpenseForecastCellUpsertResponse(BaseModel):
    updated: bool
    actual_cutoff_month: int
    mode: str = "write"


class ExpenseForecastImportPreviewItem(BaseModel):
    row_number: int
    owner_name: str | None = None
    budget_subject: str
    field_name: EditableFieldName
    field_label: str
    month: int | None = None
    value: float
    action: str
    message: str | None = None


class ExpenseForecastImportPreviewResponse(BaseModel):
    file_name: str
    import_mode: ImportMode
    actual_cutoff_month: int
    preview_count: int
    insertable_cells: int
    updatable_cells: int
    skipped_cells: int
    error_cells: int
    items: list[ExpenseForecastImportPreviewItem] = Field(default_factory=list)


class ExpenseForecastImportApplyResponse(BaseModel):
    file_name: str
    import_mode: ImportMode
    actual_cutoff_month: int
    inserted_cells: int
    updated_cells: int
    skipped_cells: int
    error_cells: int


class ExpenseForecastOverrideRequest(BaseModel):
    forecast_year: int
    forecast_version: str
    owner_name: str
    subject_id: int
    month: int
    override_value: float
    override_reason: str | None = None


class ExpenseForecastTraceResponse(BaseModel):
    forecast_year: int
    forecast_version: str
    owner_name: str
    subject_id: int
    rule_id: int | None = None
    rule_scheme: RuleSchemeCode | None = None
    items: list[ExpenseForecastTraceMonthItem] = Field(default_factory=list)


class ExpenseForecastExportRequest(BaseModel):
    year: int
    forecast_version: str
    scope_type: ScopeType
    scope_value: str
    compile_mode: CompileMode = "scope"
    subject_id: int | None = None
    amount_unit: str = "yuan"
    exclude_fields: list[str] = Field(default_factory=list)


class ExpenseForecastGroupExportRequest(BaseModel):
    year: str
    forecast_version: str
    group_name: str
    amount_unit: str = "wan"
    exclude_fields: list[str] = Field(default_factory=list)


def build_expense_forecast_router(
    *,
    default_year: int,
    write_operation_log: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter()

    def _text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _default_version() -> str:
        return default_expense_forecast_version()

    async def _ensure_tables() -> None:
        await ensure_expense_forecast_schema_ready(common_db_path())

    async def _load_metric_source_month_map(
        year: int,
        indicator_code: str,
        product_code: str | None = None,
    ) -> dict[int, float]:
        return await load_expense_forecast_metric_source_month_map(
            common_db_path=common_db_path(),
            budget_db_path=budget_db_path(year),
            year=year,
            indicator_code=indicator_code,
            product_code=product_code,
        )

    async def _calculate_rule_months(**kwargs) -> dict[int, dict[str, Any]]:
        return await calculate_expense_forecast_rule_months(
            **kwargs,
            load_metric_source_month_map=_load_metric_source_month_map,
        )

    async def _load_rule_rows(
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str] | None = None,
        subject_id: int | None = None,
    ) -> list[dict[str, Any]]:
        await _ensure_tables()
        return await load_expense_forecast_rule_rows(
            common_db_path(),
            year=year,
            forecast_version=forecast_version,
            owner_names=owner_names,
            subject_id=subject_id,
        )

    async def _list_rules(
        *,
        year: int,
        forecast_version: str,
        owner_name: str,
        subject_id: int | None,
    ) -> list[dict[str, Any]]:
        normalized_owner_name = _text(owner_name)
        return await _load_rule_rows(
            year=year,
            forecast_version=_text(forecast_version) or _default_version(),
            owner_names=[normalized_owner_name] if normalized_owner_name else None,
            subject_id=subject_id,
        )

    async def _load_rule_identity(*, rule_id: int) -> dict[str, Any] | None:
        await _ensure_tables()
        return await load_expense_forecast_rule_identity(common_db_path(), rule_id=rule_id)

    class _ExpenseForecastRuleDetailSource:
        async def load_rule_rows(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str] | None = None,
            subject_id: int | None = None,
        ) -> list[dict[str, Any]]:
            return await _load_rule_rows(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
                subject_id=subject_id,
            )

        async def load_rule_identity(self, *, rule_id: int) -> dict[str, Any] | None:
            return await _load_rule_identity(rule_id=rule_id)

    async def _load_rule_detail(*, rule_id: int) -> dict[str, Any]:
        return await load_expense_forecast_rule_detail(
            rule_id=rule_id,
            default_year=default_year,
            default_version=_default_version(),
            source=_ExpenseForecastRuleDetailSource(),
        )

    async def _delete_rule(*, rule_id: int) -> None:
        await _ensure_tables()
        await delete_expense_forecast_rule_definition_or_raise(
            db_path=common_db_path(),
            rule_id=rule_id,
        )

    async def _load_rule_map(
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int], dict[str, Any]]:
        rows = await _load_rule_rows(year=year, forecast_version=forecast_version, owner_names=owner_names)
        return build_enabled_expense_forecast_rule_map(rows)

    async def _load_calc_result_map(
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], dict[str, Any]]:
        return await load_expense_forecast_calc_result_map(
            common_db_path(),
            year=year,
            forecast_version=forecast_version,
            owner_names=owner_names,
        )

    async def _load_override_map(
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], dict[str, Any]]:
        return await load_expense_forecast_override_map(
            common_db_path(),
            year=year,
            forecast_version=forecast_version,
            owner_names=owner_names,
        )

    class _ExpenseForecastRecalculationSource:
        async def load_scope_rows(self) -> list[tuple[str, str, str]]:
            return await _load_scope_rows()

        async def load_rule_rows(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
            subject_id: int | None,
        ) -> list[dict[str, Any]]:
            return await _load_rule_rows(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
                subject_id=subject_id,
            )

        async def load_actual_cutoff_month(self, year: int) -> int:
            return await _actual_cutoff_month(year)

        async def load_actual_map(self, year: int, owner_names: list[str]) -> dict[tuple[str, str, int], float]:
            return await _load_actual_map(year, owner_names)

        async def load_annual_input_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, str], float]:
            return await _load_annual_input_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_forecast_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, int], float]:
            return await _load_forecast_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_override_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, int], dict[str, Any]]:
            return await _load_override_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_metric_source_month_map(
            self,
            year: int,
            indicator_code: str,
            product_code: str | None = None,
        ) -> dict[int, float]:
            return await _load_metric_source_month_map(year, indicator_code, product_code)

        async def save_recalculation_results(
            self,
            *,
            year: int,
            forecast_version: str,
            rows: list,
            now: str,
        ) -> int:
            return await save_expense_forecast_recalculation_results(
                db_path=common_db_path(),
                year=year,
                forecast_version=forecast_version,
                rows=rows,
                now=now,
            )

    async def _recalculate_rules(
        *,
        year: int,
        forecast_version: str,
        owner_name: str | None = None,
        subject_id: int | None = None,
        trigger: Literal["manual", "auto"] = "manual",
    ) -> tuple[int, int]:
        normalized_owner_name = _text(owner_name)
        return await recalculate_expense_forecast_rules(
            year=year,
            forecast_version=_text(forecast_version) or _default_version(),
            source=_ExpenseForecastRecalculationSource(),
            now=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            owner_name=normalized_owner_name or None,
            subject_id=subject_id,
            trigger=trigger,
        )

    class _ExpenseForecastRuleSaveSource:
        async def save_rule_definition(
            self,
            *,
            rule: dict[str, Any],
            rule_id: int | None,
            now: str,
        ):
            return await save_expense_forecast_rule_definition(
                db_path=common_db_path(),
                rule=rule,
                rule_id=rule_id,
                now=now,
            )

        async def load_rule_rows(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
            subject_id: int | None,
        ) -> list[dict[str, Any]]:
            return await _load_rule_rows(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
                subject_id=subject_id,
            )

        async def recalculate_rules(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_name: str | None,
            subject_id: int | None,
        ) -> tuple[int, int]:
            return await _recalculate_rules(
                year=year,
                forecast_version=forecast_version,
                owner_name=owner_name,
                subject_id=subject_id,
                trigger="auto",
            )

        async def write_operation_log(self, **kwargs) -> None:
            await write_operation_log(**kwargs)

    def _resolve_rule_org_product_variables(rule: dict[str, Any]) -> dict[str, Any]:
        variables = list(rule.get("variables", []) or [])
        if not variables:
            return rule
        with sqlite3.connect(common_db_path()) as conn:
            org_product_refs_by_data = load_org_product_metric_refs_by_runtime_ref_code_sync(conn)
        return {
            **rule,
            "variables": resolve_org_product_variables(
                variables,
                org_product_refs_by_runtime_ref_code=org_product_refs_by_data,
            ),
        }

    async def _save_rule_payload(*, rule: dict[str, Any], rule_id: int | None = None) -> ExpenseForecastRuleRow:
        await _ensure_tables()
        try:
            rule = _resolve_rule_org_product_variables(rule)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            matched = await save_expense_forecast_rule(
                rule=rule,
                rule_id=rule_id,
                source=_ExpenseForecastRuleSaveSource(),
                now=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        except ExpenseForecastRuleSaveError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return ExpenseForecastRuleRow.model_validate(matched)

    async def _save_rule(body: ExpenseForecastRuleSaveRequest, rule_id: int | None = None) -> ExpenseForecastRuleRow:
        return await _save_rule_payload(rule=body.model_dump(), rule_id=rule_id)

    class _ExpenseForecastRuleCopySource:
        async def load_rule_rows(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str] | None = None,
            subject_id: int | None = None,
        ) -> list[dict[str, Any]]:
            return await _load_rule_rows(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
                subject_id=subject_id,
            )

        async def save_rule(self, *, rule: dict[str, Any], rule_id: int | None):
            return await _save_rule_payload(rule=rule, rule_id=rule_id)

    async def _copy_rules(
        *,
        year: int,
        source_version: str,
        target_version: str,
    ) -> int:
        return await copy_expense_forecast_rules_from_version(
            year=year,
            source_version=_text(source_version),
            target_version=_text(target_version),
            source=_ExpenseForecastRuleCopySource(),
        )

    class _ExpenseForecastRuleImportPreviewSource:
        async def load_subject_lookup(self) -> tuple[dict[int, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
            return await _subject_lookup()

        async def load_org_product_refs_by_runtime_ref_code(self) -> dict[str, tuple[str, ...]]:
            with sqlite3.connect(common_db_path()) as conn:
                return load_org_product_metric_refs_by_runtime_ref_code_sync(conn)

        async def load_rule_rows(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str] | None = None,
            subject_id: int | None = None,
        ) -> list[dict[str, Any]]:
            return await _load_rule_rows(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
                subject_id=subject_id,
            )

    class _ExpenseForecastRuleImportApplySource(_ExpenseForecastRuleImportPreviewSource):
        async def save_rule(self, *, rule: dict[str, Any], rule_id: int | None):
            return await _save_rule_payload(rule=rule, rule_id=rule_id)

    async def _preview_rule_import(*, raw: bytes):
        return await preview_expense_forecast_rule_import_workbook(
            raw=raw,
            default_year=default_year,
            default_version=_default_version(),
            source=_ExpenseForecastRuleImportPreviewSource(),
        )

    async def _apply_rule_import(*, raw: bytes):
        return await apply_expense_forecast_rule_import_workbook(
            raw=raw,
            default_year=default_year,
            default_version=_default_version(),
            source=_ExpenseForecastRuleImportApplySource(),
        )

    def _download_rule_template():
        with sqlite3.connect(common_db_path()) as conn:
            org_product_refs_by_data = load_org_product_metric_refs_by_runtime_ref_code_sync(conn)
        stream = build_expense_forecast_rule_template_workbook(
            default_year=default_year,
            default_version=_default_version(),
            org_product_refs_by_runtime_ref_code=org_product_refs_by_data,
        )
        return excel_streaming_response(
            stream,
            filename="费用预测逻辑配置模板.xlsx",
            fallback_filename="expense-forecast-rule-template.xlsx",
        )

    async def _load_scope_rows() -> list[tuple[str, str, str]]:
        return await load_expense_forecast_scope_rows(common_db_path())

    async def _resolve_scope_owners(scope_type: ScopeType, scope_value: str) -> list[str]:
        rows = await _load_scope_rows()
        try:
            return resolve_expense_forecast_scope_owners(
                rows,
                scope_type=scope_type,
                scope_value=scope_value,
            )
        except ExpenseForecastDataContextError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def _load_budget_subject_rows() -> list[dict[str, Any]]:
        return await load_expense_forecast_budget_subject_rows(common_db_path())

    async def _load_manage_department_map() -> dict[str, str]:
        return await load_expense_forecast_manage_department_map(common_db_path())

    async def _load_product_department_owner_map() -> dict[str, str]:
        return await load_expense_forecast_product_department_owner_map()

    async def _actual_cutoff_month(year: int) -> int:
        return await load_expense_forecast_actual_cutoff_month(
            common_db_path(),
            year=year,
        )

    async def _load_actual_map(year: int, owner_names: list[str]) -> dict[tuple[str, str, int], float]:
        return await load_expense_forecast_actual_map(
            common_db_path(),
            year=year,
            owner_names=owner_names,
        )

    async def _load_forecast_map(
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], float]:
        await _ensure_tables()
        return await load_expense_forecast_forecast_map(
            common_db_path(),
            year=year,
            forecast_version=forecast_version,
            owner_names=owner_names,
        )

    async def _load_annual_input_map(
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, str], float]:
        await _ensure_tables()
        return await load_expense_forecast_annual_input_map(
            common_db_path(),
            year=year,
            forecast_version=forecast_version,
            owner_names=owner_names,
        )

    async def _load_annual_budget_map(year: int, owner_names: list[str]) -> dict[tuple[str, str], float]:
        product_department_owner_map = await _load_product_department_owner_map()
        return await load_expense_forecast_annual_budget_map(
            budget_db_path(year),
            owner_names=owner_names,
            product_department_owner_map=product_department_owner_map,
        )

    class _ExpenseForecastRuleSimulationSource:
        async def load_subject_by_id(self, subject_id: int) -> dict[str, Any] | None:
            by_id, _ = await _subject_lookup()
            return by_id.get(int(subject_id))

        async def load_actual_cutoff_month(self, year: int) -> int:
            return await _actual_cutoff_month(year)

        async def load_actual_map(self, year: int, owner_names: list[str]) -> dict[tuple[str, str, int], float]:
            return await _load_actual_map(year, owner_names)

        async def load_annual_input_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, str], float]:
            return await _load_annual_input_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_forecast_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, int], float]:
            return await _load_forecast_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def calculate_rule_months(self, **kwargs) -> dict[int, dict[str, Any]]:
            return await _calculate_rule_months(**kwargs)

    async def _simulate_rule(*, rule: dict[str, Any]) -> dict[str, Any]:
        try:
            rule = _resolve_rule_org_product_variables(rule)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return await simulate_expense_forecast_rule_definition(
            rule=rule,
            source=_ExpenseForecastRuleSimulationSource(),
        )

    class _ExpenseForecastCellSource:
        async def load_subject_lookup(self) -> tuple[dict[int, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
            return await _subject_lookup()

        async def load_manage_department_map(self) -> dict[str, str]:
            return await _load_manage_department_map()

        async def load_actual_cutoff_month(self, year: int) -> int:
            return await _actual_cutoff_month(year)

        async def load_rule_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int], dict[str, Any]]:
            return await _load_rule_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def recalculate_rules(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_name: str,
            subject_id: int,
        ) -> tuple[int, int]:
            return await _recalculate_rules(
                year=year,
                forecast_version=forecast_version,
                owner_name=owner_name,
                subject_id=subject_id,
                trigger="auto",
            )

        async def write_operation_log(self, **kwargs) -> None:
            await write_operation_log(**kwargs)

    class _ExpenseForecastImportApplySource:
        async def recalculate_rules(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_name: str,
            subject_id: int,
        ) -> tuple[int, int]:
            return await _recalculate_rules(
                year=year,
                forecast_version=forecast_version,
                owner_name=owner_name,
                subject_id=subject_id,
                trigger="auto",
            )

        async def write_operation_log(self, **kwargs) -> None:
            await write_operation_log(**kwargs)

    class _ExpenseForecastImportPreviewSource:
        async def load_subject_lookup(self) -> tuple[dict[int, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
            return await _subject_lookup()

        async def resolve_scope_owners(self, scope_type: str, scope_value: str) -> list[str]:
            return await _resolve_scope_owners(_normalize_scope_type(scope_type), scope_value)

        async def load_actual_cutoff_month(self, year: int) -> int:
            return await _actual_cutoff_month(year)

        async def load_manage_department_map(self) -> dict[str, str]:
            return await _load_manage_department_map()

        async def load_forecast_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, int], float]:
            return await _load_forecast_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_rule_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int], dict[str, Any]]:
            return await _load_rule_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_annual_input_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, str], float]:
            return await _load_annual_input_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_calc_result_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, int], dict[str, Any]]:
            return await _load_calc_result_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

    class _ExpenseForecastViewSource:
        async def load_budget_subject_rows(self) -> list[dict[str, Any]]:
            return await _load_budget_subject_rows()

        async def resolve_scope_owners(self, scope_type: ScopeType, scope_value: str) -> list[str]:
            return await _resolve_scope_owners(scope_type, scope_value)

        async def load_actual_cutoff_month(self, year: int) -> int:
            return await _actual_cutoff_month(year)

        async def load_manage_department_map(self) -> dict[str, str]:
            return await _load_manage_department_map()

        async def load_actual_map(self, year: int, owner_names: list[str]) -> dict[tuple[str, str, int], float]:
            return await _load_actual_map(year, owner_names)

        async def load_annual_budget_map(self, year: int, owner_names: list[str]) -> dict[tuple[str, str], float]:
            return await _load_annual_budget_map(year, owner_names)

        async def load_forecast_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, int], float]:
            return await _load_forecast_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_rule_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int], dict[str, Any]]:
            return await _load_rule_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_calc_result_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, int], dict[str, Any]]:
            return await _load_calc_result_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_override_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, int], dict[str, Any]]:
            return await _load_override_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_annual_input_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, str], float]:
            return await _load_annual_input_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

    class _ExpenseForecastTraceSource:
        async def load_calc_result_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, int], dict[str, Any]]:
            return await _load_calc_result_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_override_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, int], dict[str, Any]]:
            return await _load_override_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_forecast_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, int], float]:
            return await _load_forecast_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_rule_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int], dict[str, Any]]:
            return await _load_rule_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

    class _ExpenseForecastOverrideSource:
        async def load_rule_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int], dict[str, Any]]:
            return await _load_rule_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_calc_result_map(
            self,
            *,
            year: int,
            forecast_version: str,
            owner_names: list[str],
        ) -> dict[tuple[str, int, int], dict[str, Any]]:
            return await _load_calc_result_map(
                year=year,
                forecast_version=forecast_version,
                owner_names=owner_names,
            )

        async def load_actual_cutoff_month(self, year: int) -> int:
            return await _actual_cutoff_month(year)

    async def _build_export_scope_view(
        *,
        year: int,
        forecast_version: str,
        scope_type: str,
        scope_value: str,
    ) -> ExpenseForecastViewResponse:
        return await _build_view(
            year=year,
            forecast_version=forecast_version,
            scope_type=_normalize_scope_type(scope_type),
            scope_value=scope_value,
        )

    class _ExpenseForecastRegularExportSource:
        async def build_scope_view(
            self,
            *,
            year: int,
            forecast_version: str,
            scope_type: str,
            scope_value: str,
        ) -> ExpenseForecastViewResponse:
            return await _build_export_scope_view(
                year=year,
                forecast_version=forecast_version,
                scope_type=scope_type,
                scope_value=scope_value,
            )

        async def build_subject_view(
            self,
            *,
            year: int,
            forecast_version: str,
            scope_type: str,
            scope_value: str,
            subject_id: int,
        ) -> ExpenseForecastSubjectViewResponse:
            return await _build_subject_owner_view(
                year=year,
                forecast_version=forecast_version,
                scope_type=_normalize_scope_type(scope_type),
                scope_value=scope_value,
                subject_id=subject_id,
            )

    class _ExpenseForecastGroupExportSource:
        async def build_scope_view(
            self,
            *,
            year: int,
            forecast_version: str,
            scope_type: str,
            scope_value: str,
        ) -> ExpenseForecastViewResponse:
            return await _build_export_scope_view(
                year=year,
                forecast_version=forecast_version,
                scope_type=scope_type,
                scope_value=scope_value,
            )

        async def load_owner_group_options(self) -> list[ExpenseForecastOwnerGroupOption]:
            return [
                ExpenseForecastOwnerGroupOption.model_validate(item)
                for item in await load_expense_forecast_owner_group_options(common_db_path())
            ]

    async def _build_view(
        *,
        year: int,
        forecast_version: str,
        scope_type: ScopeType,
        scope_value: str,
    ) -> ExpenseForecastViewResponse:
        try:
            view_model = await build_expense_forecast_scope_read_model(
                year=year,
                forecast_version=forecast_version,
                scope_type=scope_type,
                scope_value=scope_value,
                source=_ExpenseForecastViewSource(),
            )
        except ExpenseForecastViewReadModelError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ExpenseForecastViewResponse.model_validate(view_model)

    async def _build_subject_owner_view(
        *,
        year: int,
        forecast_version: str,
        scope_type: ScopeType,
        scope_value: str,
        subject_id: int,
    ) -> ExpenseForecastSubjectViewResponse:
        try:
            view_model = await build_expense_forecast_subject_read_model(
                year=year,
                forecast_version=forecast_version,
                scope_type=scope_type,
                scope_value=scope_value,
                subject_id=int(subject_id),
                source=_ExpenseForecastViewSource(),
            )
        except ExpenseForecastViewReadModelError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ExpenseForecastSubjectViewResponse.model_validate(view_model)

    async def _build_group_owner_view(
        *,
        year: int,
        forecast_version: str,
        group_name: str,
    ) -> ExpenseForecastGroupViewResponse:
        try:
            view_model = await build_expense_forecast_group_read_model(
                year=year,
                forecast_version=forecast_version,
                group_name=group_name,
                source=_ExpenseForecastViewSource(),
            )
        except ExpenseForecastViewReadModelError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ExpenseForecastGroupViewResponse.model_validate(view_model)

    async def _subject_lookup() -> tuple[dict[int, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        rows = await _load_budget_subject_rows()
        return build_expense_forecast_subject_lookup(rows)

    def _normalize_scope_type(raw: str) -> ScopeType:
        value = _text(raw).lower()
        if value not in {"entity", "group", "owner"}:
            raise HTTPException(status_code=400, detail="编制口径仅支持 entity、group、owner")
        return value  # type: ignore[return-value]

    def _normalize_import_mode(raw: str) -> ImportMode:
        value = _text(raw).lower()
        if value not in {"append", "overwrite"}:
            raise HTTPException(status_code=400, detail="导入模式仅支持 append 或 overwrite")
        return value  # type: ignore[return-value]

    async def _preview_import(
        *,
        file_name: str,
        raw: bytes,
        year: int,
        forecast_version: str,
        scope_type: ScopeType,
        scope_value: str,
        import_mode: ImportMode,
        group_name: str = "",
        compile_mode: CompileMode = "scope",
        subject_id: int | None = None,
    ) -> tuple[ExpenseForecastImportPreviewResponse, list[dict[str, Any]]]:
        try:
            preview = await build_expense_forecast_import_preview_from_source(
                file_name=file_name,
                raw=raw,
                year=year,
                forecast_version=forecast_version,
                scope_type=scope_type,
                scope_value=scope_value,
                import_mode=import_mode,
                group_name=group_name,
                compile_mode=compile_mode,
                subject_id=subject_id,
                all_owner_scope_value=ALL_OWNER_SCOPE_VALUE,
                source=_ExpenseForecastImportPreviewSource(),
            )
        except ExpenseForecastImportPreviewWorkflowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        response = ExpenseForecastImportPreviewResponse(
            file_name=preview.file_name,
            import_mode=preview.import_mode,  # type: ignore[arg-type]
            actual_cutoff_month=preview.actual_cutoff_month,
            preview_count=preview.preview_count,
            insertable_cells=preview.insertable_cells,
            updatable_cells=preview.updatable_cells,
            skipped_cells=preview.skipped_cells,
            error_cells=preview.error_cells,
            items=[ExpenseForecastImportPreviewItem(**item) for item in preview.items],
        )
        return response, preview.normalized_rows

    @router.get("/api/expense-forecast/meta", response_model=ExpenseForecastMetaResponse)
    async def get_expense_forecast_meta(year: int = Query(default_year)):
        await _ensure_tables()
        meta = await load_expense_forecast_meta(
            common_db_path(),
            year=year,
            default_version=_default_version(),
        )
        return ExpenseForecastMetaResponse.model_validate(meta)

    @router.get("/api/expense-forecast/view", response_model=ExpenseForecastViewResponse)
    async def get_expense_forecast_view(
        year: int = Query(default_year),
        forecast_version: str = Query(...),
        scope_type: str = Query(...),
        scope_value: str = Query(...),
    ):
        return await _build_view(
            year=year,
            forecast_version=_text(forecast_version) or _default_version(),
            scope_type=_normalize_scope_type(scope_type),
            scope_value=_text(scope_value),
        )

    @router.get("/api/expense-forecast/subject-view", response_model=ExpenseForecastSubjectViewResponse)
    async def get_expense_forecast_subject_view(
        year: int = Query(default_year),
        forecast_version: str = Query(...),
        scope_type: str = Query(...),
        scope_value: str = Query(...),
        subject_id: int = Query(...),
    ):
        return await _build_subject_owner_view(
            year=year,
            forecast_version=_text(forecast_version) or _default_version(),
            scope_type=_normalize_scope_type(scope_type),
            scope_value=_text(scope_value),
            subject_id=int(subject_id),
        )

    @router.get("/api/expense-forecast/group-view", response_model=ExpenseForecastGroupViewResponse)
    async def get_expense_forecast_group_view(
        year: int = Query(default_year),
        forecast_version: str = Query(...),
        group_name: str = Query(...),
    ):
        return await _build_group_owner_view(
            year=year,
            forecast_version=_text(forecast_version) or _default_version(),
            group_name=_text(group_name),
        )

    @router.post("/api/expense-forecast/cell", response_model=ExpenseForecastCellUpsertResponse)
    async def upsert_expense_forecast_cell(body: ExpenseForecastCellUpsertRequest):
        await _ensure_tables()
        try:
            result = await upsert_expense_forecast_cell_with_validation(
                db_path=common_db_path(),
                year=int(body.year),
                forecast_version=_text(body.forecast_version) or _default_version(),
                scope_type=body.scope_type,
                scope_value=_text(body.scope_value),
                subject_id=int(body.subject_id),
                field_name=body.field_name,
                month=body.month,
                value=float(body.value),
                source=_ExpenseForecastCellSource(),
                now=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        except ExpenseForecastCellWorkflowError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        return ExpenseForecastCellUpsertResponse(
            updated=True,
            actual_cutoff_month=result.actual_cutoff_month,
            mode=result.mode,
        )

    @router.post("/api/expense-forecast/import-preview", response_model=ExpenseForecastImportPreviewResponse)
    async def preview_expense_forecast_import(
        year: int = Query(default_year),
        forecast_version: str = Query(...),
        scope_type: str = Query(...),
        scope_value: str = Query(...),
        group_name: str = Query(""),
        compile_mode: str = Query("scope"),
        subject_id: int | None = Query(None),
        mode: str = Query("append"),
        file: UploadFile = File(...),
    ):
        await _ensure_tables()
        raw = await file.read()
        response, _rows = await _preview_import(
            file_name=file.filename or "费用预测导入.xlsx",
            raw=raw,
            year=year,
            forecast_version=_text(forecast_version) or _default_version(),
            scope_type=_normalize_scope_type(scope_type),
            scope_value=_text(scope_value),
            import_mode=_normalize_import_mode(mode),
            group_name=_text(group_name),
            compile_mode=compile_mode,
            subject_id=subject_id,
        )
        return response

    @router.post("/api/expense-forecast/import-apply", response_model=ExpenseForecastImportApplyResponse)
    async def apply_expense_forecast_import(
        year: int = Query(default_year),
        forecast_version: str = Query(...),
        scope_type: str = Query(...),
        scope_value: str = Query(...),
        group_name: str = Query(""),
        compile_mode: str = Query("scope"),
        subject_id: int | None = Query(None),
        mode: str = Query("append"),
        file: UploadFile = File(...),
    ):
        await _ensure_tables()
        normalized_scope_type = _normalize_scope_type(scope_type)
        normalized_mode = _normalize_import_mode(mode)
        normalized_scope_value = _text(scope_value)
        normalized_version = _text(forecast_version) or _default_version()
        raw = await file.read()
        preview, rows = await _preview_import(
            file_name=file.filename or "费用预测导入.xlsx",
            raw=raw,
            year=year,
            forecast_version=normalized_version,
            scope_type=normalized_scope_type,
            scope_value=normalized_scope_value,
            import_mode=normalized_mode,
            group_name=_text(group_name),
            compile_mode=compile_mode,
            subject_id=subject_id,
        )
        apply_result = await apply_expense_forecast_import_rows_with_recalculation(
            db_path=common_db_path(),
            rows=rows,
            year=int(year),
            forecast_version=normalized_version,
            scope_type=normalized_scope_type,
            scope_value=normalized_scope_value,
            group_name=_text(group_name),
            import_mode=normalized_mode,
            skipped_cells=preview.skipped_cells,
            error_cells=preview.error_cells,
            source=_ExpenseForecastImportApplySource(),
            now=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        inserted = apply_result.inserted_cells
        updated = apply_result.updated_cells
        skipped = apply_result.skipped_cells
        errors = apply_result.error_cells

        return ExpenseForecastImportApplyResponse(
            file_name=file.filename or "费用预测导入.xlsx",
            import_mode=normalized_mode,
            actual_cutoff_month=preview.actual_cutoff_month,
            inserted_cells=inserted,
            updated_cells=updated,
            skipped_cells=skipped,
            error_cells=errors,
        )

    @router.post("/api/expense-forecast/export")
    async def export_expense_forecast(body: ExpenseForecastExportRequest):
        try:
            result = await build_expense_forecast_export_from_source(
                year=int(body.year),
                forecast_version=body.forecast_version,
                default_version=_default_version(),
                scope_type=body.scope_type,
                scope_value=body.scope_value,
                compile_mode=body.compile_mode,
                subject_id=body.subject_id,
                amount_unit=body.amount_unit,
                exclude_fields=body.exclude_fields,
                source=_ExpenseForecastRegularExportSource(),
            )
        except ExpenseForecastExportPlanError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return excel_streaming_response(
            result.stream,
            filename=result.display_file_name,
            fallback_filename="expense-forecast.xlsx",
        )

    @router.post("/api/expense-forecast/export-by-group")
    async def export_expense_forecast_by_group(body: ExpenseForecastGroupExportRequest):
        try:
            result = await build_expense_forecast_group_export_from_source(
                year=int(body.year),
                forecast_version=body.forecast_version,
                default_version=_default_version(),
                group_name=body.group_name,
                amount_unit=body.amount_unit,
                exclude_fields=body.exclude_fields,
                source=_ExpenseForecastGroupExportSource(),
            )
        except ExpenseForecastExportPlanError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return excel_streaming_response(
            result.stream,
            filename=result.display_file_name,
            fallback_filename="expense-forecast-group.xlsx",
        )

    register_expense_forecast_rule_routes(
        router,
        default_year=default_year,
        list_rules=_list_rules,
        load_rule_detail=_load_rule_detail,
        save_rule=_save_rule,
        delete_rule=_delete_rule,
        recalculate_rules=_recalculate_rules,
        simulate_rule=_simulate_rule,
        copy_rules=_copy_rules,
        download_rule_template=_download_rule_template,
        preview_rule_import=_preview_rule_import,
        apply_rule_import=_apply_rule_import,
    )

    @router.get("/api/expense-forecast/trace", response_model=ExpenseForecastTraceResponse)
    async def get_expense_forecast_trace(
        year: int = Query(default_year),
        forecast_version: str = Query(...),
        owner_name: str = Query(...),
        subject_id: int = Query(...),
    ):
        normalized_version = _text(forecast_version)
        normalized_owner_name = _text(owner_name)
        trace = await build_expense_forecast_trace_read_model_from_source(
            year=year,
            forecast_version=normalized_version,
            owner_name=normalized_owner_name,
            subject_id=int(subject_id),
            source=_ExpenseForecastTraceSource(),
        )
        return ExpenseForecastTraceResponse(
            forecast_year=year,
            forecast_version=normalized_version,
            owner_name=normalized_owner_name,
            subject_id=int(subject_id),
            rule_id=trace.rule_id,
            rule_scheme=trace.rule_scheme,  # type: ignore[arg-type]
            items=[ExpenseForecastTraceMonthItem(**item.__dict__) for item in trace.items],
        )

    @router.post("/api/expense-forecast/override", response_model=ExpenseForecastCellUpsertResponse)
    async def override_expense_forecast_value(body: ExpenseForecastOverrideRequest):
        try:
            result = await save_expense_forecast_override_with_rule_check(
                db_path=common_db_path(),
                year=int(body.forecast_year),
                forecast_version=_text(body.forecast_version),
                owner_name=_text(body.owner_name),
                subject_id=int(body.subject_id),
                month=int(body.month),
                override_value=float(body.override_value),
                override_reason=body.override_reason,
                source=_ExpenseForecastOverrideSource(),
                now=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        except ExpenseForecastOverrideWorkflowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ExpenseForecastCellUpsertResponse(
            updated=True,
            actual_cutoff_month=result.actual_cutoff_month,
            mode="override",
        )

    @router.delete("/api/expense-forecast/override")
    async def delete_expense_forecast_override(
        year: int = Query(default_year),
        forecast_version: str = Query(...),
        owner_name: str = Query(...),
        subject_id: int = Query(...),
        month: int = Query(...),
    ):
        await delete_expense_forecast_override_with_restore(
            db_path=common_db_path(),
            year=year,
            forecast_version=_text(forecast_version),
            owner_name=_text(owner_name),
            subject_id=int(subject_id),
            month=int(month),
            source=_ExpenseForecastOverrideSource(),
            now=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    return router
