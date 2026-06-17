from __future__ import annotations

import app.core.aiosqlite_compat as aiosqlite
from fastapi.responses import StreamingResponse

from app.core.db_paths import common_db_path
from app.schemas import BudgetSummaryAggregateRequest, BudgetSummaryExportPivotRequest
from app.services.runtime_metric_refs import load_org_product_metric_refs_by_runtime_ref_code
from app.services.pivot_aggregate import list_compare_pivot_aggregate_rows
from app.services.pivot_aggregate_export import aggregate_workbook_response, build_pivot_aggregate_workbook


class CompareExportService:
    async def export_compare_pivot_aggregate(self, body: BudgetSummaryExportPivotRequest) -> StreamingResponse:
        aggregate_body = BudgetSummaryAggregateRequest(
            row_field_ids=body.row_field_ids,
            column_field_ids=body.column_field_ids,
            page_field_ids=body.page_field_ids,
            page_selections=body.page_selections,
            pivot_search_text=body.pivot_search_text,
        )
        rows = await list_compare_pivot_aggregate_rows(aggregate_body)
        async with aiosqlite.connect(common_db_path()) as common_db:
            await common_db.execute("PRAGMA foreign_keys = ON")
            org_product_refs = await load_org_product_metric_refs_by_runtime_ref_code(common_db)
        wb = build_pivot_aggregate_workbook(
            rows=rows,
            body=body,
            title="多年度对比透视聚合结果",
            source_label="对比聚合表 compare_pivot_aggregate",
            org_product_refs_by_runtime_ref_code=org_product_refs,
        )
        return aggregate_workbook_response(wb, "compare_pivot_aggregate_export.xlsx")
