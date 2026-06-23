"""MySQL database initialization from schema definitions."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pymysql

import app.core.pymysql_compat  # noqa: F401 — monkey-patch for sqlite3 compat

from app.core.config import settings
from app.db_bootstrap.budget_data import (
    ensure_budget_data_update_time_triggers,
    validate_budget_data_fact_table,
)
from app.db_bootstrap.budget_version import ensure_budget_version_schema_sync
from app.db_bootstrap.business_cost_income import (
    ensure_business_cost_income_schema_with_common,
)
from app.db_bootstrap.runtime_metric_tree import (
    ensure_runtime_metric_identity_tables,
)
from app.db_bootstrap.expense import (
    ensure_bi_mapping_schema_sync,
    ensure_department_expense_master_schema_sync,
    ensure_expense_actual_import_schema_sync,
    ensure_expense_budget_entry_schema_sync,
    ensure_expense_forecast_schema_sync,
)
from app.db_bootstrap.current_contracts import (
    ensure_runtime_metric_identity_schema,
    ensure_org_product_runtime_catalog_schema,
)
from app.db_bootstrap.derived_read_models import (
    ensure_budget_read_model_schema,
    ensure_compare_read_model_schema,
)
from app.db_bootstrap.generated_paths import validate_generated_file_paths
from app.db_bootstrap.report_display import ensure_budget_output_display_item_schema_sync
from app.db_bootstrap.retired_deletion import drop_retired_tables
from app.db_bootstrap.runner import sync_current_budget_registry
from app.db_bootstrap.schemas import BUDGET_SCHEMA, COMMON_SCHEMA, COMPARE_SCHEMA
from app.db_bootstrap.seeds import seed_default_smart_ppt, seed_periods
from app.db_bootstrap.smart_report import ensure_smart_report_schema_sync
from app.routers.org_product_helpers import ensure_org_product_schema
from app.services.org_product_metric_runtime_sync import (
    OrgProductMetricRuntimeSyncError,
    assert_all_runtime_metric_refs_are_confirmed_org_product_metrics,
    normalize_legacy_corp_data_account_refs,
    normalize_org_product_metric_mapping_statuses,
    normalize_read_model_data_code_names,
    purge_legacy_corp_metric_master,
    sync_existing_org_product_metric_tables,
)

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _purge_legacy_aa05_nodes(conn: pymysql.Connection) -> int:
    """Delete legacy .05 expense tree nodes that were replaced by .90/.91 trees.

    Only targets the old expense tree (AA.05 / A.05 / A01.05 / ... / F01.05),
    NOT legitimate .05 leaf nodes inside non-expense metric codes (e.g. A01.14.01.01.05).
    """
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute(
            "DELETE FROM data_account_metric_node "
            "WHERE node_code LIKE '%.05%' "
            "  AND node_code NOT LIKE '%.90%' "
            "  AND node_code NOT LIKE '%.91%' "
            "  AND node_code NOT LIKE 'A01.14%' "
            "ORDER BY LENGTH(node_code) DESC"
        )
        removed = int(cur.rowcount or 0)
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    return removed


def _purge_legacy_second_segment_99_nodes(conn: pymysql.Connection) -> int:
    """Delete retired *.99.* metric branches (e.g. A02.99) from the runtime master."""
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute(
            "DELETE FROM data_account_metric_node "
            "WHERE node_code REGEXP '^[^.]+\\\\.99(\\\\.|$)' "
            "ORDER BY LENGTH(node_code) DESC"
        )
        removed = int(cur.rowcount or 0)
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    return removed


def _purge_legacy_org_product_metric_branches(conn: pymysql.Connection) -> tuple[int, int]:
    """Remove retired org/product metric branches that must not return after MySQL migration."""
    removed_aa05 = _purge_legacy_aa05_nodes(conn)
    removed_seg99 = _purge_legacy_second_segment_99_nodes(conn)
    if removed_aa05 or removed_seg99:
        logger.info(
            "purged_legacy_org_product_metric_branches aa05=%s seg99=%s",
            removed_aa05,
            removed_seg99,
        )
    return removed_aa05, removed_seg99


def _connect() -> pymysql.Connection:
    """Create a new MySQL connection from settings."""
    return pymysql.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=False,
        init_command="SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci",
    )


def _executescript(conn: pymysql.Connection, sql_script: str) -> None:
    """Execute a multi-statement SQL script by splitting on semicolons.

    Uses $$ delimiter only when triggers/procedures are present.
    """
    if "$$" in sql_script:
        statements = [
            s.strip()
            for s in sql_script.replace("DELIMITER $$", "").replace("DELIMITER ;", "").split("$$")
            if s.strip()
        ]
    else:
        statements = [s.strip() for s in sql_script.split(";") if s.strip()]
    with conn.cursor() as cur:
        for stmt in statements:
            stmt = stmt.strip()
            if stmt:
                try:
                    cur.execute(stmt)
                except (pymysql.err.ProgrammingError, pymysql.err.OperationalError) as e:
                    errno = e.args[0] if e.args else None
                    if errno == 1061 and stmt.lstrip().upper().startswith("CREATE INDEX"):
                        continue
                    print(f"[init_db] WARNING: DDL skipped: {str(e)[:100]}")


def _connection_params() -> dict:
    """Return connection kwargs for pymysql.connect()."""
    return {
        "host": settings.MYSQL_HOST,
        "port": settings.MYSQL_PORT,
        "user": settings.MYSQL_USER,
        "password": settings.MYSQL_PASSWORD,
        "database": settings.MYSQL_DATABASE,
        "charset": "utf8mb4",
        "autocommit": False,
        "init_command": "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci",
    }


def _ensure_intelligent_budget_tasks(conn: pymysql.Connection) -> None:
    """Create the intelligent budget simulation task store during DB bootstrap."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS intelligent_budget_tasks (
                task_id VARCHAR(255) PRIMARY KEY,
                target_text VARCHAR(255) NOT NULL,
                parsed_target LONGTEXT NOT NULL,
                status VARCHAR(255) NOT NULL,
                stage VARCHAR(255) NOT NULL,
                step_summary LONGTEXT,
                baseline_solution LONGTEXT,
                solutions LONGTEXT NOT NULL,
                negotiation_message LONGTEXT,
                negotiation_suggestions LONGTEXT,
                created_at VARCHAR(255) NOT NULL DEFAULT (NOW())
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )


def _init_common_tables(conn: pymysql.Connection, calendar_year: int) -> None:
    _executescript(conn, COMMON_SCHEMA)
    ensure_department_expense_master_schema_sync(conn)
    ensure_expense_forecast_schema_sync(conn)
    ensure_bi_mapping_schema_sync(conn)
    ensure_expense_actual_import_schema_sync(conn)
    ensure_expense_budget_entry_schema_sync(conn)
    ensure_budget_output_display_item_schema_sync(conn)
    ensure_org_product_schema(conn)
    ensure_org_product_runtime_catalog_schema(conn)
    ensure_runtime_metric_identity_schema(conn)
    drop_retired_tables(conn)
    ensure_smart_report_schema_sync(conn)
    validate_generated_file_paths(conn, settings.data_dir)
    seed_periods(conn, calendar_year)
    ensure_runtime_metric_identity_tables(conn)
    _ensure_intelligent_budget_tasks(conn)
    normalize_org_product_metric_mapping_statuses(conn)
    sync_existing_org_product_metric_tables(conn)
    seed_default_smart_ppt(conn)
    now = _iso_now()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users(
              user_name, first_login_password, daily_login_password,
              permission_type, first_login_flag, create_time, update_time
            ) VALUES (%s, %s, %s, 1, 1, %s, %s)
            """,
            (settings.local_user_name, "Abc12345", None, now, now),
        )
    conn.commit()


def init_common_db(calendar_year: int) -> None:
    conn = _connect()
    try:
        _init_common_tables(conn, calendar_year)
    finally:
        conn.close()


def _init_budget_tables(conn: pymysql.Connection) -> None:
    _executescript(conn, BUDGET_SCHEMA)
    ensure_budget_version_schema_sync(conn)
    ensure_budget_data_update_time_triggers(conn)
    ensure_budget_read_model_schema(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM version")
        row = cur.fetchone()
        if row[0] == 0:
            now = _iso_now()
            cur.execute(
                "INSERT INTO version (budget_year, version_date_time, version_name, current_month) VALUES (%s, %s, %s, %s)",
                (settings.budget_year, now, "V2024.04.01", 1),
            )
    now = _iso_now()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT IGNORE INTO settings(budget_year, setting_key, setting_value) VALUES (%s, 'year', %s)",
            (settings.budget_year, str(settings.budget_year)),
        )
        cur.execute(
            "INSERT IGNORE INTO settings(budget_year, setting_key, setting_value) VALUES (%s, 'create_user', %s)",
            (settings.budget_year, settings.local_user_name),
        )
        cur.execute(
            "INSERT IGNORE INTO settings(budget_year, setting_key, setting_value) VALUES (%s, 'create_time', %s)",
            (settings.budget_year, now),
        )
    conn.commit()


def init_budget_db() -> None:
    conn = _connect()
    try:
        _init_budget_tables(conn)
    finally:
        conn.close()


def _init_compare_tables(conn: pymysql.Connection) -> None:
    _executescript(conn, COMPARE_SCHEMA)
    ensure_compare_read_model_schema(conn)
    conn.commit()


def init_compare_db() -> None:
    conn = _connect()
    try:
        _init_compare_tables(conn)
    finally:
        conn.close()


def ensure_databases() -> None:
    """Idempotent: create tables and core seed if missing."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
            """)
            has_users = cur.fetchone() is not None

        if not has_users:
            _init_common_tables(conn, settings.budget_year)
        else:
            _executescript(conn, COMMON_SCHEMA)
            ensure_department_expense_master_schema_sync(conn)
            ensure_expense_forecast_schema_sync(conn)
            ensure_bi_mapping_schema_sync(conn)
            ensure_expense_actual_import_schema_sync(conn)
            ensure_expense_budget_entry_schema_sync(conn)
            ensure_budget_output_display_item_schema_sync(conn)
            ensure_org_product_schema(conn)
            ensure_org_product_runtime_catalog_schema(conn)
            ensure_runtime_metric_identity_schema(conn)
            drop_retired_tables(conn)
            ensure_smart_report_schema_sync(conn)
            validate_generated_file_paths(conn, settings.data_dir)
            ensure_runtime_metric_identity_tables(conn)
            _ensure_intelligent_budget_tasks(conn)
            normalize_org_product_metric_mapping_statuses(conn)
            sync_existing_org_product_metric_tables(conn)
            seed_periods(conn, settings.budget_year)
            seed_default_smart_ppt(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM users")
                row = cur.fetchone()
                if int(row[0] or 0) == 0:
                    now = _iso_now()
                    cur.execute(
                        """
                        INSERT INTO users(
                          user_name, first_login_password, daily_login_password,
                          permission_type, first_login_flag, create_time, update_time
                        ) VALUES (%s, %s, %s, 1, 1, %s, %s)
                        """,
                        (settings.local_user_name, "Abc12345", None, now, now),
                    )
        conn.commit()
    finally:
        conn.close()

    # Budget tables (version, budget_data, budget_summary, budget_pivot_aggregate)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'version'
            """)
            has_version = cur.fetchone() is not None

        if not has_version:
            _init_budget_tables(conn)
        else:
            _executescript(conn, BUDGET_SCHEMA)
            now = _iso_now()
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM version")
                row = cur.fetchone()
                if row[0] == 0:
                    cur.execute(
                        "INSERT INTO version (budget_year, version_date_time, version_name, current_month) VALUES (%s, %s, %s, %s)",
                        (settings.budget_year, now, "V2024.04.01", 1),
                    )
            ensure_budget_version_schema_sync(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'budget_data'
                """)
                budget_data_cols = {str(r[0]) for r in cur.fetchall()}
            if budget_data_cols:
                ensure_budget_data_update_time_triggers(conn)
            ensure_budget_read_model_schema(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                      id INT AUTO_INCREMENT PRIMARY KEY,
                      budget_year INT NOT NULL,
                      setting_key VARCHAR(255) NOT NULL,
                      setting_value TEXT NOT NULL,
                      UNIQUE (budget_year, setting_key)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
            now = _iso_now()
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT IGNORE INTO settings(budget_year, setting_key, setting_value) VALUES (%s, 'year', %s)",
                    (settings.budget_year, str(settings.budget_year)),
                )
                cur.execute(
                    "INSERT IGNORE INTO settings(budget_year, setting_key, setting_value) VALUES (%s, 'create_user', %s)",
                    (settings.budget_year, settings.local_user_name),
                )
                cur.execute(
                    "INSERT IGNORE INTO settings(budget_year, setting_key, setting_value) VALUES (%s, 'create_time', %s)",
                    (settings.budget_year, now),
                )
            ensure_business_cost_income_schema_with_common(conn, None, settings.budget_year)
            conn.commit()
    finally:
        conn.close()

    sync_current_budget_registry(_connect, settings.budget_year)

    # Compare tables
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'compare_budget_summary'
            """)
            has_compare = cur.fetchone() is not None

        if not has_compare:
            _init_compare_tables(conn)
        else:
            _executescript(conn, COMPARE_SCHEMA)
            ensure_compare_read_model_schema(conn)
            conn.commit()
    finally:
        conn.close()

    # Post-init validation with common tables
    conn = _connect()
    try:
        normalize_legacy_corp_data_account_refs(conn)
        normalize_read_model_data_code_names(conn)
        # MySQL 运行态以迁移后的 data_account_metric_node 为准；不要在启动时 merge
        # 规范 .05 费用树（会重新写入 AA.05/A01.05 等已退休分支）。
        _purge_legacy_org_product_metric_branches(conn)
        from app.db_bootstrap.runtime_metric_tree import _sync_derived_metric_node_identity

        _sync_derived_metric_node_identity(conn)
        normalize_org_product_metric_mapping_statuses(conn)
        purge_legacy_corp_metric_master(conn)
        try:
            assert_all_runtime_metric_refs_are_confirmed_org_product_metrics(
                conn,
                budget_paths=conn,
                read_model_paths=conn,
            )
        except OrgProductMetricRuntimeSyncError as exc:
            logger.warning("org_product_runtime_ref_check_skipped_on_startup: %s", exc)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    ensure_databases()
    print("OK")
