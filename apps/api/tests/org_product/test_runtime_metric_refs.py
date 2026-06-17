from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import aiosqlite

from app.core.config import settings
from app.services.runtime_budget_paths import active_budget_database_files
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
                    common_conn.executescript(
                        """
                        CREATE TABLE data_account_metric_binding (
                          data_acct_code TEXT NOT NULL
                        );
                        INSERT INTO data_account_metric_binding(data_acct_code)
                        VALUES ('A01.01.01.001');
                        """
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
                conn.executescript(
                    """
                    CREATE TABLE data_account (
                      data_acct_code TEXT PRIMARY KEY,
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
                      node_code TEXT PRIMARY KEY,
                      node_name TEXT NOT NULL,
                      metric_rollup_method TEXT NOT NULL DEFAULT 'NONE'
                    );
                    CREATE TABLE data_account_metric_binding (
                      data_acct_code TEXT PRIMARY KEY,
                      metric_node_code TEXT NOT NULL,
                      scope_type TEXT NOT NULL,
                      scope_code TEXT NOT NULL,
                      is_active INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE TABLE org_product_tree_snapshot (
                      id INTEGER PRIMARY KEY CHECK (id = 1),
                      payload_json TEXT NOT NULL,
                      updated_at TEXT NOT NULL
                    );
                    INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
                    VALUES ('A01.01.01.001', '产品利息收入', '金额');
                    INSERT INTO data_account_metric_node(node_code, node_name, metric_rollup_method)
                    VALUES ('A01.01.01.001', '产品利息收入', 'SUM');
                    INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at)
                    VALUES(1, '{"code":"AA","name":"微众银行","children":[{"code":"A","name":"个金群","children":[{"code":"A01","name":"泛微粒贷","children":[]}]}]}', 'now');
                    INSERT INTO data_account_metric_binding(data_acct_code, metric_node_code, scope_type, scope_code)
                    VALUES ('A01.01.01.001', 'A01.01.01.001', 'PRODUCT', 'A01');
                    """
                )

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
        self.assertEqual(account.product_name, "泛微粒贷")

    async def test_fetch_runtime_ref_list_applies_usage_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account (
                      data_acct_code TEXT PRIMARY KEY,
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
                      node_code TEXT PRIMARY KEY,
                      node_name TEXT NOT NULL,
                      metric_rollup_method TEXT NOT NULL DEFAULT 'NONE'
                    );
                    CREATE TABLE data_account_metric_binding (
                      data_acct_code TEXT NOT NULL,
                      metric_node_code TEXT NOT NULL,
                      scope_type TEXT NOT NULL,
                      scope_code TEXT NOT NULL,
                      is_active INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE TABLE org_product_tree_snapshot (
                      id INTEGER PRIMARY KEY CHECK (id = 1),
                      payload_json TEXT NOT NULL,
                      updated_at TEXT NOT NULL
                    );
                    INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
                    VALUES ('A01.01.01.001', '产品利息收入', '金额');
                    INSERT INTO data_account_metric_node(node_code, node_name, metric_rollup_method)
                    VALUES ('A01.01.01.001', '产品利息收入', 'NONE');
                    INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at)
                    VALUES(1, '{"code":"AA","name":"微众银行","children":[{"code":"A","name":"个金群","children":[{"code":"A01","name":"泛微粒贷","children":[]}]}]}', 'now');
                    INSERT INTO data_account_metric_binding(data_acct_code, metric_node_code, scope_type, scope_code, is_active)
                    VALUES
                      ('A01.01.01.001', 'A01.01.01.001', 'PRODUCT', 'A01', 1),
                      ('A01.01.01.001', 'A01.01.01.001', 'PRODUCT', 'A01', 0);
                    CREATE TABLE org_product_metric_table (
                      entity_code TEXT,
                      table_name TEXT,
                      payload_json TEXT
                    );
                    INSERT INTO org_product_metric_table VALUES (
                      'A01',
                      '业务状况表',
                      '{"metrics":[{"code":"A010101001","name":"管理贷款余额"},{"code":"A0105","name":"05费用","mapping_status":"ORG_PRODUCT_ONLY_OR_CREATE_LATER"}]}'
                    );
                    """
                )

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
        self.assertEqual(account.product_name, "泛微粒贷")
        self.assertEqual(account.budget_data_ref_count, 2)
        self.assertEqual(account.metric_binding_ref_count, 2)
        self.assertEqual(account.org_product_metric_ref_count, 1)
        self.assertEqual(org_product_counts, {"A01.01.01.001": 1, "A01.05": 1})
        self.assertTrue(account.has_budget_data_records)

    async def test_org_product_metric_ref_counts_derive_from_metric_code_and_ignore_legacy_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE org_product_metric_table (
                      entity_code TEXT,
                      table_name TEXT,
                      payload_json TEXT
                    );
                    INSERT INTO org_product_metric_table VALUES (
                      'A03',
                      '业务状况表',
                      '{"metrics":[{"code":"A0303010101078","name":"旧未确认状态","mapping_status":"ORG_PRODUCT_ONLY_OR_CREATE_LATER","data_acct_code":"Z99.OLD"},{"code":"A030501","name":"费用项"}]}'
                    );
                    """
                )

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
                conn.executescript(
                    """
                    CREATE TABLE data_account (
                      data_acct_code TEXT PRIMARY KEY,
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
                      node_code TEXT PRIMARY KEY,
                      node_name TEXT NOT NULL,
                      metric_rollup_method TEXT NOT NULL DEFAULT 'NONE'
                    );
                    CREATE TABLE data_account_metric_binding (
                      data_acct_code TEXT NOT NULL,
                      metric_node_code TEXT NOT NULL,
                      scope_type TEXT NOT NULL,
                      scope_code TEXT NOT NULL,
                      is_active INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE TABLE org_product_tree_snapshot (
                      id INTEGER PRIMARY KEY CHECK (id = 1),
                      payload_json TEXT NOT NULL,
                      updated_at TEXT NOT NULL
                    );
                    INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
                    VALUES ('A01.01.01.001', '产品利息收入', '金额');
                    INSERT INTO data_account_metric_node(node_code, node_name, metric_rollup_method)
                    VALUES ('A01.01.01.001', '产品利息收入', 'NONE');
                    INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at)
                    VALUES(1, '{"code":"AA","name":"微众银行","children":[{"code":"A","name":"个金群","children":[{"code":"A01","name":"泛微粒贷","children":[]}]}]}', 'now');
                    INSERT INTO data_account_metric_binding(data_acct_code, metric_node_code, scope_type, scope_code, is_active)
                    VALUES ('A01.01.01.001', 'A01.01.01.001', 'PRODUCT', 'A01', 1);
                    """
                )

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


if __name__ == "__main__":
    unittest.main()
