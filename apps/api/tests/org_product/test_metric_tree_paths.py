from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.metric_tree_paths import build_metric_path, load_active_metric_node_map_sync


class MetricTreePathTests(unittest.TestCase):
    def test_load_active_metric_node_map_sync_normalizes_active_nodes_for_path_building(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account_metric_node (
                      node_code TEXT PRIMARY KEY,
                      node_name TEXT,
                      parent_code TEXT,
                      level INTEGER,
                      sort_order INTEGER,
                      is_active INTEGER
                    );
                    INSERT INTO data_account_metric_node(node_code, node_name, parent_code, level, sort_order, is_active)
                    VALUES
                      ('a01', '开鑫贷', NULL, 1, 10, 1),
                      ('A01.01', '收入', 'a01', 2, 20, 1),
                      ('A01.01.001', '余额', 'A01.01', 3, 30, 1),
                      ('A02', '停用', NULL, 1, 40, 0);
                    """
                )

                node_map = load_active_metric_node_map_sync(conn)

        self.assertEqual(
            build_metric_path("a01.01.001", node_map),
            ["A01 开鑫贷", "A01.01 收入", "A01.01.001 余额"],
        )
        self.assertNotIn("A02", node_map)


if __name__ == "__main__":
    unittest.main()
