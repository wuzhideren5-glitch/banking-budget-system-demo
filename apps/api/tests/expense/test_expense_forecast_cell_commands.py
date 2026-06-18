from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.db_bootstrap.expense import EXPENSE_FORECAST_SCHEMA
from app.services import expense_forecast_cell_commands as cell_module
from app.services.expense_forecast_cell_commands import upsert_expense_forecast_cell_value


NOW = "2026-06-01T12:00:00Z"


def init_db(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("CREATE TABLE budget_subject_catalog (id INTEGER PRIMARY KEY)")
        db.executemany("INSERT INTO budget_subject_catalog(id) VALUES (?)", [(11,), (12,)])
        db.executescript(EXPENSE_FORECAST_SCHEMA)
        db.commit()


def fetch_rows(path: Path, sql: str) -> list[sqlite3.Row]:
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return list(db.execute(sql))


class FakeCellWorkflowSource:
    def __init__(self, *, cutoff_month: int = 1, auto_refresh_enabled: bool = False) -> None:
        self.cutoff_month = cutoff_month
        self.auto_refresh_enabled = auto_refresh_enabled
        self.recalculate_requests: list[tuple[int, str, str, int]] = []
        self.requests: list[tuple[str, int, str, tuple[str, ...]]] = []
        self.operation_logs: list[dict] = []

    async def load_subject_lookup(self) -> tuple[dict[int, dict], dict[str, list[dict]]]:
        return {
            11: {
                "id": 11,
                "parent_id": None,
                "subject_name": "差旅费",
                "is_leaf": True,
                "formula_text": "",
            },
            12: {
                "id": 12,
                "parent_id": None,
                "subject_name": "父科目",
                "is_leaf": False,
                "formula_text": "",
            },
        }, {}

    async def load_manage_department_map(self) -> dict[str, str]:
        return {"差旅费": "部门A"}

    async def load_actual_cutoff_month(self, year: int) -> int:
        self.requests.append(("cutoff", year, "", ()))
        return self.cutoff_month

    async def load_rule_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.requests.append(("rule", year, forecast_version, tuple(owner_names)))
        return {
            ("部门A", 11): {
                "id": 7,
                "auto_refresh_enabled": self.auto_refresh_enabled,
            }
        }

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


class ExpenseForecastCellCommandTests(unittest.TestCase):
    def test_runtime_common_cell_writes_use_mysql_pool(self) -> None:
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
            with patch.object(cell_module, "get_pool", return_value=fake_pool):
                month_result = await upsert_expense_forecast_cell_value(
                    db_path=Path(settings.data_dir) / "common.db",
                    year=2026,
                    forecast_version="V1",
                    scope_type="owner",
                    scope_value="部门A",
                    subject_id=11,
                    field_name="month_forecast",
                    month=2,
                    value=123.0,
                    now=NOW,
                )
                annual_result = await upsert_expense_forecast_cell_value(
                    db_path=Path(settings.data_dir) / "common.db",
                    year=2026,
                    forecast_version="V1",
                    scope_type="owner",
                    scope_value="部门A",
                    subject_id=11,
                    field_name="business_submission",
                    month=None,
                    value=456.0,
                    now=NOW,
                )
            self.assertEqual(month_result.mode, "manual")
            self.assertEqual(annual_result.mode, "annual")
            return fake_pool

        fake_pool = asyncio.run(run())

        self.assertEqual(fake_pool.conn.begun, 2)
        self.assertEqual(fake_pool.conn.committed, 2)
        self.assertEqual(fake_pool.conn.rolled_back, 0)
        executed_sql = "\n".join(sql for sql, _ in fake_pool.conn.cursor_obj.calls)
        self.assertIn("INSERT INTO expense_forecast_entry", executed_sql)
        self.assertIn("DELETE FROM expense_forecast_override", executed_sql)
        self.assertIn("INSERT INTO expense_forecast_annual_entry", executed_sql)
        self.assertIn("ON DUPLICATE KEY UPDATE", executed_sql)
        self.assertIn("%s", executed_sql)
        self.assertNotIn("ON CONFLICT", executed_sql)
        self.assertNotIn("PRAGMA foreign_keys", executed_sql)

    def test_cell_commands_do_not_import_aiosqlite(self) -> None:
        source = Path(cell_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)

    def test_month_cell_upsert_writes_manual_value_and_clears_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)
            with sqlite3.connect(db_path) as db:
                db.execute(
                    """
                    INSERT INTO expense_forecast_override(
                      forecast_year, forecast_version, owner_name, subject_id, month, rule_id,
                      system_value, override_value, override_reason, operator_name, created_at, updated_at
                    ) VALUES (2026, 'V1', '部门A', 11, 2, NULL, 80, 90, '旧覆盖', '', ?, ?)
                    """,
                    (NOW, NOW),
                )
                db.commit()

            result = asyncio.run(
                upsert_expense_forecast_cell_value(
                    db_path=db_path,
                    year=2026,
                    forecast_version="V1",
                    scope_type="owner",
                    scope_value="部门A",
                    subject_id=11,
                    field_name="month_forecast",
                    month=2,
                    value=123.0,
                    now=NOW,
                )
            )

            self.assertEqual(result.mode, "manual")
            forecast_rows = fetch_rows(
                db_path,
                "SELECT scope_type, scope_value, subject_id, month, forecast_value FROM expense_forecast_entry",
            )
            self.assertEqual([dict(row) for row in forecast_rows], [
                {
                    "scope_type": "owner",
                    "scope_value": "部门A",
                    "subject_id": 11,
                    "month": 2,
                    "forecast_value": 123.0,
                }
            ])
            self.assertEqual(fetch_rows(db_path, "SELECT * FROM expense_forecast_override"), [])

    def test_annual_cell_upsert_writes_annual_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)

            result = asyncio.run(
                upsert_expense_forecast_cell_value(
                    db_path=db_path,
                    year=2026,
                    forecast_version="V1",
                    scope_type="owner",
                    scope_value="部门A",
                    subject_id=11,
                    field_name="business_submission",
                    month=None,
                    value=456.0,
                    now=NOW,
                )
            )

            self.assertEqual(result.mode, "annual")
            annual_rows = fetch_rows(
                db_path,
                "SELECT scope_type, scope_value, subject_id, field_name, field_value FROM expense_forecast_annual_entry",
            )
            self.assertEqual([dict(row) for row in annual_rows], [
                {
                    "scope_type": "owner",
                    "scope_value": "部门A",
                    "subject_id": 11,
                    "field_name": "business_submission",
                    "field_value": 456.0,
                }
            ])

    def test_cell_workflow_rejects_non_owner_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)

            with self.assertRaisesRegex(
                cell_module.ExpenseForecastCellWorkflowError,
                "费用预估仅支持在费用归属部门口径下录入",
            ):
                asyncio.run(
                    cell_module.upsert_expense_forecast_cell_with_validation(
                        db_path=db_path,
                        year=2026,
                        forecast_version="V1",
                        scope_type="group",
                        scope_value="事业群A",
                        subject_id=11,
                        field_name="month_forecast",
                        month=2,
                        value=123.0,
                        source=FakeCellWorkflowSource(),
                        now=NOW,
                    )
                )

    def test_cell_workflow_validates_subject_and_upserts_month_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)
            source = FakeCellWorkflowSource(cutoff_month=1)

            result = asyncio.run(
                cell_module.upsert_expense_forecast_cell_with_validation(
                    db_path=db_path,
                    year=2026,
                    forecast_version="V1",
                    scope_type="owner",
                    scope_value="部门A",
                    subject_id=11,
                    field_name="month_forecast",
                    month=2,
                    value=123.0,
                    source=source,
                    now=NOW,
                )
            )

            self.assertEqual(result.mode, "manual")
            self.assertEqual(result.actual_cutoff_month, 1)
            self.assertEqual(result.subject_name, "差旅费")
            self.assertEqual(result.field_label, "M2")
            self.assertFalse(result.recalculated)
            self.assertEqual(
                source.requests,
                [
                    ("cutoff", 2026, "", ()),
                    ("rule", 2026, "V1", ("部门A",)),
                ],
            )
            forecast_rows = fetch_rows(
                db_path,
                "SELECT scope_type, scope_value, subject_id, month, forecast_value FROM expense_forecast_entry",
            )
            self.assertEqual([dict(row) for row in forecast_rows], [
                {
                    "scope_type": "owner",
                    "scope_value": "部门A",
                    "subject_id": 11,
                    "month": 2,
                    "forecast_value": 123.0,
                }
            ])
            self.assertEqual(source.operation_logs, [
                {
                    "action_type": "UPSERT",
                    "action_desc": "写入费用预测 差旅费 M2",
                    "target_table": "expense_forecast_entry",
                    "affected_rows": 1,
                    "after_data": {
                        "year": 2026,
                        "forecast_version": "V1",
                        "scope_type": "owner",
                        "scope_value": "部门A",
                        "subject_id": 11,
                        "field_name": "month_forecast",
                        "month": 2,
                        "value": 123.0,
                    },
                }
            ])

    def test_cell_workflow_recalculates_when_annual_field_has_auto_refresh_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)
            source = FakeCellWorkflowSource(auto_refresh_enabled=True)

            result = asyncio.run(
                cell_module.upsert_expense_forecast_cell_with_validation(
                    db_path=db_path,
                    year=2026,
                    forecast_version="V1",
                    scope_type="owner",
                    scope_value="部门A",
                    subject_id=11,
                    field_name="capital_advice",
                    month=None,
                    value=456.0,
                    source=source,
                    now=NOW,
                )
            )

            self.assertEqual(result.mode, "annual")
            self.assertEqual(result.field_label, "资划建议")
            self.assertTrue(result.recalculated)
            self.assertEqual(source.recalculate_requests, [(2026, "V1", "部门A", 11)])


if __name__ == "__main__":
    unittest.main()
