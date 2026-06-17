from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import templates as templates_module


class TemplateRouterTests(unittest.TestCase):
    def test_template_download_uses_registered_stem_only(self) -> None:
        previous_dir = templates_module.settings.download_template_dir
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "budget_data_temp.xlsx").write_bytes(b"template")
            (root / "unregistered.xlsx").write_bytes(b"hidden")
            templates_module.settings.download_template_dir = root
            app = FastAPI()
            app.include_router(templates_module.router)
            client = TestClient(app)
            try:
                ok = client.get("/api/templates/budget_data_temp")
                self.assertEqual(ok.status_code, 200)
                self.assertEqual(ok.content, b"template")

                old_full_name = client.get("/api/templates/budget_data_temp.xlsx")
                self.assertEqual(old_full_name.status_code, 404)

                unregistered = client.get("/api/templates/unregistered")
                self.assertEqual(unregistered.status_code, 404)
            finally:
                templates_module.settings.download_template_dir = previous_dir

    def test_data_account_import_template_is_not_public_download_entry(self) -> None:
        previous_dir = templates_module.settings.download_template_dir
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data_acct_temp.xlsx").write_bytes(b"legacy template")
            templates_module.settings.download_template_dir = root
            app = FastAPI()
            app.include_router(templates_module.router)
            client = TestClient(app)
            try:
                response = client.get("/api/templates/data_acct_temp")
                self.assertEqual(response.status_code, 404)
                self.assertIn("未注册模板", response.json()["detail"])
            finally:
                templates_module.settings.download_template_dir = previous_dir


if __name__ == "__main__":
    unittest.main()
