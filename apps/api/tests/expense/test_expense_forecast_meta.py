from __future__ import annotations

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.core.config import settings
import app.services.expense_forecast_meta as expense_forecast_meta_module
from app.services.expense_forecast_meta import (
    build_expense_forecast_leaf_subject_options,
    build_expense_forecast_scope_options,
    load_expense_forecast_meta,
    load_expense_forecast_owner_group_options,
    load_expense_forecast_version_suggestions,
)


class ExpenseForecastMetaTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.common_db = Path(self.tmp.name) / "common.db"

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
            CREATE TABLE expense_forecast_entry (
                forecast_year INTEGER,
                forecast_version TEXT,
                update_time TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO dept_account(dept_code, parent_code, dept_name, level, entity_name) VALUES (?, ?, ?, ?, ?)",
            [
                ("G1", None, "个人金融事业群", 1, "微众银行"),
                ("G2", None, "科技子", 1, "科技子"),
                ("O1", "G1", "部门B", 2, "微众银行"),
                ("O2", "G1", "部门A", 2, "微众银行"),
                ("O3", "G2", "部门C", 2, "科技子"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO budget_subject_catalog(id, parent_id, level_number, subject_name, manage_department, formula_text, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, None, 1, "费用合计", "", None, 1),
                (2, 1, 2, "办公费", "", None, 20),
                (3, 1, 2, "差旅费", "", None, 10),
                (4, None, 1, "公式科目", "", "A+B", 5),
            ],
        )
        conn.executemany(
            "INSERT INTO expense_forecast_entry(forecast_year, forecast_version, update_time) VALUES (?, ?, ?)",
            [
                (2026, "V1", "2026-05-01T00:00:00Z"),
                (2026, "V2", "2026-05-02T00:00:00Z"),
                (2025, "OLD", "2026-05-03T00:00:00Z"),
            ],
        )
        conn.commit()
        conn.close()

    async def test_version_suggestions_use_mysql_for_runtime_common_db(self) -> None:
        class FakePool:
            async def fetch_all(self, sql, params=()):
                self.sql = sql
                self.params = params
                return [
                    {"forecast_version": "V2", "latest_time": "2026-05-02T00:00:00Z"},
                    {"forecast_version": "V1", "latest_time": "2026-05-01T00:00:00Z"},
                ]

        fake_pool = FakePool()
        runtime_common_path = Path(settings.data_dir) / "common.db"
        with patch.object(expense_forecast_meta_module, "get_pool", return_value=fake_pool):
            versions = await load_expense_forecast_version_suggestions(
                runtime_common_path,
                year=2026,
                default_version="D0",
            )

        self.assertEqual(versions, ["D0", "V2", "V1"])
        self.assertIn("FROM expense_forecast_entry", fake_pool.sql)
        self.assertIn("forecast_year = %s", fake_pool.sql)
        self.assertEqual(fake_pool.params, (2026,))

    def test_expense_forecast_meta_does_not_import_aiosqlite(self) -> None:
        source = Path(expense_forecast_meta_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)

    def test_scope_options_group_current_department_tree(self) -> None:
        options = build_expense_forecast_scope_options(
            [
                ("科技子", "科技子", "部门C"),
                ("微众银行", "个人金融事业群", "部门B"),
                ("微众银行", "个人金融事业群", "部门A"),
                ("未知实体", "未知事业群", "长部门"),
            ]
        )

        self.assertEqual(
            [item["value"] for item in options["entity_options"]],
            ["微众银行", "科技子", "未知实体"],
        )
        self.assertEqual(
            [item["value"] for item in options["group_options"]],
            ["个人金融事业群", "科技子", "未知事业群"],
        )
        self.assertEqual(
            [item["value"] for item in options["owner_options"]],
            ["部门A", "部门B", "部门C", "长部门"],
        )
        personal_group = options["owner_group_options"][0]
        self.assertEqual(personal_group["group_value"], "个人金融事业群")
        self.assertEqual(
            [item["value"] for item in personal_group["owner_options"]],
            ["部门A", "部门B"],
        )

    def test_leaf_subject_options_skip_parent_and_formula_rows(self) -> None:
        rows = [
            {"id": 1, "subject_name": "费用合计", "formula_text": None, "sort_order": 1, "is_leaf": False},
            {"id": 2, "subject_name": "办公费", "formula_text": None, "sort_order": 20, "is_leaf": True},
            {"id": 3, "subject_name": "差旅费", "formula_text": None, "sort_order": 10, "is_leaf": True},
            {"id": 4, "subject_name": "公式科目", "formula_text": "A+B", "sort_order": 5, "is_leaf": True},
        ]

        self.assertEqual(
            build_expense_forecast_leaf_subject_options(rows),
            [{"id": 3, "label": "差旅费"}, {"id": 2, "label": "办公费"}],
        )

    async def test_load_meta_returns_current_filters_leaf_subjects_and_version_suggestions(self) -> None:
        self.setup_common_db()

        meta = await load_expense_forecast_meta(
            self.common_db,
            year=2026,
            default_version="D0",
        )

        self.assertEqual(meta["default_year"], 2026)
        self.assertEqual(meta["default_version"], "D0")
        self.assertEqual(meta["version_suggestions"], ["D0", "V2", "V1"])
        self.assertEqual(
            [item["value"] for item in meta["entity_options"]],
            ["微众银行", "科技子"],
        )
        self.assertEqual(
            [item["label"] for item in meta["leaf_subject_options"]],
            ["差旅费", "办公费"],
        )

        owner_group_options = await load_expense_forecast_owner_group_options(self.common_db)
        self.assertEqual(owner_group_options[0]["group_value"], "个人金融事业群")
        self.assertEqual(
            [item["value"] for item in owner_group_options[0]["owner_options"]],
            ["部门A", "部门B"],
        )


if __name__ == "__main__":
    unittest.main()
