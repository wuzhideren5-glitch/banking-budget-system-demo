from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.expense_budget_execution_subject_catalog import (
    BudgetSubjectCatalogError,
    load_budget_subject_catalog_rows,
)


def _create_catalog_db(db_path: Path, *, with_rows: bool) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE budget_subject_catalog (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              parent_id INTEGER,
              level_number INTEGER NOT NULL DEFAULT 1,
              subject_name TEXT NOT NULL,
              manage_department TEXT,
              formula_text TEXT,
              sort_order INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        if with_rows:
            conn.executescript(
                """
                INSERT INTO budget_subject_catalog(
                  id, parent_id, level_number, subject_name, manage_department, formula_text, sort_order
                ) VALUES
                  (10, NULL, 1, '业务费用', '归口A', '0', 20),
                  (11, 10, 2, 'IT费用', NULL, NULL, 30);
                """
            )
        conn.commit()
    finally:
        conn.close()


class ExpenseBudgetExecutionSubjectCatalogTests(unittest.TestCase):
    def test_loads_current_budget_subject_catalog_rows(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _create_catalog_db(db_path, with_rows=True)

                rows = await load_budget_subject_catalog_rows(db_path)

            self.assertEqual(
                rows,
                [
                    {
                        "id": 10,
                        "parent_id": None,
                        "level_number": 1,
                        "level_label": "1级",
                        "subject_name": "业务费用",
                        "manage_department": "归口A",
                        "formula_text": "0",
                        "sort_order": 20,
                    },
                    {
                        "id": 11,
                        "parent_id": 10,
                        "level_number": 2,
                        "level_label": "2级",
                        "subject_name": "IT费用",
                        "manage_department": None,
                        "formula_text": None,
                        "sort_order": 30,
                    },
                ],
            )

        asyncio.run(run())

    def test_raises_when_current_budget_subject_catalog_is_empty(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _create_catalog_db(db_path, with_rows=False)

                with self.assertRaises(BudgetSubjectCatalogError):
                    await load_budget_subject_catalog_rows(db_path)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
