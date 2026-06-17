from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db_bootstrap.expense import BI_MAPPING_SCHEMA
from app.services.bi_department_mapping import (
    BiDepartmentMappingError,
    auto_generate_manage_dept_owner_mappings,
    create_manage_dept_owner_mapping,
    get_manage_dept_owner_reference_data,
    list_manage_dept_owner_mappings,
    update_manage_dept_owner_mapping,
)


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            BI_MAPPING_SCHEMA
            + """
            CREATE TABLE dept_account (
              dept_code TEXT PRIMARY KEY,
              dept_name TEXT NOT NULL,
              entity_name TEXT NOT NULL DEFAULT '微众银行',
              parent_code TEXT,
              level INTEGER NOT NULL,
              is_leaf INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE budget_subject_catalog (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              parent_id INTEGER,
              level_number INTEGER NOT NULL,
              subject_name TEXT NOT NULL,
              manage_department TEXT,
              formula_text TEXT,
              sort_order INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE expense_actual_detail_raw (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              bi_ai_source_name TEXT,
              owner_name_raw TEXT,
              owner_name_mapped TEXT,
              budget_subject_mapped TEXT,
              owner_matched INTEGER,
              subject_matched INTEGER
            );
            INSERT INTO dept_account(dept_code, dept_name, parent_code, level, is_leaf)
            VALUES ('Y1', '事业群A', NULL, 1, 0),
                   ('Y101', '费用部门A', 'Y1', 2, 1);
            INSERT INTO budget_subject_catalog(id, parent_id, level_number, subject_name, sort_order)
            VALUES (1, NULL, 1, '业务及管理费', 1),
                   (2, 1, 2, '业务费用', 2),
                   (3, 2, 3, '差旅费', 3);
            INSERT INTO expense_actual_detail_raw(
              bi_ai_source_name, owner_name_raw, owner_name_mapped,
              budget_subject_mapped, owner_matched, subject_matched
            )
            VALUES ('差旅管控', '归口部门A', '费用部门A', '差旅费', 1, 1);
            """
        )
        conn.commit()
    finally:
        conn.close()


class BiDepartmentMappingServiceTests(unittest.TestCase):
    def test_manage_dept_owner_mapping_autogenerate_and_duplicate_error(self) -> None:
        async def run(path: Path) -> None:
            result = await auto_generate_manage_dept_owner_mappings(path)
            rows = await list_manage_dept_owner_mappings(path)
            self.assertEqual({"generated": 1, "skipped": 0}, result)
            self.assertEqual("归口部门A", rows[0]["manage_department"])
            self.assertEqual("费用部门A", rows[0]["owner_department"])
            with self.assertRaises(BiDepartmentMappingError) as raised:
                await create_manage_dept_owner_mapping(
                    {"manage_department": "归口部门A", "owner_department": "费用部门A"},
                    path,
                )
            self.assertEqual(409, raised.exception.status_code)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "common.db"
            _seed_db(path)
            asyncio.run(run(path))

    def test_manual_other_owner_department_is_allowed(self) -> None:
        async def run(path: Path) -> None:
            created = await create_manage_dept_owner_mapping(
                {"manage_department": "新归口部门", "owner_department": "其他-手填费用归属"},
                path,
            )
            self.assertEqual("其他-手填费用归属", created["owner_department"])

            updated = await update_manage_dept_owner_mapping(
                int(created["id"]),
                {"owner_department": "其他-改后费用归属"},
                path,
            )
            self.assertEqual({"id": int(created["id"]), "owner_department": "其他-改后费用归属"}, updated)
            rows = await list_manage_dept_owner_mappings(path)
            self.assertEqual("其他-改后费用归属", rows[0]["owner_department"])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "common.db"
            _seed_db(path)
            asyncio.run(run(path))

    def test_reference_data_returns_owner_department_groups(self) -> None:
        async def run(path: Path) -> None:
            ref = await get_manage_dept_owner_reference_data(path)
            self.assertEqual(["费用部门A"], ref["owner_departments"])
            self.assertEqual([{"group_name": "事业群A", "departments": ["费用部门A"]}], ref["owner_dept_groups"])
            self.assertEqual(["归口部门A"], ref["manage_departments"])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "common.db"
            _seed_db(path)
            asyncio.run(run(path))


if __name__ == "__main__":
    unittest.main()
