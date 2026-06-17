"""Read-model context assembly for expense forecast views."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.services.expense_forecast_data_context import build_expense_forecast_effective_manage_departments
from app.services.expense_forecast_view_model import (
    ScopeType,
    build_expense_forecast_scope_view_model,
    build_expense_forecast_subject_owner_view_model,
)


class ExpenseForecastViewReadModelError(ValueError):
    """Raised when current data cannot build an expense forecast view."""


@dataclass(frozen=True)
class ExpenseForecastViewContext:
    actual_cutoff_month: int
    actual_map: dict[tuple[str, str, int], float]
    annual_budget_map: dict[tuple[str, str], float]
    forecast_map: dict[tuple[str, int, int], float]
    rule_map: dict[tuple[str, int], dict[str, Any]]
    calc_result_map: dict[tuple[str, int, int], dict[str, Any]]
    override_map: dict[tuple[str, int, int], dict[str, Any]]
    annual_input_map: dict[tuple[str, int, str], float]


@dataclass(frozen=True)
class ExpenseForecastStaticViewContext:
    subject_rows: list[dict[str, Any]]
    effective_manage_by_id: dict[int, str]
    actual_cutoff_month: int


class ExpenseForecastViewSource(Protocol):
    async def load_budget_subject_rows(self) -> list[dict[str, Any]]:
        ...

    async def resolve_scope_owners(self, scope_type: ScopeType, scope_value: str) -> list[str]:
        ...

    async def load_actual_cutoff_month(self, year: int) -> int:
        ...

    async def load_manage_department_map(self) -> dict[str, str]:
        ...

    async def load_actual_map(self, year: int, owner_names: list[str]) -> dict[tuple[str, str, int], float]:
        ...

    async def load_annual_budget_map(self, year: int, owner_names: list[str]) -> dict[tuple[str, str], float]:
        ...

    async def load_forecast_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], float]:
        ...

    async def load_rule_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int], dict[str, Any]]:
        ...

    async def load_calc_result_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], dict[str, Any]]:
        ...

    async def load_override_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], dict[str, Any]]:
        ...

    async def load_annual_input_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, str], float]:
        ...


async def _load_expense_forecast_view_context(
    *,
    year: int,
    forecast_version: str,
    owners: list[str],
    source: ExpenseForecastViewSource,
    actual_cutoff_month: int | None = None,
) -> ExpenseForecastViewContext:
    resolved_actual_cutoff_month = (
        int(actual_cutoff_month)
        if actual_cutoff_month is not None
        else await source.load_actual_cutoff_month(year)
    )
    actual_map = await source.load_actual_map(year, owners)
    annual_budget_map = await source.load_annual_budget_map(year, owners)
    forecast_map = await source.load_forecast_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=owners,
    )
    rule_map = await source.load_rule_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=owners,
    )
    calc_result_map = await source.load_calc_result_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=owners,
    )
    override_map = await source.load_override_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=owners,
    )
    annual_input_map = await source.load_annual_input_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=owners,
    )
    return ExpenseForecastViewContext(
        actual_cutoff_month=resolved_actual_cutoff_month,
        actual_map=actual_map,
        annual_budget_map=annual_budget_map,
        forecast_map=forecast_map,
        rule_map=rule_map,
        calc_result_map=calc_result_map,
        override_map=override_map,
        annual_input_map=annual_input_map,
    )


async def _load_expense_forecast_static_view_context(
    *,
    year: int,
    source: ExpenseForecastViewSource,
) -> ExpenseForecastStaticViewContext:
    subject_rows = await source.load_budget_subject_rows()
    if not subject_rows:
        raise ExpenseForecastViewReadModelError("当前没有可用的预算科目树")

    manage_department_map = await source.load_manage_department_map()
    effective_manage_by_id, _effective_manage_by_name = build_expense_forecast_effective_manage_departments(
        subject_rows,
        manage_department_map,
    )
    actual_cutoff_month = await source.load_actual_cutoff_month(int(year))
    return ExpenseForecastStaticViewContext(
        subject_rows=subject_rows,
        effective_manage_by_id=effective_manage_by_id,
        actual_cutoff_month=actual_cutoff_month,
    )


async def _build_scope_read_model_for_owners(
    *,
    year: int,
    forecast_version: str,
    scope_type: ScopeType,
    scope_value: str,
    owners: list[str],
    static_context: ExpenseForecastStaticViewContext,
    source: ExpenseForecastViewSource,
) -> dict[str, Any]:
    view_context = await _load_expense_forecast_view_context(
        year=year,
        forecast_version=forecast_version,
        owners=owners,
        source=source,
        actual_cutoff_month=static_context.actual_cutoff_month,
    )
    return _build_scope_read_model_from_context(
        year=year,
        forecast_version=forecast_version,
        scope_type=scope_type,
        scope_value=scope_value,
        owners=owners,
        static_context=static_context,
        view_context=view_context,
    )


def _build_scope_read_model_from_context(
    *,
    year: int,
    forecast_version: str,
    scope_type: ScopeType,
    scope_value: str,
    owners: list[str],
    static_context: ExpenseForecastStaticViewContext,
    view_context: ExpenseForecastViewContext,
) -> dict[str, Any]:
    return build_expense_forecast_scope_view_model(
        year=year,
        forecast_version=forecast_version,
        scope_type=scope_type,
        scope_value=scope_value,
        subject_rows=static_context.subject_rows,
        owners=owners,
        actual_cutoff_month=view_context.actual_cutoff_month,
        effective_manage_by_id=static_context.effective_manage_by_id,
        actual_map=view_context.actual_map,
        annual_budget_map=view_context.annual_budget_map,
        forecast_map=view_context.forecast_map,
        rule_map=view_context.rule_map,
        calc_result_map=view_context.calc_result_map,
        override_map=view_context.override_map,
        annual_input_map=view_context.annual_input_map,
    )


async def build_expense_forecast_scope_read_model(
    *,
    year: int,
    forecast_version: str,
    scope_type: ScopeType,
    scope_value: str,
    source: ExpenseForecastViewSource,
) -> dict[str, Any]:
    owners = await source.resolve_scope_owners(scope_type, scope_value)
    static_context = await _load_expense_forecast_static_view_context(year=year, source=source)
    return await _build_scope_read_model_for_owners(
        year=year,
        forecast_version=forecast_version,
        scope_type=scope_type,
        scope_value=scope_value,
        owners=owners,
        static_context=static_context,
        source=source,
    )


async def build_expense_forecast_subject_read_model(
    *,
    year: int,
    forecast_version: str,
    scope_type: ScopeType,
    scope_value: str,
    subject_id: int,
    source: ExpenseForecastViewSource,
) -> dict[str, Any]:
    static_context = await _load_expense_forecast_static_view_context(year=year, source=source)
    subject_rows = static_context.subject_rows
    by_id = {int(row["id"]): row for row in subject_rows}
    subject = by_id.get(int(subject_id))
    if not subject:
        raise ExpenseForecastViewReadModelError("所选预算科目不存在")
    if not bool(subject["is_leaf"]) or subject["formula_text"]:
        raise ExpenseForecastViewReadModelError("按预算科目编制仅支持选择末级叶子预算科目")

    normalized_manage_department = static_context.effective_manage_by_id.get(int(subject_id), "")
    owners = await source.resolve_scope_owners(scope_type, scope_value)
    if normalized_manage_department:
        owners = [owner_name for owner_name in owners if owner_name == normalized_manage_department]

    view_context = await _load_expense_forecast_view_context(
        year=year,
        forecast_version=forecast_version,
        owners=owners,
        source=source,
        actual_cutoff_month=static_context.actual_cutoff_month,
    )

    return build_expense_forecast_subject_owner_view_model(
        year=year,
        forecast_version=forecast_version,
        scope_type=scope_type,
        scope_value=scope_value,
        actual_cutoff_month=view_context.actual_cutoff_month,
        subject_id=int(subject_id),
        subject_name=str(subject["subject_name"]).strip(),
        owners=owners,
        normalized_manage_department=normalized_manage_department,
        actual_map=view_context.actual_map,
        annual_budget_map=view_context.annual_budget_map,
        forecast_map=view_context.forecast_map,
        rule_map=view_context.rule_map,
        calc_result_map=view_context.calc_result_map,
        override_map=view_context.override_map,
        annual_input_map=view_context.annual_input_map,
    )


async def build_expense_forecast_group_read_model(
    *,
    year: int,
    forecast_version: str,
    group_name: str,
    source: ExpenseForecastViewSource,
) -> dict[str, Any]:
    owner_names = await source.resolve_scope_owners("group", group_name)
    static_context = await _load_expense_forecast_static_view_context(year=year, source=source)
    group_view_context = await _load_expense_forecast_view_context(
        year=year,
        forecast_version=forecast_version,
        owners=owner_names,
        source=source,
        actual_cutoff_month=static_context.actual_cutoff_month,
    )
    owner_views: list[dict[str, Any]] = []
    actual_cutoff_month = 0
    for owner_name in owner_names:
        owner_view = _build_scope_read_model_from_context(
            year=year,
            forecast_version=forecast_version,
            scope_type="owner",
            scope_value=owner_name,
            owners=[owner_name],
            static_context=static_context,
            view_context=group_view_context,
        )
        actual_cutoff_month = max(actual_cutoff_month, int(owner_view["actual_cutoff_month"]))
        owner_views.append(
            {
                "owner_name": owner_name,
                "rows": owner_view["rows"],
            }
        )
    return {
        "year": year,
        "forecast_version": forecast_version,
        "group_name": group_name,
        "actual_cutoff_month": actual_cutoff_month,
        "owner_views": owner_views,
    }
