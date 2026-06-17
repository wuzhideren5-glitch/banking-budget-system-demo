"""Requirement-slot helpers for Agent budget analysis turns."""

from __future__ import annotations

from datetime import date
import re
from typing import Any

from app.services.agent_compare_version import (
    extract_compare_show_level,
    is_explicit_year_comparison,
)
from app.services.agent_time_context import last_completed_calendar_month


def extract_agent_slot_status(query: str) -> dict[str, bool]:
    text = (query or "").lower()
    has_time = bool(
        re.search(
            r"(20\d{2}|y20\d{2}|q[1-4]|m\d{2}|本月|本季度|本年|去年|今年|一季度|二季度|三季度|四季度|"
            r"最近一个?月|近一个?月|近一月|上个?月(?!年))",
            text,
        )
    )
    has_entity = bool(re.search(r"(科目|部门|产品|贷款|存款|资产|负债|利润|收入|支出)", text))
    has_comparison = bool(re.search(r"(同比|环比|对比|较|vs|预算.?实际|差异)", text))
    has_granularity = bool(re.search(r"(明细|汇总|按月|按季|按年|钻取|层级)", text))
    return {
        "time_period": has_time,
        "business_scope": has_entity,
        "comparison_type": has_comparison,
        "granularity": has_granularity,
    }


def slot_status_from_structured_agent_slots(slots: dict[str, Any]) -> dict[str, bool]:
    return {
        "time_period": bool(slots.get("time_period") or slots.get("time_granularity_hint")),
        "business_scope": bool(slots.get("business_scope")),
        "comparison_type": True,
        "granularity": bool(slots.get("granularity") or slots.get("time_granularity_hint")),
    }


def extract_structured_agent_slots(query: str, *, today: date | None = None) -> dict[str, Any]:
    text = query or ""
    slots: dict[str, Any] = {}

    year_match = re.search(r"(20\d{2})", text)
    if year_match:
        slots["time_period"] = f"Y{year_match.group(1)}"
    elif re.search(r"(最近一个?月|近一个?月|近一月|上个?月(?!年|方|下))", text):
        last_month = last_completed_calendar_month(today)
        slots["time_period"] = f"{last_month['year_tag']} {last_month['month_tag']}"
    elif re.search(r"(本年|今年)", text):
        slots["time_period"] = "current_year"

    if re.search(r"(一季度|q1|Q1)", text):
        slots["time_granularity_hint"] = "Q1"
    elif re.search(r"(二季度|q2|Q2)", text):
        slots["time_granularity_hint"] = "Q2"
    elif re.search(r"(三季度|q3|Q3)", text):
        slots["time_granularity_hint"] = "Q3"
    elif re.search(r"(四季度|q4|Q4)", text):
        slots["time_granularity_hint"] = "Q4"

    for department in ["个人金融部", "企业金融部", "普惠金融部", "科技事业部", "司库部门", "境外金融部"]:
        if department in text:
            slots["business_scope"] = department
            break
    if "department" not in slots and "business_scope" not in slots and "部门" in text:
        slots["business_scope"] = "部门维度"

    if re.search(r"(预算.?实际|预实|差异)", text):
        slots["comparison_type"] = "budget_vs_actual"
    elif ("同比" in text) or is_explicit_year_comparison(text):
        slots["comparison_type"] = "yoy"
    elif "环比" in text:
        slots["comparison_type"] = "mom"

    compare_show_level = extract_compare_show_level(text)
    if compare_show_level is not None:
        slots["comparison_show_level"] = compare_show_level

    if re.search(r"(按月|月度)", text):
        slots["granularity"] = "month"
    elif re.search(r"(按季|季度)", text):
        slots["granularity"] = "quarter"
    elif re.search(r"(按年|年度)", text):
        slots["granularity"] = "year"
    elif "明细" in text:
        slots["granularity"] = "detail"
    elif "汇总" in text:
        slots["granularity"] = "summary"

    return slots


def contextual_agent_slots_from_history(
    history: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    recent_user_messages = [str(item.get("content") or "") for item in history if item.get("role") == "user"][-8:]
    for text in recent_user_messages:
        merged.update(extract_structured_agent_slots(text, today=today))
    return merged
