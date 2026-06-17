from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.agent_compare_version import (
    compare_level_meta,
    compare_version_choice_hint,
    current_compare_show_level_version,
    extract_compare_show_level,
    extract_compare_target_year,
    filter_compare_options_by_target_year,
    format_compare_version_options,
    is_explicit_year_comparison,
    is_yoy_requested,
    load_compare_version_options,
)


class AgentCompareVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.common_db = root / "common.db"
        self.compare_db = root / "compare.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_common_db(self) -> None:
        with sqlite3.connect(self.common_db) as conn:
            conn.executescript(
                """
                CREATE TABLE databases(
                    id INTEGER PRIMARY KEY,
                    year INTEGER,
                    data_file_name TEXT
                );
                CREATE TABLE edit_show_version(
                    id INTEGER PRIMARY KEY,
                    data_file_id INTEGER,
                    edit_show_sign INTEGER,
                    version_id INTEGER
                );

                INSERT INTO databases(id, year, data_file_name) VALUES (1, 2026, 'current_budget');
                INSERT INTO databases(id, year, data_file_name) VALUES (2, 2025, 'compare_budget');
                INSERT INTO edit_show_version(id, data_file_id, edit_show_sign, version_id) VALUES (1, 1, 1, 101);
                INSERT INTO edit_show_version(id, data_file_id, edit_show_sign, version_id) VALUES (2, 2, 2, 202);
                """
            )

    def _create_compare_db(self) -> None:
        with sqlite3.connect(self.compare_db) as conn:
            conn.executescript(
                """
                CREATE TABLE compare_budget_summary(
                    show_level INTEGER,
                    source_year INTEGER,
                    source_version_id INTEGER,
                    source_version_name TEXT
                );

                INSERT INTO compare_budget_summary VALUES (1, 2026, 101, 'base');
                INSERT INTO compare_budget_summary VALUES (2, 2025, 202, 'last_year');
                INSERT INTO compare_budget_summary VALUES (6, 2024, 303, 'ignored_level');
                INSERT INTO compare_budget_summary VALUES (3, 2024, 0, 'ignored_version');
                """
            )

    def test_parse_compare_level_and_target_year(self) -> None:
        self.assertEqual(extract_compare_show_level("L3"), 3)
        self.assertEqual(extract_compare_show_level("show level 4"), 4)
        self.assertEqual(extract_compare_show_level("层级5"), 5)
        self.assertEqual(extract_compare_show_level("2"), 2)

        self.assertTrue(is_explicit_year_comparison("2026年和2025年对比"))
        self.assertFalse(is_explicit_year_comparison("预算实际差异"))
        self.assertEqual(extract_compare_target_year("2026年和2025年对比"), 2025)
        self.assertTrue(is_yoy_requested("看同比", {}))
        self.assertTrue(is_yoy_requested("2026年和2025年对比", {}))

    def test_compare_db_options_prefer_snapshot_and_filter_current_levels(self) -> None:
        self._create_common_db()
        self._create_compare_db()

        options = load_compare_version_options(
            compare_db=self.compare_db,
            common_db=self.common_db,
        )

        self.assertEqual(options, [(1, 2026, 101, "base"), (2, 2025, 202, "last_year")])
        self.assertEqual(
            format_compare_version_options(options),
            ["L1（2026年 / V101 base）", "L2（2025年 / V202 last_year）"],
        )
        self.assertEqual(
            filter_compare_options_by_target_year(options, 2025),
            [(2, 2025, 202, "last_year")],
        )
        self.assertEqual(filter_compare_options_by_target_year(options, 2023), options)

    def test_fallback_options_use_common_edit_show_version_when_compare_missing(self) -> None:
        self._create_common_db()

        options = load_compare_version_options(
            compare_db=self.compare_db,
            common_db=self.common_db,
        )

        self.assertEqual(
            options,
            [
                (1, 2026, 101, "current_budget / V101"),
                (2, 2025, 202, "compare_budget / V202"),
            ],
        )

    def test_level_meta_and_choice_hint_use_current_show_level_version(self) -> None:
        self._create_common_db()
        self._create_compare_db()

        self.assertEqual(
            current_compare_show_level_version(common_db=self.common_db, show_level=2),
            202,
        )
        self.assertEqual(
            compare_level_meta(compare_db=self.compare_db, common_db=self.common_db, show_level=2),
            {
                "show_level": 2,
                "source_year": 2025,
                "source_version_id": 202,
                "source_version_name": "last_year",
            },
        )
        self.assertEqual(
            compare_version_choice_hint(
                compare_db=self.compare_db,
                common_db=self.common_db,
                show_level=2,
            ),
            "已选择同比版本：L2（2025年 / V202 last_year）。",
        )


if __name__ == "__main__":
    unittest.main()
