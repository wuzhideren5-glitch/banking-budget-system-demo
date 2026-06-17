from __future__ import annotations

import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import expense_forecast as expense_forecast_module


async def _no_operation_log(*_args, **_kwargs) -> None:
    return None


def _view_model(*, year: int, forecast_version: str, scope_type: str, scope_value: str) -> dict[str, Any]:
    return {
        "year": year,
        "forecast_version": forecast_version,
        "scope_type": scope_type,
        "scope_value": scope_value,
        "actual_cutoff_month": 0,
        "rows": [],
    }


class ExpenseForecastRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_scope_read_model = expense_forecast_module.build_expense_forecast_scope_read_model
        self.previous_export_workflow = expense_forecast_module.build_expense_forecast_export_from_source
        self.previous_group_export_workflow = expense_forecast_module.build_expense_forecast_group_export_from_source
        self.previous_owner_group_options = expense_forecast_module.load_expense_forecast_owner_group_options
        self.previous_common_db_path = expense_forecast_module.common_db_path

        async def fake_scope_read_model(*, year, forecast_version, scope_type, scope_value, source):
            return _view_model(
                year=year,
                forecast_version=forecast_version,
                scope_type=scope_type,
                scope_value=scope_value,
            )

        async def fake_export_workflow(**kwargs):
            self.assertEqual(kwargs["year"], 2026)
            self.assertEqual(kwargs["forecast_version"], "V1")
            return SimpleNamespace(stream=BytesIO(b"forecast workbook"), display_file_name="费用预测表_2026_V1.xlsx")

        async def fake_group_export_workflow(**kwargs):
            self.assertEqual(kwargs["group_name"], "事业群A")
            return SimpleNamespace(stream=BytesIO(b"group workbook"), display_file_name="费用预测表_2026_事业群A.xlsx")

        async def fake_owner_group_options(_path):
            return [
                {
                    "group_value": "事业群A",
                    "group_label": "事业群A",
                    "owner_options": [{"value": "部门A", "label": "部门A"}],
                }
            ]

        expense_forecast_module.build_expense_forecast_scope_read_model = fake_scope_read_model
        expense_forecast_module.build_expense_forecast_export_from_source = fake_export_workflow
        expense_forecast_module.build_expense_forecast_group_export_from_source = fake_group_export_workflow
        expense_forecast_module.load_expense_forecast_owner_group_options = fake_owner_group_options
        expense_forecast_module.common_db_path = lambda: "common.db"

        app = FastAPI()
        app.include_router(
            expense_forecast_module.build_expense_forecast_router(
                default_year=2026,
                write_operation_log=_no_operation_log,
            )
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        expense_forecast_module.build_expense_forecast_scope_read_model = self.previous_scope_read_model
        expense_forecast_module.build_expense_forecast_export_from_source = self.previous_export_workflow
        expense_forecast_module.build_expense_forecast_group_export_from_source = self.previous_group_export_workflow
        expense_forecast_module.load_expense_forecast_owner_group_options = self.previous_owner_group_options
        expense_forecast_module.common_db_path = self.previous_common_db_path

    def test_export_uses_common_excel_download_contract(self) -> None:
        response = self.client.post(
            "/api/expense-forecast/export",
            json={
                "year": 2026,
                "forecast_version": "V1",
                "scope_type": "owner",
                "scope_value": "部门A",
                "compile_mode": "scope",
                "amount_unit": "yuan",
                "exclude_fields": [],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"forecast workbook")
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        disposition = response.headers["content-disposition"]
        self.assertIn("filename=expense-forecast.xlsx", disposition)
        self.assertIn("filename*=UTF-8''%E8%B4%B9%E7%94%A8%E9%A2%84%E6%B5%8B", disposition)

    def test_group_export_uses_common_excel_download_contract(self) -> None:
        response = self.client.post(
            "/api/expense-forecast/export-by-group",
            json={
                "year": "2026",
                "forecast_version": "V1",
                "group_name": "事业群A",
                "amount_unit": "yuan",
                "exclude_fields": [],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"group workbook")
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        disposition = response.headers["content-disposition"]
        self.assertIn("filename=expense-forecast-group.xlsx", disposition)
        self.assertIn("filename*=UTF-8''%E8%B4%B9%E7%94%A8%E9%A2%84%E6%B5%8B", disposition)

    def test_router_does_not_hand_roll_export_download_responses(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("StreamingResponse", router_source)
        self.assertNotIn("filename*=", router_source)
        self.assertNotIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", router_source)
        self.assertIn("excel_streaming_response", router_source)

    def test_router_delegates_trace_read_model_assembly(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("build_expense_forecast_trace_read_model(", router_source)
        self.assertIn("build_expense_forecast_trace_read_model_from_source", router_source)

    def test_trace_source_exposes_trace_read_model_runtime_adapters(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")
        trace_source = router_source.split("class _ExpenseForecastTraceSource:", 1)[1].split(
            "class _ExpenseForecastOverrideSource:",
            1,
        )[0]
        trace_route = router_source.split("async def get_expense_forecast_trace(", 1)[1].split(
            "@router.post(\"/api/expense-forecast/override\"",
            1,
        )[0]

        self.assertIn("load_calc_result_map", trace_source)
        self.assertIn("load_override_map", trace_source)
        self.assertIn("load_forecast_map", trace_source)
        self.assertIn("load_rule_map", trace_source)
        self.assertIn("source=_ExpenseForecastTraceSource()", trace_route)
        self.assertNotIn("source=_ExpenseForecastViewSource()", trace_route)

    def test_router_delegates_override_workflows(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("save_expense_forecast_override(", router_source)
        self.assertNotIn("delete_expense_forecast_override_value(", router_source)
        self.assertIn("save_expense_forecast_override_with_rule_check", router_source)
        self.assertIn("delete_expense_forecast_override_with_restore", router_source)

    def test_override_source_exposes_override_workflow_runtime_adapters(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")
        override_source = router_source.split("class _ExpenseForecastOverrideSource:", 1)[1].split(
            "class _ExpenseForecastExportSource:",
            1,
        )[0]
        save_route = router_source.split("async def override_expense_forecast_value(", 1)[1].split(
            "@router.delete(\"/api/expense-forecast/override\"",
            1,
        )[0]
        delete_route = router_source.split("async def delete_expense_forecast_override(", 1)[1].split(
            "return router",
            1,
        )[0]

        self.assertIn("load_rule_map", override_source)
        self.assertIn("load_calc_result_map", override_source)
        self.assertIn("load_actual_cutoff_month", override_source)
        self.assertIn("source=_ExpenseForecastOverrideSource()", save_route)
        self.assertIn("source=_ExpenseForecastOverrideSource()", delete_route)
        self.assertNotIn("source=_ExpenseForecastViewSource()", save_route)
        self.assertNotIn("source=_ExpenseForecastViewSource()", delete_route)

    def test_router_delegates_cell_workflow(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("def _safe_float", router_source)
        self.assertNotIn("upsert_expense_forecast_cell_value(", router_source)
        self.assertNotIn("该预算科目仅归口管理部门", router_source)
        self.assertNotIn("该月份已有实际数", router_source)
        self.assertNotIn("写入费用预测", router_source)
        self.assertIn("upsert_expense_forecast_cell_with_validation", router_source)

    def test_cell_source_exposes_cell_workflow_runtime_adapters(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")
        cell_source = router_source.split("class _ExpenseForecastCellSource:", 1)[1].split(
            "class _ExpenseForecastViewSource:",
            1,
        )[0]
        cell_route = router_source.split("async def upsert_expense_forecast_cell(", 1)[1].split(
            "@router.post(\"/api/expense-forecast/import-preview\"",
            1,
        )[0]

        self.assertIn("load_subject_lookup", cell_source)
        self.assertIn("load_manage_department_map", cell_source)
        self.assertIn("load_actual_cutoff_month", cell_source)
        self.assertIn("load_rule_map", cell_source)
        self.assertIn("recalculate_rules", cell_source)
        self.assertIn("write_operation_log", cell_source)
        self.assertIn("source=_ExpenseForecastCellSource()", cell_route)
        self.assertNotIn("source=_ExpenseForecastViewSource()", cell_route)

    def test_router_delegates_import_apply_workflow(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("apply_expense_forecast_import_rows(", router_source)
        self.assertNotIn("for owner_name, target_subject_id in apply_result.recalc_targets", router_source)
        self.assertNotIn("导入费用预测", router_source)
        self.assertIn("apply_expense_forecast_import_rows_with_recalculation", router_source)

    def test_import_apply_source_exposes_import_apply_runtime_adapters(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")
        import_apply_source = router_source.split("class _ExpenseForecastImportApplySource:", 1)[1].split(
            "class _ExpenseForecastViewSource:",
            1,
        )[0]
        apply_route = router_source.split("async def apply_expense_forecast_import(", 1)[1].split(
            "@router.post(\"/api/expense-forecast/export\"",
            1,
        )[0]

        self.assertIn("recalculate_rules", import_apply_source)
        self.assertIn("write_operation_log", import_apply_source)
        self.assertIn("source=_ExpenseForecastImportApplySource()", apply_route)
        self.assertNotIn("source=_ExpenseForecastViewSource()", apply_route)

    def test_router_delegates_import_preview_workflow(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("build_expense_forecast_import_plan(", router_source)
        self.assertNotIn("parse_expense_forecast_import_rows_for_plan(", router_source)
        self.assertNotIn("evaluate_expense_forecast_import_preview(", router_source)
        self.assertIn("build_expense_forecast_import_preview_from_source", router_source)

    def test_import_preview_source_exposes_import_preview_runtime_adapters(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")
        import_preview_source = router_source.split("class _ExpenseForecastImportPreviewSource:", 1)[1].split(
            "class _ExpenseForecastViewSource:",
            1,
        )[0]
        preview_workflow = router_source.split("async def _preview_import(", 1)[1].split(
            "@router.get(\"/api/expense-forecast/meta\"",
            1,
        )[0]

        self.assertIn("load_subject_lookup", import_preview_source)
        self.assertIn("resolve_scope_owners", import_preview_source)
        self.assertIn("load_actual_cutoff_month", import_preview_source)
        self.assertIn("load_manage_department_map", import_preview_source)
        self.assertIn("load_forecast_map", import_preview_source)
        self.assertIn("load_rule_map", import_preview_source)
        self.assertIn("load_annual_input_map", import_preview_source)
        self.assertIn("load_calc_result_map", import_preview_source)
        self.assertIn("source=_ExpenseForecastImportPreviewSource()", preview_workflow)
        self.assertNotIn("source=_ExpenseForecastViewSource()", preview_workflow)

    def test_router_delegates_export_workflows(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("build_expense_forecast_export_plan(", router_source)
        self.assertNotIn("build_expense_forecast_group_export_plan(", router_source)
        self.assertNotIn("build_expense_forecast_export_workbook(", router_source)
        self.assertNotIn("build_expense_forecast_group_export_workbook(", router_source)
        self.assertIn("build_expense_forecast_export_from_source", router_source)
        self.assertIn("build_expense_forecast_group_export_from_source", router_source)

    def test_recalculation_source_only_exposes_recalculation_runtime_adapters(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")
        recalculation_source = router_source.split("class _ExpenseForecastRecalculationSource:", 1)[1].split(
            "class _ExpenseForecastRuleSaveSource:",
            1,
        )[0]

        self.assertNotIn("build_scope_view", recalculation_source)
        self.assertNotIn("build_subject_view", recalculation_source)
        self.assertNotIn("load_owner_group_options", recalculation_source)
        self.assertIn("save_recalculation_results", recalculation_source)

    def test_rule_import_preview_and_apply_use_separate_runtime_adapters(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")

        self.assertIn("class _ExpenseForecastRuleImportPreviewSource:", router_source)
        self.assertIn("class _ExpenseForecastRuleImportApplySource(_ExpenseForecastRuleImportPreviewSource):", router_source)
        preview_source = router_source.split("class _ExpenseForecastRuleImportPreviewSource:", 1)[1].split(
            "class _ExpenseForecastRuleImportApplySource(_ExpenseForecastRuleImportPreviewSource):",
            1,
        )[0]
        apply_source = router_source.split(
            "class _ExpenseForecastRuleImportApplySource(_ExpenseForecastRuleImportPreviewSource):",
            1,
        )[1].split(
            "async def _preview_rule_import(",
            1,
        )[0]
        preview_workflow = router_source.split("async def _preview_rule_import(", 1)[1].split(
            "async def _apply_rule_import(",
            1,
        )[0]
        apply_workflow = router_source.split("async def _apply_rule_import(", 1)[1].split(
            "def _download_rule_template(",
            1,
        )[0]

        self.assertIn("load_subject_lookup", preview_source)
        self.assertIn("load_rule_rows", preview_source)
        self.assertNotIn("save_rule", preview_source)
        self.assertIn("save_rule", apply_source)
        self.assertIn("source=_ExpenseForecastRuleImportPreviewSource()", preview_workflow)
        self.assertIn("source=_ExpenseForecastRuleImportApplySource()", apply_workflow)
        self.assertNotIn("source=_ExpenseForecastRuleImportSource()", router_source)

    def test_rule_copy_and_import_save_payload_without_http_request_dto(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")
        copy_source = router_source.split("class _ExpenseForecastRuleCopySource:", 1)[1].split(
            "async def _copy_rules(",
            1,
        )[0]
        import_apply_source = router_source.split(
            "class _ExpenseForecastRuleImportApplySource(_ExpenseForecastRuleImportPreviewSource):",
            1,
        )[1].split(
            "async def _preview_rule_import(",
            1,
        )[0]

        self.assertIn("async def _save_rule_payload(", router_source)
        self.assertIn("_save_rule_payload(rule=rule, rule_id=rule_id)", copy_source)
        self.assertIn("_save_rule_payload(rule=rule, rule_id=rule_id)", import_apply_source)
        self.assertNotIn("ExpenseForecastRuleSaveRequest.model_validate(rule)", router_source)

    def test_regular_and_group_export_use_separate_runtime_adapters(self) -> None:
        router_source = Path(expense_forecast_module.__file__).read_text(encoding="utf-8")

        self.assertIn("class _ExpenseForecastRegularExportSource:", router_source)
        self.assertIn("class _ExpenseForecastGroupExportSource:", router_source)
        regular_export_source = router_source.split("class _ExpenseForecastRegularExportSource:", 1)[1].split(
            "class _ExpenseForecastGroupExportSource:",
            1,
        )[0]
        group_export_source = router_source.split("class _ExpenseForecastGroupExportSource:", 1)[1].split(
            "async def _build_view(",
            1,
        )[0]
        view_source = router_source.split("class _ExpenseForecastViewSource:", 1)[1].split(
            "class _ExpenseForecastRegularExportSource:",
            1,
        )[0]
        regular_export_route = router_source.split("async def export_expense_forecast(", 1)[1].split(
            "@router.post(\"/api/expense-forecast/export-by-group\")",
            1,
        )[0]
        group_export_route = router_source.split("async def export_expense_forecast_by_group(", 1)[1].split(
            "register_expense_forecast_rule_routes(",
            1,
        )[0]

        self.assertIn("build_scope_view", regular_export_source)
        self.assertIn("build_subject_view", regular_export_source)
        self.assertNotIn("load_owner_group_options", regular_export_source)
        self.assertIn("build_scope_view", group_export_source)
        self.assertIn("load_owner_group_options", group_export_source)
        self.assertNotIn("build_subject_view", group_export_source)
        self.assertNotIn("build_scope_view", view_source)
        self.assertNotIn("build_subject_view", view_source)
        self.assertNotIn("load_owner_group_options", view_source)
        self.assertIn("source=_ExpenseForecastRegularExportSource()", regular_export_route)
        self.assertIn("source=_ExpenseForecastGroupExportSource()", group_export_route)
        self.assertNotIn("source=_ExpenseForecastExportSource()", router_source)


if __name__ == "__main__":
    unittest.main()
