"""Cross-year compare summary synchronization service."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.core.database import get_pool
from app.db_bootstrap.budget_version import ensure_budget_version_schema_sync
from app.db_bootstrap.derived_read_models import (
    ensure_budget_read_model_schema,
    ensure_compare_read_model_schema,
)
from app.core.db_paths import common_db_path, compare_db_path
from app.schemas import CompareSummarySyncResult
from app.services.budget_summary_rebuild import rebuild_budget_summary_for_version


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _uses_mysql_path(path: Path | str, *, names: set[str] | None = None, budget: bool = False) -> bool:
    try:
        candidate = Path(path).expanduser().resolve()
        data_dir = Path(settings.data_dir).expanduser().resolve()
        temp_root = Path(tempfile.gettempdir()).expanduser().resolve()
    except (TypeError, OSError):
        return False
    try:
        candidate.relative_to(temp_root)
        return False
    except ValueError:
        pass
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    if budget:
        return re.fullmatch(r"budget_\d{4}\.db", candidate.name) is not None
    return names is not None and candidate.name in names


def _uses_mysql_common_path(path: Path | str) -> bool:
    return _uses_mysql_path(path, names={"common.db"})


def _uses_mysql_compare_path(path: Path | str) -> bool:
    return _uses_mysql_path(path, names={"compare.db"})


def _uses_mysql_budget_path(path: Path | str) -> bool:
    return _uses_mysql_path(path, budget=True)


async def _load_selected_versions(common_path: Path) -> list[Any]:
    sql = """
        SELECT e.edit_show_sign, e.data_file_id, e.version_id, d.data_file_name, d.year
        FROM edit_show_version e
        JOIN `databases` d ON d.id = e.data_file_id
        WHERE e.edit_show_sign BETWEEN 1 AND 5
        ORDER BY e.edit_show_sign
        """
    if _uses_mysql_common_path(common_path):
        return await get_pool().fetch_all(sql)
    with sqlite3.connect(common_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        return conn.execute(sql).fetchall()


async def _fetch_budget_version_row(budget_path: Path, source_version_id: int, source_year: int) -> Any | None:
    if _uses_mysql_budget_path(budget_path):
        return await get_pool().fetch_one(
            """
            SELECT version_name, current_month
            FROM version
            WHERE version_id = %s AND budget_year = %s
            """,
            (source_version_id, source_year),
        )
    with sqlite3.connect(budget_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_budget_version_schema_sync(conn)
        return conn.execute(
            "SELECT version_name, current_month FROM version WHERE version_id = ?",
            (source_version_id,),
        ).fetchone()


async def _budget_summary_count(budget_path: Path, source_version_id: int, source_year: int) -> int:
    if _uses_mysql_budget_path(budget_path):
        row = await get_pool().fetch_one(
            """
            SELECT COUNT(*) AS row_count
            FROM budget_summary
            WHERE version_id = %s AND budget_year = %s
            """,
            (source_version_id, source_year),
        )
        return int(_row_value(row, "row_count", 0) or 0) if row else 0
    with sqlite3.connect(budget_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_budget_read_model_schema(conn)
        row = conn.execute(
            "SELECT COUNT(*) FROM budget_summary WHERE version_id = ?",
            (source_version_id,),
        ).fetchone()
        return int(row[0] or 0) if row else 0


async def _load_budget_summary_rows(budget_path: Path, source_version_id: int, source_year: int) -> list[Any]:
    sql = """
        SELECT metric_level1, metric_level2, metric_level3, metric_level4, metric_level5,
               dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
               year, month, quarter, budget_actual, version_name, value, value_type,
               value_source
        FROM budget_summary
        WHERE version_id = ?{budget_year_filter}
        ORDER BY metric_level1, metric_level2, metric_level3, data_code_name, month, budget_actual
        """
    if _uses_mysql_budget_path(budget_path):
        return await get_pool().fetch_all(
            sql.format(budget_year_filter=" AND budget_year = ?").replace("?", "%s"),
            (source_version_id, source_year),
        )
    with sqlite3.connect(budget_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_budget_read_model_schema(conn)
        return conn.execute(
            sql.format(budget_year_filter=""),
            (source_version_id,),
        ).fetchall()


def _compare_insert_sql(placeholder: str) -> str:
    return f"""
        INSERT INTO compare_budget_summary (
          show_level, data_file_id, source_year, source_version_id, source_version_name,
          metric_level1, metric_level2, metric_level3, metric_level4, metric_level5,
          dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
          year, month, quarter, budget_actual, value, value_type, value_source, sync_time
        ) VALUES ({', '.join([placeholder] * 23)})
        """


def _compare_job_log_sql(placeholder: str) -> str:
    return f"""
        INSERT INTO compare_sync_job_log (
          start_time, end_time, trigger_source, status, message, operator_user_id
        ) VALUES ({', '.join([placeholder] * 6)})
        """


async def _write_compare_success(
    compare_path: Path,
    rows_to_insert: list[tuple[Any, ...]],
    *,
    start_time: str,
    end_time: str,
    trigger_source: str,
    status: str,
    message: str,
    operator_user_id: int | None,
) -> None:
    if _uses_mysql_compare_path(compare_path):
        await get_pool().execute("DELETE FROM compare_budget_summary")
        if rows_to_insert:
            await get_pool().execute_many(_compare_insert_sql("%s"), rows_to_insert)
        await get_pool().execute(
            _compare_job_log_sql("%s"),
            (start_time, end_time, trigger_source, status, message, operator_user_id),
        )
        return
    with sqlite3.connect(compare_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_compare_read_model_schema(conn)
        conn.execute("DELETE FROM compare_budget_summary")
        if rows_to_insert:
            conn.executemany(_compare_insert_sql("?"), rows_to_insert)
        conn.execute(
            _compare_job_log_sql("?"),
            (start_time, end_time, trigger_source, status, message, operator_user_id),
        )
        conn.commit()


async def _write_compare_failure_log(
    compare_path: Path,
    *,
    start_time: str,
    end_time: str,
    trigger_source: str,
    status: str,
    message: str,
    operator_user_id: int | None,
) -> None:
    if _uses_mysql_compare_path(compare_path):
        await get_pool().execute(
            _compare_job_log_sql("%s"),
            (start_time, end_time, trigger_source, status, message, operator_user_id),
        )
        return
    with sqlite3.connect(compare_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_compare_read_model_schema(conn)
        conn.execute(
            _compare_job_log_sql("?"),
            (start_time, end_time, trigger_source, status, message, operator_user_id),
        )
        conn.commit()


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
                selected = await _load_selected_versions(common_path)

                selected_versions = len(selected)
                rows_to_insert: list[tuple[Any, ...]] = []
                for row in selected:
                    show_level = int(_row_value(row, "edit_show_sign", 0))
                    data_file_id = int(_row_value(row, "data_file_id", 1))
                    source_version_id = int(_row_value(row, "version_id", 2))
                    data_file_name = str(_row_value(row, "data_file_name", 3))
                    source_year = int(_row_value(row, "year", 4))
                    budget_path = settings.data_dir / str(data_file_name)
                    if not _uses_mysql_budget_path(budget_path) and not budget_path.exists():
                        continue
                    ver_row = await _fetch_budget_version_row(budget_path, source_version_id, source_year)
                    if not ver_row:
                        raise HTTPException(status_code=400, detail=f"版本 {int(source_version_id)} 不存在")
                    version_name_raw = _row_value(ver_row, "version_name", 0)
                    ver_name = str(version_name_raw) if version_name_raw is not None else None
                    current_month = int(_row_value(ver_row, "current_month", 1))
                    level_rules.append(
                        f"L{int(show_level)}: {data_file_name} / V{int(source_version_id)}"
                        f"{(' ' + ver_name) if ver_name else ''} / current_month={current_month}"
                        f" / month<{current_month}取实际, month>={current_month}取预算"
                    )
                    summary_count = await _budget_summary_count(budget_path, source_version_id, source_year)
                    if summary_count == 0:
                        await rebuild_budget_summary_for_version(
                            int(source_version_id),
                            budget_path,
                        )
                        summary_count = await _budget_summary_count(budget_path, source_version_id, source_year)
                    if summary_count == 0:
                        level_rules.append(
                            f"L{int(show_level)}: {data_file_name} / V{int(source_version_id)} 汇总明细为空（budget_data 无记录）"
                        )
                    for summary_row in await _load_budget_summary_rows(budget_path, source_version_id, source_year):
                        rows_to_insert.append(
                            (
                                int(show_level),
                                int(data_file_id),
                                int(source_year),
                                int(source_version_id),
                                ver_name or _row_value(summary_row, "version_name", 14),
                                _row_value(summary_row, "metric_level1", 0),
                                _row_value(summary_row, "metric_level2", 1),
                                _row_value(summary_row, "metric_level3", 2),
                                _row_value(summary_row, "metric_level4", 3),
                                _row_value(summary_row, "metric_level5", 4),
                                _row_value(summary_row, "dept_level1", 5),
                                _row_value(summary_row, "dept_level2", 6),
                                _row_value(summary_row, "dept_level3", 7),
                                _row_value(summary_row, "data_code_name", 8),
                                _row_value(summary_row, "product_code_name", 9),
                                _row_value(summary_row, "year", 10),
                                _row_value(summary_row, "month", 11),
                                _row_value(summary_row, "quarter", 12),
                                int(_row_value(summary_row, "budget_actual", 13) or 0),
                                float(_row_value(summary_row, "value", 15) or 0.0),
                                _row_value(summary_row, "value_type", 16),
                                _row_value(summary_row, "value_source", 17),
                                start_time,
                            )
                        )

                inserted_rows = len(rows_to_insert)
                if level_rules:
                    rule_message = "；".join(level_rules)
                end_time = _iso_now()
                await _write_compare_success(
                    compare_path,
                    rows_to_insert,
                    start_time=start_time,
                    end_time=end_time,
                    trigger_source=trigger_source,
                    status=status,
                    message=message,
                    operator_user_id=operator_user_id,
                )
                await self._set_compare_refresh_time(end_time)
            except Exception as exc:
                status = "failed"
                message = str(exc)
                end_time = _iso_now()
                await _write_compare_failure_log(
                    compare_path,
                    start_time=start_time,
                    end_time=end_time,
                    trigger_source=trigger_source,
                    status=status,
                    message=message,
                    operator_user_id=operator_user_id,
                )
                raise HTTPException(status_code=500, detail=f"同步 compare_summary 失败: {exc}")

            return CompareSummarySyncResult(
                inserted_rows=inserted_rows,
                selected_versions=selected_versions,
                trigger_source=trigger_source,
                message=message,
                rule_message=rule_message,
                level_rules=level_rules,
            )
