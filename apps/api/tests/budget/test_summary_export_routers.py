from __future__ import annotations

import unittest
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.routers import budget_summary_export as budget_summary_export_module
from app.routers import compare_summary_export as compare_summary_export_module


class SummaryExportRouterTests(unittest.TestCase):
    def test_budget_summary_export_router_delegates_to_service_callable(self) -> None:
        calls = []

        async def fake_export_budget_pivot_aggregate(**kwargs):
            calls.append(kwargs)
            return Response(content=b"budget export", media_type="application/octet-stream")

        app = FastAPI()
        app.include_router(
            budget_summary_export_module.build_budget_summary_export_router(
                export_budget_pivot_aggregate=fake_export_budget_pivot_aggregate,
            )
        )

        response = TestClient(app).post(
            "/api/budget-summary/export-aggregate-pivot",
            json={"row_field_ids": ["dept_level1"], "column_field_ids": ["month"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"budget export")
        self.assertEqual(calls[0]["output_filename"], "budget_pivot_aggregate_export.xlsx")

    def test_compare_summary_export_router_delegates_to_service_callable(self) -> None:
        calls = []

        async def fake_export_compare_pivot_aggregate(body):
            calls.append(body)
            return Response(content=b"compare export", media_type="application/octet-stream")

        app = FastAPI()
        app.include_router(
            compare_summary_export_module.build_compare_summary_export_router(
                export_compare_pivot_aggregate_callable=fake_export_compare_pivot_aggregate,
            )
        )

        response = TestClient(app).post(
            "/api/compare-summary/export-aggregate-pivot",
            json={"row_field_ids": ["dept_level1"], "column_field_ids": ["month"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"compare export")
        self.assertEqual(calls[0].row_field_ids, ["dept_level1"])

    def test_summary_export_routers_do_not_import_streaming_response(self) -> None:
        budget_router_source = Path(budget_summary_export_module.__file__).read_text(encoding="utf-8")
        compare_router_source = Path(compare_summary_export_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("StreamingResponse", budget_router_source)
        self.assertNotIn("StreamingResponse", compare_router_source)
        self.assertIn("Response", budget_router_source)
        self.assertIn("Response", compare_router_source)

    def test_main_export_adapter_keeps_only_live_export_adapters(self) -> None:
        main_source = (Path(__file__).parent / "app" / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("StreamingResponse", main_source)
        self.assertNotIn("JSONResponse", main_source)
        self.assertNotIn("from fastapi.responses import Response", main_source)
        self.assertNotIn("budget_summary_field_meta", main_source)
        self.assertNotIn("build_export_versions_info_text", main_source)
        self.assertNotIn("build_export_year_datetime_text", main_source)
        self.assertNotIn("normalize_summary_value", main_source)
        self.assertNotIn("write_template_pivot_data_area", main_source)
        self.assertNotIn("async def _export_budget_summary_formula_tree_workbook", main_source)
        self.assertNotIn("async def _export_budget_pivot_aggregate", main_source)
        self.assertNotIn("def _get_budget_summary_export_service", main_source)
        self.assertNotIn("async def _export_compare_pivot_aggregate", main_source)
        self.assertNotIn("def _get_compare_export_service", main_source)
        self.assertNotIn("async def _try_latest_version_id", main_source)


if __name__ == "__main__":
    unittest.main()
