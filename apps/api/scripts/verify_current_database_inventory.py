from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
import sys


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.db_bootstrap.retired_deletion import existing_retired_tables  # noqa: E402
from app.services.runtime_metric_refs import derive_runtime_ref_from_org_product_metric_code  # noqa: E402


DEFAULT_DATABASES = (
    REPO_ROOT / "var" / "data" / "common.db",
    REPO_ROOT / "var" / "data" / "budget_2025.db",
    REPO_ROOT / "var" / "data" / "budget_2026.db",
    REPO_ROOT / "var" / "data" / "compare.db",
)
DEFAULT_INVENTORY_DOC = REPO_ROOT / "docs" / "development" / "current-database-inventory.md"
DEFAULT_WORKSPACE_CATALOG = REPO_ROOT / "apps" / "web" / "src" / "app" / "workspaceCatalog.tsx"
DEFAULT_WEB_MASTER_DATA_API = REPO_ROOT / "apps" / "web" / "src" / "lib" / "masterDataApi.ts"
DEFAULT_API_MAIN = REPO_ROOT / "apps" / "api" / "app" / "main.py"
DEFAULT_DATA_ACCOUNTS_ROUTER = REPO_ROOT / "apps" / "api" / "app" / "routers" / "data_accounts.py"
DEFAULT_DATA_PRODUCT_COMPONENT = REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "DataProductContent.tsx"
DEFAULT_PRODUCT_TYPES_ROUTER = REPO_ROOT / "apps" / "api" / "app" / "routers" / "product_types.py"
DEFAULT_ORG_PRODUCT_METRICS_ROUTER = REPO_ROOT / "apps" / "api" / "app" / "routers" / "org_product_metrics.py"
DEFAULT_RETIRED_PROJECTIONS_BOOTSTRAP = REPO_ROOT / "apps" / "api" / "app" / "db_bootstrap" / "projections.py"
DEFAULT_RUNTIME_METRIC_TREE_BOOTSTRAP = REPO_ROOT / "apps" / "api" / "app" / "db_bootstrap" / "runtime_metric_tree.py"
DEFAULT_RUNTIME_SYNC_SERVICE = REPO_ROOT / "apps" / "api" / "app" / "services" / "org_product_metric_runtime_sync.py"
DEFAULT_API_APP_ROOT = REPO_ROOT / "apps" / "api" / "app"
DEFAULT_ORG_PRODUCT_RUNTIME_CATALOG_SERVICE = (
    REPO_ROOT / "apps" / "api" / "app" / "services" / "org_product_runtime_catalog.py"
)
DEFAULT_EXPENSE_MASTER_SYNC_SERVICE = (
    REPO_ROOT / "apps" / "api" / "app" / "services" / "expense_budget_execution_master_sync.py"
)
DEFAULT_METRIC_TREE_ROLLUPS_SERVICE = (
    REPO_ROOT / "apps" / "api" / "app" / "services" / "metric_tree_rollups.py"
)
DEFAULT_AGENT_DOMAIN_LEXICON_SERVICE = (
    REPO_ROOT / "apps" / "api" / "app" / "services" / "agent_domain_lexicon.py"
)
DEFAULT_AGENT_QUERY_SERVICE = REPO_ROOT / "apps" / "api" / "app" / "agent_query.py"
DEFAULT_BUDGET_OUTPUT_DISPLAY_SERVICE = (
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_output_display.py"
)
DEFAULT_BUDGET_OUTPUT_DISPLAY_CONFIG_SERVICE = (
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_output_display_config.py"
)
DEFAULT_BUDGET_DISPLAY_CONFIG_IMPORT_SERVICE = (
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_display_config_import.py"
)
DEFAULT_SMART_REPORT_SERVICE = (
    REPO_ROOT / "apps" / "api" / "app" / "services" / "smart_report_service.py"
)
DEFAULT_SMART_PPT_SERVICE = (
    REPO_ROOT / "apps" / "api" / "app" / "services" / "smart_ppt_service.py"
)
DEFAULT_BUSINESS_COST_INCOME_COMMANDS_SERVICE = (
    REPO_ROOT / "apps" / "api" / "app" / "services" / "business_cost_income_commands.py"
)
DEFAULT_EXPENSE_FORECAST_RULE_IMPORT_WORKFLOW_SERVICE = (
    REPO_ROOT / "apps" / "api" / "app" / "services" / "expense_forecast_rule_import_workflow.py"
)
RETIRED_DIRECT_METRIC_RESTRUCTURE_SCRIPTS = (
    REPO_ROOT / "apps" / "api" / "scripts" / "restructure_business_admin_expense_metric_tree.py",
    REPO_ROOT / "apps" / "api" / "scripts" / "restructure_business_expense_evaluation_metric_tree.py",
)
RETIRED_DATA_ACCOUNT_FRONTEND_FILES = (
    REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "DataAccountContent.tsx",
    REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "DataAccountMetricNavigator.tsx",
    REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "DataAccountTableControls.tsx",
    REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "DataAccountTableHeader.tsx",
    REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "OrgProductPanpan99ExpenseContent.tsx",
    REPO_ROOT / "apps" / "web" / "src" / "lib" / "dataAccountViewModel.ts",
    REPO_ROOT / "apps" / "web" / "e2e" / "data-account-view-model.spec.ts",
)
LOCAL_METRIC_CODE_PATTERN = r"\d{2}(?:\.\d{2})*(?:\.\d{3})?"
PRODUCT_ROOT_NODE_RE = re.compile(r"^[A-Z][A-Z0-9]*$")
PRODUCT_PREFIXED_METRIC_CODE_RE = re.compile(
    rf"^[A-Z][A-Z0-9]*\.{LOCAL_METRIC_CODE_PATTERN}$"
)
METRIC_IDENTITY_TABLES = (
    "data_account",
    "data_account_metric_node",
    "data_account_metric_binding",
)
METRIC_IDENTITY_BINDING_SQL_MARKERS = (
    "CHECK (data_acct_code = metric_node_code)",
    "CHECK (scope_code = SUBSTR(metric_node_code, 1, INSTR(metric_node_code, '.') - 1))",
    "(scope_type = 'CORP' AND scope_code = 'CORP')",
    "(scope_type = 'PRODUCT' AND scope_code <> 'CORP')",
)
METRIC_IDENTITY_NODE_SQL_MARKERS = (
    "CHECK (level BETWEEN 1 AND 8)",
    "CHECK (node_type IN ('CATEGORY', 'GROUP', 'METRIC'))",
)
BUSINESS_DATA_ACCOUNT_REF_TARGETS = (
    ("budget_output_display_item", "data_acct_code"),
    ("budget_data", "data_acct_code"),
    ("business_cost_income_item", "data_acct_code"),
    ("business_cost_income_source_mapping", "data_acct_code"),
)
DERIVED_READ_MODEL_DATA_CODE_NAME_TARGETS = (
    ("budget_summary", "data_code_name"),
    ("budget_pivot_aggregate", "data_code_name"),
    ("compare_budget_summary", "data_code_name"),
    ("compare_pivot_aggregate", "data_code_name"),
)
LEGACY_SECOND_SEGMENT_99_DIRECT_TARGETS = (
    ("data_account", "data_acct_code"),
    ("data_account_metric_node", "node_code"),
    ("data_account_metric_binding", "data_acct_code"),
    ("data_account_metric_binding", "metric_node_code"),
    ("budget_data", "data_acct_code"),
    ("business_cost_income_item", "data_acct_code"),
    ("business_cost_income_source_mapping", "data_acct_code"),
)
ORG_PRODUCT_REF_PAYLOAD_TABLES = (
    ("org_product_metric_table", "metrics", "metric"),
    ("org_product_data_entry_snapshot", "metrics", "data_entry_legacy"),
    ("org_product_data_entry_snapshot_v2", "metrics", "data_entry"),
    ("org_product_data_entry_draft", "metrics", "data_entry_draft"),
    ("org_product_output_snapshot_v1", "rows", "output"),
)
RETIRED_WORKSPACE_MENU_MARKERS = (
    'id: "data-account"',
    "数据科目运行表",
    "数据科目投影",
)
RETIRED_DATA_ACCOUNT_API_MARKERS = (
    "/api/data-accounts",
    "/api/data-account-metric-tree",
    "build_data_accounts_router",
)
RETIRED_PRODUCT_WORKSPACE_MARKERS = (
    'id: "data-product"',
    'label: "产品科目维护"',
    "DataProductContent",
)
RETIRED_PRODUCT_API_MARKERS = (
    "/api/product-types",
    "build_product_types_router",
)
RETIRED_PANPAN99_MARKERS = (
    "panpan99-page",
    "/api/org-product-metrics/panpan99-page",
    "/api/org-product-metrics/data-account-projection",
    "OrgProductPanpan99ExpenseContent",
    "PROTECTED_05_REVIEW_ONLY",
)
ALLOWED_RETIRED_PANPAN99_MARKER_FILES = {
    "PROTECTED_05_REVIEW_ONLY": frozenset({DEFAULT_RUNTIME_SYNC_SERVICE}),
}
RETIRED_RUNTIME_BACKFILL_MARKERS = (
    "merge_data_account_runtime_rows_into_org_product_metrics",
    "merge_budget_referenced_data_accounts_into_org_product_metrics",
    "merge_projection_data_code_names_into_org_product_metrics",
    "_ensure_runtime_metric_identity_for_refs",
    "_load_data_dictionary_names",
    "seed_data_account_metric_tree",
    "系统按数据科目初始化生成",
    "数据科目初始化发现旧编码",
    "_metric_node_code_from_product_local",
    "_strip_metric_product_prefix",
    "预算事实引用回收机构及产品指标主表",
    "由数据科目运行主键收回机构及产品指标主表",
)
RETIRED_FRAMEWORK_MASTER_WRITE_MARKERS = (
    "data_account_upserts",
    "build_framework_master_plan_from_accounts",
    "_load_existing_data_accounts",
    "INSERT INTO data_account",
    "数据科目同步",
)
RETIRED_METRIC_TREE_ROLLUP_WRITE_MARKERS = (
    "INSERT INTO data_account",
    "UPDATE data_account",
    "系统生成：指标树父节点汇总数据科目",
    "系统生成：指标树父节点汇总绑定",
    "official_metric_account_code",
)
RETIRED_DATA_ACCOUNT_IDENTITY_FILES = (
    REPO_ROOT / "apps" / "api" / "app" / "data_account_identity.py",
)
RETIRED_DATA_ACCOUNT_METRIC_MODULE_FILES = (
    REPO_ROOT / "apps" / "api" / "app" / "db_bootstrap" / "data_account_metric_tree.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "data_account_rollup_formulas.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "data_account_runtime_paths.py",
)
RETIRED_AGENT_RUNTIME_LEXICON_MARKERS = (
    "FROM data_account\"",
    "FROM data_account_metric_node",
    "SELECT data_acct_code AS code",
    "SELECT node_code AS code",
)
RETIRED_RUNTIME_CANDIDATE_SOURCE_MARKERS = (
    "'data_account:' || d.data_acct_code",
    "'data_account' AS source_type",
    "'数据科目' AS source_label",
)
RETIRED_DATA_ACCOUNT_EXPORT_API_MARKERS = (
    "build_data_account_export_workbook",
    "export_data_accounts_workbook",
    "DATA_ACCOUNT_EXPORT_HEADERS",
    "DATA_ACCOUNT_RUNTIME_INTRO_ROWS",
)
RETIRED_DATA_ACCOUNT_SERVICE_FILES = (
    REPO_ROOT / "apps" / "api" / "app" / "services" / "data_account_usage.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "data_account_export.py",
)
RETIRED_DATA_ACCOUNT_USAGE_API_MARKERS = (
    "DataAccountRow",
    "row_to_account",
    "fetch_account_detail",
    "fetch_account_list",
    "list_data_accounts",
    "get_account_row",
)
RETIRED_FORMULA_DATA_ACCOUNT_API_MARKERS = (
    "OFFICIAL_DATA_ACCOUNT_CODE",
    "DATA_ACCOUNT_CODE_RE",
    "ANGLE_DATA_ACCOUNT_CODE_RE",
    "extract_data_account_code",
    "load_data_account_scope_map",
)
RETIRED_RUNTIME_REF_NAMING_MARKERS = (
    "DataAccountCodeExtractor",
    "extract_data_acct_code_from_name",
    "_extract_data_acct_code_from_name",
    "clear_budget_display_data_account_binding",
    "_load_bound_data_account_source",
    "_ensure_data_account_reference",
    "load_data_metric_bindings",
    "load_org_product_refs_by_data_acct_code",
    "load_org_product_metric_refs_by_data_acct_code",
    "load_confirmed_org_product_data_acct_codes",
    "org_product_refs_by_data_acct_code",
    "refs_by_data_acct_code",
    "resolve_metric_data_acct_codes",
    "sum_data_metric",
    "_load_bound_data_account_codes",
    "extract_data_account_name",
    "_data_account_code_candidates",
    "_excel_data_account_formula",
    "data_acct_row_numbers",
    "delete_budget_data_for_data_account",
    "allow_formula_accounts",
    "_load_formula_accounts",
    "formula_accounts",
)
RUNTIME_REF_NAMING_GUARD_FILES = (
    REPO_ROOT / "apps" / "api" / "app" / "main.py",
    REPO_ROOT / "apps" / "api" / "app" / "routers" / "chart_write.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "chart_data.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_display_structure.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_output_display_config.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "business_cost_income_commands.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_simulation_metrics.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_simulation_results.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "expense_forecast_metric_sources.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "expense_budget_execution_budget_source.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_output_export.py",
    REPO_ROOT / "apps" / "api" / "app" / "budget_data_writer.py",
)
FORMULA_RUNTIME_REF_API_FILES = (
    REPO_ROOT / "apps" / "api" / "app" / "formula_refs.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "formula_engine.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_summary_export_service.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_output_export.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "pivot_aggregate_export.py",
)
REQUIRED_CONFIRMED_ORG_PRODUCT_CANDIDATE_FILES = (
    DEFAULT_BUDGET_OUTPUT_DISPLAY_SERVICE,
    DEFAULT_BUDGET_OUTPUT_DISPLAY_CONFIG_SERVICE,
    DEFAULT_BUDGET_DISPLAY_CONFIG_IMPORT_SERVICE,
    DEFAULT_SMART_REPORT_SERVICE,
    DEFAULT_BUSINESS_COST_INCOME_COMMANDS_SERVICE,
)
REQUIRED_CONFIRMED_ORG_PRODUCT_REF_MARKERS = (
    (
        DEFAULT_EXPENSE_FORECAST_RULE_IMPORT_WORKFLOW_SERVICE,
        "机构及产品指标编码未在机构产品指标中确认",
    ),
    (
        DEFAULT_SMART_REPORT_SERVICE,
        "计算指标组成项未在机构及产品指标主表中确认",
    ),
    (
        DEFAULT_SMART_REPORT_SERVICE,
        "报告公式变量未在机构及产品指标主表中确认",
    ),
    (
        DEFAULT_SMART_PPT_SERVICE,
        "PPT 模板绑定指标未在机构及产品指标主表中确认",
    ),
)
USER_FACING_RUNTIME_REF_LABEL_FILES = (
    REPO_ROOT / "apps" / "api" / "app" / "agent_graph.py",
    REPO_ROOT / "apps" / "api" / "app" / "agent_product_intent.py",
    REPO_ROOT / "apps" / "api" / "app" / "agent_query.py",
    REPO_ROOT / "apps" / "api" / "app" / "agent_query_spec.py",
    REPO_ROOT / "apps" / "api" / "app" / "schemas.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "agent_analysis_filters.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "agent_pivot_suggestion.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_output_display.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_output_display_config.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_simulation_export.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "budget_summary_export_service.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "runtime_ref_export.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "export_common.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "expense_forecast_rule_import.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "expense_forecast_rule_import_workflow.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "input_output_topic_overview.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "pivot_aggregate.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "pivot_aggregate_export.py",
    REPO_ROOT / "apps" / "api" / "app" / "services" / "smart_report_service.py",
    REPO_ROOT / "apps" / "web" / "src" / "app" / "workspaceCatalog.tsx",
    REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "AnalysisReportContent.tsx",
    REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "BudgetActualBatchContent.tsx",
    REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "BudgetSimulationContent.tsx",
    REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "BudgetSimulationReverseContent.tsx",
    REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "ExcelUploadDialog.tsx",
    REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "ExpenseForecastRuleContent.tsx",
    REPO_ROOT / "apps" / "web" / "src" / "app" / "components" / "pivotTableModel.ts",
    REPO_ROOT / "apps" / "web" / "src" / "lib" / "agentApi.ts",
    REPO_ROOT / "resources" / "knowledge_base" / "01_data_semantics" / "README.md",
    REPO_ROOT / "resources" / "knowledge_base" / "01_data_semantics" / "data_dictionary_template.csv",
    REPO_ROOT / "resources" / "knowledge_base" / "01_data_semantics" / "field_table_name_mapping_zh.json",
    REPO_ROOT / "resources" / "knowledge_base" / "04_term_synonyms" / "synonyms_template.csv",
    REPO_ROOT / "resources" / "knowledge_base" / "06_agent_prompts" / "product_manager_intent_catalog.md",
    REPO_ROOT / "resources" / "knowledge_base" / "06_agent_prompts" / "product_manager_intent_messages.json",
    REPO_ROOT / "resources" / "knowledge_base" / "06_agent_prompts" / "product_manager_intent_metric_rules.md",
    REPO_ROOT / "resources" / "knowledge_base" / "06_agent_prompts" / "product_manager_intent_system.md",
    REPO_ROOT / "resources" / "knowledge_base" / "06_agent_prompts" / "product_manager_intent_user.md",
)
RETIRED_USER_FACING_DATA_ACCOUNT_LABEL_MARKERS = (
    "数据科目",
    "标准指标树",
    "底层数据科目",
    "数据科目指标优先",
    "数据科目绑定样例",
    "写入数据科目",
)
METRIC_IDENTITY_WRITE_SQL_RE = re.compile(
    r"\b(?:INSERT(?:\s+OR\s+REPLACE)?|REPLACE|UPDATE|DELETE)\s+"
    r"(?:INTO|FROM)?\s*"
    r"(?:data_account|data_account_metric_node|data_account_metric_binding)\b",
    re.IGNORECASE,
)
ALLOWED_METRIC_IDENTITY_WRITE_FILES = frozenset(
    {
        DEFAULT_RUNTIME_SYNC_SERVICE,
        DEFAULT_RUNTIME_METRIC_TREE_BOOTSTRAP,
    }
)
PRODUCT_TYPE_WRITE_SQL_RE = re.compile(
    r"\b(?:"
    r"CREATE\s+TABLE|"
    r"INSERT(?:\s+OR\s+REPLACE)?\s+INTO|"
    r"REPLACE\s+INTO|"
    r"UPDATE|"
    r"DELETE\s+FROM|"
    r"DROP\s+TABLE|"
    r"DROP\s+VIEW|"
    r"CREATE\s+VIEW"
    r")\s+product_type\b",
    re.IGNORECASE,
)
ALLOWED_PRODUCT_TYPE_WRITE_FILES = frozenset(
    {
        DEFAULT_ORG_PRODUCT_RUNTIME_CATALOG_SERVICE,
    }
)
RETIRED_SOURCE_MARKER_FILES = (
    DEFAULT_WORKSPACE_CATALOG,
    DEFAULT_WEB_MASTER_DATA_API,
    DEFAULT_API_MAIN,
    DEFAULT_ORG_PRODUCT_METRICS_ROUTER,
    DEFAULT_RUNTIME_SYNC_SERVICE,
    DEFAULT_RUNTIME_METRIC_TREE_BOOTSTRAP,
)


@dataclass(frozen=True)
class TableInventoryRow:
    database: Path
    table: str
    rows: int


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _display_path(db_path: Path) -> str:
    try:
        return str(db_path.relative_to(REPO_ROOT))
    except ValueError:
        return str(db_path)


def _repo_relative_or_absolute(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _iter_python_files(root: Path) -> tuple[Path, ...]:
    if not root.exists():
        return ()
    return tuple(
        path
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
    )


def direct_metric_identity_write_violations(
    app_root: Path = DEFAULT_API_APP_ROOT,
    *,
    allowed_files: frozenset[Path] = ALLOWED_METRIC_IDENTITY_WRITE_FILES,
) -> tuple[str, ...]:
    violations: list[str] = []
    allowed = {path.resolve() for path in allowed_files}
    for path in _iter_python_files(app_root):
        if path.resolve() in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        for match in METRIC_IDENTITY_WRITE_SQL_RE.finditer(source):
            line_no = source.count("\n", 0, match.start()) + 1
            snippet = " ".join(match.group(0).split())
            violations.append(
                f"direct_metric_identity_write:{_repo_relative_or_absolute(path)}:{line_no}:{snippet}"
            )
            break
    return tuple(violations)


def direct_product_type_write_violations(
    app_root: Path = DEFAULT_API_APP_ROOT,
    *,
    allowed_files: frozenset[Path] = ALLOWED_PRODUCT_TYPE_WRITE_FILES,
) -> tuple[str, ...]:
    violations: list[str] = []
    allowed = {path.resolve() for path in allowed_files}
    for path in _iter_python_files(app_root):
        if path.resolve() in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        for match in PRODUCT_TYPE_WRITE_SQL_RE.finditer(source):
            line_no = source.count("\n", 0, match.start()) + 1
            snippet = " ".join(match.group(0).split())
            violations.append(
                f"direct_product_type_write:{_repo_relative_or_absolute(path)}:{line_no}:{snippet}"
            )
            break
    return tuple(violations)


def user_facing_data_account_label_violations(
    paths: tuple[Path, ...] = USER_FACING_RUNTIME_REF_LABEL_FILES,
    *,
    markers: tuple[str, ...] = RETIRED_USER_FACING_DATA_ACCOUNT_LABEL_MARKERS,
) -> tuple[str, ...]:
    violations: list[str] = []
    for path in paths:
        if not path.exists() or path.is_dir():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker in source:
                violations.append(
                    f"retired_user_facing_data_account_label:"
                    f"{_repo_relative_or_absolute(path)}:{marker}"
                )
    return tuple(violations)


def list_current_tables(db_path: Path) -> tuple[str, ...]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    finally:
        conn.close()
    return tuple(str(row[0]) for row in rows)


def list_current_relations(db_path: Path) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT name, type
            FROM sqlite_master
            WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    finally:
        conn.close()
    return {str(row[0]): str(row[1]) for row in rows}


def _table_sql(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return str(row[0] or "") if row else ""


def _is_product_prefixed_metric_code(code: str) -> bool:
    return PRODUCT_PREFIXED_METRIC_CODE_RE.fullmatch(str(code or "").strip().upper()) is not None


def _derived_read_model_data_code(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.split(maxsplit=1)[0].strip().upper().replace(" ", "")


def _has_legacy_second_segment_99(value: str) -> bool:
    code = _derived_read_model_data_code(value)
    parts = code.split(".")
    return len(parts) >= 2 and parts[1] == "99"


def _is_current_metric_tree_node_code(code: str) -> bool:
    text = str(code or "").strip().upper()
    return bool(
        PRODUCT_ROOT_NODE_RE.fullmatch(text)
        or PRODUCT_PREFIXED_METRIC_CODE_RE.fullmatch(text)
    )


def _is_leaf_metric_payload_node(node: dict) -> bool:
    children = node.get("children")
    return not isinstance(children, list) or not any(isinstance(child, dict) for child in children)


def _is_org_product_fee05_metric_code(entity_code: str, raw_code: str) -> bool:
    code = str(raw_code or "").strip().upper().replace(" ", "")
    if not code:
        return False
    if "." in code:
        parts = [part for part in code.split(".") if part]
        return len(parts) >= 2 and parts[1] == "05"
    owner = str(entity_code or "").strip().upper()
    if owner and code.startswith(owner):
        remainder = code[len(owner) :]
    elif code.startswith(("AA", "AB")):
        remainder = code[2:]
    else:
        remainder = code[3:] if len(code) >= 3 else ""
    return len(remainder) >= 2 and remainder[:2] == "05"


def _iter_metric_payload_nodes(nodes: list[dict]) -> tuple[dict, ...]:
    flattened: list[dict] = []
    stack = list(nodes)
    while stack:
        node = stack.pop(0)
        flattened.append(node)
        children = node.get("children") if isinstance(node, dict) else []
        if isinstance(children, list):
            stack[0:0] = [child for child in children if isinstance(child, dict)]
    return tuple(flattened)


def _append_org_product_mapping_status_violations(
    violations: list[str],
    *,
    prefix: str,
    entity: str,
    table: str,
    code: str,
    status: str,
    metric_ref: str,
    data_ref: str,
) -> None:
    label_prefix = f"{prefix}_" if prefix else ""
    if status == "PROTECTED_05_REVIEW_ONLY":
        violations.append(f"{label_prefix}legacy_protected_status:{entity}/{table}/{code}/{metric_ref or '-'}/{data_ref or '-'}")


def retired_workspace_menu_violations(catalog_path: Path = DEFAULT_WORKSPACE_CATALOG) -> tuple[str, ...]:
    if not catalog_path.exists():
        return (f"missing_workspace_catalog:{catalog_path}",)
    text = catalog_path.read_text(encoding="utf-8")
    violations: list[str] = []
    for marker in RETIRED_WORKSPACE_MENU_MARKERS:
        if marker in text:
            violations.append(f"retired_workspace_menu_marker:{marker}")
    for marker in RETIRED_PRODUCT_WORKSPACE_MARKERS:
        if marker in text:
            violations.append(f"retired_product_workspace_marker:{marker}")
    for path in RETIRED_DATA_ACCOUNT_FRONTEND_FILES:
        if path.exists():
            violations.append(f"retired_data_account_frontend_file_exists:{_repo_relative_or_absolute(path)}")
    if DEFAULT_DATA_ACCOUNTS_ROUTER.exists():
        violations.append(f"retired_data_accounts_router_exists:{DEFAULT_DATA_ACCOUNTS_ROUTER.relative_to(REPO_ROOT)}")
    if DEFAULT_DATA_PRODUCT_COMPONENT.exists():
        violations.append(f"retired_product_component_exists:{DEFAULT_DATA_PRODUCT_COMPONENT.relative_to(REPO_ROOT)}")
    if DEFAULT_PRODUCT_TYPES_ROUTER.exists():
        violations.append(f"retired_product_types_router_exists:{DEFAULT_PRODUCT_TYPES_ROUTER.relative_to(REPO_ROOT)}")
    if DEFAULT_RETIRED_PROJECTIONS_BOOTSTRAP.exists():
        violations.append(
            f"retired_projection_bootstrap_exists:{_repo_relative_or_absolute(DEFAULT_RETIRED_PROJECTIONS_BOOTSTRAP)}"
        )
    for path in RETIRED_DIRECT_METRIC_RESTRUCTURE_SCRIPTS:
        if path.exists():
            violations.append(f"retired_direct_metric_restructure_script_exists:{_repo_relative_or_absolute(path)}")
    for path in (DEFAULT_WEB_MASTER_DATA_API, DEFAULT_API_MAIN):
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in RETIRED_DATA_ACCOUNT_API_MARKERS:
            if marker in source:
                violations.append(f"retired_data_accounts_api_marker:{path.relative_to(REPO_ROOT)}:{marker}")
        for marker in RETIRED_PRODUCT_API_MARKERS:
            if marker in source:
                violations.append(f"retired_product_api_marker:{path.relative_to(REPO_ROOT)}:{marker}")
    for path in RETIRED_SOURCE_MARKER_FILES:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in RETIRED_PANPAN99_MARKERS:
            if marker in source:
                allowed_files = ALLOWED_RETIRED_PANPAN99_MARKER_FILES.get(marker, frozenset())
                if path.resolve() in {allowed.resolve() for allowed in allowed_files}:
                    continue
                violations.append(f"retired_panpan99_marker:{_repo_relative_or_absolute(path)}:{marker}")
        for marker in RETIRED_RUNTIME_BACKFILL_MARKERS:
            if marker in source:
                violations.append(f"retired_runtime_backfill_marker:{_repo_relative_or_absolute(path)}:{marker}")
    if DEFAULT_EXPENSE_MASTER_SYNC_SERVICE.exists():
        source = DEFAULT_EXPENSE_MASTER_SYNC_SERVICE.read_text(encoding="utf-8")
        for marker in RETIRED_FRAMEWORK_MASTER_WRITE_MARKERS:
            if marker in source:
                violations.append(
                    f"retired_framework_master_write_marker:"
                    f"{_repo_relative_or_absolute(DEFAULT_EXPENSE_MASTER_SYNC_SERVICE)}:{marker}"
                )
    if DEFAULT_METRIC_TREE_ROLLUPS_SERVICE.exists():
        source = DEFAULT_METRIC_TREE_ROLLUPS_SERVICE.read_text(encoding="utf-8")
        for marker in RETIRED_METRIC_TREE_ROLLUP_WRITE_MARKERS:
            if marker in source:
                violations.append(
                    f"retired_metric_tree_rollup_write_marker:"
                    f"{_repo_relative_or_absolute(DEFAULT_METRIC_TREE_ROLLUPS_SERVICE)}:{marker}"
                )
    for path in (DEFAULT_AGENT_DOMAIN_LEXICON_SERVICE, DEFAULT_AGENT_QUERY_SERVICE):
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in RETIRED_AGENT_RUNTIME_LEXICON_MARKERS:
            if marker in source:
                violations.append(
                    f"retired_agent_runtime_lexicon_marker:"
                    f"{_repo_relative_or_absolute(path)}:{marker}"
                )
    for path in REQUIRED_CONFIRMED_ORG_PRODUCT_CANDIDATE_FILES:
        if not path.exists():
            violations.append(f"missing_confirmed_org_product_candidate_file:{_repo_relative_or_absolute(path)}")
            continue
        source = path.read_text(encoding="utf-8")
        if "load_confirmed_org_product_runtime_ref_codes" not in source:
            violations.append(
                f"missing_confirmed_org_product_candidate_guard:{_repo_relative_or_absolute(path)}"
            )
        for marker in RETIRED_RUNTIME_CANDIDATE_SOURCE_MARKERS:
            if marker in source:
                violations.append(
                    f"retired_runtime_candidate_source_marker:"
                    f"{_repo_relative_or_absolute(path)}:{marker}"
                )
    for path, marker in REQUIRED_CONFIRMED_ORG_PRODUCT_REF_MARKERS:
        if not path.exists():
            violations.append(f"missing_confirmed_org_product_ref_guard_file:{_repo_relative_or_absolute(path)}")
            continue
        source = path.read_text(encoding="utf-8")
        if marker not in source:
            violations.append(
                f"missing_confirmed_org_product_ref_guard:"
                f"{_repo_relative_or_absolute(path)}:{marker}"
            )
    runtime_ref_export_service = REPO_ROOT / "apps" / "api" / "app" / "services" / "runtime_ref_export.py"
    if runtime_ref_export_service.exists():
        source = runtime_ref_export_service.read_text(encoding="utf-8")
        for marker in RETIRED_DATA_ACCOUNT_EXPORT_API_MARKERS:
            if marker in source:
                violations.append(
                    f"retired_runtime_ref_export_api_marker:"
                    f"{_repo_relative_or_absolute(runtime_ref_export_service)}:{marker}"
                )
    for path in RETIRED_DATA_ACCOUNT_SERVICE_FILES:
        if path.exists():
            violations.append(f"retired_data_account_service_file_exists:{_repo_relative_or_absolute(path)}")
    for path in RETIRED_DATA_ACCOUNT_IDENTITY_FILES:
        if path.exists():
            violations.append(f"retired_data_account_identity_file_exists:{_repo_relative_or_absolute(path)}")
    for path in RETIRED_DATA_ACCOUNT_METRIC_MODULE_FILES:
        if path.exists():
            violations.append(f"retired_data_account_metric_module_file_exists:{_repo_relative_or_absolute(path)}")
    for path in (
        REPO_ROOT / "apps" / "api" / "app" / "schemas.py",
        REPO_ROOT / "apps" / "api" / "app" / "services" / "runtime_metric_refs.py",
    ):
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in RETIRED_DATA_ACCOUNT_USAGE_API_MARKERS:
            if marker in source:
                violations.append(
                    f"retired_runtime_metric_refs_api_marker:"
                    f"{_repo_relative_or_absolute(path)}:{marker}"
                )
    for path in FORMULA_RUNTIME_REF_API_FILES:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in RETIRED_FORMULA_DATA_ACCOUNT_API_MARKERS:
            if marker in source:
                violations.append(
                    f"retired_formula_data_account_api_marker:"
                    f"{_repo_relative_or_absolute(path)}:{marker}"
                )
    for path in RUNTIME_REF_NAMING_GUARD_FILES:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in RETIRED_RUNTIME_REF_NAMING_MARKERS:
            if marker in source:
                violations.append(
                    f"retired_runtime_ref_naming_marker:"
                    f"{_repo_relative_or_absolute(path)}:{marker}"
                )
    violations.extend(user_facing_data_account_label_violations())
    violations.extend(direct_metric_identity_write_violations())
    violations.extend(direct_product_type_write_violations())
    return tuple(violations)


def metric_identity_contract_violations(db_path: Path) -> tuple[str, ...]:
    conn = sqlite3.connect(db_path)
    try:
        current_relations = list_current_relations(db_path)
        if not any(table in current_relations for table in METRIC_IDENTITY_TABLES):
            return ()
        violations: list[str] = []
        for table in METRIC_IDENTITY_TABLES:
            if table not in current_relations:
                violations.append(f"missing_relation:{table}")
        if current_relations.get("data_account_metric_binding") == "table":
            violations.append("binding_physical_table_retired:data_account_metric_binding")
        elif current_relations.get("data_account_metric_binding") not in {"", None, "view"}:
            violations.append("binding_relation_type_invalid:data_account_metric_binding")
        if violations:
            return tuple(violations)

        node_sql = _table_sql(conn, "data_account_metric_node")
        for marker in METRIC_IDENTITY_NODE_SQL_MARKERS:
            if marker not in node_sql:
                violations.append(f"node_schema_missing:{marker}")
        if current_relations.get("data_account_metric_binding") != "view":
            violations.append("binding_view_missing:data_account_metric_binding")

        bad_data_codes: list[str] = []
        legacy_corp_data_codes: list[str] = []
        for (code,) in conn.execute("SELECT data_acct_code FROM data_account ORDER BY data_acct_code"):
            normalized = str(code or "").strip().upper()
            if normalized.startswith("CORP."):
                legacy_corp_data_codes.append(normalized)
                if len(legacy_corp_data_codes) >= 10:
                    break
            if normalized and not _is_product_prefixed_metric_code(normalized):
                bad_data_codes.append(normalized)
            if len(bad_data_codes) >= 10:
                break
        if bad_data_codes:
            violations.append("data_account_non_product_prefixed:" + ",".join(bad_data_codes))
        if legacy_corp_data_codes:
            violations.append("data_account_legacy_corp:" + ",".join(legacy_corp_data_codes))

        invalid_node_codes: list[str] = []
        for row in conn.execute(
            """
            SELECT node_code, product_code, local_metric_code, logic_code, level,
                   horizontal_rollup, vertical_rollup
            FROM data_account_metric_node
            ORDER BY node_code
            """
        ):
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
                not _is_current_metric_tree_node_code(node_code)
                or product_code != expected_product
                or local_metric_code != expected_local
                or logic_code != expected_local
                or level != expected_level
                or horizontal_rollup not in {0, 1}
                or vertical_rollup not in {0, 1}
            ):
                invalid_node_codes.append(node_code)
            if len(invalid_node_codes) >= 10:
                break
        if invalid_node_codes:
            violations.append("metric_node_identity_invalid:" + ",".join(invalid_node_codes))

        bad_bindings: list[str] = []
        for row in conn.execute(
            """
            SELECT data_acct_code, metric_node_code, scope_type, scope_code
            FROM data_account_metric_binding
            ORDER BY data_acct_code
            """
        ):
            data_code = str(row[0] or "").strip().upper()
            metric_code = str(row[1] or "").strip().upper()
            scope_type = str(row[2] or "").strip().upper()
            scope_code = str(row[3] or "").strip().upper()
            product_prefix = metric_code.split(".", 1)[0] if _is_product_prefixed_metric_code(metric_code) else ""
            expected_scope_type = "CORP" if product_prefix == "CORP" else "PRODUCT"
            if data_code != metric_code or not product_prefix or scope_code != product_prefix or scope_type != expected_scope_type:
                bad_bindings.append(f"{data_code}/{metric_code}/{scope_type}/{scope_code}")
            if len(bad_bindings) >= 10:
                break
        if bad_bindings:
            violations.append("metric_binding_identity_invalid:" + ",".join(bad_bindings))
        return tuple(violations)
    finally:
        conn.close()


def org_product_metric_guard_violations(db_path: Path) -> tuple[str, ...]:
    conn = sqlite3.connect(db_path)
    try:
        current_tables = set(list_current_tables(db_path))
        violations: list[str] = []

        if "org_product_metric_table" in current_tables:
            for entity_code, table_name, payload_json in conn.execute(
                """
                SELECT entity_code, table_name, payload_json
                FROM org_product_metric_table
                ORDER BY entity_code, table_name
                """
            ):
                entity = str(entity_code or "").strip().upper()
                table = str(table_name or "").strip()
                if entity == "CORP":
                    violations.append(f"legacy_corp_metric_table:{entity}/{table}")
                    if len(violations) >= 20:
                        return tuple(violations)
                try:
                    payload = json.loads(payload_json or "{}")
                except Exception:
                    violations.append(f"invalid_payload:{entity}/{table}")
                    continue
                metrics = payload.get("metrics") if isinstance(payload, dict) else []
                if not isinstance(metrics, list):
                    violations.append(f"invalid_metrics:{entity}/{table}")
                    continue
                for node in _iter_metric_payload_nodes([item for item in metrics if isinstance(item, dict)]):
                    code = str(node.get("code") or "").strip().upper()
                    runtime_ref = derive_runtime_ref_from_org_product_metric_code(
                        entity_code=entity,
                        metric_code=code,
                    )
                    _append_org_product_mapping_status_violations(
                        violations,
                        prefix="",
                        entity=entity,
                        table=table,
                        code=code,
                        status=str(node.get("mapping_status") or "").strip().upper(),
                        metric_ref=runtime_ref,
                        data_ref=runtime_ref,
                    )
                    if len(violations) >= 20:
                        return tuple(violations)

        if "org_product_data_entry_snapshot" in current_tables:
            for entity_code, table_name, payload_json in conn.execute(
                """
                SELECT entity_code, table_name, payload_json
                FROM org_product_data_entry_snapshot
                ORDER BY entity_code, table_name
                """
            ):
                entity = str(entity_code or "").strip().upper()
                table = str(table_name or "").strip()
                try:
                    payload = json.loads(payload_json or "{}")
                except Exception:
                    violations.append(f"data_entry_legacy_invalid_payload:{entity}/{table}")
                    continue
                metrics = payload.get("metrics") if isinstance(payload, dict) else []
                if not isinstance(metrics, list):
                    violations.append(f"data_entry_legacy_invalid_metrics:{entity}/{table}")
                    continue
                for row in [item for item in metrics if isinstance(item, dict)]:
                    _append_org_product_mapping_status_violations(
                        violations,
                        prefix="data_entry_legacy",
                        entity=entity,
                        table=table,
                        code=str(row.get("metric_code") or "").strip().upper(),
                        status=str(row.get("mapping_status") or "").strip().upper(),
                        metric_ref=str(row.get("metric_node_code") or "").strip(),
                        data_ref=str(row.get("data_acct_code") or "").strip(),
                    )
                    if len(violations) >= 20:
                        return tuple(violations)

        if "org_product_data_entry_snapshot_v2" in current_tables:
            for entity_code, table_name, payload_json in conn.execute(
                """
                SELECT entity_code, table_name, payload_json
                FROM org_product_data_entry_snapshot_v2
                ORDER BY entity_code, table_name
                """
            ):
                entity = str(entity_code or "").strip().upper()
                table = str(table_name or "").strip()
                try:
                    payload = json.loads(payload_json or "{}")
                except Exception:
                    violations.append(f"data_entry_invalid_payload:{entity}/{table}")
                    continue
                metrics = payload.get("metrics") if isinstance(payload, dict) else []
                if not isinstance(metrics, list):
                    violations.append(f"data_entry_invalid_metrics:{entity}/{table}")
                    continue
                for row in [item for item in metrics if isinstance(item, dict)]:
                    _append_org_product_mapping_status_violations(
                        violations,
                        prefix="data_entry",
                        entity=entity,
                        table=table,
                        code=str(row.get("metric_code") or "").strip().upper(),
                        status=str(row.get("mapping_status") or "").strip().upper(),
                        metric_ref=str(row.get("metric_node_code") or "").strip(),
                        data_ref=str(row.get("data_acct_code") or "").strip(),
                    )
                    if len(violations) >= 20:
                        return tuple(violations)

        if "org_product_data_entry_draft" in current_tables:
            for entity_code, table_name, payload_json in conn.execute(
                """
                SELECT entity_code, table_name, payload_json
                FROM org_product_data_entry_draft
                ORDER BY entity_code, table_name
                """
            ):
                entity = str(entity_code or "").strip().upper()
                table = str(table_name or "").strip()
                try:
                    payload = json.loads(payload_json or "{}")
                except Exception:
                    violations.append(f"data_entry_draft_invalid_payload:{entity}/{table}")
                    continue
                metrics = payload.get("metrics") if isinstance(payload, dict) else []
                if not isinstance(metrics, list):
                    violations.append(f"data_entry_draft_invalid_metrics:{entity}/{table}")
                    continue
                for row in [item for item in metrics if isinstance(item, dict)]:
                    _append_org_product_mapping_status_violations(
                        violations,
                        prefix="data_entry_draft",
                        entity=entity,
                        table=table,
                        code=str(row.get("metric_code") or "").strip().upper(),
                        status=str(row.get("mapping_status") or "").strip().upper(),
                        metric_ref=str(row.get("metric_node_code") or "").strip(),
                        data_ref=str(row.get("data_acct_code") or "").strip(),
                    )
                    if len(violations) >= 20:
                        return tuple(violations)

        if "org_product_output_snapshot_v1" in current_tables:
            for entity_code, table_name, payload_json in conn.execute(
                """
                SELECT entity_code, table_name, payload_json
                FROM org_product_output_snapshot_v1
                ORDER BY entity_code, table_name
                """
            ):
                entity = str(entity_code or "").strip().upper()
                table = str(table_name or "").strip()
                try:
                    payload = json.loads(payload_json or "{}")
                except Exception:
                    violations.append(f"output_invalid_payload:{entity}/{table}")
                    continue
                rows = payload.get("rows") if isinstance(payload, dict) else []
                if not isinstance(rows, list):
                    violations.append(f"output_invalid_rows:{entity}/{table}")
                    continue
                for row in [item for item in rows if isinstance(item, dict)]:
                    _append_org_product_mapping_status_violations(
                        violations,
                        prefix="output",
                        entity=entity,
                        table=table,
                        code=str(row.get("code") or "").strip().upper(),
                        status=str(row.get("mapping_status") or "").strip().upper(),
                        metric_ref=str(row.get("metric_node_code") or "").strip(),
                        data_ref=str(row.get("data_acct_code") or "").strip(),
                    )
                    if len(violations) >= 20:
                        return tuple(violations)

        return tuple(violations)
    finally:
        conn.close()


def metric_identity_violations_by_database(db_paths: tuple[Path, ...]) -> dict[Path, tuple[str, ...]]:
    return {
        db_path: violations
        for db_path in db_paths
        if (violations := metric_identity_contract_violations(db_path))
    }


def org_product_metric_guard_violations_by_database(db_paths: tuple[Path, ...]) -> dict[Path, tuple[str, ...]]:
    return {
        db_path: violations
        for db_path in db_paths
        if (violations := org_product_metric_guard_violations(db_path))
    }


def _append_org_product_runtime_ref_violations(
    violations: list[str],
    *,
    entity: str,
    table: str,
    code: str,
    status: str,
    is_leaf: bool,
    metric_ref: str,
    data_ref: str,
    metric_nodes: set[str],
    data_accounts: set[str],
    bindings: dict[str, str],
) -> None:
    metric = str(metric_ref or "").strip().upper()
    data = str(data_ref or "").strip().upper()
    if not metric and not data:
        if str(status or "").strip().upper() == "MANUAL_CONFIRMED" and is_leaf:
            label = f"{entity}/{table}/{code or '-'}/-/-"
            violations.append(f"org_product_confirmed_leaf_missing_ref:{label}")
        return
    label = f"{entity}/{table}/{code or '-'}/{metric or '-'}/{data or '-'}"
    if not metric or not data:
        violations.append(f"org_product_ref_one_sided:{label}")
        return
    if metric != data:
        violations.append(f"org_product_ref_mismatch:{label}")
        return
    if not _is_product_prefixed_metric_code(metric):
        violations.append(f"org_product_ref_not_product_prefixed:{label}")
    if metric not in metric_nodes:
        violations.append(f"org_product_ref_missing_metric_node:{label}")
    if data not in data_accounts:
        violations.append(f"org_product_ref_missing_data_account:{label}")
    if bindings.get(data) != data:
        violations.append(f"org_product_ref_missing_or_invalid_binding:{label}")


def org_product_metric_runtime_ref_violations(db_path: Path) -> tuple[str, ...]:
    conn = sqlite3.connect(db_path)
    try:
        current_relations = list_current_relations(db_path)
        if "org_product_metric_table" not in current_relations:
            return ()
        required = {"data_account", "data_account_metric_node", "data_account_metric_binding"}
        missing = sorted(required - set(current_relations))
        if missing:
            return tuple(f"missing_runtime_relation:{table}" for table in missing)
        if current_relations.get("data_account_metric_binding") != "view":
            return ("runtime_binding_must_be_view:data_account_metric_binding",)

        metric_nodes = {
            str(row[0] or "").strip().upper()
            for row in conn.execute("SELECT node_code FROM data_account_metric_node")
        }
        data_accounts = {
            str(row[0] or "").strip().upper()
            for row in conn.execute("SELECT data_acct_code FROM data_account")
        }
        bindings = {
            str(row[0] or "").strip().upper(): str(row[1] or "").strip().upper()
            for row in conn.execute("SELECT data_acct_code, metric_node_code FROM data_account_metric_binding")
        }
        violations: list[str] = []
        confirmed_refs: set[str] = set()
        for entity_code, table_name, payload_json in conn.execute(
            """
            SELECT entity_code, table_name, payload_json
            FROM org_product_metric_table
            ORDER BY entity_code, table_name
            """
        ):
            entity = str(entity_code or "").strip().upper()
            table = str(table_name or "").strip()
            try:
                payload = json.loads(payload_json or "{}")
            except Exception:
                violations.append(f"org_product_ref_invalid_payload:{entity}/{table}")
                continue
            metrics = payload.get("metrics") if isinstance(payload, dict) else []
            if not isinstance(metrics, list):
                violations.append(f"org_product_ref_invalid_metrics:{entity}/{table}")
                continue
            for node in _iter_metric_payload_nodes([item for item in metrics if isinstance(item, dict)]):
                status = str(node.get("mapping_status") or "").strip().upper()
                code = str(node.get("code") or "").strip().upper()
                data_ref = derive_runtime_ref_from_org_product_metric_code(
                    entity_code=entity,
                    metric_code=code,
                )
                metric_ref = data_ref
                if data_ref:
                    confirmed_refs.add(data_ref)
                _append_org_product_runtime_ref_violations(
                    violations,
                    entity=entity,
                    table=table,
                    code=code,
                    status=status,
                    is_leaf=_is_leaf_metric_payload_node(node),
                    metric_ref=metric_ref,
                    data_ref=data_ref,
                    metric_nodes=metric_nodes,
                    data_accounts=data_accounts,
                    bindings=bindings,
                )
                if len(violations) >= 20:
                    return tuple(violations)
        for data_code in sorted(data_accounts):
            if data_code not in confirmed_refs:
                violations.append(f"data_account_missing_org_product_confirmed_ref:{data_code}")
            if len(violations) >= 20:
                return tuple(violations)
        return tuple(violations)
    finally:
        conn.close()


def org_product_metric_runtime_ref_violations_by_database(db_paths: tuple[Path, ...]) -> dict[Path, tuple[str, ...]]:
    return {
        db_path: violations
        for db_path in db_paths
        if (violations := org_product_metric_runtime_ref_violations(db_path))
    }


def _confirmed_org_product_data_refs(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        current_relations = set(list_current_relations(db_path))
        if "data_account" not in current_relations:
            return set()
        return {
            str(row[0] or "").strip().upper()
            for row in conn.execute("SELECT data_acct_code FROM data_account")
            if str(row[0] or "").strip()
        }
    finally:
        conn.close()


def business_data_account_ref_violations_by_database(db_paths: tuple[Path, ...]) -> dict[Path, tuple[str, ...]]:
    confirmed_refs: set[str] = set()
    for db_path in db_paths:
        confirmed_refs.update(_confirmed_org_product_data_refs(db_path))
    if not confirmed_refs:
        return {}

    out: dict[Path, tuple[str, ...]] = {}
    for db_path in db_paths:
        conn = sqlite3.connect(db_path)
        try:
            current_tables = set(list_current_tables(db_path))
            violations: list[str] = []
            for table, column in BUSINESS_DATA_ACCOUNT_REF_TARGETS:
                if table not in current_tables:
                    continue
                for (value,) in conn.execute(
                    f"""
                    SELECT DISTINCT {_quote_identifier(column)}
                    FROM {_quote_identifier(table)}
                    WHERE {_quote_identifier(column)} IS NOT NULL
                      AND TRIM({_quote_identifier(column)}) <> ''
                    ORDER BY {_quote_identifier(column)}
                    """
                ):
                    code = str(value or "").strip().upper()
                    if code and code not in confirmed_refs:
                        violations.append(f"{table}.{column}:{code}")
                    if len(violations) >= 20:
                        break
                if len(violations) >= 20:
                    break
            if violations:
                out[db_path] = tuple(violations)
        finally:
            conn.close()
    return out


def derived_read_model_data_code_name_ref_violations_by_database(db_paths: tuple[Path, ...]) -> dict[Path, tuple[str, ...]]:
    confirmed_refs: set[str] = set()
    for db_path in db_paths:
        confirmed_refs.update(_confirmed_org_product_data_refs(db_path))
    if not confirmed_refs:
        return {}

    out: dict[Path, tuple[str, ...]] = {}
    for db_path in db_paths:
        conn = sqlite3.connect(db_path)
        try:
            current_tables = set(list_current_tables(db_path))
            violations: list[str] = []
            for table, column in DERIVED_READ_MODEL_DATA_CODE_NAME_TARGETS:
                if table not in current_tables:
                    continue
                for (value,) in conn.execute(
                    f"""
                    SELECT DISTINCT {_quote_identifier(column)}
                    FROM {_quote_identifier(table)}
                    WHERE {_quote_identifier(column)} IS NOT NULL
                      AND TRIM({_quote_identifier(column)}) <> ''
                    ORDER BY {_quote_identifier(column)}
                    """
                ):
                    code = _derived_read_model_data_code(str(value or ""))
                    if not code:
                        continue
                    if code.startswith("CORP."):
                        violations.append(f"{table}.{column}:legacy_corp:{code}")
                    elif code not in confirmed_refs:
                        violations.append(f"{table}.{column}:{code}")
                    if len(violations) >= 20:
                        break
                if len(violations) >= 20:
                    break
            if violations:
                out[db_path] = tuple(violations)
        finally:
            conn.close()
    return out


def legacy_second_segment_99_violations(db_path: Path) -> tuple[str, ...]:
    conn = sqlite3.connect(db_path)
    try:
        current_tables = set(list_current_tables(db_path))
        violations: list[str] = []
        for table, column in (*LEGACY_SECOND_SEGMENT_99_DIRECT_TARGETS, *DERIVED_READ_MODEL_DATA_CODE_NAME_TARGETS):
            if table not in current_tables:
                continue
            for (value,) in conn.execute(
                f"""
                SELECT DISTINCT {_quote_identifier(column)}
                FROM {_quote_identifier(table)}
                WHERE {_quote_identifier(column)} IS NOT NULL
                  AND TRIM({_quote_identifier(column)}) <> ''
                ORDER BY {_quote_identifier(column)}
                """
            ):
                code = _derived_read_model_data_code(str(value or ""))
                if _has_legacy_second_segment_99(code):
                    violations.append(f"{table}.{column}:{code}")
                if len(violations) >= 20:
                    return tuple(violations)

        for table, payload_key, prefix in ORG_PRODUCT_REF_PAYLOAD_TABLES:
            if table not in current_tables:
                continue
            for entity_code, table_name, payload_json in conn.execute(
                f"""
                SELECT entity_code, table_name, payload_json
                FROM {_quote_identifier(table)}
                ORDER BY entity_code, table_name
                """
            ):
                entity = str(entity_code or "").strip().upper()
                table_label = str(table_name or "").strip()
                try:
                    payload = json.loads(payload_json or "{}")
                except Exception:
                    continue
                rows = payload.get(payload_key) if isinstance(payload, dict) else []
                if not isinstance(rows, list):
                    continue
                iterable = (
                    _iter_metric_payload_nodes([item for item in rows if isinstance(item, dict)])
                    if payload_key == "metrics"
                    else tuple(item for item in rows if isinstance(item, dict))
                )
                for row in iterable:
                    for field in ("metric_node_code", "data_acct_code"):
                        code = _derived_read_model_data_code(str(row.get(field) or ""))
                        if _has_legacy_second_segment_99(code):
                            violations.append(f"{prefix}.{field}:{entity}/{table_label}/{code}")
                        if len(violations) >= 20:
                            return tuple(violations)
        return tuple(violations)
    finally:
        conn.close()


def legacy_second_segment_99_violations_by_database(db_paths: tuple[Path, ...]) -> dict[Path, tuple[str, ...]]:
    return {
        db_path: violations
        for db_path in db_paths
        if (violations := legacy_second_segment_99_violations(db_path))
    }


def org_product_runtime_catalog_violations(db_path: Path) -> tuple[str, ...]:
    conn = sqlite3.connect(db_path)
    try:
        objects = {
            str(row[0]): str(row[1])
            for row in conn.execute(
                "SELECT name, type FROM sqlite_master WHERE name IN ('org_product_tree_snapshot', 'product_type')"
            )
        }
        if "org_product_tree_snapshot" not in objects:
            return ()
        violations: list[str] = []
        product_type_kind = objects.get("product_type")
        if product_type_kind:
            violations.append(f"retired_product_type_object:{product_type_kind}")
            return tuple(violations)
        try:
            row_count = int(
                conn.execute(
                    """
                    WITH RECURSIVE org_product_runtime_products(
                      product_code, product_name, parent_code, level, children
                    ) AS (
                      SELECT
                        UPPER(TRIM(COALESCE(json_extract(payload_json, '$.code'), ''))),
                        TRIM(COALESCE(json_extract(payload_json, '$.name'), '')),
                        NULL,
                        1,
                        json_extract(payload_json, '$.children')
                      FROM org_product_tree_snapshot
                      WHERE id = 1
                      UNION ALL
                      SELECT
                        UPPER(TRIM(COALESCE(json_extract(child.value, '$.code'), ''))),
                        TRIM(COALESCE(json_extract(child.value, '$.name'), '')),
                        org_product_runtime_products.product_code,
                        org_product_runtime_products.level + 1,
                        json_extract(child.value, '$.children')
                      FROM org_product_runtime_products,
                           json_each(COALESCE(org_product_runtime_products.children, '[]')) AS child
                    )
                    SELECT COUNT(*)
                    FROM org_product_runtime_products
                    WHERE product_code <> '' AND product_name <> ''
                    """
                ).fetchone()[0]
                or 0
            )
        except sqlite3.Error as exc:
            violations.append(f"org_product_runtime_catalog_query_failed:{exc}")
            return tuple(violations)
        if row_count <= 0:
            violations.append("org_product_runtime_catalog_empty")
        return tuple(violations)
    finally:
        conn.close()


def org_product_runtime_catalog_violations_by_database(db_paths: tuple[Path, ...]) -> dict[Path, tuple[str, ...]]:
    return {
        db_path: violations
        for db_path in db_paths
        if (violations := org_product_runtime_catalog_violations(db_path))
    }


def canonical_expense_metric_tree_violations(db_path: Path) -> tuple[str, ...]:
    conn = sqlite3.connect(db_path)
    try:
        current_tables = set(list_current_tables(db_path))
        if "data_account_metric_node" not in current_tables:
            return ()
        from app.services.business_admin_expense_metric_tree import all_business_admin_expense_nodes
        from app.services.business_expense_evaluation_metric_tree import all_business_expense_evaluation_nodes

        expected_nodes = {
            str(node.node_code).strip().upper(): str(node.node_name).strip()
            for node in (*all_business_admin_expense_nodes(), *all_business_expense_evaluation_nodes())
        }
        actual_nodes = {
            str(row[0] or "").strip().upper(): str(row[1] or "").strip()
            for row in conn.execute(
                """
                SELECT node_code, node_name
                FROM data_account_metric_node
                WHERE (node_code LIKE 'AA.05.01%' OR node_code LIKE 'AA.05.02%')
                """
            )
        }
        violations: list[str] = []
        for code, name in sorted(expected_nodes.items()):
            if not code.startswith(("AA.05.01", "AA.05.02")):
                continue
            if code not in actual_nodes:
                violations.append(f"canonical_expense_missing:{code}")
            elif actual_nodes[code] != name:
                violations.append(f"canonical_expense_name_mismatch:{code}:{actual_nodes[code]}<>{name}")
            if len(violations) >= 20:
                return tuple(violations)
        legacy_corp_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM data_account_metric_node
                WHERE node_code='CORP.05.01'
                   OR node_code LIKE 'CORP.05.01.%'
                   OR node_code='CORP.05.02'
                   OR node_code LIKE 'CORP.05.02.%'
                """
            ).fetchone()[0]
            or 0
        )
        if legacy_corp_count:
            violations.append(f"canonical_expense_legacy_corp_nodes:{legacy_corp_count}")
        return tuple(violations)
    finally:
        conn.close()


def canonical_expense_metric_tree_violations_by_database(db_paths: tuple[Path, ...]) -> dict[Path, tuple[str, ...]]:
    return {
        db_path: violations
        for db_path in db_paths
        if (violations := canonical_expense_metric_tree_violations(db_path))
    }


def database_inventory(db_path: Path) -> tuple[TableInventoryRow, ...]:
    conn = sqlite3.connect(db_path)
    try:
        rows: list[TableInventoryRow] = []
        for table in list_current_tables(db_path):
            count = conn.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table)}").fetchone()[0]
            rows.append(TableInventoryRow(database=db_path, table=table, rows=int(count)))
        return tuple(rows)
    finally:
        conn.close()


def retired_tables_by_database(db_paths: tuple[Path, ...]) -> dict[Path, tuple[str, ...]]:
    return {db_path: existing_retired_tables(db_path) for db_path in db_paths}


def missing_tables_from_doc(db_paths: tuple[Path, ...], doc_path: Path) -> dict[Path, tuple[str, ...]]:
    text = doc_path.read_text(encoding="utf-8")
    missing: dict[Path, tuple[str, ...]] = {}
    for db_path in db_paths:
        tables = tuple(table for table in list_current_tables(db_path) if table not in text)
        if tables:
            missing[db_path] = tables
    return missing


def _section_text(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    next_heading = text.find("\n## ", start + len(heading))
    if next_heading < 0:
        return text[start:]
    return text[start:next_heading]


def _table_has_markdown_owner_line(table: str, section: str, *, database_name: str | None = None) -> bool:
    table_token = f"`{table}`"
    database_token = f"`{database_name}`" if database_name else None
    for line in section.splitlines():
        if not line.startswith("|") or table_token not in line:
            continue
        if database_token is not None and database_token not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and all(cell and set(cell) != {"-"} for cell in cells[:3]):
            return True
    return False


def _table_has_generic_markdown_owner_line(table: str, text: str) -> bool:
    table_token = f"`{table}`"
    bare_table_token = table
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        if table_token not in line and bare_table_token not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and all(cell and set(cell) != {"-"} for cell in cells[:3]):
            return True
    return False


def missing_tables_from_owner_doc(db_paths: tuple[Path, ...], doc_path: Path) -> dict[Path, tuple[str, ...]]:
    text = doc_path.read_text(encoding="utf-8")
    common_section = _section_text(text, "## Common DB Table Groups")
    annual_section = _section_text(text, "## Annual DB Tables")
    compare_section = _section_text(text, "## Compare DB Tables")
    missing: dict[Path, tuple[str, ...]] = {}
    for db_path in db_paths:
        database_name = db_path.name
        missing_tables: list[str] = []
        for table in list_current_tables(db_path):
            if database_name == "common.db":
                documented = _table_has_markdown_owner_line(table, common_section)
            elif database_name.startswith("budget_"):
                documented = _table_has_markdown_owner_line(
                    table,
                    annual_section,
                    database_name=database_name,
                )
            elif database_name == "compare.db":
                documented = _table_has_markdown_owner_line(table, compare_section)
            else:
                documented = _table_has_generic_markdown_owner_line(table, text)
            if not documented:
                missing_tables.append(table)
        if missing_tables:
            missing[db_path] = tuple(missing_tables)
    return missing


def render_inventory(db_paths: tuple[Path, ...], inventory_doc: Path | None = None) -> str:
    lines: list[str] = []
    for db_path in db_paths:
        lines.append(f"## {_display_path(db_path)}")
        inventory = database_inventory(db_path)
        lines.append(f"tables={len(inventory)}")
        for row in inventory:
            lines.append(f"{row.table}|{row.rows}")
        lines.append("")
    retired = retired_tables_by_database(db_paths)
    found = {db_path: tables for db_path, tables in retired.items() if tables}
    if found:
        lines.append("retired_tables=found")
        for db_path, tables in found.items():
            lines.append(f"{_display_path(db_path)}|{','.join(tables)}")
    else:
        lines.append("retired_tables=none")
    if inventory_doc is not None:
        missing_doc_tables = missing_tables_from_doc(db_paths, inventory_doc)
        if missing_doc_tables:
            lines.append("inventory_doc=missing_tables")
            for db_path, tables in missing_doc_tables.items():
                lines.append(f"{_display_path(db_path)}|{','.join(tables)}")
        else:
            lines.append("inventory_doc=ok")
        missing_owner_tables = missing_tables_from_owner_doc(db_paths, inventory_doc)
        if missing_owner_tables:
            lines.append("inventory_owner_doc=missing_tables")
            for db_path, tables in missing_owner_tables.items():
                lines.append(f"{_display_path(db_path)}|{','.join(tables)}")
        else:
            lines.append("inventory_owner_doc=ok")
        metric_identity_violations = metric_identity_violations_by_database(db_paths)
        if metric_identity_violations:
            lines.append("metric_identity_contract=failed")
            for db_path, violations in metric_identity_violations.items():
                lines.append(f"{_display_path(db_path)}|{';'.join(violations)}")
        else:
            lines.append("metric_identity_contract=ok")
        org_product_metric_violations = org_product_metric_guard_violations_by_database(db_paths)
        if org_product_metric_violations:
            lines.append("org_product_metric_guard=failed")
            for db_path, violations in org_product_metric_violations.items():
                lines.append(f"{_display_path(db_path)}|{';'.join(violations)}")
        else:
            lines.append("org_product_metric_guard=ok")
        org_product_runtime_ref_violations = org_product_metric_runtime_ref_violations_by_database(db_paths)
        if org_product_runtime_ref_violations:
            lines.append("org_product_metric_runtime_refs=failed")
            for db_path, violations in org_product_runtime_ref_violations.items():
                lines.append(f"{_display_path(db_path)}|{';'.join(violations)}")
        else:
            lines.append("org_product_metric_runtime_refs=ok")
        business_ref_violations = business_data_account_ref_violations_by_database(db_paths)
        if business_ref_violations:
            lines.append("business_data_account_refs=failed")
            for db_path, violations in business_ref_violations.items():
                lines.append(f"{_display_path(db_path)}|{';'.join(violations)}")
        else:
            lines.append("business_data_account_refs=ok")
        derived_ref_violations = derived_read_model_data_code_name_ref_violations_by_database(db_paths)
        if derived_ref_violations:
            lines.append("derived_read_model_data_code_name_refs=failed")
            for db_path, violations in derived_ref_violations.items():
                lines.append(f"{_display_path(db_path)}|{';'.join(violations)}")
        else:
            lines.append("derived_read_model_data_code_name_refs=ok")
        legacy_99_violations = legacy_second_segment_99_violations_by_database(db_paths)
        if legacy_99_violations:
            lines.append("legacy_second_segment_99=failed")
            for db_path, violations in legacy_99_violations.items():
                lines.append(f"{_display_path(db_path)}|{';'.join(violations)}")
        else:
            lines.append("legacy_second_segment_99=ok")
        canonical_expense_violations = canonical_expense_metric_tree_violations_by_database(db_paths)
        if canonical_expense_violations:
            lines.append("canonical_expense_metric_tree=failed")
            for db_path, violations in canonical_expense_violations.items():
                lines.append(f"{_display_path(db_path)}|{';'.join(violations)}")
        else:
            lines.append("canonical_expense_metric_tree=ok")
        org_product_runtime_catalog_violations = org_product_runtime_catalog_violations_by_database(db_paths)
        if org_product_runtime_catalog_violations:
            lines.append("org_product_runtime_catalog=failed")
            for db_path, violations in org_product_runtime_catalog_violations.items():
                lines.append(f"{_display_path(db_path)}|{';'.join(violations)}")
        else:
            lines.append("org_product_runtime_catalog=ok")
        workspace_menu_violations = retired_workspace_menu_violations()
        if workspace_menu_violations:
            lines.append("retired_workspace_menus=failed")
            lines.append(";".join(workspace_menu_violations))
        else:
            lines.append("retired_workspace_menus=ok")
    return "\n".join(lines).strip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print current SQLite table counts and fail if retired tables are present.",
    )
    parser.add_argument(
        "--db",
        action="append",
        type=Path,
        help="Database path to inspect. Can be repeated. Defaults to current var/data databases.",
    )
    parser.add_argument(
        "--inventory-doc",
        type=Path,
        help=(
            "Markdown inventory document that must mention every inspected table. "
            "Defaults to docs/development/current-database-inventory.md when default DBs are inspected."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_paths = tuple(path.resolve() for path in args.db) if args.db else DEFAULT_DATABASES
    inventory_doc = args.inventory_doc.resolve() if args.inventory_doc else (DEFAULT_INVENTORY_DOC if not args.db else None)
    missing = tuple(db_path for db_path in db_paths if not db_path.exists())
    if missing:
        for db_path in missing:
            print(f"missing_db={db_path}", file=sys.stderr)
        return 2
    if inventory_doc is not None and not inventory_doc.exists():
        print(f"missing_inventory_doc={inventory_doc}", file=sys.stderr)
        return 2

    print(render_inventory(db_paths, inventory_doc), end="")
    retired = retired_tables_by_database(db_paths)
    missing_doc_tables = missing_tables_from_doc(db_paths, inventory_doc) if inventory_doc is not None else {}
    missing_owner_tables = missing_tables_from_owner_doc(db_paths, inventory_doc) if inventory_doc is not None else {}
    metric_identity_violations = metric_identity_violations_by_database(db_paths) if inventory_doc is not None else {}
    org_product_metric_violations = org_product_metric_guard_violations_by_database(db_paths) if inventory_doc is not None else {}
    org_product_runtime_ref_violations = org_product_metric_runtime_ref_violations_by_database(db_paths) if inventory_doc is not None else {}
    business_ref_violations = business_data_account_ref_violations_by_database(db_paths) if inventory_doc is not None else {}
    derived_ref_violations = derived_read_model_data_code_name_ref_violations_by_database(db_paths) if inventory_doc is not None else {}
    canonical_expense_violations = canonical_expense_metric_tree_violations_by_database(db_paths) if inventory_doc is not None else {}
    org_product_runtime_catalog_violations = org_product_runtime_catalog_violations_by_database(db_paths) if inventory_doc is not None else {}
    workspace_menu_violations = retired_workspace_menu_violations() if inventory_doc is not None else ()
    return (
        1
        if any(tables for tables in retired.values())
        or missing_doc_tables
        or missing_owner_tables
        or metric_identity_violations
        or org_product_metric_violations
        or org_product_runtime_ref_violations
        or business_ref_violations
        or derived_ref_violations
        or canonical_expense_violations
        or org_product_runtime_catalog_violations
        or workspace_menu_violations
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
