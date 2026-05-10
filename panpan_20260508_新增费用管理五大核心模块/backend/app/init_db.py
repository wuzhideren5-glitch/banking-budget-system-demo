"""Create SQLite files per Banking_Budget_Database_PDD.md."""
from __future__ import annotations

import calendar
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db_paths import budget_db_path, common_db_path, compare_db_path, list_budget_database_files

COMMON_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS product_type (
  product_code TEXT PRIMARY KEY NOT NULL,
  product_name TEXT NOT NULL,
  remark TEXT
);

CREATE TABLE IF NOT EXISTS data_account (
  data_acct_code TEXT PRIMARY KEY NOT NULL,
  data_acct_name TEXT NOT NULL,
  product_code TEXT REFERENCES product_type(product_code),
  applies_to_all_products INTEGER NOT NULL DEFAULT 0 CHECK (applies_to_all_products IN (0, 1)),
  budget_formula TEXT,
  actual_formula TEXT,
  need_calc INTEGER NOT NULL DEFAULT 0 CHECK (need_calc IN (0, 1)),
  value_type TEXT NOT NULL,
  remark TEXT,
  CHECK (
    (applies_to_all_products = 1 AND product_code IS NULL)
    OR (applies_to_all_products = 0 AND product_code IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS report_account (
  report_acct_code TEXT PRIMARY KEY NOT NULL,
  report_acct_name TEXT NOT NULL,
  parent_code TEXT REFERENCES report_account(report_acct_code),
  is_summary INTEGER NOT NULL DEFAULT 1,
  is_minus INTEGER NOT NULL DEFAULT 0,
  level INTEGER NOT NULL,
  is_leaf INTEGER NOT NULL DEFAULT 0,
  remark TEXT
);

CREATE TABLE IF NOT EXISTS report_data_mapping (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_acct_code TEXT NOT NULL REFERENCES report_account(report_acct_code),
  data_acct_code TEXT NOT NULL REFERENCES data_account(data_acct_code),
  UNIQUE (report_acct_code, data_acct_code)
);

CREATE TABLE IF NOT EXISTS dept_account (
  dept_code TEXT PRIMARY KEY NOT NULL,
  dept_name TEXT NOT NULL,
  parent_code TEXT REFERENCES dept_account(dept_code),
  level INTEGER NOT NULL,
  is_leaf INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dept_product_mapping (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dept_code TEXT NOT NULL REFERENCES dept_account(dept_code),
  product_code TEXT NOT NULL REFERENCES product_type(product_code),
  UNIQUE (product_code)
);

CREATE TABLE IF NOT EXISTS expense_sync_meta (
  sync_key TEXT PRIMARY KEY NOT NULL,
  source_file TEXT NOT NULL,
  source_mtime TEXT,
  synced_at TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0,
  note TEXT
);

CREATE TABLE IF NOT EXISTS expense_framework_budget_department (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_name TEXT NOT NULL DEFAULT '',
  group_name TEXT NOT NULL,
  owner_name TEXT NOT NULL,
  budget_department TEXT NOT NULL,
  UNIQUE (group_name, owner_name, budget_department)
);

CREATE TABLE IF NOT EXISTS expense_framework_product_department (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_name TEXT NOT NULL DEFAULT '',
  group_name TEXT NOT NULL,
  owner_name TEXT NOT NULL,
  product_department TEXT NOT NULL,
  UNIQUE (group_name, owner_name, product_department)
);

CREATE TABLE IF NOT EXISTS expense_framework_subject (
  budget_subject TEXT PRIMARY KEY NOT NULL,
  level_label TEXT,
  manage_department TEXT,
  formula_text TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS budget_subject_catalog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_id INTEGER REFERENCES budget_subject_catalog(id) ON DELETE RESTRICT,
  level_number INTEGER NOT NULL CHECK (level_number BETWEEN 1 AND 5),
  subject_name TEXT NOT NULL,
  formula_text TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS expense_execution_monthly (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_name TEXT NOT NULL,
  budget_subject TEXT NOT NULL,
  month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
  amount REAL NOT NULL DEFAULT 0,
  UNIQUE (owner_name, budget_subject, month)
);

CREATE TABLE IF NOT EXISTS expense_forecast_entry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  forecast_year INTEGER NOT NULL,
  forecast_version TEXT NOT NULL,
  scope_type TEXT NOT NULL CHECK (scope_type IN ('entity', 'group', 'owner')),
  scope_value TEXT NOT NULL,
  subject_id INTEGER NOT NULL REFERENCES budget_subject_catalog(id) ON DELETE CASCADE,
  month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
  forecast_value REAL NOT NULL DEFAULT 0,
  create_time TEXT NOT NULL,
  update_time TEXT NOT NULL,
  UNIQUE (forecast_year, forecast_version, scope_type, scope_value, subject_id, month)
);

CREATE INDEX IF NOT EXISTS idx_expense_forecast_lookup
ON expense_forecast_entry(forecast_year, forecast_version, scope_type, scope_value);

CREATE TABLE IF NOT EXISTS period (
  period_id INTEGER PRIMARY KEY AUTOINCREMENT,
  year TEXT NOT NULL,
  month TEXT NOT NULL,
  quarter TEXT NOT NULL,
  year_month TEXT NOT NULL UNIQUE,
  days INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chart_template (
  template_id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_name TEXT NOT NULL,
  chart_type TEXT NOT NULL,
  config_json TEXT NOT NULL,
  create_time TEXT,
  update_time TEXT,
  remark TEXT
);

CREATE TABLE IF NOT EXISTS operation_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  action_type TEXT NOT NULL,
  action_desc TEXT NOT NULL,
  target_table TEXT,
  affected_rows INTEGER,
  before_data TEXT,
  after_data TEXT,
  ip_address TEXT,
  create_time TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_name TEXT NOT NULL UNIQUE,
  first_login_password TEXT NOT NULL,
  daily_login_password TEXT,
  permission_type INTEGER NOT NULL CHECK (permission_type IN (1, 2, 3)),
  first_login_flag INTEGER NOT NULL DEFAULT 1 CHECK (first_login_flag IN (0, 1)),
  create_time TEXT NOT NULL,
  update_time TEXT
);

CREATE TABLE IF NOT EXISTS databases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data_file_name TEXT NOT NULL UNIQUE,
  year INTEGER NOT NULL,
  create_time TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edit_show_version (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data_file_id INTEGER NOT NULL REFERENCES databases(id),
  version_id INTEGER NOT NULL,
  edit_show_sign INTEGER NOT NULL CHECK (edit_show_sign BETWEEN 0 AND 5)
);

CREATE TABLE IF NOT EXISTS user_sessions (
  session_id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0, 1)),
  create_time TEXT NOT NULL,
  expire_time TEXT NOT NULL,
  last_seen_time TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feishu_user_binding (
  open_id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  create_time TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feishu_user_binding_user_id ON feishu_user_binding(user_id);
"""

BUDGET_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS version (
  version_id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_date_time TEXT NOT NULL,
  version_name TEXT NOT NULL,
  current_month INTEGER NOT NULL DEFAULT 1 CHECK (current_month BETWEEN 1 AND 13)
);

CREATE TABLE IF NOT EXISTS settings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  setting_key TEXT NOT NULL UNIQUE,
  setting_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_data (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data_acct_code TEXT NOT NULL,
  product_code TEXT NOT NULL,
  period_id INTEGER NOT NULL,
  budget_actual INTEGER NOT NULL CHECK (budget_actual IN (0, 1)),
  version_id INTEGER NOT NULL REFERENCES version(version_id),
  value REAL NOT NULL DEFAULT 0,
  need_calc INTEGER NOT NULL DEFAULT 1,
  create_time TEXT,
  update_time TEXT,
  UNIQUE (data_acct_code, product_code, period_id, version_id, budget_actual)
);

CREATE TABLE IF NOT EXISTS budget_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_level1 TEXT,
  report_level2 TEXT,
  report_level3 TEXT,
  report_level4 TEXT,
  report_level5 TEXT,
  dept_level1 TEXT,
  dept_level2 TEXT,
  dept_level3 TEXT,
  data_code_name TEXT NOT NULL,
  product_code_name TEXT,
  year TEXT NOT NULL,
  month TEXT NOT NULL,
  quarter TEXT NOT NULL,
  budget_actual INTEGER NOT NULL,
  version_id INTEGER NOT NULL REFERENCES version(version_id),
  version_name TEXT,
  value REAL NOT NULL DEFAULT 0,
  value_type TEXT NOT NULL,
  update_time TEXT
);

CREATE TRIGGER IF NOT EXISTS trg_budget_data_set_update_time_insert
AFTER INSERT ON budget_data
FOR EACH ROW
WHEN NEW.update_time IS NULL OR TRIM(NEW.update_time) = ''
BEGIN
  UPDATE budget_data
  SET update_time = CURRENT_TIMESTAMP
  WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER IF NOT EXISTS trg_budget_data_set_update_time_update
AFTER UPDATE OF data_acct_code, product_code, period_id, budget_actual, version_id, value, need_calc, create_time
ON budget_data
FOR EACH ROW
BEGIN
  UPDATE budget_data
  SET update_time = CURRENT_TIMESTAMP
  WHERE rowid = NEW.rowid;
END;
"""

COMPARE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  setting_key TEXT NOT NULL UNIQUE,
  setting_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS compare_budget_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  show_level INTEGER NOT NULL CHECK (show_level BETWEEN 1 AND 5),
  data_file_id INTEGER NOT NULL,
  source_year INTEGER NOT NULL,
  source_version_id INTEGER NOT NULL,
  source_version_name TEXT,
  report_level1 TEXT,
  report_level2 TEXT,
  report_level3 TEXT,
  report_level4 TEXT,
  report_level5 TEXT,
  dept_level1 TEXT,
  dept_level2 TEXT,
  dept_level3 TEXT,
  data_code_name TEXT NOT NULL,
  product_code_name TEXT,
  year TEXT NOT NULL,
  month TEXT NOT NULL,
  quarter TEXT NOT NULL,
  budget_actual INTEGER NOT NULL CHECK (budget_actual IN (0, 1)),
  value REAL NOT NULL DEFAULT 0,
  value_type TEXT NOT NULL,
  sync_time TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_compare_budget_summary_show_level
ON compare_budget_summary(show_level);

CREATE INDEX IF NOT EXISTS idx_compare_budget_summary_source
ON compare_budget_summary(source_year, source_version_id);

CREATE TABLE IF NOT EXISTS compare_sync_job_log (
  job_id INTEGER PRIMARY KEY AUTOINCREMENT,
  start_time TEXT NOT NULL,
  end_time TEXT,
  trigger_source TEXT NOT NULL,
  status TEXT NOT NULL,
  message TEXT,
  operator_user_id INTEGER
);
"""


def _quarter_for_month(m: int) -> str:
    if m <= 3:
        return "Q1"
    if m <= 6:
        return "Q2"
    if m <= 9:
        return "Q3"
    return "Q4"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_budget_data_update_time_triggers(conn: sqlite3.Connection) -> None:
    """Ensure budget_data update_time is maintained at DB level."""
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS trg_budget_data_set_update_time_insert
        AFTER INSERT ON budget_data
        FOR EACH ROW
        WHEN NEW.update_time IS NULL OR TRIM(NEW.update_time) = ''
        BEGIN
          UPDATE budget_data
          SET update_time = CURRENT_TIMESTAMP
          WHERE rowid = NEW.rowid;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_budget_data_set_update_time_update
        AFTER UPDATE OF data_acct_code, product_code, period_id, budget_actual, version_id, value, need_calc, create_time
        ON budget_data
        FOR EACH ROW
        BEGIN
          UPDATE budget_data
          SET update_time = CURRENT_TIMESTAMP
          WHERE rowid = NEW.rowid;
        END;
        """
    )


def seed_periods(conn: sqlite3.Connection, calendar_year: int) -> None:
    y_label = f"Y{calendar_year}"
    for m in range(1, 13):
        mm = f"M{m:02d}"
        year_month = f"{calendar_year}-{m:02d}"
        days = calendar.monthrange(calendar_year, m)[1]
        q = _quarter_for_month(m)
        conn.execute(
            """
            INSERT OR IGNORE INTO period (year, month, quarter, year_month, days)
            VALUES (?, ?, ?, ?, ?)
            """,
            (y_label, mm, q, year_month, days),
        )


def init_common_db(path: Path, calendar_year: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(COMMON_SCHEMA)
        seed_periods(conn, calendar_year)
        now = _iso_now()
        conn.execute(
            """
            INSERT INTO users(
              user_name, first_login_password, daily_login_password,
              permission_type, first_login_flag, create_time, update_time
            ) VALUES (?, ?, ?, 1, 1, ?, ?)
            """,
            (settings.local_user_name, "Abc12345", None, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def init_budget_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(BUDGET_SCHEMA)
        ensure_budget_data_update_time_triggers(conn)
        cur = conn.execute("SELECT COUNT(*) FROM version")
        if cur.fetchone()[0] == 0:
            now = _iso_now()
            conn.execute(
                "INSERT INTO version (version_date_time, version_name, current_month) VALUES (?, ?, ?)",
                (now, "V2024.04.01", 1),
            )
        now = _iso_now()
        conn.execute(
            "INSERT OR IGNORE INTO settings(setting_key, setting_value) VALUES ('year', ?)",
            (str(settings.budget_year),),
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings(setting_key, setting_value) VALUES ('create_user', ?)",
            (settings.local_user_name,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings(setting_key, setting_value) VALUES ('create_time', ?)",
            (now,),
        )
        conn.commit()
    finally:
        conn.close()


def init_compare_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(COMPARE_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def migrate_data_account_applies_to_all(conn: sqlite3.Connection) -> None:
    """Backfill applies_to_all_products; NULL product_code => all products."""
    cur = conn.execute("PRAGMA table_info(data_account)")
    cols = {str(r[1]) for r in cur.fetchall()}
    if "applies_to_all_products" not in cols:
        conn.execute(
            "ALTER TABLE data_account ADD COLUMN applies_to_all_products INTEGER NOT NULL DEFAULT 0"
        )
    conn.execute(
        "UPDATE data_account SET applies_to_all_products = 1 WHERE product_code IS NULL"
    )
    conn.execute(
        "UPDATE data_account SET applies_to_all_products = 0 WHERE product_code IS NOT NULL"
    )


def migrate_budget_data_product_code(budget_path: Path, common_path: Path) -> None:
    """Add product_code to budget_data; expand all-product accounts to one row per product."""
    conn_b = sqlite3.connect(budget_path)
    try:
        conn_b.execute("PRAGMA foreign_keys = ON")
        cur = conn_b.execute("PRAGMA table_info(budget_data)")
        cols = {str(r[1]) for r in cur.fetchall()}
        if "product_code" in cols:
            ensure_budget_data_update_time_triggers(conn_b)
            conn_b.commit()
            return
        conn_c = sqlite3.connect(common_path)
        try:
            conn_c.execute("PRAGMA foreign_keys = ON")
            da_rows = list(
                conn_c.execute(
                    "SELECT data_acct_code, product_code, applies_to_all_products FROM data_account"
                )
            )
            da_map = {str(r[0]): (r[1], int(r[2] or 0)) for r in da_rows}
            products = [
                str(r[0])
                for r in conn_c.execute(
                    "SELECT product_code FROM product_type ORDER BY product_code"
                )
            ]
        finally:
            conn_c.close()
        if not products:
            products = ["_UNSET"]
        old_rows = list(
            conn_b.execute(
                """
                SELECT data_acct_code, period_id, budget_actual, version_id, value,
                       need_calc, create_time, update_time
                FROM budget_data
                """
            )
        )
        conn_b.execute("ALTER TABLE budget_data RENAME TO budget_data_old")
        conn_b.executescript(
            """
            CREATE TABLE budget_data (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              data_acct_code TEXT NOT NULL,
              product_code TEXT NOT NULL,
              period_id INTEGER NOT NULL,
              budget_actual INTEGER NOT NULL CHECK (budget_actual IN (0, 1)),
              version_id INTEGER NOT NULL REFERENCES version(version_id),
              value REAL NOT NULL DEFAULT 0,
              need_calc INTEGER NOT NULL DEFAULT 1,
              create_time TEXT,
              update_time TEXT,
              UNIQUE (data_acct_code, product_code, period_id, version_id, budget_actual)
            );
            """
        )
        inserts: list[tuple] = []
        for row in old_rows:
            dac, pid, ba, vid, val, nc, ct, ut = row
            dac = str(dac)
            info = da_map.get(dac)
            if not info:
                inserts.append(
                    (dac, products[0], pid, ba, vid, val, nc, ct, ut)
                )
                continue
            prod_code, applies_all = info
            if applies_all:
                for pc in products:
                    inserts.append((dac, pc, pid, ba, vid, val, nc, ct, ut))
            else:
                pc = str(prod_code) if prod_code else products[0]
                inserts.append((dac, pc, pid, ba, vid, val, nc, ct, ut))
        conn_b.executemany(
            """
            INSERT INTO budget_data (
              data_acct_code, product_code, period_id, budget_actual, version_id,
              value, need_calc, create_time, update_time
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            inserts,
        )
        conn_b.execute("DROP TABLE budget_data_old")
        ensure_budget_data_update_time_triggers(conn_b)
        conn_b.commit()
    finally:
        conn_b.close()


def ensure_databases() -> None:
    """Idempotent: create files and core seed if missing."""
    common = common_db_path()
    if not common.exists():
        init_common_db(common, settings.budget_year)
    else:
        conn = sqlite3.connect(common)
        try:
            conn.executescript("PRAGMA foreign_keys = ON;")
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='period'"
            )
            if cur.fetchone() is None:
                conn.executescript(COMMON_SCHEMA)
            cur = conn.execute("PRAGMA table_info(data_account)")
            data_account_cols = {str(r[1]) for r in cur.fetchall()}
            if "need_calc" not in data_account_cols:
                conn.execute(
                    """
                    ALTER TABLE data_account
                    ADD COLUMN need_calc INTEGER NOT NULL DEFAULT 0
                    CHECK (need_calc IN (0, 1))
                    """
                )
            conn.execute(
                """
                UPDATE data_account
                SET need_calc = CASE
                  WHEN need_calc = 1 THEN 1
                  ELSE 0
                END
                WHERE need_calc IS NULL OR need_calc NOT IN (0, 1)
                """
            )
            migrate_data_account_applies_to_all(conn)
            # NOTE:
            # 这里不再尝试重建 report_account 表去修改列默认值，
            # 避免历史库在存在外键依赖（report_data_mapping 等）时触发启动失败。
            # 默认值由新建库的 DDL 和前端/后端新增接口参数共同保障。
            conn.execute(
                """
                UPDATE report_account
                SET is_summary = CASE WHEN is_summary = 1 THEN 1 ELSE 0 END
                WHERE is_summary IS NULL OR is_summary NOT IN (0, 1)
                """
            )
            conn.execute(
                """
                UPDATE report_account
                SET is_minus = CASE WHEN is_minus = 1 THEN 1 ELSE 0 END
                WHERE is_minus IS NULL OR is_minus NOT IN (0, 1)
                """
            )
            seed_periods(conn, settings.budget_year)
            # 兼容历史库：将部门-产品映射从多对多收敛为“一部门叶子 -> 多产品，产品唯一归属”。
            # 若历史上同一 product_code 有多条映射，保留最早 id 的记录并清理其余记录。
            conn.execute(
                """
                DELETE FROM dept_product_mapping
                WHERE id NOT IN (
                    SELECT MIN(id) FROM dept_product_mapping GROUP BY product_code
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_dept_product_mapping_product_code_unique
                ON dept_product_mapping(product_code)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_name TEXT NOT NULL UNIQUE,
                  first_login_password TEXT NOT NULL,
                  daily_login_password TEXT,
                  permission_type INTEGER NOT NULL CHECK (permission_type IN (1, 2, 3)),
                  first_login_flag INTEGER NOT NULL DEFAULT 1 CHECK (first_login_flag IN (0, 1)),
                  create_time TEXT NOT NULL,
                  update_time TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS databases (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  data_file_name TEXT NOT NULL UNIQUE,
                  year INTEGER NOT NULL,
                  create_time TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edit_show_version (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  data_file_id INTEGER NOT NULL REFERENCES databases(id),
                  version_id INTEGER NOT NULL,
                  edit_show_sign INTEGER NOT NULL CHECK (edit_show_sign BETWEEN 0 AND 5)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_sessions (
                  session_id TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id),
                  must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0, 1)),
                  create_time TEXT NOT NULL,
                  expire_time TEXT NOT NULL,
                  last_seen_time TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feishu_user_binding (
                  open_id TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id),
                  create_time TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feishu_user_binding_user_id ON feishu_user_binding(user_id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expense_sync_meta (
                  sync_key TEXT PRIMARY KEY NOT NULL,
                  source_file TEXT NOT NULL,
                  source_mtime TEXT,
                  synced_at TEXT NOT NULL,
                  row_count INTEGER NOT NULL DEFAULT 0,
                  note TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expense_framework_budget_department (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  entity_name TEXT NOT NULL DEFAULT '',
                  group_name TEXT NOT NULL,
                  owner_name TEXT NOT NULL,
                  budget_department TEXT NOT NULL,
                  UNIQUE (group_name, owner_name, budget_department)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expense_framework_product_department (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  entity_name TEXT NOT NULL DEFAULT '',
                  group_name TEXT NOT NULL,
                  owner_name TEXT NOT NULL,
                  product_department TEXT NOT NULL,
                  UNIQUE (group_name, owner_name, product_department)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expense_framework_subject (
                  budget_subject TEXT PRIMARY KEY NOT NULL,
                  level_label TEXT,
                  manage_department TEXT,
                  formula_text TEXT,
                  sort_order INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expense_execution_monthly (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  owner_name TEXT NOT NULL,
                  budget_subject TEXT NOT NULL,
                  month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
                  amount REAL NOT NULL DEFAULT 0,
                  UNIQUE (owner_name, budget_subject, month)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS budget_subject_catalog (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  parent_id INTEGER REFERENCES budget_subject_catalog(id) ON DELETE RESTRICT,
                  level_number INTEGER NOT NULL CHECK (level_number BETWEEN 1 AND 5),
                  subject_name TEXT NOT NULL,
                  formula_text TEXT,
                  sort_order INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expense_actual_import_batch (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  file_name TEXT NOT NULL,
                  import_mode TEXT NOT NULL,
                  periods_text TEXT,
                  total_rows INTEGER NOT NULL DEFAULT 0,
                  matched_owner_rows INTEGER NOT NULL DEFAULT 0,
                  matched_subject_rows INTEGER NOT NULL DEFAULT 0,
                  unmatched_rows INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  note TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expense_actual_detail_raw (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  batch_id INTEGER REFERENCES expense_actual_import_batch(id) ON DELETE SET NULL,
                  period_ym TEXT NOT NULL,
                  period_text TEXT,
                  org_code TEXT,
                  org_name TEXT,
                  dep_code TEXT,
                  dep_name TEXT,
                  subject_code TEXT,
                  subject_name TEXT,
                  amount REAL NOT NULL DEFAULT 0,
                  fee_type_code TEXT,
                  fee_type_name TEXT,
                  control_item_code TEXT,
                  control_item_name TEXT,
                  control_dept_code TEXT,
                  owner_name_raw TEXT,
                  owner_name_mapped TEXT,
                  monthly_caliber TEXT,
                  budget_subject_raw TEXT,
                  budget_subject_mapped TEXT,
                  owner_matched INTEGER NOT NULL DEFAULT 0 CHECK (owner_matched IN (0, 1)),
                  subject_matched INTEGER NOT NULL DEFAULT 0 CHECK (subject_matched IN (0, 1)),
                  match_note TEXT
                )
                """
            )
            cur = conn.execute("PRAGMA table_info(expense_framework_budget_department)")
            framework_budget_cols = {str(r[1]) for r in cur.fetchall()}
            if "entity_name" not in framework_budget_cols:
                conn.execute(
                    """
                    ALTER TABLE expense_framework_budget_department
                    ADD COLUMN entity_name TEXT NOT NULL DEFAULT ''
                    """
                )
            cur = conn.execute("PRAGMA table_info(expense_framework_product_department)")
            framework_product_cols = {str(r[1]) for r in cur.fetchall()}
            if "entity_name" not in framework_product_cols:
                conn.execute(
                    """
                    ALTER TABLE expense_framework_product_department
                    ADD COLUMN entity_name TEXT NOT NULL DEFAULT ''
                    """
                )
            cur = conn.execute("SELECT COUNT(*) FROM users")
            if int(cur.fetchone()[0] or 0) == 0:
                now = _iso_now()
                conn.execute(
                    """
                    INSERT INTO users(
                      user_name, first_login_password, daily_login_password,
                      permission_type, first_login_flag, create_time, update_time
                    ) VALUES (?, ?, ?, 1, 1, ?, ?)
                    """,
                    (settings.local_user_name, "Abc12345", None, now, now),
                )
            conn.commit()
        finally:
            conn.close()

    budget = budget_db_path(settings.budget_year)
    if not budget.exists():
        init_budget_db(budget)
    else:
        conn = sqlite3.connect(budget)
        try:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='version'"
            )
            if cur.fetchone() is None:
                conn.executescript(BUDGET_SCHEMA)
                now = _iso_now()
                conn.execute(
                    "INSERT INTO version (version_date_time, version_name, current_month) VALUES (?, ?, ?)",
                    (now, "V2024.04.01", 1),
                )
            cur = conn.execute("PRAGMA table_info(budget_data)")
            budget_data_cols = {str(r[1]) for r in cur.fetchall()}
            cur = conn.execute("PRAGMA table_info(version)")
            version_cols = {str(r[1]) for r in cur.fetchall()}
            if "needs_calc" in budget_data_cols and "need_calc" not in budget_data_cols:
                try:
                    conn.execute(
                        "ALTER TABLE budget_data RENAME COLUMN needs_calc TO need_calc"
                    )
                except sqlite3.OperationalError:
                    conn.execute(
                        """
                        ALTER TABLE budget_data
                        ADD COLUMN need_calc INTEGER NOT NULL DEFAULT 1
                        CHECK (need_calc IN (0, 1))
                        """
                    )
                    conn.execute(
                        """
                        UPDATE budget_data
                        SET need_calc = CASE
                          WHEN needs_calc IN (0, 1) THEN needs_calc
                          ELSE 0
                        END
                        """
                    )
            elif "need_calc" not in budget_data_cols:
                conn.execute(
                    """
                    ALTER TABLE budget_data
                    ADD COLUMN need_calc INTEGER NOT NULL DEFAULT 1
                    CHECK (need_calc IN (0, 1))
                    """
                )
            elif "needs_calc" in budget_data_cols and "need_calc" in budget_data_cols:
                conn.execute(
                    """
                    UPDATE budget_data
                    SET need_calc = CASE
                      WHEN needs_calc IN (0, 1) THEN needs_calc
                      ELSE COALESCE(need_calc, 0)
                    END
                    """
                )
                try:
                    conn.execute("ALTER TABLE budget_data DROP COLUMN needs_calc")
                except sqlite3.OperationalError:
                    pass
            conn.execute(
                """
                UPDATE budget_data
                SET need_calc = CASE
                  WHEN need_calc = 1 THEN 1
                  ELSE 0
                END
                WHERE need_calc IS NULL OR need_calc NOT IN (0, 1)
                """
            )
            if "current_month" not in version_cols:
                conn.execute(
                    """
                    ALTER TABLE version
                    ADD COLUMN current_month INTEGER NOT NULL DEFAULT 1
                    CHECK (current_month BETWEEN 1 AND 13)
                    """
                )
            conn.execute(
                """
                UPDATE version
                SET current_month = CASE
                  WHEN current_month BETWEEN 1 AND 13 THEN current_month
                  ELSE 1
                END
                WHERE current_month IS NULL OR current_month NOT BETWEEN 1 AND 13
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  setting_key TEXT NOT NULL UNIQUE,
                  setting_value TEXT NOT NULL
                )
                """
            )
            now = _iso_now()
            conn.execute(
                "INSERT OR IGNORE INTO settings(setting_key, setting_value) VALUES ('year', ?)",
                (str(settings.budget_year),),
            )
            conn.execute(
                "INSERT OR IGNORE INTO settings(setting_key, setting_value) VALUES ('create_user', ?)",
                (settings.local_user_name,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO settings(setting_key, setting_value) VALUES ('create_time', ?)",
                (now,),
            )
            conn.commit()
        finally:
            conn.close()
        migrate_budget_data_product_code(budget, common)

    # 基础自愈：确保当前年度预算库在 databases 中可见，并在首次场景下提供一条展示层级配置。
    common_conn = sqlite3.connect(common)
    budget_conn = sqlite3.connect(budget)
    try:
        now = _iso_now()
        data_file_name = budget.name
        common_conn.execute(
            """
            INSERT OR IGNORE INTO databases(data_file_name, year, create_time)
            VALUES (?, ?, ?)
            """,
            (data_file_name, int(settings.budget_year), now),
        )
        cur = common_conn.execute(
            "SELECT id FROM databases WHERE data_file_name = ?",
            (data_file_name,),
        )
        row = cur.fetchone()
        if row is not None:
            data_file_id = int(row[0])
            cur = common_conn.execute(
                "SELECT COUNT(*) FROM edit_show_version WHERE edit_show_sign BETWEEN 1 AND 5"
            )
            show_count = int(cur.fetchone()[0] or 0)
            if show_count == 0:
                cur = budget_conn.execute(
                    "SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1"
                )
                vrow = cur.fetchone()
                if vrow is not None:
                    common_conn.execute(
                        """
                        INSERT INTO edit_show_version(data_file_id, version_id, edit_show_sign)
                        VALUES (?, ?, 1)
                        """,
                        (data_file_id, int(vrow[0])),
                    )
        common_conn.commit()
    finally:
        common_conn.close()
        budget_conn.close()

    compare = compare_db_path()
    if not compare.exists():
        init_compare_db(compare)
    else:
        conn = sqlite3.connect(compare)
        try:
            conn.executescript(COMPARE_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    # 历史年度库兜底：为所有 budget_*.db 补齐 budget_data.update_time 触发器。
    for bpath in list_budget_database_files():
        conn = sqlite3.connect(bpath)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_data'"
            )
            if cur.fetchone() is None:
                continue
            ensure_budget_data_update_time_triggers(conn)
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    ensure_databases()
    print("OK:", common_db_path(), budget_db_path(settings.budget_year), compare_db_path())
