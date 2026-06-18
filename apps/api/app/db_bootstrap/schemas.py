"""MySQL schema definitions for database bootstrap."""
from __future__ import annotations

from app.db_bootstrap.business_cost_income import BUSINESS_COST_INCOME_SCHEMA

COMMON_SCHEMA = """
CREATE TABLE IF NOT EXISTS budget_output_display_item (
  row_key VARCHAR(255) PRIMARY KEY NOT NULL,
  display_view VARCHAR(255) NOT NULL,
  parent_row_key VARCHAR(255),
  data_acct_code VARCHAR(255),
  org_product_ref VARCHAR(255),
  org_product_entity_code VARCHAR(255),
  org_product_table_name VARCHAR(255),
  org_product_metric_code VARCHAR(255),
  org_product_metric_name VARCHAR(255),
  row_type VARCHAR(32) NOT NULL CHECK (row_type IN ('GROUP', 'METRIC')),
  display_name VARCHAR(255) NOT NULL,
  value_type VARCHAR(64),
  level INT NOT NULL DEFAULT 1,
  sort_order INT NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at VARCHAR(64) NOT NULL DEFAULT '',
  updated_at VARCHAR(64) NOT NULL DEFAULT '',
  FOREIGN KEY (parent_row_key) REFERENCES budget_output_display_item(row_key) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_budget_output_display_item_order
ON budget_output_display_item(display_view, is_active, sort_order, row_key);

CREATE INDEX idx_budget_output_display_item_parent
ON budget_output_display_item(parent_row_key);

CREATE TABLE IF NOT EXISTS data_account_metric_node (
  node_code VARCHAR(255) PRIMARY KEY NOT NULL,
  node_name VARCHAR(255) NOT NULL,
  parent_code VARCHAR(255),
  product_code VARCHAR(64),
  local_metric_code VARCHAR(64),
  logic_code VARCHAR(255),
  functional_group_code VARCHAR(64),
  metric_table_name VARCHAR(255) NOT NULL DEFAULT '',
  level INT NOT NULL CHECK (level BETWEEN 1 AND 8),
  node_type VARCHAR(32) NOT NULL CHECK (node_type IN ('CATEGORY', 'GROUP', 'METRIC')),
  horizontal_rollup TINYINT(1) NOT NULL DEFAULT 0 CHECK (horizontal_rollup IN (0, 1)),
  vertical_rollup TINYINT(1) NOT NULL DEFAULT 0 CHECK (vertical_rollup IN (0, 1)),
  runtime_account_enabled TINYINT(1) NOT NULL DEFAULT 0 CHECK (runtime_account_enabled IN (0, 1)),
  budget_formula TEXT,
  actual_formula TEXT,
  budget_rule_code VARCHAR(64),
  budget_rule_config_json JSON,
  need_calc TINYINT(1) NOT NULL DEFAULT 0 CHECK (need_calc IN (0, 1)),
  formula_calc_mode TINYINT(1) NOT NULL DEFAULT 0 CHECK (formula_calc_mode BETWEEN 0 AND 3),
  allow_manual_entry TINYINT(1) NOT NULL DEFAULT 1 CHECK (allow_manual_entry IN (0, 1)),
  value_type VARCHAR(32) NOT NULL DEFAULT '金额',
  sort_order INT NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  remark TEXT,
  created_at VARCHAR(64) NOT NULL DEFAULT '',
  updated_at VARCHAR(64) NOT NULL DEFAULT '',
  annual_agg_rule VARCHAR(255) NOT NULL DEFAULT '',
  FOREIGN KEY (parent_code) REFERENCES data_account_metric_node(node_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE OR REPLACE VIEW data_account AS
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

CREATE OR REPLACE VIEW data_account_metric_binding AS
SELECT
  d.data_acct_code AS data_acct_code,
  n.node_code AS metric_node_code,
  CASE
    WHEN COALESCE(n.product_code, '') = 'CORP' THEN 'CORP'
    ELSE 'PRODUCT'
  END AS scope_type,
  CASE
    WHEN COALESCE(n.product_code, '') <> '' THEN n.product_code
    WHEN LOCATE('.', n.node_code) > 0 THEN SUBSTR(n.node_code, 1, LOCATE('.', n.node_code) - 1)
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

CREATE INDEX idx_data_account_metric_node_parent
ON data_account_metric_node(parent_code);

CREATE TABLE IF NOT EXISTS dept_account (
  dept_code VARCHAR(255) PRIMARY KEY NOT NULL,
  dept_name VARCHAR(255) NOT NULL,
  entity_name VARCHAR(255) NOT NULL DEFAULT '微众银行',
  parent_code VARCHAR(255),
  level INT NOT NULL,
  is_leaf TINYINT(1) NOT NULL DEFAULT 0,
  FOREIGN KEY (parent_code) REFERENCES dept_account(dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS period (
  period_id INT AUTO_INCREMENT PRIMARY KEY,
  `year` VARCHAR(8) NOT NULL,
  month VARCHAR(8) NOT NULL,
  quarter VARCHAR(8) NOT NULL,
  `year_month` VARCHAR(16) NOT NULL UNIQUE,
  days INT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS smart_report_template (
  template_id INT AUTO_INCREMENT PRIMARY KEY,
  template_code VARCHAR(64) NOT NULL UNIQUE,
  template_name VARCHAR(255) NOT NULL,
  template_type VARCHAR(32) NOT NULL DEFAULT 'analysis' CHECK (template_type IN ('analysis', 'report', 'summary', 'ppt')),
  file_path VARCHAR(512) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
  version_no INT NOT NULL DEFAULT 1,
  remark TEXT,
  created_by VARCHAR(64),
  created_at VARCHAR(64) NOT NULL,
  updated_at VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS smart_report_template_variable (
  variable_id INT AUTO_INCREMENT PRIMARY KEY,
  template_id INT NOT NULL,
  variable_key VARCHAR(255) NOT NULL,
  variable_name VARCHAR(255) NOT NULL,
  variable_type VARCHAR(32) NOT NULL CHECK (variable_type IN ('metric', 'formula', 'calc', 'parameter', 'text', 'table', 'chart', 'analysis')),
  binding_config_json JSON,
  display_order INT NOT NULL DEFAULT 0,
  created_at VARCHAR(64) NOT NULL,
  updated_at VARCHAR(64) NOT NULL,
  UNIQUE (template_id, variable_key),
  FOREIGN KEY (template_id) REFERENCES smart_report_template(template_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS smart_report_calc_metric (
  metric_code VARCHAR(255) PRIMARY KEY NOT NULL,
  metric_name VARCHAR(255) NOT NULL,
  expression TEXT NOT NULL,
  components_json JSON NOT NULL,
  value_type VARCHAR(32) NOT NULL DEFAULT '金额',
  format_type VARCHAR(32) NOT NULL DEFAULT 'number',
  remark TEXT,
  created_at VARCHAR(64) NOT NULL,
  updated_at VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS smart_report_blueprint (
  blueprint_id INT AUTO_INCREMENT PRIMARY KEY,
  blueprint_name VARCHAR(255) NOT NULL,
  source_filename VARCHAR(512) NOT NULL,
  inspection_json JSON NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'confirmed', 'archived')),
  output_file_path VARCHAR(512),
  last_generated_at VARCHAR(64),
  created_at VARCHAR(64) NOT NULL,
  updated_at VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS smart_report_instance (
  instance_id INT AUTO_INCREMENT PRIMARY KEY,
  template_id INT NOT NULL,
  instance_name VARCHAR(255) NOT NULL,
  parameter_values_json JSON NOT NULL,
  text_values_json JSON,
  data_snapshot_json JSON,
  output_file_path VARCHAR(512),
  generation_status VARCHAR(32) NOT NULL DEFAULT 'pending' CHECK (generation_status IN ('pending', 'running', 'success', 'failed')),
  error_message TEXT,
  last_generated_at VARCHAR(64),
  last_refresh_at VARCHAR(64),
  created_at VARCHAR(64) NOT NULL,
  updated_at VARCHAR(64) NOT NULL,
  FOREIGN KEY (template_id) REFERENCES smart_report_template(template_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS smart_report_job (
  job_id INT AUTO_INCREMENT PRIMARY KEY,
  instance_id INT,
  job_type VARCHAR(32) NOT NULL CHECK (job_type IN ('generate', 'refresh')),
  job_status VARCHAR(32) NOT NULL CHECK (job_status IN ('pending', 'running', 'success', 'failed')),
  started_at VARCHAR(64),
  finished_at VARCHAR(64),
  error_message TEXT,
  FOREIGN KEY (instance_id) REFERENCES smart_report_instance(instance_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_smart_report_variable_template
ON smart_report_template_variable(template_id);

CREATE INDEX idx_smart_report_instance_template
ON smart_report_instance(template_id);

CREATE TABLE IF NOT EXISTS smart_ppt_scene (
  scene_id INT AUTO_INCREMENT PRIMARY KEY,
  scene_code VARCHAR(64) NOT NULL UNIQUE,
  scene_name VARCHAR(255) NOT NULL,
  scene_type VARCHAR(32) NOT NULL DEFAULT 'board',
  description TEXT,
  slide_template_json JSON,
  default_params_json JSON,
  sort_order INT DEFAULT 0,
  status VARCHAR(32) DEFAULT 'active',
  created_at VARCHAR(64) NOT NULL,
  updated_at VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS smart_ppt_chart_config (
  config_id INT AUTO_INCREMENT PRIMARY KEY,
  config_code VARCHAR(64) NOT NULL UNIQUE,
  chart_type VARCHAR(64) NOT NULL,
  metric_config_json JSON NOT NULL,
  visual_config_json JSON,
  remark TEXT,
  created_at VARCHAR(64) NOT NULL,
  updated_at VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS smart_ppt_instance (
  instance_id INT AUTO_INCREMENT PRIMARY KEY,
  scene_id INT NOT NULL,
  instance_name VARCHAR(255) NOT NULL,
  parameter_values_json JSON NOT NULL,
  output_file_path VARCHAR(512),
  generation_status VARCHAR(32) NOT NULL DEFAULT 'pending' CHECK (generation_status IN ('pending', 'running', 'success', 'failed')),
  error_message TEXT,
  last_generated_at VARCHAR(64),
  created_at VARCHAR(64) NOT NULL,
  updated_at VARCHAR(64) NOT NULL,
  FOREIGN KEY (scene_id) REFERENCES smart_ppt_scene(scene_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_smart_ppt_scene_sort
ON smart_ppt_scene(sort_order, scene_id);

CREATE INDEX idx_smart_ppt_instance_scene
ON smart_ppt_instance(scene_id, created_at DESC);

CREATE TABLE IF NOT EXISTS operation_log (
  log_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64),
  action_type VARCHAR(64) NOT NULL,
  action_desc TEXT NOT NULL,
  target_table VARCHAR(255),
  affected_rows INT,
  before_data TEXT,
  after_data TEXT,
  ip_address VARCHAR(64),
  create_time VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_name VARCHAR(255) NOT NULL UNIQUE,
  first_login_password VARCHAR(255) NOT NULL,
  daily_login_password VARCHAR(255),
  permission_type INT NOT NULL CHECK (permission_type IN (1, 2, 3)),
  first_login_flag TINYINT(1) NOT NULL DEFAULT 1 CHECK (first_login_flag IN (0, 1)),
  create_time VARCHAR(64) NOT NULL,
  update_time VARCHAR(64)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `databases` (
  id INT AUTO_INCREMENT PRIMARY KEY,
  data_file_name VARCHAR(255) NOT NULL UNIQUE,
  `year` INT NOT NULL,
  create_time VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS edit_show_version (
  id INT AUTO_INCREMENT PRIMARY KEY,
  data_file_id INT NOT NULL,
  version_id INT NOT NULL,
  edit_show_sign INT NOT NULL CHECK (edit_show_sign BETWEEN 0 AND 5),
  FOREIGN KEY (data_file_id) REFERENCES `databases`(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_sessions (
  session_id VARCHAR(255) PRIMARY KEY,
  user_id INT NOT NULL,
  must_change_password TINYINT(1) NOT NULL DEFAULT 0 CHECK (must_change_password IN (0, 1)),
  create_time VARCHAR(64) NOT NULL,
  expire_time VARCHAR(64) NOT NULL,
  last_seen_time VARCHAR(64) NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS feishu_user_binding (
  open_id VARCHAR(255) PRIMARY KEY,
  user_id INT NOT NULL,
  create_time VARCHAR(64) NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_feishu_user_binding_user_id ON feishu_user_binding(user_id);

CREATE TABLE IF NOT EXISTS expense_sync_meta (
  sync_key VARCHAR(255) PRIMARY KEY NOT NULL,
  source_file VARCHAR(512) NOT NULL,
  source_mtime VARCHAR(64),
  synced_at VARCHAR(64) NOT NULL,
  row_count INT NOT NULL DEFAULT 0,
  note TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS expense_framework_budget_department (
  id INT AUTO_INCREMENT PRIMARY KEY,
  entity_name VARCHAR(255) NOT NULL DEFAULT '',
  group_name VARCHAR(255) NOT NULL,
  owner_name VARCHAR(255) NOT NULL,
  budget_department VARCHAR(255) NOT NULL,
  UNIQUE (group_name, owner_name, budget_department)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS expense_framework_product_department (
  id INT AUTO_INCREMENT PRIMARY KEY,
  entity_name VARCHAR(255) NOT NULL DEFAULT '',
  group_name VARCHAR(255) NOT NULL,
  owner_name VARCHAR(255) NOT NULL,
  product_department VARCHAR(255) NOT NULL,
  UNIQUE (group_name, owner_name, product_department)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS expense_framework_subject (
  budget_subject VARCHAR(255) PRIMARY KEY NOT NULL,
  level_label VARCHAR(64),
  manage_department VARCHAR(255),
  formula_text TEXT,
  sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS budget_subject_catalog (
  id INT AUTO_INCREMENT PRIMARY KEY,
  parent_id INT,
  level_number INT NOT NULL CHECK (level_number BETWEEN 1 AND 5),
  subject_name VARCHAR(255) NOT NULL,
  manage_department VARCHAR(255),
  formula_text TEXT,
  sort_order INT NOT NULL DEFAULT 0,
  FOREIGN KEY (parent_id) REFERENCES budget_subject_catalog(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS manage_dept_owner_mapping (
  id INT AUTO_INCREMENT PRIMARY KEY,
  manage_department VARCHAR(255) NOT NULL,
  owner_department VARCHAR(255) NOT NULL,
  UNIQUE (manage_department)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS expense_forecast_entry (
  id INT AUTO_INCREMENT PRIMARY KEY,
  forecast_year INT NOT NULL,
  forecast_version VARCHAR(64) NOT NULL,
  scope_type VARCHAR(32) NOT NULL CHECK (scope_type IN ('entity', 'group', 'owner')),
  scope_value VARCHAR(255) NOT NULL,
  subject_id INT NOT NULL,
  month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
  forecast_value DOUBLE NOT NULL DEFAULT 0,
  create_time VARCHAR(64) NOT NULL,
  update_time VARCHAR(64) NOT NULL,
  UNIQUE (forecast_year, forecast_version, scope_type, scope_value, subject_id, month),
  FOREIGN KEY (subject_id) REFERENCES budget_subject_catalog(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_expense_forecast_lookup
ON expense_forecast_entry(forecast_year, forecast_version, scope_type, scope_value);

CREATE TABLE IF NOT EXISTS expense_forecast_annual_entry (
  id INT AUTO_INCREMENT PRIMARY KEY,
  forecast_year INT NOT NULL,
  forecast_version VARCHAR(64) NOT NULL,
  scope_type VARCHAR(32) NOT NULL CHECK (scope_type IN ('entity', 'group', 'owner')),
  scope_value VARCHAR(255) NOT NULL,
  subject_id INT NOT NULL,
  field_name VARCHAR(64) NOT NULL CHECK (field_name IN ('business_submission', 'capital_advice')),
  field_value DOUBLE NOT NULL DEFAULT 0,
  create_time VARCHAR(64) NOT NULL,
  update_time VARCHAR(64) NOT NULL,
  UNIQUE (forecast_year, forecast_version, scope_type, scope_value, subject_id, field_name),
  FOREIGN KEY (subject_id) REFERENCES budget_subject_catalog(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_expense_forecast_annual_lookup
ON expense_forecast_annual_entry(forecast_year, forecast_version, scope_type, scope_value);

CREATE TABLE IF NOT EXISTS expense_forecast_rule (
  id INT AUTO_INCREMENT PRIMARY KEY,
  forecast_year INT NOT NULL,
  forecast_version VARCHAR(64) NOT NULL,
  owner_name VARCHAR(255) NOT NULL,
  subject_id INT NOT NULL,
  scheme_code VARCHAR(32) NOT NULL CHECK (scheme_code IN ('MANUAL', 'RESIDUAL_ALLOC', 'METRIC_EXPR')),
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  allow_manual_override TINYINT(1) NOT NULL DEFAULT 0,
  auto_refresh_enabled TINYINT(1) NOT NULL DEFAULT 1,
  manual_recalc_enabled TINYINT(1) NOT NULL DEFAULT 1,
  metric_source_priority VARCHAR(32) NOT NULL DEFAULT 'metric_first'
    CHECK (metric_source_priority IN ('metric_first', 'inline_first')),
  effective_from_month INT NOT NULL DEFAULT 1 CHECK (effective_from_month BETWEEN 1 AND 12),
  effective_to_month INT NOT NULL DEFAULT 12 CHECK (effective_to_month BETWEEN 1 AND 12),
  priority INT NOT NULL DEFAULT 100,
  remark TEXT,
  created_at VARCHAR(64) NOT NULL,
  updated_at VARCHAR(64) NOT NULL,
  UNIQUE (forecast_year, forecast_version, owner_name, subject_id),
  FOREIGN KEY (subject_id) REFERENCES budget_subject_catalog(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_expense_forecast_rule_lookup
ON expense_forecast_rule(forecast_year, forecast_version, owner_name, subject_id);

CREATE TABLE IF NOT EXISTS expense_forecast_rule_param (
  id INT AUTO_INCREMENT PRIMARY KEY,
  rule_id INT NOT NULL,
  param_group VARCHAR(64) NOT NULL DEFAULT 'common',
  param_key VARCHAR(255) NOT NULL,
  param_value TEXT,
  value_type VARCHAR(32) NOT NULL DEFAULT 'string',
  UNIQUE (rule_id, param_group, param_key),
  FOREIGN KEY (rule_id) REFERENCES expense_forecast_rule(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS expense_forecast_rule_variable (
  id INT AUTO_INCREMENT PRIMARY KEY,
  rule_id INT NOT NULL,
  variable_code VARCHAR(255) NOT NULL,
  variable_name VARCHAR(255),
  source_type VARCHAR(32) NOT NULL CHECK (
    source_type IN ('metric_tree', 'forecast_inline', 'actual', 'annual_field', 'constant')
  ),
  source_key VARCHAR(255),
  source_subkey VARCHAR(255),
  default_value DOUBLE,
  sort_order INT NOT NULL DEFAULT 0,
  FOREIGN KEY (rule_id) REFERENCES expense_forecast_rule(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_expense_forecast_rule_variable_rule
ON expense_forecast_rule_variable(rule_id, sort_order, id);

CREATE TABLE IF NOT EXISTS expense_forecast_calc_result (
  id INT AUTO_INCREMENT PRIMARY KEY,
  forecast_year INT NOT NULL,
  forecast_version VARCHAR(64) NOT NULL,
  owner_name VARCHAR(255) NOT NULL,
  subject_id INT NOT NULL,
  month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
  rule_id INT,
  calc_value DOUBLE NOT NULL DEFAULT 0,
  calc_basis_json JSON,
  calc_status VARCHAR(32) NOT NULL DEFAULT 'ok',
  calc_time VARCHAR(64) NOT NULL,
  UNIQUE (forecast_year, forecast_version, owner_name, subject_id, month),
  FOREIGN KEY (subject_id) REFERENCES budget_subject_catalog(id) ON DELETE CASCADE,
  FOREIGN KEY (rule_id) REFERENCES expense_forecast_rule(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_expense_forecast_calc_lookup
ON expense_forecast_calc_result(forecast_year, forecast_version, owner_name, subject_id);

CREATE TABLE IF NOT EXISTS expense_forecast_override (
  id INT AUTO_INCREMENT PRIMARY KEY,
  forecast_year INT NOT NULL,
  forecast_version VARCHAR(64) NOT NULL,
  owner_name VARCHAR(255) NOT NULL,
  subject_id INT NOT NULL,
  month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
  rule_id INT,
  system_value DOUBLE NOT NULL DEFAULT 0,
  override_value DOUBLE NOT NULL DEFAULT 0,
  override_reason TEXT,
  operator_name VARCHAR(64),
  created_at VARCHAR(64) NOT NULL,
  updated_at VARCHAR(64) NOT NULL,
  UNIQUE (forecast_year, forecast_version, owner_name, subject_id, month),
  FOREIGN KEY (subject_id) REFERENCES budget_subject_catalog(id) ON DELETE CASCADE,
  FOREIGN KEY (rule_id) REFERENCES expense_forecast_rule(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_expense_forecast_override_lookup
ON expense_forecast_override(forecast_year, forecast_version, owner_name, subject_id);

CREATE TABLE IF NOT EXISTS expense_actual_import_batch (
  id INT AUTO_INCREMENT PRIMARY KEY,
  import_kind VARCHAR(64) NOT NULL DEFAULT 'current_year_actual',
  file_name VARCHAR(512) NOT NULL,
  import_mode VARCHAR(32) NOT NULL,
  periods_text TEXT,
  total_rows INT NOT NULL DEFAULT 0,
  matched_owner_rows INT NOT NULL DEFAULT 0,
  matched_subject_rows INT NOT NULL DEFAULT 0,
  unmatched_rows INT NOT NULL DEFAULT 0,
  created_at VARCHAR(64) NOT NULL,
  note TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS expense_actual_detail_raw (
  id INT AUTO_INCREMENT PRIMARY KEY,
  batch_id INT,
  import_kind VARCHAR(64) NOT NULL DEFAULT 'current_year_actual',
  data_date VARCHAR(64),
  period_ym VARCHAR(16) NOT NULL,
  period_text VARCHAR(64),
  org_code VARCHAR(64),
  org_name VARCHAR(255),
  dep_code VARCHAR(64),
  dep_name VARCHAR(255),
  subject_code VARCHAR(64),
  subject_name VARCHAR(255),
  journal_name VARCHAR(255),
  serial_no VARCHAR(64),
  line_desc TEXT,
  amount DOUBLE NOT NULL DEFAULT 0,
  fee_type_code VARCHAR(64),
  fee_type_name VARCHAR(255),
  bi_ai_source_code VARCHAR(64),
  bi_ai_source_name VARCHAR(255),
  manage_department_code VARCHAR(64),
  owner_name_raw VARCHAR(255),
  owner_name_mapped VARCHAR(255),
  monthly_caliber VARCHAR(64),
  budget_subject_raw VARCHAR(255),
  budget_subject_mapped VARCHAR(255),
  fee_major_mapped VARCHAR(255),
  fee_category_mapped VARCHAR(255),
  budget_release_caliber_mapped VARCHAR(255),
  manage_department2 VARCHAR(255),
  special_control_tag VARCHAR(64),
  owner_matched TINYINT(1) NOT NULL DEFAULT 0 CHECK (owner_matched IN (0, 1)),
  subject_matched TINYINT(1) NOT NULL DEFAULT 0 CHECK (subject_matched IN (0, 1)),
  match_note TEXT,
  FOREIGN KEY (batch_id) REFERENCES expense_actual_import_batch(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

"""

BUDGET_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS version (
  version_id INT AUTO_INCREMENT PRIMARY KEY,
  budget_year INT NOT NULL,
  version_date_time VARCHAR(64) NOT NULL,
  version_name VARCHAR(255) NOT NULL,
  current_month INT NOT NULL DEFAULT 1 CHECK (current_month BETWEEN 1 AND 13)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_version_year ON version(budget_year);

CREATE TABLE IF NOT EXISTS settings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  budget_year INT NOT NULL,
  setting_key VARCHAR(255) NOT NULL,
  setting_value TEXT NOT NULL,
  UNIQUE (budget_year, setting_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_settings_year ON settings(budget_year);

CREATE TABLE IF NOT EXISTS budget_data (
  id INT AUTO_INCREMENT PRIMARY KEY,
  budget_year INT NOT NULL,
  data_acct_code VARCHAR(255) NOT NULL,
  product_code VARCHAR(64) NOT NULL,
  period_id INT NOT NULL,
  budget_actual TINYINT(1) NOT NULL CHECK (budget_actual IN (0, 1)),
  version_id INT NOT NULL,
  value DOUBLE NOT NULL DEFAULT 0,
  formula_value DOUBLE,
  manual_value DOUBLE,
  value_source VARCHAR(32) NOT NULL DEFAULT 'manual' CHECK (value_source IN ('manual', 'formula', 'none', 'rollup')),
  need_calc TINYINT(1) NOT NULL DEFAULT 1,
  create_time VARCHAR(64),
  update_time VARCHAR(64),
  UNIQUE (budget_year, data_acct_code, product_code, period_id, version_id, budget_actual),
  FOREIGN KEY (version_id) REFERENCES version(version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_budget_data_year ON budget_data(budget_year);
CREATE INDEX idx_budget_data_lookup ON budget_data(budget_year, data_acct_code, product_code, version_id);

CREATE TABLE IF NOT EXISTS budget_summary (
  id INT AUTO_INCREMENT PRIMARY KEY,
  budget_year INT NOT NULL,
  metric_level1 VARCHAR(255),
  metric_level2 VARCHAR(255),
  metric_level3 VARCHAR(255),
  metric_level4 VARCHAR(255),
  metric_level5 VARCHAR(255),
  dept_level1 VARCHAR(255),
  dept_level2 VARCHAR(255),
  dept_level3 VARCHAR(255),
  data_code_name VARCHAR(255) NOT NULL,
  product_code_name VARCHAR(255),
  `year` VARCHAR(8) NOT NULL,
  month VARCHAR(8) NOT NULL,
  quarter VARCHAR(8) NOT NULL,
  budget_actual TINYINT(1) NOT NULL,
  version_id INT NOT NULL,
  version_name VARCHAR(255),
  value DOUBLE NOT NULL DEFAULT 0,
  value_type VARCHAR(32) NOT NULL,
  value_source VARCHAR(32) NOT NULL DEFAULT 'manual',
  update_time VARCHAR(64),
  FOREIGN KEY (version_id) REFERENCES version(version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_budget_summary_year ON budget_summary(budget_year);

CREATE TABLE IF NOT EXISTS budget_pivot_aggregate (
  id INT AUTO_INCREMENT PRIMARY KEY,
  budget_year INT NOT NULL,
  grain VARCHAR(16) NOT NULL CHECK (grain IN ('year', 'quarter', 'month')),
  metric_level1 VARCHAR(255),
  metric_level2 VARCHAR(255),
  metric_level3 VARCHAR(255),
  metric_level4 VARCHAR(255),
  metric_level5 VARCHAR(255),
  dept_level1 VARCHAR(255),
  dept_level2 VARCHAR(255),
  dept_level3 VARCHAR(255),
  data_code_name VARCHAR(255) NOT NULL,
  product_code_name VARCHAR(255),
  `year` VARCHAR(8) NOT NULL,
  month VARCHAR(8) NOT NULL,
  quarter VARCHAR(8) NOT NULL,
  budget_actual TINYINT(1) NOT NULL CHECK (budget_actual IN (0, 1)),
  version_id INT NOT NULL,
  version_name VARCHAR(255),
  value DOUBLE NOT NULL DEFAULT 0,
  value_type VARCHAR(32) NOT NULL,
  value_source VARCHAR(32) NOT NULL DEFAULT 'manual',
  update_time VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_budget_pivot_aggregate_year ON budget_pivot_aggregate(budget_year);
CREATE INDEX idx_budget_pivot_aggregate_grain
ON budget_pivot_aggregate(grain);
CREATE INDEX idx_budget_pivot_aggregate_version
ON budget_pivot_aggregate(version_id, grain);

{BUSINESS_COST_INCOME_SCHEMA}
"""

COMPARE_SCHEMA = """
CREATE TABLE IF NOT EXISTS compare_settings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  setting_key VARCHAR(255) NOT NULL UNIQUE,
  setting_value TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS compare_budget_summary (
  id INT AUTO_INCREMENT PRIMARY KEY,
  show_level INT NOT NULL CHECK (show_level BETWEEN 1 AND 5),
  data_file_id INT NOT NULL,
  source_year INT NOT NULL,
  source_version_id INT NOT NULL,
  source_version_name VARCHAR(255),
  metric_level1 VARCHAR(255),
  metric_level2 VARCHAR(255),
  metric_level3 VARCHAR(255),
  metric_level4 VARCHAR(255),
  metric_level5 VARCHAR(255),
  dept_level1 VARCHAR(255),
  dept_level2 VARCHAR(255),
  dept_level3 VARCHAR(255),
  data_code_name VARCHAR(255) NOT NULL,
  product_code_name VARCHAR(255),
  `year` VARCHAR(8) NOT NULL,
  month VARCHAR(8) NOT NULL,
  quarter VARCHAR(8) NOT NULL,
  budget_actual TINYINT(1) NOT NULL CHECK (budget_actual IN (0, 1)),
  value DOUBLE NOT NULL DEFAULT 0,
  value_type VARCHAR(32) NOT NULL,
  value_source VARCHAR(32) NOT NULL DEFAULT 'manual',
  sync_time VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_compare_budget_summary_show_level
ON compare_budget_summary(show_level);

CREATE INDEX idx_compare_budget_summary_source
ON compare_budget_summary(source_year, source_version_id);

CREATE TABLE IF NOT EXISTS compare_pivot_aggregate (
  id INT AUTO_INCREMENT PRIMARY KEY,
  grain VARCHAR(16) NOT NULL CHECK (grain IN ('year', 'quarter', 'month')),
  show_level INT NOT NULL CHECK (show_level BETWEEN 1 AND 5),
  data_file_id INT NOT NULL,
  source_year INT NOT NULL,
  source_version_id INT NOT NULL,
  source_version_name VARCHAR(255),
  metric_level1 VARCHAR(255),
  metric_level2 VARCHAR(255),
  metric_level3 VARCHAR(255),
  metric_level4 VARCHAR(255),
  metric_level5 VARCHAR(255),
  dept_level1 VARCHAR(255),
  dept_level2 VARCHAR(255),
  dept_level3 VARCHAR(255),
  data_code_name VARCHAR(255) NOT NULL,
  product_code_name VARCHAR(255),
  `year` VARCHAR(8) NOT NULL,
  month VARCHAR(8) NOT NULL,
  quarter VARCHAR(8) NOT NULL,
  budget_actual TINYINT(1) NOT NULL CHECK (budget_actual IN (0, 1)),
  value DOUBLE NOT NULL DEFAULT 0,
  value_type VARCHAR(32) NOT NULL,
  value_source VARCHAR(32) NOT NULL DEFAULT 'manual',
  sync_time VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_compare_pivot_aggregate_grain
ON compare_pivot_aggregate(grain);

CREATE INDEX idx_compare_pivot_aggregate_level
ON compare_pivot_aggregate(show_level, grain);

CREATE TABLE IF NOT EXISTS compare_sync_job_log (
  job_id INT AUTO_INCREMENT PRIMARY KEY,
  start_time VARCHAR(64) NOT NULL,
  end_time VARCHAR(64),
  trigger_source VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  message TEXT,
  operator_user_id INT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""
