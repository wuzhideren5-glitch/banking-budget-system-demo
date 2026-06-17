from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.agent.agent_query import ReadOnlySqlExecutor


class ReadOnlySqlExecutorTests(unittest.TestCase):
    def test_value_type_mapping_uses_org_product_metric_code_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            common_db = root / "common.db"
            budget_db = root / "budget.db"
            with sqlite3.connect(common_db) as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account(data_acct_code TEXT, data_acct_name TEXT, value_type TEXT);
                    CREATE TABLE org_product_metric_table(entity_code TEXT, table_name TEXT, payload_json TEXT);
                    INSERT INTO data_account VALUES
                        ('A03.01.01.001', '汽金管理贷款余额', '金额'),
                        ('Z99.01.001', '孤立运行数据科目', '数量');
                    INSERT INTO org_product_metric_table VALUES (
                        'A03',
                        '业务状况表',
                        '{"metrics":[{"code":"A030101001","name":"汽金管理贷款余额"},{"code":"Z9901","name":"孤立运行数据科目","mapping_status":"ORG_PRODUCT_ONLY_OR_CREATE_LATER","metric_node_code":"Z99.01.001","data_acct_code":"Z99.01.001"}]}'
                    );
                    """
                )

            executor = ReadOnlySqlExecutor(budget_db_path=budget_db, common_db_path=common_db)

        self.assertEqual(executor.data_name_value_type["汽金管理贷款余额"], "金额")
        self.assertEqual(executor.data_name_value_type["A03.01.01.001 汽金管理贷款余额"], "金额")
        self.assertNotIn("孤立运行数据科目", executor.data_name_value_type)
        self.assertNotIn("Z99.01.001 孤立运行数据科目", executor.data_name_value_type)


if __name__ == "__main__":
    unittest.main()
