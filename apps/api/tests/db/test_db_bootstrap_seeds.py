from __future__ import annotations

import json
import sqlite3
import unittest

from app.db_bootstrap.seeds import seed_periods, seed_smart_ppt_defaults


class DbBootstrapSeedTests(unittest.TestCase):
    def test_seed_periods_creates_full_year_calendar(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE period (
                  year TEXT NOT NULL,
                  month TEXT NOT NULL,
                  quarter TEXT NOT NULL,
                  year_month TEXT NOT NULL,
                  days INTEGER NOT NULL,
                  UNIQUE(year, month)
                )
                """
            )

            seed_periods(conn, 2028)
            seed_periods(conn, 2028)

            rows = conn.execute(
                "SELECT month, quarter, year_month, days FROM period ORDER BY month"
            ).fetchall()
            self.assertEqual(len(rows), 12)
            self.assertEqual(rows[0], ("M01", "Q1", "2028-01", 31))
            self.assertEqual(rows[1], ("M02", "Q1", "2028-02", 29))
            self.assertEqual(rows[-1], ("M12", "Q4", "2028-12", 31))
        finally:
            conn.close()

    def test_seed_smart_ppt_defaults_upserts_json_payloads(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE smart_ppt_chart_config (
                  config_code TEXT PRIMARY KEY NOT NULL,
                  chart_type TEXT NOT NULL,
                  metric_config_json TEXT NOT NULL,
                  visual_config_json TEXT NOT NULL,
                  remark TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE smart_ppt_scene (
                  scene_code TEXT PRIMARY KEY NOT NULL,
                  scene_name TEXT NOT NULL,
                  scene_type TEXT NOT NULL,
                  description TEXT,
                  slide_template_json TEXT NOT NULL,
                  default_params_json TEXT NOT NULL,
                  sort_order INTEGER NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                """
            )
            chart_configs = [
                {
                    "config_code": "trend",
                    "chart_type": "line",
                    "metric_config_json": {"metric": "income"},
                    "visual_config_json": {"title": "收入趋势"},
                    "remark": "first",
                }
            ]
            scenes = [
                {
                    "scene_code": "monthly",
                    "scene_name": "月度经营分析会",
                    "scene_type": "monthly",
                    "description": "desc",
                    "slide_template_json": {"slides": [{"type": "cover"}]},
                    "default_params_json": {"month": "4"},
                    "sort_order": 2,
                }
            ]

            seed_smart_ppt_defaults(conn, chart_configs, scenes)
            chart_configs[0]["remark"] = "updated"
            seed_smart_ppt_defaults(conn, chart_configs, scenes)

            chart_row = conn.execute(
                """
                SELECT chart_type, metric_config_json, visual_config_json, remark
                FROM smart_ppt_chart_config
                WHERE config_code = 'trend'
                """
            ).fetchone()
            self.assertEqual(chart_row[0], "line")
            self.assertEqual(json.loads(chart_row[1]), {"metric": "income"})
            self.assertEqual(json.loads(chart_row[2]), {"title": "收入趋势"})
            self.assertEqual(chart_row[3], "updated")

            scene_row = conn.execute(
                """
                SELECT scene_name, scene_type, slide_template_json, default_params_json, status
                FROM smart_ppt_scene
                WHERE scene_code = 'monthly'
                """
            ).fetchone()
            self.assertEqual(scene_row[0], "月度经营分析会")
            self.assertEqual(scene_row[1], "monthly")
            self.assertEqual(json.loads(scene_row[2]), {"slides": [{"type": "cover"}]})
            self.assertEqual(json.loads(scene_row[3]), {"month": "4"})
            self.assertEqual(scene_row[4], "active")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

