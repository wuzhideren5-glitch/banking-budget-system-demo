from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiosqlite
from fastapi import APIRouter, HTTPException, Query

from app.db_paths import common_db_path
from app.formula_refs import extract_formula_codes
from app.schemas import (
    BudgetInputBatchUpsert,
    BudgetInputCellUpsert,
    BudgetInputLoadResponse,
    BudgetInputPeriod,
    BudgetInputRow,
    BudgetInputWriteResult,
)


def build_budget_input_runtime_router(
    *,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
    get_version_current_month: Callable[[int, Path | None], Awaitable[int]],
    get_year_period_months: Callable[[int], Awaitable[dict[int, int]]],
    purge_disallowed_budget_data_for_version: Callable[[aiosqlite.Connection, int, int, dict[int, int]], Awaitable[None]],
    normalize_formula: Callable[[str | None], str],
    month_index: Callable[[str], int],
    is_month_editable: Callable[[int, int, int], bool],
    budget_actual_allowed_for_month: Callable[[int, int, int], bool],
    normalize_formula_ref_value: Callable[[float, str | None], float],
    try_calculate_formula_value: Callable[[str | None, dict[str, float]], tuple[float, str | None]],
    build_report_path: Callable[[str, dict[str, str], dict[str, str | None]], list[str]],
    is_formula_locked_data_account: Callable[[str, int], Awaitable[bool]],
    ensure_budget_input_period_editable: Callable[..., Awaitable[None]],
    set_budget_data_need_calc_for_cells: Callable[[list[tuple[str, str, int, int, int]], int, Path | None], Awaitable[int]],
    recalculate_product_formula_rows: Callable[..., Awaitable[int]],
    sync_compare_budget_summary: Callable[..., Awaitable[Any]] | None = None,
    write_operation_log: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter()
    _sync_state: dict[str, Any] = {"running": False, "last_started_at": 0.0}
    _sync_min_interval_sec = 45.0

    def schedule_compare_sync(trigger_source: str = "auto_after_budget_input_save") -> None:
        """后台异步同步 compare，节流避免每次单元格编辑都触发全量重建。"""
        if sync_compare_budget_summary is None:
            return
        now = time.monotonic()
        if bool(_sync_state["running"]):
            return
        if now - float(_sync_state["last_started_at"]) < _sync_min_interval_sec:
            return
        _sync_state["running"] = True
        _sync_state["last_started_at"] = now

        async def _runner() -> None:
            try:
                await sync_compare_budget_summary(trigger_source=trigger_source)
            except Exception:
                # 同步失败不影响用户保存链路；可通过 compare_sync_job_log 观察状态。
                pass
            finally:
                _sync_state["running"] = False

        asyncio.create_task(_runner())

    @router.get("/api/budget-input", response_model=BudgetInputLoadResponse)
    async def load_budget_input(
        product_code: str = Query(..., min_length=1),
        budget_actual: int = Query(0),
        version_id: int | None = Query(None),
    ):
        if budget_actual not in (0, 1):
            raise HTTPException(status_code=400, detail="budget_actual 必须为 0（预算）或 1（实际）")

        editable_budget_path, editable_year, editable_vid = await editable_context_provider()
        vid = int(version_id if version_id is not None else editable_vid)
        if vid != editable_vid:
            raise HTTPException(status_code=409, detail="当前可编辑版本已变更，请刷新页面后重试")
        normalized_product_code = product_code.strip().upper()
        current_month = await get_version_current_month(vid, editable_budget_path)
        common_path = common_db_path()
        budget_path = editable_budget_path
        year_label = f"Y{editable_year}"
        period_month_map_year = await get_year_period_months(editable_year)

        async with aiosqlite.connect(common_path) as cdb, aiosqlite.connect(budget_path) as bdb:
            await cdb.execute("PRAGMA foreign_keys = ON")
            await bdb.execute("PRAGMA foreign_keys = ON")
            await purge_disallowed_budget_data_for_version(bdb, vid, current_month, period_month_map_year)

            cur_accounts = await cdb.execute(
                """
                SELECT data_acct_code, data_acct_name, value_type, budget_formula, actual_formula
                FROM data_account
                WHERE product_code = ? OR applies_to_all_products = 1
                ORDER BY data_acct_code
                """,
                (normalized_product_code,),
            )
            account_rows = await cur_accounts.fetchall()
            data_codes = [str(r[0]) for r in account_rows]
            data_name_map = {str(r[0]): str(r[1]) for r in account_rows}
            data_value_type_map = {str(r[0]): str(r[2]) for r in account_rows}
            data_formula_map = {
                str(r[0]): (
                    normalize_formula(r[3]) if budget_actual == 0 else normalize_formula(r[4])
                )
                for r in account_rows
            }

            cur_periods = await cdb.execute(
                """
                SELECT period_id, month
                FROM period
                WHERE year = ?
                ORDER BY period_id
                """,
                (year_label,),
            )
            period_rows = await cur_periods.fetchall()
            periods = [
                BudgetInputPeriod(
                    period_id=int(r[0]),
                    month_label=str(r[1]),
                    month_index=month_index(str(r[1])),
                    editable=is_month_editable(current_month, budget_actual, month_index(str(r[1]))),
                )
                for r in period_rows
            ]
            period_ids = [p.period_id for p in periods]
            month_by_period_id = {int(r[0]): month_index(str(r[1])) for r in period_rows}
            allowed_period_ids = [
                pid
                for pid in period_ids
                if budget_actual_allowed_for_month(budget_actual, month_by_period_id.get(pid, 0), current_month)
            ]

            if data_codes and allowed_period_ids:
                inserts = [
                    (code, normalized_product_code, pid, budget_actual, vid, 0.0, 0)
                    for code in data_codes
                    for pid in allowed_period_ids
                ]
                await bdb.executemany(
                    """
                    INSERT OR IGNORE INTO budget_data
                    (data_acct_code, product_code, period_id, budget_actual, version_id, value, need_calc)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    inserts,
                )
                await bdb.commit()

            value_map: dict[tuple[str, int], float] = {}
            if data_codes and period_ids:
                data_placeholders = ",".join(["?"] * len(data_codes))
                period_placeholders = ",".join(["?"] * len(period_ids))
                cur_values = await bdb.execute(
                    f"""
                    SELECT data_acct_code, period_id, value
                    FROM budget_data
                    WHERE version_id = ?
                      AND budget_actual = ?
                      AND product_code = ?
                      AND data_acct_code IN ({data_placeholders})
                      AND period_id IN ({period_placeholders})
                    """,
                    (vid, budget_actual, normalized_product_code, *data_codes, *period_ids),
                )
                for r in await cur_values.fetchall():
                    value_map[(str(r[0]), int(r[1]))] = float(r[2] or 0.0)

            report_codes_by_data: dict[str, list[str]] = {c: [] for c in data_codes}
            report_name_map: dict[str, str] = {}
            report_parent_map: dict[str, str | None] = {}
            if data_codes:
                data_placeholders = ",".join(["?"] * len(data_codes))
                cur_mappings = await cdb.execute(
                    f"""
                    SELECT report_acct_code, data_acct_code
                    FROM report_data_mapping
                    WHERE data_acct_code IN ({data_placeholders})
                    ORDER BY report_acct_code, data_acct_code
                    """,
                    data_codes,
                )
                mapping_rows = await cur_mappings.fetchall()
                report_codes = sorted({str(r[0]) for r in mapping_rows})
                for report_code, data_code in mapping_rows:
                    report_codes_by_data.setdefault(str(data_code), []).append(str(report_code))

                if report_codes:
                    report_placeholders = ",".join(["?"] * len(report_codes))
                    cur_reports = await cdb.execute(
                        f"""
                        SELECT report_acct_code, report_acct_name, parent_code
                        FROM report_account
                        WHERE report_acct_code IN ({report_placeholders})
                        """,
                        report_codes,
                    )
                    for rr in await cur_reports.fetchall():
                        report_name_map[str(rr[0])] = str(rr[1])
                        report_parent_map[str(rr[0])] = str(rr[2]) if rr[2] is not None else None

                    # pull ancestor chain names for complete path display
                    unresolved = {
                        parent
                        for parent in report_parent_map.values()
                        if parent and parent not in report_name_map
                    }
                    while unresolved:
                        parent_placeholders = ",".join(["?"] * len(unresolved))
                        cur_ancestors = await cdb.execute(
                            f"""
                            SELECT report_acct_code, report_acct_name, parent_code
                            FROM report_account
                            WHERE report_acct_code IN ({parent_placeholders})
                            """,
                            tuple(unresolved),
                        )
                        fetched = await cur_ancestors.fetchall()
                        if not fetched:
                            break
                        unresolved = set()
                        for rr in fetched:
                            code = str(rr[0])
                            report_name_map[code] = str(rr[1])
                            report_parent_map[code] = str(rr[2]) if rr[2] is not None else None
                            parent = report_parent_map[code]
                            if parent and parent not in report_name_map:
                                unresolved.add(parent)

            rows: list[BudgetInputRow] = []
            formula_error_map: dict[str, list[str | None]] = {}
            for data_code in data_codes:
                formula = data_formula_map.get(data_code, "")
                if not formula:
                    continue
                ref_codes = sorted(extract_formula_codes(formula))
                errs: list[str | None] = []
                for pid in period_ids:
                    refs_for_period = {
                        code: normalize_formula_ref_value(
                            value_map.get((code, pid), 0.0),
                            data_value_type_map.get(code, ""),
                        )
                        for code in ref_codes
                    }
                    _, err = try_calculate_formula_value(formula, refs_for_period)
                    errs.append(err)
                formula_error_map[data_code] = errs

            for data_code in data_codes:
                values = [value_map.get((data_code, pid), 0.0) for pid in period_ids]
                total = float(sum(values))
                report_codes = sorted(set(report_codes_by_data.get(data_code, [])))
                if not report_codes:
                    rows.append(
                        BudgetInputRow(
                            report_path=["未映射数据科目"],
                            report_code=None,
                            data_acct_code=data_code,
                            data_acct_name=data_name_map.get(data_code, ""),
                            value_type=data_value_type_map.get(data_code, "金额"),
                            calc_formula=data_formula_map.get(data_code) or None,
                            formula_locked=bool(data_formula_map.get(data_code)),
                            formula_errors=formula_error_map.get(data_code, [None] * len(period_ids)),
                            values=values,
                            total=total,
                        )
                    )
                    continue
                for report_code in report_codes:
                    rows.append(
                        BudgetInputRow(
                            report_path=build_report_path(report_code, report_name_map, report_parent_map),
                            report_code=report_code,
                            data_acct_code=data_code,
                            data_acct_name=data_name_map.get(data_code, ""),
                            value_type=data_value_type_map.get(data_code, "金额"),
                            calc_formula=data_formula_map.get(data_code) or None,
                            formula_locked=bool(data_formula_map.get(data_code)),
                            formula_errors=formula_error_map.get(data_code, [None] * len(period_ids)),
                            values=values,
                            total=total,
                        )
                    )

            rows.sort(
                key=lambda r: (
                    r.report_code is None,
                    r.report_code or "ZZZ",
                    r.data_acct_code,
                )
            )
            return BudgetInputLoadResponse(
                budget_year=editable_year,
                version_id=vid,
                current_month=current_month,
                budget_actual=budget_actual,
                product_code=normalized_product_code,
                periods=periods,
                rows=rows,
            )

    @router.post("/api/budget-input/recalculate", response_model=BudgetInputWriteResult)
    async def recalculate_budget_input(
        product_code: str = Query(..., min_length=1),
        budget_actual: int = Query(0),
        version_id: int | None = Query(None),
    ):
        if budget_actual not in (0, 1):
            raise HTTPException(status_code=400, detail="budget_actual 必须为 0（预算）或 1（实际）")
        editable_budget_path, editable_year, editable_vid = await editable_context_provider()
        vid = int(version_id if version_id is not None else editable_vid)
        if vid != editable_vid:
            raise HTTPException(status_code=409, detail="当前可编辑版本已变更，请刷新页面后重试")
        recalculated = await recalculate_product_formula_rows(
            product_code=product_code,
            version_id=vid,
            budget_actual=budget_actual,
            budget_path=editable_budget_path,
            budget_year=editable_year,
        )
        schedule_compare_sync("auto_after_budget_input_recalculate")
        return BudgetInputWriteResult(saved=recalculated)

    @router.post("/api/budget-input/cell", response_model=BudgetInputWriteResult)
    async def save_budget_input_cell(body: BudgetInputCellUpsert):
        if await is_formula_locked_data_account(body.data_acct_code, body.budget_actual):
            raise HTTPException(status_code=409, detail="该数据科目由公式计算，不允许手工录入")
        editable_budget_path, _editable_year, editable_vid = await editable_context_provider()
        if int(body.version_id) != int(editable_vid):
            raise HTTPException(status_code=409, detail="当前可编辑版本已变更，请刷新页面后重试")
        await ensure_budget_input_period_editable(
            version_id=body.version_id,
            budget_actual=body.budget_actual,
            period_id=body.period_id,
            budget_path=editable_budget_path,
        )
        pc = body.product_code.strip().upper()
        path = editable_budget_path
        async with aiosqlite.connect(path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                """
                INSERT INTO budget_data (data_acct_code, product_code, period_id, budget_actual, version_id, value, need_calc)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(data_acct_code, product_code, period_id, version_id, budget_actual)
                DO UPDATE SET value = excluded.value, need_calc = 1, update_time = CURRENT_TIMESTAMP
                """,
                (
                    body.data_acct_code.strip().upper(),
                    pc,
                    body.period_id,
                    body.budget_actual,
                    body.version_id,
                    body.value,
                ),
            )
            await db.commit()
        edited_cell = [(
            body.data_acct_code.strip().upper(),
            pc,
            body.period_id,
            body.version_id,
            body.budget_actual,
        )]
        await set_budget_data_need_calc_for_cells(edited_cell, 0, editable_budget_path)
        await write_operation_log(
            action_type="UPDATE",
            action_desc=f"更新预算基础数据单元格 {body.data_acct_code}/period={body.period_id}",
            target_table="budget_data",
            affected_rows=1,
            after_data={
                "data_acct_code": body.data_acct_code,
                "period_id": body.period_id,
                "version_id": body.version_id,
                "budget_actual": body.budget_actual,
                "value": body.value,
            },
        )
        schedule_compare_sync("auto_after_budget_input_save")
        return BudgetInputWriteResult(saved=1)

    @router.post("/api/budget-input/batch", response_model=BudgetInputWriteResult)
    async def save_budget_input_batch(body: BudgetInputBatchUpsert):
        if not body.items:
            return BudgetInputWriteResult(saved=0)
        editable_budget_path, _editable_year, editable_vid = await editable_context_provider()
        checked_period_keys: set[tuple[int, int, int]] = set()
        for item in body.items:
            if int(item.version_id) != int(editable_vid):
                raise HTTPException(status_code=409, detail="当前可编辑版本已变更，请刷新页面后重试")
            if await is_formula_locked_data_account(item.data_acct_code, item.budget_actual):
                raise HTTPException(
                    status_code=409,
                    detail=f"数据科目 {item.data_acct_code} 由公式计算，不允许手工录入",
                )
            month_check_key = (item.version_id, item.budget_actual, item.period_id)
            if month_check_key not in checked_period_keys:
                checked_period_keys.add(month_check_key)
                await ensure_budget_input_period_editable(
                    version_id=item.version_id,
                    budget_actual=item.budget_actual,
                    period_id=item.period_id,
                    budget_path=editable_budget_path,
                )
        path = editable_budget_path
        params = [
            (
                item.data_acct_code.strip().upper(),
                item.product_code.strip().upper(),
                item.period_id,
                item.budget_actual,
                item.version_id,
                item.value,
            )
            for item in body.items
        ]
        async with aiosqlite.connect(path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.executemany(
                """
                INSERT INTO budget_data (data_acct_code, product_code, period_id, budget_actual, version_id, value, need_calc)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(data_acct_code, product_code, period_id, version_id, budget_actual)
                DO UPDATE SET value = excluded.value, need_calc = 1, update_time = CURRENT_TIMESTAMP
                """,
                params,
            )
            await db.commit()
        seen_keys: set[tuple[str, str, int, int, int]] = set()
        for item in body.items:
            key = (
                item.data_acct_code.strip().upper(),
                item.product_code.strip().upper(),
                item.period_id,
                item.version_id,
                item.budget_actual,
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
        await set_budget_data_need_calc_for_cells(list(seen_keys), 0, editable_budget_path)
        await write_operation_log(
            action_type="BATCH_UPDATE",
            action_desc=f"批量更新预算基础数据 {len(body.items)} 条",
            target_table="budget_data",
            affected_rows=len(body.items),
            after_data={"saved": len(body.items)},
        )
        schedule_compare_sync("auto_after_budget_input_save")
        return BudgetInputWriteResult(saved=len(body.items))

    return router
