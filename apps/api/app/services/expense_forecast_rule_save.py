"""Orchestration for saving expense forecast rules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


AUTO_RECALCULATE_SCHEMES = {"RESIDUAL_ALLOC", "METRIC_EXPR"}


class ExpenseForecastRuleSaveError(RuntimeError):
    """Raised when a saved rule cannot be resolved into a read model row."""


@dataclass(frozen=True)
class ExpenseForecastRuleSaveContext:
    year: int
    forecast_version: str
    owner_name: str
    subject_id: int
    scheme_code: str
    auto_refresh_enabled: bool

    @property
    def should_recalculate(self) -> bool:
        return self.auto_refresh_enabled and self.scheme_code in AUTO_RECALCULATE_SCHEMES


class SavedExpenseForecastRule(Protocol):
    rule_id: int


class ExpenseForecastRuleSaveSource(Protocol):
    async def save_rule_definition(
        self,
        *,
        rule: Mapping[str, Any],
        rule_id: int | None,
        now: str,
    ) -> SavedExpenseForecastRule:
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

    async def recalculate_rules(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_name: str | None,
        subject_id: int | None,
    ) -> tuple[int, int]:
        ...

    async def write_operation_log(self, **kwargs) -> None:
        ...


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _rule_save_context(rule: Mapping[str, Any]) -> ExpenseForecastRuleSaveContext:
    return ExpenseForecastRuleSaveContext(
        year=int(rule["forecast_year"]),
        forecast_version=_text(rule["forecast_version"]),
        owner_name=_text(rule["owner_name"]),
        subject_id=int(rule["subject_id"]),
        scheme_code=_text(rule.get("scheme_code")),
        auto_refresh_enabled=bool(rule.get("auto_refresh_enabled")),
    )


def _rule_save_audit_log(
    *,
    rule: Mapping[str, Any],
    rule_id: int | None,
    context: ExpenseForecastRuleSaveContext,
) -> dict[str, Any]:
    if rule_id is None:
        action_type = "INSERT"
        action_desc = f"新增费用预测规则 {context.owner_name}/{context.subject_id}"
        after_data = dict(rule)
    else:
        action_type = "UPDATE"
        action_desc = f"更新费用预测规则 {context.owner_name}/{context.subject_id}"
        after_data = {"id": int(rule_id), **dict(rule)}

    return {
        "action_type": action_type,
        "action_desc": action_desc,
        "target_table": "expense_forecast_rule",
        "affected_rows": 1,
        "after_data": after_data,
    }


async def save_expense_forecast_rule(
    *,
    rule: Mapping[str, Any],
    rule_id: int | None,
    source: ExpenseForecastRuleSaveSource,
    now: str,
) -> dict[str, Any]:
    saved = await source.save_rule_definition(rule=rule, rule_id=rule_id, now=now)
    saved_rule_id = int(saved.rule_id)
    context = _rule_save_context(rule)

    rows = await source.load_rule_rows(
        year=context.year,
        forecast_version=context.forecast_version,
        owner_names=[context.owner_name],
        subject_id=context.subject_id,
    )
    matched = next((row for row in rows if int(row["id"]) == saved_rule_id), None)
    if matched is None:
        raise ExpenseForecastRuleSaveError("保存规则后未找到结果")

    if context.should_recalculate:
        await source.recalculate_rules(
            year=context.year,
            forecast_version=context.forecast_version,
            owner_name=context.owner_name,
            subject_id=context.subject_id,
        )

    await source.write_operation_log(
        **_rule_save_audit_log(
            rule=rule,
            rule_id=rule_id,
            context=context,
        )
    )
    return matched
