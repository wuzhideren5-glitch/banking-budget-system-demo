from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiosqlite

from app.core.config import settings
from app.db_bootstrap.runtime_metric_tree import ensure_runtime_metric_identity_tables
from app.services.runtime_budget_paths import active_budget_database_files
from app.services import runtime_metric_refs as runtime_metric_refs_module
from app.services.runtime_metric_refs import (
    count_org_product_metric_refs,
    enrich_account_usage_flags,
    fetch_runtime_ref_detail,
    fetch_runtime_ref_list,
    list_runtime_refs,
    load_budget_data_ref_counts,
    load_org_product_metric_ref_counts,
    row_to_runtime_ref,
)


class RuntimeMetricRefsTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _seed_org_product_tree(conn: sqlite3.Connection) -> None:
        """Create the org_product_tree_snapshot table used by the CTE."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS org_product_tree_snapshot (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              payload_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "DELETE FROM org_product_tree_snapshot WHERE id = 1"
        )
        conn.execute(
            "INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at) VALUES (1, ?, 'now')",
            ('{"code":"AA","name":"微众银行","children":[{"code":"A01","name":"泛微粒贷","children":[]}]}',),
        )

    async def test_row_to_runtime_ref_rejects_legacy_short_rows(self) -> None:
        with self.assertRaisesRegex(ValueError, "当前机构及产品指标兼容 read model"):
            row_to_runtime_ref(("A01.01.01.001", "产品利息收入"))

    async def test_counts_budget_data_refs_across_year_files(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            try:
                common_conn = sqlite3.connect(data_dir / "common.db")
                try:
                    ensure_runtime_metric_identity_tables(common_conn)
                    common_conn.execute(
                        """
                        INSERT INTO data_account_metric_node(
                          node_code, node_name, parent_code, product_code,
                          local_metric_code, logic_code,
                          functional_group_code, metric_table_name,
                          level, node_type,
                          runtime_account_enabled, value_type
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        ('A01.01.01.001', '开鑫贷日均余额', 'A01.01.01', 'A01',
                         '01.01.001', '01.01.001',
                         '业务状况表', '业务状况表',
                         4, 'METRIC', 1, '金额'),
                    )
                    common_conn.commit()
                finally:
                    common_conn.close()

                for year, values in ((2099, [100, 200]), (2100, [300])):
                    conn = sqlite3.connect(data_dir / f"budget_{year}.db")
                    try:
                        conn.execute(
                            """
                            CREATE TABLE budget_data (
                              data_acct_code TEXT NOT NULL,
                              value REAL NOT NULL
                            )
                            """
                        )
                        conn.executemany(
                            "INSERT INTO budget_data(data_acct_code, value) VALUES (?, ?)",
                            [("A01.01.01.001", value) for value in values],
                        )
                        conn.commit()
                    finally:
                        conn.close()

                counts = await load_budget_data_ref_counts()
                account = row_to_runtime_ref(
                    (
                        "A01.01.01.001",
                        "开鑫贷日均余额",
                        "A01.01.01.001",
                        "日均余额",
                        "PRODUCT",
                        "A01",
                        None,
                        None,
                        0,
                        0,
                        1,
                        "金额",
                        None,
                        "泛微粒贷",
                    )
                )
                enriched = await enrich_account_usage_flags(account)

                self.assertEqual(
                    [path.name for path in active_budget_database_files()],
                    ["budget_2099.db", "budget_2100.db"],
                )
                self.assertEqual(counts, {"A01.01.01.001": 3})
                self.assertEqual(enriched.budget_data_ref_count, 3)
                self.assertEqual(enriched.metric_binding_ref_count, 1)
                self.assertTrue(enriched.has_budget_data_records)
            finally:
                settings.data_dir = original_data_dir

    async def test_fetch_runtime_ref_detail_joins_current_metric_identity_read_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with sqlite3.connect(db_path) as conn:
                ensure_runtime_metric_identity_tables(conn)
                self._seed_org_product_tree(conn)
                conn.execute(
                    """
                    INSERT INTO data_account_metric_node(
                      node_code, node_name, parent_code, product_code,
                      local_metric_code, logic_code,
                      functional_group_code, metric_table_name,
                      level, node_type,
                      runtime_account_enabled, value_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ('A01.01.01.001', '产品利息收入', 'A01.01.01', 'A01',
                     '01.01.001', '01.01.001',
                     '业务状况表', '业务状况表',
                     4, 'METRIC', 1, '金额'),
                )
                conn.commit()

            async with aiosqlite.connect(db_path) as db:
                account = await fetch_runtime_ref_detail(db, "A01.01.01.001")

        self.assertIsNotNone(account)
        assert account is not None
        self.assertEqual(account.data_acct_code, "A01.01.01.001")
        self.assertEqual(account.metric_code, "A01.01.01.001")
        self.assertEqual(account.metric_name, "产品利息收入")
        self.assertEqual(account.metric_node_code, "A01.01.01.001")
        self.assertEqual(account.metric_node_name, "产品利息收入")
        self.assertEqual(account.scope_type, "PRODUCT")
        self.assertEqual(account.scope_code, "A01")

    async def test_fetch_runtime_ref_list_applies_usage_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with sqlite3.connect(db_path) as conn:
                ensure_runtime_metric_identity_tables(conn)
                self._seed_org_product_tree(conn)
                conn.execute(
                    """
                    INSERT INTO data_account_metric_node(
                      node_code, node_name, parent_code, product_code,
                      local_metric_code, logic_code,
                      functional_group_code, metric_table_name,
                      level, node_type,
                      runtime_account_enabled, value_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ('A01.01.01.001', '产品利息收入', 'A01.01.01', 'A01',
                     '01.01.001', '01.01.001',
                     '业务状况表', '业务状况表',
                     4, 'METRIC', 1, '金额'),
                )
                conn.commit()

            async with aiosqlite.connect(db_path) as db:
                org_product_counts = await load_org_product_metric_ref_counts(db)
                accounts = await fetch_runtime_ref_list(
                    db,
                    {"A01.01.01.001": 2},
                )

        self.assertEqual(len(accounts), 1)
        account = accounts[0]
        self.assertEqual(account.data_acct_code, "A01.01.01.001")
        self.assertEqual(account.metric_node_name, "产品利息收入")
        self.assertEqual(account.budget_data_ref_count, 2)
        self.assertEqual(account.org_product_metric_ref_count, 1)
        self.assertEqual(org_product_counts, {"A01.01.01.001": 1})
        self.assertTrue(account.has_budget_data_records)

    async def test_org_product_metric_ref_counts_derive_from_metric_code_and_ignore_legacy_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with sqlite3.connect(db_path) as conn:
                ensure_runtime_metric_identity_tables(conn)
                self._seed_org_product_tree(conn)
                conn.execute(
                    """
                    INSERT INTO data_account_metric_node(
                      node_code, node_name, parent_code, product_code,
                      local_metric_code, logic_code,
                      functional_group_code, metric_table_name,
                      level, node_type,
                      runtime_account_enabled, value_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ('A03.03.01.01.01.078', '旧未确认状态', 'A03.03.01.01.01', 'A03',
                     '03.01.01.01.078', '03.01.01.01.078',
                     '业务状况表', '业务状况表',
                     6, 'METRIC', 1, '金额'),
                )
                conn.commit()

            count = await count_org_product_metric_refs(
                "A03.03.01.01.01.078",
                common_db=db_path,
            )

        self.assertEqual(count, 1)

    async def test_usage_queries_use_explicit_database_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            common_db = data_dir / "custom_common.db"
            included_budget = data_dir / "budget_included.db"
            ignored_budget = data_dir / "budget_ignored.db"

            with sqlite3.connect(common_db) as conn:
                ensure_runtime_metric_identity_tables(conn)
                self._seed_org_product_tree(conn)
                conn.execute(
                    """
                    INSERT INTO data_account_metric_node(
                      node_code, node_name, parent_code, product_code,
                      local_metric_code, logic_code,
                      functional_group_code, metric_table_name,
                      level, node_type,
                      runtime_account_enabled, value_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ('A01.01.01.001', '产品利息收入', 'A01.01.01', 'A01',
                     '01.01.001', '01.01.001',
                     '业务状况表', '业务状况表',
                     4, 'METRIC', 1, '金额'),
                )
                conn.commit()

            for path, values in (
                (included_budget, [100, 200]),
                (ignored_budget, [300, 400, 500]),
            ):
                with sqlite3.connect(path) as conn:
                    conn.execute(
                        """
                        CREATE TABLE budget_data (
                          data_acct_code TEXT NOT NULL,
                          value REAL NOT NULL
                        )
                        """
                    )
                    conn.executemany(
                        "INSERT INTO budget_data(data_acct_code, value) VALUES (?, ?)",
                        [("A01.01.01.001", value) for value in values],
                    )

            accounts = await list_runtime_refs(
                common_db,
                budget_paths=[included_budget],
            )
            account = row_to_runtime_ref(
                (
                    "A01.01.01.001",
                    "产品利息收入",
                    "A01.01.01.001",
                    "产品利息收入",
                    "PRODUCT",
                    "A01",
                    None,
                    None,
                    0,
                    0,
                    1,
                    "金额",
                    None,
                    "泛微粒贷",
                )
            )
            enriched = await enrich_account_usage_flags(
                account,
                common_db=common_db,
                budget_paths=[included_budget],
            )

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].budget_data_ref_count, 2)
        self.assertEqual(accounts[0].metric_binding_ref_count, 1)
        self.assertEqual(enriched.budget_data_ref_count, 2)
        self.assertEqual(enriched.metric_binding_ref_count, 1)


class _FakeRuntimeMetricRefsMysqlPool:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((" ".join(sql.split()), tuple(params)))
        if "from budget_data" in normalized:
            return [{"data_acct_code": "A01.01.01.001", "ref_count": 2}]
        if "from data_account_metric_binding" in normalized and "count(*)" in normalized:
            return [{"data_acct_code": "A01.01.01.001", "ref_count": 1}]
        if "from data_account_metric_node" in normalized and "runtime_account_enabled = 1" in normalized:
            return [
                {
                    "node_code": "A01.01.01.001",
                    "node_name": "产品利息收入",
                    "product_code": "A01",
                    "metric_table_name": "业务状况表",
                }
            ]
        if "from data_account d" in normalized:
            return [
                {
                    "data_acct_code": "A01.01.01.001",
                    "data_acct_name": "产品利息收入",
                    "metric_node_code": "A01.01.01.001",
                    "node_name": "产品利息收入",
                    "scope_type": "PRODUCT",
                    "scope_code": "A01",
                    "budget_formula": None,
                    "actual_formula": None,
                    "need_calc": 0,
                    "formula_calc_mode": 0,
                    "allow_manual_entry": 1,
                    "value_type": "金额",
                    "remark": None,
                    "product_name": "泛微粒贷",
                }
            ]
        raise AssertionError(f"Unexpected fetch_all SQL: {sql}")


class RuntimeMetricRefsMysqlPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_runtime_refs_uses_mysql_for_runtime_paths(self) -> None:
        fake_pool = _FakeRuntimeMetricRefsMysqlPool()

        with patch.object(runtime_metric_refs_module, "get_pool", return_value=fake_pool):
            accounts = await list_runtime_refs(
                settings.data_dir / "common.db",
                budget_paths=[settings.data_dir / "budget_2026.db"],
            )

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].data_acct_code, "A01.01.01.001")
        self.assertEqual(accounts[0].budget_data_ref_count, 2)
        self.assertEqual(accounts[0].metric_binding_ref_count, 1)
        self.assertEqual(accounts[0].org_product_metric_ref_count, 1)
        budget_sql, budget_params = next(
            (sql, params)
            for sql, params in fake_pool.fetch_all_calls
            if "FROM budget_data" in sql
        )
        self.assertIn("budget_year IN (%s)", budget_sql)
        self.assertEqual(budget_params, (2026,))

    def test_runtime_metric_refs_service_does_not_import_aiosqlite(self) -> None:
        source = Path(runtime_metric_refs_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("aiosqlite", source)


if __name__ == "__main__":
    unittest.main()
