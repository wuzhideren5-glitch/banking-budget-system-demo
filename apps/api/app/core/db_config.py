"""数据库配置常量与年度发现。

替代旧的 db_paths.py，提供单 database 模式下的表列表和年度发现函数。
"""

from __future__ import annotations

# 单 database 名称
DATABASE_NAME: str = "banking_budget"

# 年度表（这些表包含 budget_year 列，用于区分不同预算年度）
YEARLY_TABLES: list[str] = [
    "version",
    "settings",
    "budget_data",
    "budget_summary",
    "budget_pivot_aggregate",
]

# 公共表（非年度表，直接合并到 banking_budget）
COMMON_TABLES: list[str] = [
    "users",
    "user_sessions",
    "operation_log",
    "data_account_metric_node",
    "data_account",
    "data_account_metric_binding",
    "org_product_tree_snapshot",
    "org_product_metric_table",
    "budget_output_display_item",
    "budget_output_display_config",
    "budget_subject_catalog",
    "manage_dept_owner_mapping",
    "bi_ai_subject_mapping",
    "dept_account",
    "expense_actual_detail_raw",
    "expense_forecast_entry",
    "expense_forecast_annual_entry",
]

# 对比分析表
COMPARE_TABLES: list[str] = [
    "compare_budget_summary",
    "compare_pivot_aggregate",
    "compare_sync_job_log",
    "compare_data_file",
]


async def list_budget_years(pool) -> list[int]:
    """从 budget_data 表获取所有活跃年度列表。

    Args:
        pool: DatabasePool 实例。

    Returns:
        去重且排序后的年度列表。如果表不存在或查询失败则返回空列表。
    """
    try:
        rows = await pool.fetch_all(
            "SELECT DISTINCT budget_year FROM budget_data ORDER BY budget_year"
        )
        return [r["budget_year"] for r in rows]
    except Exception:
        return []
