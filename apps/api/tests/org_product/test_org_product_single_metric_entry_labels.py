from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_workspace_file(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def read_web_sources() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PROJECT_ROOT / "apps/web/src").rglob("*"))
        if path.suffix in {".ts", ".tsx"}
    )


def test_frontend_uses_org_product_metrics_as_only_configuration_entry() -> None:
    checked_files = [
        "apps/web/src/app/components/WorkArea.tsx",
        "apps/web/src/app/components/FormulaEditorDialog.tsx",
        "apps/web/src/app/components/BudgetDisplayReportContent.tsx",
        "apps/web/src/app/components/BusinessCostIncomeRatioAdminContent.tsx",
        "apps/web/src/app/components/OrgProductMetricContent.tsx",
        "apps/web/src/app/components/OrgProductDataEntryContent.tsx",
        "apps/web/src/app/workspaceCatalog.tsx",
        "apps/web/src/app/App.tsx",
    ]
    combined = "\n".join(read_workspace_file(path) for path in checked_files)

    forbidden_phrases = [
        "数据科目投影",
        "99潘潘费用类",
        "评审导入预览",
        "重建投影并刷新",
        "第二段 05 -> 99",
        "99目标编码",
        "/api/org-product-metrics/panpan99-page",
        "/api/org-product-metrics/data-account-projection",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined

    assert "机构及产品指标”为唯一配置入口" in combined
    assert "所有预算事实和报表直接使用同一套指标主键" in combined
    assert "确认并写入预算事实" in combined
    assert 'id: "org-product-metrics"' in combined
    assert 'label: "机构及产品指标"' in combined
    assert 'id: "data-account"' not in read_workspace_file("apps/web/src/app/workspaceCatalog.tsx")
    assert 'label: "数据科目运行表"' not in read_workspace_file("apps/web/src/app/workspaceCatalog.tsx")
    assert "listDataAccounts" not in read_workspace_file("apps/web/src/app/components/FormulaEditorDialog.tsx")
    assert "listDataAccounts" not in read_workspace_file("apps/web/src/app/components/BusinessCostIncomeRatioAdminContent.tsx")


def test_frontend_product_runtime_copy_does_not_reintroduce_product_maintenance_semantics() -> None:
    web_sources = read_web_sources()

    forbidden_phrases = [
        "productMaintenance",
        "maintenanceProduct",
        "MaintenanceProduct",
        "compareProductForMaintenance",
        "ProductTypeDto",
        "ProductTreeNode",
        "buildProductTree",
        "buildProductNodeIndex",
        "buildProductPathLabels",
        "buildProductLeafCodesByCode",
        "productTypes",
        "setProductTypes",
        "listProductTypes",
        "/api/product-types",
        "产品科目维护",
        "产品科目树",
        "05 保护",
        "05保护",
        "保护行不会出现在此处",
        "存量/兼容",
        "存量数据科目运行表",
        "未由机构产品指标确认",
        "数据科目运行表仅作为",
        "数据科目运行表（只读补充）",
        "历史状态兼容",
        "迁移底稿",
        "迁移待办",
        "migration-backlog",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in web_sources

    assert "/api/org-product-runtime-products" in web_sources
    assert "listOrgProductRuntimeProducts" in web_sources
    assert "DataProductContent" not in web_sources


def test_backend_product_runtime_response_model_does_not_use_legacy_product_type_name() -> None:
    router_source = read_workspace_file("apps/api/app/routers/org_product_runtime_catalog.py")
    org_product_metrics_source = read_workspace_file("apps/api/app/routers/org_product_metrics.py")
    schema_source = read_workspace_file("apps/api/app/schemas.py")
    auth_policy_source = read_workspace_file("apps/api/app/services/auth_access_policy.py")
    combined = f"{router_source}\n{schema_source}"

    assert "ProductTypeRow" not in combined
    assert "OrgProductRuntimeProductRow" in combined
    assert "list_org_product_runtime_products" in router_source
    assert '"/api/org-product-runtime-products"' in router_source
    assert '"/api/product-types"' not in router_source
    assert '"/api/product-types"' not in auth_policy_source
    assert "product_catalog_rows" not in org_product_metrics_source
    assert "org_product_runtime_catalog_rows" in org_product_metrics_source
    assert 'path.startswith("/api/dept-accounts") or path.startswith("/api/product-types")' not in auth_policy_source


def test_backend_product_runtime_modules_do_not_use_legacy_product_catalog_names() -> None:
    checked_files = [
        "apps/api/app/main.py",
        "apps/api/app/db_bootstrap/current_contracts.py",
        "apps/api/app/routers/org_product_metrics.py",
        "apps/api/app/routers/org_product_runtime_catalog.py",
        "apps/api/app/services/org_product_runtime_catalog.py",
    ]
    combined = "\n".join(read_workspace_file(path) for path in checked_files)

    forbidden_phrases = [
        "services.product_catalog",
        "routers.product_catalog",
        "product_catalog.py",
        "ProductCatalog",
        "list_product_catalog_rows",
        "sync_product_catalog_from_org_product_tree",
        "build_product_catalog_router",
        "ensure_product_type_tree_schema",
        "product_type_tree_schema",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined

    assert "ensure_org_product_runtime_catalog_schema" in combined


def test_product_runtime_docs_name_org_product_master_runtime_catalog_not_product_type_view() -> None:
    checked_files = [
        "CONTEXT.md",
        "docs/development/current-system-map.md",
        "docs/development/current-database-inventory.md",
        "docs/product/Banking_Budget_Database_PDD.md",
        "docs/product/Banking_Budget_Database_ERD.md",
        "docs/product/Banking_Budget_System_PDD.md",
        "docs/product/Banking_Budget_UI_Unified_PDD.md",
    ]
    combined = "\n".join(read_workspace_file(path) for path in checked_files)

    forbidden_phrases = [
        "ProductTypeView",
        "OrgProductRuntimeView",
        "只读兼容视图",
        "兼容读模型",
        "只读运行视图",
        "`product_type` 仅",
        "`product_type` 只",
        "数据科目页只保留",
        "数据科目运行表、机构及产品",
        "rebuild_data_accounts_from_org_product_metrics.py",
        "data_account_direct_rebuild_conflicts",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined

    assert "机构及产品主表" in combined
    assert "运行产品清单" in combined
    assert "旧“产品科目维护”物理表" in combined


def test_org_product_runtime_validation_surfaces_do_not_use_legacy_product_catalog_names() -> None:
    assert not (PROJECT_ROOT / "apps/api/test_product_catalog_router.py").exists()
    assert not (PROJECT_ROOT / "apps/api/scripts/export_org_product_metric_migration_backlog.py").exists()
    assert not (PROJECT_ROOT / "apps/api/test_org_product_metric_migration_backlog.py").exists()
    retired_migration_scripts = [
        "add_org_product_customer_io_metrics.py",
        "audit_org_product_metric_alignment.py",
        "confirm_org_product_metric_mappings.py",
        "fix_org_product_metric_source_conflicts.py",
        "seed_org_product_metric_tables.py",
    ]
    for script_name in retired_migration_scripts:
        assert not (PROJECT_ROOT / "apps/api/scripts" / script_name).exists()

    full_journey_source = read_workspace_file("apps/api/scripts/full_user_journey.py")
    simulation_test_source = read_workspace_file("apps/api/test_simulation_api.py")
    combined = f"{full_journey_source}\n{simulation_test_source}"

    forbidden_phrases = [
        '"list products"',
        '"product list"',
        "test_product_catalog_router",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined

    assert "list org-product runtime products" in full_journey_source
    assert "org-product runtime product list" in simulation_test_source


def test_runtime_ref_export_is_runtime_workbook_not_projection_template() -> None:
    web_api_source = read_workspace_file("apps/web/src/lib/masterDataApi.ts")
    export_service_source = read_workspace_file("apps/api/app/services/runtime_ref_export.py")

    forbidden = [
        "data_account_template_export.xlsx",
        "data_account_projection_export.xlsx",
        "数据科目投影",
        "投影说明",
    ]
    for phrase in forbidden:
        assert phrase not in web_api_source
        assert phrase not in export_service_source

    assert not (PROJECT_ROOT / "apps/api/app/routers/data_accounts.py").exists()
    assert "/api/data-accounts" not in web_api_source
    assert "data_account_runtime_export.xlsx" not in web_api_source
    assert 'ws.title = "机构及产品指标编码清单"' in export_service_source
    assert 'wb.create_sheet("运行说明", 0)' in export_service_source
    assert "机构及产品指标编码直接来自机构及产品指标体系主键" in export_service_source
    assert 'ws.title = "数据科目运行表"' not in export_service_source


def test_data_account_frontend_no_longer_exposes_direct_configuration_helpers() -> None:
    web_api_source = read_workspace_file("apps/web/src/lib/masterDataApi.ts")

    forbidden_api_helpers = [
        "DataAccountDto",
        "DataAccountMetricTreeDto",
        "listDataAccounts",
        "exportDataAccounts",
        "listDataAccountMetricTree",
        "dataAccountImportWorkflow",
        "createDataAccount(",
        "updateDataAccount(",
        "deleteDataAccount(",
        "createDataAccountMetricNode(",
        "DataAccountMetricNodeCreateDto",
        "isDataAccountCreateMetricNodeSelectable",
    ]
    for phrase in forbidden_api_helpers:
        assert phrase not in web_api_source

    assert not (PROJECT_ROOT / "apps/web/src/app/components/DataAccountCreateDialog.tsx").exists()
    assert not (PROJECT_ROOT / "apps/web/src/app/components/DataAccountContent.tsx").exists()
    assert not (PROJECT_ROOT / "apps/web/src/app/components/DataAccountMetricNodeDialog.tsx").exists()
    assert not (PROJECT_ROOT / "apps/web/src/app/components/DataAccountMetricPicker.tsx").exists()
    assert not (PROJECT_ROOT / "apps/web/src/app/components/DataAccountMetricNavigator.tsx").exists()
    assert not (PROJECT_ROOT / "apps/web/src/app/components/DataAccountTableControls.tsx").exists()
    assert not (PROJECT_ROOT / "apps/web/src/app/components/DataAccountTableHeader.tsx").exists()
    assert not (PROJECT_ROOT / "apps/web/src/app/components/OrgProductPanpan99ExpenseContent.tsx").exists()
    assert not (PROJECT_ROOT / "apps/web/src/lib/dataAccountViewModel.ts").exists()
    assert not (PROJECT_ROOT / "apps/web/e2e/data-account-view-model.spec.ts").exists()


def test_workspace_catalog_exposes_single_org_product_configuration_path() -> None:
    workspace_source = read_workspace_file("apps/web/src/app/workspaceCatalog.tsx")

    forbidden_labels = [
        'label: "产品科目维护"',
        'label: "数据科目维护"',
        'label: "数据科目运行表"',
        '{ id: "data-account"',
        'label: "预算/实际数据跑批"',
        "DataProductContent",
    ]
    for phrase in forbidden_labels:
        assert phrase not in workspace_source

    required_labels = [
        '{ id: "org-product-tree", label: "机构及产品"',
        '{ id: "org-product-metrics", label: "机构及产品指标"',
        '{ id: "budget-actual-batch", label: "预算事实刷新跑批"',
    ]
    for phrase in required_labels:
        assert phrase in workspace_source


def test_backend_guidance_does_not_send_users_back_to_projection_or_data_account_config() -> None:
    checked_files = [
        "apps/api/app/services/budget_output_display.py",
        "apps/api/app/agent_product_intent.py",
        "apps/api/app/agent_prompt_assets.py",
        "apps/api/app/agent_query.py",
        "apps/api/app/services/expense_forecast_rule_import.py",
        "apps/api/app/routers/templates.py",
        "apps/api/app/routers/dept_catalog.py",
        "apps/api/app/routers/budget_simulation.py",
        "apps/api/app/routers/org_product_metrics.py",
        "apps/api/app/services/business_cost_income_commands.py",
    ]
    combined = "\n".join(read_workspace_file(path) for path in checked_files)

    forbidden_phrases = [
        "请先到数据科目维护页",
        "从数据科目维护表选择",
        "数据科目指标树导出流程",
        "标准数据科目指标树",
        "Excel导入同步数据科目指标树节点",
        "数据科目投影",
        "机构及产品指标投影",
        "panpan99-page",
        "data-account-projection",
        "migration-backlog",
        "迁移待办",
        "迁移底稿",
        "05 费用保护行",
        "PROTECTED_05_REVIEW_ONLY",
        '"data_acct_temp":',
        ' / "data_acct_temp.xlsx"',
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined

    assert "请先到机构及产品指标维护唯一指标体系" in combined
    assert "从已确认机构产品指标选择" in combined
    assert "机构及产品指标导出流程" in combined
    assert "机构及产品指标节点" in combined
    assert ' / "dept_acct_temp.xlsx"' in combined


def test_current_docs_do_not_list_retired_org_product_metric_migration_scripts() -> None:
    combined = "\n".join(
        read_workspace_file(path)
        for path in [
            "docs/development/current-system-map.md",
            "docs/product/Banking_Budget_Files.md",
        ]
    )

    forbidden_script_names = [
        "add_org_product_customer_io_metrics.py",
        "audit_org_product_metric_alignment.py",
        "confirm_org_product_metric_mappings.py",
        "export_org_product_metric_migration_backlog.py",
        "fix_org_product_metric_source_conflicts.py",
        "seed_org_product_metric_tables.py",
    ]
    for script_name in forbidden_script_names:
        assert script_name not in combined


def test_data_account_independent_write_and_backfill_services_are_retired() -> None:
    retired_paths = [
        "apps/api/app/services/data_account_commands.py",
        "apps/api/app/services/data_account_import.py",
        "apps/api/app/services/data_account_metric_tree.py",
        "apps/api/app/services/data_account_write_workflow.py",
        "apps/api/app/db_bootstrap/data_account_metric_tree.py",
        "apps/api/app/db_bootstrap/projections.py",
        "apps/api/app/data_account_write.py",
        "apps/api/test_data_account_commands.py",
        "apps/api/test_data_account_import.py",
        "apps/api/test_data_account_metric_tree.py",
        "apps/api/test_data_account_write.py",
    ]
    for path in retired_paths:
        assert not (PROJECT_ROOT / path).exists()

    runtime_sync_source = read_workspace_file("apps/api/app/services/org_product_metric_runtime_sync.py")
    metric_tree_bootstrap_source = read_workspace_file("apps/api/app/db_bootstrap/runtime_metric_tree.py")
    init_db_source = read_workspace_file("apps/api/app/init_db.py")
    combined = f"{runtime_sync_source}\n{metric_tree_bootstrap_source}\n{init_db_source}"
    retired_backfill_markers = [
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
        "DATA_DICTIONARY_SEED",
        "预算事实引用回收机构及产品指标主表",
        "由数据科目运行主键收回机构及产品指标主表",
    ]
    for marker in retired_backfill_markers:
        assert marker not in combined

    framework_master_sync_source = read_workspace_file(
        "apps/api/app/services/expense_budget_execution_master_sync.py"
    )
    retired_framework_master_write_markers = [
        "data_account_upserts",
        "build_framework_master_plan_from_accounts",
        "_load_existing_data_accounts",
        "INSERT INTO data_account",
        "数据科目同步",
    ]
    for marker in retired_framework_master_write_markers:
        assert marker not in framework_master_sync_source

    assert "assert_all_runtime_metric_refs_are_confirmed_org_product_metrics" in combined
    assert "from app.db_bootstrap.derived_read_models import" in init_db_source
