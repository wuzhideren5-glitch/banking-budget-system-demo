"""Orchestration for expense forecast rule recalculation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.services.expense_forecast_recalculation_commands import ExpenseForecastRecalculatedMonth
from app.services.expense_forecast_rule_calculation import calculate_expense_forecast_rule_months

ExpenseForecastRecalculationTrigger = Literal["manual", "auto"]


class ExpenseForecastRecalculationSource(Protocol):
    async def load_scope_rows(self) -> list[tuple[str, str, str]]:
        ...

    async def load_rule_rows(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
        subject_id: int | None,
    ) -> list[dict[str, Any]]:
        ...

    async def load_actual_cutoff_month(self, year: int) -> int:
        ...

    async def load_actual_map(self, year: int, owner_names: list[str]) -> dict[tuple[str, str, int], float]:
        ...

    async def load_annual_input_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, str], float]:
        ...

    async def load_forecast_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], float]:
        ...

    async def load_override_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], dict[str, Any]]:
        ...

    async def load_metric_source_month_map(
        self,
        year: int,
        indicator_code: str,
        product_code: str | None = None,
    ) -> dict[int, float]:
        ...

    async def save_recalculation_results(
        self,
        *,
        year: int,
        forecast_version: str,
        rows: list[ExpenseForecastRecalculatedMonth],
        now: str,
    ) -> int:
        ...


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


@dataclass(frozen=True)
class ExpenseForecastRecalculationContext:
    owners: list[str]
    rules: list[dict[str, Any]]
    actual_cutoff_month: int
    actual_map: dict[tuple[str, str, int], float]
    annual_input_map: dict[tuple[str, int, str], float]
    forecast_map: dict[tuple[str, int, int], float]
    override_map: dict[tuple[str, int, int], dict[str, Any]]


def _rule_enabled_for_trigger(rule: dict[str, Any], trigger: ExpenseForecastRecalculationTrigger) -> bool:
    if not bool(rule.get("enabled")):
        return False
    if trigger == "manual" and not bool(rule.get("manual_recalc_enabled", True)):
        return False
    return True


async def _load_recalculation_context(
    *,
    year: int,
    forecast_version: str,
    source: ExpenseForecastRecalculationSource,
    trigger: ExpenseForecastRecalculationTrigger,
    owner_name: str | None,
    subject_id: int | None,
) -> ExpenseForecastRecalculationContext | None:
    owners = [_text(owner_name)] if _text(owner_name) else [
        _text(item[2]) for item in await source.load_scope_rows() if _text(item[2])
    ]
    owners = [item for item in owners if item]
    if not owners:
        return None

    loaded_rules = await source.load_rule_rows(
        year=year,
        forecast_version=forecast_version,
        owner_names=owners,
        subject_id=subject_id,
    )
    rules = [rule for rule in loaded_rules if _rule_enabled_for_trigger(rule, trigger)]
    if not rules:
        return None

    actual_cutoff_month = await source.load_actual_cutoff_month(year)
    actual_map = await source.load_actual_map(year, owners)
    annual_input_map = await source.load_annual_input_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=owners,
    )
    forecast_map = await source.load_forecast_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=owners,
    )
    override_map = await source.load_override_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=owners,
    )

    return ExpenseForecastRecalculationContext(
        owners=owners,
        rules=rules,
        actual_cutoff_month=actual_cutoff_month,
        actual_map=actual_map,
        annual_input_map=annual_input_map,
        forecast_map=forecast_map,
        override_map=override_map,
    )


async def recalculate_expense_forecast_rules(
    *,
    year: int,
    forecast_version: str,
    source: ExpenseForecastRecalculationSource,
    now: str,
    owner_name: str | None = None,
    subject_id: int | None = None,
    trigger: ExpenseForecastRecalculationTrigger = "manual",
) -> tuple[int, int]:
    context = await _load_recalculation_context(
        year=year,
        forecast_version=forecast_version,
        source=source,
        trigger=trigger,
        owner_name=owner_name,
        subject_id=subject_id,
    )
    if context is None:
        return 0, 0

    recalculated_rows: list[ExpenseForecastRecalculatedMonth] = []
    for rule in context.rules:
        owner = _text(rule["owner_name"])
        rule_subject_id = int(rule["subject_id"])
        month_values = await calculate_expense_forecast_rule_months(
            rule=rule,
            year=year,
            forecast_version=forecast_version,
            owner_name=owner,
            subject_id=rule_subject_id,
            subject_name=_text(rule["subject_name"]),
            actual_cutoff_month=context.actual_cutoff_month,
            annual_input_map=context.annual_input_map,
            actual_map=context.actual_map,
            forecast_map=context.forecast_map,
            load_metric_source_month_map=source.load_metric_source_month_map,
        )
        for month, item in month_values.items():
            override = context.override_map.get((owner, rule_subject_id, int(month)))
            recalculated_rows.append(
                ExpenseForecastRecalculatedMonth(
                    owner_name=owner,
                    subject_id=rule_subject_id,
                    month=int(month),
                    rule_id=int(rule["id"]),
                    calc_value=float(item["value"]),
                    calc_basis_json=_text(item.get("basis")),
                    has_override=override is not None,
                    override_value=float(override["override_value"]) if override else 0.0,
                )
            )

    updated_cells = await source.save_recalculation_results(
        year=year,
        forecast_version=forecast_version,
        rows=recalculated_rows,
        now=now,
    )
    return len(context.rules), updated_cells
