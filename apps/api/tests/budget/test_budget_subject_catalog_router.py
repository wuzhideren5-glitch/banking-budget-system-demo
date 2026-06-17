from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import budget_subject_catalog as budget_subject_catalog_module
from app.services.budget_subject_catalog import BudgetSubjectCatalogWorkbook


async def no_operation_log(*_args, **_kwargs) -> None:
    return None


class BudgetSubjectCatalogRouterTests(unittest.TestCase):
    def test_export_uses_common_excel_download_contract(self) -> None:
        previous_list_query = budget_subject_catalog_module.list_budget_subject_catalog_query
        previous_build_workbook = budget_subject_catalog_module.build_budget_subject_catalog_workbook

        async def fake_list_query(*args, **kwargs):
            return []

        def fake_build_workbook(rows):
            self.assertEqual(rows, [])
            return BudgetSubjectCatalogWorkbook(
                content=b"fake workbook",
                filename="部门预算科目.xlsx",
            )

        budget_subject_catalog_module.list_budget_subject_catalog_query = fake_list_query
        budget_subject_catalog_module.build_budget_subject_catalog_workbook = fake_build_workbook
        app = FastAPI()
        app.include_router(
            budget_subject_catalog_module.build_budget_subject_catalog_router(
                write_operation_log=no_operation_log,
            )
        )
        client = TestClient(app)
        try:
            response = client.get("/api/budget-subject-catalog/export")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"fake workbook")
            self.assertEqual(
                response.headers["content-type"],
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            disposition = response.headers["content-disposition"]
            self.assertIn("filename=workbook.xlsx", disposition)
            self.assertIn("filename*=UTF-8''%E9%83%A8%E9%97%A8%E9%A2%84%E7%AE%97", disposition)
        finally:
            budget_subject_catalog_module.list_budget_subject_catalog_query = previous_list_query
            budget_subject_catalog_module.build_budget_subject_catalog_workbook = previous_build_workbook


if __name__ == "__main__":
    unittest.main()
