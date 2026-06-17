from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from app.db_bootstrap.expense import ensure_expense_actual_import_schema_sync
from app.services.expense_actual_import_batches import (
    ExpenseActualImportBatchMissingError,
    ExpenseActualImportExportMissingError,
    delete_expense_actual_import_batch,
    export_expense_actual_import_batch,
    list_expense_actual_import_batches,
    normalize_import_kind,
)


def _seed_batch(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        ensure_expense_actual_import_schema_sync(conn)
        cur = conn.execute(
            """
            INSERT INTO expense_actual_import_batch(
              import_kind, file_name, import_mode, periods_text, total_rows,
              matched_owner_rows, matched_subject_rows, unmatched_rows, created_at, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "current_year_actual",
                "actual.xlsx",
                "append",
                "2026-04",
                1,
                1,
                1,
                0,
                "2026-06-02T00:00:00Z",
                "note",
            ),
        )
        batch_id = int(cur.lastrowid)
        conn.execute(
            """
            INSERT INTO expense_actual_detail_raw(
              batch_id, import_kind, data_date, period_ym, period_text, org_code, org_name,
              dep_code, dep_name, subject_code, subject_name, journal_name, serial_no, line_desc,
              amount, fee_type_code, fee_type_name, bi_ai_source_code, bi_ai_source_name,
              manage_department_code, owner_name_raw, owner_name_mapped, monthly_caliber,
              budget_subject_raw, budget_subject_mapped, fee_major_mapped, fee_category_mapped,
              budget_release_caliber_mapped, manage_department2, special_control_tag,
              owner_matched, subject_matched, match_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                "current_year_actual",
                "2026-04-30",
                "2026-04",
                "2026年4月",
                "ORG",
                "费用部门",
                "DEP",
                "责任中心",
                "SUB",
                "科目",
                "日记帐",
                "SN001",
                "说明",
                123.45,
                "F01",
                "费用类别",
                "C01",
                "管控口径",
                "CD01",
                "原始归口",
                "映射归口",
                "月报口径",
                "原始预算科目",
                "映射预算科目",
                "费用大类",
                "费用类别一级",
                "预算发布",
                "归口2",
                "专项",
                1,
                1,
                "",
            ),
        )
        conn.commit()
        return batch_id
    finally:
        conn.close()


class ExpenseActualImportBatchServiceTests(unittest.TestCase):
    def test_normalize_import_kind_rejects_unknown_value(self) -> None:
        with self.assertRaises(ValueError):
            normalize_import_kind("legacy_actual")

    def test_list_export_and_delete_batch(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                batch_id = _seed_batch(db_path)

                batches = await list_expense_actual_import_batches(db_path)
                exported = await export_expense_actual_import_batch(db_path, batch_id=batch_id)
                out_path = Path(tmp) / "export.xlsx"
                out_path.write_bytes(exported.content)
                wb = load_workbook(out_path, data_only=True)
                ws = wb.active
                deleted = await delete_expense_actual_import_batch(db_path, batch_id=batch_id)

                self.assertEqual(len(batches), 1)
                self.assertEqual(batches[0].id, batch_id)
                self.assertEqual(batches[0].periods, ["2026-04"])
                self.assertIn(f"批次{batch_id}", exported.filename)
                self.assertEqual(ws["A1"].value, "数据日期")
                self.assertEqual(ws["O1"].value, "BI-AI源编码")
                self.assertEqual(ws["P1"].value, "BI-AI源名称")
                self.assertEqual(ws["X2"].value, "已匹配")
                self.assertEqual(deleted.deleted_rows, 1)
                with sqlite3.connect(db_path) as conn:
                    detail_count = conn.execute("SELECT COUNT(*) FROM expense_actual_detail_raw").fetchone()[0]
                    batch_count = conn.execute("SELECT COUNT(*) FROM expense_actual_import_batch").fetchone()[0]
                self.assertEqual(detail_count, 0)
                self.assertEqual(batch_count, 0)

        asyncio.run(run())

    def test_export_missing_batch_raises(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                conn = sqlite3.connect(db_path)
                try:
                    ensure_expense_actual_import_schema_sync(conn)
                    conn.commit()
                finally:
                    conn.close()

                with self.assertRaises(ExpenseActualImportExportMissingError):
                    await export_expense_actual_import_batch(db_path)
                with self.assertRaises(ExpenseActualImportBatchMissingError):
                    await export_expense_actual_import_batch(db_path, batch_id=999)
                with self.assertRaises(ExpenseActualImportBatchMissingError):
                    await delete_expense_actual_import_batch(db_path, batch_id=999)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
