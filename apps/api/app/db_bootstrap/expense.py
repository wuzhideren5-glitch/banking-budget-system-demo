"""Bootstrap helpers for department-expense private tables."""
from __future__ import annotations

import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
from app.db_bootstrap._ddl_normalize import normalize_ddl, find_missing_markers
from typing import Protocol


class AsyncSqlExecutor(Protocol):
    async def execute(self, sql: str, parameters: object = ...) -> object: ...


EXPENSE_FORECAST_SCHEMA = """
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
"""


BI_MAPPING_SCHEMA = """
CREATE TABLE IF NOT EXISTS manage_dept_owner_mapping (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  manage_department TEXT NOT NULL,
  owner_department TEXT NOT NULL,
  UNIQUE (manage_department)
);
"""


BI_AI_SUBJECT_MAPPING_SCHEMA = """
CREATE TABLE IF NOT EXISTS bi_ai_subject_mapping (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  level5_code TEXT NOT NULL DEFAULT '',
  level5_name TEXT NOT NULL DEFAULT '',
  level6_code TEXT NOT NULL DEFAULT '',
  level6_name TEXT NOT NULL DEFAULT '',
  budget_release_caliber TEXT NOT NULL DEFAULT '',
  fee_category TEXT NOT NULL DEFAULT '',
  fee_major TEXT NOT NULL DEFAULT '',
  manage_department_override TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0,
  source_file TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (level6_code, level6_name, sort_order)
);
"""


EXPENSE_BUDGET_ENTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS expense_budget_entry_batch (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  budget_year INTEGER NOT NULL,
  file_name TEXT NOT NULL,
  import_mode TEXT NOT NULL,
  total_rows INTEGER NOT NULL DEFAULT 0,
  matched_rows INTEGER NOT NULL DEFAULT 0,
  unmatched_rows INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  note TEXT
);

CREATE TABLE IF NOT EXISTS expense_budget_entry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER REFERENCES expense_budget_entry_batch(id) ON DELETE CASCADE,
  budget_year INTEGER NOT NULL,
  owner_name_raw TEXT NOT NULL,
  owner_name_mapped TEXT,
  budget_subject_raw TEXT NOT NULL,
  budget_subject_mapped TEXT,
  amount REAL NOT NULL DEFAULT 0,
  adjustment_amount REAL NOT NULL DEFAULT 0,
  owner_matched INTEGER NOT NULL DEFAULT 0 CHECK (owner_matched IN (0, 1)),
  subject_matched INTEGER NOT NULL DEFAULT 0 CHECK (subject_matched IN (0, 1)),
  match_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_expense_budget_entry_year
ON expense_budget_entry(budget_year);

CREATE INDEX IF NOT EXISTS idx_expense_budget_entry_batch
ON expense_budget_entry(batch_id);
"""


EXPENSE_ACTUAL_IMPORT_SCHEMA = """
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


DEPARTMENT_EXPENSE_MASTER_REQUIRED_COLUMNS = {
    "dept_account": {
        "dept_code",
        "dept_name",
        "entity_name",
        "parent_code",
        "level",
        "is_leaf",
    },
    "budget_subject_catalog": {
        "id",
        "parent_id",
        "level_number",
        "subject_name",
        "manage_department",
        "formula_text",
        "sort_order",
    },
    "expense_framework_budget_department": {
        "id",
        "entity_name",
        "group_name",
        "owner_name",
        "budget_department",
    },
    "expense_framework_product_department": {
        "id",
        "entity_name",
        "group_name",
        "owner_name",
        "product_department",
    },
    "expense_framework_subject": {
        "budget_subject",
        "level_label",
        "manage_department",
        "formula_text",
        "sort_order",
    },
}


DEPARTMENT_EXPENSE_MASTER_REQUIRED_SQL_MARKERS = {
    "dept_account": (
        "entity_name TEXT NOT NULL DEFAULT '微众银行'",
    ),
    "budget_subject_catalog": (
        "level_number INTEGER NOT NULL CHECK (level_number BETWEEN 1 AND 5)",
    ),
    "expense_framework_budget_department": (
        "entity_name TEXT NOT NULL DEFAULT ''",
        "UNIQUE (group_name, owner_name, budget_department)",
    ),
    "expense_framework_product_department": (
        "entity_name TEXT NOT NULL DEFAULT ''",
        "UNIQUE (group_name, owner_name, product_department)",
    ),
}


async def _execute_script(db: AsyncSqlExecutor, script: str) -> None:
    for statement in script.split(";"):
        sql = statement.strip()
        if sql:
            await db.execute(f"{sql};")


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def _table_sql(db: AsyncSqlExecutor, table_name: str) -> str:
    """Return the DDL text for a table via SHOW CREATE TABLE."""
    try:
        cur = await db.execute(f"SHOW CREATE TABLE `{table_name}`")
        row = await cur.fetchone()  # type: ignore[attr-defined]
        return str(row[1] or "") if row else ""
    except Exception:
        return ""


async def _table_columns(db: AsyncSqlExecutor, table_name: str) -> list[str]:
    cur = await db.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")
    rows = await cur.fetchall()  # type: ignore[attr-defined]
    return [str(row[1]) for row in rows]


async def _assert_current_expense_forecast_contract(db: AsyncSqlExecutor) -> None:
    columns = set(await _table_columns(db, "expense_forecast_rule"))
    table_sql = (await _table_sql(db, "expense_forecast_rule")).lower()
    if columns and (
        "metric_source_priority" not in columns
        or "driver_source_priority" in columns
        or "driver_expr" in table_sql
        or "driver_first" in table_sql
    ):
        raise RuntimeError("费用预测规则发现旧 driver 合同，系统不再自动迁移")

    if await _table_sql(db, "expense_forecast_rule_param"):
        cur = await db.execute(
            "SELECT 1 FROM expense_forecast_rule_param WHERE param_group = 'driver' LIMIT 1"
        )
        if await cur.fetchone():  # type: ignore[attr-defined]
            raise RuntimeError("费用预测规则参数发现旧 driver 参数组，系统不再自动迁移")

    variable_sql = (await _table_sql(db, "expense_forecast_rule_variable")).lower()
    if "driver_module" in variable_sql:
        raise RuntimeError("费用预测规则变量发现旧 driver_module 来源，系统不再自动迁移")


async def ensure_expense_forecast_schema(db: AsyncSqlExecutor) -> None:
    """Ensure fee-forecast input, rule, result, and override tables exist."""
    await _execute_script(db, EXPENSE_FORECAST_SCHEMA)
    await _assert_current_expense_forecast_contract(db)


def _table_sql_sync(conn: sqlite3.Connection, table_name: str) -> str:
    """Return the DDL text for a table via SHOW CREATE TABLE."""
    try:
        row = conn.execute(f"SHOW CREATE TABLE `{table_name}`").fetchone()
        return str(row[1] or "") if row else ""
    except Exception:
        return ""


def _table_columns_sync(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    ]


def _assert_current_expense_forecast_contract_sync(conn: sqlite3.Connection) -> None:
    columns = set(_table_columns_sync(conn, "expense_forecast_rule"))
    table_sql = _table_sql_sync(conn, "expense_forecast_rule").lower()
    if columns and (
        "metric_source_priority" not in columns
        or "driver_source_priority" in columns
        or "driver_expr" in table_sql
        or "driver_first" in table_sql
    ):
        raise RuntimeError("费用预测规则发现旧 driver 合同，系统不再自动迁移")

    if _table_sql_sync(conn, "expense_forecast_rule_param"):
        row = conn.execute(
            "SELECT 1 FROM expense_forecast_rule_param WHERE param_group = 'driver' LIMIT 1"
        ).fetchone()
        if row:
            raise RuntimeError("费用预测规则参数发现旧 driver 参数组，系统不再自动迁移")

    variable_sql = _table_sql_sync(conn, "expense_forecast_rule_variable").lower()
    if "driver_module" in variable_sql:
        raise RuntimeError("费用预测规则变量发现旧 driver_module 来源，系统不再自动迁移")


def ensure_expense_forecast_schema_sync(conn: sqlite3.Connection) -> None:
    """Synchronous startup adapter for the fee-forecast schema Module."""
    conn.executescript(EXPENSE_FORECAST_SCHEMA)
    _assert_current_expense_forecast_contract_sync(conn)


def _missing_sql_markers(table_sql: str, markers: tuple[str, ...]) -> list[str]:
    """Check if all markers appear in the DDL text, using cross-database normalization."""
    return find_missing_markers(table_sql, markers)


async def ensure_department_expense_master_schema(db: AsyncSqlExecutor) -> None:
    """Validate current department-expense master and framework tables.

    DDL is owned by COMMON_SCHEMA. This adapter keeps runtime paths on the
    current physical-table contract.
    """
    for table_name, required_columns in DEPARTMENT_EXPENSE_MASTER_REQUIRED_COLUMNS.items():
        columns = set(await _table_columns(db, table_name))
        if not columns:
            raise RuntimeError(f"部门费用主数据表 {table_name} 不存在，系统不再自动迁移")
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"部门费用主数据表 {table_name} 缺少当前字段，系统不再自动迁移："
                + ", ".join(missing)
            )
        table_sql = await _table_sql(db, table_name)
        missing_markers = _missing_sql_markers(
            table_sql,
            DEPARTMENT_EXPENSE_MASTER_REQUIRED_SQL_MARKERS.get(table_name, ()),
        )
        if missing_markers:
            raise RuntimeError(
                f"部门费用主数据表 {table_name} 缺少当前约束，系统不再自动迁移："
                + ", ".join(missing_markers)
            )


def ensure_department_expense_master_schema_sync(conn: sqlite3.Connection) -> None:
    """Synchronous startup adapter for current department-expense master tables."""
    for table_name, required_columns in DEPARTMENT_EXPENSE_MASTER_REQUIRED_COLUMNS.items():
        columns = set(_table_columns_sync(conn, table_name))
        if not columns:
            raise RuntimeError(f"部门费用主数据表 {table_name} 不存在，系统不再自动迁移")
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"部门费用主数据表 {table_name} 缺少当前字段，系统不再自动迁移："
                + ", ".join(missing)
            )
        table_sql = _table_sql_sync(conn, table_name)
        missing_markers = _missing_sql_markers(
            table_sql,
            DEPARTMENT_EXPENSE_MASTER_REQUIRED_SQL_MARKERS.get(table_name, ()),
        )
        if missing_markers:
            raise RuntimeError(
                f"部门费用主数据表 {table_name} 缺少当前约束，系统不再自动迁移："
                + ", ".join(missing_markers)
            )


BI_MAPPING_REQUIRED_COLUMNS = {
    "manage_dept_owner_mapping": {
        "id",
        "manage_department",
        "owner_department",
    },
}


BI_MAPPING_REQUIRED_SQL_MARKERS = {
    "manage_dept_owner_mapping": (
        "UNIQUE (manage_department)",
    ),
}


BI_AI_SUBJECT_MAPPING_REQUIRED_COLUMNS = {
    "id",
    "level5_code",
    "level5_name",
    "level6_code",
    "level6_name",
    "budget_release_caliber",
    "fee_category",
    "fee_major",
    "manage_department_override",
    "sort_order",
    "source_file",
    "created_at",
    "updated_at",
}


BI_AI_SUBJECT_MAPPING_REQUIRED_SQL_MARKERS = (
    "UNIQUE (level6_code, level6_name, sort_order)",
)


BI_AI_SUBJECT_MAPPING_OBSOLETE_COLUMNS = {
    "level2_name",
    "level3_code",
    "level3_name",
    "level4_code",
    "level4_name",
}


async def _assert_current_bi_mapping_contract(db: AsyncSqlExecutor) -> None:
    for table_name, required_columns in BI_MAPPING_REQUIRED_COLUMNS.items():
        columns = set(await _table_columns(db, table_name))
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"BI映射表 {table_name} 缺少当前字段，系统不再自动迁移："
                + ", ".join(missing)
            )
        table_sql = await _table_sql(db, table_name)
        missing_markers = find_missing_markers(
            table_sql,
            BI_MAPPING_REQUIRED_SQL_MARKERS.get(table_name, ()),
        )
        if missing_markers:
            raise RuntimeError(
                f"BI映射表 {table_name} 缺少当前唯一约束，系统不再自动迁移："
                + ", ".join(missing_markers)
            )


def _assert_current_bi_mapping_contract_sync(conn: sqlite3.Connection) -> None:
    for table_name, required_columns in BI_MAPPING_REQUIRED_COLUMNS.items():
        columns = set(_table_columns_sync(conn, table_name))
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"BI映射表 {table_name} 缺少当前字段，系统不再自动迁移："
                + ", ".join(missing)
            )
        table_sql = _table_sql_sync(conn, table_name)
        missing_markers = find_missing_markers(
            table_sql,
            BI_MAPPING_REQUIRED_SQL_MARKERS.get(table_name, ()),
        )
        if missing_markers:
            raise RuntimeError(
                f"BI映射表 {table_name} 缺少当前唯一约束，系统不再自动迁移："
                + ", ".join(missing_markers)
            )


async def _assert_current_bi_ai_subject_mapping_contract(db: AsyncSqlExecutor) -> None:
    table_name = "bi_ai_subject_mapping"
    columns = set(await _table_columns(db, table_name))
    missing = sorted(BI_AI_SUBJECT_MAPPING_REQUIRED_COLUMNS - columns)
    obsolete = sorted(BI_AI_SUBJECT_MAPPING_OBSOLETE_COLUMNS & columns)
    if missing:
        raise RuntimeError(
            f"BI-AI科目映射表 {table_name} 缺少当前字段，系统不再自动迁移："
            + ", ".join(missing)
        )
    if obsolete:
        raise RuntimeError(
            f"BI-AI科目映射表 {table_name} 仍包含已删除字段："
            + ", ".join(obsolete)
        )
    table_sql = await _table_sql(db, table_name)
    missing_markers = find_missing_markers(
        table_sql,
        BI_AI_SUBJECT_MAPPING_REQUIRED_SQL_MARKERS,
    )
    if missing_markers:
        raise RuntimeError(
            f"BI-AI科目映射表 {table_name} 缺少当前唯一约束，系统不再自动迁移："
            + ", ".join(missing_markers)
        )


def _assert_current_bi_ai_subject_mapping_contract_sync(conn: sqlite3.Connection) -> None:
    table_name = "bi_ai_subject_mapping"
    columns = set(_table_columns_sync(conn, table_name))
    missing = sorted(BI_AI_SUBJECT_MAPPING_REQUIRED_COLUMNS - columns)
    obsolete = sorted(BI_AI_SUBJECT_MAPPING_OBSOLETE_COLUMNS & columns)
    if missing:
        raise RuntimeError(
            f"BI-AI科目映射表 {table_name} 缺少当前字段，系统不再自动迁移："
            + ", ".join(missing)
        )
    if obsolete:
        raise RuntimeError(
            f"BI-AI科目映射表 {table_name} 仍包含已删除字段："
            + ", ".join(obsolete)
        )
    table_sql = _table_sql_sync(conn, table_name)
    missing_markers = find_missing_markers(
        table_sql,
        BI_AI_SUBJECT_MAPPING_REQUIRED_SQL_MARKERS,
    )
    if missing_markers:
        raise RuntimeError(
            f"BI-AI科目映射表 {table_name} 缺少当前唯一约束，系统不再自动迁移："
            + ", ".join(missing_markers)
        )


async def ensure_bi_mapping_schema(db: AsyncSqlExecutor) -> None:
    """Ensure BI mapping private tables exist and match the current contract."""
    await _execute_script(db, BI_MAPPING_SCHEMA)
    await _assert_current_bi_mapping_contract(db)


def ensure_bi_mapping_schema_sync(conn: sqlite3.Connection) -> None:
    """Synchronous startup adapter for the BI mapping schema Module."""
    conn.executescript(BI_MAPPING_SCHEMA)
    _assert_current_bi_mapping_contract_sync(conn)


async def _migrate_bi_ai_subject_mapping_contract(db: AsyncSqlExecutor, columns: set[str]) -> None:
    obsolete_columns = BI_AI_SUBJECT_MAPPING_OBSOLETE_COLUMNS & columns
    if not obsolete_columns:
        return
    await db.execute("DROP TABLE IF EXISTS __bi_ai_subject_mapping_new")
    await _execute_script(
        db,
        BI_AI_SUBJECT_MAPPING_SCHEMA.replace(
            "bi_ai_subject_mapping",
            "__bi_ai_subject_mapping_new",
            1,
        ),
    )
    manage_override_expr = (
        "COALESCE(manage_department_override, '')"
        if "manage_department_override" in columns
        else "''"
    )
    filter_clause = (
        "WHERE COALESCE(level3_code, '') NOT IN ('YS0104', 'YS0105')"
        if "level3_code" in columns
        else ""
    )
    await db.execute(
        f"""
        INSERT INTO __bi_ai_subject_mapping_new(
          id, level5_code, level5_name, level6_code, level6_name,
          budget_release_caliber, fee_category, fee_major,
          manage_department_override, sort_order, source_file, created_at, updated_at
        )
        SELECT
          id,
          COALESCE(level5_code, ''),
          COALESCE(level5_name, ''),
          COALESCE(level6_code, ''),
          COALESCE(level6_name, ''),
          COALESCE(budget_release_caliber, ''),
          COALESCE(fee_category, ''),
          COALESCE(fee_major, ''),
          {manage_override_expr},
          COALESCE(sort_order, 0),
          COALESCE(source_file, ''),
          COALESCE(created_at, ''),
          COALESCE(updated_at, '')
        FROM bi_ai_subject_mapping
        {filter_clause}
        """
    )
    await db.execute("DROP TABLE bi_ai_subject_mapping")
    await db.execute("ALTER TABLE __bi_ai_subject_mapping_new RENAME TO bi_ai_subject_mapping")


def _migrate_bi_ai_subject_mapping_contract_sync(conn: sqlite3.Connection, columns: set[str]) -> None:
    obsolete_columns = BI_AI_SUBJECT_MAPPING_OBSOLETE_COLUMNS & columns
    if not obsolete_columns:
        return
    conn.execute("DROP TABLE IF EXISTS __bi_ai_subject_mapping_new")
    conn.executescript(
        BI_AI_SUBJECT_MAPPING_SCHEMA.replace(
            "bi_ai_subject_mapping",
            "__bi_ai_subject_mapping_new",
            1,
        )
    )
    manage_override_expr = (
        "COALESCE(manage_department_override, '')"
        if "manage_department_override" in columns
        else "''"
    )
    filter_clause = (
        "WHERE COALESCE(level3_code, '') NOT IN ('YS0104', 'YS0105')"
        if "level3_code" in columns
        else ""
    )
    conn.execute(
        f"""
        INSERT INTO __bi_ai_subject_mapping_new(
          id, level5_code, level5_name, level6_code, level6_name,
          budget_release_caliber, fee_category, fee_major,
          manage_department_override, sort_order, source_file, created_at, updated_at
        )
        SELECT
          id,
          COALESCE(level5_code, ''),
          COALESCE(level5_name, ''),
          COALESCE(level6_code, ''),
          COALESCE(level6_name, ''),
          COALESCE(budget_release_caliber, ''),
          COALESCE(fee_category, ''),
          COALESCE(fee_major, ''),
          {manage_override_expr},
          COALESCE(sort_order, 0),
          COALESCE(source_file, ''),
          COALESCE(created_at, ''),
          COALESCE(updated_at, '')
        FROM bi_ai_subject_mapping
        {filter_clause}
        """
    )
    conn.execute("DROP TABLE bi_ai_subject_mapping")
    conn.execute("ALTER TABLE __bi_ai_subject_mapping_new RENAME TO bi_ai_subject_mapping")


async def ensure_bi_ai_subject_mapping_schema(db: AsyncSqlExecutor) -> None:
    """Ensure the BI-AI subject mapping table exists and matches the current contract."""
    await _execute_script(db, BI_AI_SUBJECT_MAPPING_SCHEMA)
    cur = await db.execute('PRAGMA table_info("bi_ai_subject_mapping")')
    columns = {str(row[1]) for row in await cur.fetchall()}
    await _migrate_bi_ai_subject_mapping_contract(db, columns)
    cur = await db.execute('PRAGMA table_info("bi_ai_subject_mapping")')
    columns = {str(row[1]) for row in await cur.fetchall()}
    if "manage_department_override" not in columns:
        await db.execute(
            "ALTER TABLE bi_ai_subject_mapping "
            "ADD COLUMN manage_department_override TEXT NOT NULL DEFAULT ''"
        )
    await _assert_current_bi_ai_subject_mapping_contract(db)


def ensure_bi_ai_subject_mapping_schema_sync(conn: sqlite3.Connection) -> None:
    """Synchronous startup adapter for the BI-AI subject mapping table."""
    conn.executescript(BI_AI_SUBJECT_MAPPING_SCHEMA)
    columns = {str(row[1]) for row in conn.execute('PRAGMA table_info("bi_ai_subject_mapping")').fetchall()}
    _migrate_bi_ai_subject_mapping_contract_sync(conn, columns)
    columns = {str(row[1]) for row in conn.execute('PRAGMA table_info("bi_ai_subject_mapping")').fetchall()}
    if "manage_department_override" not in columns:
        conn.execute(
            "ALTER TABLE bi_ai_subject_mapping "
            "ADD COLUMN manage_department_override TEXT NOT NULL DEFAULT ''"
        )
    _assert_current_bi_ai_subject_mapping_contract_sync(conn)


EXPENSE_ACTUAL_IMPORT_REQUIRED_COLUMNS = {
    "expense_actual_import_batch": {
        "id",
        "import_kind",
        "file_name",
        "import_mode",
        "periods_text",
        "total_rows",
        "matched_owner_rows",
        "matched_subject_rows",
        "unmatched_rows",
        "created_at",
        "note",
    },
    "expense_actual_detail_raw": {
        "id",
        "batch_id",
        "import_kind",
        "data_date",
        "period_ym",
        "period_text",
        "org_code",
        "org_name",
        "dep_code",
        "dep_name",
        "subject_code",
        "subject_name",
        "journal_name",
        "serial_no",
        "line_desc",
        "amount",
        "fee_type_code",
        "fee_type_name",
        "bi_ai_source_code",
        "bi_ai_source_name",
        "manage_department_code",
        "owner_name_raw",
        "owner_name_mapped",
        "monthly_caliber",
        "budget_subject_raw",
        "budget_subject_mapped",
        "fee_major_mapped",
        "fee_category_mapped",
        "budget_release_caliber_mapped",
        "manage_department2",
        "special_control_tag",
        "owner_matched",
        "subject_matched",
        "match_note",
    },
}


EXPENSE_ACTUAL_IMPORT_REQUIRED_SQL_MARKERS = {
    "expense_actual_import_batch": (
        "import_kind TEXT NOT NULL DEFAULT 'current_year_actual'",
    ),
    "expense_actual_detail_raw": (
        "import_kind TEXT NOT NULL DEFAULT 'current_year_actual'",
        "owner_matched INTEGER NOT NULL DEFAULT 0 CHECK (owner_matched IN (0, 1))",
        "subject_matched INTEGER NOT NULL DEFAULT 0 CHECK (subject_matched IN (0, 1))",
    ),
}


async def _assert_current_expense_actual_import_contract(db: AsyncSqlExecutor) -> None:
    for table_name, required_columns in EXPENSE_ACTUAL_IMPORT_REQUIRED_COLUMNS.items():
        columns = set(await _table_columns(db, table_name))
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"费用执行明细导入表 {table_name} 缺少当前字段，系统不再自动迁移："
                + ", ".join(missing)
            )
        table_sql = await _table_sql(db, table_name)
        missing_markers = _missing_sql_markers(
            table_sql,
            EXPENSE_ACTUAL_IMPORT_REQUIRED_SQL_MARKERS.get(table_name, ()),
        )
        if missing_markers:
            raise RuntimeError(
                f"费用执行明细导入表 {table_name} 缺少当前约束，系统不再自动迁移："
                + ", ".join(missing_markers)
            )


def _assert_current_expense_actual_import_contract_sync(conn: sqlite3.Connection) -> None:
    for table_name, required_columns in EXPENSE_ACTUAL_IMPORT_REQUIRED_COLUMNS.items():
        columns = set(_table_columns_sync(conn, table_name))
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"费用执行明细导入表 {table_name} 缺少当前字段，系统不再自动迁移："
                + ", ".join(missing)
            )
        table_sql = _table_sql_sync(conn, table_name)
        missing_markers = _missing_sql_markers(
            table_sql,
            EXPENSE_ACTUAL_IMPORT_REQUIRED_SQL_MARKERS.get(table_name, ()),
        )
        if missing_markers:
            raise RuntimeError(
                f"费用执行明细导入表 {table_name} 缺少当前约束，系统不再自动迁移："
                + ", ".join(missing_markers)
            )


async def ensure_expense_budget_entry_schema(db: AsyncSqlExecutor) -> None:
    await _execute_script(db, EXPENSE_BUDGET_ENTRY_SCHEMA)
    cur = await db.execute('PRAGMA table_info("expense_budget_entry")')
    columns = {str(row[1]) for row in await cur.fetchall()}
    if "adjustment_amount" not in columns:
        await db.execute(
            'ALTER TABLE expense_budget_entry ADD COLUMN adjustment_amount REAL NOT NULL DEFAULT 0'
        )


def ensure_expense_budget_entry_schema_sync(conn: sqlite3.Connection) -> None:
    conn.executescript(EXPENSE_BUDGET_ENTRY_SCHEMA)
    columns = {str(row[1]) for row in conn.execute('PRAGMA table_info("expense_budget_entry")').fetchall()}
    if "adjustment_amount" not in columns:
        conn.execute(
            'ALTER TABLE expense_budget_entry ADD COLUMN adjustment_amount REAL NOT NULL DEFAULT 0'
        )


async def ensure_expense_actual_import_schema(db: AsyncSqlExecutor) -> None:
    """Ensure raw expense-actual import tables and their mapping dependencies exist."""
    await _execute_script(db, EXPENSE_ACTUAL_IMPORT_SCHEMA)
    await _assert_current_expense_actual_import_contract(db)
    await ensure_bi_mapping_schema(db)
    await ensure_bi_ai_subject_mapping_schema(db)


def ensure_expense_actual_import_schema_sync(conn: sqlite3.Connection) -> None:
    """Synchronous startup adapter for raw expense actual imports."""
    conn.executescript(EXPENSE_ACTUAL_IMPORT_SCHEMA)
    _assert_current_expense_actual_import_contract_sync(conn)
    ensure_bi_mapping_schema_sync(conn)
    ensure_bi_ai_subject_mapping_schema_sync(conn)
