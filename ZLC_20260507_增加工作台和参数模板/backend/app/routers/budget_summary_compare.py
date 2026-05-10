from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

import aiosqlite
from fastapi import APIRouter, HTTPException, Query

from app.db_paths import compare_db_path
from app.schemas import (
    BudgetSummaryRebuildResult,
    BudgetSummaryRowDto,
    CompareSummaryRowDto,
    CompareSummarySyncResult,
    CompareSyncLatestStatus,
)


def build_budget_summary_compare_router(
    *,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
    get_version_current_month: Callable[[int, Path | None], Awaitable[int]],
    rebuild_budget_summary_for_version: Callable[[int, Path | None], Awaitable[int]],
    sync_compare_budget_summary: Callable[..., Awaitable[CompareSummarySyncResult]],
    write_operation_log: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/budget-summary/rebuild", response_model=BudgetSummaryRebuildResult)
    async def rebuild_budget_summary(version_id: int | None = Query(None)):
        editable_budget_path, _editable_year, editable_vid = await editable_context_provider()
        vid = int(version_id if version_id is not None else editable_vid)
        current_month = await get_version_current_month(vid, editable_budget_path)
        rebuilt = await rebuild_budget_summary_for_version(vid, editable_budget_path)
        await write_operation_log(
            action_type="REBUILD",
            action_desc=f"重建数据汇总版本 {vid}",
            target_table="budget_summary",
            affected_rows=rebuilt,
            after_data={"version_id": vid, "rebuilt_rows": rebuilt},
        )
        rule_message = (
            f"current_month={current_month}；透视口径按月切换：month<{current_month} 取实际值，"
            f"month>={current_month} 取预算值。"
        )
        return BudgetSummaryRebuildResult(
            version_id=vid,
            current_month=current_month,
            rebuilt_rows=rebuilt,
            rule_message=rule_message,
        )

    @router.get("/api/budget-summary", response_model=list[BudgetSummaryRowDto])
    async def list_budget_summary(version_id: int | None = Query(None)):
        editable_budget_path, _editable_year, editable_vid = await editable_context_provider()
        async with aiosqlite.connect(editable_budget_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur_ver = await db.execute("SELECT version_id, current_month FROM version")
            version_month_map = {int(r[0]): int(r[1] or 1) for r in await cur_ver.fetchall()}
            if version_id is not None:
                vid = int(version_id)
                sql = """
                SELECT report_level1, report_level2, report_level3, report_level4, report_level5,
                       dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
                       year, month, quarter, budget_actual, version_id, version_name,
                       value, value_type, update_time
                FROM budget_summary
                WHERE version_id = ?
                ORDER BY version_id, report_level1, report_level2, report_level3, data_code_name, month, budget_actual
                """
                args: tuple[Any, ...] = (vid,)
            else:
                sql = """
                SELECT report_level1, report_level2, report_level3, report_level4, report_level5,
                       dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
                       year, month, quarter, budget_actual, version_id, version_name,
                       value, value_type, update_time
                FROM budget_summary
                ORDER BY version_id, report_level1, report_level2, report_level3, data_code_name, month, budget_actual
                """
                args = ()
            cur = await db.execute(
                sql,
                args,
            )
            rows = await cur.fetchall()
        return [
            (
                lambda cm: BudgetSummaryRowDto(
                    report_level1=r[0],
                    report_level2=r[1],
                    report_level3=r[2],
                    report_level4=r[3],
                    report_level5=r[4],
                    dept_level1=r[5],
                    dept_level2=r[6],
                    dept_level3=r[7],
                    data_code_name=r[8],
                    product_code_name=r[9],
                    year=r[10],
                    month=r[11],
                    quarter=r[12],
                    budget_actual=int(r[13]),
                    version_id=int(r[14]),
                    version_name=r[15],
                    current_month=cm,
                    rule_message=f"current_month={cm}；month<{cm} 取实际值，month>={cm} 取预算值。",
                    value=float(r[16] or 0.0),
                    value_type=r[17],
                    update_time=r[18],
                )
            )(max(1, min(13, int(version_month_map.get(int(r[14]), 1) or 1))))
            for r in rows
        ]

    @router.get("/api/compare-summary", response_model=list[CompareSummaryRowDto])
    async def list_compare_summary(show_level: int | None = Query(None)):
        if show_level is not None and show_level not in (1, 2, 3, 4, 5):
            raise HTTPException(status_code=400, detail="show_level 必须在 1-5 范围内")
        path = compare_db_path()
        if not path.exists():
            return []
        async with aiosqlite.connect(path) as db:
            sql = """
                SELECT show_level, data_file_id, source_year, source_version_id, source_version_name,
                       report_level1, report_level2, report_level3, report_level4, report_level5,
                       dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
                       year, month, quarter, budget_actual, value, value_type, sync_time
                FROM compare_budget_summary
            """
            args: tuple[Any, ...] = ()
            if show_level is not None:
                sql += " WHERE show_level = ?"
                args = (show_level,)
            sql += """
                ORDER BY show_level, source_year, source_version_id,
                         report_level1, report_level2, report_level3, data_code_name, month, budget_actual
            """
            cur = await db.execute(sql, args)
            rows = await cur.fetchall()
        return [
            CompareSummaryRowDto(
                show_level=int(r[0]),
                data_file_id=int(r[1]),
                source_year=int(r[2]),
                source_version_id=int(r[3]),
                source_version_name=r[4],
                report_level1=r[5],
                report_level2=r[6],
                report_level3=r[7],
                report_level4=r[8],
                report_level5=r[9],
                dept_level1=r[10],
                dept_level2=r[11],
                dept_level3=r[12],
                data_code_name=r[13],
                product_code_name=r[14],
                year=r[15],
                month=r[16],
                quarter=r[17],
                budget_actual=int(r[18]),
                value=float(r[19] or 0.0),
                value_type=r[20],
                sync_time=r[21],
            )
            for r in rows
        ]

    @router.post("/api/compare-summary/sync", response_model=CompareSummarySyncResult)
    async def sync_compare_summary(trigger_source: str = Query("manual")):
        if trigger_source not in {"manual", "auto_after_setting_save", "auto_on_system_page_open"}:
            raise HTTPException(status_code=400, detail="trigger_source 非法")
        return await sync_compare_budget_summary(trigger_source=trigger_source)

    @router.get("/api/compare-summary/sync/latest", response_model=CompareSyncLatestStatus)
    async def get_compare_summary_sync_latest():
        path = compare_db_path()
        if not path.exists():
            return CompareSyncLatestStatus()
        async with aiosqlite.connect(path) as cdb:
            await cdb.execute("PRAGMA foreign_keys = ON")
            cur = await cdb.execute(
                """
                SELECT job_id, start_time, end_time, trigger_source, status, message
                FROM compare_sync_job_log
                ORDER BY job_id DESC
                LIMIT 1
                """
            )
            row = await cur.fetchone()
        if not row:
            return CompareSyncLatestStatus()
        return CompareSyncLatestStatus(
            job_id=int(row[0]),
            start_time=str(row[1]) if row[1] is not None else None,
            end_time=str(row[2]) if row[2] is not None else None,
            trigger_source=str(row[3]) if row[3] is not None else None,
            status=str(row[4]) if row[4] is not None else None,
            message=str(row[5]) if row[5] is not None else None,
        )

    return router
