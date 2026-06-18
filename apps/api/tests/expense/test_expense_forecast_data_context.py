from __future__ import annotations

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.core.config import settings
import app.services.expense_forecast_data_context as module
from app.services.expense_forecast_data_context import (
    ExpenseForecastDataContextError,
    build_expense_forecast_effective_manage_departments,
    build_expense_forecast_subject_lookup,
    load_expense_forecast_actual_cutoff_month,
    load_expense_forecast_actual_map,
    load_expense_forecast_annual_budget_map,
    load_expense_forecast_annual_input_map,
    load_expense_forecast_budget_subject_rows,
    load_expense_forecast_forecast_map,
    load_expense_forecast_manage_department_map,
    load_expense_forecast_scope_rows,
    resolve_expense_forecast_scope_owners,
)


class ExpenseForecastDataContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.common_db = Path(self.tmp.name) / "common.db"
        self.budget_db = Path(self.tmp.name) / "budget_2026.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def setup_common_db(self) -> None:
        conn = sqlite3.connect(self.common_db)
        conn.executescript(
            """
            CREATE TABLE dept_account (
                dept_code TEXT PRIMARY KEY,
                parent_code TEXT,
                dept_name TEXT,
                level INTEGER,
                entity_name TEXT
            );
            CREATE TABLE budget_subject_catalog (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER,
                level_number INTEGER NOT NULL,
                subject_name TEXT NOT NULL,
                manage_department TEXT,
                formula_text TEXT,
                sort_order INTEGER DEFAULT 0
            );
            CREATE TABLE expense_actual_detail_raw (
                import_kind TEXT NOT NULL DEFAULT 'current_year_actual',
                owner_name_mapped TEXT,
                budget_subject_mapped TEXT,
                period_ym TEXT,
                amount REAL,
                owner_matched INTEGER,
                subject_matched INTEGER
            );
            CREATE TABLE expense_forecast_entry (
                forecast_year INTEGER,
                forecast_version TEXT,
                scope_type TEXT,
                scope_value TEXT,
                subject_id INTEGER,
                month INTEGER,
                forecast_value REAL
            );
            CREATE TABLE expense_forecast_annual_entry (
                forecast_year INTEGER,
                forecast_version TEXT,
                scope_type TEXT,
                scope_value TEXT,
                subject_id INTEGER,
                field_name TEXT,
                field_value REAL
            );
            """
        )
        conn.executemany(
            "INSERT INTO dept_account(dept_code, parent_code, dept_name, level, entity_name) VALUES (?, ?, ?, ?, ?)",
            [
                ("G1", None, "事业群A", 1, "微众银行"),
                ("G2", None, "事业群B", 1, "科技子"),
                ("O1", "G1", "部门A", 2, "微众银行"),
                ("O2", "G1", "部门B", 2, "微众银行"),
                ("O3", "G2", "部门C", 2, "科技子"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO budget_subject_catalog(id, parent_id, level_number, subject_name, manage_department, formula_text, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, None, 1, "费用合计", "科技管理部", None, 1),
                (2, 1, 2, "差旅费", "", None, 2),
                (3, 1, 2, "办公费", "使用部门", None, 3),
                (4, None, 1, "公式科目", "", "A+B", 4),
            ],
        )
        conn.executemany(
            """
            INSERT INTO expense_actual_detail_raw(
                import_kind, owner_name_mapped, budget_subject_mapped, period_ym,
                amount, owner_matched, subject_matched
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("current_year_actual", "部门A", "差旅费", "2026-01", 100.0, 1, 1),
                ("current_year_actual", "部门A", "差旅费", "2026-01", 50.0, 1, 1),
                ("current_year_actual", "部门A", "差旅费", "2026-13", 999.0, 1, 1),
                ("current_year_actual", "部门X", "差旅费", "2026-02", 500.0, 1, 1),
                ("current_year_actual", "部门A", "差旅费", "2026-07", 888.0, 0, 1),
                ("current_year_actual", "部门A", "差旅费", "2026-08", 888.0, 1, 0),
                ("prior_year_actual", "部门A", "差旅费", "2026-01", 777.0, 1, 1),
            ],
        )
        conn.execute(
            """
            INSERT INTO expense_forecast_entry(forecast_year, forecast_version, scope_type, scope_value, subject_id, month, forecast_value)
            VALUES (2026, 'V1', 'owner', '部门A', 2, 3, 88.0)
            """
        )
        conn.execute(
            """
            INSERT INTO expense_forecast_annual_entry(forecast_year, forecast_version, scope_type, scope_value, subject_id, field_name, field_value)
            VALUES (2026, 'V1', 'owner', '部门A', 2, 'business_submission', 188.0)
            """
        )
        conn.commit()
        conn.close()

    def setup_budget_db(self) -> None:
        conn = sqlite3.connect(self.budget_db)
        conn.executescript(
            """
            CREATE TABLE version (version_id INTEGER PRIMARY KEY);
            CREATE TABLE budget_summary (
                version_id INTEGER,
                budget_actual INTEGER,
                product_code_name TEXT,
                data_code_name TEXT,
                value REAL
            );
            INSERT INTO version(version_id) VALUES (1), (2);
            INSERT INTO budget_summary(version_id, budget_actual, product_code_name, data_code_name, value)
            VALUES
                (2, 0, '部门A-产品', '01 差旅费', 100.125),
                (2, 0, '部门A-产品', '差旅费', 10.0),
                (2, 1, '部门A-产品', '01 差旅费', 999.0),
                (1, 0, '部门A-产品', '01 差旅费', 888.0),
                (2, 0, '部门B-产品', '01 差旅费', 25.0);
            """
        )
        conn.commit()
        conn.close()

    async def test_runtime_common_and_budget_reads_use_mysql_pool(self) -> None:
        class FakePool:
            def __init__(self) -> None:
                self.fetch_all_calls: list[tuple[str, tuple]] = []
                self.fetch_one_calls: list[tuple[str, tuple]] = []

            async def fetch_all(self, sql, params=()):
                self.fetch_all_calls.append((sql, params))
                if "FROM dept_account child" in sql:
                    return [
                        {"entity_name": "微众银行", "group_name": "事业群A", "owner_name": "部门A"},
                        {"entity_name": "微众银行", "group_name": "事业群A", "owner_name": "部门B"},
                    ]
                if "FROM budget_subject_catalog c" in sql:
                    return [
                        {
                            "id": 1,
                            "parent_id": None,
                            "level_number": 1,
                            "subject_name": "费用合计",
                            "manage_department": "科技管理部",
                            "formula_text": None,
                            "sort_order": 1,
                            "has_children": 1,
                        },
                        {
                            "id": 2,
                            "parent_id": 1,
                            "level_number": 2,
                            "subject_name": "差旅费",
                            "manage_department": "",
                            "formula_text": None,
                            "sort_order": 2,
                            "has_children": 0,
                        },
                    ]
                if "SELECT subject_name, manage_department" in sql:
                    return [{"subject_name": "费用合计", "manage_department": "科技管理部"}]
                if "FROM expense_actual_detail_raw" in sql and "MAX" not in sql:
                    return [{"owner_name_mapped": "部门A", "budget_subject_mapped": "差旅费", "month": 1, "amount": 150.0}]
                if "FROM expense_forecast_entry" in sql:
                    return [{"scope_value": "部门A", "subject_id": 2, "month": 3, "forecast_value": 88.0}]
                if "FROM expense_forecast_annual_entry" in sql:
                    return [{"scope_value": "部门A", "subject_id": 2, "field_name": "business_submission", "field_value": 188.0}]
                if "FROM budget_summary" in sql:
                    return [
                        {"product_code_name": "部门A-产品", "data_code_name": "01 差旅费", "value": 100.125},
                        {"product_code_name": "部门A-产品", "data_code_name": "差旅费", "value": 10.0},
                    ]
                raise AssertionError(sql)

            async def fetch_one(self, sql, params=()):
                self.fetch_one_calls.append((sql, params))
                if "MAX" in sql:
                    return {"cutoff_month": 2}
                if "FROM version" in sql:
                    return {"version_id": 2026000003}
                raise AssertionError(sql)

        fake_pool = FakePool()
        runtime_common = Path(settings.data_dir) / "common.db"
        runtime_budget = Path(settings.data_dir) / "budget_2026.db"

        with patch.object(module, "get_pool", return_value=fake_pool):
            scope_rows = await load_expense_forecast_scope_rows(runtime_common)
            subject_rows = await load_expense_forecast_budget_subject_rows(runtime_common)
            manage_map = await load_expense_forecast_manage_department_map(runtime_common)
            actual_map = await load_expense_forecast_actual_map(runtime_common, year=2026, owner_names=["部门A"])
            cutoff = await load_expense_forecast_actual_cutoff_month(runtime_common, year=2026)
            forecast_map = await load_expense_forecast_forecast_map(
                runtime_common,
                year=2026,
                forecast_version="V1",
                owner_names=["部门A"],
            )
            annual_input_map = await load_expense_forecast_annual_input_map(
                runtime_common,
                year=2026,
                forecast_version="V1",
                owner_names=["部门A"],
            )
            annual_budget_map = await load_expense_forecast_annual_budget_map(
                runtime_budget,
                owner_names=["部门A"],
            )

        self.assertEqual(scope_rows[0], ("微众银行", "事业群A", "部门A"))
        self.assertTrue(subject_rows[1]["is_leaf"])
        self.assertEqual(manage_map, {"费用合计": "科技管理部"})
        self.assertEqual(actual_map, {("部门A", "差旅费", 1): 150.0})
        self.assertEqual(cutoff, 2)
        self.assertEqual(forecast_map, {("部门A", 2, 3): 88.0})
        self.assertEqual(annual_input_map, {("部门A", 2, "business_submission"): 188.0})
        self.assertEqual(annual_budget_map, {("部门A", "差旅费"): 110.12})
        self.assertEqual(fake_pool.fetch_one_calls[-1][1], (2026,))
        budget_sql, budget_params = fake_pool.fetch_all_calls[-1]
        self.assertIn("FROM budget_summary", budget_sql)
        self.assertIn("budget_year = %s", budget_sql)
        self.assertEqual(budget_params, (2026000003, 2026))

    def test_data_context_does_not_import_aiosqlite(self) -> None:
        source = Path(module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)

    async def test_scope_rows_and_owner_resolution_use_current_department_tree(self) -> None:
        self.setup_common_db()

        rows = await load_expense_forecast_scope_rows(self.common_db)

        self.assertIn(("微众银行", "事业群A", "部门A"), rows)
        self.assertEqual(
            resolve_expense_forecast_scope_owners(rows, scope_type="group", scope_value="事业群A"),
            ["部门A", "部门B"],
        )
        self.assertEqual(
            resolve_expense_forecast_scope_owners(rows, scope_type="entity", scope_value="科技子"),
            ["部门C"],
        )
        with self.assertRaisesRegex(ExpenseForecastDataContextError, "没有可用"):
            resolve_expense_forecast_scope_owners(rows, scope_type="owner", scope_value="不存在部门")

    async def test_subject_rows_and_effective_manage_departments_are_inherited(self) -> None:
        self.setup_common_db()

        rows = await load_expense_forecast_budget_subject_rows(self.common_db)
        manage_map = await load_expense_forecast_manage_department_map(self.common_db)
        effective_by_id, effective_by_name = build_expense_forecast_effective_manage_departments(rows, manage_map)
        by_id, by_name = build_expense_forecast_subject_lookup(rows)

        self.assertFalse(by_id[1]["is_leaf"])
        self.assertTrue(by_id[2]["is_leaf"])
        self.assertEqual(effective_by_id[1], "科技业务")
        self.assertEqual(effective_by_id[2], "科技业务")
        self.assertEqual(effective_by_id[3], "科技业务")
        self.assertEqual(effective_by_name["差旅费"], ["科技业务"])
        self.assertEqual(by_name["差旅费"][0]["id"], 2)

    async def test_actual_forecast_and_annual_input_maps_use_current_owner_subject_grain(self) -> None:
        self.setup_common_db()

        actual_map = await load_expense_forecast_actual_map(
            self.common_db,
            year=2026,
            owner_names=["部门A"],
        )
        forecast_map = await load_expense_forecast_forecast_map(
            self.common_db,
            year=2026,
            forecast_version="V1",
            owner_names=["部门A"],
        )
        annual_input_map = await load_expense_forecast_annual_input_map(
            self.common_db,
            year=2026,
            forecast_version="V1",
            owner_names=["部门A"],
        )

        self.assertEqual(actual_map, {("部门A", "差旅费", 1): 150.0})
        self.assertEqual(forecast_map, {("部门A", 2, 3): 88.0})
        self.assertEqual(annual_input_map, {("部门A", 2, "business_submission"): 188.0})

    async def test_actual_cutoff_month_uses_current_matched_valid_actual_rows(self) -> None:
        self.setup_common_db()

        cutoff_month = await load_expense_forecast_actual_cutoff_month(
            self.common_db,
            year=2026,
        )
        missing_year = await load_expense_forecast_actual_cutoff_month(
            self.common_db,
            year=2025,
        )

        self.assertEqual(cutoff_month, 2)
        self.assertEqual(missing_year, 0)

    async def test_actual_map_does_not_use_retired_monthly_snapshot_fallback(self) -> None:
        self.setup_common_db()

        missing_owner = await load_expense_forecast_actual_map(
            self.common_db,
            year=2026,
            owner_names=["部门B"],
        )
        missing_year = await load_expense_forecast_actual_map(
            self.common_db,
            year=2025,
            owner_names=["部门A"],
        )

        self.assertEqual(missing_owner, {})
        self.assertEqual(missing_year, {})

    async def test_annual_budget_map_reads_latest_budget_version_and_strips_subject_prefix(self) -> None:
        self.setup_budget_db()

        annual_budget_map = await load_expense_forecast_annual_budget_map(
            self.budget_db,
            owner_names=["部门A"],
        )

        self.assertEqual(annual_budget_map, {("部门A", "差旅费"): 110.12})


if __name__ == "__main__":
    unittest.main()
