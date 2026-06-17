"""Current SQLite schema definitions for database bootstrap."""
from __future__ import annotations

from app.db_bootstrap.business_cost_income import BUSINESS_COST_INCOME_SCHEMA

COMMON_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS budget_output_display_item (
  row_key TEXT PRIMARY KEY NOT NULL,
  display_view TEXT NOT NULL,
  parent_row_key TEXT REFERENCES budget_output_display_item(row_key) ON DELETE SET NULL,
  data_acct_code TEXT,
  org_product_ref TEXT,
  org_product_entity_code TEXT,
  org_product_table_name TEXT,
  org_product_metric_code TEXT,
  org_product_metric_name TEXT,
  row_type TEXT NOT NULL CHECK (row_type IN ('GROUP', 'METRIC')),
  display_name TEXT NOT NULL,
  value_type TEXT,
  level INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_budget_output_display_item_order
ON budget_output_display_item(display_view, is_active, sort_order, row_key);

CREATE INDEX IF NOT EXISTS idx_budget_output_display_item_parent
ON budget_output_display_item(parent_row_key);

CREATE TABLE IF NOT EXISTS data_account_metric_node (
  node_code TEXT PRIMARY KEY NOT NULL,
  node_name TEXT NOT NULL,
  parent_code TEXT REFERENCES data_account_metric_node(node_code),
  product_code TEXT,
  local_metric_code TEXT,
  logic_code TEXT,
  functional_group_code TEXT,
  level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 8),
  node_type TEXT NOT NULL CHECK (node_type IN ('CATEGORY', 'GROUP', 'METRIC')),
  horizontal_rollup INTEGER NOT NULL DEFAULT 0 CHECK (horizontal_rollup IN (0, 1)),
  vertical_rollup INTEGER NOT NULL DEFAULT 0 CHECK (vertical_rollup IN (0, 1)),
  runtime_account_enabled INTEGER NOT NULL DEFAULT 0 CHECK (runtime_account_enabled IN (0, 1)),
  budget_formula TEXT,
  actual_formula TEXT,
  budget_rule_code TEXT,
  budget_rule_config_json TEXT,
  need_calc INTEGER NOT NULL DEFAULT 0 CHECK (need_calc IN (0, 1)),
  formula_calc_mode INTEGER NOT NULL DEFAULT 0 CHECK (formula_calc_mode BETWEEN 0 AND 3),
  allow_manual_entry INTEGER NOT NULL DEFAULT 1 CHECK (allow_manual_entry IN (0, 1)),
  value_type TEXT NOT NULL DEFAULT '金额',
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  remark TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE VIEW IF NOT EXISTS data_account AS
SELECT
  node_code AS data_acct_code,
  node_name AS data_acct_name,
  budget_formula,
  actual_formula,
  budget_rule_code,
  budget_rule_config_json,
  need_calc,
  formula_calc_mode,
  allow_manual_entry,
  value_type,
  remark
FROM data_account_metric_node
WHERE runtime_account_enabled = 1 AND is_active = 1;

CREATE VIEW IF NOT EXISTS data_account_metric_binding AS
SELECT
  d.data_acct_code AS data_acct_code,
  n.node_code AS metric_node_code,
  CASE
    WHEN COALESCE(n.product_code, '') = 'CORP' THEN 'CORP'
    ELSE 'PRODUCT'
  END AS scope_type,
  CASE
    WHEN COALESCE(n.product_code, '') <> '' THEN n.product_code
    WHEN INSTR(n.node_code, '.') > 0 THEN SUBSTR(n.node_code, 1, INSTR(n.node_code, '.') - 1)
    ELSE n.node_code
  END AS scope_code,
  n.sort_order AS sort_order,
  n.is_active AS is_active,
  n.remark AS remark,
  n.created_at AS created_at,
  n.updated_at AS updated_at
FROM data_account d
JOIN data_account_metric_node n ON n.node_code = d.data_acct_code
WHERE n.is_active = 1;

CREATE INDEX IF NOT EXISTS idx_data_account_metric_node_parent
ON data_account_metric_node(parent_code);

CREATE TABLE IF NOT EXISTS dept_account (
  dept_code TEXT PRIMARY KEY NOT NULL,
  dept_name TEXT NOT NULL,
  entity_name TEXT NOT NULL DEFAULT '微众银行',
  parent_code TEXT REFERENCES dept_account(dept_code),
  level INTEGER NOT NULL,
  is_leaf INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS period (
  period_id INTEGER PRIMARY KEY AUTOINCREMENT,
  year TEXT NOT NULL,
  month TEXT NOT NULL,
  quarter TEXT NOT NULL,
  year_month TEXT NOT NULL UNIQUE,
  days INTEGER NOT NULL
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

CREATE TABLE IF NOT EXISTS smart_report_blueprint (
  blueprint_id INTEGER PRIMARY KEY AUTOINCREMENT,
  blueprint_name TEXT NOT NULL,
  source_filename TEXT NOT NULL,
  inspection_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'confirmed', 'archived')),
  output_file_path TEXT,
  last_generated_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS smart_report_instance (
  instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE IF NOT EXISTS smart_ppt_scene (
  scene_id INTEGER PRIMARY KEY AUTOINCREMENT,
  scene_code TEXT NOT NULL UNIQUE,
  scene_name TEXT NOT NULL,
  scene_type TEXT NOT NULL DEFAULT 'board',
  description TEXT,
  slide_template_json TEXT,
  default_params_json TEXT,
  sort_order INTEGER DEFAULT 0,
  status TEXT DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS smart_ppt_chart_config (
  config_id INTEGER PRIMARY KEY AUTOINCREMENT,
  config_code TEXT NOT NULL UNIQUE,
  chart_type TEXT NOT NULL,
  metric_config_json TEXT NOT NULL,
  visual_config_json TEXT,
  remark TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS smart_ppt_instance (
  instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
  scene_id INTEGER NOT NULL REFERENCES smart_ppt_scene(scene_id),
  instance_name TEXT NOT NULL,
  parameter_values_json TEXT NOT NULL,
  output_file_path TEXT,
  generation_status TEXT NOT NULL DEFAULT 'pending' CHECK (generation_status IN ('pending', 'running', 'success', 'failed')),
  error_message TEXT,
  last_generated_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_smart_ppt_scene_sort
ON smart_ppt_scene(sort_order, scene_id);

CREATE INDEX IF NOT EXISTS idx_smart_ppt_instance_scene
ON smart_ppt_instance(scene_id, created_at DESC);

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

CREATE TABLE IF NOT EXISTS budget_subject_catalog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_id INTEGER REFERENCES budget_subject_catalog(id) ON DELETE RESTRICT,
  level_number INTEGER NOT NULL CHECK (level_number BETWEEN 1 AND 5),
  subject_name TEXT NOT NULL,
  manage_department TEXT,
  formula_text TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS manage_dept_owner_mapping (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  manage_department TEXT NOT NULL,
  owner_department TEXT NOT NULL,
  UNIQUE (manage_department)
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

CREATE TABLE IF NOT EXISTS expense_forecast_annual_entry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  forecast_year INTEGER NOT NULL,
  forecast_version TEXT NOT NULL,
  scope_type TEXT NOT NULL CHECK (scope_type IN ('entity', 'group', 'owner')),
  scope_value TEXT NOT NULL,
  subject_id INTEGER NOT NULL REFERENCES budget_subject_catalog(id) ON DELETE CASCADE,
  field_name TEXT NOT NULL CHECK (field_name IN ('business_submission', 'capital_advice')),
  field_value REAL NOT NULL DEFAULT 0,
  create_time TEXT NOT NULL,
  update_time TEXT NOT NULL,
  UNIQUE (forecast_year, forecast_version, scope_type, scope_value, subject_id, field_name)
);

CREATE INDEX IF NOT EXISTS idx_expense_forecast_annual_lookup
ON expense_forecast_annual_entry(forecast_year, forecast_version, scope_type, scope_value);

CREATE TABLE IF NOT EXISTS expense_forecast_rule (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  forecast_year INTEGER NOT NULL,
  forecast_version TEXT NOT NULL,
  owner_name TEXT NOT NULL,
  subject_id INTEGER NOT NULL REFERENCES budget_subject_catalog(id) ON DELETE CASCADE,
  scheme_code TEXT NOT NULL CHECK (scheme_code IN ('MANUAL', 'RESIDUAL_ALLOC', 'METRIC_EXPR')),
  enabled INTEGER NOT NULL DEFAULT 1,
  allow_manual_override INTEGER NOT NULL DEFAULT 0,
  auto_refresh_enabled INTEGER NOT NULL DEFAULT 1,
  manual_recalc_enabled INTEGER NOT NULL DEFAULT 1,
  metric_source_priority TEXT NOT NULL DEFAULT 'metric_first'
    CHECK (metric_source_priority IN ('metric_first', 'inline_first')),
  effective_from_month INTEGER NOT NULL DEFAULT 1 CHECK (effective_from_month BETWEEN 1 AND 12),
  effective_to_month INTEGER NOT NULL DEFAULT 12 CHECK (effective_to_month BETWEEN 1 AND 12),
  priority INTEGER NOT NULL DEFAULT 100,
  remark TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (forecast_year, forecast_version, owner_name, subject_id)
);

CREATE INDEX IF NOT EXISTS idx_expense_forecast_rule_lookup
ON expense_forecast_rule(forecast_year, forecast_version, owner_name, subject_id);

CREATE TABLE IF NOT EXISTS expense_forecast_rule_param (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id INTEGER NOT NULL REFERENCES expense_forecast_rule(id) ON DELETE CASCADE,
  param_group TEXT NOT NULL DEFAULT 'common',
  param_key TEXT NOT NULL,
  param_value TEXT,
  value_type TEXT NOT NULL DEFAULT 'string',
  UNIQUE (rule_id, param_group, param_key)
);

CREATE TABLE IF NOT EXISTS expense_forecast_rule_variable (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id INTEGER NOT NULL REFERENCES expense_forecast_rule(id) ON DELETE CASCADE,
  variable_code TEXT NOT NULL,
  variable_name TEXT,
  source_type TEXT NOT NULL CHECK (
    source_type IN ('metric_tree', 'forecast_inline', 'actual', 'annual_field', 'constant')
  ),
  source_key TEXT,
  source_subkey TEXT,
  default_value REAL,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_expense_forecast_rule_variable_rule
ON expense_forecast_rule_variable(rule_id, sort_order, id);

CREATE TABLE IF NOT EXISTS expense_forecast_calc_result (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  forecast_year INTEGER NOT NULL,
  forecast_version TEXT NOT NULL,
  owner_name TEXT NOT NULL,
  subject_id INTEGER NOT NULL REFERENCES budget_subject_catalog(id) ON DELETE CASCADE,
  month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
  rule_id INTEGER REFERENCES expense_forecast_rule(id) ON DELETE SET NULL,
  calc_value REAL NOT NULL DEFAULT 0,
  calc_basis_json TEXT,
  calc_status TEXT NOT NULL DEFAULT 'ok',
  calc_time TEXT NOT NULL,
  UNIQUE (forecast_year, forecast_version, owner_name, subject_id, month)
);

CREATE INDEX IF NOT EXISTS idx_expense_forecast_calc_lookup
ON expense_forecast_calc_result(forecast_year, forecast_version, owner_name, subject_id);

CREATE TABLE IF NOT EXISTS expense_forecast_override (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  forecast_year INTEGER NOT NULL,
  forecast_version TEXT NOT NULL,
  owner_name TEXT NOT NULL,
  subject_id INTEGER NOT NULL REFERENCES budget_subject_catalog(id) ON DELETE CASCADE,
  month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
  rule_id INTEGER REFERENCES expense_forecast_rule(id) ON DELETE SET NULL,
  system_value REAL NOT NULL DEFAULT 0,
  override_value REAL NOT NULL DEFAULT 0,
  override_reason TEXT,
  operator_name TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (forecast_year, forecast_version, owner_name, subject_id, month)
);

CREATE INDEX IF NOT EXISTS idx_expense_forecast_override_lookup
ON expense_forecast_override(forecast_year, forecast_version, owner_name, subject_id);

CREATE TABLE IF NOT EXISTS expense_actual_import_batch (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_kind TEXT NOT NULL DEFAULT 'current_year_actual',
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
  import_kind TEXT NOT NULL DEFAULT 'current_year_actual',
  data_date TEXT,
  period_ym TEXT NOT NULL,
  period_text TEXT,
  org_code TEXT,
  org_name TEXT,
  dep_code TEXT,
  dep_name TEXT,
  subject_code TEXT,
  subject_name TEXT,
  journal_name TEXT,
  serial_no TEXT,
  line_desc TEXT,
  amount REAL NOT NULL DEFAULT 0,
  fee_type_code TEXT,
  fee_type_name TEXT,
  bi_ai_source_code TEXT,
  bi_ai_source_name TEXT,
  manage_department_code TEXT,
  owner_name_raw TEXT,
  owner_name_mapped TEXT,
  monthly_caliber TEXT,
  budget_subject_raw TEXT,
  budget_subject_mapped TEXT,
  fee_major_mapped TEXT,
  fee_category_mapped TEXT,
  budget_release_caliber_mapped TEXT,
  manage_department2 TEXT,
  special_control_tag TEXT,
  owner_matched INTEGER NOT NULL DEFAULT 0 CHECK (owner_matched IN (0, 1)),
  subject_matched INTEGER NOT NULL DEFAULT 0 CHECK (subject_matched IN (0, 1)),
  match_note TEXT
);

"""

BUDGET_SCHEMA = f"""
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
  formula_value REAL,
  manual_value REAL,
  value_source TEXT NOT NULL DEFAULT 'manual' CHECK (value_source IN ('manual', 'formula', 'none', 'rollup')),
  need_calc INTEGER NOT NULL DEFAULT 1,
  create_time TEXT,
  update_time TEXT,
  UNIQUE (data_acct_code, product_code, period_id, version_id, budget_actual)
);

CREATE TABLE IF NOT EXISTS budget_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  metric_level1 TEXT,
  metric_level2 TEXT,
  metric_level3 TEXT,
  metric_level4 TEXT,
  metric_level5 TEXT,
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
  value_source TEXT NOT NULL DEFAULT 'manual',
  update_time TEXT
);

CREATE TABLE IF NOT EXISTS budget_pivot_aggregate (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  grain TEXT NOT NULL CHECK (grain IN ('year', 'quarter', 'month')),
  metric_level1 TEXT,
  metric_level2 TEXT,
  metric_level3 TEXT,
  metric_level4 TEXT,
  metric_level5 TEXT,
  dept_level1 TEXT,
  dept_level2 TEXT,
  dept_level3 TEXT,
  data_code_name TEXT NOT NULL,
  product_code_name TEXT,
  year TEXT NOT NULL,
  month TEXT NOT NULL,
  quarter TEXT NOT NULL,
  budget_actual INTEGER NOT NULL CHECK (budget_actual IN (0, 1)),
  version_id INTEGER NOT NULL,
  version_name TEXT,
  value REAL NOT NULL DEFAULT 0,
  value_type TEXT NOT NULL,
  value_source TEXT NOT NULL DEFAULT 'manual',
  update_time TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_budget_pivot_aggregate_grain
ON budget_pivot_aggregate(grain);

CREATE INDEX IF NOT EXISTS idx_budget_pivot_aggregate_version
ON budget_pivot_aggregate(version_id, grain);

{BUSINESS_COST_INCOME_SCHEMA}

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
AFTER UPDATE OF data_acct_code, product_code, period_id, budget_actual, version_id, value, formula_value, manual_value, value_source, need_calc, create_time
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
  metric_level1 TEXT,
  metric_level2 TEXT,
  metric_level3 TEXT,
  metric_level4 TEXT,
  metric_level5 TEXT,
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
  value_source TEXT NOT NULL DEFAULT 'manual',
  sync_time TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_compare_budget_summary_show_level
ON compare_budget_summary(show_level);

CREATE INDEX IF NOT EXISTS idx_compare_budget_summary_source
ON compare_budget_summary(source_year, source_version_id);

CREATE TABLE IF NOT EXISTS compare_pivot_aggregate (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  grain TEXT NOT NULL CHECK (grain IN ('year', 'quarter', 'month')),
  show_level INTEGER NOT NULL CHECK (show_level BETWEEN 1 AND 5),
  data_file_id INTEGER NOT NULL,
  source_year INTEGER NOT NULL,
  source_version_id INTEGER NOT NULL,
  source_version_name TEXT,
  metric_level1 TEXT,
  metric_level2 TEXT,
  metric_level3 TEXT,
  metric_level4 TEXT,
  metric_level5 TEXT,
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
  value_source TEXT NOT NULL DEFAULT 'manual',
  sync_time TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_compare_pivot_aggregate_grain
ON compare_pivot_aggregate(grain);

CREATE INDEX IF NOT EXISTS idx_compare_pivot_aggregate_level
ON compare_pivot_aggregate(show_level, grain);

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
