from __future__ import annotations

import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import expense_actual_import as expense_actual_import_module
from app.services.expense_actual_import_batches import ExpenseActualImportExportWorkbook


async def no_operation_log(*_args, **_kwargs) -> None:
    return None


class ExpenseActualImportRouterTests(unittest.TestCase):
    def test_export_uses_common_excel_download_contract(self) -> None:
        previous_common_db_path = expense_actual_import_module.common_db_path
        previous_ensure_ready = expense_actual_import_module.ensure_expense_actual_import_schema_ready
        previous_export_batch = expense_actual_import_module.export_expense_actual_import_batch

        async def fake_ensure_ready(path):
            self.assertEqual(path, "common.db")

        async def fake_export_batch(path, *, batch_id, import_kind):
            self.assertEqual(path, "common.db")
            self.assertEqual(batch_id, 7)
            self.assertEqual(import_kind, "prior_year_actual")
            return ExpenseActualImportExportWorkbook(
                content=b"fake workbook",
                filename="上年实际导入_匹配结果_批次7.xlsx",
            )

        expense_actual_import_module.common_db_path = lambda: "common.db"
        expense_actual_import_module.ensure_expense_actual_import_schema_ready = fake_ensure_ready
        expense_actual_import_module.export_expense_actual_import_batch = fake_export_batch
        app = FastAPI()
        app.include_router(
            expense_actual_import_module.build_expense_actual_import_router(
                write_operation_log=no_operation_log,
            )
        )
        client = TestClient(app)
        try:
            response = client.get(
                "/api/expense-actual-import/export",
                params={"batch_id": 7, "import_kind": "prior_year_actual"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"fake workbook")
            self.assertEqual(
                response.headers["content-type"],
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            self.assertEqual(response.headers["access-control-expose-headers"], "Content-Disposition")
            disposition = response.headers["content-disposition"]
            self.assertIn("filename=expense-actual-matched.xlsx", disposition)
            self.assertIn("filename*=UTF-8''%E4%B8%8A%E5%B9%B4%E5%AE%9E%E9%99%85", disposition)
        finally:
            expense_actual_import_module.common_db_path = previous_common_db_path
            expense_actual_import_module.ensure_expense_actual_import_schema_ready = previous_ensure_ready
            expense_actual_import_module.export_expense_actual_import_batch = previous_export_batch

    def test_router_does_not_hand_roll_excel_download_response(self) -> None:
        router_source = Path(expense_actual_import_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("StreamingResponse", router_source)
        self.assertNotIn("BytesIO", router_source)
        self.assertNotIn("filename*=", router_source)
        self.assertNotIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", router_source)
        self.assertIn("excel_streaming_response", router_source)


if __name__ == "__main__":
    unittest.main()
