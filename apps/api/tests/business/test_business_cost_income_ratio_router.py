from __future__ import annotations

import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.routers import business_cost_income_ratio as business_cost_income_ratio_module


async def _noop_operation_log(**_kwargs) -> None:
    return None


class BusinessCostIncomeRatioRouterTests(unittest.TestCase):
    def test_template_uses_common_excel_download_contract(self) -> None:
        previous_parse_months = business_cost_income_ratio_module.parse_months
        previous_template_workbook = business_cost_income_ratio_module.build_bcir_actual_import_template_workbook

        def fake_parse_months(raw):
            self.assertEqual(raw, "1,2")
            return (1, 2)

        def fake_template_workbook(*, year, product_codes, months):
            self.assertEqual(year, 2026)
            self.assertEqual(product_codes, ["A02", "A01"])
            self.assertEqual(months, (1, 2))
            wb = Workbook()
            wb.active.title = "实际数"
            wb.active["A1"] = "template"
            return wb

        try:
            business_cost_income_ratio_module.parse_months = fake_parse_months
            business_cost_income_ratio_module.build_bcir_actual_import_template_workbook = fake_template_workbook

            app = FastAPI()
            app.include_router(
                business_cost_income_ratio_module.build_business_cost_income_ratio_router(
                    write_operation_log=_noop_operation_log,
                )
            )
            response = TestClient(app).get(
                "/api/business-cost-income-ratio/template",
                params=[
                    ("product_codes", "A01"),
                    ("product_code", "A02"),
                    ("year", "2026"),
                    ("months", "1,2"),
                ],
            )
        finally:
            business_cost_income_ratio_module.parse_months = previous_parse_months
            business_cost_income_ratio_module.build_bcir_actual_import_template_workbook = previous_template_workbook

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        disposition = response.headers["content-disposition"]
        self.assertIn("filename=bcir_import_template.xlsx", disposition)
        self.assertIn("filename*=UTF-8''business_cost_income_import_template_2026.xlsx", disposition)

    def test_router_does_not_hand_roll_template_download_response(self) -> None:
        router_source = Path(business_cost_income_ratio_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("StreamingResponse", router_source)
        self.assertNotIn("BytesIO", router_source)
        self.assertNotIn("quote(", router_source)
        self.assertNotIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", router_source)
        self.assertNotIn("Content-Disposition", router_source)
        self.assertIn("workbook_streaming_response", router_source)


if __name__ == "__main__":
    unittest.main()
