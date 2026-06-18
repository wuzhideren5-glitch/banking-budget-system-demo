from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiosqlite

from app.core.config import settings
from app.services import metric_tree_rollups as metric_tree_rollups_module
from app.budget_data_writer import (
    BudgetDataWriteError,
    BudgetDataWriteItem,
    MANUAL_INPUT_POLICY,
    write_budget_data_items,
)
from app.services.metric_tree_rollups import estimate_metric_tree_rollups, rebuild_metric_tree_rollups


def build_common_db(
    path: Path,
    *,
    include_sum_parent_account: bool = False,
    include_formula_parent: bool = False,
) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE org_product_tree_snapshot (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              payload_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE data_account (
              data_acct_code TEXT PRIMARY KEY NOT NULL,
              data_acct_name TEXT NOT NULL,
              budget_formula TEXT,
              actual_formula TEXT,
              need_calc INTEGER NOT NULL DEFAULT 0,
              formula_calc_mode INTEGER NOT NULL DEFAULT 0,
              allow_manual_entry INTEGER NOT NULL DEFAULT 1,
              value_type TEXT NOT NULL,
              remark TEXT
            );
            CREATE TABLE data_account_metric_node (
              node_code TEXT PRIMARY KEY NOT NULL,
              node_name TEXT NOT NULL,
              parent_code TEXT,
              product_code TEXT,
              local_metric_code TEXT,
              level INTEGER NOT NULL,
              node_type TEXT NOT NULL,
              logic_code TEXT,
              horizontal_rollup INTEGER NOT NULL DEFAULT 0,
              vertical_rollup INTEGER NOT NULL DEFAULT 0,
              sort_order INTEGER NOT NULL DEFAULT 0,
              is_active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              remark TEXT
            );
            CREATE TABLE data_account_metric_binding (
              data_acct_code TEXT PRIMARY KEY NOT NULL,
              metric_node_code TEXT NOT NULL,
              scope_type TEXT NOT NULL,
              scope_code TEXT NOT NULL,
              sort_order INTEGER NOT NULL DEFAULT 0,
              is_active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              remark TEXT,
              UNIQUE(metric_node_code, scope_code)
            );
            CREATE TABLE period (
              period_id INTEGER PRIMARY KEY NOT NULL,
              year TEXT NOT NULL,
              month TEXT NOT NULL,
              quarter TEXT NOT NULL
            );
            INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at)
            VALUES(1, '{"code":"AA","name":"微众银行","children":[{"code":"A","name":"个金群","children":[{"code":"A01","name":"开鑫贷","children":[]}]}]}', 'now');
            INSERT INTO period(period_id, year, month, quarter)
            VALUES (1, 'Y2099', 'M01', 'Q1'), (2, 'Y2099', 'M02', 'Q1');
            INSERT INTO data_account_metric_node(
              node_code, node_name, parent_code, product_code, local_metric_code, level,
              node_type, logic_code, vertical_rollup, sort_order
            ) VALUES
              ('A01', '开鑫贷', NULL, 'A01', '', 1, 'CATEGORY', '', 0, 1),
              ('A01.01', '贷款资产', 'A01', 'A01', '01', 2, 'GROUP', '01', 0, 1),
              ('A01.01.01', '贷款余额', 'A01.01', 'A01', '01.01', 3, 'GROUP', '01.01', 1, 1),
              ('A01.01.01.001', '日均余额', 'A01.01.01', 'A01', '01.01.001', 4, 'METRIC', '01.01.001', 0, 1);
            INSERT INTO data_account(
              data_acct_code, data_acct_name, allow_manual_entry, value_type
            ) VALUES ('A01.01.01.001', '开鑫贷日均余额', 1, '金额');
            INSERT INTO data_account_metric_binding(
              data_acct_code, metric_node_code, scope_type, scope_code, sort_order, is_active
            ) VALUES ('A01.01.01.001', 'A01.01.01.001', 'PRODUCT', 'A01', 1, 1);
            """
        )
        if include_sum_parent_account:
            conn.executescript(
                """
                INSERT INTO data_account(
                  data_acct_code, data_acct_name, need_calc, formula_calc_mode, allow_manual_entry, value_type
                ) VALUES ('A01.01.01', '开鑫贷贷款余额', 0, 0, 0, '金额');
                INSERT INTO data_account_metric_binding(
                  data_acct_code, metric_node_code, scope_type, scope_code, sort_order, is_active
                ) VALUES ('A01.01.01', 'A01.01.01', 'PRODUCT', 'A01', 0, 1);
                """
            )
        if include_formula_parent:
            conn.executescript(
                """
                INSERT INTO data_account_metric_node(
                  node_code, node_name, parent_code, product_code, local_metric_code, level,
                  node_type, logic_code, sort_order
                ) VALUES
                  ('A01.02', '收益率', 'A01', 'A01', '02', 2, 'GROUP', '02', 1),
                  ('A01.02.01', '贷款收益率', 'A01.02', 'A01', '02.01', 3, 'GROUP', '02.01', 1),
                  ('A01.02.01.001', '利息收入', 'A01.02.01', 'A01', '02.01.001', 4, 'METRIC', '02.01.001', 1),
                  ('A01.02.01.002', '贷款余额', 'A01.02.01', 'A01', '02.01.002', 4, 'METRIC', '02.01.002', 2);
                INSERT INTO data_account(
                  data_acct_code, data_acct_name, budget_formula, actual_formula,
                  need_calc, formula_calc_mode, allow_manual_entry, value_type
                ) VALUES
                  ('A01.02.01.001', '开鑫贷利息收入', NULL, NULL, 0, 0, 1, '金额'),
                  ('A01.02.01.002', '开鑫贷贷款余额', NULL, NULL, 0, 0, 1, '金额'),
                  (
                    'A01.02.01',
                    '开鑫贷贷款收益率',
                    'A01.02.01.001 / A01.02.01.002',
                    'A01.02.01.001 / A01.02.01.002',
                    1,
                    3,
                    0,
                    '百分比'
                  );
                INSERT INTO data_account_metric_binding(
                  data_acct_code, metric_node_code, scope_type, scope_code, sort_order, is_active
                ) VALUES
                  ('A01.02.01.001', 'A01.02.01.001', 'PRODUCT', 'A01', 1, 1),
                  ('A01.02.01.002', 'A01.02.01.002', 'PRODUCT', 'A01', 2, 1),
                  ('A01.02.01', 'A01.02.01', 'PRODUCT', 'A01', 0, 1);
                """
            )
        conn.commit()
    finally:
        conn.close()


def build_budget_db(path: Path, *, include_formula_parent: bool = False) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE version (
              version_id INTEGER PRIMARY KEY NOT NULL,
              version_date_time TEXT NOT NULL,
              version_name TEXT NOT NULL,
              current_month INTEGER NOT NULL
            );
            CREATE TABLE budget_data (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              data_acct_code TEXT NOT NULL,
              product_code TEXT NOT NULL,
              period_id INTEGER NOT NULL,
              budget_actual INTEGER NOT NULL CHECK (budget_actual IN (0, 1)),
              version_id INTEGER NOT NULL,
              value REAL NOT NULL DEFAULT 0,
              formula_value REAL,
              manual_value REAL,
              value_source TEXT NOT NULL DEFAULT 'manual' CHECK (value_source IN ('manual', 'formula', 'none', 'rollup')),
              need_calc INTEGER NOT NULL DEFAULT 1,
              create_time TEXT,
              update_time TEXT,
              UNIQUE (data_acct_code, product_code, period_id, version_id, budget_actual)
            );
            INSERT INTO version(version_id, version_date_time, version_name, current_month)
            VALUES (1, '2099-01-01T00:00:00Z', 'V2099', 13);
            INSERT INTO budget_data(
              data_acct_code, product_code, period_id, budget_actual, version_id,
              value, manual_value, value_source, need_calc
            ) VALUES
              ('A01.01.01.001', 'A01', 1, 1, 1, 10, 10, 'manual', 0),
              ('A01.01.01.001', 'A01', 2, 1, 1, 20, 20, 'manual', 0);
            """
        )
        if include_formula_parent:
            conn.executescript(
                """
                INSERT INTO budget_data(
                  data_acct_code, product_code, period_id, budget_actual, version_id,
                  value, manual_value, value_source, need_calc
                ) VALUES
                  ('A01.02.01.001', 'A01', 1, 1, 1, 100, 100, 'manual', 0),
                  ('A01.02.01.002', 'A01', 1, 1, 1, 1000, 1000, 'manual', 0),
                  ('A01.02.01.001', 'A01', 2, 1, 1, 200, 200, 'manual', 0),
                  ('A01.02.01.002', 'A01', 2, 1, 1, 1000, 1000, 'manual', 0);
                """
            )
        conn.commit()
    finally:
        conn.close()


class MetricTreeRollupTests(unittest.IsolatedAsyncioTestCase):
    async def test_sum_parent_rollup_writes_parent_node_fact_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            budget_path = Path(tmp) / "budget_2099.db"
            build_common_db(common_path, include_sum_parent_account=True)
            build_budget_db(budget_path)

            result = await rebuild_metric_tree_rollups(
                common_path=common_path,
                budget_path=budget_path,
                budget_year=2099,
                version_id=1,
                product_codes=["A01"],
                budget_actuals=[1],
            )

            self.assertEqual(result.written_cells, 2)
            async with aiosqlite.connect(common_path) as db:
                cur = await db.execute(
                    """
                    SELECT d.allow_manual_entry, b.metric_node_code
                    FROM data_account d
                    JOIN data_account_metric_binding b ON b.data_acct_code = d.data_acct_code
                    WHERE d.data_acct_code = 'A01.01.01'
                    """
                )
                row = await cur.fetchone()
            self.assertEqual(row, (0, "A01.01.01"))

            conn = sqlite3.connect(budget_path)
            try:
                rows = conn.execute(
                    """
                    SELECT period_id, value, value_source
                    FROM budget_data
                    WHERE data_acct_code = 'A01.01.01'
                    ORDER BY period_id
                    """
                ).fetchall()
            finally:
                conn.close()
            self.assertEqual(rows, [(1, 10.0, "rollup"), (2, 20.0, "rollup")])

    async def test_sum_parent_rollup_does_not_create_missing_runtime_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            budget_path = Path(tmp) / "budget_2099.db"
            build_common_db(common_path)
            build_budget_db(budget_path)

            result = await rebuild_metric_tree_rollups(
                common_path=common_path,
                budget_path=budget_path,
                budget_year=2099,
                version_id=1,
                product_codes=["A01"],
                budget_actuals=[1],
            )

            self.assertEqual(result.written_cells, 0)
            self.assertIn("A01.01.01/A01 未在机构及产品指标表确认运行主键，已跳过汇总。", result.warnings)
            async with aiosqlite.connect(common_path) as db:
                cur = await db.execute(
                    "SELECT COUNT(*) FROM data_account WHERE data_acct_code = 'A01.01.01'"
                )
                row = await cur.fetchone()
            self.assertEqual(row[0], 0)

    async def test_manual_writer_rejects_parent_rollup_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            budget_path = Path(tmp) / "budget_2099.db"
            build_common_db(common_path, include_sum_parent_account=True)
            build_budget_db(budget_path)
            await rebuild_metric_tree_rollups(
                common_path=common_path,
                budget_path=budget_path,
                budget_year=2099,
                version_id=1,
                product_codes=["A01"],
                budget_actuals=[1],
            )

            with self.assertRaises(BudgetDataWriteError):
                await write_budget_data_items(
                    budget_path=budget_path,
                    common_path=common_path,
                    policy=MANUAL_INPUT_POLICY,
                    items=[
                        BudgetDataWriteItem(
                            data_acct_code="A01.01.01",
                            product_code="A01",
                            period_id=1,
                            budget_actual=1,
                            version_id=1,
                            value=999,
                        )
                    ],
                )

    async def test_manual_writer_accepts_product_prefixed_metric_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            budget_path = Path(tmp) / "budget_2099.db"
            build_common_db(common_path)
            build_budget_db(budget_path)

            result = await write_budget_data_items(
                budget_path=budget_path,
                common_path=common_path,
                policy=MANUAL_INPUT_POLICY,
                items=[
                    BudgetDataWriteItem(
                        data_acct_code="A01.01.01.001",
                        product_code="A01",
                        period_id=1,
                        budget_actual=1,
                        version_id=1,
                        value=88,
                    )
                ],
            )

            self.assertEqual(result.saved_cells, 1)
            conn = sqlite3.connect(budget_path)
            try:
                row = conn.execute(
                    """
                    SELECT product_code, value, value_source
                    FROM budget_data
                    WHERE data_acct_code = 'A01.01.01.001'
                    """
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(row, ("A01", 88.0, "manual"))

    async def test_plan_estimate_matches_rebuild_and_ignores_retired_formula_rollup_method(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            budget_path = Path(tmp) / "budget_2099.db"
            build_common_db(common_path, include_sum_parent_account=True, include_formula_parent=True)
            build_budget_db(budget_path, include_formula_parent=True)

            estimate = await estimate_metric_tree_rollups(
                common_path=common_path,
                budget_year=2099,
                product_codes=["A01"],
                budget_actuals=[1],
            )
            result = await rebuild_metric_tree_rollups(
                common_path=common_path,
                budget_path=budget_path,
                budget_year=2099,
                version_id=1,
                product_codes=["A01"],
                budget_actuals=[1],
            )

            self.assertEqual(estimate.rollup_account_count, 1)
            self.assertEqual(estimate.rollup_task_count, 1)
            self.assertEqual(estimate.rollup_cell_count, 2)
            self.assertFalse(estimate.audit_truncated)
            self.assertEqual(
                [
                    (
                        item.node_code,
                        item.target_data_acct_code,
                        item.method,
                        item.budget_actual,
                        item.cell_count,
                        item.source_count,
                    )
                    for item in estimate.audit_items
                ],
                [
                    ("A01.01.01", "A01.01.01", "SUM", 1, 2, 1),
                ],
            )
            self.assertEqual(result.rollup_account_count, estimate.rollup_account_count)
            self.assertEqual(result.rollup_task_count, estimate.rollup_task_count)
            self.assertEqual(result.rollup_cell_count, estimate.rollup_cell_count)
            self.assertEqual(result.written_cells, estimate.rollup_cell_count)

            conn = sqlite3.connect(budget_path)
            try:
                rows = conn.execute(
                    """
                    SELECT period_id, value, value_source
                    FROM budget_data
                    WHERE data_acct_code = 'A01.02.01'
                    ORDER BY period_id
                    """
                ).fetchall()
            finally:
                conn.close()
            self.assertEqual(rows, [])


class _FakeMetricTreeRollupMysqlPool:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((" ".join(sql.split()), tuple(params)))
        if "from data_account_metric_node" in normalized and "select node_code, node_name" in normalized:
            return [
                {
                    "node_code": "A01",
                    "node_name": "开鑫贷",
                    "parent_code": None,
                    "node_type": "CATEGORY",
                    "level": 1,
                    "product_code": "A01",
                    "logic_code": "",
                    "horizontal_rollup": 0,
                    "vertical_rollup": 0,
                },
                {
                    "node_code": "A01.01",
                    "node_name": "贷款资产",
                    "parent_code": "A01",
                    "node_type": "GROUP",
                    "level": 2,
                    "product_code": "A01",
                    "logic_code": "01",
                    "horizontal_rollup": 0,
                    "vertical_rollup": 0,
                },
                {
                    "node_code": "A01.01.01",
                    "node_name": "贷款余额",
                    "parent_code": "A01.01",
                    "node_type": "GROUP",
                    "level": 3,
                    "product_code": "A01",
                    "logic_code": "01.01",
                    "horizontal_rollup": 0,
                    "vertical_rollup": 1,
                },
                {
                    "node_code": "A01.01.01.001",
                    "node_name": "日均余额",
                    "parent_code": "A01.01.01",
                    "node_type": "METRIC",
                    "level": 4,
                    "product_code": "A01",
                    "logic_code": "01.01.001",
                    "horizontal_rollup": 0,
                    "vertical_rollup": 0,
                },
            ]
        if "from data_account_metric_binding" in normalized:
            return [
                {
                    "metric_node_code": "A01.01.01.001",
                    "scope_type": "PRODUCT",
                    "scope_code": "A01",
                    "data_acct_code": "A01.01.01.001",
                    "data_acct_name": "开鑫贷日均余额",
                    "value_type": "金额",
                    "budget_formula": None,
                    "actual_formula": None,
                    "sort_order": 1,
                },
                {
                    "metric_node_code": "A01.01.01",
                    "scope_type": "PRODUCT",
                    "scope_code": "A01",
                    "data_acct_code": "A01.01.01",
                    "data_acct_name": "开鑫贷贷款余额",
                    "value_type": "金额",
                    "budget_formula": None,
                    "actual_formula": None,
                    "sort_order": 0,
                },
            ]
        if "from period" in normalized:
            return [{"period_id": 1}, {"period_id": 2}]
        if "from budget_data" in normalized:
            return [
                {
                    "data_acct_code": "A01.01.01.001",
                    "product_code": "A01",
                    "period_id": 1,
                    "budget_actual": 1,
                    "value": 10,
                },
                {
                    "data_acct_code": "A01.01.01.001",
                    "product_code": "A01",
                    "period_id": 2,
                    "budget_actual": 1,
                    "value": 20,
                },
            ]
        raise AssertionError(f"Unexpected fetch_all SQL: {sql}")

    async def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((" ".join(sql.split()), tuple(params)))
        if "from org_product_tree_snapshot" in normalized:
            return {
                "payload_json": '{"code":"AA","name":"微众银行","children":[{"code":"A","name":"个金群","children":[{"code":"A01","name":"开鑫贷","children":[]}]}]}'
            }
        raise AssertionError(f"Unexpected fetch_one SQL: {sql}")


class MetricTreeRollupMysqlPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_rebuild_metric_tree_rollups_uses_mysql_for_runtime_paths(self) -> None:
        fake_pool = _FakeMetricTreeRollupMysqlPool()
        captured: dict[str, object] = {}

        async def fake_delete_rollup_budget_data_rows(**kwargs):
            captured["delete_kwargs"] = kwargs
            return 0

        async def fake_write_budget_data_items(**kwargs):
            captured["write_kwargs"] = kwargs

            class Result:
                saved_cells = len(kwargs["items"])
                warnings: list[str] = []

            return Result()

        with (
            patch.object(metric_tree_rollups_module, "get_pool", return_value=fake_pool),
            patch.object(metric_tree_rollups_module, "delete_rollup_budget_data_rows", fake_delete_rollup_budget_data_rows),
            patch.object(metric_tree_rollups_module, "write_budget_data_items", fake_write_budget_data_items),
        ):
            result = await rebuild_metric_tree_rollups(
                common_path=settings.data_dir / "common.db",
                budget_path=settings.data_dir / "budget_2026.db",
                budget_year=2026,
                version_id=2026000003,
                product_codes=["A01"],
                budget_actuals=[1],
            )

        self.assertEqual(result.written_cells, 2)
        budget_sql, budget_params = next(
            (sql, params)
            for sql, params in fake_pool.fetch_all_calls
            if "FROM budget_data" in sql
        )
        self.assertIn("budget_year = %s", budget_sql)
        self.assertEqual(budget_params[:2], (2026, 2026000003))
        write_items = captured["write_kwargs"]["items"]  # type: ignore[index]
        self.assertEqual([item.value for item in write_items], [10.0, 20.0])
        source = Path(metric_tree_rollups_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("aiosqlite", source)
