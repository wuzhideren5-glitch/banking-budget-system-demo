from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import re

from app.budget_data_writer import (
    IMPORT_INPUT_POLICY,
    BudgetDataWriteItem,
    BudgetDataWritePolicy,
    BudgetDataWriteResult,
    write_budget_data_items,
)
from app.budget_window import budget_actual_allowed_for_month
from app.runtime_metric_identity import product_code_from_runtime_metric_ref
from app.services.budget_summary_rebuild import rebuild_budget_summary_for_version
from app.services.global_refresh_status import set_budget_refresh_time
from app.services.metric_tree_rollups import rebuild_metric_tree_rollups
from app.services.pivot_aggregate import rebuild_budget_pivot_aggregate_for_version
from app.services.runtime_metric_refs import derive_runtime_ref_from_org_product_metric_code


@dataclass
class OrgProductBudgetSyncPlan:
    write_items: list[BudgetDataWriteItem] = field(default_factory=list)
    candidate_rows: int = 0
    unbound_rows: int = 0
    non_confirmed_rows: int = 0
    empty_rows: int = 0
    skipped_cells: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_response(self) -> dict[str, Any]:
        return {
            "candidate_rows": self.candidate_rows,
            "writable_cells": len(self.write_items),
            "unbound_rows": self.unbound_rows,
            "non_confirmed_rows": self.non_confirmed_rows,
            "empty_rows": self.empty_rows,
            "skipped_cells": self.skipped_cells,
            "warnings": self.warnings[:80],
        }


@dataclass
class OrgProductBudgetSyncApplyResult:
    write_result: BudgetDataWriteResult
    metric_rollup_cells_written: int = 0
    summary_rows: int = 0
    budget_aggregate_rows: int = 0


async def _infer_budget_year(common_path: Path, period_ids: set[int]) -> int | None:
    if not period_ids or not common_path.exists():
        return None
    import app.core.aiosqlite_compat as aiosqlite

    placeholders = ",".join("?" for _ in period_ids)
    async with aiosqlite.connect(common_path) as db:
        cur = await db.execute(
            f"SELECT year FROM period WHERE period_id IN ({placeholders}) LIMIT 1",
            tuple(sorted(period_ids)),
        )
        row = await cur.fetchone()
    if not row:
        return None
    text = str(row[0] or "").strip().upper()
    if text.startswith("Y"):
        text = text[1:]
    try:
        return int(text)
    except ValueError:
        return None


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_code(value: Any) -> str:
    return _normalize_text(value).upper().replace(" ", "")


def _parse_numeric_cell(value: Any) -> tuple[bool, float | None, str]:
    text = _normalize_text(value)
    if not text:
        return False, None, ""
    normalized = text.replace(",", "").replace("，", "").replace(" ", "")
    normalized = normalized.replace("％", "%")
    is_percent = normalized.endswith("%")
    if is_percent:
        normalized = normalized[:-1]
    try:
        number = float(normalized)
    except ValueError:
        return True, None, f"无法解析数字：{text}"
    return True, number / 100.0 if is_percent else number, ""


def _iter_month_cells(values: dict[str, Any]) -> list[tuple[int, int, Any, str]]:
    months = values.get("months") if isinstance(values.get("months"), dict) else {}
    out: list[tuple[int, int, Any, str]] = []
    for key, raw_value in months.items():
        key_text = _normalize_text(key).lower()
        match = re.fullmatch(r"([af])(\d{1,2})", key_text)
        if not match:
            continue
        month = int(match.group(2))
        if not 1 <= month <= 12:
            continue
        budget_actual = 1 if match.group(1) == "a" else 0
        out.append((budget_actual, month, raw_value, key_text))
    return out


def plan_org_product_budget_sync(
    *,
    payload: dict[str, Any],
    entity_code: str,
    table_name: str,
    year: int,
    budget_version_id: int,
    current_month: int,
    period_month_map: dict[int, int],
    budget_actuals: list[int] | None = None,
) -> OrgProductBudgetSyncPlan:
    allowed_actuals = {int(item) for item in (budget_actuals or [1, 0]) if int(item) in (0, 1)}
    if not allowed_actuals:
        allowed_actuals = {1, 0}
    period_by_month = {int(month): int(period_id) for period_id, month in period_month_map.items()}
    plan = OrgProductBudgetSyncPlan()
    metrics = payload.get("metrics") if isinstance(payload, dict) else []
    if not isinstance(metrics, list):
        return plan

    entity = _normalize_code(entity_code)
    table = _normalize_text(table_name)
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        metric_code = _normalize_code(metric.get("metric_code") or metric.get("code"))
        metric_name = _normalize_text(metric.get("metric_name") or metric.get("name"))
        data_acct_code = derive_runtime_ref_from_org_product_metric_code(
            entity_code=entity,
            metric_code=metric_code,
        )
        row_ref = f"{entity}:{table}:{metric_code or metric_name or '-'}"

        if not data_acct_code:
            plan.unbound_rows += 1
            continue

        values = metric.get("values") if isinstance(metric.get("values"), dict) else {}
        month_cells = _iter_month_cells(values)
        if not month_cells:
            plan.empty_rows += 1
            continue

        plan.candidate_rows += 1
        product_code = product_code_from_runtime_metric_ref(data_acct_code) or entity
        wrote_for_row = False
        for budget_actual, month, raw_value, cell_key in month_cells:
            if budget_actual not in allowed_actuals:
                continue
            has_value, numeric_value, parse_error = _parse_numeric_cell(raw_value)
            if not has_value:
                continue
            source_ref = f"{row_ref}/{cell_key}"
            if parse_error or numeric_value is None:
                plan.skipped_cells += 1
                plan.warnings.append(f"{source_ref}: {parse_error or '无有效数值'}")
                continue
            period_id = period_by_month.get(month)
            if period_id is None:
                plan.skipped_cells += 1
                plan.warnings.append(f"{source_ref}: {year} 年 M{month:02d} 未找到期间")
                continue
            if not budget_actual_allowed_for_month(int(budget_actual), month, int(current_month)):
                kind = "实际值" if budget_actual == 1 else "预算值"
                plan.skipped_cells += 1
                plan.warnings.append(
                    f"{source_ref}: 当前版本月份窗口限制，{kind}不允许写入 {month} 月（current_month={int(current_month)}）"
                )
                continue
            plan.write_items.append(
                BudgetDataWriteItem(
                    data_acct_code=data_acct_code,
                    product_code=product_code,
                    period_id=int(period_id),
                    budget_actual=int(budget_actual),
                    version_id=int(budget_version_id),
                    value=float(numeric_value),
                    source_ref=source_ref,
                )
            )
            wrote_for_row = True
        if not wrote_for_row:
            plan.empty_rows += 1
    return plan


async def apply_org_product_budget_sync_plan(
    *,
    plan: OrgProductBudgetSyncPlan,
    common_path: Path,
    budget_path: Path,
    budget_version_id: int,
    timestamp: str,
    write_items: Callable[..., Awaitable[BudgetDataWriteResult]] = write_budget_data_items,
    write_policy: BudgetDataWritePolicy = IMPORT_INPUT_POLICY,
    rebuild_summary: Callable[[int, Path | None], Awaitable[int]] = rebuild_budget_summary_for_version,
    rebuild_aggregate: Callable[[int, Path], Awaitable[int]] = rebuild_budget_pivot_aggregate_for_version,
    set_refresh_time: Callable[[Path, str], Awaitable[None]] = set_budget_refresh_time,
    rebuild_configured_rollups: Callable[..., Awaitable[Any]] = rebuild_metric_tree_rollups,
) -> OrgProductBudgetSyncApplyResult:
    write_result = await write_items(
        budget_path=budget_path,
        common_path=common_path,
        items=plan.write_items,
        policy=write_policy,
    )
    if int(write_result.saved_cells or 0) <= 0:
        return OrgProductBudgetSyncApplyResult(write_result=write_result)

    metric_rollup_cells_written = 0
    period_ids = {int(item.period_id) for item in plan.write_items}
    budget_year = await _infer_budget_year(common_path, period_ids)
    if budget_year is not None and common_path.exists() and budget_path.exists():
        rollup_result = await rebuild_configured_rollups(
            common_path=common_path,
            budget_path=budget_path,
            budget_year=int(budget_year),
            version_id=int(budget_version_id),
            product_codes=sorted(write_result.affected_products),
            budget_actuals=sorted({int(item.budget_actual) for item in plan.write_items}),
        )
        metric_rollup_cells_written = int(getattr(rollup_result, "written_cells", 0) or 0)
        write_result.warnings.extend(
            str(item)
            for item in getattr(rollup_result, "warnings", []) or []
            if str(item).strip()
        )

        # 年度聚合刷新
        try:
            from app.services.annual_aggregation import refresh_annual_aggregates_for_products

            annual_result = await refresh_annual_aggregates_for_products(
                common_path=common_path,
                budget_path=budget_path,
                product_codes=sorted(write_result.affected_products),
                budget_actuals=sorted({int(item.budget_actual) for item in plan.write_items}),
                year=int(budget_year),
                version_id=int(budget_version_id),
            )
            annual_count = int(annual_result.get("refreshed", 0))
        except Exception:
            annual_count = 0

    summary_rows = await rebuild_summary(int(budget_version_id), budget_path)
    await set_refresh_time(budget_path, timestamp)
    budget_aggregate_rows = await rebuild_aggregate(int(budget_version_id), budget_path)
    return OrgProductBudgetSyncApplyResult(
        write_result=write_result,
        metric_rollup_cells_written=metric_rollup_cells_written,
        summary_rows=int(summary_rows),
        budget_aggregate_rows=int(budget_aggregate_rows),
    )
