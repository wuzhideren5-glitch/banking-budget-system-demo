from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core.config import settings
from app.services.expense_budget_execution_actuals import ExpenseActualError, load_actual_rows
from app.services.expense_budget_execution_framework import (
    FrameworkBudgetDepartmentRow,
    FrameworkSubjectRow,
    ParsedFramework,
    build_framework_context,
)


def _framework_context():
    return build_framework_context(
        ParsedFramework(
            source_file=Path("framework.xlsx"),
            budget_departments=[
                FrameworkBudgetDepartmentRow("微众银行", "个人金融事业群", "A01 零售部", "A01 零售部")
            ],
            product_departments=[],
            subjects=[FrameworkSubjectRow("一级", "业务费用", "A01 零售部", "0", 1)],
        )
    )


def _create_common_db(data_dir: Path) -> None:
    conn = sqlite3.connect(data_dir / "common.db")
    try:
        conn.executescript(
            """
            CREATE TABLE expense_actual_import_batch (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              import_kind TEXT NOT NULL DEFAULT 'current_year_actual',
              file_name TEXT NOT NULL,
              import_mode TEXT NOT NULL DEFAULT 'append',
              periods_text TEXT,
              total_rows INTEGER NOT NULL DEFAULT 0,
              matched_owner_rows INTEGER NOT NULL DEFAULT 0,
              matched_subject_rows INTEGER NOT NULL DEFAULT 0,
              unmatched_rows INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              note TEXT
            );
            CREATE TABLE expense_actual_detail_raw (
              batch_id INTEGER REFERENCES expense_actual_import_batch(id) ON DELETE SET NULL,
              import_kind TEXT NOT NULL DEFAULT 'current_year_actual',
              owner_name_mapped TEXT,
              budget_subject_mapped TEXT,
              fee_major_mapped TEXT,
              fee_category_mapped TEXT,
              budget_release_caliber_mapped TEXT,
              period_ym TEXT,
              amount REAL,
              owner_matched INTEGER,
              subject_matched INTEGER
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


class ExpenseBudgetExecutionActualsTests(unittest.IsolatedAsyncioTestCase):
    async def test_load_actual_rows_uses_current_year_raw_detail_import(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            _create_common_db(data_dir)
            conn = sqlite3.connect(data_dir / "common.db")
            try:
                conn.executescript(
                    """
                    INSERT INTO expense_actual_import_batch(
                      id, import_kind, file_name, import_mode, periods_text, total_rows,
                      matched_owner_rows, matched_subject_rows, unmatched_rows, created_at, note
                    ) VALUES (1, 'current_year_actual', 'raw.xlsx', 'append', '2026-03', 1, 1, 1, 0, 'now', 'raw');
                    INSERT INTO expense_actual_detail_raw(
                      batch_id, import_kind, owner_name_mapped, budget_subject_mapped, period_ym,
                      amount, owner_matched, subject_matched, budget_release_caliber_mapped
                    ) VALUES
                      (1, 'current_year_actual', 'A01 零售部', '业务费用', '2026-03', 300, 1, 1, ''),
                      (NULL, 'prior_year_actual', 'A01 零售部', '业务费用', '2026-03', 999, 1, 1, '');
                    """
                )
                conn.commit()
            finally:
                conn.close()
            try:
                loaded = await load_actual_rows(_framework_context())
            finally:
                settings.data_dir = original_data_dir

        self.assertEqual(loaded.source_mode, "internal")
        self.assertIn("raw.xlsx", loaded.source_description)
        self.assertEqual(loaded.actual_by_owner[("A01 零售部", "业务费用")][2], 300.0)

    async def test_load_actual_rows_requires_current_raw_detail_import(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            _create_common_db(data_dir)
            try:
                with self.assertRaisesRegex(ExpenseActualError, "费用执行明细导入"):
                    await load_actual_rows(_framework_context())
            finally:
                settings.data_dir = original_data_dir


if __name__ == "__main__":
    unittest.main()
