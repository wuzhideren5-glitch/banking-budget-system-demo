"""Current schema setup and contract validation for runtime metric identity tables."""
from __future__ import annotations

import re
from pathlib import Path

import pymysql


# 05 / 05.01 / 05.01.01.02.001 / 05.01.01.03.01.001 / 05.02.09.02.101
LOCAL_METRIC_CODE_PATTERN = r"\d{2}(?:\.\d{2})*(?:\.\d{3})?"
PRODUCT_ROOT_NODE_RE = re.compile(r"^[A-Z][A-Z0-9]*$")
PRODUCT_PREFIXED_METRIC_CODE_RE = re.compile(
    rf"^[A-Z][A-Z0-9]*\.{LOCAL_METRIC_CODE_PATTERN}$"
)
METRIC_NODE_REQUIRED_COLUMNS = [
    "node_code",
    "node_name",
    "parent_code",
    "product_code",
    "local_metric_code",
    "logic_code",
    "functional_group_code",
    "metric_table_name",
    "level",
    "node_type",
    "horizontal_rollup",
    "vertical_rollup",
    "runtime_account_enabled",
    "budget_formula",
    "actual_formula",
    "budget_rule_code",
    "budget_rule_config_json",
    "need_calc",
    "formula_calc_mode",
    "allow_manual_entry",
    "value_type",
    "annual_agg_rule",
    "sort_order",
    "is_active",
    "remark",
    "created_at",
    "updated_at",
]
RUNTIME_ACCOUNT_NODE_COLUMNS = {
    "runtime_account_enabled": "TINYINT(1) NOT NULL DEFAULT 0",
    "budget_formula": "TEXT",
    "actual_formula": "TEXT",
    "budget_rule_code": "VARCHAR(64)",
    "budget_rule_config_json": "JSON",
    "need_calc": "TINYINT(1) NOT NULL DEFAULT 0",
    "formula_calc_mode": "TINYINT(1) NOT NULL DEFAULT 0",
    "allow_manual_entry": "TINYINT(1) NOT NULL DEFAULT 1",
    "value_type": "VARCHAR(32) NOT NULL DEFAULT '金额'",
    "annual_agg_rule": "VARCHAR(255) NOT NULL DEFAULT ''",
}
DATA_ACCOUNT_VIEW_REQUIRED_COLUMNS = [
    "data_acct_code",
    "data_acct_name",
    "budget_formula",
    "actual_formula",
    "budget_rule_code",
    "budget_rule_config_json",
    "need_calc",
    "formula_calc_mode",
    "allow_manual_entry",
    "value_type",
    "remark",
]
METRIC_BINDING_REQUIRED_COLUMNS = [
    "data_acct_code",
    "metric_node_code",
    "scope_type",
    "scope_code",
    "sort_order",
    "is_active",
    "remark",
    "created_at",
    "updated_at",
]


def _is_product_prefixed_metric_code(code: str, scope_code: str | None = None) -> bool:
    text = str(code or "").strip().upper()
    if not PRODUCT_PREFIXED_METRIC_CODE_RE.fullmatch(text):
        return False
    product = text.split(".", 1)[0]
    if scope_code and product != str(scope_code or "").strip().upper():
        return False
    return True


def _is_current_metric_tree_node_code(code: str) -> bool:
    text = str(code or "").strip().upper()
    return bool(PRODUCT_ROOT_NODE_RE.fullmatch(text) or PRODUCT_PREFIXED_METRIC_CODE_RE.fullmatch(text))


def _table_exists(conn: pymysql.Connection, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            (table_name,),
        )
        return cur.fetchone() is not None


def _relation_type(conn: pymysql.Connection, relation_name: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT TABLE_TYPE
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            (relation_name,),
        )
        row = cur.fetchone()
    if row is None:
        return ""
    table_type = str(row[0] or "")
    return "view" if table_type == "VIEW" else "table"


def _table_columns(conn: pymysql.Connection, table_name: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (table_name,),
        )
        return {str(row[0]) for row in cur.fetchall()}


def _table_sql(conn: pymysql.Connection, table_name: str) -> str:
    # MySQL doesn't store original DDL; approximate from INFORMATION_SCHEMA
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                   COLUMN_KEY, EXTRA
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (table_name,),
        )
        cols = cur.fetchall()
    return " ".join(f"{c[0]} {c[1]}" for c in cols) if cols else ""


def _ensure_metric_binding_view(conn: pymysql.Connection) -> None:
    relation_type = _relation_type(conn, "data_account_metric_binding")
    with conn.cursor() as cur:
        if relation_type == "table":
            cur.execute("DROP TABLE data_account_metric_binding")
        elif relation_type == "view":
            cur.execute("DROP VIEW data_account_metric_binding")
        cur.execute(
            """
            CREATE VIEW data_account_metric_binding AS
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
            WHERE n.is_active = 1
            """
        )


def _ensure_data_account_view(conn: pymysql.Connection) -> None:
    relation_type = _relation_type(conn, "data_account")
    with conn.cursor() as cur:
        if relation_type == "table":
            cur.execute(
                """
                SELECT d.data_acct_code
                FROM data_account d
                LEFT JOIN data_account_metric_node n ON n.node_code = d.data_acct_code
                WHERE n.node_code IS NULL
                ORDER BY d.data_acct_code
                LIMIT 10
                """
            )
            missing_nodes = [str(row[0] or "").strip().upper() for row in cur.fetchall()]
            if missing_nodes:
                return
            cur.execute(
                """
                UPDATE data_account_metric_node
                SET
                  node_name = COALESCE(
                    (SELECT d.data_acct_name FROM data_account d WHERE d.data_acct_code = node_code),
                    node_name
                  ),
                  runtime_account_enabled = CASE
                    WHEN EXISTS (SELECT 1 FROM data_account d WHERE d.data_acct_code = node_code) THEN 1
                    ELSE runtime_account_enabled
                  END,
                  budget_formula = (
                    SELECT d.budget_formula FROM data_account d WHERE d.data_acct_code = node_code
                  ),
                  actual_formula = (
                    SELECT d.actual_formula FROM data_account d WHERE d.data_acct_code = node_code
                  ),
                  budget_rule_code = (
                    SELECT d.budget_rule_code FROM data_account d WHERE d.data_acct_code = node_code
                  ),
                  budget_rule_config_json = (
                    SELECT d.budget_rule_config_json FROM data_account d WHERE d.data_acct_code = node_code
                  ),
                  need_calc = COALESCE(
                    (SELECT d.need_calc FROM data_account d WHERE d.data_acct_code = node_code),
                    need_calc
                  ),
                  formula_calc_mode = COALESCE(
                    (SELECT d.formula_calc_mode FROM data_account d WHERE d.data_acct_code = node_code),
                    formula_calc_mode
                  ),
                  allow_manual_entry = COALESCE(
                    (SELECT d.allow_manual_entry FROM data_account d WHERE d.data_acct_code = node_code),
                    allow_manual_entry
                  ),
                  value_type = COALESCE(
                    (SELECT d.value_type FROM data_account d WHERE d.data_acct_code = node_code),
                    value_type,
                    '金额'
                  ),
                  remark = COALESCE(
                    remark,
                    (SELECT d.remark FROM data_account d WHERE d.data_acct_code = node_code)
                  )
                WHERE EXISTS (
                  SELECT 1 FROM data_account d WHERE d.data_acct_code = node_code
                )
                """
            )
            cur.execute("DROP TABLE data_account")
        elif relation_type == "view":
            cur.execute("DROP VIEW data_account")
        cur.execute(
            """
            CREATE VIEW data_account AS
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
            WHERE runtime_account_enabled = 1 AND is_active = 1
            """
        )


def _ensure_metric_node_v02_columns(conn: pymysql.Connection) -> None:
    if not _table_exists(conn, "data_account_metric_node"):
        return
    cols = _table_columns(conn, "data_account_metric_node")
    with conn.cursor() as cur:
        if "logic_code" not in cols:
            cur.execute("ALTER TABLE data_account_metric_node ADD COLUMN logic_code VARCHAR(255)")
        if "horizontal_rollup" not in cols:
            cur.execute(
                "ALTER TABLE data_account_metric_node ADD COLUMN horizontal_rollup TINYINT(1) NOT NULL DEFAULT 0"
            )
        if "vertical_rollup" not in cols:
            cur.execute(
                "ALTER TABLE data_account_metric_node ADD COLUMN vertical_rollup TINYINT(1) NOT NULL DEFAULT 0"
            )
    cols = _table_columns(conn, "data_account_metric_node")
    with conn.cursor() as cur:
        for column_name, column_type in RUNTIME_ACCOUNT_NODE_COLUMNS.items():
            if column_name not in cols:
                cur.execute(f"ALTER TABLE data_account_metric_node ADD COLUMN {column_name} {column_type}")
    cols = _table_columns(conn, "data_account_metric_node")
    with conn.cursor() as cur:
        if "metric_table_name" not in cols:
            cur.execute("ALTER TABLE data_account_metric_node ADD COLUMN metric_table_name VARCHAR(255) NOT NULL DEFAULT ''")
            # Migrate Chinese table names from functional_group_code to metric_table_name
            cur.execute(
                """
                UPDATE data_account_metric_node
                SET metric_table_name = functional_group_code
                WHERE functional_group_code NOT REGEXP '^[0-9].*'
                  AND COALESCE(functional_group_code, '') <> ''
                """
            )
        # Always derive logic_code from node_code (strip product prefix, keep dots)
        cur.execute(
            """
            UPDATE data_account_metric_node
            SET logic_code = CASE
                WHEN LOCATE('.', node_code) = 0 THEN ''
                ELSE SUBSTR(node_code, LOCATE('.', node_code) + 1)
            END
            """
        )


def _assert_exact_columns(
    conn: pymysql.Connection,
    table_name: str,
    required_columns: list[str],
    label: str,
) -> None:
    cols = _table_columns(conn, table_name)
    required = set(required_columns)
    missing = sorted(required - cols)
    if missing:
        raise RuntimeError(
            f"{label}缺少当前字段，系统不再自动迁移："
            + ", ".join(missing)
        )

    retired_or_extra = sorted(cols - required)
    if retired_or_extra:
        raise RuntimeError(
            f"{label}发现旧字段/非当前字段，系统不再自动迁移："
            + ", ".join(retired_or_extra)
        )


def _assert_current_metric_tree_physical_schema(conn: pymysql.Connection) -> None:
    _assert_exact_columns(
        conn,
        "data_account_metric_node",
        METRIC_NODE_REQUIRED_COLUMNS,
        "指标树表",
    )
    if _relation_type(conn, "data_account") != "view":
        raise RuntimeError("运行指标引用必须是由指标树派生的 view，不再允许物理表")
    _assert_exact_columns(
        conn,
        "data_account",
        DATA_ACCOUNT_VIEW_REQUIRED_COLUMNS,
        "运行指标引用视图",
    )
    if _relation_type(conn, "data_account_metric_binding") != "view":
        raise RuntimeError("兼容指标绑定必须是由指标树派生的 view，不再允许物理表")
    _assert_exact_columns(
        conn,
        "data_account_metric_binding",
        METRIC_BINDING_REQUIRED_COLUMNS,
        "兼容指标绑定视图",
    )

    node_sql = _table_sql(conn, "data_account_metric_node")
    node_markers = (
        "CHECK (level BETWEEN 1 AND 8)",
        "CHECK (node_type IN ('CATEGORY', 'GROUP', 'METRIC'))",
    )
    missing_node_checks = [marker for marker in node_markers if marker not in node_sql]
    if missing_node_checks:
        raise RuntimeError(
            "指标树表缺少当前约束，系统不再自动重建："
            + ", ".join(missing_node_checks)
        )


def _assert_current_metric_identity(conn: pymysql.Connection) -> None:
    """Fail fast when retired metric-code shapes remain in current tables."""
    relation = _relation_type(conn, "data_account")
    if relation in {"table", "view"}:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT data_acct_code FROM data_account")
            bad_data_codes = [
                str(row[0] or "").strip().upper()
                for row in cur.fetchall()
                if str(row[0] or "").strip()
                and not _is_product_prefixed_metric_code(str(row[0] or "").strip().upper())
            ][:10]
        if bad_data_codes:
            raise RuntimeError(
                "机构及产品指标兼容表发现旧编码/非产品前缀指标主键，系统不再自动迁移："
                + ", ".join(bad_data_codes)
            )

    with conn.cursor() as cur:
        cur.execute("SELECT node_code FROM data_account_metric_node")
        bad_node_codes = [
            str(row[0] or "").strip().upper()
            for row in cur.fetchall()
            if str(row[0] or "").strip()
            and not _is_current_metric_tree_node_code(str(row[0] or "").strip().upper())
        ][:10]
    if bad_node_codes:
        raise RuntimeError(
            "指标树发现旧本地指标节点，系统不再自动迁移："
            + ", ".join(bad_node_codes)
        )

    invalid_node_fields: list[str] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT node_code, product_code, local_metric_code, logic_code, level,
                   horizontal_rollup, vertical_rollup
            FROM data_account_metric_node
            ORDER BY node_code
            """
        )
        for row in cur.fetchall():
            node_code = str(row[0] or "").strip().upper()
            product_code = str(row[1] or "").strip().upper()
            local_metric_code = str(row[2] or "").strip().upper()
            logic_code = str(row[3] or "").strip().upper()
            level = int(row[4] or 0)
            horizontal_rollup = int(row[5] or 0)
            vertical_rollup = int(row[6] or 0)
            if not node_code:
                continue

            expected_level = node_code.count(".") + 1
            if "." in node_code:
                expected_product, expected_local = node_code.split(".", 1)
            else:
                expected_product, expected_local = node_code, ""
            if (
                product_code != expected_product
                or local_metric_code != expected_local
                or logic_code != expected_local
                or level != expected_level
                or horizontal_rollup not in {0, 1}
                or vertical_rollup not in {0, 1}
            ):
                invalid_node_fields.append(node_code)
            if len(invalid_node_fields) >= 10:
                break
    if invalid_node_fields:
        raise RuntimeError(
            "指标树发现派生字段或汇总方式不符合当前合同，系统不再自动修正："
            + ", ".join(invalid_node_fields)
        )

    bad_bindings: list[str] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT data_acct_code, metric_node_code, scope_code
            FROM data_account_metric_binding
            """
        )
        for data_code, metric_code, scope_code in cur.fetchall():
            data = str(data_code or "").strip().upper()
            metric = str(metric_code or "").strip().upper()
            scope = str(scope_code or "").strip().upper()
            product = metric.split(".", 1)[0] if _is_product_prefixed_metric_code(metric) else ""
            if data != metric or not product or scope != product:
                bad_bindings.append(f"{data}/{metric}/{scope}")
            if len(bad_bindings) >= 10:
                break
    if bad_bindings:
        raise RuntimeError(
            "兼容指标绑定发现旧指标身份，系统不再自动迁移："
            + ", ".join(bad_bindings)
        )


def ensure_runtime_metric_identity_tables(conn: pymysql.Connection) -> None:
    """Create runtime metric identity tables and validate current contracts."""
    with conn.cursor() as cur:
        cur.execute(
            """
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
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_data_account_metric_node_parent
            ON data_account_metric_node(parent_code)
            """
        )
    _ensure_metric_node_v02_columns(conn)
    _ensure_data_account_view(conn)
    _ensure_metric_binding_view(conn)
    _assert_current_metric_tree_physical_schema(conn)
    _assert_current_metric_identity(conn)


def ensure_budget_data_uses_current_metric_identity(conn: pymysql.Connection) -> None:
    """Reject annual facts that still use retired data-account code shapes."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'budget_data'
            """
        )
        if cur.fetchone() is None:
            return
        cur.execute(
            """
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'budget_data'
            """
        )
        columns = {str(row[0]) for row in cur.fetchall()}
        product_expr = "product_code" if "product_code" in columns else "NULL"
        cur.execute(f"SELECT DISTINCT data_acct_code, {product_expr} FROM budget_data")
        bad_rows: list[str] = []
        for data_acct_code, product_code in cur.fetchall():
            data_code = str(data_acct_code or "").strip().upper()
            product = str(product_code or "").strip().upper()
            data_product = (
                data_code.split(".", 1)[0]
                if _is_product_prefixed_metric_code(data_code)
                else ""
            )
            if not data_product or (product and product != data_product):
                bad_rows.append(f"{data_code}/{product or '_'}")
            if len(bad_rows) >= 10:
                break
    if bad_rows:
        raise RuntimeError(
            "budget_data 发现旧预算事实指标编码，系统不再自动迁移："
            + ", ".join(bad_rows)
        )
