from __future__ import annotations

from io import BytesIO
import unittest

from openpyxl import Workbook

from app.services.expense_forecast_import_parser import (
    ExpenseForecastImportParseError,
    parse_expense_forecast_group_import_file,
    parse_expense_forecast_import_file,
    parse_expense_forecast_subject_import_file,
)


def workbook_bytes(rows: list[list[object | None]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


class ExpenseForecastImportParserTests(unittest.TestCase):
    def test_regular_import_parses_month_and_annual_fields(self) -> None:
        raw = workbook_bytes(
            [
                ["费用预测表"],
                ["元数据"],
                ["预算科目", "M1", "2月", "业务报送", "资划建议"],
                ["差旅费", "1,234.56", "bad", "300", None],
            ]
        )

        rows = parse_expense_forecast_import_file(raw)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["budget_subject"], "差旅费")
        self.assertEqual(rows[0]["field_name"], "month_forecast")
        self.assertEqual(rows[0]["month"], 1)
        self.assertEqual(rows[0]["value"], 1234.56)
        self.assertIsNone(rows[0]["error"])
        self.assertEqual(rows[1]["month"], 2)
        self.assertEqual(rows[1]["error"], "月份 M2 不是有效数字")
        self.assertEqual(rows[2]["field_name"], "business_submission")
        self.assertEqual(rows[2]["field_label"], "业务报送")
        self.assertEqual(rows[2]["value"], 300.0)

    def test_group_import_assigns_rows_to_owner_sections(self) -> None:
        raw = workbook_bytes(
            [
                ["费用预测表（按事业群导出）"],
                ["元数据"],
                ["预算科目", "M1", "业务报送"],
                ["事业群A", None, None],
                ["  费用合计", None, None],
                ["  部门A", None, None],
                ["    差旅费", 100, 200],
                ["  部门B", None, None],
                ["    差旅费", 300, 400],
            ]
        )

        rows = parse_expense_forecast_group_import_file(raw, owner_names=["部门A", "部门B"])

        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["owner_name"], "部门A")
        self.assertEqual(rows[0]["budget_subject"], "差旅费")
        self.assertEqual(rows[0]["value"], 100.0)
        self.assertEqual(rows[1]["field_name"], "business_submission")
        self.assertEqual(rows[2]["owner_name"], "部门B")
        self.assertEqual(rows[2]["value"], 300.0)

    def test_subject_import_uses_default_owner_when_column_is_blank(self) -> None:
        raw = workbook_bytes(
            [
                ["费用预测表"],
                ["费用归属部门", "M1", "业务报送"],
                [None, "5，000", "700"],
            ]
        )

        rows = parse_expense_forecast_subject_import_file(
            raw,
            subject_name="差旅费",
            default_owner_name="部门A",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["owner_name"], "部门A")
        self.assertEqual(rows[0]["budget_subject"], "差旅费")
        self.assertEqual(rows[0]["value"], 5000.0)
        self.assertEqual(rows[1]["field_name"], "business_submission")

    def test_group_import_rejects_non_group_workbook(self) -> None:
        raw = workbook_bytes(
            [
                ["费用预测表"],
                ["预算科目", "M1"],
                ["差旅费", 1],
            ]
        )

        with self.assertRaises(ExpenseForecastImportParseError) as ctx:
            parse_expense_forecast_group_import_file(raw, owner_names=["部门A"])

        self.assertIn("按事业群导出的Excel模板", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
