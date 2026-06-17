"""Compare-version clarification helpers for Agent product-intent routing."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from app.agent.agent_query_spec import merge_current_query_specs
from app.services.agent_compare_version import (
    extract_compare_show_level,
    extract_compare_target_year,
    filter_compare_options_by_target_year,
    format_compare_version_options,
    is_yoy_requested,
    load_compare_version_options,
)


def map_pm_missing_aspects(aspects: list[Any]) -> list[str]:
    out: list[str] = []
    for aspect in aspects or []:
        text = str(aspect).strip()
        if text == "time":
            out.append("time_period")
        elif text == "org_product":
            out.append("business_scope")
        elif text == "metric_scope":
            out.append("metric_scope")
        elif text in (
            "time_period",
            "business_scope",
            "comparison_type",
            "comparison_version",
            "granularity",
            "metric_scope",
        ):
            out.append(text)
    seen: set[str] = set()
    result: list[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _query_spec_from_pm(pm: Mapping[str, Any] | None) -> dict[str, Any]:
    query_spec = pm.get("query_spec") if isinstance(pm, Mapping) else None
    return query_spec if isinstance(query_spec, dict) else {}


def _base_user_query(query: str, pending_query_spec: Mapping[str, Any], next_pending: dict[str, Any]) -> str:
    pending_base = str(pending_query_spec.get("__base_user_query__") or "").strip()
    if pending_base:
        return pending_base
    current_base = str(next_pending.get("__base_user_query__") or "").strip()
    if current_base:
        return current_base
    return str(query or "")


def resolve_compare_version_clarification(
    query: str,
    *,
    route: str,
    pm: Mapping[str, Any] | None,
    pending_query_spec: Mapping[str, Any] | None,
    compare_db: Path,
    common_db: Path,
) -> dict[str, Any]:
    """
    Decide whether a PM data-query route needs compare L1-L5 selection.

    Returns:
    - {"action": "none"} when no compare clarification is relevant.
    - {"action": "clarify", ...} when caller should short-circuit and ask for a level.
    - {"action": "selected", "query_spec": ...} when a selected level should be written into PM query_spec.
    """
    if route not in {"data_query_ready", "data_query_incomplete"}:
        return {"action": "none"}

    pending = pending_query_spec if isinstance(pending_query_spec, Mapping) else {}
    require_compare_level = bool(pending.get("__require_compare_level__", False))
    yoy_requested = is_yoy_requested(query, {}) or require_compare_level
    selected_level = extract_compare_show_level(query)
    if not yoy_requested:
        return {"action": "none"}

    if not selected_level:
        rows = load_compare_version_options(compare_db=compare_db, common_db=common_db)
        rows = filter_compare_options_by_target_year(rows, extract_compare_target_year(query))
        options = format_compare_version_options(rows)
        numbered = "\n".join(f"{idx + 1}. {text}" for idx, text in enumerate(options)) if options else ""
        reply = (
            "你要求做同比分析，请先选择 compare 版本（L1-L5）。\n"
            "可直接回复编号或 Lx（例如：1 或 L1）。"
        )
        if numbered:
            reply = f"{reply}\n\n{numbered}"
        next_pending = merge_current_query_specs(dict(pending), _query_spec_from_pm(pm))
        next_pending["__require_compare_level__"] = True
        next_pending["__base_user_query__"] = _base_user_query(query, pending, next_pending)
        missing_slots = [
            item
            for item in map_pm_missing_aspects(list((pm or {}).get("missing_aspects") or []))
            if item != "comparison_type"
        ]
        if "comparison_version" not in missing_slots:
            missing_slots.insert(0, "comparison_version")
        return {
            "action": "clarify",
            "reply": reply,
            "missing_slots": missing_slots,
            "clarification_options": {"comparison_version": options},
            "pending_query_spec": next_pending,
        }

    next_pending = merge_current_query_specs(dict(pending), _query_spec_from_pm(pm))
    next_pending["__require_compare_level__"] = False
    next_pending["__selected_compare_level__"] = int(selected_level)
    next_pending["__base_user_query__"] = _base_user_query(query, pending, next_pending)
    return {"action": "selected", "query_spec": next_pending}
