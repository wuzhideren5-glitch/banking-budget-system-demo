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
  budget_formula TEXT,
  actual_formula TEXT,
  need_calc INTEGER NOT NULL DEFAULT 0 CHECK (need_calc IN (0, 1)),
  budget_rule_code TEXT,
  budget_rule_config_json TEXT,
  value_type TEXT NOT NULL,
  product_codes TEXT,
  remark TEXT
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


def migrate_data_account_product_codes(conn: sqlite3.Connection) -> None:
    """Ensure product_codes column exists in data_account table."""
    cur = conn.execute("PRAGMA table_info(data_account)")
    cols = {str(r[1]) for r in cur.fetchall()}
    if "product_codes" not in cols:
        conn.execute(
            "ALTER TABLE data_account ADD COLUMN product_codes TEXT"
        )


def migrate_data_account_budget_rule_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(data_account)")
    cols = {str(r[1]) for r in cur.fetchall()}
    if "budget_rule_code" not in cols:
        conn.execute("ALTER TABLE data_account ADD COLUMN budget_rule_code TEXT")
    if "budget_rule_config_json" not in cols:
        conn.execute("ALTER TABLE data_account ADD COLUMN budget_rule_config_json TEXT")


def ensure_assumption_support_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scenario_catalog (
          scenario_code TEXT PRIMARY KEY NOT NULL,
          scenario_name TEXT NOT NULL,
          is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
          remark TEXT
        )
        """
    )
    conn.execute(
        """
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
        )
        """
    )
    conn.execute(
        """
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
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assumption_rule_template (
          rule_code TEXT PRIMARY KEY NOT NULL,
          rule_name TEXT NOT NULL,
          rule_type TEXT NOT NULL,
          config_json TEXT NOT NULL,
          is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
          remark TEXT,
          create_time TEXT NOT NULL,
          update_time TEXT NOT NULL
        )
        """
    )
    cur = conn.execute("PRAGMA table_info(assumption_parameter)")
    cols = {str(r[1]) for r in cur.fetchall()}
    if "apply_products" not in cols:
        conn.execute("ALTER TABLE assumption_parameter ADD COLUMN apply_products TEXT")
    if "input_mode" not in cols:
        conn.execute("ALTER TABLE assumption_parameter ADD COLUMN input_mode TEXT NOT NULL DEFAULT 'manual'")
    if "value_formula" not in cols:
        conn.execute("ALTER TABLE assumption_parameter ADD COLUMN value_formula TEXT")
    if "source_data_code" not in cols:
        conn.execute("ALTER TABLE assumption_parameter ADD COLUMN source_data_code TEXT")


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
            "DEPOSIT_INTEREST_V1",
            "存款产品1利息支出",
            "formula_monthly",
            (
                '{"template_family":"interest","supports_scenario":true,'
                '"formula_expression":"A(\\"AVG_BALANCE\\") * P(\\"CUSTOMER_RATE\\") * DAYS() / 360",'
                '"data_bindings":{"AVG_BALANCE":""},"parameter_bindings":{"CUSTOMER_RATE":""}}'
            ),
            "每月利息支出 = 存款月均规模 * 对客利率 * 当月天数 / 360。",
        ),
        (
            "DEPOSIT_INTEREST_V2",
            "存款产品2利息支出",
            "formula_monthly",
            (
                '{"template_family":"interest","supports_scenario":true,'
                '"formula_expression":"A(\\"AVG_BALANCE\\") * P(\\"CUSTOMER_RATE\\") * DAYS() / 360 + '
                'A(\\"AVG_BALANCE\\") * (('
                'P(\\"LEGAL_RESERVE_RATE\\") * DAYS() / 360 * P(\\"LEGAL_RESERVE_RATIO\\") + '
                'P(\\"EXCESS_RESERVE_RATE\\") * DAYS() / 360 * P(\\"EXCESS_RESERVE_RATIO\\") + '
                'P(\\"NCD_RATE\\") * MAX(0, MIN(1 - P(\\"LEGAL_RESERVE_RATIO\\") - P(\\"EXCESS_RESERVE_RATIO\\"), P(\\"LOAN_EX_BILL_RATIO\\"))) + '
                'P(\\"INTERBANK_ASSET_YIELD\\") * MAX(0, 1 - P(\\"LEGAL_RESERVE_RATIO\\") - P(\\"EXCESS_RESERVE_RATIO\\")) - '
                'P(\\"CUSTOMER_RATE\\")'
                ') / 360 * DAYS() * P(\\"CHANNEL_FEE_RATIO\\"))",'
                '"data_bindings":{"AVG_BALANCE":""},'
                '"parameter_bindings":{"CUSTOMER_RATE":"","LEGAL_RESERVE_RATE":"","LEGAL_RESERVE_RATIO":"","EXCESS_RESERVE_RATE":"","EXCESS_RESERVE_RATIO":"","NCD_RATE":"","LOAN_EX_BILL_RATIO":"","INTERBANK_ASSET_YIELD":"","CHANNEL_FEE_RATIO":""}}'
            ),
            "每月利息支出 = 对客利息支出 + 渠道费，其中渠道费率按法准/超准/同业存单/同业资产收益综合测算。",
        ),
        (
            "DEPOSIT_INTEREST_V3",
            "存款产品3利息支出",
            "formula_monthly",
            (
                '{"template_family":"interest","supports_scenario":true,'
                '"formula_expression":"A(\\"AVG_BALANCE\\") * P(\\"CUSTOMER_RATE\\") * DAYS() / 360 + '
                'A(\\"AVG_BALANCE\\") * (('
                'P(\\"LEGAL_RESERVE_RATE\\") * 365 / 360 * P(\\"LEGAL_RESERVE_RATIO\\") + '
                'P(\\"EXCESS_RESERVE_RATE\\") * 365 / 360 * (1 - P(\\"LEGAL_RESERVE_RATIO\\")) * 0.5 + '
                'P(\\"PLACEMENT_CURRENT_YIELD\\") * (1 - P(\\"LEGAL_RESERVE_RATIO\\")) * 0.5 - '
                'P(\\"CUSTOMER_RATE\\")'
                ') / 360 * DAYS() * P(\\"CHANNEL_FEE_RATIO\\"))",'
                '"data_bindings":{"AVG_BALANCE":""},'
                '"parameter_bindings":{"CUSTOMER_RATE":"","LEGAL_RESERVE_RATE":"","LEGAL_RESERVE_RATIO":"","EXCESS_RESERVE_RATE":"","PLACEMENT_CURRENT_YIELD":"","CHANNEL_FEE_RATIO":""}}'
            ),
            "每月利息支出 = 对客利息支出 + 渠道费，渠道费率按法准/超准/存放同业活期收益综合测算。",
        ),
        (
            "LOAN_INTEREST_V1",
            "贷款产品1利息收入",
            "formula_monthly",
            (
                '{"template_family":"interest","supports_scenario":true,'
                '"formula_expression":"A(\\"AVG_BALANCE\\") * P(\\"CUSTOMER_RATE\\") * DAYS() / 360 - '
                'A(\\"AVG_BALANCE\\") * ((P(\\"AVG_FIN_COST_RATE\\") / 1.06 * (1 - P(\\"OVERDUE_90_RATIO\\")) * P(\\"PENALTY_INTEREST_RATIO\\") - P(\\"NCD_RATE\\")) * '
                'P(\\"CONTRACT_CHANNEL_FEE_RATIO\\") * (1 - P(\\"CHANNEL_FEE_EXEMPT_RATIO\\")) / 1.06) * DAYS() / 360",'
                '"data_bindings":{"AVG_BALANCE":""},'
                '"parameter_bindings":{"CUSTOMER_RATE":"","AVG_FIN_COST_RATE":"","OVERDUE_90_RATIO":"","PENALTY_INTEREST_RATIO":"","NCD_RATE":"","CONTRACT_CHANNEL_FEE_RATIO":"","CHANNEL_FEE_EXEMPT_RATIO":""}}'
            ),
            "每月利息收入 = 对客利息收入 - 渠道费支出，其中渠道费率按平均财务利率、逾期占比、罚息比例及同业存单利率测算。",
        ),
        (
            "LOAN_INTEREST_V2",
            "贷款产品2利息收入",
            "formula_monthly",
            (
                '{"template_family":"interest","supports_scenario":true,'
                '"formula_expression":"A(\\"AVG_BALANCE\\") * P(\\"CUSTOMER_RATE\\") * DAYS() / 360 - '
                'A(\\"AVG_BALANCE\\") * (P(\\"LOAN_ACTUAL_RATE\\") * P(\\"CONTRACT_CHANNEL_FEE_RATIO\\") * P(\\"RECEIVED_INTEREST_RATIO\\")) * DAYS() / 360",'
                '"data_bindings":{"AVG_BALANCE":""},'
                '"parameter_bindings":{"CUSTOMER_RATE":"","LOAN_ACTUAL_RATE":"","CONTRACT_CHANNEL_FEE_RATIO":"","RECEIVED_INTEREST_RATIO":""}}'
            ),
            "每月利息收入 = 对客利息收入 - 渠道费支出，其中渠道费率 = 贷款实际利率 * 合同渠道费率 * 实收利息比例。",
        ),
        (
            "DEPOSIT_INTEREST_ACTUAL_RATE",
            "存款利息支出（上月实际利率）",
            "formula_monthly",
            (
                '{"template_family":"interest","supports_scenario":true,'
                '"formula_expression":"A(\\"AVG_BALANCE\\") * PREV_ACTUAL(\\"ACTUAL_CUSTOMER_RATE\\") * DAYS() / 360",'
                '"data_bindings":{"AVG_BALANCE":"","ACTUAL_CUSTOMER_RATE":""},'
                '"parameter_bindings":{}}'
            ),
            "每月利息支出 = 存款月均规模 * 上月实际对客利率 * 当月天数 / 360。",
        ),
        (
            "LOAN_INTEREST_V3",
            "贷款产品3利息收入",
            "formula_monthly",
            (
                '{"template_family":"interest","supports_scenario":true,'
                '"formula_expression":"A(\\"AVG_BALANCE\\") * PREV_ACTUAL(\\"ACTUAL_CUSTOMER_RATE\\") * DAYS() / 360",'
                '"data_bindings":{"AVG_BALANCE":"","ACTUAL_CUSTOMER_RATE":""},'
                '"parameter_bindings":{}}'
            ),
            "每月利息收入 = 贷款月均规模 * 上月实际对客利率 * 当月天数 / 360。",
        ),
        (
            "EXPENSE_ANNUAL_AVG",
            "费用年度总额平均分月",
            "expense_annual_average",
            (
                '{"template_family":"expense","allocation_mode":"average","product_split_mode":"none",'
                '"history_mode":"actual_then_forecast","supports_scenario":true}'
            ),
            "适用于单产品费用科目：先取全年总额，再扣截止当前月累计实际，剩余金额在后续月份平均分摊。",
        ),
        (
            "EXPENSE_ANNUAL_PRODUCT_AVG",
            "费用年度总额按产品拆分后分月",
            "expense_annual_product_average",
            (
                '{"template_family":"expense","allocation_mode":"average","product_split_mode":"equal",'
                '"history_mode":"actual_then_forecast","supports_scenario":true}'
            ),
            "适用于多产品费用科目：先按产品平均拆分年度总额，再按各产品剩余金额对后续月份平均分摊。",
        ),
    ]
    parameters = [
        ("LEGAL_RESERVE_RATE", "法准利率", "监管与利率", "百分比", "global", "monthly", "%", "法定准备金利率。"),
        ("EXCESS_RESERVE_RATE", "超准利率", "监管与利率", "百分比", "global", "monthly", "%", "超额准备金利率。"),
        ("LEGAL_RESERVE_RATIO", "法定存款准备金比例", "监管与利率", "百分比", "global", "monthly", "%", "法定存款准备金比例。"),
        ("EXCESS_RESERVE_RATIO", "超准比例", "监管与利率", "百分比", "global", "monthly", "%", "超额准备金占比。"),
        ("NCD_RATE", "同业存单利率", "监管与利率", "百分比", "global", "monthly", "%", "同业存单利率。"),
        ("INTERBANK_ASSET_YIELD", "同业资产收益率", "监管与利率", "百分比", "global", "monthly", "%", "同业资产收益率。"),
        ("PLACEMENT_CURRENT_YIELD", "存放同业活期收益率", "监管与利率", "百分比", "global", "monthly", "%", "存放同业活期收益率。"),
        ("LOAN_EX_BILL_RATIO", "各项贷款不含票据比例", "贷款参数", "百分比", "global", "monthly", "%", "各项贷款（不含票据）比例。"),
        ("CUSTOMER_RATE", "对客利率", "产品利率", "百分比", "product", "monthly", "%", "对客执行利率。"),
        ("CHANNEL_FEE_RATIO", "渠道费率", "渠道参数", "百分比", "product", "monthly", "%", "渠道费比率或折算系数。"),
        ("AVG_FIN_COST_RATE", "平均财务利率", "贷款参数", "百分比", "product", "monthly", "%", "平均财务利率。"),
        ("OVERDUE_90_RATIO", "逾期90天以上贷款占比", "贷款参数", "百分比", "product", "monthly", "%", "逾期90天以上贷款占比。"),
        ("PENALTY_INTEREST_RATIO", "逾期罚息比例", "贷款参数", "百分比", "product", "monthly", "%", "逾期罚息比例。"),
        ("CONTRACT_CHANNEL_FEE_RATIO", "合同渠道费率", "渠道参数", "百分比", "product", "monthly", "%", "合同约定渠道费率。"),
        ("CHANNEL_FEE_EXEMPT_RATIO", "免收渠道费占比", "渠道参数", "百分比", "product", "monthly", "%", "免收渠道费占比。"),
        ("LOAN_ACTUAL_RATE", "贷款实际利率", "贷款参数", "百分比", "product", "monthly", "%", "贷款实际利率。"),
        ("RECEIVED_INTEREST_RATIO", "实收利息比例", "贷款参数", "百分比", "product", "monthly", "%", "实收利息比例。"),
        ("EXPENSE_ANNUAL_TOTAL", "费用年度总额", "费用参数", "金额", "product", "annual", "元", "费用类科目年度总额。"),
        ("KX_SELF_AVG_BALANCE", "开鑫贷自持日均余额", "开鑫贷规模驱动", "金额", "product", "monthly", "亿元", "开鑫贷自持业务日均余额。"),
        ("KX_JOINT_AVG_BALANCE", "开鑫贷联贷日均余额", "开鑫贷规模驱动", "金额", "product", "monthly", "亿元", "开鑫贷联合贷款业务日均余额。"),
        ("KX_PLATFORM_FEE_RATE", "开鑫贷平台费率", "开鑫贷费率参数", "百分比", "product", "monthly", "%", "开鑫贷联合贷款服务费平台费率。"),
        ("KX_INSURANCE_PREMIUM", "开鑫贷保费支出", "开鑫贷风险参数", "金额", "product", "monthly", "亿元", "开鑫贷保险代偿相关保费支出。"),
        ("KX_INSURANCE_NET_COMP", "开鑫贷保险代偿净额", "开鑫贷风险参数", "金额", "product", "monthly", "亿元", "开鑫贷保险代偿净赔付或净补偿金额。"),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO assumption_rule_template(
          rule_code, rule_name, rule_type, config_json, remark, create_time, update_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [(code, name, rule_type, config_json, remark, now, now) for code, name, rule_type, config_json, remark in templates],
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO assumption_parameter(
          parameter_code, parameter_name, category, value_type, scope_type,
          time_granularity, default_unit, is_enabled, remark, create_time, update_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        [
            (code, name, category, value_type, scope_type, granularity, unit, remark, now, now)
            for code, name, category, value_type, scope_type, granularity, unit, remark in parameters
        ],
    )


def ensure_forecast_workbench_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
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
        )
        """
    )
    conn.execute(
        """
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
        )
        """
    )


def seed_forecast_workbench_defaults(conn: sqlite3.Connection) -> None:
    now = _iso_now()
    retired_line_codes = [
        "REV_INTEREST_INCOME",
        "REV_INTEREST_EXPENSE",
        "REV_FEE_INCOME",
        "REV_FEE_EXPENSE",
        "COST_BUSINESS_TAX",
        "COST_MANAGE_TAX",
        "BALANCE_AVG_SCALE",
    ]
    retired_anchor_bindings = [
        ("KX_SELF_AVG_BAL", "binding_hint", "SELF_AVG_BALANCE"),
        ("KX_JOINT_AVG_BAL", "binding_hint", "JOINT_AVG_BALANCE"),
        ("KX_PLATFORM_RATE", "binding_hint", "PLATFORM_RATE"),
        ("KX_RISK_COST", "binding_hint", "INSURANCE_COMP"),
        ("KX_INSURANCE", "binding_hint", "INSURANCE_PREMIUM"),
        ("KX_INSURANCE_NET", "binding_hint", "INSURANCE_NET_COMP"),
    ]
    lines = [
        ("KX_REV_TOTAL", "营业收入", "开鑫贷", "收入汇总", "detail", 10, "汇总利息净收入、净手续费收入及其他收入", "对应工作簿1“开鑫贷”页营业收入总行。"),
        ("KX_NET_INTEREST", "利息净收入", "开鑫贷", "收入汇总", "detail", 20, "重点绑定日均余额、利率、FTP 与渠道费参数", "对应工作簿1中的利息净收入主线。"),
        ("KX_NET_FEE", "净手续费收入", "开鑫贷", "收入汇总", "detail", 30, "由手续费收入与手续费支出共同驱动", "对应工作簿1中的净手续费收入。"),
        ("KX_FEE_IN", "手续费收入", "开鑫贷", "中收收入", "detail", 40, "重点绑定平台费收入、拒量导流服务费等收入项", "对应工作簿1中的手续费收入。"),
        ("KX_FEE_OUT", "手续费支出", "开鑫贷", "中收支出", "detail", 50, "重点绑定渠道费、催收、征信、清结算等支出项", "对应工作簿1中的手续费支出。"),
        ("KX_RISK_COST", "风险成本", "开鑫贷", "风险成本", "detail", 60, "按不良率、代偿、拨备相关驱动项测算", "对应工作簿1中的风险成本。"),
        ("KX_TAX_SURCHARGE", "税金及附加", "开鑫贷", "费用类", "detail", 70, "可按年度总额模板均摊", "对应工作簿1中的税金及附加。"),
        ("KX_FIXED_MGMT", "固定管理费", "开鑫贷", "费用类", "detail", 80, "适合采用年度总额分摊模板", "对应工作簿1中的固定管理费。"),
        ("KX_SELF_AVG_BAL", "自持日均余额", "开鑫贷", "规模驱动", "detail", 90, "作为自持利息收入、风险成本、渠道费的重要规模底座", "对应工作簿1中的自持日均余额。"),
        ("KX_JOINT_AVG_BAL", "联贷日均余额", "开鑫贷", "规模驱动", "detail", 100, "作为联合贷平台费、催收等测算底座", "对应工作簿1中的联贷日均余额。"),
        ("KX_AVG_FIN_RATE_SELF", "平均财务利率-自持", "开鑫贷", "利率参数", "detail", 110, "结合平均财务利率、逾期占比、合同渠道费率等参数维护", "对应工作簿1中的平均财务利率-自持。"),
        ("KX_PLATFORM_FEE_IN", "平台费收入", "开鑫贷", "中收收入", "detail", 120, "主要对应联合贷款服务费收入", "对应工作簿1中的平台费收入。"),
        ("KX_PLATFORM_RATE", "平台费率", "开鑫贷", "利率参数", "detail", 130, "用于联合贷服务费收入测算", "对应工作簿1中的平台费率。"),
        ("KX_CHANNEL_FEE", "导流/渠道费", "开鑫贷", "中收支出", "detail", 140, "主要对应00渠道费与导流渠道费", "对应工作簿1中的渠道费相关行。"),
        ("KX_COLLECTION", "催收", "开鑫贷", "中收支出", "detail", 150, "主要对应催收费、催收费_联合贷款", "对应工作簿1中的催收。"),
        ("KX_CREDIT", "征信", "开鑫贷", "中收支出", "detail", 160, "主要对应征信费", "对应工作簿1中的征信。"),
        ("KX_CLEARING", "清结算", "开鑫贷", "中收支出", "detail", 170, "主要对应清算费", "对应工作簿1中的清结算。"),
        ("KX_TECH_SERVICE", "技术服务费支出", "开鑫贷", "中收支出", "detail", 180, "主要对应技术服务费", "对应工作簿1中的技术服务费支出。"),
        ("KX_INSURANCE", "保费支出", "开鑫贷", "风险成本", "detail", 190, "主要对应保险代偿相关支出", "对应工作簿1中的保费支出。"),
        ("KX_INSURANCE_NET", "保险代偿净额", "开鑫贷", "风险成本", "detail", 200, "用于跟踪保险代偿净赔付与风险抵减", "对应工作簿1中的保险代偿净额。"),
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
        ("KX_NET_INTEREST", "assumption_parameter", "CONTRACT_CHANNEL_FEE_RATIO", "", "ratio", 50, "合同渠道费率"),
        ("KX_NET_INTEREST", "assumption_parameter", "CHANNEL_FEE_EXEMPT_RATIO", "", "ratio", 60, "免收渠道费占比"),
        ("KX_SELF_AVG_BAL", "assumption_parameter", "KX_SELF_AVG_BALANCE", "", "scale", 10, "开鑫贷自持日均余额参数"),
        ("KX_JOINT_AVG_BAL", "assumption_parameter", "KX_JOINT_AVG_BALANCE", "", "scale", 10, "开鑫贷联贷日均余额参数"),
        ("KX_NET_FEE", "report_account", "A03", "", "report_anchor", 10, "净手续费收入锚点"),
        ("KX_FEE_IN", "data_account", "C4001", "", "income", 10, "合作贷款平台费"),
        ("KX_FEE_IN", "data_account", "C4005", "", "income", 20, "对公平台服务"),
        ("KX_FEE_IN", "data_account", "C4006", "", "income", 30, "代销业务手续费收入"),
        ("KX_FEE_IN", "data_account", "C4008", "", "income", 40, "其他手续费收入"),
        ("KX_PLATFORM_FEE_IN", "data_account", "C4001", "", "income", 10, "合作贷款平台费"),
        ("KX_PLATFORM_FEE_IN", "data_account", "C4005", "", "income", 20, "对公平台服务"),
        ("KX_PLATFORM_RATE", "assumption_parameter", "KX_PLATFORM_FEE_RATE", "", "rate", 10, "开鑫贷平台费率参数"),
        ("KX_FEE_OUT", "data_account", "C4101", "", "expense", 10, "渠道费"),
        ("KX_FEE_OUT", "data_account", "C4102", "", "expense", 20, "催收费"),
        ("KX_FEE_OUT", "data_account", "C4103", "", "expense", 30, "征信费"),
        ("KX_FEE_OUT", "data_account", "C4105", "", "expense", 40, "技术服务费"),
        ("KX_FEE_OUT", "data_account", "C4106", "", "expense", 50, "清算费"),
        ("KX_FEE_OUT", "data_account", "C4107", "", "expense", 60, "积分手续费"),
        ("KX_FEE_OUT", "data_account", "C4108", "", "expense", 70, "其他手续费支出"),
        ("KX_CHANNEL_FEE", "data_account", "C4101", "", "expense", 10, "渠道费"),
        ("KX_CHANNEL_FEE", "assumption_parameter", "CONTRACT_CHANNEL_FEE_RATIO", "", "ratio", 20, "合同渠道费率"),
        ("KX_CHANNEL_FEE", "assumption_parameter", "CHANNEL_FEE_EXEMPT_RATIO", "", "ratio", 30, "免收渠道费占比"),
        ("KX_COLLECTION", "data_account", "C4002", "", "expense", 10, "同业贷款催收费"),
        ("KX_COLLECTION", "data_account", "C4102", "", "expense", 20, "催收费"),
        ("KX_CREDIT", "data_account", "C4103", "", "expense", 10, "征信费"),
        ("KX_CLEARING", "data_account", "C4106", "", "expense", 10, "清算费"),
        ("KX_TECH_SERVICE", "data_account", "C4105", "", "expense", 10, "技术服务费"),
        ("KX_TAX_SURCHARGE", "assumption_rule_template", "EXPENSE_ANNUAL_AVG", "", "template", 10, "年度总额平均分月"),
        ("KX_TAX_SURCHARGE", "assumption_parameter", "EXPENSE_ANNUAL_TOTAL", "", "annual_total", 20, "税金及附加年度总额"),
        ("KX_FIXED_MGMT", "assumption_rule_template", "EXPENSE_ANNUAL_AVG", "", "template", 10, "年度总额平均分月"),
        ("KX_FIXED_MGMT", "assumption_parameter", "EXPENSE_ANNUAL_TOTAL", "", "annual_total", 20, "固定管理费年度总额"),
        ("KX_RISK_COST", "data_account", "C5200", "", "risk", 10, "风险成本_基础拨备"),
        ("KX_RISK_COST", "data_account", "C5201", "", "risk", 20, "风险成本_超额拨备"),
        ("KX_RISK_COST", "data_account", "C5203", "", "risk", 30, "其他风险成本"),
        ("KX_RISK_COST", "assumption_parameter", "KX_INSURANCE_NET_COMP", "", "risk_adjustment", 40, "保险代偿净额对风险成本的抵减影响"),
        ("KX_INSURANCE", "assumption_parameter", "KX_INSURANCE_PREMIUM", "", "expense", 10, "开鑫贷保费支出参数"),
        ("KX_INSURANCE_NET", "assumption_parameter", "KX_INSURANCE_NET_COMP", "", "expense", 10, "开鑫贷保险代偿净额参数"),
        ("XXA_REV_TOTAL", "report_account", "A01", "", "report_anchor", 10, "营业收入总览锚点"),
        ("XXA_NET_INTEREST", "assumption_rule_template", "LOAN_INTEREST_V1", "", "template", 10, "贷款利息收入模板"),
        ("XXA_NET_FEE", "report_account", "A03", "", "report_anchor", 10, "净手续费收入锚点"),
    ]
    if retired_line_codes:
        placeholders = ",".join(["?"] * len(retired_line_codes))
        conn.execute(
            f"DELETE FROM forecast_line_binding WHERE line_code IN ({placeholders})",
            retired_line_codes,
        )
        conn.execute(
            f"DELETE FROM forecast_workbench_layout WHERE line_code IN ({placeholders})",
            retired_line_codes,
        )
    for line_code, binding_type, binding_code in retired_anchor_bindings:
        conn.execute(
            """
            DELETE FROM forecast_line_binding
            WHERE line_code = ? AND binding_type = ? AND binding_code = ?
            """,
            (line_code, binding_type, binding_code),
        )
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
        [
            (line_code, line_name, line_group, line_category, display_mode, sort_order, binding_hint, remark, now, now)
            for line_code, line_name, line_group, line_category, display_mode, sort_order, binding_hint, remark in lines
        ],
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
        [
            (line_code, binding_type, binding_code, binding_name, binding_role, sort_order, remark, now, now)
            for line_code, binding_type, binding_code, binding_name, binding_role, sort_order, remark in bindings
        ],
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
