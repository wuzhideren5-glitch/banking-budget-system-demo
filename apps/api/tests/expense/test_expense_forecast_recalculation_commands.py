from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.db_bootstrap.expense import EXPENSE_FORECAST_SCHEMA
import app.services.expense_forecast_recalculation_commands as module
from app.services.expense_forecast_recalculation_commands import (
    ExpenseForecastRecalculatedMonth,
    save_expense_forecast_recalculation_results,
)


NOW = "2026-06-01T12:00:00Z"


def init_db(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("CREATE TABLE budget_subject_catalog (id INTEGER PRIMARY KEY)")
        db.executemany("INSERT INTO budget_subject_catalog(id) VALUES (?)", [(11,), (12,)])
        db.executescript(EXPENSE_FORECAST_SCHEMA)
        db.executemany(
            """
            INSERT INTO expense_forecast_rule(
              id, forecast_year, forecast_version, owner_name, subject_id, scheme_code,
              enabled, allow_manual_override, auto_refresh_enabled, manual_recalc_enabled,
              metric_source_priority, effective_from_month, effective_to_month, priority,
              created_at, updated_at
            ) VALUES (?, 2026, 'V1', '部门A', ?, 'RESIDUAL_ALLOC', 1, 1, 1, 1, 'metric_first', 1, 12, 100, ?, ?)
            """,
            [(7, 11, NOW, NOW), (8, 12, NOW, NOW)],
        )
        db.execute(
            """
            INSERT INTO expense_forecast_override(
              forecast_year, forecast_version, owner_name, subject_id, month, rule_id,
              system_value, override_value, override_reason, operator_name, created_at, updated_at
            ) VALUES (2026, 'V1', '部门A', 11, 2, 7, 80, 150, '管理调整', '', ?, ?)
            """,
            (NOW, NOW),
        )
        db.commit()


def fetch_rows(path: Path, sql: str) -> list[sqlite3.Row]:
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return list(db.execute(sql))


class ExpenseForecastRecalculationCommandTests(unittest.TestCase):
    def test_runtime_common_recalculation_writes_use_mysql_pool(self) -> None:
        class FakeCursor:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple]] = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def execute(self, sql, params=()):
                self.calls.append((sql, tuple(params)))

        class FakeConnection:
            def __init__(self) -> None:
                self.cursor_obj = FakeCursor()
                self.begun = 0
                self.committed = 0
                self.rolled_back = 0

            async def begin(self):
                self.begun += 1

            async def commit(self):
                self.committed += 1

            async def rollback(self):
                self.rolled_back += 1

            def cursor(self):
                return self.cursor_obj

        class FakeAcquire:
            def __init__(self, conn: FakeConnection) -> None:
                self.conn = conn

            async def __aenter__(self):
                return self.conn

            async def __aexit__(self, exc_type, exc, tb):
                return None

        class FakePool:
            def __init__(self) -> None:
                self.conn = FakeConnection()

            def acquire(self):
                return FakeAcquire(self.conn)

        async def run() -> FakePool:
            fake_pool = FakePool()
            with patch.object(module, "get_pool", return_value=fake_pool):
                updated = await save_expense_forecast_recalculation_results(
                    db_path=Path(settings.data_dir) / "common.db",
                    year=2026,
                    forecast_version="V1",
                    rows=[
                        ExpenseForecastRecalculatedMonth(
                            owner_name="部门A",
                            subject_id=11,
                            month=2,
                            rule_id=7,
                            calc_value=120.0,
                            calc_basis_json='{"basis":"system"}',
                            has_override=True,
                            override_value=150.0,
                        )
                    ],
                    now=NOW,
                )
            self.assertEqual(updated, 1)
            return fake_pool

        fake_pool = asyncio.run(run())

        self.assertEqual(fake_pool.conn.begun, 1)
        self.assertEqual(fake_pool.conn.committed, 1)
        self.assertEqual(fake_pool.conn.rolled_back, 0)
        executed_sql = "\n".join(sql for sql, _ in fake_pool.conn.cursor_obj.calls)
        self.assertIn("ON DUPLICATE KEY UPDATE", executed_sql)
        self.assertIn("UPDATE expense_forecast_override", executed_sql)
        self.assertIn("%s", executed_sql)
        self.assertNotIn("ON CONFLICT", executed_sql)
        self.assertNotIn("PRAGMA foreign_keys", executed_sql)

    def test_recalculation_commands_do_not_import_aiosqlite(self) -> None:
        source = Path(module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)

    def test_saves_calc_results_and_preserves_override_final_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)

            updated_cells = asyncio.run(
                save_expense_forecast_recalculation_results(
                    db_path=db_path,
                    year=2026,
                    forecast_version="V1",
                    rows=[
                        ExpenseForecastRecalculatedMonth(
                            owner_name="部门A",
                            subject_id=11,
                            month=2,
                            rule_id=7,
                            calc_value=120.0,
                            calc_basis_json='{"basis":"system"}',
                            has_override=True,
                            override_value=150.0,
                        ),
                        ExpenseForecastRecalculatedMonth(
                            owner_name="部门A",
                            subject_id=12,
                            month=3,
                            rule_id=8,
                            calc_value=220.0,
                            calc_basis_json='{"basis":"system"}',
                        ),
                    ],
                    now=NOW,
                )
            )

            self.assertEqual(updated_cells, 2)
            calc_rows = fetch_rows(
                db_path,
                """
                SELECT owner_name, subject_id, month, rule_id, calc_value, calc_basis_json
                FROM expense_forecast_calc_result
                ORDER BY subject_id, month
                """,
            )
            self.assertEqual([dict(row) for row in calc_rows], [
                {
                    "owner_name": "部门A",
                    "subject_id": 11,
                    "month": 2,
                    "rule_id": 7,
                    "calc_value": 120.0,
                    "calc_basis_json": '{"basis":"system"}',
                },
                {
                    "owner_name": "部门A",
                    "subject_id": 12,
                    "month": 3,
                    "rule_id": 8,
                    "calc_value": 220.0,
                    "calc_basis_json": '{"basis":"system"}',
                },
            ])

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
                    "forecast_value": 150.0,
                },
                {
                    "scope_type": "owner",
                    "scope_value": "部门A",
                    "subject_id": 12,
                    "month": 3,
                    "forecast_value": 220.0,
                },
            ])

            override_rows = fetch_rows(
                db_path,
                "SELECT subject_id, month, system_value, override_value FROM expense_forecast_override",
            )
            self.assertEqual([dict(row) for row in override_rows], [
                {
                    "subject_id": 11,
                    "month": 2,
                    "system_value": 120.0,
                    "override_value": 150.0,
                }
            ])


if __name__ == "__main__":
    unittest.main()
