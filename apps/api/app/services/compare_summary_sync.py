"""Cross-year compare summary synchronization service."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import aiosqlite
from fastapi import HTTPException

from app.core.config import settings
from app.db_bootstrap.budget_version import ensure_budget_version_schema
from app.db_bootstrap.derived_read_models import (
    ensure_budget_summary_read_model_schema_async,
    ensure_compare_summary_read_model_schema_async,
)
from app.core.db_paths import common_db_path, compare_db_path
from app.schemas import CompareSummarySyncResult
from app.services.budget_summary_rebuild import rebuild_budget_summary_for_version


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CompareSummarySyncService:
    def __init__(self, set_compare_refresh_time: Callable[[str], Awaitable[None]]):
        self._set_compare_refresh_time = set_compare_refresh_time
        self._lock = asyncio.Lock()

    async def sync(
        self,
        trigger_source: str = "manual",
        operator_user_id: int | None = None,
    ) -> CompareSummarySyncResult:
        async with self._lock:
            start_time = _iso_now()
            compare_path = compare_db_path()
            common_path = common_db_path()
            selected_versions = 0
            inserted_rows = 0
            message = "ok"
            rule_message = ""
            level_rules: list[str] = []
            status = "success"
            try:
                async with aiosqlite.connect(common_path) as cdb:
                    await cdb.execute("PRAGMA foreign_keys = ON")
                    cur = await cdb.execute(
                        """
                        SELECT e.edit_show_sign, e.data_file_id, e.version_id, d.data_file_name, d.year
                        FROM edit_show_version e
                        JOIN databases d ON d.id = e.data_file_id
                        WHERE e.edit_show_sign BETWEEN 1 AND 5
                        ORDER BY e.edit_show_sign
                        """
                    )
                    selected = await cur.fetchall()

                selected_versions = len(selected)
                rows_to_insert: list[tuple[Any, ...]] = []
                for show_level, data_file_id, source_version_id, data_file_name, source_year in selected:
                    budget_path = settings.data_dir / str(data_file_name)
                    if not budget_path.exists():
                        continue
                    async with aiosqlite.connect(budget_path) as bdb:
                        await bdb.execute("PRAGMA foreign_keys = ON")
                        await ensure_budget_version_schema(bdb)
                        await ensure_budget_summary_read_model_schema_async(bdb)
                        cur_ver = await bdb.execute(
                            "SELECT version_name, current_month FROM version WHERE version_id = ?",
                            (int(source_version_id),),
                        )
                        ver_row = await cur_ver.fetchone()
                        if not ver_row:
                            raise HTTPException(status_code=400, detail=f"版本 {int(source_version_id)} 不存在")
                        ver_name = str(ver_row[0]) if ver_row[0] is not None else None
                        current_month = int(ver_row[1])
                        level_rules.append(
                            f"L{int(show_level)}: {data_file_name} / V{int(source_version_id)}"
                            f"{(' ' + ver_name) if ver_name else ''} / current_month={current_month}"
                            f" / month<{current_month}取实际, month>={current_month}取预算"
                        )
                        cur_summary_cnt = await bdb.execute(
                            "SELECT COUNT(*) FROM budget_summary WHERE version_id = ?",
                            (int(source_version_id),),
                        )
                        summary_cnt_row = await cur_summary_cnt.fetchone()
                        if int(summary_cnt_row[0] or 0) == 0:
                            await rebuild_budget_summary_for_version(
                                int(source_version_id),
                                budget_path,
                            )
                            cur_summary_cnt = await bdb.execute(
                                "SELECT COUNT(*) FROM budget_summary WHERE version_id = ?",
                                (int(source_version_id),),
                            )
                            summary_cnt_row = await cur_summary_cnt.fetchone()
                        if int(summary_cnt_row[0] or 0) == 0:
                            level_rules.append(
                                f"L{int(show_level)}: {data_file_name} / V{int(source_version_id)} 汇总明细为空（budget_data 无记录）"
                            )
                        cur = await bdb.execute(
                            """
                            SELECT metric_level1, metric_level2, metric_level3, metric_level4, metric_level5,
                                   dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
                                   year, month, quarter, budget_actual, version_name, value, value_type,
                                   value_source
                            FROM budget_summary
                            WHERE version_id = ?
                            ORDER BY metric_level1, metric_level2, metric_level3, data_code_name, month, budget_actual
                            """,
                            (int(source_version_id),),
                        )
                        for row in await cur.fetchall():
                            rows_to_insert.append(
                                (
                                    int(show_level),
                                    int(data_file_id),
                                    int(source_year),
                                    int(source_version_id),
                                    ver_name or row[14],
                                    row[0],
                                    row[1],
                                    row[2],
                                    row[3],
                                    row[4],
                                    row[5],
                                    row[6],
                                    row[7],
                                    row[8],
                                    row[9],
                                    row[10],
                                    row[11],
                                    row[12],
                                    int(row[13] or 0),
                                    float(row[15] or 0.0),
                                    row[16],
                                    row[17],
                                    start_time,
                                )
                            )

                async with aiosqlite.connect(compare_path) as cdb:
                    await cdb.execute("PRAGMA foreign_keys = ON")
                    await ensure_compare_summary_read_model_schema_async(cdb)
                    await cdb.execute("DELETE FROM compare_budget_summary")
                    if rows_to_insert:
                        await cdb.executemany(
                            """
                            INSERT INTO compare_budget_summary (
                              show_level, data_file_id, source_year, source_version_id, source_version_name,
                              metric_level1, metric_level2, metric_level3, metric_level4, metric_level5,
                              dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
                              year, month, quarter, budget_actual, value, value_type, value_source, sync_time
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            rows_to_insert,
                        )
                    inserted_rows = len(rows_to_insert)
                    if level_rules:
                        rule_message = "；".join(level_rules)
                    end_time = _iso_now()
                    await cdb.execute(
                        """
                        INSERT INTO compare_sync_job_log (
                          start_time, end_time, trigger_source, status, message, operator_user_id
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (start_time, end_time, trigger_source, status, message, operator_user_id),
                    )
                    await cdb.commit()
                await self._set_compare_refresh_time(end_time)
            except Exception as exc:
                status = "failed"
                message = str(exc)
                end_time = _iso_now()
                async with aiosqlite.connect(compare_path) as cdb:
                    await cdb.execute("PRAGMA foreign_keys = ON")
                    await cdb.execute(
                        """
                        INSERT INTO compare_sync_job_log (
                          start_time, end_time, trigger_source, status, message, operator_user_id
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (start_time, end_time, trigger_source, status, message, operator_user_id),
                    )
                    await cdb.commit()
                raise HTTPException(status_code=500, detail=f"同步 compare_summary 失败: {exc}")

            return CompareSummarySyncResult(
                inserted_rows=inserted_rows,
                selected_versions=selected_versions,
                trigger_source=trigger_source,
                message=message,
                rule_message=rule_message,
                level_rules=level_rules,
            )
