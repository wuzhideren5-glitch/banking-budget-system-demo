"""Memory append payload helpers for Agent budget turns."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _mapping_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_value(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def build_agent_final_requirement(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "slot_status": _mapping_value(state.get("slot_status")),
        "missing_slots": _list_value(state.get("missing_slots")),
        "clarified_slots": _mapping_value(state.get("clarified_slots")),
        "assumptions": _list_value(state.get("assumptions")),
    }


def build_agent_pivot_memory_config(
    state: Mapping[str, Any],
    *,
    budget_year: int,
) -> dict[str, Any]:
    query = str(state.get("user_query") or "")
    clarified_slots = _mapping_value(state.get("clarified_slots"))
    time_period = str(clarified_slots.get("time_period") or "").strip()
    return {
        "rows": ["dept_level1" if "部门" in query else "data_code_name"],
        "columns": ["month"],
        "pages": ["budget_actual", "version_name"],
        "filters": {
            "year": time_period or f"Y{int(budget_year)}",
        },
    }


def build_agent_memory_append_payload(
    state: Mapping[str, Any],
    *,
    budget_year: int,
) -> dict[str, Any]:
    executed_result = state.get("executed_result")
    return {
        "user_query": str(state.get("user_query") or ""),
        "intent_type": str(state.get("intent_type") or "budget"),
        "next_action": str(state.get("next_action") or ""),
        "suggested_sql": state.get("suggested_sql"),
        "analysis_summary": str(state.get("reply") or ""),
        "executed_result": executed_result if isinstance(executed_result, dict) else None,
        "final_requirement": build_agent_final_requirement(state),
        "pivot_config": build_agent_pivot_memory_config(state, budget_year=budget_year),
        "clarification_rounds": int(state.get("clarification_rounds") or 0),
    }
