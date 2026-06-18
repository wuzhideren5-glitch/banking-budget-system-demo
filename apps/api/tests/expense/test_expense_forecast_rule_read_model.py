from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.core.config import settings
import app.services.expense_forecast_rule_read_model as module
from app.services.expense_forecast_rule_read_model import (
    build_enabled_expense_forecast_rule_map,
    load_expense_forecast_calc_result_map,
    load_expense_forecast_override_map,
    load_expense_forecast_rule_identity,
    load_expense_forecast_rule_rows,
)


class ExpenseForecastRuleReadModelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "common.db"
        self.setup_db()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def setup_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE budget_subject_catalog (
                id INTEGER PRIMARY KEY,
                subject_name TEXT NOT NULL
            );
            CREATE TABLE expense_forecast_rule (
                id INTEGER PRIMARY KEY,
                forecast_year INTEGER NOT NULL,
                forecast_version TEXT NOT NULL,
                owner_name TEXT NOT NULL,
                subject_id INTEGER NOT NULL,
                scheme_code TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                allow_manual_override INTEGER NOT NULL,
                auto_refresh_enabled INTEGER NOT NULL,
                manual_recalc_enabled INTEGER NOT NULL,
                metric_source_priority TEXT,
                effective_from_month INTEGER,
                effective_to_month INTEGER,
                priority INTEGER,
                remark TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE expense_forecast_rule_param (
                id INTEGER PRIMARY KEY,
                rule_id INTEGER NOT NULL,
                param_group TEXT,
                param_key TEXT NOT NULL,
                param_value TEXT,
                value_type TEXT
            );
            CREATE TABLE expense_forecast_rule_variable (
                id INTEGER PRIMARY KEY,
                rule_id INTEGER NOT NULL,
                variable_code TEXT NOT NULL,
                variable_name TEXT,
                source_type TEXT NOT NULL,
                source_key TEXT,
                source_subkey TEXT,
                default_value REAL,
                sort_order INTEGER
            );
            CREATE TABLE expense_forecast_calc_result (
                forecast_year INTEGER,
                forecast_version TEXT,
                owner_name TEXT,
                subject_id INTEGER,
                month INTEGER,
                rule_id INTEGER,
                calc_value REAL,
                calc_basis_json TEXT,
                calc_status TEXT
            );
            CREATE TABLE expense_forecast_override (
                forecast_year INTEGER,
                forecast_version TEXT,
                owner_name TEXT,
                subject_id INTEGER,
                month INTEGER,
                rule_id INTEGER,
                system_value REAL,
                override_value REAL,
                override_reason TEXT
            );
            CREATE TABLE org_product_metric_table (
                entity_code TEXT,
                table_name TEXT,
                payload_json TEXT
            );
            INSERT INTO budget_subject_catalog(id, subject_name)
            VALUES (11, '差旅费'), (12, '办公费'), (13, '会议费');
            INSERT INTO expense_forecast_rule(
                id, forecast_year, forecast_version, owner_name, subject_id, scheme_code,
                enabled, allow_manual_override, auto_refresh_enabled, manual_recalc_enabled,
                metric_source_priority, effective_from_month, effective_to_month, priority,
                remark, created_at, updated_at
            )
            VALUES
                (7, 2026, 'V1', '部门B', 12, 'MANUAL', 1, 0, 0, 1, NULL, NULL, NULL, NULL, '', 'c7', 'u7'),
                (5, 2026, 'V1', '部门A', 11, 'RESIDUAL_ALLOC', 1, 1, 1, 1, 'inline_first', 2, 10, 20, '备注', 'c5', 'u5'),
                (6, 2026, 'V1', '部门A', 13, 'METRIC_EXPR', 0, 1, 1, 0, 'metric_first', 1, 12, 10, NULL, 'c6', 'u6'),
                (8, 2025, 'V1', '部门A', 11, 'MANUAL', 1, 0, 0, 0, 'metric_first', 1, 12, 100, NULL, 'c8', 'u8');
            INSERT INTO expense_forecast_rule_param(rule_id, param_group, param_key, param_value, value_type)
            VALUES
                (5, '', 'target_total', '1200', ''),
                (5, 'alloc', 'mode', 'progressive', 'string'),
                (6, 'metric_expr', 'expression', 'A+B', 'string');
            INSERT INTO expense_forecast_rule_variable(
                rule_id, variable_code, variable_name, source_type, source_key, source_subkey, default_value, sort_order
            )
            VALUES
                (5, 'B', NULL, 'constant', NULL, NULL, NULL, 2),
                (5, 'A', '指标A', 'metric_tree', 'A01.01', 'balance', 1.5, 1),
                (6, 'FEE05', '05未确认', 'metric_tree', '05.03', 'A01', 0, 1);
            INSERT INTO expense_forecast_calc_result(
                forecast_year, forecast_version, owner_name, subject_id, month, rule_id, calc_value, calc_basis_json, calc_status
            )
            VALUES
                (2026, 'V1', '部门A', 11, 3, 5, 88.5, '{"ok":true}', NULL),
                (2026, 'V1', '部门B', 12, 4, NULL, 20.0, '', 'stale');
            INSERT INTO expense_forecast_override(
                forecast_year, forecast_version, owner_name, subject_id, month, rule_id, system_value, override_value, override_reason
            )
            VALUES
                (2026, 'V1', '部门A', 11, 3, 5, 88.5, 99.0, '业务调整'),
                (2026, 'V1', '部门B', 12, 4, NULL, 20.0, 22.0, '');
            """
        )
        conn.execute(
            """
            INSERT INTO org_product_metric_table(entity_code, table_name, payload_json)
            VALUES (?, ?, ?)
            """,
            (
                "A01",
                "业务状况表",
                json.dumps(
                    {
                        "metrics": [
                            {
                                "code": "A0110",
                                "name": "管理贷款余额",
                                "data_acct_code": "A01.01",
                                "mapping_status": "MANUAL_CONFIRMED",
                            },
                            {
                                "code": "A010503",
                                "name": "05未确认项",
                                "data_acct_code": "05.03",
                                "mapping_status": "MANUAL_CONFIRMED",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        conn.commit()
        conn.close()

    async def test_runtime_common_reads_use_mysql_pool(self) -> None:
        class FakePool:
            def __init__(self) -> None:
                self.fetch_all_calls: list[tuple[str, tuple]] = []
                self.fetch_one_calls: list[tuple[str, tuple]] = []

            async def fetch_one(self, sql, params=()):
                self.fetch_one_calls.append((sql, params))
                if "FROM expense_forecast_rule" in sql:
                    return {
                        "forecast_year": 2026,
                        "forecast_version": "V1",
                        "owner_name": "部门A",
                        "subject_id": 11,
                    }
                raise AssertionError(sql)

            async def fetch_all(self, sql, params=()):
                self.fetch_all_calls.append((sql, params))
                if "FROM expense_forecast_rule r" in sql:
                    return [
                        {
                            "id": 5,
                            "forecast_year": 2026,
                            "forecast_version": "V1",
                            "owner_name": "部门A",
                            "subject_id": 11,
                            "subject_name": "差旅费",
                            "scheme_code": "RESIDUAL_ALLOC",
                            "enabled": 1,
                            "allow_manual_override": 1,
                            "auto_refresh_enabled": 1,
                            "manual_recalc_enabled": 1,
                            "metric_source_priority": "inline_first",
                            "effective_from_month": 2,
                            "effective_to_month": 10,
                            "priority": 20,
                            "remark": "备注",
                            "created_at": "c5",
                            "updated_at": "u5",
                        }
                    ]
                if "FROM expense_forecast_rule_param" in sql:
                    return [
                        {
                            "rule_id": 5,
                            "param_group": "",
                            "param_key": "target_total",
                            "param_value": "1200",
                            "value_type": "",
                        }
                    ]
                if "FROM expense_forecast_rule_variable" in sql:
                    return [
                        {
                            "rule_id": 5,
                            "variable_code": "A",
                            "variable_name": "指标A",
                            "source_type": "metric_tree",
                            "source_key": "A01.01",
                            "source_subkey": "balance",
                            "default_value": 1.5,
                            "sort_order": 1,
                        }
                    ]
                if "FROM data_account_metric_node" in sql:
                    return [
                        {
                            "node_code": "A01.01",
                            "node_name": "管理贷款余额",
                            "product_code": "A01",
                            "metric_table_name": "业务状况表",
                        }
                    ]
                if "FROM expense_forecast_calc_result" in sql:
                    return [
                        {
                            "owner_name": "部门A",
                            "subject_id": 11,
                            "month": 3,
                            "rule_id": 5,
                            "calc_value": 88.5,
                            "calc_basis_json": '{"ok":true}',
                            "calc_status": None,
                        }
                    ]
                if "FROM expense_forecast_override" in sql:
                    return [
                        {
                            "owner_name": "部门A",
                            "subject_id": 11,
                            "month": 3,
                            "rule_id": 5,
                            "system_value": 88.5,
                            "override_value": 99.0,
                            "override_reason": "业务调整",
                        }
                    ]
                raise AssertionError(sql)

        fake_pool = FakePool()
        runtime_common = Path(settings.data_dir) / "common.db"
        with patch.object(module, "get_pool", return_value=fake_pool):
            identity = await load_expense_forecast_rule_identity(runtime_common, rule_id=5)
            rows = await load_expense_forecast_rule_rows(
                runtime_common,
                year=2026,
                forecast_version="V1",
                owner_names=["部门A"],
            )
            calc_map = await load_expense_forecast_calc_result_map(
                runtime_common,
                year=2026,
                forecast_version="V1",
                owner_names=["部门A"],
            )
            override_map = await load_expense_forecast_override_map(
                runtime_common,
                year=2026,
                forecast_version="V1",
                owner_names=["部门A"],
            )

        self.assertEqual(identity["subject_id"], 11)
        self.assertEqual(rows[0]["params"][0]["param_group"], "common")
        self.assertEqual(rows[0]["variables"][0]["org_product_refs"], ["A01:业务状况表:A01.01 管理贷款余额"])
        self.assertEqual(calc_map[("部门A", 11, 3)]["calc_status"], "ok")
        self.assertEqual(override_map[("部门A", 11, 3)]["override_reason"], "业务调整")
        self.assertTrue(all("%s" in sql or "?" not in sql for sql, _params in fake_pool.fetch_all_calls))
        self.assertEqual(fake_pool.fetch_one_calls[0][1], (5,))

    def test_rule_read_model_does_not_import_aiosqlite(self) -> None:
        source = Path(module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)

    async def test_rule_rows_expand_params_variables_and_defaults(self) -> None:
        rows = await load_expense_forecast_rule_rows(
            self.db_path,
            year=2026,
            forecast_version="V1",
            owner_names=["部门A"],
        )

        self.assertEqual([row["id"] for row in rows], [6, 5])
        disabled_rule = rows[0]
        enabled_rule = rows[1]
        self.assertFalse(disabled_rule["enabled"])
        self.assertEqual(disabled_rule["subject_name"], "会议费")
        self.assertEqual(disabled_rule["variables"][0]["org_product_refs"], ["A01:业务状况表:A010503 05未确认项"])
        self.assertEqual(enabled_rule["subject_name"], "差旅费")
        self.assertEqual(enabled_rule["metric_source_priority"], "inline_first")
        self.assertEqual(enabled_rule["effective_from_month"], 2)
        self.assertEqual(enabled_rule["effective_to_month"], 10)
        self.assertEqual(enabled_rule["priority"], 20)
        self.assertEqual(enabled_rule["remark"], "备注")
        self.assertEqual(
            enabled_rule["params"],
            [
                {
                    "param_group": "common",
                    "param_key": "target_total",
                    "param_value": "1200",
                    "value_type": "string",
                },
                {
                    "param_group": "alloc",
                    "param_key": "mode",
                    "param_value": "progressive",
                    "value_type": "string",
                },
            ],
        )
        self.assertEqual([item["variable_code"] for item in enabled_rule["variables"]], ["A", "B"])
        self.assertEqual(enabled_rule["variables"][0]["default_value"], 1.5)
        self.assertEqual(
            enabled_rule["variables"][0]["org_product_refs"],
            ["A01:业务状况表:A0110 管理贷款余额"],
        )
        self.assertIsNone(enabled_rule["variables"][1]["source_key"])
        self.assertEqual(enabled_rule["variables"][1]["org_product_refs"], [])

    async def test_rule_rows_filter_by_subject_and_build_enabled_map(self) -> None:
        rows = await load_expense_forecast_rule_rows(
            self.db_path,
            year=2026,
            forecast_version="V1",
            subject_id=11,
        )

        self.assertEqual([row["id"] for row in rows], [5])
        rule_map = build_enabled_expense_forecast_rule_map(rows)
        self.assertEqual(list(rule_map.keys()), [("部门A", 11)])
        self.assertEqual(rule_map[("部门A", 11)]["scheme_code"], "RESIDUAL_ALLOC")

    async def test_rule_identity_loads_cross_version_locator(self) -> None:
        identity = await load_expense_forecast_rule_identity(self.db_path, rule_id=8)
        missing = await load_expense_forecast_rule_identity(self.db_path, rule_id=999)

        self.assertEqual(
            identity,
            {
                "forecast_year": 2025,
                "forecast_version": "V1",
                "owner_name": "部门A",
                "subject_id": 11,
            },
        )
        self.assertIsNone(missing)

    async def test_rule_map_excludes_disabled_rows(self) -> None:
        rows = await load_expense_forecast_rule_rows(
            self.db_path,
            year=2026,
            forecast_version="V1",
            owner_names=["部门A"],
        )

        rule_map = build_enabled_expense_forecast_rule_map(rows)

        self.assertEqual(list(rule_map.keys()), [("部门A", 11)])

    async def test_calc_result_and_override_maps_use_owner_subject_month_keys(self) -> None:
        calc_map = await load_expense_forecast_calc_result_map(
            self.db_path,
            year=2026,
            forecast_version="V1",
            owner_names=["部门A", "部门B"],
        )
        override_map = await load_expense_forecast_override_map(
            self.db_path,
            year=2026,
            forecast_version="V1",
            owner_names=["部门A", "部门B"],
        )

        self.assertEqual(
            calc_map[("部门A", 11, 3)],
            {
                "rule_id": 5,
                "calc_value": 88.5,
                "calc_basis_json": '{"ok":true}',
                "calc_status": "ok",
            },
        )
        self.assertEqual(calc_map[("部门B", 12, 4)]["calc_status"], "stale")
        self.assertIsNone(calc_map[("部门B", 12, 4)]["rule_id"])
        self.assertEqual(
            override_map[("部门A", 11, 3)],
            {
                "rule_id": 5,
                "system_value": 88.5,
                "override_value": 99.0,
                "override_reason": "业务调整",
            },
        )
        self.assertIsNone(override_map[("部门B", 12, 4)]["override_reason"])

    async def test_empty_owner_names_short_circuit_private_state_maps(self) -> None:
        self.assertEqual(
            await load_expense_forecast_calc_result_map(
                self.db_path,
                year=2026,
                forecast_version="V1",
                owner_names=[],
            ),
            {},
        )
        self.assertEqual(
            await load_expense_forecast_override_map(
                self.db_path,
                year=2026,
                forecast_version="V1",
                owner_names=[],
            ),
            {},
        )


if __name__ == "__main__":
    unittest.main()
