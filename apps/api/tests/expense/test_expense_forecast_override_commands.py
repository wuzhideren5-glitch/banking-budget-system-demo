from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
import unittest

from app.db_bootstrap.expense import EXPENSE_FORECAST_SCHEMA
from app.services import expense_forecast_override_commands as override_module
from app.services.expense_forecast_override_commands import (
    delete_expense_forecast_override,
    save_expense_forecast_override,
)


NOW = "2026-06-01T12:00:00Z"


def init_db(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("CREATE TABLE budget_subject_catalog (id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO budget_subject_catalog(id) VALUES (11)")
        db.executescript(EXPENSE_FORECAST_SCHEMA)
        db.execute(
            """
            INSERT INTO expense_forecast_rule(
              id, forecast_year, forecast_version, owner_name, subject_id, scheme_code,
              enabled, allow_manual_override, auto_refresh_enabled, manual_recalc_enabled,
              metric_source_priority, effective_from_month, effective_to_month, priority,
              created_at, updated_at
            ) VALUES (7, 2026, 'V1', '部门A', 11, 'RESIDUAL_ALLOC', 1, 1, 1, 1, 'metric_first', 1, 12, 100, ?, ?)
            """,
            (NOW, NOW),
        )
        db.commit()


def fetch_rows(path: Path, sql: str) -> list[sqlite3.Row]:
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return list(db.execute(sql))


class FakeOverrideWorkflowSource:
    def __init__(self, *, allow_manual_override: bool = True) -> None:
        self.allow_manual_override = allow_manual_override
        self.requests: list[tuple[str, int, str, tuple[str, ...]]] = []

    async def load_rule_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.requests.append(("rule", year, forecast_version, tuple(owner_names)))
        return {
            ("部门A", 11): {
                "id": 7,
                "allow_manual_override": self.allow_manual_override,
            }
        }

    async def load_calc_result_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.requests.append(("calc", year, forecast_version, tuple(owner_names)))
        return {
            ("部门A", 11, 4): {
                "calc_value": 120.0,
            }
        }

    async def load_actual_cutoff_month(self, year: int) -> int:
        self.requests.append(("cutoff", year, "", ()))
        return 3


class ExpenseForecastOverrideCommandTests(unittest.TestCase):
    def test_save_override_writes_override_and_final_forecast_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)

            asyncio.run(
                save_expense_forecast_override(
                    db_path=db_path,
                    year=2026,
                    forecast_version="V1",
                    owner_name="部门A",
                    subject_id=11,
                    month=4,
                    rule_id=7,
                    system_value=120.0,
                    override_value=150.0,
                    override_reason="管理调整",
                    now=NOW,
                )
            )

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
                    "subject_id": 11,
                    "month": 4,
                    "rule_id": 7,
                    "system_value": 120.0,
                    "override_value": 150.0,
                    "override_reason": "管理调整",
                }
            ])
            forecast_rows = fetch_rows(
                db_path,
                "SELECT scope_type, scope_value, subject_id, month, forecast_value FROM expense_forecast_entry",
            )
            self.assertEqual([dict(row) for row in forecast_rows], [
                {
                    "scope_type": "owner",
                    "scope_value": "部门A",
                    "subject_id": 11,
                    "month": 4,
                    "forecast_value": 150.0,
                }
            ])

    def test_delete_override_restores_system_forecast_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)
            asyncio.run(
                save_expense_forecast_override(
                    db_path=db_path,
                    year=2026,
                    forecast_version="V1",
                    owner_name="部门A",
                    subject_id=11,
                    month=4,
                    rule_id=7,
                    system_value=120.0,
                    override_value=150.0,
                    override_reason="管理调整",
                    now=NOW,
                )
            )

            asyncio.run(
                delete_expense_forecast_override(
                    db_path=db_path,
                    year=2026,
                    forecast_version="V1",
                    owner_name="部门A",
                    subject_id=11,
                    month=4,
                    restored_value=120.0,
                    now=NOW,
                )
            )

            self.assertEqual(fetch_rows(db_path, "SELECT * FROM expense_forecast_override"), [])
            forecast_rows = fetch_rows(
                db_path,
                "SELECT scope_type, scope_value, subject_id, month, forecast_value FROM expense_forecast_entry",
            )
            self.assertEqual([dict(row) for row in forecast_rows], [
                {
                    "scope_type": "owner",
                    "scope_value": "部门A",
                    "subject_id": 11,
                    "month": 4,
                    "forecast_value": 120.0,
                }
            ])

    def test_save_override_workflow_checks_rule_and_uses_system_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)
            source = FakeOverrideWorkflowSource()

            result = asyncio.run(
                override_module.save_expense_forecast_override_with_rule_check(
                    db_path=db_path,
                    year=2026,
                    forecast_version="V1",
                    owner_name="部门A",
                    subject_id=11,
                    month=4,
                    override_value=150.0,
                    override_reason="管理调整",
                    source=source,
                    now=NOW,
                )
            )

            self.assertEqual(result.actual_cutoff_month, 3)
            self.assertEqual(
                source.requests,
                [
                    ("rule", 2026, "V1", ("部门A",)),
                    ("calc", 2026, "V1", ("部门A",)),
                    ("cutoff", 2026, "", ()),
                ],
            )
            override_rows = fetch_rows(
                db_path,
                "SELECT rule_id, system_value, override_value FROM expense_forecast_override",
            )
            self.assertEqual([dict(row) for row in override_rows], [
                {"rule_id": 7, "system_value": 120.0, "override_value": 150.0}
            ])

    def test_delete_override_workflow_restores_system_value_from_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)
            source = FakeOverrideWorkflowSource()
            asyncio.run(
                save_expense_forecast_override(
                    db_path=db_path,
                    year=2026,
                    forecast_version="V1",
                    owner_name="部门A",
                    subject_id=11,
                    month=4,
                    rule_id=7,
                    system_value=120.0,
                    override_value=150.0,
                    override_reason="管理调整",
                    now=NOW,
                )
            )

            asyncio.run(
                override_module.delete_expense_forecast_override_with_restore(
                    db_path=db_path,
                    year=2026,
                    forecast_version="V1",
                    owner_name="部门A",
                    subject_id=11,
                    month=4,
                    source=source,
                    now=NOW,
                )
            )

            self.assertEqual(fetch_rows(db_path, "SELECT * FROM expense_forecast_override"), [])
            forecast_rows = fetch_rows(
                db_path,
                "SELECT forecast_value FROM expense_forecast_entry WHERE scope_value = '部门A' AND subject_id = 11 AND month = 4",
            )
            self.assertEqual([dict(row) for row in forecast_rows], [{"forecast_value": 120.0}])


if __name__ == "__main__":
    unittest.main()
