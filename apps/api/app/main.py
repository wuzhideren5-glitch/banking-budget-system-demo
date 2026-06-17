from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.audit import write_operation_log
from app.agent.agent_graph import AgentGraphService
from app.agent.agent_debug_trace import AgentDebugTraceStore
from app.agent.agent_memory import ConversationMemoryStore
from app.agent.agent_query import ReadOnlySqlExecutor
from app.budget_data_writer import purge_disallowed_budget_data_for_version
from app.core.config import settings
from app.integrations.deepseek_client import DeepseekClient
from app.core.db_paths import budget_db_path, common_db_path, compare_db_path, list_budget_database_files
from app.formula_refs import extract_runtime_metric_ref_code
from app.integrations.feishu_bot import start_feishu_background
from app.init_db import BUDGET_SCHEMA, ensure_databases
from app.knowledge_base import KnowledgeBaseService
from app.core.passwords import hash_daily_password, verify_daily_password
from app.services.compare_export_service import CompareExportService
from app.services.budget_summary_rebuild import rebuild_budget_summary_for_version
from app.services.compare_summary_sync import CompareSummarySyncService
from app.services.metric_tree_rollups import (
    estimate_metric_tree_rollups as estimate_metric_tree_rollups_service,
    rebuild_metric_tree_rollups as rebuild_metric_tree_rollups_service,
)
from app.services.formula_engine import normalize_formula, try_calculate_formula_value
from app.services.global_refresh_status import (
    collect_global_refresh_status,
    last_budget_or_compare_calc_time,
    set_budget_refresh_time,
    set_compare_refresh_time,
)
from app.services.budget_summary_export_service import BudgetSummaryExportService
from app.services.budget_actual_batch import (
    formula_rows_for_budget_actual_batch_product,
    recalculate_budget_actual_batch_product_formula_rows,
)
from app.services.budget_fact_periods import load_budget_fact_period_month_map_from_path
from app.services.smart_ppt_service import SmartPptService
from app.services.smart_report_service import SmartReportService
from app.services.auth_sessions import load_auth_session_context
from app.services.auth_access_policy import (
    role_name_from_permission,
    validate_password_policy,
)
from app.services.auth_request_middleware import build_auth_request_middleware
from app.services.department_expense_contracts import validate_dept_code_with_parent
from app.services.system_catalog import parse_year_from_budget_filename, resolve_system_database_file_name
from app.services.system_versions import load_chart_version_options
from app.services.export_common import (
    color_worksheet_row_font,
    normalize_excel_cell,
)
from app.routers.agent_runtime import build_agent_runtime_router
from app.routers.agent_debug import build_agent_debug_router
from app.routers.auth import build_auth_router
from app.routers.budget_subject_catalog import build_budget_subject_catalog_router
from app.routers.dept_catalog import build_dept_catalog_router
from app.routers.budget_actual_batch import build_budget_actual_batch_router
from app.routers.intelligent_budget_simulation import build_intelligent_budget_simulation_router
from app.routers.budget_simulation import build_budget_simulation_router
from app.routers.budget_output import build_budget_output_router
from app.routers.bi_subject_mapping import build_bi_ai_subject_mapping_router
from app.routers.business_cost_income_ratio import build_business_cost_income_ratio_router
from app.routers.input_output_topic_overview import build_input_output_topic_overview_router
from app.routers.org_product_tree import router as org_product_tree_router
from app.routers.org_product_metric_config import router as org_product_metric_config_router
from app.routers.org_product_report_import import router as org_product_report_import_router
from app.routers.org_product_data_entry import router as org_product_data_entry_router
from app.routers.org_product_output import router as org_product_output_router
from app.routers.bi_department_mapping import build_bi_department_mapping_router
from app.routers.expense_actual_import import build_expense_actual_import_router
from app.routers.expense_budget_entry import build_expense_budget_entry_router
from app.routers.expense_budget_execution import build_expense_budget_execution_router
from app.routers.expense_forecast import build_expense_forecast_router
from app.routers.global_refresh_status import build_global_refresh_status_router
from app.routers.budget_summary_export import build_budget_summary_export_router
from app.routers.budget_summary_compare import build_budget_summary_compare_router
from app.routers.compare_summary_export import build_compare_summary_export_router
from app.routers.chart_readonly import build_chart_readonly_router
from app.routers.chart_write import build_chart_write_router
from app.routers.health import router as health_router
from app.routers.org_product_runtime_catalog import build_org_product_runtime_catalog_router
from app.routers.smart_ppt import build_smart_ppt_router
from app.routers.smart_reports import build_smart_reports_router
from app.routers.system_admin import build_system_admin_router
from app.routers.system_catalog import build_system_catalog_router
from app.routers.system_edit_show import build_system_edit_show_router
from app.routers.templates import router as templates_router
from app.routers.version_snapshot import build_version_snapshot_router
from app.services.version_snapshot import (
    load_editable_version_context,
    load_latest_version_in_path,
    load_version_name_and_current_month_from_file,
)
from app.schemas import (
    ChartVersionItemDto,
    GlobalRefreshStatusResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_databases()
    start_feishu_background(agent_service)
    yield


app = FastAPI(title="Banking Budget API", lifespan=lifespan)
_cors_regex = (settings.cors_origin_regex or "").strip()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_origin_regex=_cors_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(templates_router)

kb_service = KnowledgeBaseService(settings.knowledge_base_dir)
smart_ppt_service = SmartPptService(data_dir=settings.data_dir)
smart_report_service = SmartReportService(data_dir=settings.data_dir, smart_ppt_service=smart_ppt_service)
smart_ppt_service.smart_report_service = smart_report_service
query_executor = ReadOnlySqlExecutor(
    budget_db_path=budget_db_path(settings.budget_year),
    common_db_path=common_db_path(),
)
memory_store = ConversationMemoryStore(settings.knowledge_base_dir)
agent_debug_trace_store = AgentDebugTraceStore(settings.agent_log_dir / "agent_llm_events.jsonl")
deepseek_client = DeepseekClient(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_base_url,
    model=settings.deepseek_model,
)
smart_report_service.deepseek_client = deepseek_client
agent_service = AgentGraphService(
    kb_service,
    query_executor=query_executor,
    memory_store=memory_store,
    deepseek_client=deepseek_client,
    debug_trace_store=agent_debug_trace_store,
    intent_trace_path=settings.agent_log_dir / "intent_router_trace.jsonl",
)
app.include_router(build_agent_runtime_router(agent_service, memory_store))
app.include_router(build_agent_debug_router(agent_debug_trace_store))

SESSION_COOKIE_NAME = "budget_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
_periodic_global_refresh_next_run_at: str | None = None


async def _editable_context() -> tuple[Path, int, int]:
    return await load_editable_version_context(common_db_path(), settings.data_dir)


async def _last_calc_time(path: Path | None = None) -> str | None:
    budget_path = path if path is not None else budget_db_path(settings.budget_year)
    return await last_budget_or_compare_calc_time(
        budget_path=budget_path,
        compare_path=compare_db_path(),
    )


async def _load_year_period_months(year: int) -> dict[int, int]:
    return await load_budget_fact_period_month_map_from_path(
        common_db_path(),
        year=year,
    )


compare_summary_sync_service = CompareSummarySyncService(
    set_compare_refresh_time=lambda ts: set_compare_refresh_time(compare_db_path(), ts),
)
budget_summary_export_service = BudgetSummaryExportService(
    editable_context_provider=_editable_context,
)
compare_export_service = CompareExportService()


async def _collect_global_refresh_status() -> GlobalRefreshStatusResponse:
    return await collect_global_refresh_status(
        budget_paths=list_budget_database_files(),
        compare_path=compare_db_path(),
        parse_year_from_budget_filename=parse_year_from_budget_filename,
        next_planned_refresh_time=_periodic_global_refresh_next_run_at,
    )


app.include_router(build_global_refresh_status_router(_collect_global_refresh_status))

async def _recalculate_product_formula_rows(
    product_code: str,
    version_id: int,
    budget_actual: int,
    *,
    budget_path: Path | None = None,
    budget_year: int | None = None,
) -> int:
    resolved_budget_year = budget_year if budget_year is not None else settings.budget_year
    resolved_budget_path = budget_path if budget_path is not None else budget_db_path(resolved_budget_year)
    return await recalculate_budget_actual_batch_product_formula_rows(
        product_code=product_code,
        version_id=version_id,
        budget_actual=budget_actual,
        budget_path=resolved_budget_path,
        budget_year=resolved_budget_year,
        common_path=common_db_path(),
    )


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _load_current_auth_session(session_id: str | None) -> dict[str, object] | None:
    return await load_auth_session_context(
        common_db=common_db_path(),
        session_id=session_id,
        now=_iso_now(),
    )


app.middleware("http")(
    build_auth_request_middleware(
        session_cookie_name=SESSION_COOKIE_NAME,
        load_session_context=_load_current_auth_session,
    )
)


app.include_router(
    build_auth_router(
        settings=settings,
        session_cookie_name=SESSION_COOKIE_NAME,
        session_ttl_seconds=SESSION_TTL_SECONDS,
        verify_daily_password=verify_daily_password,
        hash_daily_password=hash_daily_password,
        validate_password_policy=validate_password_policy,
        role_name_from_permission=role_name_from_permission,
        iso_now=_iso_now,
        editable_context_provider=_editable_context,
        latest_version_in_path_provider=load_latest_version_in_path,
        last_calc_time_provider=_last_calc_time,
    )
)
app.include_router(
    build_version_snapshot_router(
        lambda data_file_name, version_id: load_version_name_and_current_month_from_file(
            settings.data_dir,
            data_file_name,
            version_id,
        )
    )
)
app.include_router(
    build_smart_reports_router(
        service=smart_report_service,
        write_operation_log=lambda **kwargs: write_operation_log(**kwargs),
    )
)
app.include_router(
    build_smart_ppt_router(
        service=smart_ppt_service,
    )
)


async def _chart_version_options() -> list[ChartVersionItemDto]:
    return await load_chart_version_options(common_db=common_db_path(), data_dir=settings.data_dir)


app.include_router(build_chart_readonly_router(_chart_version_options))


app.include_router(
    build_chart_write_router(
        chart_version_options_provider=_chart_version_options,
        extract_runtime_metric_ref_code_from_name=extract_runtime_metric_ref_code,
    )
)


app.include_router(
    build_budget_simulation_router(
        editable_context_provider=lambda: _editable_context(),
        get_year_period_months=lambda year: _load_year_period_months(year),
    )
)
app.include_router(build_intelligent_budget_simulation_router(deepseek_client=deepseek_client))

app.include_router(
    build_budget_actual_batch_router(
        editable_context_provider=lambda: _editable_context(),
        formula_rows_for_product=lambda *args, **kwargs: formula_rows_for_budget_actual_batch_product(*args, **kwargs),
        recalculate_product_formula_rows=lambda *args, **kwargs: _recalculate_product_formula_rows(*args, **kwargs),
        estimate_metric_tree_rollups=lambda **kwargs: estimate_metric_tree_rollups_service(
            common_path=common_db_path(),
            **kwargs,
        ),
        rebuild_metric_tree_rollups=lambda **kwargs: rebuild_metric_tree_rollups_service(
            common_path=common_db_path(),
            **kwargs,
        ),
        rebuild_budget_summary_for_version=(
            lambda version_id, budget_path: rebuild_budget_summary_for_version(version_id, budget_path)
        ),
        sync_compare_budget_summary=lambda **kwargs: compare_summary_sync_service.sync(**kwargs),
        set_budget_refresh_time=lambda budget_path, ts: set_budget_refresh_time(budget_path, ts),
        iso_now=lambda: _iso_now(),
        write_operation_log=lambda **kwargs: write_operation_log(**kwargs),
    )
)


app.include_router(
    build_budget_summary_compare_router(
        editable_context_provider=lambda: _editable_context(),
    )
)
app.include_router(
    build_budget_output_router(
        editable_context_provider=lambda: _editable_context(),
        data_dir=settings.data_dir,
    )
)
app.include_router(
    build_compare_summary_export_router(
        export_compare_pivot_aggregate_callable=compare_export_service.export_compare_pivot_aggregate,
    )
)
app.include_router(
    build_system_catalog_router(
        settings=settings,
        budget_schema=BUDGET_SCHEMA,
        get_year_period_months=lambda year: _load_year_period_months(year),
        iso_now=lambda: _iso_now(),
    )
)
app.include_router(
    build_system_admin_router(
        settings=settings,
        resolve_data_file_name=lambda data_file_id: resolve_system_database_file_name(
            common_db_path(),
            data_file_id,
        ),
        parse_year_from_budget_filename=lambda file_name: parse_year_from_budget_filename(file_name),
        get_year_period_months=lambda year: _load_year_period_months(year),
        iso_now=lambda: _iso_now(),
        purge_disallowed_budget_data_for_version=purge_disallowed_budget_data_for_version,
        validate_password_policy=validate_password_policy,
    )
)
app.include_router(
    build_system_edit_show_router()
)
app.include_router(
    build_budget_subject_catalog_router(
        write_operation_log=lambda **kwargs: write_operation_log(**kwargs),
    )
)
app.include_router(
    build_expense_actual_import_router(
        write_operation_log=lambda **kwargs: write_operation_log(**kwargs),
    )
)
app.include_router(
    build_expense_budget_entry_router(
        write_operation_log=lambda **kwargs: write_operation_log(**kwargs),
    )
)
app.include_router(build_bi_ai_subject_mapping_router())
app.include_router(
    build_expense_forecast_router(
        default_year=settings.budget_year,
        write_operation_log=lambda **kwargs: write_operation_log(**kwargs),
    )
)
app.include_router(build_bi_department_mapping_router())
app.include_router(
    build_business_cost_income_ratio_router(
        write_operation_log=lambda **kwargs: write_operation_log(**kwargs),
    )
)
app.include_router(build_input_output_topic_overview_router())
app.include_router(org_product_tree_router)
app.include_router(org_product_metric_config_router)
app.include_router(org_product_report_import_router)
app.include_router(org_product_data_entry_router)
app.include_router(org_product_output_router)
app.include_router(
    build_org_product_runtime_catalog_router(
        write_operation_log=lambda **kwargs: write_operation_log(**kwargs),
    )
)
app.include_router(
    build_dept_catalog_router(
        normalize_cell=normalize_excel_cell,
        color_row=color_worksheet_row_font,
        validate_dept_code_with_parent=validate_dept_code_with_parent,
        write_operation_log=lambda **kwargs: write_operation_log(**kwargs),
    )
)
app.include_router(
    build_budget_summary_export_router(
        export_budget_pivot_aggregate=budget_summary_export_service.export_budget_pivot_aggregate,
    )
)
app.include_router(
    build_expense_budget_execution_router(
        editable_context_provider=lambda: _editable_context(),
    )
)

