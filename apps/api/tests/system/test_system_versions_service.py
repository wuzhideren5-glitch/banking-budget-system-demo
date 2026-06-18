from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.budget_data_writer import purge_disallowed_budget_data_for_version
from app.schemas import SystemVersionCreateRequest, SystemVersionPatchRequest
from app.services import system_versions
from app.services.system_versions import (
    SystemVersionSchemaError,
    create_system_version,
    delete_system_version,
    list_system_versions,
    patch_system_version,
)


def _seed_budget_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE version (
              version_id INTEGER PRIMARY KEY AUTOINCREMENT,
              version_date_time TEXT NOT NULL,
              version_name TEXT NOT NULL,
              current_month INTEGER NOT NULL CHECK (current_month BETWEEN 1 AND 13)
            );
            CREATE TABLE budget_data (
              data_acct_code TEXT NOT NULL,
              product_code TEXT NOT NULL,
              period_id INTEGER NOT NULL,
              budget_actual INTEGER NOT NULL,
              version_id INTEGER NOT NULL,
              value REAL NOT NULL,
              formula_value REAL,
              manual_value REAL,
              value_source TEXT NOT NULL,
              need_calc INTEGER NOT NULL,
              create_time TEXT NOT NULL,
              update_time TEXT NOT NULL
            );
            CREATE TABLE budget_summary (
              version_id INTEGER NOT NULL,
              value REAL NOT NULL
            );
            INSERT INTO version(version_id, version_date_time, version_name, current_month)
            VALUES (1, '2026-06-01T00:00:00Z', 'Parent', 7);
            INSERT INTO budget_data(
              data_acct_code, product_code, period_id, budget_actual, version_id,
              value, formula_value, manual_value, value_source, need_calc, create_time, update_time
            ) VALUES
              ('A.01', 'A', 1, 1, 1, 11, 11, NULL, 'manual', 0, 'old', 'old'),
              ('A.01', 'A', 6, 1, 1, 16, 16, NULL, 'manual', 0, 'old', 'old'),
              ('A.01', 'A', 7, 0, 1, 20, 20, NULL, 'manual', 0, 'old', 'old'),
              ('A.01', 'A', 1, 0, 1, 99, 99, NULL, 'manual', 0, 'old', 'old'),
              ('A.01', 'A', 7, 1, 1, 77, 77, NULL, 'manual', 0, 'old', 'old');
            """
        )


def _seed_common_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE edit_show_version (
              id INTEGER PRIMARY KEY,
              data_file_id INTEGER NOT NULL,
              edit_show_sign INTEGER NOT NULL,
              version_id INTEGER NOT NULL
            );
            INSERT INTO edit_show_version(id, data_file_id, edit_show_sign, version_id)
            VALUES (1, 42, 0, 2);
            """
        )


def _seed_chart_budget_db(db_path: Path, rows: list[tuple[int, str, str, int]]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE version (
              version_id INTEGER PRIMARY KEY,
              version_date_time TEXT NOT NULL,
              version_name TEXT NOT NULL,
              current_month INTEGER NOT NULL CHECK (current_month BETWEEN 1 AND 13)
            );
            """
        )
        conn.executemany(
            """
            INSERT INTO version(version_id, version_name, version_date_time, current_month)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )


class SystemVersionsServiceTests(unittest.TestCase):
    def test_loads_chart_version_options_from_selected_show_slots(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                common_db = data_dir / "common.db"
                with sqlite3.connect(common_db) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE databases(
                            id INTEGER PRIMARY KEY,
                            data_file_name TEXT NOT NULL,
                            year INTEGER NOT NULL
                        );
                        CREATE TABLE edit_show_version(
                            id INTEGER PRIMARY KEY,
                            data_file_id INTEGER NOT NULL,
                            edit_show_sign INTEGER NOT NULL,
                            version_id INTEGER NOT NULL
                        );

                        INSERT INTO databases(id, data_file_name, year)
                        VALUES (1, 'budget_2026.db', 2026),
                               (2, 'budget_2025.db', 2025),
                               (3, 'missing.db', 2024);
                        INSERT INTO edit_show_version(id, data_file_id, edit_show_sign, version_id)
                        VALUES (1, 1, 2, 3),
                               (2, 2, 1, 11),
                               (3, 3, 3, 99);
                        """
                    )
                _seed_chart_budget_db(
                    data_dir / "budget_2026.db",
                    [
                        (1, "一月版", "2026-01-01T00:00:00Z", 1),
                        (3, "三月版", "2026-03-01T00:00:00Z", 3),
                    ],
                )
                _seed_chart_budget_db(
                    data_dir / "budget_2025.db",
                    [(11, "十一月版", "2025-11-01T00:00:00Z", 11)],
                )

                load_options = getattr(system_versions, "load_chart_version_options")
                options = await load_options(common_db=common_db, data_dir=data_dir)

                self.assertEqual(
                    [
                        (
                            option.show_level,
                            option.data_file_id,
                            option.data_file_name,
                            option.year,
                            option.version_id,
                            option.version_name,
                            option.current_month,
                        )
                        for option in options
                    ],
                    [
                        (1, 2, "budget_2025.db", 2025, 11, "L1 十一月版", 11),
                        (2, 1, "budget_2026.db", 2026, 3, "L2 三月版", 3),
                    ],
                )

        asyncio.run(run())

    def test_chart_version_options_falls_back_to_database_list_when_show_slots_are_empty(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                common_db = data_dir / "common.db"
                with sqlite3.connect(common_db) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE databases(
                            id INTEGER PRIMARY KEY,
                            data_file_name TEXT NOT NULL,
                            year INTEGER NOT NULL
                        );
                        CREATE TABLE edit_show_version(
                            id INTEGER PRIMARY KEY,
                            data_file_id INTEGER NOT NULL,
                            edit_show_sign INTEGER NOT NULL,
                            version_id INTEGER NOT NULL
                        );

                        INSERT INTO databases(id, data_file_name, year)
                        VALUES (1, 'budget_2025.db', 2025),
                               (2, 'budget_2026.db', 2026);
                        """
                    )
                _seed_chart_budget_db(
                    data_dir / "budget_2026.db",
                    [
                        (1, "预算一版", "2026-01-01T00:00:00Z", 1),
                        (2, "预算二版", "2026-02-01T00:00:00Z", 2),
                    ],
                )
                _seed_chart_budget_db(
                    data_dir / "budget_2025.db",
                    [(7, "去年版", "2025-07-01T00:00:00Z", 7)],
                )

                load_options = getattr(system_versions, "load_chart_version_options")
                options = await load_options(common_db=common_db, data_dir=data_dir)

                self.assertEqual(
                    [(option.year, option.version_id, option.version_name) for option in options],
                    [
                        (2026, 1, "L1 预算一版"),
                        (2026, 2, "L1 预算二版"),
                        (2025, 7, "L1 去年版"),
                    ],
                )
                self.assertTrue(all(option.show_level == 1 for option in options))

        asyncio.run(run())

    def test_main_no_longer_keeps_chart_version_options_sql(self) -> None:
        main_source = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("WHERE e.edit_show_sign BETWEEN 1 AND 5", main_source)
        self.assertNotIn("SELECT 1 AS edit_show_sign", main_source)
        self.assertNotIn("SELECT version_id, version_name, current_month", main_source)
        self.assertNotIn("SELECT 1 FROM sqlite_master WHERE type='table' AND name='version'", main_source)
        self.assertNotIn("SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1", main_source)
        self.assertIn("load_chart_version_options", main_source)
        self.assertNotIn("try_latest_version_id_in_path", main_source)
        self.assertNotIn("async def _try_latest_version_id", main_source)

    def test_try_latest_version_id_in_path_reads_existing_budget_db_without_creating_missing_file(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                missing_budget = data_dir / "missing.db"

                load_latest_id = getattr(system_versions, "try_latest_version_id_in_path")
                self.assertIsNone(await load_latest_id(missing_budget))
                self.assertFalse(missing_budget.exists())

                no_version_table = data_dir / "no_version_table.db"
                with sqlite3.connect(no_version_table) as conn:
                    conn.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
                self.assertIsNone(await load_latest_id(no_version_table))

                empty_version_table = data_dir / "empty_version_table.db"
                with sqlite3.connect(empty_version_table) as conn:
                    conn.execute(
                        """
                        CREATE TABLE version(
                            version_id INTEGER PRIMARY KEY,
                            version_name TEXT NOT NULL
                        )
                        """
                    )
                self.assertIsNone(await load_latest_id(empty_version_table))

                budget_db = data_dir / "budget_2026.db"
                with sqlite3.connect(budget_db) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE version(
                            version_id INTEGER PRIMARY KEY,
                            version_name TEXT NOT NULL
                        );
                        INSERT INTO version(version_id, version_name)
                        VALUES (1, '一月版'), (4, '四月版'), (2, '二月版');
                        """
                    )

                self.assertEqual(await load_latest_id(budget_db), 4)

        asyncio.run(run())

    def test_create_patch_delete_version_uses_current_month_contract(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                budget_db = data_dir / "budget_2026.db"
                common_db = data_dir / "common.db"
                _seed_budget_db(budget_db)
                _seed_common_db(common_db)

                async def resolve_data_file_name(data_file_id: int) -> str:
                    self.assertEqual(data_file_id, 42)
                    return "budget_2026.db"

                async def period_months(year: int) -> dict[int, int]:
                    self.assertEqual(year, 2026)
                    return {1: 1, 6: 6, 7: 7}

                def parse_year(file_name: str) -> int | None:
                    return 2026 if file_name == "budget_2026.db" else None

                versions = await list_system_versions(
                    data_dir=data_dir,
                    data_file_id=42,
                    resolve_data_file_name=resolve_data_file_name,
                )
                self.assertEqual([(v.version_id, v.current_month) for v in versions], [(1, 7)])

                created = await create_system_version(
                    data_dir=data_dir,
                    data_file_id=42,
                    request=SystemVersionCreateRequest(
                        version_name="Child",
                        parent_version_id=1,
                        current_month=7,
                    ),
                    resolve_data_file_name=resolve_data_file_name,
                    parse_year_from_budget_filename=parse_year,
                    get_year_period_months=period_months,
                    purge_disallowed_budget_data_for_version=purge_disallowed_budget_data_for_version,
                    now="2026-06-03T00:00:00Z",
                )
                self.assertEqual(created.version_id, 2)
                self.assertEqual(created.current_month, 7)

                with sqlite3.connect(budget_db) as conn:
                    copied_rows = conn.execute(
                        """
                        SELECT period_id, budget_actual, value, create_time, update_time
                        FROM budget_data
                        WHERE version_id = 2
                        ORDER BY period_id, budget_actual
                        """
                    ).fetchall()
                self.assertEqual(
                    copied_rows,
                    [
                        (1, 1, 11.0, "2026-06-03T00:00:00Z", "2026-06-03T00:00:00Z"),
                        (6, 1, 16.0, "2026-06-03T00:00:00Z", "2026-06-03T00:00:00Z"),
                        (7, 0, 20.0, "2026-06-03T00:00:00Z", "2026-06-03T00:00:00Z"),
                    ],
                )

                patched = await patch_system_version(
                    data_dir=data_dir,
                    data_file_id=42,
                    version_id=2,
                    request=SystemVersionPatchRequest(version_name="Child Renamed"),
                    resolve_data_file_name=resolve_data_file_name,
                )
                self.assertEqual(patched.version_name, "Child Renamed")
                self.assertEqual(patched.current_month, 7)

                with sqlite3.connect(budget_db) as conn:
                    conn.execute("INSERT INTO budget_summary(version_id, value) VALUES (2, 123)")
                    conn.commit()

                deleted = await delete_system_version(
                    common_db=common_db,
                    data_dir=data_dir,
                    data_file_id=42,
                    version_id=2,
                    resolve_data_file_name=resolve_data_file_name,
                )
                self.assertEqual(deleted["budget_data_deleted"], 3)
                self.assertEqual(deleted["file_name"], "budget_2026.db")

                with sqlite3.connect(budget_db) as conn:
                    self.assertEqual(
                        conn.execute("SELECT COUNT(*) FROM version WHERE version_id = 2").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        conn.execute("SELECT COUNT(*) FROM budget_summary WHERE version_id = 2").fetchone()[0],
                        0,
                    )
                with sqlite3.connect(common_db) as conn:
                    self.assertEqual(
                        conn.execute("SELECT COUNT(*) FROM edit_show_version WHERE version_id = 2").fetchone()[0],
                        0,
                    )

        asyncio.run(run())

    def test_rejects_old_version_table_without_current_month(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                budget_db = data_dir / "budget_2026.db"
                with sqlite3.connect(budget_db) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE version (
                          version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                          version_date_time TEXT NOT NULL,
                          version_name TEXT NOT NULL
                        );
                        """
                    )

                async def resolve_data_file_name(_data_file_id: int) -> str:
                    return "budget_2026.db"

                with self.assertRaises(SystemVersionSchemaError):
                    await list_system_versions(
                        data_dir=data_dir,
                        data_file_id=42,
                        resolve_data_file_name=resolve_data_file_name,
                    )

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
