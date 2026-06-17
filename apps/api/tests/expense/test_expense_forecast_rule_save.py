from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unittest

from app.services import expense_forecast_rule_save as expense_forecast_rule_save_module
from app.services.expense_forecast_rule_save import (
    ExpenseForecastRuleSaveError,
    save_expense_forecast_rule,
)


@dataclass(frozen=True)
class SavedRule:
    rule_id: int


class FakeRuleSaveSource:
    def __init__(self, *, saved_rule_id: int = 7, loaded_rows: list[dict] | None = None) -> None:
        self.saved_rule_id = saved_rule_id
        self.loaded_rows = loaded_rows or [
            {
                "id": saved_rule_id,
                "owner_name": "部门A",
                "subject_id": 11,
                "scheme_code": "METRIC_EXPR",
            }
        ]
        self.save_request: dict | None = None
        self.load_requests: list[dict] = []
        self.recalculate_requests: list[dict] = []
        self.operation_logs: list[dict] = []

    async def save_rule_definition(self, *, rule: dict, rule_id: int | None, now: str) -> SavedRule:
        self.save_request = {"rule": rule, "rule_id": rule_id, "now": now}
        return SavedRule(rule_id=self.saved_rule_id)

    async def load_rule_rows(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
        subject_id: int | None,
    ) -> list[dict]:
        self.load_requests.append(
            {
                "year": year,
                "forecast_version": forecast_version,
                "owner_names": owner_names,
                "subject_id": subject_id,
            }
        )
        return self.loaded_rows

    async def recalculate_rules(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_name: str | None,
        subject_id: int | None,
    ) -> tuple[int, int]:
        self.recalculate_requests.append(
            {
                "year": year,
                "forecast_version": forecast_version,
                "owner_name": owner_name,
                "subject_id": subject_id,
            }
        )
        return (1, 12)

    async def write_operation_log(self, **kwargs) -> None:
        self.operation_logs.append(kwargs)


def metric_expr_rule(**overrides) -> dict:
    rule = {
        "forecast_year": 2026,
        "forecast_version": " V1 ",
        "owner_name": " 部门A ",
        "subject_id": 11,
        "scheme_code": "METRIC_EXPR",
        "auto_refresh_enabled": True,
    }
    rule.update(overrides)
    return rule


class ExpenseForecastRuleSaveTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_returns_loaded_rule_and_recalculates_auto_metric_rule(self) -> None:
        source = FakeRuleSaveSource()
        rule = metric_expr_rule()

        row = await save_expense_forecast_rule(
            rule=rule,
            rule_id=None,
            source=source,
            now="2026-06-04T12:00:00Z",
        )

        self.assertEqual(row["id"], 7)
        self.assertEqual(source.save_request, {"rule": rule, "rule_id": None, "now": "2026-06-04T12:00:00Z"})
        self.assertEqual(
            source.load_requests,
            [
                {
                    "year": 2026,
                    "forecast_version": "V1",
                    "owner_names": ["部门A"],
                    "subject_id": 11,
                }
            ],
        )
        self.assertEqual(
            source.recalculate_requests,
            [
                {
                    "year": 2026,
                    "forecast_version": "V1",
                    "owner_name": "部门A",
                    "subject_id": 11,
                }
            ],
        )
        self.assertEqual(
            source.operation_logs,
            [
                {
                    "action_type": "INSERT",
                    "action_desc": "新增费用预测规则 部门A/11",
                    "target_table": "expense_forecast_rule",
                    "affected_rows": 1,
                    "after_data": rule,
                }
            ],
        )

    async def test_update_audit_log_includes_rule_id_and_payload(self) -> None:
        source = FakeRuleSaveSource()
        rule = metric_expr_rule()

        await save_expense_forecast_rule(
            rule=rule,
            rule_id=7,
            source=source,
            now="2026-06-04T12:00:00Z",
        )

        self.assertEqual(
            source.operation_logs,
            [
                {
                    "action_type": "UPDATE",
                    "action_desc": "更新费用预测规则 部门A/11",
                    "target_table": "expense_forecast_rule",
                    "affected_rows": 1,
                    "after_data": {"id": 7, **rule},
                }
            ],
        )

    async def test_save_skips_recalculation_for_manual_or_disabled_auto_refresh(self) -> None:
        manual_source = FakeRuleSaveSource()
        disabled_source = FakeRuleSaveSource()

        await save_expense_forecast_rule(
            rule=metric_expr_rule(scheme_code="MANUAL"),
            rule_id=7,
            source=manual_source,
            now="2026-06-04T12:00:00Z",
        )
        await save_expense_forecast_rule(
            rule=metric_expr_rule(auto_refresh_enabled=False),
            rule_id=7,
            source=disabled_source,
            now="2026-06-04T12:00:00Z",
        )

        self.assertEqual(manual_source.recalculate_requests, [])
        self.assertEqual(disabled_source.recalculate_requests, [])

    async def test_save_raises_when_saved_rule_cannot_be_loaded_back(self) -> None:
        source = FakeRuleSaveSource(saved_rule_id=7, loaded_rows=[{"id": 8}])

        with self.assertRaisesRegex(ExpenseForecastRuleSaveError, "保存规则后未找到结果"):
            await save_expense_forecast_rule(
                rule=metric_expr_rule(),
                rule_id=None,
                source=source,
                now="2026-06-04T12:00:00Z",
            )
        self.assertEqual(source.operation_logs, [])

    def test_save_workflow_centralizes_rule_identity_and_audit_payload(self) -> None:
        source_text = Path(expense_forecast_rule_save_module.__file__).read_text(encoding="utf-8")

        self.assertIn("class ExpenseForecastRuleSaveContext:", source_text)
        self.assertIn("def _rule_save_context(", source_text)
        self.assertIn("def _rule_save_audit_log(", source_text)
        self.assertIn("context = _rule_save_context(rule)", source_text)
        self.assertIn("await source.write_operation_log(", source_text)
        self.assertIn("**_rule_save_audit_log(", source_text)


if __name__ == "__main__":
    unittest.main()
