from __future__ import annotations

from io import BytesIO
import unittest

from openpyxl import Workbook

from app.services.expense_actual_import_parser import (
    ExpenseActualImportParseError,
    FrameworkContext,
    build_preview_response,
    normalize_key,
    parse_actual_file,
)


def _xlsx_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "费用执行表"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def _context() -> FrameworkContext:
    ctx = FrameworkContext()
    ctx.owner_names.add("映射归口")
    ctx.owner_alias_map[normalize_key("映射归口")] = "映射归口"
    ctx.manage_dept_owner_map[normalize_key("原始管理部门")] = "映射归口"
    ctx.manage_dept_owner_map[normalize_key("R列部门")] = "归口管理部门2"

    ctx.subject_names.add("映射预算科目")
    ctx.subject_alias_map[normalize_key("映射预算科目")] = "映射预算科目"
    ctx.bi_ai_subject_mapping[normalize_key("BI6")] = "映射预算科目"
    ctx.bi_ai_subject_mapping_detail[normalize_key("BI6")] = ("费用大类", "费用类别一级", "预算发布")
    return ctx


class ExpenseActualImportParserTests(unittest.TestCase):
    def test_parse_xlsx_maps_owner_subject_bi_detail_and_preview(self) -> None:
        headers = [
            "数据日期",
            "期间",
            "费用发生部门编码",
            "费用发生部门",
            "责任中心编码",
            "责任中心",
            "科目描述",
            "金额",
            "费用类别编码",
            "费用类别",
            "管控口径编码",
            "管控口径名称",
            "归口管理部门编码",
            "费用归属部门",
            "预算科目",
            "专项场景",
            "空列",
            "归口管理部门2",
            "科目编码",
        ]
        raw = _xlsx_bytes(
            headers,
            [
                [
                    "2026-04-30",
                    "2026年4月",
                    "ORG",
                    "费用部门",
                    "DEP",
                    "责任中心",
                    "其他外包服务费",
                    "1,234.56",
                    "F01",
                    "费用类别",
                    "C01",
                    "管控口径",
                    "CD01",
                    "原始管理部门",
                    "BI6",
                    "运营其他",
                    "",
                    "R列部门",
                    "SUB",
                ]
            ],
        )

        rows = parse_actual_file("actual.xlsx", raw, _context())
        preview = build_preview_response("actual.xlsx", rows)
        row = rows[0]

        self.assertEqual(row.period_ym, "2026-04")
        self.assertEqual(row.amount, 1234.56)
        self.assertEqual(row.owner_name_mapped, "映射归口")
        self.assertEqual(row.budget_subject_mapped, "映射预算科目")
        self.assertEqual(row.fee_major_mapped, "费用大类")
        self.assertEqual(row.fee_category_mapped, "费用类别一级")
        self.assertEqual(row.budget_release_caliber_mapped, "预算发布")
        self.assertEqual(row.manage_department2, "归口管理部门2")
        self.assertEqual(row.special_control_tag, "抵押")
        self.assertEqual(row.match_note, None)
        self.assertEqual(preview.row_count, 1)
        self.assertEqual(preview.periods, ["2026-04"])
        self.assertEqual(preview.matched_owner_rows, 1)
        self.assertEqual(preview.matched_subject_rows, 1)
        self.assertEqual(preview.unmatched_rows, 0)
        self.assertEqual(preview.preview_rows[0].match_status, "已匹配")

    def test_parse_xlsx_rejects_missing_required_headers(self) -> None:
        raw = _xlsx_bytes(["期间", "金额"], [["2026-04", 1]])

        with self.assertRaisesRegex(ExpenseActualImportParseError, "导入文件缺少字段"):
            parse_actual_file("bad.xlsx", raw, _context())

    def test_parse_xlsx_rejects_position_only_required_columns(self) -> None:
        headers = [
            "数据日期",
            "期间",
            "费用发生部门编码",
            "费用发生部门",
            "责任中心编码",
            "责任中心",
            "科目编码",
            "科目描述",
            "金额",
            "费用类别编码",
            "费用类别",
            "管控口径编码",
            "管控口径名称",
            "归口管理部门编码",
            "",
            "预算科目",
        ]
        raw = _xlsx_bytes(headers, [["2026-04-30"] + [""] * (len(headers) - 1)])

        with self.assertRaisesRegex(ExpenseActualImportParseError, "费用归属部门"):
            parse_actual_file("position-only.xlsx", raw, _context())

    def test_parse_xlsx_does_not_match_bi_ai_by_fixed_column_position(self) -> None:
        headers = [
            "数据日期",
            "期间",
            "费用发生部门编码",
            "费用发生部门",
            "责任中心编码",
            "责任中心",
            "科目描述",
            "金额",
            "费用类别编码",
            "费用类别",
            "管控口径编码",
            "管控口径名称",
            "归口管理部门编码",
            "费用归属部门",
            "非口径列",
            "专项场景",
            "空列",
            "归口管理部门2",
            "科目编码",
            "预算科目",
        ]
        raw = _xlsx_bytes(
            headers,
            [
                [
                    "2026-04-30",
                    "2026年4月",
                    "ORG",
                    "费用部门",
                    "DEP",
                    "责任中心",
                    "其他外包服务费",
                    "100",
                    "F01",
                    "费用类别",
                    "",
                    "",
                    "CD01",
                    "原始管理部门",
                    "BI6",
                    "",
                    "",
                    "R列部门",
                    "SUB",
                    "",
                ]
            ],
        )

        row = parse_actual_file("actual.xlsx", raw, _context())[0]

        self.assertEqual(row.fee_major_mapped, "")
        self.assertEqual(row.fee_category_mapped, "")
        self.assertEqual(row.budget_release_caliber_mapped, "")


if __name__ == "__main__":
    unittest.main()
