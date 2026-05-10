"""手动执行驱动模块 seed"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.db_paths import budget_db_path, common_db_path
from app.init_db import _seed_driver_data

common = common_db_path()
print(f"Seeding driver data to: {common}")
_seed_driver_data(common)

import sqlite3
conn = sqlite3.connect(str(common))
cats = conn.execute("SELECT COUNT(*) FROM driver_category").fetchone()[0]
inds = conn.execute("SELECT COUNT(*) FROM driver_indicator").fetchone()[0]
prods = conn.execute("SELECT COUNT(*) FROM driver_product").fetchone()[0]
conn.close()
print(f"Done! Categories: {cats}, Indicators: {inds}, Driver_Products: {prods}")
