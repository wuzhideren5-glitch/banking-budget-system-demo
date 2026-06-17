from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.services.expense_budget_execution_actuals import (
    ExpenseActualError,
    load_actual_rows,
)
from app.services.expense_budget_execution_budget_source import (
    BudgetSourceError,
    load_imported_caliber_monthly_totals,
    load_imported_owner_caliber_monthly_totals,
    load_budget_rows,
    load_previous_year_actual_by_owner_subject,
    load_previous_year_actual_subject_monthly,
)
from app.services.expense_budget_execution_framework import (
    ExpenseFrameworkError,
    FrameworkContext,
    ParsedFramework,
    load_framework_context,
    matches_template_scope,
)
from app.services.expense_budget_execution_monthly_report import (
    build_monthly_report_sections,
)
from app.services.expense_budget_execution_modes import (
    DISPLAY_REPORT_MODES,
    EXPORT_REPORT_MODES,
    REPORT_PERSPECTIVES,
)
from app.services.expense_budget_execution_query_report import (
    build_query_report_model,
)
from app.services.expense_budget_execution_report_context import (
    ExpenseReportEntityContext,
    ExpenseReportScopeContext,
    build_report_entity_context,
    build_report_scope_context,
)
from app.services.expense_budget_execution_subject_catalog import (
    BudgetSubjectCatalogError,
    load_budget_subject_catalog_rows,
)
from app.services.expense_budget_execution_subject_report import (
    build_subject_report_model,
)
from app.services.expense_budget_execution_template_report import (
    build_template_report_model,
)
from app.services.expense_budget_entry_store import (
    load_expense_budget_entry_subject_totals,
)

EditableContextProvider = Callable[[], Awaitable[tuple[Path, int, int]]]
MISSING_CURRENT_ACTUAL_IMPORT_NOTE = "当前未检测到已导入的费用执行明细，请在“费用执行明细导入”中导入本年实际明细。"


# ─── 异常类与验证 ───

class ExpenseBudgetExecutionReportError(Exception):
    """Raised when the expense execution report cannot be resolved."""


def validate_report_perspective(perspective: str) -> None:
    if perspective not in REPORT_PERSPECTIVES:
        raise ExpenseBudgetExecutionReportError("perspective 仅支持 entity、group 或 owner_dept")


def resolve_subject_filter_id(subject_id: int | None) -> int | None:
    if subject_id is None:
        return None
    try:
        selected_subject_id = int(subject_id)
    except (TypeError, ValueError) as exc:
        raise ExpenseBudgetExecutionReportError("subject_id 仅支持正整数") from exc
    if selected_subject_id <= 0:
        raise ExpenseBudgetExecutionReportError("subject_id 仅支持正整数")
    return selected_subject_id


def validate_report_month_filter(report_month: int | None) -> None:
    if report_month is None:
        return
    try:
        selected_month = int(report_month)
    except (TypeError, ValueError) as exc:
        raise ExpenseBudgetExecutionReportError("report_month 仅支持 1-12") from exc
    if selected_month < 1 or selected_month > 12:
        raise ExpenseBudgetExecutionReportError("report_month 仅支持 1-12")


@dataclass(frozen=True)
# ─── 上下文数据类 ───

class ExpenseBudgetExecutionReportSelection:
    mode: str = "query"
    perspective: str = "group"
    keyword: str = ""
    include_zero_rows: bool = False
    entity_name: str = ""
    group_name: str = ""
    owner_dept: str = ""
    subject_id: int | None = None
    report_month: int | None = None


@dataclass(frozen=True)
class ExpenseBudgetExecutionReportResolutionPlan:
    report_kind: str


@dataclass(frozen=True)
class TemplateActualContext:
    current_subject_monthly_totals: dict[str, list[float]]
    previous_year_subject_monthly_totals: dict[str, list[float]]
    previous_year_subject_totals: dict[str, float]
    current_actual_source_file: str
    previous_actual_source_file: str
    has_imported_previous_actuals: bool
    budget_subject_totals: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ReportRuntimeContext:
    budget_db: Path
    budget_year: int
    version_id: int
    ctx: FrameworkContext
    parsed: ParsedFramework
    framework_source_mode: str
    framework_source_file: str
    actual_by_owner: dict[tuple[str, str], list[float]]
    actual_source_mode: str
    actual_source_file: str
    version_name: str
    current_month: int
    selected_month: int
    budget_by_owner: dict[tuple[str, str], float]
    budget_source: str | None = None


@dataclass(frozen=True)
class ScopedReportContext:
    runtime: ReportRuntimeContext
    scope_context: ExpenseReportScopeContext
    subject_rows: list[dict[str, Any]]
    selected_entity: str
    selected_group: str
    selected_owner: str


@dataclass(frozen=True)
class QueryReportContext:
    runtime: ReportRuntimeContext
    perspective: str
    scoped: ScopedReportContext


@dataclass(frozen=True)
class SubjectReportContext:
    runtime: ReportRuntimeContext
    entity_context: ExpenseReportEntityContext
    subject_rows: list[dict[str, Any]]
    selected_entity: str


@dataclass(frozen=True)
class OwnerPriorActualContext:
    runtime: ReportRuntimeContext
    previous_year_actual_by_owner_subject: dict[tuple[str, str], list[float]]
    previous_actual_source_file: str


@dataclass(frozen=True)
class BusinessOwnerActualContext:
    runtime: ReportRuntimeContext
    current_actual_by_owner_subject: dict[tuple[str, str], list[float]]
    previous_year_actual_by_owner_subject: dict[tuple[str, str], list[float]]
    current_actual_source_file: str
    previous_actual_source_file: str


@dataclass(frozen=True)
class MonthlyReportContext:
    runtime: ReportRuntimeContext
    scoped: ScopedReportContext
    template_actual: TemplateActualContext
    business_owner_actual: BusinessOwnerActualContext
    owner_prior_actual: OwnerPriorActualContext


@dataclass(frozen=True)
class TemplateReportContext:
    runtime: ReportRuntimeContext
    scoped: ScopedReportContext
    template_actual: TemplateActualContext


@dataclass(frozen=True)
class SubjectModeReportContext:
    runtime: ReportRuntimeContext
    subject: SubjectReportContext
    owner_prior_actual: OwnerPriorActualContext


# ─── 数据加载函数 ───

async def _load_framework_context() -> tuple[FrameworkContext, str, str, ParsedFramework]:
    try:
        return await load_framework_context()
    except ExpenseFrameworkError as exc:
        raise ExpenseBudgetExecutionReportError(str(exc)) from exc


async def _load_actual_rows(
    ctx: FrameworkContext,
) -> tuple[
    dict[tuple[str, str], list[float]],
    dict[tuple[str, str], list[float]],
    dict[tuple[str, str], list[float]],
    str,
    str,
]:
    try:
        loaded = await load_actual_rows(ctx)
    except ExpenseActualError as exc:
        raise ExpenseBudgetExecutionReportError(str(exc)) from exc
    return (
        loaded.actual_by_entity,
        loaded.actual_by_group,
        loaded.actual_by_owner,
        loaded.source_mode,
        loaded.source_description,
    )


async def _load_budget_rows(
    ctx: FrameworkContext,
    budget_db: Path,
    version_id: int,
) -> tuple[
    str,
    int,
    dict[tuple[str, str], float],
    dict[tuple[str, str], float],
    dict[tuple[str, str], float],
    str | None,
]:
    try:
        return await load_budget_rows(ctx, budget_db, version_id)
    except BudgetSourceError as exc:
        raise ExpenseBudgetExecutionReportError(str(exc)) from exc


async def _load_budget_subject_catalog_rows() -> list[dict[str, Any]]:
    try:
        return await load_budget_subject_catalog_rows()
    except BudgetSubjectCatalogError as exc:
        raise ExpenseBudgetExecutionReportError(str(exc)) from exc


# ─── 报表解析与聚合 ───

def _resolve_selected_month(report_month: int | None, current_month: int) -> int:
    selected_month = int(report_month or current_month)
    if selected_month < 1 or selected_month > 12:
        raise ExpenseBudgetExecutionReportError("report_month 仅支持 1-12")
    return selected_month


async def load_report_runtime_context(
    *,
    editable_context_provider: EditableContextProvider,
    report_month: int | None = None,
) -> ReportRuntimeContext:
    validate_report_month_filter(report_month)
    budget_db, budget_year, version_id = await editable_context_provider()
    ctx, framework_source_mode, framework_source_file, parsed = await _load_framework_context()
    (
        _actual_by_entity,
        _actual_by_group,
        actual_by_owner,
        actual_source_mode,
        actual_source_file,
    ) = await _load_actual_rows(ctx)
    loaded_budget_rows = await _load_budget_rows(ctx, budget_db, version_id)
    (
        version_name,
        current_month,
        _budget_by_entity,
        _budget_by_group,
        budget_by_owner,
        *budget_source_parts,
    ) = loaded_budget_rows
    budget_source = budget_source_parts[0] if budget_source_parts else None
    return ReportRuntimeContext(
        budget_db=budget_db,
        budget_year=budget_year,
        version_id=version_id,
        ctx=ctx,
        parsed=parsed,
        framework_source_mode=framework_source_mode,
        framework_source_file=framework_source_file,
        actual_by_owner=actual_by_owner,
        actual_source_mode=actual_source_mode,
        actual_source_file=actual_source_file,
        version_name=version_name,
        current_month=current_month,
        selected_month=_resolve_selected_month(report_month, current_month),
        budget_by_owner=budget_by_owner,
        budget_source=budget_source,
    )


async def load_scoped_report_context(
    *,
    runtime: ReportRuntimeContext,
    entity_name: str = "",
    group_name: str = "",
    owner_dept: str = "",
) -> ScopedReportContext:
    scope_context = build_report_scope_context(
        runtime.ctx,
        runtime.parsed,
        entity_name=entity_name,
        group_name=group_name,
        owner_dept=owner_dept,
    )
    subject_rows = await _load_budget_subject_catalog_rows()
    return ScopedReportContext(
        runtime=runtime,
        scope_context=scope_context,
        subject_rows=subject_rows,
        selected_entity=scope_context.selected_entity,
        selected_group=scope_context.selected_group,
        selected_owner=scope_context.selected_owner,
    )


async def load_subject_report_context(
    *,
    runtime: ReportRuntimeContext,
    entity_name: str = "",
) -> SubjectReportContext:
    entity_context = build_report_entity_context(runtime.ctx, entity_name=entity_name)
    subject_rows = await _load_budget_subject_catalog_rows()
    return SubjectReportContext(
        runtime=runtime,
        entity_context=entity_context,
        subject_rows=subject_rows,
        selected_entity=entity_context.selected_entity,
    )


async def load_query_report_context(
    *,
    runtime: ReportRuntimeContext,
    perspective: str,
    entity_name: str = "",
    group_name: str = "",
    owner_dept: str = "",
) -> QueryReportContext:
    validate_report_perspective(perspective)
    scoped = await load_scoped_report_context(
        runtime=runtime,
        entity_name=entity_name,
        group_name=group_name,
        owner_dept=owner_dept,
    )
    return QueryReportContext(
        runtime=runtime,
        perspective=perspective,
        scoped=scoped,
    )


async def load_owner_prior_actual_context(
    *,
    runtime: ReportRuntimeContext,
) -> OwnerPriorActualContext:
    previous_year_actual_by_owner_subject, previous_actual_source_file = await load_previous_year_actual_by_owner_subject(
        runtime.ctx,
        runtime.budget_db,
        runtime.budget_year,
    )
    return OwnerPriorActualContext(
        runtime=runtime,
        previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
        previous_actual_source_file=previous_actual_source_file,
    )


async def load_business_owner_actual_context(
    *,
    runtime: ReportRuntimeContext,
) -> BusinessOwnerActualContext:
    current_actual_by_owner_subject, current_actual_source_file = await load_imported_owner_caliber_monthly_totals(
        runtime.ctx,
        "current_year_actual",
    )
    previous_year_actual_by_owner_subject, previous_actual_source_file = await load_imported_owner_caliber_monthly_totals(
        runtime.ctx,
        "prior_year_actual",
    )
    return BusinessOwnerActualContext(
        runtime=runtime,
        current_actual_by_owner_subject=current_actual_by_owner_subject,
        previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
        current_actual_source_file=current_actual_source_file,
        previous_actual_source_file=previous_actual_source_file,
    )


async def load_monthly_report_context(
    *,
    runtime: ReportRuntimeContext,
    entity_name: str = "",
    group_name: str = "",
    owner_dept: str = "",
) -> MonthlyReportContext:
    scoped = await load_scoped_report_context(
        runtime=runtime,
        entity_name=entity_name,
        group_name=group_name,
        owner_dept=owner_dept,
    )
    template_actual = await load_scoped_template_actual_context(
        runtime=runtime,
        scoped=scoped,
    )
    business_owner_actual = await load_business_owner_actual_context(runtime=runtime)
    owner_prior_actual = await load_owner_prior_actual_context(runtime=runtime)
    return MonthlyReportContext(
        runtime=runtime,
        scoped=scoped,
        template_actual=template_actual,
        business_owner_actual=business_owner_actual,
        owner_prior_actual=owner_prior_actual,
    )


async def load_template_report_context(
    *,
    runtime: ReportRuntimeContext,
    entity_name: str = "",
    group_name: str = "",
    owner_dept: str = "",
) -> TemplateReportContext:
    scoped = await load_scoped_report_context(
        runtime=runtime,
        entity_name=entity_name,
        group_name=group_name,
        owner_dept=owner_dept,
    )
    template_actual = await load_scoped_template_actual_context(
        runtime=runtime,
        scoped=scoped,
    )
    return TemplateReportContext(
        runtime=runtime,
        scoped=scoped,
        template_actual=template_actual,
    )


async def load_subject_mode_report_context(
    *,
    runtime: ReportRuntimeContext,
    entity_name: str = "",
) -> SubjectModeReportContext:
    subject = await load_subject_report_context(
        runtime=runtime,
        entity_name=entity_name,
    )
    owner_prior_actual = await load_owner_prior_actual_context(runtime=runtime)
    return SubjectModeReportContext(
        runtime=runtime,
        subject=subject,
        owner_prior_actual=owner_prior_actual,
    )


def build_report_response_payload(
    *,
    mode: str,
    budget_year: int,
    version_id: int,
    version_name: str,
    current_month: int,
    framework_source_mode: str,
    actual_source_mode: str,
    framework_source_file: str,
    actual_source_file: str,
    note_parts: list[str],
    previous_actual_source_file: str | None = None,
    context_fields: dict[str, Any] | None = None,
    body_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": mode,
        "budget_year": budget_year,
        "version_id": version_id,
        "version_name": version_name,
        "current_month": current_month,
        "framework_source_mode": framework_source_mode,
        "actual_source_mode": actual_source_mode,
        "framework_source_file": framework_source_file,
        "actual_source_file": actual_source_file,
    }
    if previous_actual_source_file is not None:
        payload["previous_actual_source_file"] = previous_actual_source_file
    payload.update(context_fields or {})
    payload.update(body_fields or {})
    payload["note"] = " ".join(note_parts)
    return payload


def build_runtime_report_response_payload(
    *,
    runtime: ReportRuntimeContext,
    mode: str,
    current_month: int | None = None,
    actual_source_file: str | None = None,
    previous_actual_source_file: str | None = None,
    note_parts: list[str],
    context_fields: dict[str, Any] | None = None,
    body_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged_note_parts = [*note_parts]
    merged_note_parts.extend(_budget_source_note_parts(runtime.budget_source))
    return build_report_response_payload(
        mode=mode,
        budget_year=runtime.budget_year,
        version_id=runtime.version_id,
        version_name=runtime.version_name,
        current_month=current_month if current_month is not None else runtime.current_month,
        framework_source_mode=runtime.framework_source_mode,
        actual_source_mode=runtime.actual_source_mode,
        framework_source_file=runtime.framework_source_file,
        actual_source_file=actual_source_file or runtime.actual_source_file,
        previous_actual_source_file=previous_actual_source_file,
        note_parts=merged_note_parts,
        context_fields=context_fields,
        body_fields=body_fields,
    )


def _budget_source_note_parts(budget_source: str | None) -> list[str]:
    if budget_source:
        return [
            f"本年预算取自{budget_source}；"
            "主表费用归属部门匹配预算录入部门，主表预算科目匹配预算录入科目，"
            "仅纳入部门与科目均已匹配的数据，金额取预算调整后金额（内部单位：元）。"
        ]
    return []


def build_report_note_parts(
    *,
    base_parts: list[str],
    actual_source_mode: str,
    scope_parts: list[str] | None = None,
) -> list[str]:
    note_parts = [*base_parts]
    note_parts.extend(scope_parts or [])
    if actual_source_mode == "source":
        note_parts.append(MISSING_CURRENT_ACTUAL_IMPORT_NOTE)
    return note_parts


def build_query_note_parts(
    *,
    scoped: ScopedReportContext,
    actual_source_mode: str,
) -> list[str]:
    return build_report_note_parts(
        base_parts=[
            "当前版本支持按“主体”“事业群”“费用归属部门”三种维度查询；预算部门维度已从报表中移除。"
        ],
        scope_parts=scoped.scope_context.selected_scope_note_parts(include_permission_note=True),
        actual_source_mode=actual_source_mode,
    )


def build_monthly_note_parts(
    *,
    scoped: ScopedReportContext,
    actual_source_mode: str,
) -> list[str]:
    return build_report_note_parts(
        base_parts=[
            "月报格式按费用报表执行模版拆分为多个区块展示，第一部分沿用部门模式的预算科目树。",
            "第二至第五部分按当前筛选范围内数据展示，并默认隐藏全零行。",
        ],
        scope_parts=scoped.scope_context.selected_scope_note_parts(),
        actual_source_mode=actual_source_mode,
    )


def build_template_note_parts(
    *,
    scoped: ScopedReportContext,
    actual_source_mode: str,
) -> list[str]:
    return build_report_note_parts(
        base_parts=[
            "部门模式按“部门预算科目”层级展示费用类型，支持逐层展开、收起和右键操作。",
            "本年实际取1月至当前月累计实际，本年预算取年度预算总额，去年同期取上一年度同月累计实际。",
        ],
        scope_parts=scoped.scope_context.selected_scope_note_parts(),
        actual_source_mode=actual_source_mode,
    )


def build_subject_note_parts(*, actual_source_mode: str) -> list[str]:
    return build_report_note_parts(
        base_parts=[
            "科目模式按表头选定的预算科目，在“部门科目维护树”上展示主体、事业群、费用归属部门的费用分布。",
            "本年实际取1月至当前月累计实际，本年预算取年度预算总额，去年同期取上一年度同月累计实际。",
            "选中父级预算科目时，会自动汇总该科目及全部下级科目金额；科目模式默认不按归口权限隐藏部门节点。",
        ],
        actual_source_mode=actual_source_mode,
    )


def build_report_title(
    *,
    title_kind: str,
    budget_year: int,
    selected_month: int,
) -> str:
    if title_kind in {"template", "monthly"}:
        return f"{budget_year}年{selected_month}月费用统计表"
    if title_kind == "subject":
        return f"{budget_year}年{selected_month}月预算科目报表"
    raise ExpenseBudgetExecutionReportError("未知报表标题类型")


def build_template_subject_tree_report(
    *,
    runtime: ReportRuntimeContext,
    scoped: ScopedReportContext,
    template_actual: TemplateActualContext,
    include_zero_rows: bool,
    keyword: str,
):
    return build_template_report_model(
        ctx=runtime.ctx,
        subject_rows=scoped.subject_rows,
        actual_by_owner=runtime.actual_by_owner,
        budget_by_owner=runtime.budget_by_owner,
        previous_year_subject_monthly_totals=template_actual.previous_year_subject_monthly_totals,
        previous_year_subject_totals=template_actual.previous_year_subject_totals,
        current_month=runtime.selected_month,
        current_subject_monthly_totals_override=template_actual.current_subject_monthly_totals,
        budget_subject_totals_override=template_actual.budget_subject_totals,
        selected_entity=scoped.selected_entity,
        selected_group=scoped.selected_group,
        selected_owner=scoped.selected_owner,
        include_zero_rows=include_zero_rows,
        keyword=keyword,
    )


def build_monthly_sections_report(
    *,
    runtime: ReportRuntimeContext,
    scoped: ScopedReportContext,
    business_owner_actual: BusinessOwnerActualContext,
    owner_prior_actual: OwnerPriorActualContext,
):
    return build_monthly_report_sections(
        ctx=runtime.ctx,
        parsed=runtime.parsed,
        subject_rows=scoped.subject_rows,
        actual_by_owner=runtime.actual_by_owner,
        budget_by_owner=runtime.budget_by_owner,
        previous_year_actual_by_owner_subject=owner_prior_actual.previous_year_actual_by_owner_subject,
        business_actual_by_owner=business_owner_actual.current_actual_by_owner_subject,
        business_previous_year_actual_by_owner_subject=business_owner_actual.previous_year_actual_by_owner_subject,
        current_month=runtime.selected_month,
        selected_entity=scoped.selected_entity,
        selected_group=scoped.selected_group,
        selected_owner=scoped.selected_owner,
    )


def build_query_rows_report(
    *,
    runtime: ReportRuntimeContext,
    scoped: ScopedReportContext,
    perspective: str,
    include_zero_rows: bool,
    keyword: str,
):
    return build_query_report_model(
        ctx=runtime.ctx,
        subject_rows=scoped.subject_rows,
        actual_by_owner=runtime.actual_by_owner,
        budget_by_owner=runtime.budget_by_owner,
        perspective=perspective,
        selected_entity=scoped.selected_entity,
        selected_group=scoped.selected_group,
        selected_owner=scoped.selected_owner,
        keyword=keyword,
        include_zero_rows=include_zero_rows,
        current_month=runtime.current_month,
    )


def build_subject_scope_report(
    *,
    runtime: ReportRuntimeContext,
    subject_context: SubjectReportContext,
    owner_prior_actual: OwnerPriorActualContext,
    selected_subject_id: int | None,
    include_zero_rows: bool,
    keyword: str,
):
    return build_subject_report_model(
        ctx=runtime.ctx,
        parsed=runtime.parsed,
        subject_rows=subject_context.subject_rows,
        actual_by_owner=runtime.actual_by_owner,
        budget_by_owner=runtime.budget_by_owner,
        previous_year_actual_by_owner_subject=owner_prior_actual.previous_year_actual_by_owner_subject,
        current_month=runtime.selected_month,
        selected_entity=subject_context.selected_entity,
        selected_subject_id=selected_subject_id,
        include_zero_rows=include_zero_rows,
        keyword=keyword,
    )


def resolve_monthly_previous_actual_source_file(
    *,
    template_actual: TemplateActualContext,
    owner_prior_actual: OwnerPriorActualContext,
) -> str:
    if template_actual.has_imported_previous_actuals:
        return template_actual.previous_actual_source_file
    return owner_prior_actual.previous_actual_source_file


def build_monthly_body_fields(
    *,
    runtime: ReportRuntimeContext,
    template_report,
    monthly_sections,
) -> dict[str, Any]:
    consistency_warnings = build_monthly_report_consistency_warnings(
        template_report=template_report,
        monthly_sections=monthly_sections,
    )
    return {
        "template_title": build_report_title(
            title_kind="monthly",
            budget_year=runtime.budget_year,
            selected_month=runtime.selected_month,
        ),
        "subject_tree": template_report.subject_tree,
        "monthly_business_rows": monthly_sections.business_rows,
        "monthly_it_rows": monthly_sections.it_rows,
        "monthly_daily_managed_blocks": monthly_sections.managed_blocks,
        "monthly_daily_other_columns": monthly_sections.daily_other_columns,
        "monthly_daily_other_rows": monthly_sections.daily_other_rows,
        "consistency_warnings": consistency_warnings,
    }


CONSISTENCY_FIELD_LABELS = {
    "current_actual": "本年实际",
    "annual_budget": "本年预算",
    "budget_progress": "预算进度%",
    "yoy_change": "同比",
    "yoy_rate": "同比%",
    "month_over_month": "环比",
    "month_over_month_rate": "环比%",
    "last_year_actual": "去年同期",
}


def _canonical_consistency_metric_name(metric_name: str) -> str:
    normalized = str(metric_name or "").strip()
    if normalized in {"费用小计", "其他"}:
        return ""
    if normalized in {"业务费用合计", "业务费用小计"}:
        return "业务费用"
    if normalized in {"IT费用合计", "IT费用小计"}:
        return "IT费用"
    return normalized


def _numeric_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _collect_metric_values(
    *,
    collected: dict[tuple[str, str, str], list[tuple[int, float | None]]],
    report_name: str,
    metric_name: str,
    level: int,
    row: dict[str, Any],
) -> None:
    normalized_metric_name = _canonical_consistency_metric_name(metric_name)
    if not normalized_metric_name:
        return
    for field in CONSISTENCY_FIELD_LABELS:
        if field not in row:
            continue
        collected[(report_name, normalized_metric_name, field)].append(
            (int(level or 0), _numeric_or_none(row.get(field)))
        )


def _collect_tree_metric_values(
    *,
    collected: dict[tuple[str, str, str], list[tuple[int, float | None]]],
    report_name: str,
    nodes: list[dict[str, Any]],
) -> None:
    for node in nodes:
        _collect_metric_values(
            collected=collected,
            report_name=report_name,
            metric_name=str(node.get("subject_name") or ""),
            level=int(node.get("level_number") or 0),
            row=node,
        )
        _collect_tree_metric_values(
            collected=collected,
            report_name=report_name,
            nodes=list(node.get("children") or []),
        )


def _collapse_report_metric_values(
    collected: dict[tuple[str, str, str], list[tuple[int, float | None]]],
) -> dict[tuple[str, str, str], float | None]:
    collapsed: dict[tuple[str, str, str], float | None] = {}
    for key, values in collected.items():
        if not values:
            continue
        min_level = min(level for level, _value in values)
        candidates = [value for level, value in values if level == min_level]
        non_null = [float(value) for value in candidates if value is not None]
        collapsed[key] = round(sum(non_null), 6) if non_null else None
    return collapsed


def build_monthly_report_consistency_warnings(
    *,
    template_report,
    monthly_sections,
) -> list[dict[str, Any]]:
    collected: dict[tuple[str, str, str], list[tuple[int, float | None]]] = defaultdict(list)
    _collect_tree_metric_values(
        collected=collected,
        report_name="费用统计表",
        nodes=list(getattr(template_report, "subject_tree", []) or []),
    )
    for row in list(getattr(monthly_sections, "business_rows", []) or []):
        _collect_metric_values(
            collected=collected,
            report_name="业务费用表",
            metric_name=str(row.get("subject_name") or ""),
            level=int(row.get("level") or 0),
            row=row,
        )
    for row in list(getattr(monthly_sections, "it_rows", []) or []):
        _collect_metric_values(
            collected=collected,
            report_name="IT费用表",
            metric_name=str(row.get("subject_name") or ""),
            level=int(row.get("level") or 0),
            row=row,
        )
    for block in list(getattr(monthly_sections, "managed_blocks", []) or []):
        for row in list(block.get("rows", []) or []):
            _collect_metric_values(
                collected=collected,
                report_name="日常费用表",
                metric_name=str(row.get("subject_name") or ""),
                level=int(row.get("level") or 0),
                row=row,
            )
    for row in list(getattr(monthly_sections, "daily_other_rows", []) or []):
        row_level = int(row.get("level") or 0)
        for column in list(getattr(monthly_sections, "daily_other_columns", []) or []):
            matrix_metric_row = {
                "current_actual": (row.get("actuals") or {}).get(column),
                "annual_budget": (row.get("budgets") or {}).get(column),
                "budget_progress": (row.get("progresses") or {}).get(column),
            }
            _collect_metric_values(
                collected=collected,
                report_name="日常费用表",
                metric_name=str(column),
                level=row_level,
                row=matrix_metric_row,
            )

    collapsed = _collapse_report_metric_values(collected)
    by_metric_field: dict[tuple[str, str], list[tuple[str, float | None]]] = defaultdict(list)
    for (report_name, metric_name, field), value in collapsed.items():
        by_metric_field[(metric_name, field)].append((report_name, value))

    warnings: list[dict[str, Any]] = []
    for (metric_name, field), report_values in sorted(by_metric_field.items()):
        unique_reports = {report_name for report_name, _value in report_values}
        if len(unique_reports) < 2:
            continue
        comparable = [
            (report_name, value)
            for report_name, value in sorted(report_values)
            if value is not None
        ]
        if len(comparable) < 2:
            continue
        values = [float(value) for _report_name, value in comparable]
        min_value = min(values)
        max_value = max(values)
        tolerance = 0.000001 if field.endswith("_rate") or field == "budget_progress" else 0.01
        if abs(max_value - min_value) <= tolerance:
            continue
        warnings.append(
            {
                "metric_name": metric_name,
                "field": field,
                "field_label": CONSISTENCY_FIELD_LABELS[field],
                "reports": [report_name for report_name, _value in comparable],
                "values": [
                    {"report": report_name, "value": value}
                    for report_name, value in comparable
                ],
                "difference": round(max_value - min_value, 6),
                "message": (
                    f"{metric_name} 的 {CONSISTENCY_FIELD_LABELS[field]} 在 "
                    f"{'、'.join(report_name for report_name, _value in comparable)} 不一致，"
                    f"最大差异 {round(max_value - min_value, 6)}。"
                ),
            }
        )
    return warnings


def build_template_body_fields(
    *,
    runtime: ReportRuntimeContext,
    template_report,
) -> dict[str, Any]:
    return {
        "template_title": build_report_title(
            title_kind="template",
            budget_year=runtime.budget_year,
            selected_month=runtime.selected_month,
        ),
        "subject_tree": template_report.subject_tree,
    }


def build_subject_body_fields(
    *,
    runtime: ReportRuntimeContext,
    subject_report,
) -> dict[str, Any]:
    return {
        "selected_subject_id": subject_report.selected_subject_id,
        "subject_scope_tree": subject_report.subject_scope_tree,
        "subject_title": build_report_title(
            title_kind="subject",
            budget_year=runtime.budget_year,
            selected_month=runtime.selected_month,
        ),
        "subject_tree": subject_report.subject_tree,
    }


def build_query_body_fields(
    *,
    perspective: str,
    query_report,
) -> dict[str, Any]:
    return {
        "perspective": perspective,
        "rows": query_report.rows,
    }


def build_query_response_payload(
    *,
    runtime: ReportRuntimeContext,
    scoped: ScopedReportContext,
    perspective: str,
    query_report,
) -> dict[str, Any]:
    note_parts = build_query_note_parts(
        scoped=scoped,
        actual_source_mode=runtime.actual_source_mode,
    )
    return build_runtime_report_response_payload(
        runtime=runtime,
        mode="query",
        note_parts=note_parts,
        context_fields=scoped.scope_context.payload_fields(),
        body_fields=build_query_body_fields(
            perspective=perspective,
            query_report=query_report,
        ),
    )


def build_query_report_payload(
    *,
    query_context: QueryReportContext,
    include_zero_rows: bool,
    keyword: str,
) -> dict[str, Any]:
    runtime = query_context.runtime
    scoped = query_context.scoped
    query_report = build_query_rows_report(
        runtime=runtime,
        scoped=scoped,
        perspective=query_context.perspective,
        include_zero_rows=include_zero_rows,
        keyword=keyword,
    )
    return build_query_response_payload(
        runtime=runtime,
        scoped=scoped,
        perspective=query_context.perspective,
        query_report=query_report,
    )


def build_monthly_response_payload(
    *,
    runtime: ReportRuntimeContext,
    scoped: ScopedReportContext,
    template_actual: TemplateActualContext,
    owner_prior_actual: OwnerPriorActualContext,
    template_report,
    monthly_sections,
) -> dict[str, Any]:
    note_parts = build_monthly_note_parts(
        scoped=scoped,
        actual_source_mode=runtime.actual_source_mode,
    )
    previous_actual_source_file = resolve_monthly_previous_actual_source_file(
        template_actual=template_actual,
        owner_prior_actual=owner_prior_actual,
    )
    return build_runtime_report_response_payload(
        runtime=runtime,
        mode="query",
        current_month=runtime.selected_month,
        actual_source_file=template_actual.current_actual_source_file,
        previous_actual_source_file=previous_actual_source_file,
        note_parts=note_parts,
        context_fields=scoped.scope_context.payload_fields(),
        body_fields=build_monthly_body_fields(
            runtime=runtime,
            template_report=template_report,
            monthly_sections=monthly_sections,
        ),
    )


def build_monthly_report_payload(
    *,
    monthly_context: MonthlyReportContext,
) -> dict[str, Any]:
    runtime = monthly_context.runtime
    scoped = monthly_context.scoped
    template_actual = monthly_context.template_actual
    business_owner_actual = monthly_context.business_owner_actual
    owner_prior_actual = monthly_context.owner_prior_actual
    template_report = build_template_subject_tree_report(
        runtime=runtime,
        scoped=scoped,
        template_actual=template_actual,
        include_zero_rows=False,
        keyword="",
    )
    monthly_sections = build_monthly_sections_report(
        runtime=runtime,
        scoped=scoped,
        business_owner_actual=business_owner_actual,
        owner_prior_actual=owner_prior_actual,
    )
    return build_monthly_response_payload(
        runtime=runtime,
        scoped=scoped,
        template_actual=template_actual,
        owner_prior_actual=owner_prior_actual,
        template_report=template_report,
        monthly_sections=monthly_sections,
    )


def build_template_response_payload(
    *,
    runtime: ReportRuntimeContext,
    scoped: ScopedReportContext,
    template_actual: TemplateActualContext,
    template_report,
) -> dict[str, Any]:
    note_parts = build_template_note_parts(
        scoped=scoped,
        actual_source_mode=runtime.actual_source_mode,
    )
    return build_runtime_report_response_payload(
        runtime=runtime,
        mode="template",
        current_month=runtime.selected_month,
        actual_source_file=template_actual.current_actual_source_file,
        previous_actual_source_file=template_actual.previous_actual_source_file,
        note_parts=note_parts,
        context_fields=scoped.scope_context.payload_fields(),
        body_fields=build_template_body_fields(
            runtime=runtime,
            template_report=template_report,
        ),
    )


def build_template_report_payload(
    *,
    template_context: TemplateReportContext,
    include_zero_rows: bool,
    keyword: str,
) -> dict[str, Any]:
    runtime = template_context.runtime
    scoped = template_context.scoped
    template_actual = template_context.template_actual
    template_report = build_template_subject_tree_report(
        runtime=runtime,
        scoped=scoped,
        template_actual=template_actual,
        include_zero_rows=include_zero_rows,
        keyword=keyword,
    )
    return build_template_response_payload(
        runtime=runtime,
        scoped=scoped,
        template_actual=template_actual,
        template_report=template_report,
    )


def build_subject_response_payload(
    *,
    runtime: ReportRuntimeContext,
    subject_context: SubjectReportContext,
    owner_prior_actual: OwnerPriorActualContext,
    subject_report,
) -> dict[str, Any]:
    note_parts = build_subject_note_parts(
        actual_source_mode=runtime.actual_source_mode,
    )
    return build_runtime_report_response_payload(
        runtime=runtime,
        mode="subject",
        current_month=runtime.selected_month,
        previous_actual_source_file=owner_prior_actual.previous_actual_source_file,
        note_parts=note_parts,
        context_fields=subject_context.entity_context.payload_fields(),
        body_fields=build_subject_body_fields(
            runtime=runtime,
            subject_report=subject_report,
        ),
    )


def build_subject_report_payload(
    *,
    subject_mode_context: SubjectModeReportContext,
    selected_subject_id: int | None,
    include_zero_rows: bool,
    keyword: str,
) -> dict[str, Any]:
    runtime = subject_mode_context.runtime
    subject_context = subject_mode_context.subject
    owner_prior_actual = subject_mode_context.owner_prior_actual
    subject_report = build_subject_scope_report(
        runtime=runtime,
        subject_context=subject_context,
        owner_prior_actual=owner_prior_actual,
        selected_subject_id=selected_subject_id,
        include_zero_rows=include_zero_rows,
        keyword=keyword,
    )
    return build_subject_response_payload(
        runtime=runtime,
        subject_context=subject_context,
        owner_prior_actual=owner_prior_actual,
        subject_report=subject_report,
    )


async def load_template_actual_context(
    *,
    ctx: FrameworkContext,
    budget_db: Path,
    budget_year: int,
    selected_month: int,
    selected_entity: str = "",
    selected_group: str = "",
    selected_owner: str = "",
    actual_source_file: str = "",
) -> TemplateActualContext:
    has_scope_filter = bool(selected_entity or selected_group or selected_owner)
    if has_scope_filter:
        current_owner_totals, current_caliber_source_file = await load_imported_owner_caliber_monthly_totals(
            ctx,
            "current_year_actual",
        )
        prior_owner_totals, prior_caliber_source_file = await load_imported_owner_caliber_monthly_totals(
            ctx,
            "prior_year_actual",
        )
        current_caliber_monthly_totals: dict[str, list[float]] = {}
        prior_caliber_monthly_totals: dict[str, list[float]] = {}
        for (owner_name, budget_subject), values in current_owner_totals.items():
            if not matches_template_scope(
                ctx=ctx,
                owner_name=owner_name,
                selected_entity=selected_entity,
                selected_group=selected_group,
                selected_owner=selected_owner,
            ):
                continue
            subject_values = current_caliber_monthly_totals.setdefault(budget_subject, [0.0] * 12)
            for idx, value in enumerate(values[:12]):
                subject_values[idx] = round(subject_values[idx] + float(value or 0.0), 2)
        for (owner_name, budget_subject), values in prior_owner_totals.items():
            if not matches_template_scope(
                ctx=ctx,
                owner_name=owner_name,
                selected_entity=selected_entity,
                selected_group=selected_group,
                selected_owner=selected_owner,
            ):
                continue
            subject_values = prior_caliber_monthly_totals.setdefault(budget_subject, [0.0] * 12)
            for idx, value in enumerate(values[:12]):
                subject_values[idx] = round(subject_values[idx] + float(value or 0.0), 2)
    else:
        current_caliber_monthly_totals, current_caliber_source_file = await load_imported_caliber_monthly_totals(
            "current_year_actual"
        )
        prior_caliber_monthly_totals, prior_caliber_source_file = await load_imported_caliber_monthly_totals(
            "prior_year_actual"
        )
    budget_subject_totals: dict[str, float] = {}
    if not has_scope_filter:
        budget_subject_totals, _budget_subject_source = await load_expense_budget_entry_subject_totals(
            ctx,
            budget_year=budget_year,
        )
    (
        fallback_previous_monthly_totals,
        fallback_previous_totals,
        fallback_previous_source_file,
    ) = await load_previous_year_actual_subject_monthly(
        ctx,
        budget_db,
        budget_year,
        selected_month,
        selected_entity,
        selected_group,
        selected_owner,
    )
    current_subject_monthly_totals = {
        key: [round(float(value or 0.0), 2) for value in values]
        for key, values in current_caliber_monthly_totals.items()
    }
    previous_year_subject_monthly_totals = (
        prior_caliber_monthly_totals
        if prior_caliber_monthly_totals
        else fallback_previous_monthly_totals
    )
    previous_year_subject_totals = (
        {
            key: round(sum(values[:selected_month]), 2)
            for key, values in previous_year_subject_monthly_totals.items()
        }
        if prior_caliber_monthly_totals
        else fallback_previous_totals
    )
    return TemplateActualContext(
        current_subject_monthly_totals=current_subject_monthly_totals,
        budget_subject_totals=budget_subject_totals,
        previous_year_subject_monthly_totals=previous_year_subject_monthly_totals,
        previous_year_subject_totals=previous_year_subject_totals,
        current_actual_source_file=current_caliber_source_file or actual_source_file,
        previous_actual_source_file=prior_caliber_source_file or fallback_previous_source_file,
        has_imported_previous_actuals=bool(prior_caliber_monthly_totals),
    )


async def load_scoped_template_actual_context(
    *,
    runtime: ReportRuntimeContext,
    scoped: ScopedReportContext,
) -> TemplateActualContext:
    return await load_template_actual_context(
        ctx=runtime.ctx,
        budget_db=runtime.budget_db,
        budget_year=runtime.budget_year,
        selected_month=runtime.selected_month,
        selected_entity=scoped.selected_entity,
        selected_group=scoped.selected_group,
        selected_owner=scoped.selected_owner,
        actual_source_file=runtime.actual_source_file,
    )


async def resolve_query_report(
    *,
    editable_context_provider: EditableContextProvider,
    perspective: str,
    keyword: str,
    include_zero_rows: bool,
    entity_name: str = "",
    group_name: str = "",
    owner_dept: str = "",
) -> dict[str, Any]:
    runtime = await load_report_runtime_context(editable_context_provider=editable_context_provider)
    query_context = await load_query_report_context(
        runtime=runtime,
        perspective=perspective,
        entity_name=entity_name,
        group_name=group_name,
        owner_dept=owner_dept,
    )
    return build_query_report_payload(
        query_context=query_context,
        include_zero_rows=include_zero_rows,
        keyword=keyword,
    )


async def resolve_monthly_report(
    *,
    editable_context_provider: EditableContextProvider,
    entity_name: str = "",
    group_name: str = "",
    owner_dept: str = "",
    report_month: int | None = None,
) -> dict[str, Any]:
    runtime = await load_report_runtime_context(
        editable_context_provider=editable_context_provider,
        report_month=report_month,
    )
    monthly_context = await load_monthly_report_context(
        runtime=runtime,
        entity_name=entity_name,
        group_name=group_name,
        owner_dept=owner_dept,
    )
    return build_monthly_report_payload(monthly_context=monthly_context)


async def resolve_template_report(
    *,
    editable_context_provider: EditableContextProvider,
    keyword: str,
    entity_name: str = "",
    group_name: str = "",
    owner_dept: str = "",
    include_zero_rows: bool = False,
    report_month: int | None = None,
) -> dict[str, Any]:
    runtime = await load_report_runtime_context(
        editable_context_provider=editable_context_provider,
        report_month=report_month,
    )
    template_context = await load_template_report_context(
        runtime=runtime,
        entity_name=entity_name,
        group_name=group_name,
        owner_dept=owner_dept,
    )
    return build_template_report_payload(
        template_context=template_context,
        include_zero_rows=include_zero_rows,
        keyword=keyword,
    )


async def resolve_subject_report(
    *,
    editable_context_provider: EditableContextProvider,
    keyword: str,
    entity_name: str = "",
    subject_id: int | None = None,
    include_zero_rows: bool = False,
    report_month: int | None = None,
) -> dict[str, Any]:
    selected_subject_id = resolve_subject_filter_id(subject_id)
    runtime = await load_report_runtime_context(
        editable_context_provider=editable_context_provider,
        report_month=report_month,
    )
    subject_mode_context = await load_subject_mode_report_context(
        runtime=runtime,
        entity_name=entity_name,
    )
    return build_subject_report_payload(
        subject_mode_context=subject_mode_context,
        selected_subject_id=selected_subject_id,
        include_zero_rows=include_zero_rows,
        keyword=keyword,
    )


def resolve_expense_budget_execution_report_plan(
    selection: ExpenseBudgetExecutionReportSelection,
    *,
    surface: str,
) -> ExpenseBudgetExecutionReportResolutionPlan:
    if surface not in {"display", "export"}:
        raise ExpenseBudgetExecutionReportError(f"未知费用预算执行报表用途: {surface}")
    allowed_modes = EXPORT_REPORT_MODES if surface == "export" else DISPLAY_REPORT_MODES
    if selection.mode not in allowed_modes:
        raise ExpenseBudgetExecutionReportError(f"未知费用预算执行报表模式: {selection.mode}")
    if selection.mode in {"query", "flat"}:
        validate_report_perspective(selection.perspective)
    if selection.mode == "template":
        return ExpenseBudgetExecutionReportResolutionPlan(report_kind="template")
    if selection.mode == "subject":
        return ExpenseBudgetExecutionReportResolutionPlan(report_kind="subject")
    if surface == "export" and selection.mode != "query":
        return ExpenseBudgetExecutionReportResolutionPlan(report_kind="query")
    return ExpenseBudgetExecutionReportResolutionPlan(report_kind="monthly")


async def resolve_report_payload_from_plan(
    *,
    editable_context_provider: EditableContextProvider,
    selection: ExpenseBudgetExecutionReportSelection,
    plan: ExpenseBudgetExecutionReportResolutionPlan,
) -> dict[str, Any]:
    if plan.report_kind == "template":
        return await resolve_template_report(
            editable_context_provider=editable_context_provider,
            keyword=selection.keyword,
            entity_name=selection.entity_name,
            group_name=selection.group_name,
            owner_dept=selection.owner_dept,
            include_zero_rows=selection.include_zero_rows,
            report_month=selection.report_month,
        )
    if plan.report_kind == "subject":
        return await resolve_subject_report(
            editable_context_provider=editable_context_provider,
            keyword=selection.keyword,
            entity_name=selection.entity_name,
            subject_id=selection.subject_id,
            include_zero_rows=selection.include_zero_rows,
            report_month=selection.report_month,
        )
    if plan.report_kind == "query":
        return await resolve_query_report(
            editable_context_provider=editable_context_provider,
            perspective=selection.perspective,
            keyword=selection.keyword,
            include_zero_rows=selection.include_zero_rows,
            entity_name=selection.entity_name,
            group_name=selection.group_name,
            owner_dept=selection.owner_dept,
        )
    if plan.report_kind == "monthly":
        return await resolve_monthly_report(
            editable_context_provider=editable_context_provider,
            entity_name=selection.entity_name,
            group_name=selection.group_name,
            owner_dept=selection.owner_dept,
            report_month=selection.report_month,
        )
    raise ExpenseBudgetExecutionReportError(f"未知费用预算执行报表模式: {plan.report_kind}")


async def resolve_display_report_payload(
    *,
    editable_context_provider: EditableContextProvider,
    selection: ExpenseBudgetExecutionReportSelection,
) -> dict[str, Any]:
    plan = resolve_expense_budget_execution_report_plan(selection, surface="display")
    return await resolve_report_payload_from_plan(
        editable_context_provider=editable_context_provider,
        selection=selection,
        plan=plan,
    )


async def resolve_export_report_payload(
    *,
    editable_context_provider: EditableContextProvider,
    selection: ExpenseBudgetExecutionReportSelection,
) -> dict[str, Any]:
    plan = resolve_expense_budget_execution_report_plan(selection, surface="export")
    return await resolve_report_payload_from_plan(
        editable_context_provider=editable_context_provider,
        selection=selection,
        plan=plan,
    )
