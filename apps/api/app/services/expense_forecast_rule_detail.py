"""Detail lookup workflow for expense forecast rules."""
from __future__ import annotations

from typing import Any, Protocol


class ExpenseForecastRuleDetailNotFound(RuntimeError):
    """Raised when a requested rule detail cannot be resolved."""


class ExpenseForecastRuleDetailSource(Protocol):
    async def load_rule_rows(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str] | None = None,
        subject_id: int | None = None,
    ) -> list[dict[str, Any]]:
        ...

    async def load_rule_identity(self, *, rule_id: int) -> dict[str, Any] | None:
        ...


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _match_rule(rows: list[dict[str, Any]], rule_id: int) -> dict[str, Any] | None:
    return next((row for row in rows if int(row["id"]) == int(rule_id)), None)


async def load_expense_forecast_rule_detail(
    *,
    rule_id: int,
    default_year: int,
    default_version: str,
    source: ExpenseForecastRuleDetailSource,
) -> dict[str, Any]:
    rows = await source.load_rule_rows(
        year=int(default_year),
        forecast_version=_text(default_version),
    )
    matched = _match_rule(rows, int(rule_id))
    if matched is not None:
        return matched

    identity = await source.load_rule_identity(rule_id=int(rule_id))
    if identity is None:
        raise ExpenseForecastRuleDetailNotFound("预测规则不存在")

    rows = await source.load_rule_rows(
        year=int(identity["forecast_year"]),
        forecast_version=_text(identity["forecast_version"]),
        owner_names=[_text(identity["owner_name"])],
        subject_id=int(identity["subject_id"]),
    )
    matched = _match_rule(rows, int(rule_id))
    if matched is None:
        raise ExpenseForecastRuleDetailNotFound("预测规则不存在")
    return matched
