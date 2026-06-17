from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "scripts" / "verify_current_database_inventory.py"

from scripts.verify_current_database_inventory import (
    business_data_account_ref_violations_by_database,
    canonical_expense_metric_tree_violations,
    direct_metric_identity_write_violations,
    direct_product_type_write_violations,
    legacy_second_segment_99_violations_by_database,
    derived_read_model_data_code_name_ref_violations_by_database,
    org_product_metric_guard_violations,
    retired_workspace_menu_violations,
    user_facing_data_account_label_violations,
)


class VerifyCurrentDatabaseInventoryScriptTests(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_prints_counts_and_succeeds_without_retired_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "current.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE current_fact(id INTEGER PRIMARY KEY);
                    INSERT INTO current_fact(id) VALUES (1), (2);
                    """
                )

            result = self.run_script("--db", str(db_path))

        self.assertEqual(result.returncode, 0)
        self.assertIn("current_fact|2", result.stdout)
        self.assertIn("retired_tables=none", result.stdout)

    def test_fails_when_retired_table_reappears(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "retired.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE report_account(id INTEGER PRIMARY KEY)")

            result = self.run_script("--db", str(db_path))

        self.assertEqual(result.returncode, 1)
        self.assertIn("retired_tables=found", result.stdout)
        self.assertIn("report_account", result.stdout)

    def test_missing_database_returns_operator_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_path = Path(tmp) / "missing.db"

            result = self.run_script("--db", str(missing_path))

        self.assertEqual(result.returncode, 2)
        self.assertIn("missing_db=", result.stderr)

    def test_retired_workspace_menu_detects_data_account_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "workspaceCatalog.tsx"
            catalog_path.write_text(
                '{ id: "data-account", label: "数据科目运行表" }\n',
                encoding="utf-8",
            )

            violations = retired_workspace_menu_violations(catalog_path)

        self.assertIn('retired_workspace_menu_marker:id: "data-account"', violations)
        self.assertIn("retired_workspace_menu_marker:数据科目运行表", violations)

    def test_retired_workspace_menu_detects_restored_data_account_frontend_files(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            retired_component = root / "apps/web/src/app/components/DataAccountContent.tsx"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            retired_component.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            retired_component.write_text("export function DataAccountContent() { return null; }\n", encoding="utf-8")

            original_files = inventory.RETIRED_DATA_ACCOUNT_FRONTEND_FILES
            try:
                inventory.RETIRED_DATA_ACCOUNT_FRONTEND_FILES = (retired_component,)
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.RETIRED_DATA_ACCOUNT_FRONTEND_FILES = original_files

        self.assertEqual(len(violations), 1)
        self.assertTrue(violations[0].startswith("retired_data_account_frontend_file_exists:"))
        self.assertTrue(violations[0].endswith("apps/web/src/app/components/DataAccountContent.tsx"))

    def test_retired_workspace_menu_detects_panpan99_endpoint_markers(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            source_path = root / "apps/api/app/routers/org_product_metrics.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            source_path.write_text('router.get("/api/org-product-metrics/panpan99-page")\n', encoding="utf-8")

            original_files = inventory.RETIRED_SOURCE_MARKER_FILES
            try:
                inventory.RETIRED_SOURCE_MARKER_FILES = (source_path,)
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.RETIRED_SOURCE_MARKER_FILES = original_files

        self.assertEqual(len(violations), 2)
        self.assertTrue(all(item.startswith("retired_panpan99_marker:") for item in violations))
        self.assertIn("panpan99-page", ";".join(violations))
        self.assertIn("/api/org-product-metrics/panpan99-page", ";".join(violations))

    def test_retired_workspace_menu_detects_runtime_backfill_markers(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            source_path = root / "apps/api/app/services/org_product_metric_runtime_sync.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            source_path.write_text(
                "def merge_data_account_runtime_rows_into_org_product_metrics():\n"
                "    return '由数据科目运行主键收回机构及产品指标主表'\n",
                encoding="utf-8",
            )

            original_files = inventory.RETIRED_SOURCE_MARKER_FILES
            try:
                inventory.RETIRED_SOURCE_MARKER_FILES = (source_path,)
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.RETIRED_SOURCE_MARKER_FILES = original_files

        self.assertEqual(len(violations), 2)
        self.assertTrue(all(item.startswith("retired_runtime_backfill_marker:") for item in violations))
        self.assertIn("merge_data_account_runtime_rows_into_org_product_metrics", ";".join(violations))
        self.assertIn("由数据科目运行主键收回机构及产品指标主表", ";".join(violations))

    def test_retired_workspace_menu_detects_agent_runtime_lexicon_reads(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            lexicon_path = root / "apps/api/app/services/agent_domain_lexicon.py"
            query_path = root / "apps/api/app/agent_query.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            lexicon_path.parent.mkdir(parents=True, exist_ok=True)
            query_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            lexicon_path.write_text(
                'CURRENT_ENTITY_SQLS = ("SELECT data_acct_code AS code, data_acct_name AS name FROM data_account",)\n',
                encoding="utf-8",
            )
            query_path.write_text(
                'sql = "SELECT data_acct_name, value_type FROM data_account"\n',
                encoding="utf-8",
            )

            original_lexicon_path = inventory.DEFAULT_AGENT_DOMAIN_LEXICON_SERVICE
            original_query_path = inventory.DEFAULT_AGENT_QUERY_SERVICE
            try:
                inventory.DEFAULT_AGENT_DOMAIN_LEXICON_SERVICE = lexicon_path
                inventory.DEFAULT_AGENT_QUERY_SERVICE = query_path
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.DEFAULT_AGENT_DOMAIN_LEXICON_SERVICE = original_lexicon_path
                inventory.DEFAULT_AGENT_QUERY_SERVICE = original_query_path

        self.assertGreaterEqual(len(violations), 2)
        self.assertTrue(all(item.startswith("retired_agent_runtime_lexicon_marker:") for item in violations))
        self.assertIn("SELECT data_acct_code AS code", ";".join(violations))
        self.assertIn("agent_query.py", ";".join(violations))

    def test_retired_workspace_menu_detects_runtime_candidate_sources(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            display_path = root / "apps/api/app/services/budget_output_display.py"
            config_path = root / "apps/api/app/services/budget_output_display_config.py"
            import_path = root / "apps/api/app/services/budget_display_config_import.py"
            smart_report_path = root / "apps/api/app/services/smart_report_service.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            display_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            display_path.write_text(
                "from app.services.runtime_metric_refs import load_confirmed_org_product_runtime_ref_codes\n"
                "sql = \"SELECT 'data_account:' || d.data_acct_code, 'data_account' AS source_type FROM data_account d\"\n",
                encoding="utf-8",
            )
            config_path.write_text(
                "from app.services.runtime_metric_refs import load_confirmed_org_product_runtime_ref_codes\n",
                encoding="utf-8",
            )
            import_path.write_text(
                "from app.services.runtime_metric_refs import load_confirmed_org_product_runtime_ref_codes\n",
                encoding="utf-8",
            )
            smart_report_path.write_text(
                "sql = 'SELECT d.data_acct_code FROM data_account d'\n",
                encoding="utf-8",
            )

            original_files = inventory.REQUIRED_CONFIRMED_ORG_PRODUCT_CANDIDATE_FILES
            try:
                inventory.REQUIRED_CONFIRMED_ORG_PRODUCT_CANDIDATE_FILES = (
                    display_path,
                    config_path,
                    import_path,
                    smart_report_path,
                )
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.REQUIRED_CONFIRMED_ORG_PRODUCT_CANDIDATE_FILES = original_files

        self.assertIn("retired_runtime_candidate_source_marker", ";".join(violations))
        self.assertIn("missing_confirmed_org_product_candidate_guard", ";".join(violations))
        self.assertIn("smart_report_service.py", ";".join(violations))

    def test_retired_workspace_menu_detects_missing_org_product_ref_guard(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            workflow_path = root / "apps/api/app/services/expense_forecast_rule_import_workflow.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            workflow_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            workflow_path.write_text("def resolve_org_product_variables(): pass\n", encoding="utf-8")

            original_markers = inventory.REQUIRED_CONFIRMED_ORG_PRODUCT_REF_MARKERS
            try:
                inventory.REQUIRED_CONFIRMED_ORG_PRODUCT_REF_MARKERS = (
                    (workflow_path, "机构及产品指标编码未在机构产品指标中确认"),
                )
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.REQUIRED_CONFIRMED_ORG_PRODUCT_REF_MARKERS = original_markers

        self.assertIn("missing_confirmed_org_product_ref_guard", ";".join(violations))
        self.assertIn("expense_forecast_rule_import_workflow.py", ";".join(violations))

    def test_user_facing_data_account_label_scan_blocks_old_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "AgentPrompt.md"
            ok_path = Path(tmp) / "RuntimeRefPrompt.md"
            bad_path.write_text("请在数据科目中选择具体 code，并使用标准指标树。", encoding="utf-8")
            ok_path.write_text("请在机构及产品指标运行引用中选择具体 code。", encoding="utf-8")

            violations = user_facing_data_account_label_violations((bad_path, ok_path))

        self.assertEqual(len(violations), 2)
        self.assertIn("retired_user_facing_data_account_label:", violations[0])
        self.assertIn("数据科目", ";".join(violations))
        self.assertIn("标准指标树", ";".join(violations))
        self.assertNotIn(str(ok_path), ";".join(violations))

    def test_retired_workspace_menu_detects_runtime_ref_export_api_names(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            export_path = root / "apps/api/app/services/runtime_ref_export.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            export_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            export_path.write_text(
                "async def build_data_account_export_workbook(): pass\n"
                "async def export_data_accounts_workbook(): pass\n",
                encoding="utf-8",
            )

            original_root = inventory.REPO_ROOT
            try:
                inventory.REPO_ROOT = root
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.REPO_ROOT = original_root

        self.assertEqual(len(violations), 2)
        self.assertTrue(all(item.startswith("retired_runtime_ref_export_api_marker:") for item in violations))
        self.assertIn("build_data_account_export_workbook", ";".join(violations))
        self.assertIn("export_data_accounts_workbook", ";".join(violations))

    def test_retired_workspace_menu_detects_restored_data_account_service_files(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            usage_path = root / "apps/api/app/services/data_account_usage.py"
            export_path = root / "apps/api/app/services/data_account_export.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            usage_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            usage_path.write_text("# retired\n", encoding="utf-8")
            export_path.write_text("# retired\n", encoding="utf-8")

            original_files = inventory.RETIRED_DATA_ACCOUNT_SERVICE_FILES
            try:
                inventory.RETIRED_DATA_ACCOUNT_SERVICE_FILES = (usage_path, export_path)
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.RETIRED_DATA_ACCOUNT_SERVICE_FILES = original_files

        self.assertEqual(len(violations), 2)
        self.assertTrue(all(item.startswith("retired_data_account_service_file_exists:") for item in violations))
        self.assertIn("data_account_usage.py", ";".join(violations))
        self.assertIn("data_account_export.py", ";".join(violations))

    def test_retired_workspace_menu_detects_runtime_metric_refs_api_names(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            schema_path = root / "apps/api/app/schemas.py"
            usage_path = root / "apps/api/app/services/runtime_metric_refs.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            schema_path.parent.mkdir(parents=True, exist_ok=True)
            usage_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            schema_path.write_text("class DataAccountRow: pass\n", encoding="utf-8")
            usage_path.write_text(
                "def row_to_account(): pass\n"
                "def fetch_account_detail(): pass\n"
                "def fetch_account_list(): pass\n"
                "def list_data_accounts(): pass\n",
                encoding="utf-8",
            )

            original_root = inventory.REPO_ROOT
            try:
                inventory.REPO_ROOT = root
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.REPO_ROOT = original_root

        self.assertEqual(len(violations), 5)
        self.assertTrue(all(item.startswith("retired_runtime_metric_refs_api_marker:") for item in violations))
        self.assertIn("DataAccountRow", ";".join(violations))
        self.assertIn("row_to_account", ";".join(violations))
        self.assertIn("fetch_account_detail", ";".join(violations))
        self.assertIn("fetch_account_list", ";".join(violations))
        self.assertIn("list_data_accounts", ";".join(violations))

    def test_retired_workspace_menu_detects_runtime_ref_naming_regressions(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            chart_path = root / "apps/api/app/services/chart_data.py"
            display_path = root / "apps/api/app/services/budget_display_structure.py"
            simulation_path = root / "apps/api/app/services/budget_simulation_metrics.py"
            export_path = root / "apps/api/app/services/budget_output_export.py"
            writer_path = root / "apps/api/app/budget_data_writer.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            chart_path.parent.mkdir(parents=True, exist_ok=True)
            display_path.parent.mkdir(parents=True, exist_ok=True)
            simulation_path.parent.mkdir(parents=True, exist_ok=True)
            export_path.parent.mkdir(parents=True, exist_ok=True)
            writer_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            chart_path.write_text(
                "DataAccountCodeExtractor = object\n"
                "extract_data_acct_code_from_name = None\n",
                encoding="utf-8",
            )
            display_path.write_text(
                "async def clear_budget_display_data_account_binding(): pass\n",
                encoding="utf-8",
            )
            simulation_path.write_text(
                "def resolve_metric_data_acct_codes(): pass\n"
                "async def load_data_metric_bindings(): pass\n",
                encoding="utf-8",
            )
            export_path.write_text(
                "def _excel_data_account_formula(): pass\n"
                "data_acct_row_numbers = {}\n",
                encoding="utf-8",
            )
            runtime_refs_path = root / "apps/api/app/services/runtime_metric_refs.py"
            runtime_refs_path.write_text(
                "async def load_org_product_metric_refs_by_data_acct_code(): pass\n"
                "async def load_confirmed_org_product_data_acct_codes(): pass\n"
                "refs_by_data_acct_code = {}\n",
                encoding="utf-8",
            )
            writer_path.write_text(
                "async def delete_budget_data_for_data_account(): pass\n"
                "allow_formula_accounts = True\n",
                encoding="utf-8",
            )

            original_files = inventory.RUNTIME_REF_NAMING_GUARD_FILES
            try:
                inventory.RUNTIME_REF_NAMING_GUARD_FILES = (
                    chart_path,
                    display_path,
                    simulation_path,
                    export_path,
                    runtime_refs_path,
                    writer_path,
                )
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.RUNTIME_REF_NAMING_GUARD_FILES = original_files

        self.assertEqual(len(violations), 13)
        self.assertTrue(all(item.startswith("retired_runtime_ref_naming_marker:") for item in violations))
        self.assertIn("DataAccountCodeExtractor", ";".join(violations))
        self.assertIn("extract_data_acct_code_from_name", ";".join(violations))
        self.assertIn("clear_budget_display_data_account_binding", ";".join(violations))
        self.assertIn("resolve_metric_data_acct_codes", ";".join(violations))
        self.assertIn("load_data_metric_bindings", ";".join(violations))
        self.assertIn("_excel_data_account_formula", ";".join(violations))
        self.assertIn("data_acct_row_numbers", ";".join(violations))
        self.assertIn("load_org_product_metric_refs_by_data_acct_code", ";".join(violations))
        self.assertIn("load_confirmed_org_product_data_acct_codes", ";".join(violations))
        self.assertIn("refs_by_data_acct_code", ";".join(violations))
        self.assertIn("delete_budget_data_for_data_account", ";".join(violations))
        self.assertIn("allow_formula_accounts", ";".join(violations))
        self.assertIn("formula_accounts", ";".join(violations))

    def test_retired_workspace_menu_detects_framework_master_data_account_writes(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            source_path = root / "apps/api/app/services/expense_budget_execution_master_sync.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            source_path.write_text(
                "data_account_upserts = []\n"
                "sql = 'INSERT INTO data_account(data_acct_code) VALUES (?)'\n",
                encoding="utf-8",
            )

            original_path = inventory.DEFAULT_EXPENSE_MASTER_SYNC_SERVICE
            try:
                inventory.DEFAULT_EXPENSE_MASTER_SYNC_SERVICE = source_path
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.DEFAULT_EXPENSE_MASTER_SYNC_SERVICE = original_path

        self.assertEqual(len(violations), 2)
        self.assertTrue(all(item.startswith("retired_framework_master_write_marker:") for item in violations))
        self.assertIn("data_account_upserts", ";".join(violations))
        self.assertIn("INSERT INTO data_account", ";".join(violations))

    def test_direct_metric_identity_write_scan_allows_only_org_product_runtime_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "app"
            allowed_path = root / "services/org_product_metric_runtime_sync.py"
            rogue_path = root / "services/rogue_metric_writer.py"
            allowed_path.parent.mkdir(parents=True, exist_ok=True)
            allowed_path.write_text("sql = 'INSERT INTO data_account(data_acct_code) VALUES (?)'\n", encoding="utf-8")
            rogue_path.write_text("sql = 'DELETE FROM data_account_metric_binding WHERE data_acct_code=?'\n", encoding="utf-8")

            violations = direct_metric_identity_write_violations(
                root,
                allowed_files=frozenset({allowed_path}),
            )

        self.assertEqual(len(violations), 1)
        self.assertIn("direct_metric_identity_write:", violations[0])
        self.assertIn("rogue_metric_writer.py", violations[0])
        self.assertIn("DELETE FROM data_account_metric_binding", violations[0])

    def test_direct_product_type_write_scan_allows_only_retired_object_drop_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "app"
            allowed_path = root / "services/org_product_runtime_catalog.py"
            rogue_path = root / "services/rogue_product_writer.py"
            allowed_path.parent.mkdir(parents=True, exist_ok=True)
            allowed_path.write_text(
                "conn.execute('DROP TABLE product_type')\n"
                "conn.execute('DROP VIEW product_type')\n",
                encoding="utf-8",
            )
            rogue_path.write_text(
                "sql = 'CREATE TABLE product_type(product_code TEXT PRIMARY KEY)'\n",
                encoding="utf-8",
            )

            violations = direct_product_type_write_violations(
                root,
                allowed_files=frozenset({allowed_path}),
            )

        self.assertEqual(len(violations), 1)
        self.assertIn("direct_product_type_write:", violations[0])
        self.assertIn("rogue_product_writer.py", violations[0])
        self.assertIn("CREATE TABLE product_type", violations[0])

    def test_retired_workspace_menu_detects_metric_tree_rollup_data_account_writes(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            source_path = root / "apps/api/app/services/metric_tree_rollups.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            source_path.write_text(
                "from app.data_account_identity import official_metric_account_code\n"
                "sql = 'UPDATE data_account SET allow_manual_entry = 0'\n",
                encoding="utf-8",
            )

            original_path = inventory.DEFAULT_METRIC_TREE_ROLLUPS_SERVICE
            try:
                inventory.DEFAULT_METRIC_TREE_ROLLUPS_SERVICE = source_path
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.DEFAULT_METRIC_TREE_ROLLUPS_SERVICE = original_path

        self.assertEqual(len(violations), 2)
        self.assertTrue(all(item.startswith("retired_metric_tree_rollup_write_marker:") for item in violations))
        self.assertIn("official_metric_account_code", ";".join(violations))
        self.assertIn("UPDATE data_account", ";".join(violations))

    def test_retired_workspace_menu_detects_restored_data_account_identity_file(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            identity_path = root / "apps/api/app/data_account_identity.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            identity_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            identity_path.write_text("# retired\n", encoding="utf-8")

            original_files = inventory.RETIRED_DATA_ACCOUNT_IDENTITY_FILES
            try:
                inventory.RETIRED_DATA_ACCOUNT_IDENTITY_FILES = (identity_path,)
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.RETIRED_DATA_ACCOUNT_IDENTITY_FILES = original_files

        self.assertEqual(len(violations), 1)
        self.assertTrue(violations[0].startswith("retired_data_account_identity_file_exists:"))
        self.assertIn("data_account_identity.py", violations[0])

    def test_retired_workspace_menu_detects_restored_data_account_metric_modules(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            tree_path = root / "apps/api/app/db_bootstrap/data_account_metric_tree.py"
            rollup_path = root / "apps/api/app/services/data_account_rollup_formulas.py"
            paths_path = root / "apps/api/app/services/data_account_runtime_paths.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            tree_path.parent.mkdir(parents=True, exist_ok=True)
            rollup_path.parent.mkdir(parents=True, exist_ok=True)
            paths_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            tree_path.write_text("# retired\n", encoding="utf-8")
            rollup_path.write_text("# retired\n", encoding="utf-8")
            paths_path.write_text("# retired\n", encoding="utf-8")

            original_files = inventory.RETIRED_DATA_ACCOUNT_METRIC_MODULE_FILES
            try:
                inventory.RETIRED_DATA_ACCOUNT_METRIC_MODULE_FILES = (tree_path, rollup_path, paths_path)
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.RETIRED_DATA_ACCOUNT_METRIC_MODULE_FILES = original_files

        self.assertEqual(len(violations), 3)
        self.assertTrue(all(item.startswith("retired_data_account_metric_module_file_exists:") for item in violations))
        self.assertIn("data_account_metric_tree.py", ";".join(violations))
        self.assertIn("data_account_rollup_formulas.py", ";".join(violations))
        self.assertIn("data_account_runtime_paths.py", ";".join(violations))

    def test_retired_workspace_menu_detects_formula_data_account_api_names(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            formula_path = root / "apps/api/app/formula_refs.py"
            engine_path = root / "apps/api/app/services/formula_engine.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            formula_path.parent.mkdir(parents=True, exist_ok=True)
            engine_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            formula_path.write_text(
                "OFFICIAL_DATA_ACCOUNT_CODE = 'A01.01.001'\n"
                "DATA_ACCOUNT_CODE_RE = object()\n"
                "ANGLE_DATA_ACCOUNT_CODE_RE = object()\n"
                "def extract_data_account_code(text): pass\n",
                encoding="utf-8",
            )
            engine_path.write_text("async def load_data_account_scope_map(db): pass\n", encoding="utf-8")

            original_files = inventory.FORMULA_RUNTIME_REF_API_FILES
            try:
                inventory.FORMULA_RUNTIME_REF_API_FILES = (formula_path, engine_path)
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.FORMULA_RUNTIME_REF_API_FILES = original_files

        self.assertEqual(len(violations), 5)
        self.assertTrue(all(item.startswith("retired_formula_data_account_api_marker:") for item in violations))
        self.assertIn("OFFICIAL_DATA_ACCOUNT_CODE", ";".join(violations))
        self.assertIn("DATA_ACCOUNT_CODE_RE", ";".join(violations))
        self.assertIn("ANGLE_DATA_ACCOUNT_CODE_RE", ";".join(violations))
        self.assertIn("extract_data_account_code", ";".join(violations))
        self.assertIn("load_data_account_scope_map", ";".join(violations))

    def test_retired_workspace_menu_detects_restored_direct_metric_restructure_scripts(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            script_path = root / "apps/api/scripts/restructure_business_admin_expense_metric_tree.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            script_path.write_text("conn.execute('INSERT INTO data_account VALUES (?, ?)')\n", encoding="utf-8")

            original_scripts = inventory.RETIRED_DIRECT_METRIC_RESTRUCTURE_SCRIPTS
            try:
                inventory.RETIRED_DIRECT_METRIC_RESTRUCTURE_SCRIPTS = (script_path,)
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.RETIRED_DIRECT_METRIC_RESTRUCTURE_SCRIPTS = original_scripts

        self.assertEqual(len(violations), 1)
        self.assertTrue(violations[0].startswith("retired_direct_metric_restructure_script_exists:"))
        self.assertTrue(violations[0].endswith("apps/api/scripts/restructure_business_admin_expense_metric_tree.py"))

    def test_retired_workspace_menu_detects_restored_projection_bootstrap_module(self) -> None:
        from scripts import verify_current_database_inventory as inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_path = root / "apps/web/src/app/workspaceCatalog.tsx"
            projection_path = root / "apps/api/app/db_bootstrap/projections.py"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            projection_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_text('{ id: "org-product-metrics", label: "机构及产品指标" }\n', encoding="utf-8")
            projection_path.write_text('"""old projection bootstrap"""\n', encoding="utf-8")

            original_path = inventory.DEFAULT_RETIRED_PROJECTIONS_BOOTSTRAP
            try:
                inventory.DEFAULT_RETIRED_PROJECTIONS_BOOTSTRAP = projection_path
                violations = retired_workspace_menu_violations(catalog_path)
            finally:
                inventory.DEFAULT_RETIRED_PROJECTIONS_BOOTSTRAP = original_path

        self.assertEqual(len(violations), 1)
        self.assertTrue(violations[0].startswith("retired_projection_bootstrap_exists:"))
        self.assertTrue(violations[0].endswith("apps/api/app/db_bootstrap/projections.py"))

    def test_retired_workspace_menu_detects_product_account_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "workspaceCatalog.tsx"
            catalog_path.write_text(
                'import { DataProductContent } from "./components/DataProductContent";\n'
                '{ id: "data-product", label: "产品科目维护", render: () => <DataProductContent /> }\n',
                encoding="utf-8",
            )

            violations = retired_workspace_menu_violations(catalog_path)

        self.assertIn('retired_product_workspace_marker:id: "data-product"', violations)
        self.assertIn('retired_product_workspace_marker:label: "产品科目维护"', violations)
        self.assertIn("retired_product_workspace_marker:DataProductContent", violations)

    def test_retired_workspace_menu_allows_org_product_only_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "workspaceCatalog.tsx"
            catalog_path.write_text(
                '{ id: "org-product-metrics", label: "机构及产品指标" }\n',
                encoding="utf-8",
            )

            violations = retired_workspace_menu_violations(catalog_path)

        self.assertEqual(violations, ())

    def test_fails_when_table_is_missing_from_inventory_doc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "current.db"
            doc_path = Path(tmp) / "inventory.md"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE current_fact(id INTEGER PRIMARY KEY)")
            doc_path.write_text("current tables\n", encoding="utf-8")

            result = self.run_script("--db", str(db_path), "--inventory-doc", str(doc_path))

        self.assertEqual(result.returncode, 1)
        self.assertIn("inventory_doc=missing_tables", result.stdout)
        self.assertIn("current_fact", result.stdout)

    def test_inventory_doc_check_succeeds_when_all_tables_have_owner_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "current.db"
            doc_path = Path(tmp) / "inventory.md"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE current_fact(id INTEGER PRIMARY KEY)")
            doc_path.write_text(
                "| Module | Tables | Current row counts |\n"
                "| --- | --- | --- |\n"
                "| Current module | `current_fact` | 0 |\n",
                encoding="utf-8",
            )

            result = self.run_script("--db", str(db_path), "--inventory-doc", str(doc_path))

        self.assertEqual(result.returncode, 0)
        self.assertIn("inventory_doc=ok", result.stdout)
        self.assertIn("inventory_owner_doc=ok", result.stdout)
        self.assertIn("metric_identity_contract=ok", result.stdout)

    def test_metric_identity_contract_succeeds_for_product_prefixed_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "current.db"
            doc_path = Path(tmp) / "inventory.md"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account (
                      data_acct_code TEXT PRIMARY KEY NOT NULL,
                      data_acct_name TEXT NOT NULL,
                      value_type TEXT NOT NULL
                    );
                    CREATE TABLE data_account_metric_node (
                      node_code TEXT PRIMARY KEY NOT NULL,
                      node_name TEXT NOT NULL,
                      parent_code TEXT REFERENCES data_account_metric_node(node_code),
                      product_code TEXT,
                      local_metric_code TEXT,
                      logic_code TEXT DEFAULT '',
                      functional_group_code TEXT,
                      horizontal_rollup INTEGER DEFAULT 0,
                      vertical_rollup INTEGER DEFAULT 0,
                      runtime_account_enabled INTEGER DEFAULT 0,
                      value_type TEXT DEFAULT '',
                      level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 8),
                      node_type TEXT NOT NULL CHECK (node_type IN ('CATEGORY', 'GROUP', 'METRIC')),
                      metric_rollup_method TEXT NOT NULL DEFAULT 'NONE' CHECK (metric_rollup_method IN ('SUM', 'FORMULA', 'NONE')),
                      sort_order INTEGER NOT NULL DEFAULT 0,
                      is_active INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE TABLE _data_account_metric_binding (
                      data_acct_code TEXT PRIMARY KEY NOT NULL REFERENCES data_account(data_acct_code),
                      metric_node_code TEXT NOT NULL REFERENCES data_account_metric_node(node_code),
                      scope_type TEXT NOT NULL CHECK (scope_type IN ('PRODUCT', 'CORP')),
                      scope_code TEXT NOT NULL,
                      sort_order INTEGER NOT NULL DEFAULT 0,
                      is_active INTEGER NOT NULL DEFAULT 1,
                      UNIQUE (metric_node_code, scope_code),
                      CHECK (data_acct_code = metric_node_code),
                      CHECK (scope_code = SUBSTR(metric_node_code, 1, INSTR(metric_node_code, '.') - 1)),
                      CHECK (
                        (scope_type = 'CORP' AND scope_code = 'CORP')
                        OR (scope_type = 'PRODUCT' AND scope_code <> 'CORP')
                      )
                    );
                    CREATE VIEW data_account_metric_binding AS SELECT * FROM _data_account_metric_binding;
                    INSERT INTO data_account VALUES ('A01.01.01.001', '产品指标', '金额');
                    INSERT INTO data_account_metric_node
                      (node_code, node_name, parent_code, product_code, local_metric_code, logic_code, level, node_type)
                    VALUES
                      ('A01', '产品', NULL, 'A01', '', '', 1, 'CATEGORY'),
                      ('A01.01.01.001', '产品指标', 'A01', 'A01', '01.01.001', '01.01.001', 4, 'METRIC');
                    INSERT INTO _data_account_metric_binding
                      (data_acct_code, metric_node_code, scope_type, scope_code)
                    VALUES ('A01.01.01.001', 'A01.01.01.001', 'PRODUCT', 'A01');
                    """
                )
            doc_path.write_text(
                "| Module | Tables | Current row counts |\n"
                "| --- | --- | --- |\n"
                "| 机构产品指标运行引用 | `data_account`, `_data_account_metric_binding`, `data_account_metric_node` | 1, 1, 2 |\n",
                encoding="utf-8",
            )

            result = self.run_script("--db", str(db_path), "--inventory-doc", str(doc_path))

        self.assertEqual(result.returncode, 0)
        self.assertIn("metric_identity_contract=ok", result.stdout)

    def test_org_product_metric_runtime_refs_fail_when_not_materialized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "current.db"
            doc_path = Path(tmp) / "inventory.md"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account (
                      data_acct_code TEXT PRIMARY KEY NOT NULL,
                      data_acct_name TEXT NOT NULL,
                      value_type TEXT NOT NULL
                    );
                    CREATE TABLE data_account_metric_node (
                      node_code TEXT PRIMARY KEY NOT NULL,
                      node_name TEXT NOT NULL,
                      parent_code TEXT REFERENCES data_account_metric_node(node_code),
                      product_code TEXT,
                      local_metric_code TEXT,
                      logic_code TEXT DEFAULT '',
                      functional_group_code TEXT,
                      horizontal_rollup INTEGER DEFAULT 0,
                      vertical_rollup INTEGER DEFAULT 0,
                      runtime_account_enabled INTEGER DEFAULT 0,
                      value_type TEXT DEFAULT '',
                      level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 8),
                      node_type TEXT NOT NULL CHECK (node_type IN ('CATEGORY', 'GROUP', 'METRIC')),
                      metric_rollup_method TEXT NOT NULL DEFAULT 'NONE' CHECK (metric_rollup_method IN ('SUM', 'FORMULA', 'NONE')),
                      sort_order INTEGER NOT NULL DEFAULT 0,
                      is_active INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE TABLE _data_account_metric_binding (
                      data_acct_code TEXT PRIMARY KEY NOT NULL REFERENCES data_account(data_acct_code),
                      metric_node_code TEXT NOT NULL REFERENCES data_account_metric_node(node_code),
                      scope_type TEXT NOT NULL CHECK (scope_type IN ('PRODUCT', 'CORP')),
                      scope_code TEXT NOT NULL,
                      sort_order INTEGER NOT NULL DEFAULT 0,
                      is_active INTEGER NOT NULL DEFAULT 1,
                      UNIQUE (metric_node_code, scope_code),
                      CHECK (data_acct_code = metric_node_code),
                      CHECK (scope_code = SUBSTR(metric_node_code, 1, INSTR(metric_node_code, '.') - 1)),
                      CHECK (
                        (scope_type = 'CORP' AND scope_code = 'CORP')
                        OR (scope_type = 'PRODUCT' AND scope_code <> 'CORP')
                      )
                    );
                    CREATE VIEW data_account_metric_binding AS SELECT * FROM _data_account_metric_binding;
                    CREATE TABLE org_product_metric_table (
                      entity_code TEXT NOT NULL,
                      entity_name TEXT NOT NULL,
                      table_id TEXT NOT NULL,
                      table_name TEXT NOT NULL,
                      payload_json TEXT NOT NULL,
                      updated_at TEXT NOT NULL,
                      PRIMARY KEY(entity_code, table_name)
                    );
                    INSERT INTO org_product_metric_table
                      (entity_code, entity_name, table_id, table_name, payload_json, updated_at)
                    VALUES
                      ('A01', '产品A', 'table-main', '业务状况表',
                       '{"metrics":[{"code":"A010101","name":"利息收入"}]}',
                       '2026-06-10T00:00:00Z');
                    """
                )
            doc_path.write_text(
                "| Module | Tables | Current row counts |\n"
                "| --- | --- | --- |\n"
                "| 机构产品指标运行引用 | `data_account`, `_data_account_metric_binding`, `data_account_metric_node` | 0, 0, 0 |\n"
                "| 机构产品指标树体系 | `org_product_metric_table` | 1 |\n",
                encoding="utf-8",
            )

            result = self.run_script("--db", str(db_path), "--inventory-doc", str(doc_path))

        self.assertEqual(result.returncode, 1)
        self.assertIn("org_product_metric_runtime_refs=failed", result.stdout)
        self.assertIn("org_product_ref_missing_metric_node:A01/业务状况表/A010101/A01.01.01/A01.01.01", result.stdout)
        self.assertIn("org_product_ref_missing_data_account:A01/业务状况表/A010101/A01.01.01/A01.01.01", result.stdout)

    def test_org_product_metric_guard_allows_empty_mapping_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE org_product_metric_table (
                      entity_code TEXT NOT NULL,
                      entity_name TEXT NOT NULL,
                      table_id TEXT NOT NULL,
                      table_name TEXT NOT NULL,
                      payload_json TEXT NOT NULL,
                      updated_at TEXT NOT NULL,
                      PRIMARY KEY(entity_code, table_name)
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO org_product_metric_table
                    (entity_code, entity_name, table_id, table_name, payload_json, updated_at)
                    VALUES ('AA', '微众银行', 'table-main', '业务状况表',
                            '{"metrics":[{"code":"AA01N04","name":"新二级指标","mapping_status":"","metric_node_code":"","data_acct_code":""}]}',
                            '2026-06-10T00:00:00Z')
                    """
                )

            violations = org_product_metric_guard_violations(db_path)

        self.assertEqual(violations, ())

    def test_business_data_account_refs_must_point_to_confirmed_org_product_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            budget_path = Path(tmp) / "budget_2026.db"
            with sqlite3.connect(common_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account (
                      data_acct_code TEXT PRIMARY KEY NOT NULL,
                      data_acct_name TEXT NOT NULL,
                      value_type TEXT NOT NULL
                    );
                    CREATE TABLE org_product_metric_table (
                      entity_code TEXT NOT NULL,
                      entity_name TEXT NOT NULL,
                      table_id TEXT NOT NULL,
                      table_name TEXT NOT NULL,
                      payload_json TEXT NOT NULL,
                      updated_at TEXT NOT NULL,
                      PRIMARY KEY(entity_code, table_name)
                    );
                    INSERT INTO data_account VALUES ('A01.01.01.01', '测试指标', '金额');
                    INSERT INTO org_product_metric_table
                    (entity_code, entity_name, table_id, table_name, payload_json, updated_at)
                    VALUES ('A01', '产品A', 'table-main', '业务状况表',
                            '{"metrics":[{"code":"A010101","name":"利息收入"}]}',
                            '2026-06-10T00:00:00Z');
                    """
                )
            with sqlite3.connect(budget_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE budget_data (
                      data_acct_code TEXT NOT NULL,
                      product_code TEXT NOT NULL,
                      period_id INTEGER NOT NULL,
                      budget_actual INTEGER NOT NULL,
                      version_id INTEGER NOT NULL,
                      value REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO budget_data
                    (data_acct_code, product_code, period_id, budget_actual, version_id, value)
                    VALUES ('A01.99.01', 'A01', 4, 0, 1, 100)
                    """
                )

            violations = business_data_account_ref_violations_by_database((common_path, budget_path))

        self.assertEqual(
            violations,
            {budget_path: ("budget_data.data_acct_code:A01.99.01",)},
        )

    def test_derived_read_model_data_code_names_must_point_to_confirmed_org_product_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            compare_path = Path(tmp) / "compare.db"
            with sqlite3.connect(common_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account (
                      data_acct_code TEXT PRIMARY KEY NOT NULL,
                      data_acct_name TEXT NOT NULL,
                      value_type TEXT NOT NULL
                    );
                    CREATE TABLE org_product_metric_table (
                      entity_code TEXT NOT NULL,
                      entity_name TEXT NOT NULL,
                      table_id TEXT NOT NULL,
                      table_name TEXT NOT NULL,
                      payload_json TEXT NOT NULL,
                      updated_at TEXT NOT NULL,
                      PRIMARY KEY(entity_code, table_name)
                    );
                    INSERT INTO data_account VALUES ('AA.01.01', '测试指标', '金额');
                    INSERT INTO org_product_metric_table
                    (entity_code, entity_name, table_id, table_name, payload_json, updated_at)
                    VALUES ('AA', '微众银行', 'table-main', '业务状况表',
                            '{"metrics":[{"code":"AA0101","name":"利息收入"}]}',
                            '2026-06-10T00:00:00Z');
                    """
                )
            with sqlite3.connect(compare_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE compare_budget_summary (
                      data_code_name TEXT NOT NULL,
                      value REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO compare_budget_summary VALUES ('CORP.01.01 旧全行利息收入', 100)"
                )
                conn.execute(
                    "INSERT INTO compare_budget_summary VALUES ('AA.99.01 未确认指标', 200)"
                )

            violations = derived_read_model_data_code_name_ref_violations_by_database((common_path, compare_path))

        self.assertEqual(
            violations,
            {
                compare_path: (
                    "compare_budget_summary.data_code_name:AA.99.01",
                    "compare_budget_summary.data_code_name:legacy_corp:CORP.01.01",
                )
            },
        )

    def test_legacy_second_segment_99_is_rejected_across_runtime_and_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            budget_path = Path(tmp) / "budget_2026.db"
            compare_path = Path(tmp) / "compare.db"
            with sqlite3.connect(common_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account(data_acct_code TEXT, data_acct_name TEXT);
                    CREATE TABLE data_account_metric_node(node_code TEXT, node_name TEXT);
                    CREATE TABLE org_product_metric_table(
                      entity_code TEXT NOT NULL,
                      table_name TEXT NOT NULL,
                      payload_json TEXT NOT NULL
                    );
                    INSERT INTO data_account VALUES ('A01.99.01', '旧保护科目');
                    INSERT INTO data_account_metric_node VALUES ('A01.99.01', '旧保护节点');
                    INSERT INTO org_product_metric_table
                    VALUES (
                      'A01',
                      '业务状况表',
                      '{"metrics":[{"code":"A019901","mapping_status":"MANUAL_CONFIRMED","metric_node_code":"A01.99.01","data_acct_code":"A01.99.01"}]}'
                    );
                    """
                )
            with sqlite3.connect(budget_path) as conn:
                conn.execute("CREATE TABLE budget_data(data_acct_code TEXT)")
                conn.execute("INSERT INTO budget_data VALUES ('A01.99.01')")
            with sqlite3.connect(compare_path) as conn:
                conn.execute("CREATE TABLE compare_budget_summary(data_code_name TEXT)")
                conn.execute("INSERT INTO compare_budget_summary VALUES ('A01.99.01 旧保护科目')")

            violations = legacy_second_segment_99_violations_by_database((common_path, budget_path, compare_path))

        self.assertEqual(
            violations,
            {
                common_path: (
                    "data_account.data_acct_code:A01.99.01",
                    "data_account_metric_node.node_code:A01.99.01",
                    "metric.metric_node_code:A01/业务状况表/A01.99.01",
                    "metric.data_acct_code:A01/业务状况表/A01.99.01",
                ),
                budget_path: ("budget_data.data_acct_code:A01.99.01",),
                compare_path: ("compare_budget_summary.data_code_name:A01.99.01",),
            },
        )

    def test_inventory_script_reports_legacy_second_segment_99(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "current.db"
            doc_path = Path(tmp) / "inventory.md"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE data_account(data_acct_code TEXT, data_acct_name TEXT)")
                conn.execute("INSERT INTO data_account VALUES ('A01.99.01', '旧保护科目')")
            doc_path.write_text(
                "| Module | Tables | Current row counts |\n"
                "| --- | --- | --- |\n"
                "| 机构产品指标运行引用 | `data_account` | 1 |\n",
                encoding="utf-8",
            )

            result = self.run_script("--db", str(db_path), "--inventory-doc", str(doc_path))

        self.assertEqual(result.returncode, 1)
        self.assertIn("legacy_second_segment_99=failed", result.stdout)
        self.assertIn("data_account.data_acct_code:A01.99.01", result.stdout)

    def test_canonical_expense_metric_tree_requires_aa_expense_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE data_account_metric_node (
                      node_code TEXT PRIMARY KEY,
                      node_name TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE org_product_metric_table (
                      entity_code TEXT NOT NULL,
                      table_name TEXT NOT NULL,
                      payload_json TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO data_account_metric_node VALUES ('AA.05.01.01', '直接费用')"
                )

            violations = canonical_expense_metric_tree_violations(db_path)

        self.assertEqual(violations, ())

    def test_metric_identity_contract_fails_for_legacy_corp_prefixed_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "current.db"
            doc_path = Path(tmp) / "inventory.md"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account (
                      data_acct_code TEXT PRIMARY KEY NOT NULL,
                      data_acct_name TEXT NOT NULL,
                      value_type TEXT NOT NULL
                    );
                    CREATE TABLE data_account_metric_node (
                      node_code TEXT PRIMARY KEY NOT NULL,
                      node_name TEXT NOT NULL,
                      product_code TEXT,
                      local_metric_code TEXT,
                      logic_code TEXT DEFAULT '',
                      horizontal_rollup INTEGER DEFAULT 0,
                      vertical_rollup INTEGER DEFAULT 0,
                      sort_order INTEGER DEFAULT 0,
                      is_active INTEGER DEFAULT 1,
                      runtime_account_enabled INTEGER DEFAULT 0,
                      value_type TEXT DEFAULT '',
                      functional_group_code TEXT DEFAULT '',
                      level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 8),
                      node_type TEXT NOT NULL CHECK (node_type IN ('CATEGORY', 'GROUP', 'METRIC')),
                      metric_rollup_method TEXT NOT NULL DEFAULT 'NONE' CHECK (metric_rollup_method IN ('SUM', 'FORMULA', 'NONE'))
                    );
                    CREATE TABLE _data_account_metric_binding (
                      data_acct_code TEXT PRIMARY KEY NOT NULL,
                      metric_node_code TEXT NOT NULL,
                      scope_type TEXT NOT NULL CHECK (scope_type IN ('PRODUCT', 'CORP')),
                      scope_code TEXT NOT NULL,
                      UNIQUE (metric_node_code, scope_code),
                      CHECK (data_acct_code = metric_node_code),
                      CHECK (scope_code = SUBSTR(metric_node_code, 1, INSTR(metric_node_code, '.') - 1)),
                      CHECK (
                        (scope_type = 'CORP' AND scope_code = 'CORP')
                        OR (scope_type = 'PRODUCT' AND scope_code <> 'CORP')
                      )
                    );
                    CREATE VIEW data_account_metric_binding AS SELECT * FROM _data_account_metric_binding;
                    INSERT INTO data_account VALUES ('CORP.00', '全行指标', '金额');
                    INSERT INTO data_account_metric_node
                      (node_code, node_name, product_code, local_metric_code, level, node_type, metric_rollup_method)
                    VALUES
                      ('CORP.00', '全行指标', 'CORP', '00', 2, 'METRIC', 'NONE');
                    INSERT INTO _data_account_metric_binding VALUES
                      ('CORP.00', 'CORP.00', 'CORP', 'CORP');
                    """
                )
            doc_path.write_text(
                "| Module | Tables | Current row counts |\n"
                "| --- | --- | --- |\n"
                "| 机构产品指标运行引用 | `data_account`, `_data_account_metric_binding`, `data_account_metric_node` | 1, 1, 1 |\n",
                encoding="utf-8",
            )

            result = self.run_script("--db", str(db_path), "--inventory-doc", str(doc_path))

        self.assertEqual(result.returncode, 1)
        self.assertIn("metric_identity_contract=failed", result.stdout)
        self.assertIn("data_account_legacy_corp:CORP.00", result.stdout)

    def test_metric_identity_contract_fails_for_retired_binding_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "current.db"
            doc_path = Path(tmp) / "inventory.md"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account (
                      data_acct_code TEXT PRIMARY KEY NOT NULL,
                      data_acct_name TEXT NOT NULL,
                      value_type TEXT NOT NULL
                    );
                    CREATE TABLE data_account_metric_node (
                      node_code TEXT PRIMARY KEY NOT NULL,
                      node_name TEXT NOT NULL,
                      product_code TEXT,
                      local_metric_code TEXT,
                      logic_code TEXT DEFAULT '',
                      horizontal_rollup INTEGER DEFAULT 0,
                      vertical_rollup INTEGER DEFAULT 0,
                      sort_order INTEGER DEFAULT 0,
                      is_active INTEGER DEFAULT 1,
                      runtime_account_enabled INTEGER DEFAULT 0,
                      value_type TEXT DEFAULT '',
                      functional_group_code TEXT DEFAULT '',
                      level INTEGER NOT NULL,
                      node_type TEXT NOT NULL,
                      metric_rollup_method TEXT NOT NULL DEFAULT 'NONE'
                    );
                    CREATE TABLE _data_account_metric_binding (
                      data_acct_code TEXT PRIMARY KEY NOT NULL,
                      metric_node_code TEXT NOT NULL,
                      scope_type TEXT NOT NULL,
                      scope_code TEXT NOT NULL
                    );
                    CREATE VIEW data_account_metric_binding AS SELECT * FROM _data_account_metric_binding;
                    INSERT INTO data_account VALUES ('A01.01.01.001.A01', '旧后缀科目', '金额');
                    INSERT INTO data_account_metric_node
                      (node_code, node_name, product_code, local_metric_code, level, node_type, metric_rollup_method)
                    VALUES
                      ('A01.01.01.001', '产品指标', 'A01', '01.01.001', 4, 'METRIC', 'NONE');
                    INSERT INTO _data_account_metric_binding VALUES
                      ('A01.01.01.001.A01', 'A01.01.01.001', 'PRODUCT', 'A01');
                    """
                )
            doc_path.write_text(
                "| Module | Tables | Current row counts |\n"
                "| --- | --- | --- |\n"
                "| 机构产品指标运行引用 | `data_account`, `_data_account_metric_binding`, `data_account_metric_node` | 1, 1, 1 |\n",
                encoding="utf-8",
            )

            result = self.run_script("--db", str(db_path), "--inventory-doc", str(doc_path))

        self.assertEqual(result.returncode, 1)
        self.assertIn("metric_identity_contract=failed", result.stdout)
        self.assertIn("metric_binding_identity_invalid:A01.01.01.001.A01/A01.01.01.001/PRODUCT/A01", result.stdout)

    def test_fails_when_table_is_not_in_owner_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "current.db"
            doc_path = Path(tmp) / "inventory.md"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE current_fact(id INTEGER PRIMARY KEY)")
            doc_path.write_text("current_fact is mentioned in prose only.\n", encoding="utf-8")

            result = self.run_script("--db", str(db_path), "--inventory-doc", str(doc_path))

        self.assertEqual(result.returncode, 1)
        self.assertIn("inventory_doc=ok", result.stdout)
        self.assertIn("inventory_owner_doc=missing_tables", result.stdout)
        self.assertIn("current_fact", result.stdout)

    def test_missing_inventory_doc_returns_operator_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "current.db"
            doc_path = Path(tmp) / "missing.md"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE current_fact(id INTEGER PRIMARY KEY)")

            result = self.run_script("--db", str(db_path), "--inventory-doc", str(doc_path))

        self.assertEqual(result.returncode, 2)
        self.assertIn("missing_inventory_doc=", result.stderr)


if __name__ == "__main__":
    unittest.main()
