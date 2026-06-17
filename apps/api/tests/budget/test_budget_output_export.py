from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app.schemas import (
    BudgetOutputDisplayReportResponse,
    BudgetOutputReportRowDto,
    BudgetOutputVersionDto,
    BudgetOutputVersionMetricDto,
)
from app.services.budget_output_export import (
    build_budget_output_display_report_export,
    build_budget_output_formula_workbook,
)


def metric(value: float) -> BudgetOutputVersionMetricDto:
    return BudgetOutputVersionMetricDto(annual_value=value, monthly_values=[0.0] * 12)


def sample_report() -> BudgetOutputDisplayReportResponse:
    version = BudgetOutputVersionDto(
        key="budget-1",
        label="26年预算",
        source="budget",
        year=2026,
        version_id=1,
        version_name="26年预算",
        current_month=1,
        selected_by_default=True,
    )
    return BudgetOutputDisplayReportResponse(
        title="预算展示报表",
        selected_year=2026,
        versions=[version],
        total_rows=[
            BudgetOutputReportRowDto(
                row_key="TOTAL.01",
                display_name="C指标",
                data_acct_code="A01.09.98.903",
                data_acct_name="C指标",
                budget_formula="A01.09.98.901 + A01.09.98.902",
                level=1,
                values_by_version={"budget-1": metric(30.0)},
            )
        ],
        total_formula_dependency_rows=[
            BudgetOutputReportRowDto(
                row_key="FORMULA_REF.A01.09.98.901",
                display_name="A指标",
                data_acct_code="A01.09.98.901",
                data_acct_name="A指标",
                level=8,
                values_by_version={"budget-1": metric(10.0)},
            ),
            BudgetOutputReportRowDto(
                row_key="FORMULA_REF.A01.09.98.902",
                display_name="B指标",
                data_acct_code="A01.09.98.902",
                data_acct_name="B指标",
                level=8,
                values_by_version={"budget-1": metric(20.0)},
            ),
        ],
    )


def header_column(ws, label: str) -> int:
    for col in range(1, ws.max_column + 1):
        if ws.cell(row=6, column=col).value == label:
            return col
    raise AssertionError(f"missing header {label}")


class BudgetOutputExportTests(unittest.TestCase):
    def test_formula_dependencies_are_exported_as_hidden_rows(self) -> None:
        report = sample_report()

        wb = build_budget_output_formula_workbook(report)
        ws = wb["预算全行总表"]

        self.assertEqual(str(ws["C7"].value).replace(" ", ""), "=C8+C9")
        self.assertTrue(ws.row_dimensions[8].hidden)
        self.assertTrue(ws.row_dimensions[9].hidden)
        self.assertEqual(ws["C8"].value, 10.0)
        self.assertEqual(ws["C9"].value, 20.0)

    def test_formula_workbook_appends_org_product_ref_columns(self) -> None:
        report = sample_report()

        wb = build_budget_output_formula_workbook(
            report,
            org_product_refs_by_runtime_ref_code={
                "A01.09.98.903": ["A01:业务状况表:A0198 C指标"],
            },
        )
        ws = wb["预算全行总表"]
        count_col = header_column(ws, "机构产品引用数量")
        source_col = header_column(ws, "机构产品来源")

        self.assertEqual(ws.cell(row=7, column=count_col).value, 1)
        self.assertEqual(ws.cell(row=7, column=source_col).value, "A01:业务状况表:A0198 C指标")

    def test_formula_workbook_prefers_display_config_org_product_ref(self) -> None:
        report = sample_report()
        report.total_rows[0].org_product_ref = "A01:业务状况表:A0198"
        report.total_rows[0].org_product_metric_name = "配置选择指标"

        wb = build_budget_output_formula_workbook(
            report,
            org_product_refs_by_runtime_ref_code={
                "A01.09.98.903": [
                    "A01:业务状况表:A0198 C指标",
                    "A02:另一张表:A0298 同数据科目",
                ],
            },
        )
        ws = wb["预算全行总表"]
        count_col = header_column(ws, "机构产品引用数量")
        source_col = header_column(ws, "机构产品来源")

        self.assertEqual(ws.cell(row=7, column=count_col).value, 1)
        self.assertEqual(ws.cell(row=7, column=source_col).value, "A01:业务状况表:A0198 配置选择指标")


class BudgetOutputExportWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_report_export_workflow_builds_report_workbook_and_filename(self) -> None:
        report = sample_report()
        report_builder = AsyncMock(return_value=report)

        async def editable_context_provider() -> tuple[Path, int, int]:
            return Path("common.db"), 2026, 1

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with sqlite3.connect(data_dir / "common.db") as conn:
                conn.execute(
                    """
                    CREATE TABLE org_product_metric_table (
                        entity_code TEXT NOT NULL,
                        entity_name TEXT NOT NULL,
                        table_id TEXT NOT NULL,
                        table_name TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (entity_code, table_name)
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO org_product_metric_table(
                      entity_code, entity_name, table_id, table_name, payload_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "A01",
                        "泛微粒贷",
                        "table-业务状况表",
                        "业务状况表",
                        json.dumps(
                            {
                                "metrics": [
                                    {
                                        "code": "A0198",
                                        "name": "C指标",
                                        "mapping_status": "MANUAL_CONFIRMED",
                                        "data_acct_code": "A01.09.98.903",
                                        "metric_node_code": "A01.09.98.903",
                                    }
                                ]
                            },
                            ensure_ascii=False,
                        ),
                        "2026-06-05T00:00:00Z",
                    ),
                )
            with patch("app.services.budget_output_export.build_budget_output_display_report", report_builder):
                export = await build_budget_output_display_report_export(
                    year=2026,
                    budget_version_id=1,
                    forecast_version_ids=[2],
                    editable_context_provider=editable_context_provider,
                    data_dir=data_dir,
                )

        self.assertEqual(export.filename, "2026年度预算展示全套报表.xlsx")
        self.assertEqual(export.workbook["预算全行总表"]["A1"].value, "2026年度预算全行总表")
        ws = export.workbook["预算全行总表"]
        count_col = header_column(ws, "机构产品引用数量")
        source_col = header_column(ws, "机构产品来源")
        self.assertEqual(ws.cell(row=7, column=count_col).value, 1)
        self.assertIn("A01:业务状况表:A0198", ws.cell(row=7, column=source_col).value)
        report_builder.assert_awaited_once_with(
            year=2026,
            budget_version_id=1,
            forecast_version_ids=[2],
            product_codes=None,
            editable_context_provider=editable_context_provider,
            data_dir=data_dir,
        )


if __name__ == "__main__":
    unittest.main()
