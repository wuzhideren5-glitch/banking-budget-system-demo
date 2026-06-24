from __future__ import annotations

import unittest

from app.routers.org_product_helpers import (
    _build_data_entry_batch_export_workbook,
    _data_entry_sheet_title,
    _match_sheet_title_to_entity_table,
)


class OrgProductDataEntryBatchExportTests(unittest.TestCase):
    def test_sheet_title_roundtrip_with_matcher(self) -> None:
        title = _data_entry_sheet_title("AA", "全行", "业务状况表")
        matched = _match_sheet_title_to_entity_table(
            title,
            [("AA", "全行", "业务状况表"), ("A01", "泛微粒贷", "业务状况表")],
        )
        self.assertEqual(matched, ("AA", "业务状况表"))

    def test_batch_workbook_creates_multiple_sheets(self) -> None:
        payloads = [
            {
                "entity_code": "AA",
                "entity_name": "全行",
                "table_name": "业务状况表",
                "year": 2026,
                "month_index": 3,
                "metrics": [
                    {
                        "metric_code": "AA.01",
                        "metric_name": "营业收入",
                        "levelLabel": "二级",
                        "nature": "收入",
                        "values": {"prev_actual": "", "prev_budget": "", "prev_forecast": "", "months": {}},
                    }
                ],
            },
            {
                "entity_code": "A01",
                "entity_name": "泛微粒贷",
                "table_name": "业务状况表",
                "year": 2026,
                "month_index": 3,
                "metrics": [
                    {
                        "metric_code": "A01.01",
                        "metric_name": "营业收入",
                        "levelLabel": "二级",
                        "nature": "收入",
                        "values": {"prev_actual": "", "prev_budget": "", "prev_forecast": "", "months": {}},
                    }
                ],
            },
        ]
        wb = _build_data_entry_batch_export_workbook(payloads)
        self.assertEqual(len(wb.sheetnames), 2)
        candidates = [
            ("AA", "全行", "业务状况表"),
            ("A01", "泛微粒贷", "业务状况表"),
        ]
        for sheet_name in wb.sheetnames:
            matched = _match_sheet_title_to_entity_table(sheet_name, candidates)
            self.assertIsNotNone(matched)


if __name__ == "__main__":
    unittest.main()
