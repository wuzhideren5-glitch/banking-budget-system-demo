from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.database import get_pool
from app.core.db_paths import common_db_path
from app.schemas import BudgetSummaryAggregateRequest, BudgetSummaryExportPivotRequest
from app.services.runtime_metric_refs import load_org_product_metric_refs_by_runtime_ref_code_sync
from app.services.pivot_aggregate import list_compare_pivot_aggregate_rows
from app.services.pivot_aggregate_export import aggregate_workbook_response, build_pivot_aggregate_workbook


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _uses_mysql_path(path: Path | str) -> bool:
    try:
        candidate = Path(path).expanduser().resolve()
    except TypeError:
        return False
    temp_root = Path(tempfile.gettempdir()).expanduser().resolve()
    try:
        candidate.relative_to(temp_root)
        return False
    except ValueError:
        pass
    data_dir = Path(settings.data_dir).expanduser().resolve()
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    return candidate.name == "common.db" or candidate.name == "compare.db" or (
        candidate.name.startswith("budget_") and candidate.suffix == ".db"
    )


async def load_compare_export_org_product_refs(common_db: Path | str) -> dict[str, list[str]]:
    if _uses_mysql_path(common_db):
        return await _load_org_product_metric_refs_by_runtime_ref_code_mysql()
    return await asyncio.to_thread(_load_org_product_metric_refs_by_runtime_ref_code_sqlite, common_db)


async def _load_org_product_metric_refs_by_runtime_ref_code_mysql() -> dict[str, list[str]]:
    try:
        rows = await get_pool().fetch_all(
            """
            SELECT node_code, node_name, product_code, metric_table_name
            FROM data_account_metric_node
            WHERE is_active = 1
              AND runtime_account_enabled = 1
              AND COALESCE(product_code, '') <> ''
              AND COALESCE(metric_table_name, '') <> ''
            """
        )
    except Exception:
        return {}
    refs_by_code: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        data_acct_code = str(_row_value(row, "node_code", 0) or "").strip().upper()
        metric_name = str(_row_value(row, "node_name", 1) or "").strip()
        entity_code = str(_row_value(row, "product_code", 2) or "").strip().upper()
        table_name = str(_row_value(row, "metric_table_name", 3) or "").strip()
        if not data_acct_code or not entity_code or not table_name:
            continue
        source_ref = f"{entity_code}:{table_name}:{data_acct_code}"
        label = f"{source_ref} {metric_name}".strip()
        dedupe_key = (data_acct_code, source_ref)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        refs_by_code.setdefault(data_acct_code, []).append(label)
    return {code: sorted(refs) for code, refs in refs_by_code.items()}


def _load_org_product_metric_refs_by_runtime_ref_code_sqlite(common_db: Path | str) -> dict[str, list[str]]:
    with sqlite3.connect(common_db) as conn:
        return {
            code: list(refs)
            for code, refs in load_org_product_metric_refs_by_runtime_ref_code_sync(conn).items()
        }


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
        org_product_refs = await load_compare_export_org_product_refs(common_db_path())
        wb = build_pivot_aggregate_workbook(
            rows=rows,
            body=body,
            title="多年度对比透视聚合结果",
            source_label="对比聚合表 compare_pivot_aggregate",
            org_product_refs_by_runtime_ref_code=org_product_refs,
        )
        return aggregate_workbook_response(wb, "compare_pivot_aggregate_export.xlsx")
