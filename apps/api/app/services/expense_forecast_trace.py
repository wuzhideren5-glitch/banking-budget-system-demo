"""Trace read model for expense forecast monthly values."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

ForecastValueSource = Literal["actual", "manual", "auto", "override", "unconfigured", "aggregate"]


@dataclass(frozen=True)
class ExpenseForecastTraceMonth:
    month: int
    final_value: float
    system_value: float | None
    override_value: float | None
    value_source: ForecastValueSource
    calc_basis_json: str | None


@dataclass(frozen=True)
class ExpenseForecastTraceReadModel:
    rule_id: int | None = None
    rule_scheme: str | None = None
    items: list[ExpenseForecastTraceMonth] = field(default_factory=list)


class ExpenseForecastTraceSource(Protocol):
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


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_expense_forecast_trace_read_model(
    *,
    owner_name: str,
    subject_id: int,
    calc_map: dict[tuple[str, int, int], dict[str, Any]],
    override_map: dict[tuple[str, int, int], dict[str, Any]],
    forecast_map: dict[tuple[str, int, int], float],
    rule: dict[str, Any] | None,
) -> ExpenseForecastTraceReadModel:
    normalized_owner = _text(owner_name)
    normalized_subject_id = int(subject_id)
    items: list[ExpenseForecastTraceMonth] = []
    for month in range(1, 13):
        key = (normalized_owner, normalized_subject_id, month)
        calc_item = calc_map.get(key)
        override = override_map.get(key)
        final_value = float(forecast_map.get(key, 0.0))
        items.append(
            ExpenseForecastTraceMonth(
                month=month,
                final_value=final_value,
                system_value=float(override["system_value"]) if override else (float(calc_item["calc_value"]) if calc_item else None),
                override_value=float(override["override_value"]) if override else None,
                value_source="override" if override else "auto" if calc_item else "manual",
                calc_basis_json=_text(calc_item.get("calc_basis_json")) if calc_item else None,
            )
        )
    return ExpenseForecastTraceReadModel(
        rule_id=int(rule["id"]) if rule else None,
        rule_scheme=_text(rule.get("scheme_code")) if rule else None,
        items=items,
    )


async def build_expense_forecast_trace_read_model_from_source(
    *,
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    source: ExpenseForecastTraceSource,
) -> ExpenseForecastTraceReadModel:
    normalized_owner = _text(owner_name)
    normalized_subject_id = int(subject_id)
    owner_names = [normalized_owner]
    calc_map = await source.load_calc_result_map(
        year=int(year),
        forecast_version=forecast_version,
        owner_names=owner_names,
    )
    override_map = await source.load_override_map(
        year=int(year),
        forecast_version=forecast_version,
        owner_names=owner_names,
    )
    forecast_map = await source.load_forecast_map(
        year=int(year),
        forecast_version=forecast_version,
        owner_names=owner_names,
    )
    rule_map = await source.load_rule_map(
        year=int(year),
        forecast_version=forecast_version,
        owner_names=owner_names,
    )
    return build_expense_forecast_trace_read_model(
        owner_name=normalized_owner,
        subject_id=normalized_subject_id,
        calc_map=calc_map,
        override_map=override_map,
        forecast_map=forecast_map,
        rule=rule_map.get((normalized_owner, normalized_subject_id)),
    )
