from __future__ import annotations


def budget_actual_allowed_for_month(budget_actual: int, month: int, current_month: int) -> bool:
    """当前月份窗口 X 下，日历月 month 是否允许该 budget_actual（0=预算 1=实际）。"""
    if not (1 <= month <= 12):
        return False
    x = max(1, min(13, current_month))
    if x == 13:
        return budget_actual == 1
    if x == 1:
        return budget_actual == 0
    if month < x:
        return budget_actual == 1
    return budget_actual == 0
