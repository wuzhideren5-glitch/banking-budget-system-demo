"""SQL builders for Agent budget_summary read-model queries."""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.services.agent_analysis_filters import (
    analysis_fact_filters,
    pm_metric_locked_without_data,
    pm_metric_scope_label,
    sql_escape_literal,
)


def _wants_list(query: str) -> bool:
    return bool(re.search(r"(列出来|清单|列表|明细|名称|有哪些|全部)", query))


def _metadata_source(
    *,
    data_source: str,
    version_id: int,
    year_tag: str,
    month_tag: str | None,
    show_level: int,
) -> tuple[str, str]:
    if data_source == "compare_l1":
        month_sql = f" AND month = '{month_tag}'" if month_tag else ""
        return (
            "compare_budget_summary",
            f"show_level = {int(show_level)} AND year = '{year_tag}'{month_sql}",
        )
    return "budget_summary", f"version_id = {int(version_id)}"


def _metadata_distinct_sql(
    *,
    table_name: str,
    where_sql: str,
    select_sql: str,
    present_sql: str,
    order_sql: str,
) -> str:
    return (
        f"SELECT DISTINCT {select_sql} "
        f"FROM {table_name} "
        f"WHERE {where_sql} AND {present_sql} "
        f"ORDER BY {order_sql} "
        "LIMIT 5000"
    )


def _metadata_count_sql(
    *,
    table_name: str,
    where_sql: str,
    count_expr: str,
    alias: str,
    present_sql: str,
) -> str:
    return (
        f"SELECT COUNT(DISTINCT {count_expr}) AS {alias} "
        f"FROM {table_name} "
        f"WHERE {where_sql} AND {present_sql} "
        "LIMIT 1"
    )


def suggest_metadata_sql(
    query: str,
    *,
    data_source: str,
    version_id: int,
    year_tag: str,
    month_tag: str | None,
    show_level: int,
) -> str:
    table_name, where_sql = _metadata_source(
        data_source=data_source,
        version_id=version_id,
        year_tag=year_tag,
        month_tag=month_tag,
        show_level=show_level,
    )
    wants_list = _wants_list(query)
    if "部门" in query:
        if wants_list:
            return _metadata_distinct_sql(
                table_name=table_name,
                where_sql=where_sql,
                select_sql="COALESCE(dept_level3, dept_level2, dept_level1) AS dept_name",
                present_sql="COALESCE(dept_level3, dept_level2, dept_level1) IS NOT NULL",
                order_sql="dept_name",
            )
        return _metadata_count_sql(
            table_name=table_name,
            where_sql=where_sql,
            count_expr="COALESCE(dept_level3, dept_level2, dept_level1)",
            alias="dept_count",
            present_sql="COALESCE(dept_level3, dept_level2, dept_level1) IS NOT NULL",
        )
    if "产品" in query:
        if wants_list:
            return _metadata_distinct_sql(
                table_name=table_name,
                where_sql=where_sql,
                select_sql="product_code_name",
                present_sql="product_code_name IS NOT NULL AND TRIM(product_code_name) != ''",
                order_sql="product_code_name",
            )
        return _metadata_count_sql(
            table_name=table_name,
            where_sql=where_sql,
            count_expr="product_code_name",
            alias="product_count",
            present_sql="product_code_name IS NOT NULL AND TRIM(product_code_name) != ''",
        )
    if "科目" in query:
        if wants_list:
            return _metadata_distinct_sql(
                table_name=table_name,
                where_sql=where_sql,
                select_sql="data_code_name",
                present_sql="data_code_name IS NOT NULL AND TRIM(data_code_name) != ''",
                order_sql="data_code_name",
            )
        return _metadata_count_sql(
            table_name=table_name,
            where_sql=where_sql,
            count_expr="data_code_name",
            alias="acct_count",
            present_sql="data_code_name IS NOT NULL AND TRIM(data_code_name) != ''",
        )
    return (
        "SELECT COUNT(*) AS total_rows "
        f"FROM {table_name} "
        f"WHERE {where_sql} "
        "LIMIT 1"
    )


def suggest_budget_summary_sql(
    query: str,
    *,
    version_id: int,
    year_tag: str,
    month_tag: str | None,
    state: Mapping[str, Any] | None = None,
) -> str:
    month_sql = f" AND month = '{month_tag}'" if month_tag else ""
    version_filter = f"version_id = {int(version_id)}"
    pm = state.get("pm_query_spec") if state is not None and isinstance(state.get("pm_query_spec"), dict) else None
    prefer_report_agg = pm_metric_locked_without_data(pm)
    report_scope_label = pm_metric_scope_label(pm)
    report_scope_sql = (
        f"'{sql_escape_literal(report_scope_label)}' AS report_scope, "
        if report_scope_label
        else ""
    )
    fact_extra = analysis_fact_filters(state, query)
    where_sql = f"{version_filter}{fact_extra} AND year = '{year_tag}'{month_sql}"

    if prefer_report_agg:
        if re.search(r"(预算.*实际.*两列|口径.*两列|分两列|并列展示|列展示)", query):
            if "部门" in query:
                return (
                    f"SELECT {report_scope_sql}dept_level1, month, "
                    "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                    "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                    "FROM budget_summary "
                    f"WHERE {where_sql} "
                    "GROUP BY dept_level1, month "
                    "ORDER BY dept_level1, month "
                    "LIMIT 5000"
                )
            if "产品" in query:
                return (
                    f"SELECT {report_scope_sql}product_code_name, month, "
                    "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                    "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                    "FROM budget_summary "
                    f"WHERE {where_sql} "
                    "GROUP BY product_code_name, month "
                    "ORDER BY product_code_name, month "
                    "LIMIT 5000"
                )
            return (
                f"SELECT {report_scope_sql}month, "
                "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                "FROM budget_summary "
                f"WHERE {where_sql} "
                "GROUP BY month "
                "ORDER BY month "
                "LIMIT 5000"
            )
        if "部门" in query:
            return (
                f"SELECT {report_scope_sql}dept_level1, month, budget_actual, SUM(value) AS total_value "
                "FROM budget_summary "
                f"WHERE {where_sql} "
                "GROUP BY dept_level1, month, budget_actual "
                "ORDER BY dept_level1, month "
                "LIMIT 5000"
            )
        if "产品" in query:
            return (
                f"SELECT {report_scope_sql}product_code_name, month, budget_actual, SUM(value) AS total_value "
                "FROM budget_summary "
                f"WHERE {where_sql} "
                "GROUP BY product_code_name, month, budget_actual "
                "ORDER BY product_code_name, month "
                "LIMIT 5000"
            )
        return (
            f"SELECT {report_scope_sql}month, budget_actual, SUM(value) AS total_value "
            "FROM budget_summary "
            f"WHERE {where_sql} "
            "GROUP BY month, budget_actual "
            "ORDER BY month "
            "LIMIT 5000"
        )

    if re.search(r"(预算.*实际.*两列|口径.*两列|分两列|并列展示|列展示)", query):
        if "部门" in query:
            return (
                "SELECT dept_level1, month, "
                "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                "FROM budget_summary "
                f"WHERE {where_sql} "
                "GROUP BY dept_level1, month "
                "ORDER BY dept_level1, month "
                "LIMIT 5000"
            )
        if "科目" in query:
            return (
                "SELECT data_code_name, month, "
                "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                "FROM budget_summary "
                f"WHERE {where_sql} "
                "GROUP BY data_code_name, month "
                "ORDER BY data_code_name, month "
                "LIMIT 5000"
            )
        return (
            "SELECT month, "
            "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
            "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
            "FROM budget_summary "
            f"WHERE {where_sql} "
            "GROUP BY month "
            "ORDER BY month "
            "LIMIT 5000"
        )
    if "部门" in query:
        return (
            "SELECT dept_level1, month, budget_actual, SUM(value) AS total_value "
            "FROM budget_summary "
            f"WHERE {where_sql} "
            "GROUP BY dept_level1, month, budget_actual "
            "ORDER BY dept_level1, month "
            "LIMIT 5000"
        )
    if "科目" in query:
        return (
            "SELECT data_code_name, month, budget_actual, SUM(value) AS total_value "
            "FROM budget_summary "
            f"WHERE {where_sql} "
            "GROUP BY data_code_name, month, budget_actual "
            "ORDER BY data_code_name, month "
            "LIMIT 5000"
        )
    return (
        "SELECT month, budget_actual, SUM(value) AS total_value "
        "FROM budget_summary "
        f"WHERE {where_sql} "
        "GROUP BY month, budget_actual "
        "ORDER BY month "
        "LIMIT 5000"
    )
