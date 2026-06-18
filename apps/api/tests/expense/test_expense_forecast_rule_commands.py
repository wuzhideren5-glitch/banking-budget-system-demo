from __future__ import annotations

import asyncio
import importlib
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.db_bootstrap.expense import EXPENSE_FORECAST_SCHEMA
import app.services.expense_forecast_rule_commands as module
from app.services.expense_forecast_rule_commands import (
    delete_expense_forecast_rule_definition,
    save_expense_forecast_rule_definition,
)


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


class ExpenseForecastRuleCommandTests(unittest.TestCase):
    def command_module(self):
        return importlib.import_module("app.services.expense_forecast_rule_commands")

    def test_runtime_common_writes_use_mysql_pool(self) -> None:
        class FakeCursor:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple]] = []
                self.lastrowid = 0
                self.rowcount = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def execute(self, sql, params=()):
                self.calls.append((sql, tuple(params)))
                if "INSERT INTO expense_forecast_rule(" in sql:
                    self.lastrowid = 123
                    self.rowcount = 1
                elif "DELETE FROM expense_forecast_rule" in sql:
                    self.rowcount = 1
                else:
                    self.rowcount = 1

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
                saved = await save_expense_forecast_rule_definition(
                    db_path=Path(settings.data_dir) / "common.db",
                    rule={
                        "forecast_year": 2026,
                        "forecast_version": "V1",
                        "owner_name": "部门A",
                        "subject_id": 11,
                        "scheme_code": "METRIC_EXPR",
                        "params": [{"param_key": "expression", "param_value": "a+b"}],
                        "variables": [{"variable_code": "a", "source_type": "metric_tree"}],
                    },
                    rule_id=None,
                    now=NOW,
                )
                self.assertEqual(saved.rule_id, 123)
                deleted = await delete_expense_forecast_rule_definition(
                    db_path=Path(settings.data_dir) / "common.db",
                    rule_id=123,
                )
                self.assertTrue(deleted)
            return fake_pool

        fake_pool = asyncio.run(run())

        self.assertEqual(fake_pool.conn.begun, 2)
        self.assertEqual(fake_pool.conn.committed, 2)
        self.assertEqual(fake_pool.conn.rolled_back, 0)
        executed_sql = "\n".join(sql for sql, _ in fake_pool.conn.cursor_obj.calls)
        self.assertIn("VALUES (%s", executed_sql)
        self.assertNotIn("VALUES (?,", executed_sql)
        self.assertNotIn("PRAGMA foreign_keys", executed_sql)

    def test_rule_commands_do_not_import_aiosqlite(self) -> None:
        source = Path(module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)

    def test_inserts_rule_params_and_variables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)

            saved = asyncio.run(
                save_expense_forecast_rule_definition(
                    db_path=db_path,
                    rule={
                        "forecast_year": 2026,
                        "forecast_version": "V1",
                        "owner_name": "部门A",
                        "subject_id": 11,
                        "scheme_code": "METRIC_EXPR",
                        "enabled": True,
                        "allow_manual_override": True,
                        "auto_refresh_enabled": True,
                        "manual_recalc_enabled": False,
                        "metric_source_priority": "inline_first",
                        "effective_from_month": 2,
                        "effective_to_month": 12,
                        "priority": 88,
                        "remark": "规则说明",
                        "params": [
                            {
                                "param_group": "metric_expr",
                                "param_key": "expression",
                                "param_value": "a + b",
                                "value_type": "string",
                            }
                        ],
                        "variables": [
                            {
                                "variable_code": "a",
                                "variable_name": "指标A",
                                "source_type": "metric_tree",
                                "source_key": "A01.01.01.001",
                                "source_subkey": "",
                                "default_value": 0.0,
                                "sort_order": 2,
                            }
                        ],
                    },
                    rule_id=None,
                    now=NOW,
                )
            )

            self.assertEqual(saved.rule_id, 1)
            rule_rows = fetch_rows(
                db_path,
                """
                SELECT forecast_year, forecast_version, owner_name, subject_id, scheme_code,
                       enabled, allow_manual_override, auto_refresh_enabled, manual_recalc_enabled,
                       metric_source_priority, effective_from_month, effective_to_month, priority,
                       remark, created_at, updated_at
                FROM expense_forecast_rule
                """,
            )
            self.assertEqual([dict(row) for row in rule_rows], [
                {
                    "forecast_year": 2026,
                    "forecast_version": "V1",
                    "owner_name": "部门A",
                    "subject_id": 11,
                    "scheme_code": "METRIC_EXPR",
                    "enabled": 1,
                    "allow_manual_override": 1,
                    "auto_refresh_enabled": 1,
                    "manual_recalc_enabled": 0,
                    "metric_source_priority": "inline_first",
                    "effective_from_month": 2,
                    "effective_to_month": 12,
                    "priority": 88,
                    "remark": "规则说明",
                    "created_at": NOW,
                    "updated_at": NOW,
                }
            ])
            param_rows = fetch_rows(
                db_path,
                "SELECT rule_id, param_group, param_key, param_value, value_type FROM expense_forecast_rule_param",
            )
            self.assertEqual([dict(row) for row in param_rows], [
                {
                    "rule_id": saved.rule_id,
                    "param_group": "metric_expr",
                    "param_key": "expression",
                    "param_value": "a + b",
                    "value_type": "string",
                }
            ])
            variable_rows = fetch_rows(
                db_path,
                """
                SELECT rule_id, variable_code, variable_name, source_type, source_key,
                       source_subkey, default_value, sort_order
                FROM expense_forecast_rule_variable
                """,
            )
            self.assertEqual([dict(row) for row in variable_rows], [
                {
                    "rule_id": saved.rule_id,
                    "variable_code": "a",
                    "variable_name": "指标A",
                    "source_type": "metric_tree",
                    "source_key": "A01.01.01.001",
                    "source_subkey": None,
                    "default_value": 0.0,
                    "sort_order": 2,
                }
            ])

    def test_updates_rule_and_replaces_params_and_variables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)
            with sqlite3.connect(db_path) as db:
                db.execute("PRAGMA foreign_keys = ON")
                db.execute(
                    """
                    INSERT INTO expense_forecast_rule(
                      id, forecast_year, forecast_version, owner_name, subject_id, scheme_code,
                      enabled, allow_manual_override, auto_refresh_enabled, manual_recalc_enabled,
                      metric_source_priority, effective_from_month, effective_to_month, priority,
                      remark, created_at, updated_at
                    ) VALUES (7, 2026, 'V1', '部门A', 11, 'MANUAL',
                      1, 0, 1, 1, 'metric_first', 1, 12, 100, '旧备注', 'OLD', 'OLD')
                    """
                )
                db.execute(
                    """
                    INSERT INTO expense_forecast_rule_param(rule_id, param_group, param_key, param_value, value_type)
                    VALUES (7, 'common', 'old', '1', 'string')
                    """
                )
                db.execute(
                    """
                    INSERT INTO expense_forecast_rule_variable(
                      rule_id, variable_code, source_type, source_key, sort_order
                    ) VALUES (7, 'old_var', 'constant', '1', 1)
                    """
                )
                db.commit()

            saved = asyncio.run(
                save_expense_forecast_rule_definition(
                    db_path=db_path,
                    rule={
                        "forecast_year": 2026,
                        "forecast_version": "V2",
                        "owner_name": "部门B",
                        "subject_id": 12,
                        "scheme_code": "RESIDUAL_ALLOC",
                        "enabled": False,
                        "allow_manual_override": True,
                        "auto_refresh_enabled": False,
                        "manual_recalc_enabled": True,
                        "metric_source_priority": "metric_first",
                        "effective_from_month": 3,
                        "effective_to_month": 10,
                        "priority": 7,
                        "remark": "",
                        "params": [
                            {
                                "param_group": "",
                                "param_key": "allocation_mode",
                                "param_value": "custom",
                                "value_type": "",
                            }
                        ],
                        "variables": [],
                    },
                    rule_id=7,
                    now=NOW,
                )
            )

            self.assertEqual(saved.rule_id, 7)
            rule_rows = fetch_rows(
                db_path,
                """
                SELECT forecast_version, owner_name, subject_id, scheme_code, enabled,
                       allow_manual_override, auto_refresh_enabled, manual_recalc_enabled,
                       effective_from_month, effective_to_month, priority, remark, created_at, updated_at
                FROM expense_forecast_rule
                WHERE id = 7
                """,
            )
            self.assertEqual([dict(row) for row in rule_rows], [
                {
                    "forecast_version": "V2",
                    "owner_name": "部门B",
                    "subject_id": 12,
                    "scheme_code": "RESIDUAL_ALLOC",
                    "enabled": 0,
                    "allow_manual_override": 1,
                    "auto_refresh_enabled": 0,
                    "manual_recalc_enabled": 1,
                    "effective_from_month": 3,
                    "effective_to_month": 10,
                    "priority": 7,
                    "remark": None,
                    "created_at": "OLD",
                    "updated_at": NOW,
                }
            ])
            param_rows = fetch_rows(
                db_path,
                "SELECT param_group, param_key, param_value, value_type FROM expense_forecast_rule_param WHERE rule_id = 7",
            )
            self.assertEqual([dict(row) for row in param_rows], [
                {
                    "param_group": "common",
                    "param_key": "allocation_mode",
                    "param_value": "custom",
                    "value_type": "string",
                }
            ])
            variable_rows = fetch_rows(
                db_path,
                "SELECT variable_code FROM expense_forecast_rule_variable WHERE rule_id = 7",
            )
            self.assertEqual(variable_rows, [])

    def test_deletes_rule_definition_and_owned_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)
            with sqlite3.connect(db_path) as db:
                db.execute("PRAGMA foreign_keys = ON")
                db.execute(
                    """
                    INSERT INTO expense_forecast_rule(
                      id, forecast_year, forecast_version, owner_name, subject_id, scheme_code,
                      enabled, allow_manual_override, auto_refresh_enabled, manual_recalc_enabled,
                      metric_source_priority, effective_from_month, effective_to_month, priority,
                      remark, created_at, updated_at
                    ) VALUES (9, 2026, 'V1', '部门A', 11, 'MANUAL',
                      1, 0, 1, 1, 'metric_first', 1, 12, 100, NULL, 'OLD', 'OLD')
                    """
                )
                db.execute(
                    """
                    INSERT INTO expense_forecast_rule_param(rule_id, param_group, param_key, param_value, value_type)
                    VALUES (9, 'common', 'amount', '100', 'number')
                    """
                )
                db.execute(
                    """
                    INSERT INTO expense_forecast_rule_variable(
                      rule_id, variable_code, source_type, source_key, sort_order
                    ) VALUES (9, 'amount', 'constant', '100', 1)
                    """
                )
                db.commit()

            deleted = asyncio.run(
                delete_expense_forecast_rule_definition(db_path=db_path, rule_id=9)
            )
            deleted_again = asyncio.run(
                delete_expense_forecast_rule_definition(db_path=db_path, rule_id=9)
            )

            self.assertTrue(deleted)
            self.assertFalse(deleted_again)
            self.assertEqual(fetch_rows(db_path, "SELECT id FROM expense_forecast_rule"), [])
            self.assertEqual(fetch_rows(db_path, "SELECT id FROM expense_forecast_rule_param"), [])
            self.assertEqual(fetch_rows(db_path, "SELECT id FROM expense_forecast_rule_variable"), [])

    def test_delete_rule_workflow_raises_when_rule_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            init_db(db_path)
            module = self.command_module()

            with self.assertRaisesRegex(module.ExpenseForecastRuleDeleteNotFound, "预测规则不存在"):
                asyncio.run(
                    module.delete_expense_forecast_rule_definition_or_raise(
                        db_path=db_path,
                        rule_id=404,
                    )
                )


if __name__ == "__main__":
    unittest.main()
