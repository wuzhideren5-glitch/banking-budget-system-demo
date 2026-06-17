from __future__ import annotations

import unittest
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import chart_write as chart_write_module
from app.services.chart_ppt_export import ChartPptExportFile, PPTX_MEDIA_TYPE


class ChartWriteRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_export_file_builder = chart_write_module.build_chart_ppt_export_file

        def fake_export_file(req):
            self.assertEqual(req.chart_type, "bar")
            self.assertEqual(req.title, "经营分析")
            return ChartPptExportFile(
                content=BytesIO(b"pptx bytes"),
                filename="chart_export_20260604.pptx",
            )

        chart_write_module.build_chart_ppt_export_file = fake_export_file

        async def version_options_provider():
            return []

        app = FastAPI()
        app.include_router(
            chart_write_module.build_chart_write_router(
                chart_version_options_provider=version_options_provider,
                extract_runtime_metric_ref_code_from_name=lambda _name: None,
            )
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        chart_write_module.build_chart_ppt_export_file = self.previous_export_file_builder

    def test_export_ppt_uses_common_binary_download_contract(self) -> None:
        response = self.client.post(
            "/api/chart/export-ppt",
            json={
                "chart_type": "bar",
                "title": "经营分析",
                "categories": ["M01"],
                "series": [{"name": "余额", "values": [1.0]}],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"pptx bytes")
        self.assertEqual(response.headers["content-type"], PPTX_MEDIA_TYPE)
        disposition = response.headers["content-disposition"]
        self.assertIn("filename=chart_export_20260604.pptx", disposition)
        self.assertIn("filename*=UTF-8''chart_export_20260604.pptx", disposition)

    def test_router_does_not_hand_roll_ppt_download_response(self) -> None:
        router_source = Path(chart_write_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("StreamingResponse", router_source)
        self.assertNotIn("Content-Disposition", router_source)
        self.assertIn("binary_streaming_response", router_source)


if __name__ == "__main__":
    unittest.main()
