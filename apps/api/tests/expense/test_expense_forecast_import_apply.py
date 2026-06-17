from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
import unittest

from app.db_bootstrap.expense import EXPENSE_FORECAST_SCHEMA
from app.services import expense_forecast_import_apply as import_apply_module
from app.services.expense_forecast_import_apply import apply_expense_forecast_import_rows


NOW = "2026-06-01T12:00:00Z"


def init_db(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("CREATE TABLE budget_subject_catalog (id INTEGER PRIMARY KEY)")
        db.executemany("INSERT INTO budget_subject_catalog(id) VALUES (?)", [(11,), (12,)])
        db.executescript(EXPENSE_FORECAST_SCHEMA)
        db.execute(
            """
            INSERT INTO expense_forecast_rule(
              id, forecast_year, forecast_version, owner_name, subject_id, scheme_code,
              enabled, allow_manual_override, auto_refresh_enabled, manual_recalc_enabled,
              metric_source_priority, effective_from_month, effective_to_month, priority,
              created_at, updated_at
            ) VALUES (7, 2026, 'V1', '部门A', 12, 'RESIDUAL_ALLOC', 1, 1, 1, 1, 'metric_first', 1, 12, 100, ?, ?)
            """,
            (NOW, NOW),
        )
        db.commit()


def fetch_rows(path: Path, sql: str) -> list[sqlite3.Row]:
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return list(db.execute(sql))


class FakeImportApplyWorkflowSource:
    def __init__(self) -> None:
        self.recalculate_requests: list[tuple[int, str, str, int]] = []
        self.operation_logs: list[dict] = []

    async def recalculate_rules(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_name: str,
        subject_id: int,
    ) -> tuple[int, int]:
        self.recalculate_requests.append((year, forecast_version, owner_name, subject_id))
        return (1, 12)

    async def write_operation_log(self, **kwargs) -> None:
        self.operation_logs.append(kwargs)


class ExpenseForecastImportApplyTests(unittest.TestCase):
    def test_applies_manual_and_auto_month_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)

            result = asyncio.run(
                apply_expense_forecast_import_rows(
                    db_path=db_path,
                    rows=[
                        {
                            "scope_value": "部门A",
                            "subject_id": 11,
                            "field_name": "month_forecast",
                            "month": 2,
                            "value": 100.0,
                            "action": "updated",
                            "rule_scheme": "MANUAL",
                        },
                        {
                            "scope_value": "部门A",
                            "subject_id": 12,
                            "field_name": "month_forecast",
                            "month": 3,
                            "value": 222.0,
                            "action": "inserted",
                            "rule_id": 7,
                            "rule_scheme": "RESIDUAL_ALLOC",
                            "system_value": 180.0,
                        },
                    ],
                    year=2026,
                    forecast_version="V1",
                    scope_type="owner",
                    now=NOW,
                )
            )

            self.assertEqual(result.inserted_cells, 1)
            self.assertEqual(result.updated_cells, 1)
            self.assertEqual(result.skipped_cells, 0)
            self.assertEqual(result.recalc_targets, [])

            forecast_rows = fetch_rows(
                db_path,
                """
                SELECT scope_type, scope_value, subject_id, month, forecast_value
                FROM expense_forecast_entry
                ORDER BY subject_id, month
                """,
            )
            self.assertEqual([dict(row) for row in forecast_rows], [
                {
                    "scope_type": "owner",
                    "scope_value": "部门A",
                    "subject_id": 11,
                    "month": 2,
                    "forecast_value": 100.0,
                },
                {
                    "scope_type": "owner",
                    "scope_value": "部门A",
                    "subject_id": 12,
                    "month": 3,
                    "forecast_value": 222.0,
                },
            ])

            override_rows = fetch_rows(
                db_path,
                """
                SELECT owner_name, subject_id, month, rule_id, system_value, override_value, override_reason
                FROM expense_forecast_override
                """,
            )
            self.assertEqual([dict(row) for row in override_rows], [
                {
                    "owner_name": "部门A",
                    "subject_id": 12,
                    "month": 3,
                    "rule_id": 7,
                    "system_value": 180.0,
                    "override_value": 222.0,
                    "override_reason": "Excel导入覆盖",
                }
            ])

    def test_applies_annual_rows_and_tracks_recalculation_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)

            result = asyncio.run(
                apply_expense_forecast_import_rows(
                    db_path=db_path,
                    rows=[
                        {
                            "scope_value": "部门A",
                            "subject_id": 11,
                            "field_name": "business_submission",
                            "month": None,
                            "value": 300.0,
                            "action": "inserted",
                        },
                        {
                            "scope_value": "部门A",
                            "subject_id": 12,
                            "field_name": "capital_advice",
                            "month": None,
                            "value": 0.0,
                            "action": "skipped",
                        },
                        {
                            "scope_value": "部门A",
                            "subject_id": 12,
                            "field_name": "business_submission",
                            "month": None,
                            "value": 999.0,
                            "action": "error",
                        },
                    ],
                    year=2026,
                    forecast_version="V1",
                    scope_type="owner",
                    now=NOW,
                )
            )

            self.assertEqual(result.inserted_cells, 1)
            self.assertEqual(result.updated_cells, 0)
            self.assertEqual(result.skipped_cells, 1)
            self.assertEqual(result.recalc_targets, [("部门A", 11)])

            annual_rows = fetch_rows(
                db_path,
                """
                SELECT scope_type, scope_value, subject_id, field_name, field_value
                FROM expense_forecast_annual_entry
                """,
            )
            self.assertEqual([dict(row) for row in annual_rows], [
                {
                    "scope_type": "owner",
                    "scope_value": "部门A",
                    "subject_id": 11,
                    "field_name": "business_submission",
                    "field_value": 300.0,
                }
            ])

    def test_apply_workflow_recalculates_targets_and_returns_preview_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)
            source = FakeImportApplyWorkflowSource()

            result = asyncio.run(
                import_apply_module.apply_expense_forecast_import_rows_with_recalculation(
                    db_path=db_path,
                    rows=[
                        {
                            "scope_value": "部门A",
                            "subject_id": 11,
                            "field_name": "business_submission",
                            "month": None,
                            "value": 300.0,
                            "action": "inserted",
                        },
                        {
                            "scope_value": "部门A",
                            "subject_id": 12,
                            "field_name": "month_forecast",
                            "month": 5,
                            "value": 0.0,
                            "action": "skipped",
                        },
                    ],
                    year=2026,
                    forecast_version="V1",
                    scope_type="owner",
                    scope_value="部门A",
                    group_name="",
                    import_mode="append",
                    skipped_cells=2,
                    error_cells=1,
                    source=source,
                    now=NOW,
                )
            )

            self.assertEqual(result.inserted_cells, 1)
            self.assertEqual(result.updated_cells, 0)
            self.assertEqual(result.skipped_cells, 2)
            self.assertEqual(result.error_cells, 1)
            self.assertEqual(result.affected_cells, 1)
            self.assertEqual(source.recalculate_requests, [(2026, "V1", "部门A", 11)])
            self.assertEqual(source.operation_logs, [
                {
                    "action_type": "IMPORT",
                    "action_desc": "导入费用预测 1 个单元格（append）",
                    "target_table": "expense_forecast_entry / expense_forecast_annual_entry",
                    "affected_rows": 1,
                    "after_data": {
                        "year": 2026,
                        "forecast_version": "V1",
                        "scope_type": "owner",
                        "scope_value": "部门A",
                        "group_name": "",
                        "mode": "append",
                        "inserted_cells": 1,
                        "updated_cells": 0,
                        "skipped_cells": 2,
                        "error_cells": 1,
                    },
                }
            ])


if __name__ == "__main__":
    unittest.main()
