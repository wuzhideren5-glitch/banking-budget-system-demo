"""Shared metric helpers for expense budget execution read models."""
from __future__ import annotations

from typing import Any

from app.services.expense_budget_execution_framework import norm_key, text


def new_month_values() -> list[float]:
    return [0.0] * 12


def month_over_month_metrics(
    monthly_actuals: list[float],
    current_month: int,
) -> tuple[float | None, float | None]:
    normalized_current_month = max(1, min(int(current_month or 1), 12))
    if normalized_current_month <= 1:
        return None, None
    current_value = round(float(monthly_actuals[normalized_current_month - 1] or 0.0), 2)
    previous_value = round(float(monthly_actuals[normalized_current_month - 2] or 0.0), 2)
    month_over_month = round(current_value - previous_value, 2)
    month_over_month_rate = round(month_over_month / previous_value, 6) if previous_value else None
    return month_over_month, month_over_month_rate


def metric_payload(
    monthly_actuals: list[float],
    annual_budget: float,
    last_year_actual: float,
    current_month: int,
) -> dict[str, Any]:
    normalized_monthly_actuals = [round(float(value or 0.0), 2) for value in monthly_actuals]
    current_amount = round(sum(normalized_monthly_actuals), 2)
    budget_amount = round(float(annual_budget), 2)
    last_year_amount = round(float(last_year_actual), 2)
    yoy_change = round(current_amount - last_year_amount, 2)
    month_over_month, month_over_month_rate = month_over_month_metrics(
        normalized_monthly_actuals,
        current_month,
    )
    return {
        "monthly_actuals": normalized_monthly_actuals,
        "current_actual": current_amount,
        "annual_budget": budget_amount,
        "budget_progress": round(current_amount / budget_amount, 6) if budget_amount else None,
        "yoy_change": yoy_change,
        "yoy_rate": round(yoy_change / last_year_amount, 6) if last_year_amount else None,
        "month_over_month": month_over_month,
        "month_over_month_rate": month_over_month_rate,
        "last_year_actual": last_year_amount,
    }


def filter_tree_by_keyword(
    nodes: list[dict[str, Any]],
    keyword: str,
) -> list[dict[str, Any]]:
    keyword_text = norm_key(keyword)
    if not keyword_text:
        return nodes
    filtered: list[dict[str, Any]] = []
    for node in nodes:
        child_nodes = filter_tree_by_keyword(list(node.get("children", [])), keyword)
        searchable = " ".join(
            [
                text(node.get("subject_name")),
                text(node.get("level_label")),
                text(node.get("formula_text")),
            ]
        )
        if keyword_text in norm_key(searchable) or child_nodes:
            next_node = dict(node)
            next_node["children"] = child_nodes
            filtered.append(next_node)
    return filtered


def metric_tree_has_amount(node: dict[str, Any]) -> bool:
    numeric_fields = [
        float(node.get("current_actual") or 0.0),
        float(node.get("annual_budget") or 0.0),
        float(node.get("last_year_actual") or 0.0),
        float(node.get("yoy_change") or 0.0),
    ]
    if any(abs(value) > 0 for value in numeric_fields):
        return True
    monthly_actuals = [float(value or 0.0) for value in list(node.get("monthly_actuals", []))]
    previous_year_monthly_actuals = [
        float(value or 0.0) for value in list(node.get("previous_year_monthly_actuals", []))
    ]
    return any(abs(value) > 0 for value in monthly_actuals + previous_year_monthly_actuals)


def force_show_zero_metric_node(node: dict[str, Any]) -> bool:
    # Panpan 0519: "超额奖金" is a required fixed row under regular HR cost even before data arrives.
    return text(node.get("subject_name")) == "超额奖金"


def filter_zero_metric_tree(
    nodes: list[dict[str, Any]],
    *,
    include_zero_rows: bool,
) -> list[dict[str, Any]]:
    if include_zero_rows:
        return nodes
    filtered: list[dict[str, Any]] = []
    for node in nodes:
        child_nodes = filter_zero_metric_tree(
            list(node.get("children", [])),
            include_zero_rows=include_zero_rows,
        )
        if metric_tree_has_amount(node) or child_nodes or force_show_zero_metric_node(node):
            next_node = dict(node)
            next_node["children"] = child_nodes
            filtered.append(next_node)
    return filtered
