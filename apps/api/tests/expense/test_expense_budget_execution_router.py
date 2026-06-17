from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.expense_budget_execution_export import ExpenseBudgetExecutionExportError
from app.services.expense_budget_execution_report_resolver import ExpenseBudgetExecutionReportError
from app.routers import expense_budget_execution as router_module


class ExpenseBudgetExecutionRouterTests(unittest.TestCase):
    def test_report_selection_centralizes_http_parameter_mapping(self) -> None:
        selection = router_module.build_expense_budget_execution_report_selection(
            mode="subject",
            perspective="owner_dept",
            keyword="差旅",
            include_zero_rows=True,
            entity_name="微众银行",
            group_name="个人金融事业群",
            owner_dept="A01 产品部",
            subject_id=12,
            report_month=3,
        )

        self.assertEqual(selection.mode, "subject")
        self.assertEqual(selection.perspective, "owner_dept")
        self.assertEqual(selection.keyword, "差旅")
        self.assertTrue(selection.include_zero_rows)
        self.assertEqual(selection.entity_name, "微众银行")
        self.assertEqual(selection.group_name, "个人金融事业群")
        self.assertEqual(selection.owner_dept, "A01 产品部")
        self.assertEqual(selection.subject_id, 12)
        self.assertEqual(selection.report_month, 3)

    def test_export_options_centralizes_http_body_mapping(self) -> None:
        body = router_module.ExpenseBudgetExecutionExportRequest(
            mode="template",
            perspective="owner_dept",
            amount_unit="ten_thousand",
            include_monthly_actuals=True,
            include_last_year_monthly_actuals=True,
        )

        options = router_module.build_expense_budget_execution_export_options(body)

        self.assertEqual(options.mode, "template")
        self.assertEqual(options.perspective, "owner_dept")
        self.assertEqual(options.amount_unit, "ten_thousand")
        self.assertTrue(options.include_monthly_actuals)
        self.assertTrue(options.include_last_year_monthly_actuals)

    def test_export_selection_centralizes_http_body_report_mapping(self) -> None:
        body = router_module.ExpenseBudgetExecutionExportRequest(
            mode="flat",
            perspective="owner_dept",
            amount_unit="million",
            keyword="差旅",
            include_zero_rows=True,
            entity_name="微众银行",
            group_name="个人金融事业群",
            owner_dept="A01 产品部",
            subject_id=12,
            report_month=3,
            include_monthly_actuals=True,
            include_last_year_monthly_actuals=True,
        )

        selection = router_module.build_expense_budget_execution_export_selection(body)

        self.assertEqual(selection.mode, "flat")
        self.assertEqual(selection.perspective, "owner_dept")
        self.assertEqual(selection.keyword, "差旅")
        self.assertTrue(selection.include_zero_rows)
        self.assertEqual(selection.entity_name, "微众银行")
        self.assertEqual(selection.group_name, "个人金融事业群")
        self.assertEqual(selection.owner_dept, "A01 产品部")
        self.assertEqual(selection.subject_id, 12)
        self.assertEqual(selection.report_month, 3)

    def test_report_error_mapping_centralizes_bad_request_response(self) -> None:
        http_error = router_module.expense_budget_execution_report_http_error(
            ExpenseBudgetExecutionReportError("report_month 仅支持 1-12")
        )

        self.assertEqual(http_error.status_code, 400)
        self.assertEqual(http_error.detail, "report_month 仅支持 1-12")

    def test_export_endpoint_maps_export_errors_to_bad_request(self) -> None:
        app = FastAPI()
        app.include_router(
            router_module.build_expense_budget_execution_router(
                editable_context_provider=AsyncMock(),
            )
        )

        with (
            patch.object(
                router_module,
                "_resolve_export_report_payload_service",
                new=AsyncMock(return_value={"note": "导出"}),
            ),
            patch.object(
                router_module,
                "build_expense_budget_execution_export",
                side_effect=ExpenseBudgetExecutionExportError("未知费用预算执行导出模式: legacy"),
            ),
        ):
            response = TestClient(app, raise_server_exceptions=False).post(
                "/api/expense-budget-execution/export",
                json={"mode": "query", "perspective": "group"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "未知费用预算执行导出模式: legacy"})


if __name__ == "__main__":
    unittest.main()
