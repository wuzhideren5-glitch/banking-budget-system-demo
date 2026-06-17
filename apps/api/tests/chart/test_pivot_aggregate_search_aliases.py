from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.pivot_aggregate import _expand_search_keyword, _search_where


class PivotAggregateSearchAliasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.common_db = Path(self.tmp.name) / "common.db"
        with sqlite3.connect(self.common_db) as conn:
            conn.executescript(
                """
                CREATE TABLE org_product_metric_table(
                    entity_code TEXT,
                    table_name TEXT,
                    payload_json TEXT
                );

                INSERT INTO org_product_metric_table VALUES (
                    'A03',
                    '业务状况表',
                    '{"metrics":[{"code":"A0303010101078","name":"汽金管理贷款余额"},{"code":"A0305","name":"汽金05指标","mapping_status":"ORG_PRODUCT_ONLY_OR_CREATE_LATER"},{"code":"A030501","name":"汽金费用手工行"}]}'
                );
                """
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_confirmed_org_product_ref_expands_to_underlying_pivot_aliases(self) -> None:
        expanded = set(_expand_search_keyword("A03业务状况表A0303010101078", common_path=self.common_db))

        self.assertIn("A03.03.01.01.01.078", expanded)
        self.assertIn("汽金管理贷款余额", expanded)

    def test_derivable_org_product_refs_expand_pivot_aliases_without_legacy_status(self) -> None:
        status_ignored_code = set(_expand_search_keyword("A0305", common_path=self.common_db))
        fee_code = set(_expand_search_keyword("A030501", common_path=self.common_db))

        self.assertIn("A03.05", status_ignored_code)
        self.assertIn("汽金05指标", status_ignored_code)
        self.assertIn("A03:业务状况表:A030501", fee_code)
        self.assertIn("A03.05.01", fee_code)
        self.assertIn("汽金费用手工行", fee_code)

    def test_search_where_keeps_one_keyword_clause_with_expanded_or_aliases(self) -> None:
        values: list[object] = []
        where = _search_where("A03业务状况表A0303010101078", values, common_path=self.common_db)

        self.assertTrue(where.startswith(" AND ("))
        self.assertIn("%A03.03.01.01.01.078%", values)
        self.assertIn("%汽金管理贷款余额%", values)


if __name__ == "__main__":
    unittest.main()
