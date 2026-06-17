from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db_bootstrap.budget_data import (
    ensure_budget_data_update_time_triggers,
    validate_budget_data_fact_table,
)
from app.db_bootstrap.runner import sync_current_budget_registry


def table_exists(path: Path, table_name: str) -> bool:
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def trigger_exists(path: Path, trigger_name: str) -> bool:
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name = ?",
            (trigger_name,),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


class DbBootstrapRunnerTests(unittest.TestCase):
    def test_sync_current_budget_registry_registers_active_budget_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            common_path = base / "common.db"
            budget_path = base / "budget_2030.db"

            common_conn = sqlite3.connect(common_path)
            try:
                common_conn.executescript(
                    """
                    CREATE TABLE databases (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      data_file_name TEXT NOT NULL UNIQUE,
                      year INTEGER NOT NULL,
                      create_time TEXT NOT NULL
                    );
                    CREATE TABLE edit_show_version (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      data_file_id INTEGER NOT NULL,
                      version_id INTEGER NOT NULL,
                      edit_show_sign INTEGER NOT NULL
                    );
                    """
                )
                common_conn.commit()
            finally:
                common_conn.close()

            budget_conn = sqlite3.connect(budget_path)
            try:
                budget_conn.executescript(
                    """
                    CREATE TABLE version (
                      version_id INTEGER PRIMARY KEY NOT NULL
                    );
                    INSERT INTO version(version_id) VALUES (1), (9);
                    """
                )
                budget_conn.commit()
            finally:
                budget_conn.close()

            sync_current_budget_registry(common_path, budget_path, 2030)
            sync_current_budget_registry(common_path, budget_path, 2030)

            conn = sqlite3.connect(common_path)
            try:
                rows = conn.execute(
                    """
                    SELECT d.data_file_name, d.year, e.version_id, e.edit_show_sign
                    FROM databases d
                    JOIN edit_show_version e ON e.data_file_id = d.id
                    """
                ).fetchall()
            finally:
                conn.close()

            self.assertEqual(rows, [("budget_2030.db", 2030, 9, 1)])

    def test_budget_data_update_time_triggers_skip_non_budget_data_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with_budget_data = base / "budget_2030.db"
            without_budget_data = base / "budget_2031.db"

            conn = sqlite3.connect(with_budget_data)
            try:
                conn.execute(
                    """
                    CREATE TABLE budget_data (
                      id INTEGER PRIMARY KEY,
                      data_acct_code TEXT,
                      product_code TEXT,
                      period_id INTEGER,
                      budget_actual INTEGER,
                      version_id INTEGER,
                      value REAL,
                      formula_value REAL,
                      manual_value REAL,
                      value_source TEXT NOT NULL DEFAULT 'manual'
                        CHECK (value_source IN ('manual', 'formula', 'none', 'rollup')),
                      need_calc INTEGER,
                      create_time TEXT,
                      update_time TEXT
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()
            sqlite3.connect(without_budget_data).close()

            for budget_file in [with_budget_data, without_budget_data]:
                conn = sqlite3.connect(budget_file)
                try:
                    ensure_budget_data_update_time_triggers(conn)
                    conn.commit()
                finally:
                    conn.close()

            self.assertTrue(trigger_exists(with_budget_data, "trg_budget_data_set_update_time_insert"))
            self.assertFalse(trigger_exists(without_budget_data, "trg_budget_data_set_update_time_insert"))

    def test_budget_data_update_time_triggers_reject_retired_needs_calc_column(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE budget_data (
                  id INTEGER PRIMARY KEY,
                  data_acct_code TEXT,
                  needs_calc INTEGER
                )
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_budget_data_update_time_triggers(conn)
            self.assertIn("needs_calc", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_budget_data_validation_rejects_missing_product_code_fact_grain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            budget_path = base / "budget_2030.db"

            conn = sqlite3.connect(budget_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE budget_data (
                      id INTEGER PRIMARY KEY,
                      data_acct_code TEXT,
                      period_id INTEGER,
                      budget_actual INTEGER,
                      version_id INTEGER,
                      value REAL,
                      need_calc INTEGER
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

            with self.assertRaises(RuntimeError) as raised:
                validate_budget_data_fact_table(budget_path)
            self.assertIn("product_code", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))

    def test_budget_data_validation_rejects_retired_data_type_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            budget_path = base / "budget_2030.db"

            conn = sqlite3.connect(budget_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE budget_data (
                      id INTEGER PRIMARY KEY,
                      data_acct_code TEXT,
                      product_code TEXT,
                      period_id INTEGER,
                      data_type TEXT,
                      budget_actual INTEGER,
                      version_id INTEGER,
                      value REAL,
                      need_calc INTEGER
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

            with self.assertRaises(RuntimeError) as raised:
                validate_budget_data_fact_table(budget_path)
            self.assertIn("data_type", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))

    def test_budget_data_validation_rejects_invalid_need_calc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            budget_path = Path(tmp) / "budget_2030.db"

            conn = sqlite3.connect(budget_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE budget_data (
                      id INTEGER PRIMARY KEY,
                      data_acct_code TEXT,
                      product_code TEXT,
                      period_id INTEGER,
                      budget_actual INTEGER,
                      version_id INTEGER,
                      value REAL,
                      formula_value REAL,
                      manual_value REAL,
                      value_source TEXT NOT NULL DEFAULT 'manual'
                        CHECK (value_source IN ('manual', 'formula', 'none', 'rollup')),
                      need_calc INTEGER,
                      create_time TEXT,
                      update_time TEXT
                    );
                    INSERT INTO budget_data(
                      data_acct_code, product_code, period_id, budget_actual, version_id,
                      value, formula_value, manual_value, value_source, need_calc
                    ) VALUES (
                      'A01.01.01.001', 'A01', 1, 0, 1,
                      123.45, NULL, 123.45, 'manual', 2
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

            with self.assertRaises(RuntimeError) as raised:
                validate_budget_data_fact_table(budget_path)
            self.assertIn("need_calc", str(raised.exception))
            self.assertIn("不再自动修正", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
