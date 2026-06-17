from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.schemas import (
    BudgetOutputDisplayConfigCreate,
    BudgetOutputDisplayConfigImportResponse,
    BudgetOutputDisplayConfigItemDto,
    BudgetOutputDisplayConfigResponse,
    BudgetOutputDisplayConfigUpdate,
    BudgetOutputDisplayReportResponse,
)
from app.services.export_common import workbook_streaming_response
from app.services.budget_output_display_config import (
    BudgetOutputDisplayConfigCreateCommand,
    BudgetOutputDisplayConfigError,
    BudgetOutputDisplayConfigUpdateCommand,
    apply_budget_output_display_config_item_create,
    apply_budget_output_display_config_item_delete,
    apply_budget_output_display_config_item_update,
    apply_budget_output_display_config_import_upload,
    build_budget_output_display_config_export_workbook,
    load_budget_output_display_config_response,
    rebuild_budget_output_display_config_from_org_product_metrics,
    rebuild_budget_output_display_config_from_excel,
)
from app.services.budget_output_display import (
    build_budget_output_display_report,
)
from app.services.budget_output_export import build_budget_output_display_report_export
from app.core.db_paths import common_db_path


def build_budget_output_router(
    *,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
    data_dir: Path,
) -> APIRouter:
    router = APIRouter()

    def _http_error(exc: BudgetOutputDisplayConfigError) -> HTTPException:
        return HTTPException(status_code=exc.status_code, detail=exc.detail)

    @router.get("/api/budget-output/display-config", response_model=BudgetOutputDisplayConfigResponse)
    async def get_budget_output_display_config():
        return await load_budget_output_display_config_response()

    @router.get("/api/budget-output/display-config/export")
    async def export_budget_output_display_config():
        wb = await build_budget_output_display_config_export_workbook()
        return workbook_streaming_response(
            wb,
            filename="预算展示配置导入模板.xlsx",
            fallback_filename="budget-display-config.xlsx",
        )

    @router.post("/api/budget-output/display-config/import", response_model=BudgetOutputDisplayConfigImportResponse)
    async def import_budget_output_display_config(
        file: UploadFile = File(...),
        mode: str = Form("replace"),
    ):
        file_name = file.filename or "budget-display-config.xlsx"
        raw = await file.read()
        return await apply_budget_output_display_config_import_upload(file_name=file_name, raw=raw, mode=mode)

    @router.post("/api/budget-output/display-config/rebuild-from-org-product")
    async def rebuild_budget_output_display_config():
        budget_path, _, _ = await editable_context_provider()
        effective_budget = budget_path if budget_path.exists() else None
        codes_json_path = common_db_path().parent / "budget_display_codes.json"
        if codes_json_path.exists():
            return await rebuild_budget_output_display_config_from_excel(
                budget_path=effective_budget,
                codes_json_path=codes_json_path,
            )
        # 回退：budget_display_codes.json 不存在，用 DB 指标树直接重建
        return await rebuild_budget_output_display_config_from_org_product_metrics(
            budget_path=effective_budget,
        )

    @router.post("/api/budget-output/display-config/items", response_model=BudgetOutputDisplayConfigItemDto)
    async def create_budget_output_display_item(payload: BudgetOutputDisplayConfigCreate):
        try:
            return await apply_budget_output_display_config_item_create(
                BudgetOutputDisplayConfigCreateCommand(
                    data_acct_code=payload.data_acct_code,
                    display_name=payload.display_name,
                    parent_row_key=payload.parent_row_key,
                    insert_after_row_key=payload.insert_after_row_key,
                    display_view=payload.display_view,
                    sort_order=payload.sort_order,
                    org_product_ref=payload.org_product_ref,
                    org_product_entity_code=payload.org_product_entity_code,
                    org_product_table_name=payload.org_product_table_name,
                    org_product_metric_code=payload.org_product_metric_code,
                    org_product_metric_name=payload.org_product_metric_name,
                )
            )
        except BudgetOutputDisplayConfigError as exc:
            raise _http_error(exc) from exc

    @router.patch("/api/budget-output/display-config/items/{row_key}", response_model=BudgetOutputDisplayConfigItemDto)
    async def update_budget_output_display_item(row_key: str, payload: BudgetOutputDisplayConfigUpdate):
        try:
            return await apply_budget_output_display_config_item_update(
                row_key,
                BudgetOutputDisplayConfigUpdateCommand(
                    data_acct_code=payload.data_acct_code,
                    display_name=payload.display_name,
                    sort_order=payload.sort_order,
                    is_active=payload.is_active,
                ),
            )
        except BudgetOutputDisplayConfigError as exc:
            raise _http_error(exc) from exc

    @router.delete("/api/budget-output/display-config/items/{row_key}")
    async def delete_budget_output_display_item(row_key: str):
        try:
            return await apply_budget_output_display_config_item_delete(row_key)
        except BudgetOutputDisplayConfigError as exc:
            raise _http_error(exc) from exc

    @router.get("/api/budget-output/display-report", response_model=BudgetOutputDisplayReportResponse)
    async def get_budget_output_display_report(
        year: int | None = Query(None),
        budget_version_id: int | None = Query(None),
        forecast_version_ids: list[int] | None = Query(None),
        product_codes: list[str] | None = Query(None),
    ):
        return await build_budget_output_display_report(
            year=year,
            budget_version_id=budget_version_id,
            forecast_version_ids=forecast_version_ids,
            product_codes=product_codes,
            editable_context_provider=editable_context_provider,
            data_dir=data_dir,
        )

    @router.get("/api/budget-output/display-report/export-full")
    async def export_budget_output_display_report_full(
        year: int | None = Query(None),
        budget_version_id: int | None = Query(None),
        forecast_version_ids: list[int] | None = Query(None),
    ):
        export = await build_budget_output_display_report_export(
            year=year,
            budget_version_id=budget_version_id,
            forecast_version_ids=forecast_version_ids,
            editable_context_provider=editable_context_provider,
            data_dir=data_dir,
        )
        return workbook_streaming_response(
            export.workbook,
            filename=export.filename,
            fallback_filename="budget-display-report.xlsx",
        )

    return router
