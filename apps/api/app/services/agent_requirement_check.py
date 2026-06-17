"""Requirement-check read model for Agent budget analysis turns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.agent_compare_version import (
    extract_compare_show_level,
    extract_compare_target_year,
    filter_compare_options_by_target_year,
    format_compare_version_options,
    is_explicit_year_comparison,
    load_compare_version_options,
)
from app.services.agent_requirement_slots import (
    contextual_agent_slots_from_history,
    extract_agent_slot_status,
    extract_structured_agent_slots,
    slot_status_from_structured_agent_slots,
)


def build_agent_requirement_check(
    state: dict[str, Any],
    *,
    query: str,
    query_kind: str,
    history: list[dict[str, Any]],
    inherit_history_slots: bool,
    pm_query_spec: dict[str, Any],
    budget_year: int,
    compare_db: Path,
    common_db: Path,
) -> dict[str, Any]:
    """Resolve whether a budget-analysis turn needs clarification."""
    if query_kind == "metadata":
        return {
            "slot_status": {
                "time_period": True,
                "business_scope": True,
                "comparison_type": True,
                "granularity": True,
            },
            "clarified_slots": {},
            "missing_slots": [],
            "assumptions": [],
            "need_clarification": False,
            "clarification_rounds": 0,
        }

    override = state.get("pm_requirement_override")
    if isinstance(override, dict) and override:
        return {
            "slot_status": dict(override.get("slot_status") or {}),
            "clarified_slots": dict(override.get("clarified_slots") or {}),
            "missing_slots": list(override.get("missing_slots") or []),
            "assumptions": list(override.get("assumptions") or []),
            "need_clarification": bool(override.get("need_clarification", False)),
            "clarification_rounds": int(override.get("clarification_rounds", 0)),
        }

    query_slot_status = extract_agent_slot_status(query)
    history_slots = contextual_agent_slots_from_history(history) if inherit_history_slots else {}
    current_slots = extract_structured_agent_slots(query)
    clarified_slots = {**history_slots, **current_slots}

    if is_explicit_year_comparison(query) and int(current_slots.get("comparison_show_level") or 0) <= 0:
        clarified_slots.pop("comparison_show_level", None)

    compare_level = int(clarified_slots.get("comparison_show_level") or 0)
    if compare_level <= 0:
        pending_level = int(pm_query_spec.get("__selected_compare_level__") or 0)
        if 1 <= pending_level <= 5:
            clarified_slots["comparison_show_level"] = pending_level
        elif bool(pm_query_spec.get("__require_compare_level__", False)):
            level_from_query = extract_compare_show_level(query)
            if level_from_query is not None:
                clarified_slots["comparison_show_level"] = level_from_query

    yoy_requested = (
        "同比" in query
        or str(clarified_slots.get("comparison_type", "")).strip().lower() == "yoy"
        or int(pm_query_spec.get("__selected_compare_level__") or 0) in {1, 2, 3, 4, 5}
        or bool(pm_query_spec.get("__require_compare_level__", False))
    )
    compare_show_level = int(clarified_slots.get("comparison_show_level") or 0)
    compare_options = (
        load_compare_version_options(compare_db=compare_db, common_db=common_db)
        if yoy_requested
        else []
    )
    target_compare_year = extract_compare_target_year(query) if yoy_requested else None
    compare_options = filter_compare_options_by_target_year(compare_options, target_compare_year)
    compare_options_text = format_compare_version_options(compare_options)

    contextual_slot_status = slot_status_from_structured_agent_slots(clarified_slots)
    slot_status = {
        "time_period": bool(query_slot_status["time_period"] or contextual_slot_status["time_period"]),
        "business_scope": bool(query_slot_status["business_scope"] or contextual_slot_status["business_scope"]),
        "comparison_type": True,
        "comparison_version": (not yoy_requested) or (1 <= compare_show_level <= 5),
        "granularity": bool(query_slot_status["granularity"] or contextual_slot_status["granularity"]),
    }
    missing = [key for key, ok in slot_status.items() if not ok]

    assumptions: list[str] = []
    if "time_period" in missing:
        assumptions.append(f"默认按当前预算年度 Y{int(budget_year)} 分析")
    if "comparison_type" in missing:
        assumptions.append("默认不做比较分析，仅输出单口径结果")
    if "granularity" in missing:
        assumptions.append("默认按月汇总粒度展示")

    wants_execute = bool(state.get("wants_execute", False))
    need_clarification = len(missing) > 0 and (
        (not wants_execute) or ("comparison_version" in missing)
    )
    history_clarify_count = sum(
        1 for item in history if item.get("role") == "assistant" and "缺失要素" in str(item.get("content", ""))
    )
    clarification_rounds = max(int(state.get("clarification_rounds", 0)), history_clarify_count)
    if wants_execute and clarification_rounds == 0 and history:
        clarification_rounds = 1
    if need_clarification:
        clarification_rounds += 1

    return {
        "slot_status": slot_status,
        "clarified_slots": clarified_slots,
        "missing_slots": missing,
        "assumptions": assumptions,
        "need_clarification": need_clarification,
        "clarification_rounds": clarification_rounds,
        "comparison_version_options": compare_options_text,
    }
