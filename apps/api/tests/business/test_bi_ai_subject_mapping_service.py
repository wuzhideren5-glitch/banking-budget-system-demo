from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from app.services import bi_ai_subject_mapping as bi_ai_subject_mapping_module
from app.services.bi_ai_subject_mapping import (
    BiAiSubjectMappingHeaderError,
    BiAiSubjectMappingSourceMissingError,
    EXPECTED_HEADERS,
    ensure_bi_ai_subject_mapping_seeded,
    list_bi_ai_subject_mapping_rows,
)


def _write_workbook(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.append(["说明行"])
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)


class BiAiSubjectMappingServiceTests(unittest.TestCase):
    def test_service_uses_mysql_gateway_path(self) -> None:
        source = Path(bi_ai_subject_mapping_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)
        self.assertIn("SHOW COLUMNS FROM", source)
        self.assertIn("SHOW TABLES LIKE", source)

    def test_seed_allows_empty_table_when_source_workbook_is_absent(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                db_path = root / "common.db"

                result = await ensure_bi_ai_subject_mapping_seeded(db_path, root)

                self.assertEqual(result.row_count, 0)
                self.assertEqual(result.source_file, "")
                with sqlite3.connect(db_path) as conn:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM bi_ai_subject_mapping"
                    ).fetchone()
                self.assertEqual(int(row[0]), 0)

        asyncio.run(run())

    def test_force_reload_requires_source_workbook(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                db_path = root / "common.db"

                with self.assertRaises(BiAiSubjectMappingSourceMissingError):
                    await ensure_bi_ai_subject_mapping_seeded(
                        db_path,
                        root,
                        force_reload=True,
                    )

        asyncio.run(run())

    def test_rejects_unexpected_source_workbook_header(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                db_path = root / "common.db"
                _write_workbook(
                    root / "resources" / "business_inputs" / "BI科目mapping.xlsx",
                    ["旧表头"],
                    [["x"]],
                )

                with self.assertRaises(BiAiSubjectMappingHeaderError):
                    await ensure_bi_ai_subject_mapping_seeded(
                        db_path,
                        root,
                        force_reload=True,
                    )

        asyncio.run(run())

    def test_seeds_and_lists_current_mapping_rows(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                db_path = root / "common.db"
                _write_workbook(
                    root / "resources" / "business_inputs" / "BI科目匹配表.xlsx",
                    EXPECTED_HEADERS,
                    [
                        [
                            "业务及管理费",
                            "L3",
                            "三级",
                            "L4",
                            "四级",
                            "L5",
                            "五级",
                            "L6",
                            "六级",
                            "预算发布",
                            "费用类别",
                            "费用大类",
                        ]
                    ],
                )

                result = await ensure_bi_ai_subject_mapping_seeded(
                    db_path,
                    root,
                    force_reload=True,
                )
                rows = await list_bi_ai_subject_mapping_rows(db_path, root)

                self.assertEqual(result.row_count, 1)
                self.assertEqual(result.source_file, "BI科目匹配表.xlsx")
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["level6_code"], "L6")
                self.assertEqual(rows[0]["fee_major"], "费用大类")
                self.assertEqual(rows[0]["source_file"], "BI科目匹配表.xlsx")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
