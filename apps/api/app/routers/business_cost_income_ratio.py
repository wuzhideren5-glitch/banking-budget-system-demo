from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, computed_field

from app.core.config import settings
from app.services.export_common import workbook_streaming_response
from app.services.business_cost_income_import import (
    FIELD_LABELS,
    build_bcir_actual_import_template_workbook,
    parse_months,
    run_bcir_actual_excel_import,
)
from app.services.business_cost_income_commands import (
    create_business_cost_income_indicator,
    create_business_cost_income_item,
    delete_business_cost_income_indicator,
    delete_business_cost_income_item,
    list_business_cost_income_indicator_configs,
    list_business_cost_income_item_configs,
    reorder_business_cost_income_indicators,
    reorder_business_cost_income_items,
    update_business_cost_income_indicator,
    update_business_cost_income_item,
    upsert_business_cost_income_value,
)
from app.services.business_cost_income_ratio import (
    build_business_cost_income_ratio_report,
    load_business_cost_income_meta_options,
)

SectionType = Literal["indicator", "input", "output"]
ItemSectionType = Literal["input", "output"]
ValueFieldType = Literal["actual", "budget", "forecast"]
IndicatorFormatType = Literal["ratio", "percent", "number"]
EntryModeType = Literal["manual", "manual_preferred", "computed", "rollup", "binding", "indicator"]
ManualEntryModeType = Literal["disabled", "manual", "manual_preferred"]


def _command_http_error(error: Exception) -> HTTPException:
    status_code = 404 if isinstance(error, LookupError) else 400
    return HTTPException(status_code=status_code, detail=str(error))


class BusinessCostIncomeRatioMetaResponse(BaseModel):
    entity_options: list[str] = Field(default_factory=list)
    product_options: list[dict[str, str]] = Field(default_factory=list)
    group_options: list[str] = Field(default_factory=list)
    amount_unit_options: list[dict[str, str]] = Field(default_factory=list)


class BusinessCostIncomeRatioMetricsDto(BaseModel):
    current_actual: float
    annual_budget: float
    budget_progress: float | None
    annual_forecast: float
    forecast_budget_gap: float
    gap_rate: float | None
    yoy_change: float
    yoy_rate: float | None
    last_year_actual: float


class BusinessCostIncomeRatioMonthlyEntryDto(BaseModel):
    month_actual: float
    month_budget: float
    month_forecast: float


class BusinessCostIncomeRatioRowDto(BaseModel):
    section: SectionType
    id: int
    name: str
    parent_id: int | None = None
    is_leaf: bool = True
    entry_mode: EntryModeType = "indicator"
    topic_metric_node_code: str | None = None
    data_acct_code: str = ""
    org_product_ref: str = ""
    org_product_entity_code: str = ""
    org_product_table_name: str = ""
    org_product_metric_code: str = ""
    org_product_metric_name: str = ""
    sort_order: int
    enabled: bool
    metrics: BusinessCostIncomeRatioMetricsDto
    monthly_entry: BusinessCostIncomeRatioMonthlyEntryDto

    @computed_field
    @property
    def metric_code(self) -> str:
        return self.org_product_metric_code or self.data_acct_code

    @computed_field
    @property
    def metric_name(self) -> str:
        return self.org_product_metric_name or self.name


class BusinessCostIncomeRatioReportResponse(BaseModel):
    report_month: str
    entity_name: str
    group_name: str | None = None
    product_code: str | None = None
    amount_unit: str
    amount_unit_label: str
    rows: list[BusinessCostIncomeRatioRowDto] = Field(default_factory=list)
    note: str = ""


class BusinessCostIncomeRatioCellUpsertRequest(BaseModel):
    year_month: str
    entity_name: str
    group_name: str | None = None
    product_code: str | None = None
    amount_unit: str = "yuan"
    item_section: ItemSectionType
    item_id: int
    field: ValueFieldType
    value: float


class BusinessCostIncomeRatioCellUpsertResponse(BaseModel):
    updated: bool


class BusinessCostIncomeRatioActualImportPreviewItemDto(BaseModel):
    row_number: int
    sheet_name: str = ""
    field: str = ""
    field_label: str = ""
    entity_name: str
    group_name: str = ""
    product_code: str
    section: str
    item_id: int | None = None
    item_name: str = ""
    month: int | None = None
    value_text: str = ""
    action: str
    message: str | None = None


class BusinessCostIncomeRatioActualImportPreviewResponse(BaseModel):
    file_name: str
    year: int
    preview_count: int
    insertable_cells: int
    updatable_cells: int = 0
    skipped_cells: int
    error_cells: int
    items: list[BusinessCostIncomeRatioActualImportPreviewItemDto] = Field(default_factory=list)


class BusinessCostIncomeRatioActualImportApplyResponse(BaseModel):
    file_name: str
    year: int
    saved_cells: int
    skipped_cells: int
    error_cells: int


class BusinessCostIncomeRatioItemDto(BaseModel):
    id: int
    product_code: str = ""
    section: ItemSectionType
    name: str
    parent_id: int | None = None
    display_group: bool = False
    data_acct_code: str = ""
    org_product_ref: str = ""
    org_product_entity_code: str = ""
    org_product_table_name: str = ""
    org_product_metric_code: str = ""
    org_product_metric_name: str = ""
    manual_entry_mode: ManualEntryModeType = "disabled"
    value_mode: Literal["tree", "self", "self_and_tree"] = "tree"
    entry_mode: EntryModeType | None = None
    sort_order: int
    enabled: bool

    @computed_field
    @property
    def metric_code(self) -> str:
        return self.org_product_metric_code or self.data_acct_code

    @computed_field
    @property
    def metric_name(self) -> str:
        return self.org_product_metric_name or self.name


class BusinessCostIncomeRatioItemCreateRequest(BaseModel):
    product_code: str | None = None
    section: ItemSectionType
    name: str = ""
    parent_id: int | None = None
    display_group: bool = False
    data_acct_code: str | None = None
    org_product_ref: str | None = None
    org_product_entity_code: str | None = None
    org_product_table_name: str | None = None
    org_product_metric_code: str | None = None
    org_product_metric_name: str | None = None
    manual_entry_mode: ManualEntryModeType = "disabled"
    value_mode: Literal["tree", "self", "self_and_tree"] = "tree"
    sort_order: int = 0
    enabled: bool = True


class BusinessCostIncomeRatioItemUpdateRequest(BaseModel):
    product_code: str | None = None
    name: str
    parent_id: int | None = None
    display_group: bool = False
    data_acct_code: str | None = None
    org_product_ref: str | None = None
    org_product_entity_code: str | None = None
    org_product_table_name: str | None = None
    org_product_metric_code: str | None = None
    org_product_metric_name: str | None = None
    manual_entry_mode: ManualEntryModeType = "disabled"
    value_mode: Literal["tree", "self", "self_and_tree"] = "tree"
    sort_order: int = 0
    enabled: bool = True


class BusinessCostIncomeRatioIndicatorDto(BaseModel):
    id: int
    product_code: str = ""
    name: str
    parent_id: int | None = None
    display_group: bool = False
    topic_metric_node_code: str | None = None
    numerator_section: ItemSectionType
    numerator_item_id: int
    numerator_value_mode: Literal["tree", "self", "self_and_tree"] = "tree"
    denominator_section: ItemSectionType
    denominator_item_id: int
    denominator_value_mode: Literal["tree", "self", "self_and_tree"] = "tree"
    format: IndicatorFormatType
    annualize: bool = False
    sort_order: int
    enabled: bool


class BusinessCostIncomeRatioIndicatorCreateRequest(BaseModel):
    product_code: str | None = None
    name: str
    parent_id: int | None = None
    display_group: bool = False
    topic_metric_node_code: str | None = None
    numerator_section: ItemSectionType
    numerator_item_id: int
    numerator_value_mode: Literal["tree", "self", "self_and_tree"] = "tree"
    denominator_section: ItemSectionType
    denominator_item_id: int
    denominator_value_mode: Literal["tree", "self", "self_and_tree"] = "tree"
    format: IndicatorFormatType = "ratio"
    annualize: bool = False
    sort_order: int = 0
    enabled: bool = True


class BusinessCostIncomeRatioIndicatorUpdateRequest(BaseModel):
    product_code: str | None = None
    name: str
    parent_id: int | None = None
    display_group: bool = False
    topic_metric_node_code: str | None = None
    numerator_section: ItemSectionType
    numerator_item_id: int
    numerator_value_mode: Literal["tree", "self", "self_and_tree"] = "tree"
    denominator_section: ItemSectionType
    denominator_item_id: int
    denominator_value_mode: Literal["tree", "self", "self_and_tree"] = "tree"
    format: IndicatorFormatType = "ratio"
    annualize: bool = False
    sort_order: int = 0
    enabled: bool = True


def build_business_cost_income_ratio_router(
    *,
    write_operation_log: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/business-cost-income-ratio/meta", response_model=BusinessCostIncomeRatioMetaResponse)
    async def get_business_cost_income_ratio_meta(
        entity_name: str | None = Query(None),
        report_month: str | None = Query(None),
        product_code: str | None = Query(None),
    ):
        return await load_business_cost_income_meta_options(
            entity_name=entity_name,
            report_month=report_month,
            product_code=product_code,
        )

    @router.get(
        "/api/business-cost-income-ratio/report",
        response_model=BusinessCostIncomeRatioReportResponse,
    )
    async def get_business_cost_income_ratio_report(
        entity_name: str = Query(...),
        report_month: str = Query(..., description="YYYY-MM"),
        group_name: str | None = Query(None),
        product_code: str | None = Query(None),
        amount_unit: str = Query("yuan"),
    ):
        try:
            return await build_business_cost_income_ratio_report(
                entity_name=entity_name,
                report_month=report_month,
                group_name=group_name,
                product_code=product_code,
                amount_unit=amount_unit,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.get("/api/business-cost-income-ratio/template")
    async def download_business_cost_income_ratio_template(
        product_codes: list[str] = Query(default_factory=list),
        product_code: str | None = Query(None),
        year: int = Query(settings.budget_year),
        months: str | None = Query(None),
    ):
        codes = [*product_codes]
        if product_code:
            codes.insert(0, product_code)
        try:
            month_values = parse_months(months)
            wb = build_bcir_actual_import_template_workbook(
                year=year,
                product_codes=codes,
                months=month_values,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        filename = f"business_cost_income_import_template_{year}.xlsx"
        return workbook_streaming_response(
            wb,
            filename=filename,
            fallback_filename="bcir_import_template.xlsx",
        )

    def _flatten_import_preview_items(result: Any) -> tuple[list[dict[str, Any]], int, int]:
        items: list[dict[str, Any]] = []
        skipped = 0
        errors = 0
        for row in result.rows:
            if row.note:
                errors += 1
                items.append(
                    {
                        "row_number": row.excel_row,
                        "sheet_name": row.sheet_name,
                        "field": row.field,
                        "field_label": FIELD_LABELS.get(row.field, row.field),
                        "entity_name": row.entity_name,
                        "group_name": row.group_name,
                        "product_code": row.product_code,
                        "section": row.section,
                        "item_id": row.item_id,
                        "item_name": row.item_name,
                        "month": None,
                        "value_text": "",
                        "action": "error",
                        "message": row.note,
                    }
                )
                continue
            for cell in row.months:
                if cell.status == "empty":
                    skipped += 1
                    continue
                if cell.status == "error":
                    errors += 1
                    action = "error"
                    message = cell.reason
                else:
                    action = "ready"
                    message = "可写入"
                items.append(
                    {
                        "row_number": row.excel_row,
                        "sheet_name": row.sheet_name,
                        "field": row.field,
                        "field_label": FIELD_LABELS.get(row.field, row.field),
                        "entity_name": row.entity_name,
                        "group_name": row.group_name,
                        "product_code": row.product_code,
                        "section": row.section,
                        "item_id": row.item_id,
                        "item_name": row.item_name,
                        "month": cell.month,
                        "value_text": cell.value_text,
                        "action": action,
                        "message": message,
                    }
                )
        return items, skipped, errors

    @router.post(
        "/api/business-cost-income-ratio/import-preview",
        response_model=BusinessCostIncomeRatioActualImportPreviewResponse,
    )
    async def preview_business_cost_income_ratio_import(
        file: UploadFile = File(...),
        year: int = Query(settings.budget_year),
        months: str | None = Query(None),
    ):
        try:
            content = await file.read()
            result = run_bcir_actual_excel_import(
                content,
                year=year,
                months=parse_months(months),
                apply=False,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        items, skipped, errors = _flatten_import_preview_items(result)
        ready_count = sum(1 for item in items if item["action"] == "ready")
        return {
            "file_name": file.filename or "",
            "year": year,
            "preview_count": len(items),
            "insertable_cells": ready_count,
            "updatable_cells": 0,
            "skipped_cells": skipped,
            "error_cells": errors,
            "items": items,
        }

    @router.post(
        "/api/business-cost-income-ratio/import-apply",
        response_model=BusinessCostIncomeRatioActualImportApplyResponse,
    )
    async def apply_business_cost_income_ratio_import(
        file: UploadFile = File(...),
        year: int = Query(settings.budget_year),
        months: str | None = Query(None),
    ):
        try:
            content = await file.read()
            result = run_bcir_actual_excel_import(
                content,
                year=year,
                months=parse_months(months),
                apply=True,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        _items, skipped, errors = _flatten_import_preview_items(result)
        await write_operation_log(
            action_type="IMPORT",
            action_desc=f"业务支出成本收入比批量导入 {file.filename or ''}",
            target_table="business_cost_income_value",
            affected_rows=result.saved_cells,
            after_data={
                "file_name": file.filename,
                "year": year,
                "saved_cells": result.saved_cells,
                "skipped_cells": skipped,
                "error_cells": errors,
            },
        )
        return {
            "file_name": file.filename or "",
            "year": year,
            "saved_cells": result.saved_cells,
            "skipped_cells": skipped,
            "error_cells": errors,
        }

    @router.post(
        "/api/business-cost-income-ratio/input/cell",
        response_model=BusinessCostIncomeRatioCellUpsertResponse,
    )
    async def upsert_business_cost_income_ratio_cell(body: BusinessCostIncomeRatioCellUpsertRequest):
        try:
            result = await upsert_business_cost_income_value(
                year_month=body.year_month,
                entity_name=body.entity_name,
                group_name=body.group_name,
                product_code=body.product_code,
                amount_unit=body.amount_unit,
                item_section=body.item_section,
                item_id=body.item_id,
                field=body.field,
                value=body.value,
            )
        except (LookupError, ValueError) as e:
            raise _command_http_error(e) from e
        await write_operation_log(
            action_type="UPSERT",
            action_desc=(
                f"业务支出成本收入比分析录入 {body.year_month} {body.entity_name} "
                f"{body.group_name or '-'} {body.product_code or '-'} "
                f"{body.item_section}:{body.item_id} {body.field}"
            ),
            target_table="business_cost_income_value",
            affected_rows=1,
            after_data=result["after_data"],
        )
        return {"updated": True}

    @router.get(
        "/api/business-cost-income-ratio/admin/items",
        response_model=list[BusinessCostIncomeRatioItemDto],
    )
    async def list_business_cost_income_ratio_items(product_code: str | None = Query(None)):
        return await list_business_cost_income_item_configs(settings.budget_year, product_code=product_code)

    @router.post(
        "/api/business-cost-income-ratio/admin/items",
        response_model=BusinessCostIncomeRatioItemDto,
    )
    async def create_business_cost_income_ratio_item(body: BusinessCostIncomeRatioItemCreateRequest):
        year = settings.budget_year
        try:
            result = await create_business_cost_income_item(
                year=year,
                product_code=body.product_code,
                section=body.section,
                name=body.name,
                parent_id=body.parent_id,
                display_group=body.display_group,
                data_acct_code=body.data_acct_code,
                org_product_ref=body.org_product_ref,
                org_product_entity_code=body.org_product_entity_code,
                org_product_table_name=body.org_product_table_name,
                org_product_metric_code=body.org_product_metric_code,
                org_product_metric_name=body.org_product_metric_name,
                manual_entry_mode=body.manual_entry_mode,
                value_mode=body.value_mode,
                enabled=body.enabled,
            )
        except (LookupError, ValueError) as e:
            raise _command_http_error(e) from e
        await write_operation_log(
            action_type="INSERT",
            action_desc=f"新增业务支出成本收入比细项 {body.section}:{body.name}",
            target_table="business_cost_income_item",
            affected_rows=1,
            after_data=result["after_data"],
        )
        return result["item"]

    @router.put(
        "/api/business-cost-income-ratio/admin/items/{item_id}",
        response_model=BusinessCostIncomeRatioItemDto,
    )
    async def update_business_cost_income_ratio_item(item_id: int, body: BusinessCostIncomeRatioItemUpdateRequest):
        year = settings.budget_year
        try:
            result = await update_business_cost_income_item(
                year=year,
                item_id=item_id,
                product_code=body.product_code,
                name=body.name,
                parent_id=body.parent_id,
                display_group=body.display_group,
                data_acct_code=body.data_acct_code,
                org_product_ref=body.org_product_ref,
                org_product_entity_code=body.org_product_entity_code,
                org_product_table_name=body.org_product_table_name,
                org_product_metric_code=body.org_product_metric_code,
                org_product_metric_name=body.org_product_metric_name,
                manual_entry_mode=body.manual_entry_mode,
                value_mode=body.value_mode,
                sort_order=body.sort_order,
                enabled=body.enabled,
            )
        except (LookupError, ValueError) as e:
            raise _command_http_error(e) from e
        await write_operation_log(
            action_type="UPDATE",
            action_desc=f"更新业务支出成本收入比细项 {item_id}",
            target_table="business_cost_income_item",
            affected_rows=1,
            before_data=result["before_data"],
            after_data=result["after_data"],
        )
        return result["item"]

    @router.delete("/api/business-cost-income-ratio/admin/items/{item_id}")
    async def delete_business_cost_income_ratio_item(item_id: int):
        year = settings.budget_year
        try:
            result = await delete_business_cost_income_item(year=year, item_id=item_id)
        except (LookupError, ValueError) as e:
            raise _command_http_error(e) from e
        await write_operation_log(
            action_type="DELETE",
            action_desc=f"删除业务支出成本收入比细项 {item_id}",
            target_table="business_cost_income_item",
            affected_rows=1,
            before_data=result["before_data"],
        )
        return {"deleted": True}

    @router.put("/api/business-cost-income-ratio/admin/items-reorder")
    async def reorder_business_cost_income_ratio_items(body: dict[str, Any]):
        item_ids = body.get("item_ids", [])
        year = settings.budget_year
        try:
            result = await reorder_business_cost_income_items(year=year, item_ids=item_ids)
        except (LookupError, ValueError) as e:
            raise _command_http_error(e) from e
        await write_operation_log(
            action_type="UPDATE",
            action_desc="批量更新业务支出成本收入比细项排序",
            target_table="business_cost_income_item",
            affected_rows=result["count"],
            after_data=result["after_data"],
        )
        return {"reordered": True, "count": result["count"]}

    @router.put("/api/business-cost-income-ratio/admin/indicators-reorder")
    async def reorder_business_cost_income_ratio_indicators(body: dict[str, Any]):
        indicator_ids = body.get("indicator_ids", [])
        year = settings.budget_year
        try:
            result = await reorder_business_cost_income_indicators(year=year, indicator_ids=indicator_ids)
        except (LookupError, ValueError) as e:
            raise _command_http_error(e) from e
        await write_operation_log(
            action_type="UPDATE",
            action_desc="批量更新业务支出成本收入比评估指标排序",
            target_table="business_cost_income_indicator",
            affected_rows=result["count"],
            after_data=result["after_data"],
        )
        return {"reordered": True, "count": result["count"]}

    @router.get(
        "/api/business-cost-income-ratio/admin/indicators",
        response_model=list[BusinessCostIncomeRatioIndicatorDto],
    )
    async def list_business_cost_income_ratio_indicators(product_code: str | None = Query(None)):
        return await list_business_cost_income_indicator_configs(
            settings.budget_year,
            product_code=product_code,
        )

    @router.post(
        "/api/business-cost-income-ratio/admin/indicators",
        response_model=BusinessCostIncomeRatioIndicatorDto,
    )
    async def create_business_cost_income_ratio_indicator(body: BusinessCostIncomeRatioIndicatorCreateRequest):
        year = settings.budget_year
        try:
            result = await create_business_cost_income_indicator(
                year=year,
                product_code=body.product_code,
                name=body.name,
                parent_id=body.parent_id,
                display_group=body.display_group,
                topic_metric_node_code=body.topic_metric_node_code,
                numerator_section=body.numerator_section,
                numerator_item_id=body.numerator_item_id,
                numerator_value_mode=body.numerator_value_mode,
                denominator_section=body.denominator_section,
                denominator_item_id=body.denominator_item_id,
                denominator_value_mode=body.denominator_value_mode,
                format=body.format,
                annualize=body.annualize,
                sort_order=body.sort_order,
                enabled=body.enabled,
            )
        except (LookupError, ValueError) as e:
            raise _command_http_error(e) from e
        await write_operation_log(
            action_type="INSERT",
            action_desc=f"新增业务支出成本收入比指标 {body.name}",
            target_table="business_cost_income_indicator",
            affected_rows=1,
            after_data=result["after_data"],
        )
        return result["indicator"]

    @router.put(
        "/api/business-cost-income-ratio/admin/indicators/{indicator_id}",
        response_model=BusinessCostIncomeRatioIndicatorDto,
    )
    async def update_business_cost_income_ratio_indicator(
        indicator_id: int, body: BusinessCostIncomeRatioIndicatorUpdateRequest
    ):
        year = settings.budget_year
        try:
            result = await update_business_cost_income_indicator(
                year=year,
                indicator_id=indicator_id,
                product_code=body.product_code,
                name=body.name,
                parent_id=body.parent_id,
                display_group=body.display_group,
                topic_metric_node_code=body.topic_metric_node_code,
                numerator_section=body.numerator_section,
                numerator_item_id=body.numerator_item_id,
                numerator_value_mode=body.numerator_value_mode,
                denominator_section=body.denominator_section,
                denominator_item_id=body.denominator_item_id,
                denominator_value_mode=body.denominator_value_mode,
                format=body.format,
                annualize=body.annualize,
                sort_order=body.sort_order,
                enabled=body.enabled,
            )
        except (LookupError, ValueError) as e:
            raise _command_http_error(e) from e
        await write_operation_log(
            action_type="UPDATE",
            action_desc=f"更新业务支出成本收入比指标 {indicator_id}",
            target_table="business_cost_income_indicator",
            affected_rows=1,
            before_data=result["before_data"],
            after_data=result["after_data"],
        )
        return result["indicator"]

    @router.delete("/api/business-cost-income-ratio/admin/indicators/{indicator_id}")
    async def delete_business_cost_income_ratio_indicator(indicator_id: int):
        year = settings.budget_year
        try:
            result = await delete_business_cost_income_indicator(year=year, indicator_id=indicator_id)
        except (LookupError, ValueError) as e:
            raise _command_http_error(e) from e
        await write_operation_log(
            action_type="DELETE",
            action_desc=f"删除业务支出成本收入比指标 {indicator_id}",
            target_table="business_cost_income_indicator",
            affected_rows=1,
            before_data=result["before_data"],
        )
        return {"deleted": True}

    return router
