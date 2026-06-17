"""Workflow assembly for expense forecast exports."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Protocol

from app.services.expense_forecast_export import (
    build_expense_forecast_export_workbook,
    build_expense_forecast_group_export_workbook,
)
from app.services.expense_forecast_export_plan import (
    ExpenseForecastExportPlanError,
    build_expense_forecast_export_plan,
    build_expense_forecast_group_export_plan,
)


@dataclass(frozen=True)
class ExpenseForecastExportWorkflowResult:
    stream: BytesIO
    display_file_name: str


class ExpenseForecastRegularExportSource(Protocol):
    async def build_scope_view(
        self,
        *,
        year: int,
        forecast_version: str,
        scope_type: str,
        scope_value: str,
    ) -> Any:
        ...

    async def build_subject_view(
        self,
        *,
        year: int,
        forecast_version: str,
        scope_type: str,
        scope_value: str,
        subject_id: int,
    ) -> Any:
        ...


class ExpenseForecastGroupExportSource(Protocol):
    async def build_scope_view(
        self,
        *,
        year: int,
        forecast_version: str,
        scope_type: str,
        scope_value: str,
    ) -> Any:
        ...

    async def load_owner_group_options(self) -> list[Any]:
        ...


async def build_expense_forecast_export_from_source(
    *,
    year: int,
    forecast_version: str,
    default_version: str,
    scope_type: str,
    scope_value: str,
    compile_mode: str,
    subject_id: int | None,
    amount_unit: str,
    exclude_fields: list[str],
    source: ExpenseForecastRegularExportSource,
) -> ExpenseForecastExportWorkflowResult:
    """Plan and build a regular expense forecast workbook without HTTP concerns."""
    export_plan = build_expense_forecast_export_plan(
        year=year,
        forecast_version=forecast_version,
        default_version=default_version,
        scope_type=scope_type,  # type: ignore[arg-type]
        scope_value=scope_value,
        compile_mode=compile_mode,
        subject_id=subject_id,
    )

    if export_plan.compile_mode == "subject":
        subject_view = await source.build_subject_view(
            year=export_plan.year,
            forecast_version=export_plan.forecast_version,
            scope_type=export_plan.scope_type,
            scope_value=export_plan.scope_value,
            subject_id=int(export_plan.subject_id or 0),
        )
        stream, display_file_name = build_expense_forecast_export_workbook(
            year=export_plan.year,
            forecast_version=export_plan.forecast_version,
            scope_type=export_plan.scope_type,
            scope_value=export_plan.scope_value,
            compile_mode=export_plan.compile_mode,
            amount_unit=amount_unit,
            exclude_fields=exclude_fields,
            subject_view=subject_view,
        )
    else:
        view = await source.build_scope_view(
            year=export_plan.year,
            forecast_version=export_plan.forecast_version,
            scope_type=export_plan.scope_type,
            scope_value=export_plan.scope_value,
        )
        stream, display_file_name = build_expense_forecast_export_workbook(
            year=export_plan.year,
            forecast_version=export_plan.forecast_version,
            scope_type=export_plan.scope_type,
            scope_value=export_plan.scope_value,
            compile_mode=export_plan.compile_mode,
            amount_unit=amount_unit,
            exclude_fields=exclude_fields,
            view=view,
        )

    return ExpenseForecastExportWorkflowResult(stream=stream, display_file_name=display_file_name)


async def build_expense_forecast_group_export_from_source(
    *,
    year: int,
    forecast_version: str,
    default_version: str,
    group_name: str,
    amount_unit: str,
    exclude_fields: list[str],
    source: ExpenseForecastGroupExportSource,
) -> ExpenseForecastExportWorkflowResult:
    """Plan and build a group expense forecast workbook without HTTP concerns."""
    export_plan = build_expense_forecast_group_export_plan(
        year=year,
        forecast_version=forecast_version,
        default_version=default_version,
        group_name=group_name,
        owner_group_options=await source.load_owner_group_options(),
    )

    owner_views: dict[str, Any] = {}
    for owner_name in export_plan.owner_names:
        owner_views[owner_name] = await source.build_scope_view(
            year=export_plan.year,
            forecast_version=export_plan.forecast_version,
            scope_type="owner",
            scope_value=owner_name,
        )

    first_owner_view = next(iter(owner_views.values()), None)
    actual_cutoff = int(getattr(first_owner_view, "actual_cutoff_month", 0) or 0)
    stream, display_file_name = build_expense_forecast_group_export_workbook(
        year=export_plan.year,
        forecast_version=export_plan.forecast_version,
        group_name=export_plan.group_name,
        amount_unit=amount_unit,
        exclude_fields=exclude_fields,
        actual_cutoff=actual_cutoff,
        owner_names=export_plan.owner_names,
        owner_views=owner_views,
    )
    return ExpenseForecastExportWorkflowResult(stream=stream, display_file_name=display_file_name)


__all__ = [
    "ExpenseForecastExportPlanError",
    "ExpenseForecastGroupExportSource",
    "ExpenseForecastRegularExportSource",
    "ExpenseForecastExportWorkflowResult",
    "build_expense_forecast_export_from_source",
    "build_expense_forecast_group_export_from_source",
]
