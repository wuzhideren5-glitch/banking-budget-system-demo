"""Simulation workflow for expense forecast rules."""
from __future__ import annotations

from typing import Any, Mapping, Protocol


class ExpenseForecastRuleSimulationError(RuntimeError):
    """Raised when a rule simulation request cannot be resolved."""


class ExpenseForecastRuleSimulationSource(Protocol):
    async def load_subject_by_id(self, subject_id: int) -> dict[str, Any] | None:
        ...

    async def load_actual_cutoff_month(self, year: int) -> int:
        ...

    async def load_actual_map(self, year: int, owner_names: list[str]) -> dict[Any, Any]:
        ...

    async def load_annual_input_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[Any, Any]:
        ...

    async def load_forecast_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[Any, Any]:
        ...

    async def calculate_rule_months(self, **kwargs) -> dict[int, dict[str, Any]]:
        ...


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _simulation_rule_payload(rule: Mapping[str, Any], *, subject_name: str) -> dict[str, Any]:
    return {
        "id": 0,
        "owner_name": _text(rule["owner_name"]),
        "subject_id": int(rule["subject_id"]),
        "subject_name": subject_name,
        "scheme_code": rule["scheme_code"],
        "effective_from_month": int(rule["effective_from_month"]),
        "effective_to_month": int(rule["effective_to_month"]),
        "metric_source_priority": rule["metric_source_priority"],
        "params": list(rule.get("params", []) or []),
        "variables": list(rule.get("variables", []) or []),
    }


async def simulate_expense_forecast_rule(
    *,
    rule: Mapping[str, Any],
    source: ExpenseForecastRuleSimulationSource,
) -> dict[str, Any]:
    year = int(rule["forecast_year"])
    forecast_version = _text(rule["forecast_version"])
    owner_name = _text(rule["owner_name"])
    subject_id = int(rule["subject_id"])
    subject = await source.load_subject_by_id(subject_id)
    if not subject:
        raise ExpenseForecastRuleSimulationError("预算科目不存在")
    subject_name = _text(subject["subject_name"])

    actual_cutoff = await source.load_actual_cutoff_month(year)
    actual_map = await source.load_actual_map(year, [owner_name])
    annual_input_map = await source.load_annual_input_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=[owner_name],
    )
    forecast_map = await source.load_forecast_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=[owner_name],
    )
    values = await source.calculate_rule_months(
        rule=_simulation_rule_payload(rule, subject_name=subject_name),
        year=year,
        forecast_version=forecast_version,
        owner_name=owner_name,
        subject_id=subject_id,
        subject_name=subject_name,
        actual_cutoff_month=actual_cutoff,
        annual_input_map=annual_input_map,
        actual_map=actual_map,
        forecast_map=forecast_map,
    )
    return {
        "scheme_code": rule["scheme_code"],
        "months": [
            {
                "month": int(month),
                "final_value": float(item["value"]),
                "system_value": float(item["value"]),
                "override_value": None,
                "value_source": "auto",
                "calc_basis_json": _text(item.get("basis")) or None,
            }
            for month, item in sorted(values.items())
        ],
    }
