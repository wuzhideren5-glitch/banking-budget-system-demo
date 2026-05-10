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
  metric_group_code TEXT,
  metric_group_name TEXT,
  product_code TEXT REFERENCES product_type(product_code),
  budget_formula TEXT,
  actual_formula TEXT,
  budget_rule_code TEXT,
  budget_rule_config_json TEXT,
  need_calc INTEGER NOT NULL DEFAULT 0 CHECK (need_calc IN (0, 1)),
  value_type TEXT NOT NULL,
  product_codes TEXT,
  remark TEXT
);

CREATE TABLE IF NOT EXISTS data_account_metric_node (
  node_code TEXT PRIMARY KEY NOT NULL,
  node_name TEXT NOT NULL,
  parent_code TEXT REFERENCES data_account_metric_node(node_code),
  level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 8),
  node_type TEXT NOT NULL CHECK (node_type IN ('CATEGORY', 'GROUP', 'METRIC')),
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  remark TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS data_account_metric_binding (
  binding_code TEXT PRIMARY KEY NOT NULL,
  metric_node_code TEXT NOT NULL REFERENCES data_account_metric_node(node_code),
  scope_type TEXT NOT NULL CHECK (scope_type IN ('PRODUCT', 'CORP')),
  scope_code TEXT NOT NULL,
  product_code TEXT REFERENCES product_type(product_code),
  data_acct_code TEXT NOT NULL REFERENCES data_account(data_acct_code),
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  remark TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (metric_node_code, scope_code),
  UNIQUE (data_acct_code, scope_code),
  CHECK (
    (scope_type = 'CORP' AND scope_code = 'CORP' AND product_code IS NULL)
    OR
    (scope_type = 'PRODUCT' AND scope_code = product_code AND product_code IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_data_account_metric_node_parent
ON data_account_metric_node(parent_code);

CREATE INDEX IF NOT EXISTS idx_data_account_metric_binding_metric
ON data_account_metric_binding(metric_node_code);

CREATE INDEX IF NOT EXISTS idx_data_account_metric_binding_data
ON data_account_metric_binding(data_acct_code);

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

CREATE TABLE IF NOT EXISTS smart_report_template (
  template_id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_code TEXT NOT NULL UNIQUE,
  template_name TEXT NOT NULL,
  template_type TEXT NOT NULL DEFAULT 'analysis' CHECK (template_type IN ('analysis', 'report', 'summary', 'ppt')),
  file_path TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
  version_no INTEGER NOT NULL DEFAULT 1,
  remark TEXT,
  created_by TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS smart_report_template_variable (
  variable_id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER NOT NULL REFERENCES smart_report_template(template_id) ON DELETE CASCADE,
  variable_key TEXT NOT NULL,
  variable_name TEXT NOT NULL,
  variable_type TEXT NOT NULL CHECK (variable_type IN ('metric', 'formula', 'calc', 'parameter', 'text', 'table', 'chart', 'analysis')),
  binding_config_json TEXT,
  display_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (template_id, variable_key)
);

CREATE TABLE IF NOT EXISTS smart_report_calc_metric (
  metric_code TEXT PRIMARY KEY NOT NULL,
  metric_name TEXT NOT NULL,
  expression TEXT NOT NULL,
  components_json TEXT NOT NULL,
  value_type TEXT NOT NULL DEFAULT '金额',
  format_type TEXT NOT NULL DEFAULT 'number',
  remark TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS smart_report_definition (
  report_id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER NOT NULL REFERENCES smart_report_template(template_id),
  report_name TEXT NOT NULL,
  report_scene TEXT,
  parameter_schema_json TEXT,
  section_schema_json TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS smart_report_instance (
  instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER REFERENCES smart_report_definition(report_id),
  template_id INTEGER NOT NULL REFERENCES smart_report_template(template_id),
  instance_name TEXT NOT NULL,
  parameter_values_json TEXT NOT NULL,
  text_values_json TEXT,
  data_snapshot_json TEXT,
  output_file_path TEXT,
  generation_status TEXT NOT NULL DEFAULT 'pending' CHECK (generation_status IN ('pending', 'running', 'success', 'failed')),
  error_message TEXT,
  last_generated_at TEXT,
  last_refresh_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS smart_report_job (
  job_id INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id INTEGER REFERENCES smart_report_instance(instance_id) ON DELETE SET NULL,
  job_type TEXT NOT NULL CHECK (job_type IN ('generate', 'refresh')),
  job_status TEXT NOT NULL CHECK (job_status IN ('pending', 'running', 'success', 'failed')),
  started_at TEXT,
  finished_at TEXT,
  error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_smart_report_variable_template
ON smart_report_template_variable(template_id);

CREATE INDEX IF NOT EXISTS idx_smart_report_instance_template
ON smart_report_instance(template_id);

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

CREATE TABLE IF NOT EXISTS expense_execution_monthly (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_name TEXT NOT NULL,
  budget_subject TEXT NOT NULL,
  month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
  amount REAL NOT NULL DEFAULT 0,
  UNIQUE (owner_name, budget_subject, month)
);

CREATE TABLE IF NOT EXISTS budget_subject_catalog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_id INTEGER REFERENCES budget_subject_catalog(id) ON DELETE RESTRICT,
  level_number INTEGER NOT NULL CHECK (level_number BETWEEN 1 AND 5),
  subject_name TEXT NOT NULL,
  formula_text TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
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
);

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
);

CREATE TABLE IF NOT EXISTS driver_category (
  category_code TEXT PRIMARY KEY NOT NULL,
  category_name TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS driver_indicator (
  indicator_code TEXT PRIMARY KEY NOT NULL,
  category_code TEXT NOT NULL REFERENCES driver_category(category_code),
  indicator_name TEXT NOT NULL,
  value_type TEXT NOT NULL,
  data_acct_code TEXT REFERENCES data_account(data_acct_code),
  has_product_detail INTEGER NOT NULL DEFAULT 0,
  has_monthly_detail INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS driver_product (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  indicator_code TEXT NOT NULL REFERENCES driver_indicator(indicator_code),
  product_code TEXT NOT NULL REFERENCES product_type(product_code),
  sort_order INTEGER NOT NULL DEFAULT 0,
  UNIQUE (indicator_code, product_code)
);

CREATE TABLE IF NOT EXISTS driver_account_mapping (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  indicator_code TEXT NOT NULL REFERENCES driver_indicator(indicator_code),
  product_code TEXT NOT NULL REFERENCES product_type(product_code),
  data_acct_code TEXT NOT NULL REFERENCES data_account(data_acct_code),
  sort_order INTEGER NOT NULL DEFAULT 0,
  UNIQUE (indicator_code, product_code, data_acct_code)
);
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


DRIVER_CATEGORIES = [
    ("CAPITAL", "资本补充驱动", 1),
    ("SCALE", "规模驱动", 2),
    ("YIELD", "收益率驱动", 3),
    ("FEE", "手续费净收入驱动", 4),
    ("RISK", "风险驱动", 5),
]

DRIVER_INDICATORS = [
    # category / code / name / value_type / has_product / has_monthly
    ("CAPITAL", "CAPITAL_INCREASE", "当年增资", "金额", 0, 1),
    ("CAPITAL", "DIVIDEND_RATIO", "当年分红比例", "百分比", 0, 0),
    ("SCALE", "MGMT_LOAN_EOY", "管理贷款时点规模", "金额", 1, 1),
    ("SCALE", "MGMT_LOAN_DAILY", "管理贷款日均规模", "金额", 1, 1),
    ("SCALE", "ONBAL_LOAN_EOY", "表内贷款时点规模", "金额", 1, 1),
    ("SCALE", "ONBAL_LOAN_DAILY", "表内贷款日均规模", "金额", 1, 1),
    ("YIELD", "LOAN_YIELD_RATE", "全行贷款收益率", "百分比", 1, 1),
    ("YIELD", "INTERBANK_YIELD_RATE", "同业资产收益率", "百分比", 1, 1),
    ("FEE", "FEE_INCOME", "手续费收入", "金额", 1, 1),
    ("FEE", "FEE_EXPENSE", "手续费支出", "金额", 1, 1),
    ("RISK", "RISK_COST_RATE", "风险成本率", "百分比", 1, 1),
    ("RISK", "NPL_RATIO", "不良率", "百分比", 1, 1),
    ("RISK", "ACTUAL_LOSS", "实际损失额", "金额", 1, 1),
    ("RISK", "PROVISION_COVERAGE", "拨备覆盖率", "百分比", 0, 0),
]

DRIVER_ACCOUNT_MAPPINGS = [
    ("MGMT_LOAN_DAILY", "Z0001", "E1200", 1),
    ("MGMT_LOAN_DAILY", "Z0002", "E1250", 1),
    ("MGMT_LOAN_DAILY", "Z0003", "E1201", 1),
    ("ONBAL_LOAN_DAILY", "Z0001", "A1200", 1),
    ("ONBAL_LOAN_DAILY", "Z0001", "A1203", 2),
    ("ONBAL_LOAN_DAILY", "Z0002", "A1250", 1),
    ("ONBAL_LOAN_DAILY", "Z0003", "A1201", 1),
    ("ONBAL_LOAN_DAILY", "Z0003", "A1204", 2),
    ("ONBAL_LOAN_DAILY", "Z0004", "A3161", 1),
    ("LOAN_YIELD_RATE", "Z0001", "K1200", 1),
    ("LOAN_YIELD_RATE", "Z0002", "K1250", 1),
    ("LOAN_YIELD_RATE", "Z0003", "K1201", 1),
    ("LOAN_YIELD_RATE", "Z0004", "K1251", 1),
]


def _seed_driver_data(common_path: Path) -> None:
    conn = sqlite3.connect(common_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("CREATE TABLE IF NOT EXISTS driver_category (category_code TEXT PRIMARY KEY NOT NULL, category_name TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS driver_indicator (indicator_code TEXT PRIMARY KEY NOT NULL, category_code TEXT NOT NULL REFERENCES driver_category(category_code), indicator_name TEXT NOT NULL, value_type TEXT NOT NULL, data_acct_code TEXT REFERENCES data_account(data_acct_code), has_product_detail INTEGER NOT NULL DEFAULT 0, has_monthly_detail INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS driver_product (id INTEGER PRIMARY KEY AUTOINCREMENT, indicator_code TEXT NOT NULL REFERENCES driver_indicator(indicator_code), product_code TEXT NOT NULL REFERENCES product_type(product_code), sort_order INTEGER NOT NULL DEFAULT 0, UNIQUE (indicator_code, product_code))")
        conn.execute("CREATE TABLE IF NOT EXISTS driver_account_mapping (id INTEGER PRIMARY KEY AUTOINCREMENT, indicator_code TEXT NOT NULL REFERENCES driver_indicator(indicator_code), product_code TEXT NOT NULL REFERENCES product_type(product_code), data_acct_code TEXT NOT NULL REFERENCES data_account(data_acct_code), sort_order INTEGER NOT NULL DEFAULT 0, UNIQUE (indicator_code, product_code, data_acct_code))")

        # seed categories
        for cc, cn, so in DRIVER_CATEGORIES:
            conn.execute(
                "INSERT OR IGNORE INTO driver_category(category_code, category_name, sort_order) VALUES (?,?,?)",
                (cc, cn, so),
            )

        # seed indicators
        for cat, code, name, vt, has_prod, has_mon in DRIVER_INDICATORS:
            conn.execute(
                "INSERT OR IGNORE INTO driver_indicator(category_code, indicator_code, indicator_name, value_type, has_product_detail, has_monthly_detail, sort_order) VALUES (?,?,?,?,?,?,0)",
                (cat, code, name, vt, has_prod, has_mon),
            )

        # seed driver_product: bind all '贷' products to indicators with has_product_detail=1
        products = [
            str(r[0]) for r in conn.execute(
                "SELECT product_code FROM product_type WHERE product_name LIKE '%贷%' ORDER BY product_code"
            )
        ]
        indicators = [
            str(r[0]) for r in conn.execute(
                "SELECT indicator_code FROM driver_indicator WHERE has_product_detail = 1 ORDER BY indicator_code"
            )
        ]
        for ic in indicators:
            for pc in products:
                conn.execute(
                    "INSERT OR IGNORE INTO driver_product(indicator_code, product_code) VALUES (?,?)",
                    (ic, pc),
                )

        for indicator_code, product_code, data_acct_code, sort_order in DRIVER_ACCOUNT_MAPPINGS:
            exists = conn.execute(
                """
                SELECT 1
                FROM driver_indicator di
                JOIN product_type pt ON pt.product_code = ?
                JOIN data_account da ON da.data_acct_code = ?
                WHERE di.indicator_code = ?
                """,
                (product_code, data_acct_code, indicator_code),
            ).fetchone()
            if exists:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO driver_account_mapping(
                      indicator_code, product_code, data_acct_code, sort_order
                    ) VALUES (?,?,?,?)
                    """,
                    (indicator_code, product_code, data_acct_code, sort_order),
                )

        conn.commit()
    finally:
        conn.close()


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
        seed_data_account_metric_tree(conn)
        migrate_data_account_budget_rule_columns(conn)
        ensure_assumption_support_tables(conn)
        seed_assumption_defaults(conn)
        ensure_forecast_workbench_tables(conn)
        seed_forecast_workbench_defaults(conn)
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


def migrate_data_account_product_codes(conn: sqlite3.Connection) -> None:
    """Ensure product_codes column exists in data_account table."""
    cur = conn.execute("PRAGMA table_info(data_account)")
    cols = {str(r[1]) for r in cur.fetchall()}
    if "product_codes" not in cols:
        conn.execute(
            "ALTER TABLE data_account ADD COLUMN product_codes TEXT"
        )
    if "metric_group_code" not in cols:
        conn.execute("ALTER TABLE data_account ADD COLUMN metric_group_code TEXT")
    if "metric_group_name" not in cols:
        conn.execute("ALTER TABLE data_account ADD COLUMN metric_group_name TEXT")


def migrate_data_account_budget_rule_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(data_account)")
    cols = {str(r[1]) for r in cur.fetchall()}
    if "budget_rule_code" not in cols:
        conn.execute("ALTER TABLE data_account ADD COLUMN budget_rule_code TEXT")
    if "budget_rule_config_json" not in cols:
        conn.execute("ALTER TABLE data_account ADD COLUMN budget_rule_config_json TEXT")


def ensure_assumption_support_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS scenario_catalog (
          scenario_code TEXT PRIMARY KEY NOT NULL,
          scenario_name TEXT NOT NULL,
          is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
          remark TEXT
        );

        CREATE TABLE IF NOT EXISTS assumption_parameter (
          parameter_code TEXT PRIMARY KEY NOT NULL,
          parameter_name TEXT NOT NULL,
          category TEXT NOT NULL,
          value_type TEXT NOT NULL,
          scope_type TEXT NOT NULL,
          time_granularity TEXT NOT NULL,
          apply_products TEXT,
          input_mode TEXT NOT NULL DEFAULT 'manual',
          value_formula TEXT,
          source_data_code TEXT,
          default_unit TEXT,
          is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
          remark TEXT,
          create_time TEXT NOT NULL,
          update_time TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assumption_value (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          parameter_code TEXT NOT NULL REFERENCES assumption_parameter(parameter_code),
          budget_year INTEGER NOT NULL,
          version_id INTEGER NOT NULL,
          scenario_code TEXT NOT NULL REFERENCES scenario_catalog(scenario_code),
          product_scope_key TEXT NOT NULL DEFAULT '',
          product_code TEXT,
          month_index INTEGER NOT NULL DEFAULT 0 CHECK (month_index BETWEEN 0 AND 12),
          value REAL NOT NULL DEFAULT 0,
          create_time TEXT NOT NULL,
          update_time TEXT NOT NULL,
          UNIQUE (parameter_code, budget_year, version_id, scenario_code, product_scope_key, month_index)
        );

        CREATE TABLE IF NOT EXISTS assumption_rule_template (
          rule_code TEXT PRIMARY KEY NOT NULL,
          rule_name TEXT NOT NULL,
          rule_type TEXT NOT NULL,
          config_json TEXT NOT NULL,
          is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
          remark TEXT,
          create_time TEXT NOT NULL,
          update_time TEXT NOT NULL
        );
        """
    )
    cur = conn.execute("PRAGMA table_info(assumption_parameter)")
    cols = {str(r[1]) for r in cur.fetchall()}
    for column_name, ddl in (
        ("apply_products", "ALTER TABLE assumption_parameter ADD COLUMN apply_products TEXT"),
        ("input_mode", "ALTER TABLE assumption_parameter ADD COLUMN input_mode TEXT NOT NULL DEFAULT 'manual'"),
        ("value_formula", "ALTER TABLE assumption_parameter ADD COLUMN value_formula TEXT"),
        ("source_data_code", "ALTER TABLE assumption_parameter ADD COLUMN source_data_code TEXT"),
    ):
        if column_name not in cols:
            conn.execute(ddl)


def seed_assumption_defaults(conn: sqlite3.Connection) -> None:
    now = _iso_now()
    conn.execute(
        """
        INSERT OR IGNORE INTO scenario_catalog(scenario_code, scenario_name, is_default, remark)
        VALUES ('BASE', '基准场景', 1, 'MVP 默认场景，为后续多场景方案预留。')
        """
    )
    templates = [
        (
            "LOAN_INTEREST_V1",
            "贷款产品利息收入模板",
            "formula_monthly",
            '{"template_family":"interest","formula_expression":"A(\\"AVG_BALANCE\\") * P(\\"CUSTOMER_RATE\\") * DAYS() / 360","data_bindings":{"AVG_BALANCE":""},"parameter_bindings":{"CUSTOMER_RATE":"","AVG_FIN_COST_RATE":"","OVERDUE_90_RATIO":"","CONTRACT_CHANNEL_FEE_RATIO":"","CHANNEL_FEE_EXEMPT_RATIO":""}}',
            "适用于开鑫贷/小小账户等贷款类产品的月度利息收入预测。",
        ),
        (
            "DEPOSIT_INTEREST_V1",
            "存款产品利息支出模板",
            "formula_monthly",
            '{"template_family":"interest","formula_expression":"A(\\"AVG_BALANCE\\") * P(\\"CUSTOMER_RATE\\") * DAYS() / 360","data_bindings":{"AVG_BALANCE":""},"parameter_bindings":{"CUSTOMER_RATE":""}}',
            "适用于存款类产品按日均余额、对客利率和天数测算利息支出。",
        ),
        (
            "EXPENSE_ANNUAL_AVG",
            "费用年度总额平均分月模板",
            "expense_annual_average",
            '{"template_family":"expense","allocation_mode":"average","history_mode":"actual_then_forecast","parameter_bindings":{"EXPENSE_ANNUAL_TOTAL":""}}',
            "适用于单产品费用科目：年度总额扣除已发生实际后在后续月份平均分摊。",
        ),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO assumption_rule_template(
          rule_code, rule_name, rule_type, config_json, remark, create_time, update_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [(code, name, rule_type, config_json, remark, now, now) for code, name, rule_type, config_json, remark in templates],
    )
    parameters = [
        ("CUSTOMER_RATE", "对客利率", "产品利率", "百分比", "product", "monthly", "按产品", "manual", None, None, "%", "对客执行利率。"),
        ("AVG_FIN_COST_RATE", "平均财务利率", "贷款参数", "百分比", "product", "monthly", "按产品", "manual", None, None, "%", "平均财务利率。"),
        ("OVERDUE_90_RATIO", "逾期90天以上贷款占比", "贷款参数", "百分比", "product", "monthly", "按产品", "manual", None, None, "%", "逾期90天以上贷款占比。"),
        ("CONTRACT_CHANNEL_FEE_RATIO", "合同渠道费率", "渠道参数", "百分比", "product", "monthly", "按产品", "manual", None, None, "%", "合同约定渠道费率。"),
        ("CHANNEL_FEE_EXEMPT_RATIO", "免收渠道费占比", "渠道参数", "百分比", "product", "monthly", "按产品", "manual", None, None, "%", "免收渠道费占比。"),
        ("EXPENSE_ANNUAL_TOTAL", "费用年度总额", "费用参数", "金额", "product", "annual", "按产品", "manual", None, None, "元", "费用类科目年度总额。"),
        ("KX_SELF_AVG_BALANCE", "开鑫贷自持日均余额", "开鑫贷规模驱动", "金额", "product", "monthly", "开鑫贷", "manual", None, None, "亿元", "开鑫贷自持业务日均余额。"),
        ("KX_JOINT_AVG_BALANCE", "开鑫贷联贷日均余额", "开鑫贷规模驱动", "金额", "product", "monthly", "开鑫贷", "manual", None, None, "亿元", "开鑫贷联合贷款业务日均余额。"),
        ("KX_PLATFORM_FEE_RATE", "开鑫贷平台费率", "开鑫贷费率参数", "百分比", "product", "monthly", "开鑫贷", "manual", None, None, "%", "开鑫贷联合贷款服务费平台费率。"),
        ("KX_INSURANCE_PREMIUM", "开鑫贷保费支出", "开鑫贷风险参数", "金额", "product", "monthly", "开鑫贷", "manual", None, None, "亿元", "开鑫贷保险代偿相关保费支出。"),
        ("KX_INSURANCE_NET_COMP", "开鑫贷保险代偿净额", "开鑫贷风险参数", "金额", "product", "monthly", "开鑫贷", "manual", None, None, "亿元", "开鑫贷保险代偿净赔付或净补偿金额。"),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO assumption_parameter(
          parameter_code, parameter_name, category, value_type, scope_type,
          time_granularity, apply_products, input_mode, value_formula,
          source_data_code, default_unit, is_enabled, remark, create_time, update_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        [(code, name, category, value_type, scope_type, granularity, products, mode, formula, source, unit, remark, now, now)
         for code, name, category, value_type, scope_type, granularity, products, mode, formula, source, unit, remark in parameters],
    )


def ensure_forecast_workbench_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS forecast_workbench_layout (
          line_code TEXT PRIMARY KEY NOT NULL,
          line_name TEXT NOT NULL,
          line_group TEXT NOT NULL,
          line_category TEXT NOT NULL,
          display_mode TEXT NOT NULL DEFAULT 'detail',
          sort_order INTEGER NOT NULL DEFAULT 0,
          is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
          binding_hint TEXT,
          remark TEXT,
          create_time TEXT NOT NULL,
          update_time TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS forecast_line_binding (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          line_code TEXT NOT NULL REFERENCES forecast_workbench_layout(line_code),
          binding_type TEXT NOT NULL,
          binding_code TEXT NOT NULL,
          binding_name TEXT,
          binding_role TEXT NOT NULL DEFAULT '',
          sort_order INTEGER NOT NULL DEFAULT 0,
          remark TEXT,
          create_time TEXT NOT NULL,
          update_time TEXT NOT NULL,
          UNIQUE (line_code, binding_type, binding_code, binding_role)
        );
        """
    )


def seed_forecast_workbench_defaults(conn: sqlite3.Connection) -> None:
    now = _iso_now()
    lines = [
        ("KX_REV_TOTAL", "营业收入", "开鑫贷", "收入汇总", "detail", 10, "汇总利息净收入、净手续费收入及其他收入", "对应工作簿1“开鑫贷”页营业收入总行。"),
        ("KX_NET_INTEREST", "利息净收入", "开鑫贷", "收入汇总", "detail", 20, "重点绑定日均余额、利率、FTP 与渠道费参数", "对应工作簿1中的利息净收入主线。"),
        ("KX_NET_FEE", "净手续费收入", "开鑫贷", "收入汇总", "detail", 30, "由手续费收入与手续费支出共同驱动", "对应工作簿1中的净手续费收入。"),
        ("KX_PLATFORM_RATE", "平台费率", "开鑫贷", "利率参数", "detail", 40, "用于联合贷服务费收入测算", "对应工作簿1中的平台费率。"),
        ("KX_CHANNEL_FEE", "导流/渠道费", "开鑫贷", "中收支出", "detail", 50, "主要对应渠道费与导流渠道费", "对应工作簿1中的渠道费相关行。"),
        ("KX_RISK_COST", "风险成本", "开鑫贷", "风险成本", "detail", 60, "按不良率、代偿、拨备相关驱动项测算", "对应工作簿1中的风险成本。"),
        ("KX_TAX_SURCHARGE", "税金及附加", "开鑫贷", "费用类", "detail", 70, "可按年度总额模板均摊", "对应工作簿1中的税金及附加。"),
        ("KX_FIXED_MGMT", "固定管理费", "开鑫贷", "费用类", "detail", 80, "适合采用年度总额分摊模板", "对应工作簿1中的固定管理费。"),
        ("KX_SELF_AVG_BAL", "自持日均余额", "开鑫贷", "规模驱动", "detail", 90, "作为自持利息收入、风险成本、渠道费的重要规模底座", "对应工作簿1中的自持日均余额。"),
        ("KX_JOINT_AVG_BAL", "联贷日均余额", "开鑫贷", "规模驱动", "detail", 100, "作为联合贷平台费、催收等测算底座", "对应工作簿1中的联贷日均余额。"),
        ("XXA_REV_TOTAL", "营业收入", "小小账户", "收入汇总", "detail", 300, "沿用与开鑫贷一致的汇总逻辑，但单独展示", "对应工作簿1“小小账户”页营业收入总行。"),
        ("XXA_NET_INTEREST", "利息净收入", "小小账户", "收入汇总", "detail", 310, "沿用利息净收入主线并单独观测", "对应工作簿1“小小账户”页利息净收入。"),
        ("XXA_NET_FEE", "净手续费收入", "小小账户", "收入汇总", "detail", 320, "沿用手续费净收入主线并单独观测", "对应工作簿1“小小账户”页净手续费收入。"),
    ]
    bindings = [
        ("KX_REV_TOTAL", "report_account", "A01", "", "report_anchor", 10, "营业收入总览锚点"),
        ("KX_NET_INTEREST", "assumption_rule_template", "LOAN_INTEREST_V1", "", "template", 10, "贷款利息收入模板"),
        ("KX_NET_INTEREST", "assumption_parameter", "CUSTOMER_RATE", "", "rate", 20, "对客利率"),
        ("KX_NET_INTEREST", "assumption_parameter", "AVG_FIN_COST_RATE", "", "rate", 30, "平均财务利率"),
        ("KX_NET_INTEREST", "assumption_parameter", "OVERDUE_90_RATIO", "", "ratio", 40, "逾期90+占比"),
        ("KX_SELF_AVG_BAL", "assumption_parameter", "KX_SELF_AVG_BALANCE", "", "scale", 10, "开鑫贷自持日均余额参数"),
        ("KX_JOINT_AVG_BAL", "assumption_parameter", "KX_JOINT_AVG_BALANCE", "", "scale", 10, "开鑫贷联贷日均余额参数"),
        ("KX_PLATFORM_RATE", "assumption_parameter", "KX_PLATFORM_FEE_RATE", "", "rate", 10, "开鑫贷平台费率参数"),
        ("KX_TAX_SURCHARGE", "assumption_rule_template", "EXPENSE_ANNUAL_AVG", "", "template", 10, "年度总额平均分月"),
        ("KX_FIXED_MGMT", "assumption_rule_template", "EXPENSE_ANNUAL_AVG", "", "template", 10, "年度总额平均分月"),
        ("KX_RISK_COST", "assumption_parameter", "KX_INSURANCE_NET_COMP", "", "risk_adjustment", 40, "保险代偿净额对风险成本的抵减影响"),
        ("XXA_REV_TOTAL", "report_account", "A01", "", "report_anchor", 10, "营业收入总览锚点"),
        ("XXA_NET_INTEREST", "assumption_rule_template", "LOAN_INTEREST_V1", "", "template", 10, "贷款利息收入模板"),
        ("XXA_NET_FEE", "report_account", "A03", "", "report_anchor", 10, "净手续费收入锚点"),
    ]
    conn.executemany(
        """
        INSERT INTO forecast_workbench_layout(
          line_code, line_name, line_group, line_category, display_mode,
          sort_order, binding_hint, remark, create_time, update_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(line_code) DO UPDATE SET
          line_name = excluded.line_name,
          line_group = excluded.line_group,
          line_category = excluded.line_category,
          display_mode = excluded.display_mode,
          sort_order = excluded.sort_order,
          is_enabled = 1,
          binding_hint = excluded.binding_hint,
          remark = excluded.remark,
          update_time = excluded.update_time
        """,
        [(line_code, line_name, line_group, line_category, display_mode, sort_order, hint, remark, now, now)
         for line_code, line_name, line_group, line_category, display_mode, sort_order, hint, remark in lines],
    )
    conn.executemany(
        """
        INSERT INTO forecast_line_binding(
          line_code, binding_type, binding_code, binding_name, binding_role,
          sort_order, remark, create_time, update_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(line_code, binding_type, binding_code, binding_role) DO UPDATE SET
          binding_name = excluded.binding_name,
          sort_order = excluded.sort_order,
          remark = excluded.remark,
          update_time = excluded.update_time
        """,
        [(line_code, binding_type, binding_code, binding_name, role, sort_order, remark, now, now)
         for line_code, binding_type, binding_code, binding_name, role, sort_order, remark in bindings],
    )


def ensure_data_account_metric_tables(conn: sqlite3.Connection) -> None:
    """Create the business metric tree tables used above data_account."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS data_account_metric_node (
          node_code TEXT PRIMARY KEY NOT NULL,
          node_name TEXT NOT NULL,
          parent_code TEXT REFERENCES data_account_metric_node(node_code),
          level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 8),
          node_type TEXT NOT NULL CHECK (node_type IN ('CATEGORY', 'GROUP', 'METRIC')),
          sort_order INTEGER NOT NULL DEFAULT 0,
          is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
          remark TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS data_account_metric_binding (
          binding_code TEXT PRIMARY KEY NOT NULL,
          metric_node_code TEXT NOT NULL REFERENCES data_account_metric_node(node_code),
          scope_type TEXT NOT NULL CHECK (scope_type IN ('PRODUCT', 'CORP')),
          scope_code TEXT NOT NULL,
          product_code TEXT REFERENCES product_type(product_code),
          data_acct_code TEXT NOT NULL REFERENCES data_account(data_acct_code),
          sort_order INTEGER NOT NULL DEFAULT 0,
          is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
          remark TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (metric_node_code, scope_code),
          UNIQUE (data_acct_code, scope_code),
          CHECK (
            (scope_type = 'CORP' AND scope_code = 'CORP' AND product_code IS NULL)
            OR
            (scope_type = 'PRODUCT' AND scope_code = product_code AND product_code IS NOT NULL)
          )
        );

        CREATE INDEX IF NOT EXISTS idx_data_account_metric_node_parent
        ON data_account_metric_node(parent_code);

        CREATE INDEX IF NOT EXISTS idx_data_account_metric_binding_metric
        ON data_account_metric_binding(metric_node_code);

        CREATE INDEX IF NOT EXISTS idx_data_account_metric_binding_data
        ON data_account_metric_binding(data_acct_code);
        """
    )


def _metric_category_for(metric_name: str) -> tuple[str, str]:
    if any(x in metric_name for x in ("费用", "薪金", "奖金", "营销", "人力")):
        return "05", "费用指标"
    if any(x in metric_name for x in ("收益率", "付息率", "FTP利率", "成本率", "利率", "年化")):
        return "02", "利率与收益率"
    if any(x in metric_name for x in ("收入", "利息收入", "营业收入", "平台费", "中收")):
        return "03", "收入指标"
    if any(x in metric_name for x in ("利息支出", "FTP利息支出", "风险成本", "减值损失", "拨备", "成本")):
        return "04", "成本与风险"
    if any(x in metric_name for x in ("日均", "余额", "时点", "规模", "总额", "存款", "贷款", "投资", "资产", "负债", "管理资产")):
        return "01", "规模与余额"
    return "09", "其他指标"


def _metric_group_for(metric_name: str, category_code: str) -> str:
    if category_code == "01":
        if "日均" in metric_name:
            return "日均指标"
        if "余额" in metric_name or "时点" in metric_name:
            return "余额与时点"
        return "规模指标"
    if category_code == "02":
        if "FTP" in metric_name:
            return "FTP利率"
        if "付息率" in metric_name:
            return "付息率"
        return "收益率"
    if category_code == "03":
        if "利息收入" in metric_name:
            return "利息收入"
        if "平台费" in metric_name or "中收" in metric_name:
            return "中间业务收入"
        return "其他收入"
    if category_code == "04":
        if "风险" in metric_name or "减值" in metric_name or "拨备" in metric_name:
            return "风险成本"
        if "FTP" in metric_name:
            return "FTP利息支出"
        return "利息与资金成本"
    if category_code == "05":
        if "人力" in metric_name or "薪金" in metric_name or "奖金" in metric_name:
            return "人力费用"
        if "营销" in metric_name:
            return "营销费用"
        return "其他费用"
    return "未归类指标"


def _strip_metric_product_prefix(name: str, product_names: list[tuple[str, str]]) -> str:
    for product_name, _product_code in product_names:
        if product_name and name.startswith(product_name):
            return name[len(product_name):].lstrip("_- ")
    manual_prefixes = ("开鑫贷单品", "开鑫贷分期", "车车贷", "企企贷", "开心小账户", "其他小小产品", "企小乐", "小企业保证金")
    for prefix in manual_prefixes:
        if name.startswith(prefix):
            return name[len(prefix):].lstrip("_- ")
    return name


def seed_data_account_metric_tree(conn: sqlite3.Connection) -> None:
    """Build an initial metric tree from existing data accounts when no bindings exist."""
    ensure_data_account_metric_tables(conn)
    cur = conn.execute("SELECT COUNT(*) FROM data_account_metric_binding")
    if int(cur.fetchone()[0] or 0) > 0:
        return

    product_names = [
        (str(name or "").strip(), str(code or "").strip().upper())
        for code, name in conn.execute("SELECT product_code, product_name FROM product_type ORDER BY LENGTH(product_name) DESC")
        if name
    ]
    rows = list(
        conn.execute(
            """
            SELECT data_acct_code, data_acct_name, metric_group_code, metric_group_name, product_codes
            FROM data_account
            ORDER BY data_acct_code
            """
        )
    )
    node_name_to_code: dict[tuple[str, str], str] = {}
    child_count: dict[str, int] = {}

    def ensure_node(code: str, name: str, parent: str | None, node_type: str, sort_order: int) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO data_account_metric_node(
              node_code, node_name, parent_code, level, node_type, sort_order, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                name,
                parent,
                code.count(".") + 1,
                node_type,
                sort_order,
                "系统按数据科目初始化生成",
            ),
        )

    def ensure_child(parent_code: str, node_name: str, node_type: str) -> str:
        key = (parent_code, node_name)
        existing = node_name_to_code.get(key)
        if existing:
            return existing
        child_count[parent_code] = child_count.get(parent_code, 0) + 1
        code = f"{parent_code}.{child_count[parent_code]:02d}"
        node_name_to_code[key] = code
        ensure_node(code, node_name, parent_code, node_type, child_count[parent_code] * 10)
        return code

    roots_seen: set[str] = set()
    for row in rows:
        data_code = str(row[0] or "").strip().upper()
        data_name = str(row[1] or "").strip()
        metric_group_code = str(row[2] or "").strip()
        metric_group_name = str(row[3] or "").strip()
        product_codes_raw = str(row[4] or "").strip().upper()
        if not data_code or not data_name:
            continue

        metric_name = metric_group_name or _strip_metric_product_prefix(data_name, product_names).strip("_- ") or data_name
        category_code, category_name = _metric_category_for(metric_name)
        if category_code not in roots_seen:
            ensure_node(category_code, category_name, None, "CATEGORY", int(category_code) * 10)
            roots_seen.add(category_code)

        group_name = _metric_group_for(metric_name, category_code)
        group_code = ensure_child(category_code, group_name, "GROUP")
        if metric_group_code and "." in metric_group_code:
            metric_node_code = metric_group_code
            parent = ".".join(metric_node_code.split(".")[:-1]) or group_code
            if parent != group_code and parent not in roots_seen:
                ensure_node(parent, group_name, category_code, "GROUP", 0)
            ensure_node(metric_node_code, metric_name, parent, "METRIC", 0)
        else:
            metric_node_code = ensure_child(group_code, metric_name, "METRIC")

        product_codes = [p.strip().upper() for p in product_codes_raw.split(",") if p.strip() and p.strip().upper() != "ALL"]
        if not product_codes:
            product_codes = ["CORP"]
        for product_code in product_codes:
            scope_type = "CORP" if product_code == "CORP" else "PRODUCT"
            product_value = None if scope_type == "CORP" else product_code
            binding_code = f"{metric_node_code}.{product_code}"
            conn.execute(
                """
                INSERT OR IGNORE INTO data_account_metric_binding(
                  binding_code, metric_node_code, scope_type, scope_code, product_code,
                  data_acct_code, sort_order, remark
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    binding_code,
                    metric_node_code,
                    scope_type,
                    product_code,
                    product_value,
                    data_code,
                    0,
                    "系统按数据科目初始化生成",
                ),
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
                    "SELECT data_acct_code, product_code, product_codes FROM data_account"
                )
            )
            da_map = {str(r[0]): (r[1], r[2]) for r in da_rows}
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
            migrate_data_account_product_codes(conn)
            migrate_data_account_budget_rule_columns(conn)
            seed_data_account_metric_tree(conn)
            ensure_assumption_support_tables(conn)
            seed_assumption_defaults(conn)
            ensure_forecast_workbench_tables(conn)
            seed_forecast_workbench_defaults(conn)
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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS smart_report_template (
                  template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  template_code TEXT NOT NULL UNIQUE,
                  template_name TEXT NOT NULL,
                  template_type TEXT NOT NULL DEFAULT 'analysis' CHECK (template_type IN ('analysis', 'report', 'summary', 'ppt')),
                  file_path TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
                  version_no INTEGER NOT NULL DEFAULT 1,
                  remark TEXT,
                  created_by TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS smart_report_template_variable (
                  variable_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  template_id INTEGER NOT NULL REFERENCES smart_report_template(template_id) ON DELETE CASCADE,
                  variable_key TEXT NOT NULL,
                  variable_name TEXT NOT NULL,
                  variable_type TEXT NOT NULL CHECK (variable_type IN ('metric', 'formula', 'calc', 'parameter', 'text', 'table', 'chart', 'analysis')),
                  binding_config_json TEXT,
                  display_order INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE (template_id, variable_key)
                );

                CREATE TABLE IF NOT EXISTS smart_report_calc_metric (
                  metric_code TEXT PRIMARY KEY NOT NULL,
                  metric_name TEXT NOT NULL,
                  expression TEXT NOT NULL,
                  components_json TEXT NOT NULL,
                  value_type TEXT NOT NULL DEFAULT '金额',
                  format_type TEXT NOT NULL DEFAULT 'number',
                  remark TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS smart_report_definition (
                  report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  template_id INTEGER NOT NULL REFERENCES smart_report_template(template_id),
                  report_name TEXT NOT NULL,
                  report_scene TEXT,
                  parameter_schema_json TEXT,
                  section_schema_json TEXT,
                  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS smart_report_instance (
                  instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  report_id INTEGER REFERENCES smart_report_definition(report_id),
                  template_id INTEGER NOT NULL REFERENCES smart_report_template(template_id),
                  instance_name TEXT NOT NULL,
                  parameter_values_json TEXT NOT NULL,
                  text_values_json TEXT,
                  data_snapshot_json TEXT,
                  output_file_path TEXT,
                  generation_status TEXT NOT NULL DEFAULT 'pending' CHECK (generation_status IN ('pending', 'running', 'success', 'failed')),
                  error_message TEXT,
                  last_generated_at TEXT,
                  last_refresh_at TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS smart_report_job (
                  job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  instance_id INTEGER REFERENCES smart_report_instance(instance_id) ON DELETE SET NULL,
                  job_type TEXT NOT NULL CHECK (job_type IN ('generate', 'refresh')),
                  job_status TEXT NOT NULL CHECK (job_status IN ('pending', 'running', 'success', 'failed')),
                  started_at TEXT,
                  finished_at TEXT,
                  error_message TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_smart_report_variable_template
                ON smart_report_template_variable(template_id);

                CREATE INDEX IF NOT EXISTS idx_smart_report_instance_template
                ON smart_report_instance(template_id);
                """
            )
            cur = conn.execute("PRAGMA table_info(smart_report_instance)")
            smart_report_instance_cols = {str(r[1]) for r in cur.fetchall()}
            if "text_values_json" not in smart_report_instance_cols:
                conn.execute("ALTER TABLE smart_report_instance ADD COLUMN text_values_json TEXT")
            cur = conn.execute(
                """
                SELECT sql FROM sqlite_master
                WHERE type = 'table' AND name = 'smart_report_template'
                """
            )
            row = cur.fetchone()
            template_table_sql = str(row[0] or "") if row else ""
            if "template_type" in template_table_sql and "CHECK" in template_table_sql and "'ppt'" not in template_table_sql:
                conn.executescript(
                    """
                    PRAGMA foreign_keys = OFF;
                    CREATE TABLE smart_report_template_new (
                      template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                      template_code TEXT NOT NULL UNIQUE,
                      template_name TEXT NOT NULL,
                      template_type TEXT NOT NULL DEFAULT 'analysis' CHECK (template_type IN ('analysis', 'report', 'summary', 'ppt')),
                      file_path TEXT NOT NULL,
                      status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
                      version_no INTEGER NOT NULL DEFAULT 1,
                      remark TEXT,
                      created_by TEXT,
                      created_at TEXT NOT NULL,
                      updated_at TEXT NOT NULL
                    );
                    INSERT INTO smart_report_template_new (
                      template_id, template_code, template_name, template_type, file_path,
                      status, version_no, remark, created_by, created_at, updated_at
                    )
                    SELECT template_id, template_code, template_name, template_type, file_path,
                           status, version_no, remark, created_by, created_at, updated_at
                    FROM smart_report_template;
                    DROP TABLE smart_report_template;
                    ALTER TABLE smart_report_template_new RENAME TO smart_report_template;
                    PRAGMA foreign_keys = ON;
                    """
                )
            cur = conn.execute(
                """
                SELECT sql FROM sqlite_master
                WHERE type = 'table' AND name = 'smart_report_template_variable'
                """
            )
            row = cur.fetchone()
            variable_table_sql = str(row[0] or "") if row else ""
            if "formula" not in variable_table_sql or "'calc'" not in variable_table_sql:
                conn.executescript(
                    """
                    PRAGMA foreign_keys = OFF;
                    CREATE TABLE smart_report_template_variable_new (
                      variable_id INTEGER PRIMARY KEY AUTOINCREMENT,
                      template_id INTEGER NOT NULL REFERENCES smart_report_template(template_id) ON DELETE CASCADE,
                      variable_key TEXT NOT NULL,
                      variable_name TEXT NOT NULL,
                      variable_type TEXT NOT NULL CHECK (variable_type IN ('metric', 'formula', 'calc', 'parameter', 'text', 'table', 'chart', 'analysis')),
                      binding_config_json TEXT,
                      display_order INTEGER NOT NULL DEFAULT 0,
                      created_at TEXT NOT NULL,
                      updated_at TEXT NOT NULL,
                      UNIQUE (template_id, variable_key)
                    );
                    INSERT INTO smart_report_template_variable_new (
                      variable_id, template_id, variable_key, variable_name, variable_type,
                      binding_config_json, display_order, created_at, updated_at
                    )
                    SELECT variable_id, template_id, variable_key, variable_name, variable_type,
                           binding_config_json, display_order, created_at, updated_at
                    FROM smart_report_template_variable;
                    DROP TABLE smart_report_template_variable;
                    ALTER TABLE smart_report_template_variable_new RENAME TO smart_report_template_variable;
                    CREATE INDEX IF NOT EXISTS idx_smart_report_variable_template
                    ON smart_report_template_variable(template_id);
                    PRAGMA foreign_keys = ON;
                    """
                )
            conn.executescript(
                """
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

                CREATE TABLE IF NOT EXISTS expense_execution_monthly (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  owner_name TEXT NOT NULL,
                  budget_subject TEXT NOT NULL,
                  month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
                  amount REAL NOT NULL DEFAULT 0,
                  UNIQUE (owner_name, budget_subject, month)
                );

                CREATE TABLE IF NOT EXISTS budget_subject_catalog (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  parent_id INTEGER REFERENCES budget_subject_catalog(id) ON DELETE RESTRICT,
                  level_number INTEGER NOT NULL CHECK (level_number BETWEEN 1 AND 5),
                  subject_name TEXT NOT NULL,
                  formula_text TEXT,
                  sort_order INTEGER NOT NULL DEFAULT 0
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
                );

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
                );
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

    # 驱动模块预置数据
    _seed_driver_data(common)

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
