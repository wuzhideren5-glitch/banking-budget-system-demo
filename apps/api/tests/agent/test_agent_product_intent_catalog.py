from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.agent.agent_product_intent import (
    _bindings_for_metric_nodes,
    _lookup_metric_nodes,
    build_catalog_digest,
    format_query_spec_locked_dimensions_block,
)


class AgentProductIntentCatalogTests(unittest.TestCase):
    def _write_agent_metric_fixture(self, common_db: Path) -> None:
        with sqlite3.connect(common_db) as conn:
            conn.executescript(
                """
                CREATE TABLE data_account_metric_node(
                    node_code TEXT,
                    node_name TEXT,
                    parent_code TEXT,
                    level INTEGER,
                    node_type TEXT,
                    sort_order INTEGER DEFAULT 0,
                    is_active INTEGER,
                    runtime_account_enabled INTEGER DEFAULT 0,
                    product_code TEXT DEFAULT '',
                    functional_group_code TEXT DEFAULT '',
                    metric_table_name TEXT NOT NULL DEFAULT '',
                    value_type TEXT DEFAULT ''
                );
                CREATE TABLE data_account_metric_binding(
                    data_acct_code TEXT,
                    metric_node_code TEXT,
                    scope_type TEXT,
                    scope_code TEXT,
                    sort_order INTEGER DEFAULT 0,
                    is_active INTEGER
                );
                CREATE TABLE data_account(data_acct_code TEXT, data_acct_name TEXT, value_type TEXT);
                CREATE TABLE dept_account(dept_code TEXT, dept_name TEXT, level INTEGER);
                CREATE TABLE org_product_tree_snapshot(id INTEGER PRIMARY KEY, payload_json TEXT);
                CREATE TABLE org_product_metric_table(entity_code TEXT, table_name TEXT, payload_json TEXT);

                INSERT INTO data_account_metric_node(node_code, node_name, parent_code, level, node_type, sort_order, is_active, runtime_account_enabled, product_code, functional_group_code, metric_table_name) VALUES
                    ('A03', '汽车金融', '', 1, 'CATEGORY', 0, 1, 0, '', '', ''),
                    ('A03.01', '规模余额指标', 'A03', 2, 'GROUP', 0, 1, 0, '', '', ''),
                    ('A03.01.01.001', '汽金管理贷款余额', 'A03.01', 4, 'METRIC', 0, 1, 1, 'A03', '业务状况表', '业务状况表'),
                    ('Z99.01.001', '孤立运行指标节点', '', 3, 'METRIC', 0, 1, 0, '', '', '');
                INSERT INTO data_account_metric_binding VALUES
                    ('A03.01.01.001', 'A03.01.01.001', 'PRODUCT', 'A03', 0, 1),
                    ('Z99.01.001', 'Z99.01.001', 'PRODUCT', 'Z99', 0, 1);
                INSERT INTO data_account VALUES
                    ('A03.01.01.001', '汽金管理贷款余额', '金额'),
                    ('Z99.01.001', '孤立运行数据科目', '金额');
                INSERT INTO dept_account VALUES ('Y103', '汽车金融部', 2);
                INSERT INTO org_product_tree_snapshot
                VALUES (1, '{"code":"AA","name":"微众银行","children":[{"code":"A","name":"个金群","children":[{"code":"A03","name":"汽车金融","children":[]}]}]}');
                INSERT INTO org_product_metric_table VALUES (
                    'A03',
                    '业务状况表',
                    '{"metrics":[{"code":"A030101001","name":"汽金管理贷款余额","value_type":"金额"},{"code":"A0305","name":"汽金05指标","mapping_status":"ORG_PRODUCT_ONLY_OR_CREATE_LATER"}]}'
                );
                """
            )

    def test_catalog_digest_sources_metrics_from_org_product_metric_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_db = Path(tmp) / "common.db"
            with sqlite3.connect(common_db) as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account_metric_node(
                        node_code TEXT,
                        node_name TEXT,
                        parent_code TEXT,
                        level INTEGER,
                        node_type TEXT,
                        is_active INTEGER,
                        runtime_account_enabled INTEGER DEFAULT 0,
                        product_code TEXT DEFAULT '',
                        functional_group_code TEXT DEFAULT '',
                        metric_table_name TEXT NOT NULL DEFAULT '',
                        value_type TEXT DEFAULT ''
                    );
                    CREATE TABLE data_account_metric_binding(data_acct_code TEXT, is_active INTEGER);
                    CREATE TABLE data_account(data_acct_code TEXT, data_acct_name TEXT, value_type TEXT);
                    CREATE TABLE dept_account(dept_code TEXT, dept_name TEXT, level INTEGER);
                    CREATE TABLE org_product_tree_snapshot(id INTEGER PRIMARY KEY, payload_json TEXT);
                    CREATE TABLE org_product_metric_table(entity_code TEXT, table_name TEXT, payload_json TEXT);

                    INSERT INTO data_account_metric_node(node_code, node_name, parent_code, level, node_type, is_active, runtime_account_enabled, product_code, functional_group_code, metric_table_name) VALUES
                        ('A03.01.01.001', '汽金管理贷款余额', '', 4, 'METRIC', 1, 1, 'A03', '业务状况表', '业务状况表'),
                        ('Z99.01.001', '孤立运行指标节点', '', 3, 'METRIC', 1, 0, '', '', '');
                    INSERT INTO data_account_metric_binding VALUES ('A03.01.01.001', 1);
                    INSERT INTO data_account VALUES
                        ('A03.01.01.001', '汽金管理贷款余额', '金额'),
                        ('Z99.01.001', '孤立运行数据科目', '金额');
                    INSERT INTO dept_account VALUES ('Y103', '汽车金融部', 2);
                    INSERT INTO org_product_tree_snapshot
                    VALUES (1, '{"code":"AA","name":"微众银行","children":[{"code":"A03","name":"汽车金融","children":[]}]}');
                    INSERT INTO org_product_metric_table VALUES (
                        'A03',
                        '业务状况表',
                        '{"metrics":[{"code":"A030101001","name":"汽金管理贷款余额","value_type":"金额"},{"code":"A0305","name":"汽金05指标","mapping_status":"ORG_PRODUCT_ONLY_OR_CREATE_LATER"}]}'
                    );
                    """
                )

            digest = build_catalog_digest(common_db, max_chars=None)

        self.assertIn("【机构及产品指标编码】", digest)
        self.assertIn("A03.01.01.001|汽金管理贷款余额|金额|A03|业务状况表|A03.01.01.001", digest)
        self.assertNotIn("孤立运行数据科目", digest)
        self.assertNotIn("孤立运行指标节点", digest)
        self.assertNotIn("汽金未确认指标", digest)
        self.assertNotIn("【数据科目】代码|名称|值类型", digest)

    def test_locked_dimensions_labels_data_accounts_as_org_product_metric_codes(self) -> None:
        block = format_query_spec_locked_dimensions_block(
            {
                "data_accounts": [{"code": "A03.01.01.001", "name": "汽金管理贷款余额"}],
                "metric_nodes": [],
                "departments": [],
                "products": [],
            }
        )

        self.assertIn("**机构及产品指标编码**", block)
        self.assertIn("- A03.01.01.001｜汽金管理贷款余额", block)
        self.assertNotIn("**数据科目**", block)

    def test_metric_lookup_ignores_orphan_runtime_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_db = Path(tmp) / "common.db"
            self._write_agent_metric_fixture(common_db)

            with sqlite3.connect(common_db) as conn:
                cur = conn.cursor()

                confirmed = _lookup_metric_nodes(cur, "汽金管理贷款余额")
                orphan = _lookup_metric_nodes(cur, "孤立运行指标节点")

        self.assertEqual([item["code"] for item in confirmed], ["A03.01.01.001"])
        self.assertEqual(orphan, [])

    def test_metric_binding_lookup_ignores_orphan_runtime_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_db = Path(tmp) / "common.db"
            self._write_agent_metric_fixture(common_db)

            with sqlite3.connect(common_db) as conn:
                cur = conn.cursor()

                confirmed = _bindings_for_metric_nodes(
                    cur,
                    node_codes=["A03.01.01.001"],
                    scope_codes=["A03"],
                    include_descendants=False,
                )
                orphan = _bindings_for_metric_nodes(
                    cur,
                    node_codes=["Z99.01.001"],
                    scope_codes=["Z99"],
                    include_descendants=False,
                )

        self.assertEqual([item["data_acct_code"] for item in confirmed], ["A03.01.01.001"])
        self.assertEqual(orphan, [])

    def test_metric_binding_lookup_expands_parent_product_scope_from_org_product_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_db = Path(tmp) / "common.db"
            self._write_agent_metric_fixture(common_db)

            with sqlite3.connect(common_db) as conn:
                cur = conn.cursor()

                rows = _bindings_for_metric_nodes(
                    cur,
                    node_codes=["A03.01.01.001"],
                    scope_codes=["A"],
                    include_descendants=False,
                )

        self.assertEqual([item["scope_code"] for item in rows], ["A03"])
        self.assertEqual([item["data_acct_code"] for item in rows], ["A03.01.01.001"])


if __name__ == "__main__":
    unittest.main()
