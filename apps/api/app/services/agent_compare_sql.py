"""SQL builder for Agent compare read-model analysis."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import re
from typing import Any, Mapping

from app.services.agent_analysis_filters import (
    analysis_fact_filters,
    pm_metric_locked_without_data,
    pm_metric_scope_label,
    sql_escape_literal,
)
from app.services.agent_compare_version import compare_level_meta, is_yoy_requested


def strip_year_constraints(scope_sql: str) -> str:
    """Remove base-year filters before building separate base/compare WHERE clauses."""
    if not scope_sql:
        return ""
    text = str(scope_sql)
    text = re.sub(
        r"\(\s*year\s*=\s*'Y20\d{2}'\s+AND\s+(month|quarter)\s+IN\s*\(([^)]*)\)\s*\)",
        r"(\1 IN (\2))",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+AND\s+year\s*=\s*'Y20\d{2}'", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\(\s*year\s*=\s*'Y20\d{2}'\s*\)", "", text, flags=re.IGNORECASE)
    return text


def _compare_dimension(query: str) -> str:
    if "部门" in query:
        return "dept_level1"
    if "科目" in query:
        return "data_code_name"
    if "产品" in query:
        return "product_code_name"
    return ""


def _comparison_requested(query: str, comparison_type: str) -> bool:
    return bool(
        re.search(r"(预算.?实际|预实|差异|偏差|同比|环比|对比|比较|vs)", query)
        or comparison_type in {"budget_vs_actual", "yoy", "mom"}
    )


def _comparison_columns_requested(query: str, comparison_type: str) -> bool:
    return bool(
        _comparison_requested(query, comparison_type)
        or re.search(r"(预算.*实际.*两列|口径.*两列|分两列|并列展示|列展示)", query)
    )


def suggest_compare_l1_sql(
    query: str,
    *,
    year_tag: str,
    month_tag: str | None,
    show_level: int,
    state: Mapping[str, Any] | None = None,
    compare_db: Path,
    common_db: Path,
    today: date | None = None,
) -> str:
    state_map = state if isinstance(state, Mapping) else {}
    scope = analysis_fact_filters(state_map, query, today=today)
    pm = state_map.get("pm_query_spec") if isinstance(state_map.get("pm_query_spec"), dict) else None
    clarified = state_map.get("clarified_slots", {}) if isinstance(state_map.get("clarified_slots", {}), dict) else {}
    scope_has_time_filter = bool(
        re.search(r"\b(month|quarter)\s+in\s*\(|\b(month|quarter)\s*=", scope, flags=re.I)
    )
    yoy = is_yoy_requested(query, clarified)
    compare_level = int((clarified or {}).get("comparison_show_level") or show_level or 1)
    compare_level = compare_level if 1 <= compare_level <= 5 else 1
    base_level = 1
    base_year_tag = str(state_map.get("query_base_year_tag") or year_tag or "").strip() or year_tag
    compare_year_tag = str(state_map.get("query_compare_year_tag") or "").strip()
    if not compare_year_tag:
        meta = compare_level_meta(
            compare_db=compare_db,
            common_db=common_db,
            show_level=compare_level,
        )
        compare_year = int(meta.get("source_year") or 0)
        if compare_year > 0:
            compare_year_tag = f"Y{compare_year}"
        else:
            match = re.search(r"Y(\d{4})", base_year_tag)
            base_year = int(match.group(1)) if match else (today or date.today()).year
            compare_year_tag = f"Y{max(base_year - 1, 2000)}"

    if yoy:
        scope_yoy = strip_year_constraints(scope)
        granularity = str((clarified or {}).get("granularity") or "").strip().lower()
        time_col = "month"
        if ("quarter" in granularity) or re.search(r"(按季|季度)", query):
            time_col = "quarter"
        elif ("year" in granularity) or (
            re.search(r"(按年|年度)", query) and not re.search(r"(按月|每月|月份|月度)", query)
        ):
            time_col = "year"
        month_sql = f" AND month = '{month_tag}'" if (time_col == "month" and month_tag and not scope_has_time_filter) else ""
        base_where = f"show_level = {base_level} AND year = '{base_year_tag}'{month_sql}{scope_yoy}"
        compare_where = f"show_level = {compare_level} AND year = '{compare_year_tag}'{month_sql}{scope_yoy}"
        dim = _compare_dimension(query)
        dim_select = f"b.{dim}, " if dim else ""
        dim_group = f"{dim}, {time_col}" if dim else f"{time_col}"
        dim_join = f"b.{dim} = c.{dim} AND " if dim else ""
        order_by = f"b.{dim}, b.{time_col}" if dim else f"b.{time_col}"
        month_type_cols = (
            "CASE WHEN COALESCE(b.base_budget_actual, 0) = 1 THEN '实际' ELSE '预算' END AS '基准口径', "
            "CASE WHEN COALESCE(c.compare_budget_actual, 0) = 1 THEN '实际' ELSE '预算' END AS '比较口径', "
            if time_col == "month"
            else ""
        )
        return (
            "WITH base AS ("
            f"SELECT {dim_group}, SUM(value) AS base_value, MAX(budget_actual) AS base_budget_actual "
            f"FROM compare_budget_summary WHERE {base_where} "
            f"GROUP BY {dim_group}"
            "), cmp AS ("
            f"SELECT {dim_group}, SUM(value) AS compare_value, MAX(budget_actual) AS compare_budget_actual "
            f"FROM compare_budget_summary WHERE {compare_where} "
            f"GROUP BY {dim_group}"
            ") "
            f"SELECT {dim_select}b.{time_col}, "
            "COALESCE(b.base_value, 0) AS '基准值', "
            "COALESCE(c.compare_value, 0) AS '比较值', "
            f"{month_type_cols}"
            "COALESCE(b.base_value, 0) - COALESCE(c.compare_value, 0) AS '同比变化量', "
            "CASE "
            "WHEN ABS(COALESCE(c.compare_value, 0)) < 1e-9 THEN NULL "
            "ELSE ROUND((COALESCE(b.base_value, 0) - COALESCE(c.compare_value, 0)) / ABS(c.compare_value) * 100.0, 2) "
            "END AS '同比变化比例(%)' "
            "FROM base b LEFT JOIN cmp c "
            f"ON {dim_join}b.{time_col} = c.{time_col} "
            f"ORDER BY {order_by} "
            "LIMIT 5000"
        )

    comparison_type = str((clarified or {}).get("comparison_type") or "").strip().lower()
    compare_requested = _comparison_columns_requested(query, comparison_type)
    prefer_report_agg = pm_metric_locked_without_data(pm)
    report_scope_label = pm_metric_scope_label(pm)
    report_scope_sql = (
        f"'{sql_escape_literal(report_scope_label)}' AS report_scope, "
        if report_scope_label
        else ""
    )
    month_sql = f" AND month = '{month_tag}'" if month_tag and not scope_has_time_filter else ""
    where_sql = f"show_level = {int(show_level)} AND year = '{year_tag}'{month_sql}{scope}"
    if prefer_report_agg:
        if compare_requested:
            if "部门" in query:
                return (
                    f"SELECT {report_scope_sql}dept_level1, month, "
                    "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                    "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                    f"FROM compare_budget_summary WHERE {where_sql} "
                    "GROUP BY dept_level1, month "
                    "ORDER BY dept_level1, month "
                    "LIMIT 5000"
                )
            if "产品" in query:
                return (
                    f"SELECT {report_scope_sql}product_code_name, month, "
                    "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                    "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                    f"FROM compare_budget_summary WHERE {where_sql} "
                    "GROUP BY product_code_name, month "
                    "ORDER BY product_code_name, month "
                    "LIMIT 5000"
                )
            return (
                f"SELECT {report_scope_sql}month, "
                "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                f"FROM compare_budget_summary WHERE {where_sql} "
                "GROUP BY month "
                "ORDER BY month "
                "LIMIT 5000"
            )
        if "部门" in query:
            return (
                f"SELECT {report_scope_sql}dept_level1, month, SUM(value) AS total_value "
                f"FROM compare_budget_summary WHERE {where_sql} "
                "GROUP BY dept_level1, month "
                "ORDER BY dept_level1, month "
                "LIMIT 5000"
            )
        if "产品" in query:
            return (
                f"SELECT {report_scope_sql}product_code_name, month, SUM(value) AS total_value "
                f"FROM compare_budget_summary WHERE {where_sql} "
                "GROUP BY product_code_name, month "
                "ORDER BY product_code_name, month "
                "LIMIT 5000"
            )
        return (
            f"SELECT {report_scope_sql}month, SUM(value) AS total_value "
            f"FROM compare_budget_summary WHERE {where_sql} "
            "GROUP BY month "
            "ORDER BY month "
            "LIMIT 5000"
        )

    if compare_requested:
        if "部门" in query:
            return (
                "SELECT dept_level1, month, "
                "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                f"FROM compare_budget_summary WHERE {where_sql} "
                "GROUP BY dept_level1, month "
                "ORDER BY dept_level1, month "
                "LIMIT 5000"
            )
        if "科目" in query:
            return (
                "SELECT data_code_name, month, "
                "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                f"FROM compare_budget_summary WHERE {where_sql} "
                "GROUP BY data_code_name, month "
                "ORDER BY data_code_name, month "
                "LIMIT 5000"
            )
        return (
            "SELECT month, "
            "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
            "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
            f"FROM compare_budget_summary WHERE {where_sql} "
            "GROUP BY month "
            "ORDER BY month "
            "LIMIT 5000"
        )
    if "部门" in query:
        return (
            "SELECT dept_level1, month, SUM(value) AS total_value "
            f"FROM compare_budget_summary WHERE {where_sql} "
            "GROUP BY dept_level1, month "
            "ORDER BY dept_level1, month "
            "LIMIT 5000"
        )
    if "科目" in query:
        return (
            "SELECT data_code_name, month, SUM(value) AS total_value "
            f"FROM compare_budget_summary WHERE {where_sql} "
            "GROUP BY data_code_name, month "
            "ORDER BY data_code_name, month "
            "LIMIT 5000"
        )
    return (
        "SELECT data_code_name, product_code_name, month, SUM(value) AS total_value "
        f"FROM compare_budget_summary WHERE {where_sql} "
        "GROUP BY data_code_name, product_code_name, month "
        "ORDER BY data_code_name, month "
        "LIMIT 5000"
    )
