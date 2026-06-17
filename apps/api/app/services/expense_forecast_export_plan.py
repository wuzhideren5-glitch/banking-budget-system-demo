"""Request planning for expense forecast exports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


ScopeType = Literal["entity", "group", "owner"]
CompileMode = Literal["scope", "subject"]


class ExpenseForecastExportPlanError(ValueError):
    """Raised when an export request cannot be mapped to a current export contract."""


@dataclass(frozen=True)
class ExpenseForecastExportPlan:
    year: int
    forecast_version: str
    scope_type: ScopeType
    scope_value: str
    compile_mode: CompileMode
    subject_id: int | None


@dataclass(frozen=True)
class ExpenseForecastGroupExportPlan:
    year: int
    forecast_version: str
    group_name: str
    owner_names: list[str]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_scope_type(raw: str) -> ScopeType:
    value = _text(raw)
    if value not in {"entity", "group", "owner"}:
        raise ExpenseForecastExportPlanError("编制口径仅支持 entity、group、owner")
    return value  # type: ignore[return-value]


def _normalize_compile_mode(raw: str) -> CompileMode:
    value = _text(raw)
    if value not in {"scope", "subject"}:
        return "scope"
    return value  # type: ignore[return-value]


def build_expense_forecast_export_plan(
    *,
    year: int,
    forecast_version: str,
    default_version: str,
    scope_type: ScopeType,
    scope_value: str,
    compile_mode: str,
    subject_id: int | None,
) -> ExpenseForecastExportPlan:
    normalized_compile_mode = _normalize_compile_mode(compile_mode)
    normalized_subject_id = int(subject_id) if subject_id is not None else None
    if normalized_compile_mode == "subject" and normalized_subject_id is None:
        raise ExpenseForecastExportPlanError("按预算科目编制导出缺少 subject_id")

    return ExpenseForecastExportPlan(
        year=int(year),
        forecast_version=_text(forecast_version) or _text(default_version),
        scope_type=_normalize_scope_type(scope_type),
        scope_value=_text(scope_value),
        compile_mode=normalized_compile_mode,
        subject_id=normalized_subject_id,
    )


def build_expense_forecast_group_export_plan(
    *,
    year: int,
    forecast_version: str,
    default_version: str,
    group_name: str,
    owner_group_options: list[Any],
) -> ExpenseForecastGroupExportPlan:
    normalized_group_name = _text(group_name)
    matched_group = next(
        (group for group in owner_group_options if _text(getattr(group, "group_value", "")) == normalized_group_name),
        None,
    )
    if not matched_group:
        raise ExpenseForecastExportPlanError(f'事业群 "{normalized_group_name}" 不存在')

    owner_names = sorted(
        [
            _text(getattr(owner, "value", ""))
            for owner in getattr(matched_group, "owner_options", [])
            if _text(getattr(owner, "value", ""))
        ],
        key=lambda value: (len(value), value),
    )

    return ExpenseForecastGroupExportPlan(
        year=int(year),
        forecast_version=_text(forecast_version) or _text(default_version),
        group_name=normalized_group_name,
        owner_names=owner_names,
    )
