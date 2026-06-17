"""Copy expense forecast rules between forecast versions."""
from __future__ import annotations

from typing import Any, Mapping, Protocol


class ExpenseForecastRuleCopySource(Protocol):
    async def load_rule_rows(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str] | None = None,
        subject_id: int | None = None,
    ) -> list[dict[str, Any]]:
        ...

    async def save_rule(self, *, rule: Mapping[str, Any], rule_id: int | None) -> Any:
        ...


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _rule_copy_payload(row: Mapping[str, Any], *, year: int, target_version: str) -> dict[str, Any]:
    return {
        "forecast_year": int(year),
        "forecast_version": target_version,
        "owner_name": _text(row["owner_name"]),
        "subject_id": int(row["subject_id"]),
        "scheme_code": row["scheme_code"],
        "enabled": bool(row["enabled"]),
        "allow_manual_override": bool(row["allow_manual_override"]),
        "auto_refresh_enabled": bool(row["auto_refresh_enabled"]),
        "manual_recalc_enabled": bool(row["manual_recalc_enabled"]),
        "metric_source_priority": row["metric_source_priority"],
        "effective_from_month": int(row["effective_from_month"]),
        "effective_to_month": int(row["effective_to_month"]),
        "priority": int(row["priority"]),
        "remark": row["remark"],
        "params": list(row.get("params", []) or []),
        "variables": list(row.get("variables", []) or []),
    }


async def copy_expense_forecast_rules_from_version(
    *,
    year: int,
    source_version: str,
    target_version: str,
    source: ExpenseForecastRuleCopySource,
) -> int:
    normalized_source_version = _text(source_version)
    normalized_target_version = _text(target_version)
    source_rows = await source.load_rule_rows(
        year=int(year),
        forecast_version=normalized_source_version,
    )
    copied = 0
    for row in source_rows:
        rule = _rule_copy_payload(row, year=int(year), target_version=normalized_target_version)
        existing = await source.load_rule_rows(
            year=int(year),
            forecast_version=normalized_target_version,
            owner_names=[rule["owner_name"]],
            subject_id=int(rule["subject_id"]),
        )
        existing_id = int(existing[0]["id"]) if existing else None
        await source.save_rule(rule=rule, rule_id=existing_id)
        copied += 1
    return copied
