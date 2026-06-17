from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db_bootstrap.expense import ensure_bi_ai_subject_mapping_schema_sync
from app.services.expense_actual_import_context import (
    ExpenseActualImportContextError,
    load_expense_actual_import_context,
)
from app.services.expense_actual_import_parser import normalize_key


def _create_master_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE dept_account (
          dept_name TEXT NOT NULL,
          level INTEGER NOT NULL
        );
        CREATE TABLE budget_subject_catalog (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          subject_name TEXT NOT NULL,
          parent_id INTEGER,
          manage_department TEXT,
          sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE manage_dept_owner_mapping (
          manage_department TEXT NOT NULL,
          owner_department TEXT NOT NULL
        );
        """
    )
    ensure_bi_ai_subject_mapping_schema_sync(conn)


def _seed_context_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        _create_master_tables(conn)
        conn.execute("INSERT INTO dept_account(dept_name, level) VALUES (?, ?)", ("映射归口", 2))
        conn.execute(
            "INSERT INTO budget_subject_catalog(subject_name, sort_order) VALUES (?, ?)",
            ("映射预算科目", 1),
        )
        conn.execute(
            "INSERT INTO manage_dept_owner_mapping(manage_department, owner_department) VALUES (?, ?)",
            ("原始管理部门", "映射归口"),
        )
        conn.execute(
            """
            INSERT INTO bi_ai_subject_mapping(
              level5_code, level5_name, level6_code, level6_name,
              budget_release_caliber, fee_category, fee_major,
              manage_department_override, sort_order, source_file, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "L5",
                "五级",
                "L6",
                "六级",
                "预算发布",
                "费用类别一级",
                "费用大类",
                "",
                1,
                "BI科目匹配表.xlsx",
                "2026-06-02T00:00:00Z",
                "2026-06-02T00:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


class ExpenseActualImportContextTests(unittest.TestCase):
    def test_loads_current_master_mapping_context(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                db_path = root / "common.db"
                _seed_context_db(db_path)

                ctx = await load_expense_actual_import_context(db_path, root)

                self.assertIn("映射归口", ctx.owner_names)
                self.assertNotIn(normalize_key("原始归口"), ctx.owner_alias_map)
                self.assertEqual(ctx.owner_alias_map[normalize_key("董事会办公室")], "公司治理部")
                self.assertIn("映射预算科目", ctx.subject_names)
                self.assertEqual(ctx.manage_dept_owner_map[normalize_key("原始管理部门")], "映射归口")
                self.assertEqual(ctx.owner_dept_manage_map[normalize_key("映射归口")], "原始管理部门")
                self.assertEqual(
                    ctx.bi_ai_subject_mapping_detail[normalize_key("L6")],
                    ("费用大类", "费用类别一级", "预算发布"),
                )
                self.assertEqual(ctx.bi_ai_subject_mapping[normalize_key("六级")], "预算发布")

        asyncio.run(run())

    def test_rejects_missing_master_data(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                db_path = root / "common.db"
                conn = sqlite3.connect(db_path)
                try:
                    _create_master_tables(conn)
                    conn.commit()
                finally:
                    conn.close()

                with self.assertRaisesRegex(ExpenseActualImportContextError, "系统主数据未初始化"):
                    await load_expense_actual_import_context(db_path, root)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
