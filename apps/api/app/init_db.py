"""Create SQLite files per Banking_Budget_Database_PDD.md."""
from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.db_bootstrap.budget_data import (
    ensure_budget_data_update_time_triggers,
    validate_budget_data_fact_table,
)
from app.db_bootstrap.budget_version import ensure_budget_version_schema_sync
from app.db_bootstrap.business_cost_income import (
    ensure_business_cost_income_schema_with_common,
)
from app.core.config import settings
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
from app.core.db_paths import budget_db_path, common_db_path, compare_db_path, list_budget_database_files
from app.routers.org_product_helpers import ensure_org_product_schema
from app.services.org_product_metric_runtime_sync import (
    OrgProductMetricRuntimeSyncError,
    assert_all_runtime_metric_refs_are_confirmed_org_product_metrics,
    merge_canonical_expense_metric_trees_into_org_product_metrics,
    normalize_legacy_corp_data_account_refs,
    normalize_org_product_metric_mapping_statuses,
    normalize_read_model_data_code_names,
    purge_legacy_corp_metric_master,
    sync_existing_org_product_metric_tables,
)

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def init_common_db(path: Path, calendar_year: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(COMMON_SCHEMA)
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
        normalize_org_product_metric_mapping_statuses(conn)
        sync_existing_org_product_metric_tables(conn)
        seed_default_smart_ppt(conn)
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
        ensure_budget_version_schema_sync(conn)
        ensure_budget_data_update_time_triggers(conn)
        ensure_budget_read_model_schema(conn)
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
        ensure_compare_read_model_schema(conn)
        conn.commit()
    finally:
        conn.close()

def ensure_databases() -> None:
    """Idempotent: create files and core seed if missing."""
    common = common_db_path()
    if not common.exists():
        init_common_db(common, settings.budget_year)
    else:
        conn = sqlite3.connect(common)
        try:
            conn.executescript(COMMON_SCHEMA)
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
            normalize_org_product_metric_mapping_statuses(conn)
            sync_existing_org_product_metric_tables(conn)
            seed_periods(conn, settings.budget_year)
            seed_default_smart_ppt(conn)
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
            ensure_budget_version_schema_sync(conn)
            cur = conn.execute("PRAGMA table_info(budget_data)")
            budget_data_cols = {str(r[1]) for r in cur.fetchall()}
            if budget_data_cols:
                ensure_budget_data_update_time_triggers(conn)
            ensure_budget_read_model_schema(conn)
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
            common_conn_for_bcir = sqlite3.connect(common)
            try:
                ensure_business_cost_income_schema_with_common(conn, common_conn_for_bcir)
            finally:
                common_conn_for_bcir.close()
            conn.commit()
        finally:
            conn.close()
    # Keep the current annual budget database registered for version selection.
    sync_current_budget_registry(common, budget, settings.budget_year)

    compare = compare_db_path()
    if not compare.exists():
        init_compare_db(compare)
    else:
        conn = sqlite3.connect(compare)
        try:
            conn.executescript(COMPARE_SCHEMA)
            ensure_compare_read_model_schema(conn)
            conn.commit()
        finally:
            conn.close()

    for budget_file in list_budget_database_files():
        conn = sqlite3.connect(budget_file)
        try:
            common_conn_for_bcir = sqlite3.connect(common)
            try:
                ensure_business_cost_income_schema_with_common(conn, common_conn_for_bcir)
            finally:
                common_conn_for_bcir.close()
            ensure_budget_read_model_schema(conn)
            conn.commit()
        finally:
            conn.close()
        validate_budget_data_fact_table(budget_file)

    conn = sqlite3.connect(common)
    try:
        budget_files = tuple(list_budget_database_files())
        read_model_files = budget_files + (compare,)
        normalize_legacy_corp_data_account_refs(budget_files)
        normalize_read_model_data_code_names(read_model_files)
        merge_canonical_expense_metric_trees_into_org_product_metrics(conn)
        normalize_org_product_metric_mapping_statuses(conn)
        purge_legacy_corp_metric_master(conn)
        try:
            assert_all_runtime_metric_refs_are_confirmed_org_product_metrics(
                conn,
                budget_paths=budget_files,
                read_model_paths=read_model_files,
            )
        except OrgProductMetricRuntimeSyncError as exc:
            logger.warning("org_product_runtime_ref_check_skipped_on_startup: %s", exc)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    ensure_databases()
    print("OK:", common_db_path(), budget_db_path(settings.budget_year), compare_db_path())
