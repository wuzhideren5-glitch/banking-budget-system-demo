from __future__ import annotations

import json
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.core.database import get_pool
from app.db_bootstrap.derived_read_models import (
    ensure_budget_read_model_schema,
    ensure_compare_read_model_schema,
)
from app.core.db_paths import common_db_path, compare_db_path
from app.schemas import BudgetSummaryAggregateRequest, BudgetSummaryRowDto, CompareSummaryRowDto
from app.services.runtime_metric_refs import derive_runtime_ref_from_org_product_metric_code
from app.services.org_product_metric_runtime_snapshot import load_org_product_metric_table_rows_from_runtime_tree


PIVOT_AGGREGATE_FIELDS = {
    "metric_level1",
    "metric_level2",
    "metric_level3",
    "metric_level4",
    "metric_level5",
    "dept_level1",
    "dept_level2",
    "dept_level3",
    "data_code_name",
    "product_code_name",
    "year",
    "month",
    "quarter",
    "budget_actual",
    "version_display",
    "value_type",
    "value_source",
}

TEXT_SEARCH_FIELDS = [
    "metric_level1",
    "metric_level2",
    "metric_level3",
    "metric_level4",
    "metric_level5",
    "dept_level1",
    "dept_level2",
    "dept_level3",
    "data_code_name",
    "product_code_name",
    "year",
    "month",
    "quarter",
    "value_type",
    "value_source",
]

MAX_PIVOT_SEARCH_ALIASES_PER_KEYWORD = 24


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    keys = getattr(row, "keys", None)
    if callable(keys) and key in keys():
        return row[key]
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


def _mysql_sql(sql: str) -> str:
    return sql.replace("?", "%s")


async def _fetch_all_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_all(_mysql_sql(sql), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, params).fetchall()


async def _fetch_one_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> Any:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_one(_mysql_sql(sql), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, params).fetchone()


async def _execute_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> int:
    if _uses_mysql_path(db_path):
        return await get_pool().execute(_mysql_sql(sql), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        cur = db.execute(sql, params)
        db.commit()
        return cur.rowcount


def _ensure_sqlite_budget_read_models(db_path: Path) -> None:
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        ensure_budget_read_model_schema(db)
        db.commit()


def _ensure_sqlite_compare_read_models(db_path: Path) -> None:
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        ensure_compare_read_model_schema(db)
        db.commit()


def _fields_from_request(body: BudgetSummaryAggregateRequest) -> set[str]:
    fields = {
        str(field_id).strip()
        for field_id in [*body.row_field_ids, *body.column_field_ids, *body.page_field_ids]
        if str(field_id).strip()
    }
    return {field for field in fields if field in PIVOT_AGGREGATE_FIELDS}


def _grain_for_fields(fields: set[str]) -> str:
    if "month" in fields:
        return "month"
    if "quarter" in fields:
        return "quarter"
    return "year"


def _normalize_org_product_search_token(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().upper()


def _is_05_code(raw_code: Any, *, entity_code: str = "") -> bool:
    code = _normalize_org_product_search_token(str(raw_code or ""))
    if not code:
        return False
    if "." in code:
        parts = [part for part in code.split(".") if part]
        return bool(parts) and (parts[0] == "05" or (len(parts) >= 2 and parts[1] == "05"))
    owner = _normalize_org_product_search_token(entity_code)
    if owner and code.startswith(owner):
        remainder = code[len(owner) :]
    elif code.startswith(("AA", "AB")):
        remainder = code[2:]
    else:
        remainder = code[3:] if len(code) >= 3 else ""
    return len(remainder) >= 2 and remainder[:2] == "05"


def _org_product_children(metric: dict[str, Any]) -> list[dict[str, Any]]:
    children = metric.get("children")
    return [item for item in children if isinstance(item, dict)] if isinstance(children, list) else []


def _search_alias_keys(*values: str) -> set[str]:
    keys: set[str] = set()
    for value in values:
        normalized = _normalize_org_product_search_token(value)
        if not normalized:
            continue
        keys.add(normalized)
        compact = re.sub(r"[:：|/\\-]+", "", normalized)
        if compact:
            keys.add(compact)
    return keys


def _load_org_product_search_aliases(common_path: Path | None = None) -> dict[str, set[str]]:
    db_path = common_path or common_db_path()
    aliases: dict[str, set[str]] = {}
    if _uses_mysql_path(db_path):
        return aliases
    if not db_path.exists():
        return aliases
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = load_org_product_metric_table_rows_from_runtime_tree(conn)
    except Exception:
        return aliases

    for row in rows:
        entity_code = str(row["entity_code"] or "").strip().upper()
        table_name = str(row["table_name"] or "").strip()
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except Exception:
            continue
        metrics = payload.get("metrics")
        stack = [item for item in metrics if isinstance(item, dict)] if isinstance(metrics, list) else []
        while stack:
            metric = stack.pop(0)
            stack.extend(_org_product_children(metric))
            metric_code = str(metric.get("code") or "").strip().upper()
            metric_name = str(metric.get("name") or "").strip()
            data_acct_code = derive_runtime_ref_from_org_product_metric_code(
                entity_code=entity_code,
                metric_code=metric_code,
            )
            metric_node_code = data_acct_code
            source_ref = f"{entity_code}:{table_name}:{metric_code}" if metric_code else ""
            alias_values = {
                value
                for value in [metric_code, metric_name, metric_node_code, data_acct_code, source_ref]
                if value
            }
            if not alias_values:
                continue
            for key in _search_alias_keys(metric_code, metric_name, metric_node_code, data_acct_code, source_ref):
                aliases.setdefault(key, set()).update(alias_values)
    return aliases


async def _load_org_product_search_aliases_mysql() -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
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
        return aliases
    for row in rows:
        entity_code = str(_row_value(row, "product_code", 2) or "").strip().upper()
        table_name = str(_row_value(row, "metric_table_name", 3) or "").strip()
        metric_code = str(_row_value(row, "node_code", 0) or "").strip().upper()
        metric_name = str(_row_value(row, "node_name", 1) or "").strip()
        data_acct_code = (
            derive_runtime_ref_from_org_product_metric_code(
                entity_code=entity_code,
                metric_code=metric_code,
            )
            or metric_code
        )
        source_ref = f"{entity_code}:{table_name}:{metric_code}" if metric_code else ""
        alias_values = {
            value
            for value in [metric_code, metric_name, data_acct_code, source_ref]
            if value
        }
        if not alias_values:
            continue
        for key in _search_alias_keys(metric_code, metric_name, data_acct_code, source_ref):
            aliases.setdefault(key, set()).update(alias_values)
    return aliases


def _expand_search_keyword(keyword: str, *, common_path: Path | None = None) -> list[str]:
    normalized = _normalize_org_product_search_token(keyword)
    expanded = {keyword}
    if normalized:
        expanded.update(_load_org_product_search_aliases(common_path).get(normalized, set()))
    return sorted(
        (item for item in expanded if str(item).strip()),
        key=lambda item: (0 if item == keyword else 1, str(item)),
    )[:MAX_PIVOT_SEARCH_ALIASES_PER_KEYWORD]


async def _expand_search_keyword_async(keyword: str, *, common_path: Path | None = None) -> list[str]:
    normalized = _normalize_org_product_search_token(keyword)
    expanded = {keyword}
    path = common_path or common_db_path()
    if normalized:
        if _uses_mysql_path(path):
            expanded.update((await _load_org_product_search_aliases_mysql()).get(normalized, set()))
        else:
            expanded.update(_load_org_product_search_aliases(path).get(normalized, set()))
    return sorted(
        (item for item in expanded if str(item).strip()),
        key=lambda item: (0 if item == keyword else 1, str(item)),
    )[:MAX_PIVOT_SEARCH_ALIASES_PER_KEYWORD]


async def ensure_budget_pivot_aggregate_table(db: Any) -> None:
    if isinstance(db, (str, Path)):
        db_path = Path(db)
        if not _uses_mysql_path(db_path):
            _ensure_sqlite_budget_read_models(db_path)
        return
    ensure_budget_read_model_schema(db)


async def ensure_compare_pivot_aggregate_table(db: Any) -> None:
    if isinstance(db, (str, Path)):
        db_path = Path(db)
        if not _uses_mysql_path(db_path):
            _ensure_sqlite_compare_read_models(db_path)
        return
    ensure_compare_read_model_schema(db)


def _budget_insert_sql(grain: str, *, include_budget_year: bool = False) -> str:
    month_expr = "month" if grain == "month" else "'全部'"
    quarter_expr = "quarter" if grain in {"month", "quarter"} else "'全部'"
    group_cols = [
        "metric_level1",
        "metric_level2",
        "metric_level3",
        "metric_level4",
        "metric_level5",
        "dept_level1",
        "dept_level2",
        "dept_level3",
        "data_code_name",
        "product_code_name",
        "year",
        "budget_actual",
        "version_id",
        "version_name",
        "value_type",
        "value_source",
    ]
    if include_budget_year:
        group_cols.insert(0, "budget_year")
    if grain == "month":
        group_cols.extend(["month", "quarter"])
    elif grain == "quarter":
        group_cols.append("quarter")
    group_by = ", ".join(group_cols)
    budget_year_cols = "budget_year, " if include_budget_year else ""
    budget_year_select = "budget_year, " if include_budget_year else ""
    return f"""
        INSERT INTO budget_pivot_aggregate (
          {budget_year_cols}grain, metric_level1, metric_level2, metric_level3, metric_level4, metric_level5,
          dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
          year, month, quarter, budget_actual, version_id, version_name, value, value_type, value_source, update_time
        )
        SELECT
          {budget_year_select}? AS grain, metric_level1, metric_level2, metric_level3, metric_level4, metric_level5,
          dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
          year, {month_expr} AS month, {quarter_expr} AS quarter, budget_actual, version_id, version_name,
          SUM(value) AS value, value_type, value_source, ? AS update_time
        FROM budget_summary
        WHERE version_id = ?
        GROUP BY {group_by}
    """


def _compare_insert_sql(grain: str) -> str:
    month_expr = "month" if grain == "month" else "'全部'"
    quarter_expr = "quarter" if grain in {"month", "quarter"} else "'全部'"
    group_cols = [
        "show_level",
        "data_file_id",
        "source_year",
        "source_version_id",
        "source_version_name",
        "metric_level1",
        "metric_level2",
        "metric_level3",
        "metric_level4",
        "metric_level5",
        "dept_level1",
        "dept_level2",
        "dept_level3",
        "data_code_name",
        "product_code_name",
        "year",
        "budget_actual",
        "value_type",
        "value_source",
    ]
    if grain == "month":
        group_cols.extend(["month", "quarter"])
    elif grain == "quarter":
        group_cols.append("quarter")
    group_by = ", ".join(group_cols)
    return f"""
        INSERT INTO compare_pivot_aggregate (
          grain, show_level, data_file_id, source_year, source_version_id, source_version_name,
          metric_level1, metric_level2, metric_level3, metric_level4, metric_level5,
          dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
          year, month, quarter, budget_actual, value, value_type, value_source, sync_time
        )
        SELECT
          ? AS grain, show_level, data_file_id, source_year, source_version_id, source_version_name,
          metric_level1, metric_level2, metric_level3, metric_level4, metric_level5,
          dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
          year, {month_expr} AS month, {quarter_expr} AS quarter, budget_actual,
          SUM(value) AS value, value_type, value_source, ? AS sync_time
        FROM compare_budget_summary
        GROUP BY {group_by}
    """


async def rebuild_budget_pivot_aggregate_for_version(version_id: int, budget_path: Path) -> int:
    now = _iso_now()
    await ensure_budget_pivot_aggregate_table(budget_path)
    await _execute_for_path(budget_path, "DELETE FROM budget_pivot_aggregate WHERE version_id = ?", (int(version_id),))
    include_budget_year = _uses_mysql_path(budget_path)
    for grain in ("year", "quarter", "month"):
        await _execute_for_path(
            budget_path,
            _budget_insert_sql(grain, include_budget_year=include_budget_year),
            (grain, now, int(version_id)),
        )
    row = await _fetch_one_for_path(
        budget_path,
        "SELECT COUNT(*) AS aggregate_count FROM budget_pivot_aggregate WHERE version_id = ?",
        (int(version_id),),
    )
    return int(_row_value(row, "aggregate_count", 0) or 0) if row else 0


async def rebuild_compare_pivot_aggregate() -> int:
    now = _iso_now()
    compare_path = compare_db_path()
    await ensure_compare_pivot_aggregate_table(compare_path)
    await _execute_for_path(compare_path, "DELETE FROM compare_pivot_aggregate")
    for grain in ("year", "quarter", "month"):
        await _execute_for_path(compare_path, _compare_insert_sql(grain), (grain, now))
    row = await _fetch_one_for_path(
        compare_path,
        "SELECT COUNT(*) AS aggregate_count FROM compare_pivot_aggregate",
    )
    return int(_row_value(row, "aggregate_count", 0) or 0) if row else 0


def _search_where(search_text: str, values: list[Any], *, common_path: Path | None = None) -> str:
    keywords = [kw.strip() for kw in search_text.replace("，", " ").replace(",", " ").split() if kw.strip()]
    clauses: list[str] = []
    for keyword in keywords:
        one = []
        for alias in _expand_search_keyword(keyword, common_path=common_path):
            like = f"%{alias}%"
            for field in TEXT_SEARCH_FIELDS:
                one.append(f"COALESCE({field}, '') LIKE ?")
                values.append(like)
            one.append("CAST(budget_actual AS CHAR) LIKE ?")
            values.append(like)
        clauses.append("(" + " OR ".join(one) + ")")
    return (" AND " + " AND ".join(clauses)) if clauses else ""


async def _search_where_async(search_text: str, values: list[Any], *, common_path: Path | None = None) -> str:
    keywords = [kw.strip() for kw in search_text.replace("，", " ").replace(",", " ").split() if kw.strip()]
    clauses: list[str] = []
    for keyword in keywords:
        one = []
        for alias in await _expand_search_keyword_async(keyword, common_path=common_path):
            like = f"%{alias}%"
            for field in TEXT_SEARCH_FIELDS:
                one.append(f"COALESCE({field}, '') LIKE ?")
                values.append(like)
            one.append("CAST(budget_actual AS CHAR) LIKE ?")
            values.append(like)
        clauses.append("(" + " OR ".join(one) + ")")
    return (" AND " + " AND ".join(clauses)) if clauses else ""


def _select_expr(field: str, selected_fields: set[str], *, compare: bool) -> str:
    if field in selected_fields:
        if field == "budget_actual":
            return "budget_actual"
        return f"COALESCE({field}, '未设置')"
    if field == "budget_actual":
        return "0"
    if field in {"year", "month", "quarter"}:
        return "'全部'"
    if field == "data_code_name":
        return "'聚合指标编码'"
    if field == "value_type":
        return "value_type"
    return "NULL"


def _group_cols(selected_fields: set[str], *, compare: bool) -> list[str]:
    cols: list[str] = []
    for field in [
        "metric_level1",
        "metric_level2",
        "metric_level3",
        "metric_level4",
        "metric_level5",
        "dept_level1",
        "dept_level2",
        "dept_level3",
        "data_code_name",
        "product_code_name",
        "year",
        "month",
        "quarter",
        "budget_actual",
    ]:
        if field in selected_fields:
            cols.append(field)
    if "version_display" in selected_fields:
        if compare:
            cols.extend(["show_level", "source_year", "source_version_id", "source_version_name"])
        else:
            cols.extend(["version_id", "version_name"])
    cols.append("value_type")
    if "value_source" in selected_fields:
        cols.append("value_source")
    return cols


def _group_sql(cols: list[str], *, table_name: str, db_path: Path) -> str:
    if _uses_mysql_path(db_path):
        return ", ".join(f"{table_name}.{col}" for col in cols)
    return ", ".join(cols)


def _apply_page_filters(body: BudgetSummaryAggregateRequest, selected_fields: set[str], values: list[Any], *, compare: bool) -> str:
    clauses: list[str] = []
    for field, raw_selected in body.page_selections.items():
        if field not in selected_fields:
            continue
        selected = str(raw_selected or "").strip()
        if not selected or selected == "全部":
            continue
        if field == "budget_actual":
            if selected == "预算":
                clauses.append("budget_actual = ?")
                values.append(0)
            elif selected == "实际":
                clauses.append("budget_actual = ?")
                values.append(1)
            continue
        if field == "version_display":
            import re

            match = re.search(r"版本号[:：]\s*(\d+)", selected)
            if match:
                if compare:
                    clauses.append("source_version_id = ?")
                else:
                    clauses.append("version_id = ?")
                values.append(int(match.group(1)))
            continue
        if field in PIVOT_AGGREGATE_FIELDS:
            clauses.append(f"COALESCE({field}, '未设置') = ?")
            values.append(selected)
    return (" AND " + " AND ".join(clauses)) if clauses else ""


async def list_budget_pivot_aggregate_rows(
    *,
    budget_path: Path,
    body: BudgetSummaryAggregateRequest,
    current_month_by_version: dict[int, int],
) -> list[BudgetSummaryRowDto]:
    selected_fields = _fields_from_request(body)
    grain = _grain_for_fields(selected_fields)
    budget_path = Path(budget_path)
    values: list[Any] = [grain]
    await ensure_budget_pivot_aggregate_table(budget_path)
    count_row = await _fetch_one_for_path(
        budget_path,
        "SELECT COUNT(*) AS aggregate_count FROM budget_pivot_aggregate WHERE grain = ?",
        (grain,),
    )
    if int(_row_value(count_row, "aggregate_count", 0) or 0) == 0:
        raise HTTPException(status_code=409, detail="多维分析聚合表为空，请先在“预算事实刷新跑批”执行跑批生成聚合表。")
    select_fields = [
        "metric_level1",
        "metric_level2",
        "metric_level3",
        "metric_level4",
        "metric_level5",
        "dept_level1",
        "dept_level2",
        "dept_level3",
        "data_code_name",
        "product_code_name",
        "year",
        "month",
        "quarter",
        "budget_actual",
        "value_source",
    ]
    select_sql = ", ".join(f"{_select_expr(field, selected_fields, compare=False)} AS {field}" for field in select_fields)
    if "version_display" in selected_fields:
        version_sql = "version_id, version_name"
    else:
        version_sql = "0 AS version_id, '聚合版本' AS version_name"
    where = "grain = ?"
    if "data_code_name" not in selected_fields and "value_source" not in selected_fields:
        where += " AND value_source <> 'rollup'"
    where += _apply_page_filters(body, selected_fields, values, compare=False)
    where += await _search_where_async(body.pivot_search_text, values, common_path=common_db_path())
    group_cols = _group_cols(selected_fields, compare=False)
    group_sql = _group_sql(group_cols, table_name="budget_pivot_aggregate", db_path=budget_path)
    rows = await _fetch_all_for_path(
        budget_path,
        f"""
        SELECT {select_sql}, {version_sql}, SUM(value) AS value, value_type, MAX(update_time) AS update_time
        FROM budget_pivot_aggregate
        WHERE {where}
        GROUP BY {group_sql}
        ORDER BY {group_sql}
        """,
        tuple(values),
    )
    result: list[BudgetSummaryRowDto] = []
    for row in rows:
        version_id = int(_row_value(row, "version_id", 15) or 0)
        if version_id not in current_month_by_version:
            raise HTTPException(status_code=400, detail=f"版本 {version_id} 缺少 current_month")
        current_month = int(current_month_by_version[version_id])
        result.append(
            BudgetSummaryRowDto(
                metric_level1=_row_value(row, "metric_level1", 0),
                metric_level2=_row_value(row, "metric_level2", 1),
                metric_level3=_row_value(row, "metric_level3", 2),
                metric_level4=_row_value(row, "metric_level4", 3),
                metric_level5=_row_value(row, "metric_level5", 4),
                dept_level1=_row_value(row, "dept_level1", 5),
                dept_level2=_row_value(row, "dept_level2", 6),
                dept_level3=_row_value(row, "dept_level3", 7),
                data_code_name=str(_row_value(row, "data_code_name", 8) or "聚合指标编码"),
                product_code_name=_row_value(row, "product_code_name", 9),
                year=str(_row_value(row, "year", 10) or "全部"),
                month=str(_row_value(row, "month", 11) or "全部"),
                quarter=str(_row_value(row, "quarter", 12) or "全部"),
                budget_actual=int(_row_value(row, "budget_actual", 13) or 0),
                value_source=_row_value(row, "value_source", 14),
                version_id=version_id,
                version_name=_row_value(row, "version_name", 16),
                current_month=current_month,
                rule_message=f"读取多维聚合表 grain={grain}；聚合规则=sum；聚合表由预算事实刷新跑批生成。",
                value=float(_row_value(row, "value", 17) or 0.0),
                value_type=str(_row_value(row, "value_type", 18) or ""),
                update_time=_row_value(row, "update_time", 19),
            )
        )
    return result


async def list_compare_pivot_aggregate_rows(body: BudgetSummaryAggregateRequest) -> list[CompareSummaryRowDto]:
    selected_fields = _fields_from_request(body)
    grain = _grain_for_fields(selected_fields)
    values: list[Any] = [grain]
    compare_path = compare_db_path()
    await ensure_compare_pivot_aggregate_table(compare_path)
    count_row = await _fetch_one_for_path(
        compare_path,
        "SELECT COUNT(*) AS aggregate_count FROM compare_pivot_aggregate WHERE grain = ?",
        (grain,),
    )
    if int(_row_value(count_row, "aggregate_count", 0) or 0) == 0:
        raise HTTPException(status_code=409, detail="多年度对比聚合表为空，请先在“预算事实刷新跑批”执行跑批并同步对比聚合表。")
    select_fields = [
        "metric_level1",
        "metric_level2",
        "metric_level3",
        "metric_level4",
        "metric_level5",
        "dept_level1",
        "dept_level2",
        "dept_level3",
        "data_code_name",
        "product_code_name",
        "year",
        "month",
        "quarter",
        "budget_actual",
        "value_source",
    ]
    select_sql = ", ".join(f"{_select_expr(field, selected_fields, compare=True)} AS {field}" for field in select_fields)
    if "version_display" in selected_fields:
        version_sql = "show_level, data_file_id, source_year, source_version_id, source_version_name"
    else:
        version_sql = "0 AS show_level, 0 AS data_file_id, 0 AS source_year, 0 AS source_version_id, '聚合版本' AS source_version_name"
    where = "grain = ?"
    if "data_code_name" not in selected_fields and "value_source" not in selected_fields:
        where += " AND value_source <> 'rollup'"
    where += _apply_page_filters(body, selected_fields, values, compare=True)
    where += await _search_where_async(body.pivot_search_text, values, common_path=common_db_path())
    group_cols = _group_cols(selected_fields, compare=True)
    group_sql = _group_sql(group_cols, table_name="compare_pivot_aggregate", db_path=compare_path)
    rows = await _fetch_all_for_path(
        compare_path,
        f"""
        SELECT {version_sql}, {select_sql}, SUM(value) AS value, value_type, MAX(sync_time) AS sync_time
        FROM compare_pivot_aggregate
        WHERE {where}
        GROUP BY {group_sql}
        ORDER BY {group_sql}
        """,
        tuple(values),
    )
    result: list[CompareSummaryRowDto] = []
    for row in rows:
        result.append(
            CompareSummaryRowDto(
                show_level=int(_row_value(row, "show_level", 0) or 0),
                data_file_id=int(_row_value(row, "data_file_id", 1) or 0),
                source_year=int(_row_value(row, "source_year", 2) or 0),
                source_version_id=int(_row_value(row, "source_version_id", 3) or 0),
                source_version_name=_row_value(row, "source_version_name", 4),
                metric_level1=_row_value(row, "metric_level1", 5),
                metric_level2=_row_value(row, "metric_level2", 6),
                metric_level3=_row_value(row, "metric_level3", 7),
                metric_level4=_row_value(row, "metric_level4", 8),
                metric_level5=_row_value(row, "metric_level5", 9),
                dept_level1=_row_value(row, "dept_level1", 10),
                dept_level2=_row_value(row, "dept_level2", 11),
                dept_level3=_row_value(row, "dept_level3", 12),
                data_code_name=str(_row_value(row, "data_code_name", 13) or "聚合指标编码"),
                product_code_name=_row_value(row, "product_code_name", 14),
                year=str(_row_value(row, "year", 15) or "全部"),
                month=str(_row_value(row, "month", 16) or "全部"),
                quarter=str(_row_value(row, "quarter", 17) or "全部"),
                budget_actual=int(_row_value(row, "budget_actual", 18) or 0),
                value_source=_row_value(row, "value_source", 19),
                value=float(_row_value(row, "value", 20) or 0.0),
                value_type=str(_row_value(row, "value_type", 21) or ""),
                sync_time=str(_row_value(row, "sync_time", 22) or ""),
            )
        )
    return result
