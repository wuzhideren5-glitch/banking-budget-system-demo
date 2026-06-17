from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import dept_catalog as dept_catalog_module
from app.services.dept_catalog import DeptAccountImportResultWorkbook, DeptTreeExportWorkbook


async def no_operation_log(*_args, **_kwargs) -> None:
    return None


class DeptCatalogRouterTests(unittest.TestCase):
    def _build_app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(
            dept_catalog_module.build_dept_catalog_router(
                normalize_cell=lambda value: str(value or ""),
                color_row=lambda *_args: None,
                validate_dept_code_with_parent=lambda *_args: None,
                write_operation_log=no_operation_log,
            )
        )
        return app

    def test_import_apply_uses_common_excel_download_contract_and_keeps_import_headers(self) -> None:
        previous_common_db_path = dept_catalog_module.common_db_path
        previous_apply_command = dept_catalog_module.apply_dept_account_import_command

        async def fake_apply_command(
            path,
            content,
            mappings,
            *,
            normalize_cell,
            color_row,
            validate_dept_code_with_parent,
        ):
            self.assertEqual(path, "common.db")
            self.assertEqual(content, b"fake upload")
            self.assertEqual(mappings, {"entityName": "主体"})
            self.assertEqual(normalize_cell(" x "), " x ")
            color_row(None, 1, 1, "ok")
            self.assertIsNone(validate_dept_code_with_parent("Y101", 2, "Y1"))
            return DeptAccountImportResultWorkbook(
                content=b"fake result",
                total=4,
                success=3,
                overwrite=1,
                failed=1,
                filename="部门科目导入结果.xlsx",
            )

        dept_catalog_module.common_db_path = lambda: "common.db"
        dept_catalog_module.apply_dept_account_import_command = fake_apply_command
        client = TestClient(self._build_app(), raise_server_exceptions=False)
        try:
            response = client.post(
                "/api/dept-accounts/import-apply",
                files={"file": ("dept.xlsx", b"fake upload", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"mappings_json": '{"entityName":"主体"}'},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"fake result")
            self.assertEqual(response.headers["x-import-total"], "4")
            self.assertEqual(response.headers["x-import-success"], "3")
            self.assertEqual(response.headers["x-import-overwrite"], "1")
            self.assertEqual(response.headers["x-import-failed"], "1")
            self.assertIn("Content-Disposition", response.headers["access-control-expose-headers"])
            disposition = response.headers["content-disposition"]
            self.assertIn("filename=workbook.xlsx", disposition)
            self.assertIn("filename*=UTF-8''%E9%83%A8%E9%97%A8%E7%A7%91%E7%9B%AE", disposition)
        finally:
            dept_catalog_module.common_db_path = previous_common_db_path
            dept_catalog_module.apply_dept_account_import_command = previous_apply_command

    def test_export_dept_tree_uses_common_excel_download_contract(self) -> None:
        previous_common_db_path = dept_catalog_module.common_db_path
        previous_build_workbook = dept_catalog_module.build_dept_tree_export_workbook

        async def fake_build_workbook(path, *, template_path):
            self.assertEqual(path, "common.db")
            self.assertTrue(str(template_path).endswith("dept_acct_temp.xlsx"))
            return DeptTreeExportWorkbook(
                content=b"fake tree",
                filename="部门架构.xlsx",
            )

        dept_catalog_module.common_db_path = lambda: "common.db"
        dept_catalog_module.build_dept_tree_export_workbook = fake_build_workbook
        client = TestClient(self._build_app(), raise_server_exceptions=False)
        try:
            response = client.get("/api/dept-tree/export")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"fake tree")
            disposition = response.headers["content-disposition"]
            self.assertIn("filename=workbook.xlsx", disposition)
            self.assertIn("filename*=UTF-8''%E9%83%A8%E9%97%A8%E6%9E%B6%E6%9E%84", disposition)
        finally:
            dept_catalog_module.common_db_path = previous_common_db_path
            dept_catalog_module.build_dept_tree_export_workbook = previous_build_workbook


if __name__ == "__main__":
    unittest.main()
