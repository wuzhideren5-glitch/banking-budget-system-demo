from __future__ import annotations

import unittest
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import budget_simulation as budget_simulation_module
from app.schemas import SimulationBaselineRow, SimulationResultRow


class BudgetSimulationRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_result_rows = budget_simulation_module.build_budget_simulation_result_rows
        self.previous_baseline_rows = budget_simulation_module.build_budget_simulation_baseline_rows
        self.previous_export_buffer = budget_simulation_module.build_budget_simulation_export_buffer
        self.previous_common_db_path = budget_simulation_module.common_db_path

        async def fake_baseline_rows(**kwargs):
            self.assertEqual(kwargs["common_path"], Path("common.db"))
            self.assertEqual(kwargs["budget_path"], Path("budget.db"))
            self.assertEqual(kwargs["version_id"], 8)
            self.assertEqual(kwargs["period_month_map"], {1: 1})
            self.assertEqual(kwargs["body"][0].indicator_code, "mgmt_loan_daily")
            return [
                SimulationBaselineRow(
                    indicator_code="MGMT_LOAN_DAILY",
                    indicator_name="管理贷款日均规模",
                    product_code="A01",
                    product_name="泛微粒贷",
                    value_type="金额",
                    baseline_value=42.5,
                    source_data_acct_codes=["A01.01.01.01.01.017"],
                    source_org_product_refs=["A01:业务状况表:A0111"],
                )
            ]

        async def fake_result_rows(common_path, body):
            self.assertEqual(common_path, Path("common.db"))
            self.assertEqual(len(body), 1)
            self.assertEqual(body[0].indicator_code, "mgmt_loan_daily")
            return [
                SimulationResultRow(
                    metric_group="盈利性指标",
                    indicator_code="PROFIT_NET",
                    indicator_name="净利润",
                    value_type="金额",
                    baseline_2025=1.0,
                    baseline_2026=2.0,
                    simulation_2026=3.0,
                )
            ]

        def fake_export_buffer(*, params, result_rows, baseline_rows=None):
            self.assertEqual(params[0].product_code, "a01")
            self.assertEqual(result_rows[0].indicator_code, "PROFIT_NET")
            self.assertEqual(baseline_rows[0].source_org_product_refs, ["A01:业务状况表:A0111"])
            return BytesIO(b"simulation workbook"), "budget_simulation_20260604120000.xlsx"

        budget_simulation_module.build_budget_simulation_baseline_rows = fake_baseline_rows
        budget_simulation_module.build_budget_simulation_result_rows = fake_result_rows
        budget_simulation_module.build_budget_simulation_export_buffer = fake_export_buffer
        budget_simulation_module.common_db_path = lambda: Path("common.db")

        async def editable_context():
            return Path("budget.db"), 2026, 8

        async def period_months(_year):
            return {1: 1}

        app = FastAPI()
        app.include_router(
            budget_simulation_module.build_budget_simulation_router(
                editable_context_provider=editable_context,
                get_year_period_months=period_months,
            )
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        budget_simulation_module.build_budget_simulation_result_rows = self.previous_result_rows
        budget_simulation_module.build_budget_simulation_baseline_rows = self.previous_baseline_rows
        budget_simulation_module.build_budget_simulation_export_buffer = self.previous_export_buffer
        budget_simulation_module.common_db_path = self.previous_common_db_path

    def test_export_uses_common_excel_download_contract(self) -> None:
        response = self.client.post(
            "/api/budget-simulation/export",
            json=[
                {
                    "indicator_code": "mgmt_loan_daily",
                    "product_code": "a01",
                    "simulate_value": 123.45,
                }
            ],
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"simulation workbook")
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        disposition = response.headers["content-disposition"]
        self.assertIn("filename=budget_simulation_20260604120000.xlsx", disposition)
        self.assertIn(
            "filename*=UTF-8''budget_simulation_20260604120000.xlsx",
            disposition,
        )

    def test_router_does_not_hand_roll_export_download_response(self) -> None:
        router_source = Path(budget_simulation_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("StreamingResponse", router_source)
        self.assertNotIn("filename*=", router_source)
        self.assertNotIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", router_source)
        self.assertIn("excel_streaming_response", router_source)


if __name__ == "__main__":
    unittest.main()
