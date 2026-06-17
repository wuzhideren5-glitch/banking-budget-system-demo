"""Agent query-context resolution for budget analysis."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from app.services.agent_compare_version import (
    compare_level_meta,
    current_compare_show_level_version,
    is_yoy_requested,
)


def resolve_compare_query_context(
    state: Mapping[str, Any],
    *,
    anchor: Mapping[str, Any],
    compare_db: Path,
    common_db: Path,
) -> dict[str, Any]:
    """
    Resolve the Agent budget query read model.

    Current contract: Agent budget analysis reads the compare read model, with
    L1 as the base display level and L1-L5 as optional comparison levels.
    """
    clarified = state.get("clarified_slots", {}) or {}
    clarified = clarified if isinstance(clarified, dict) else {}
    pm_spec = state.get("pm_query_spec") if isinstance(state.get("pm_query_spec"), dict) else {}
    chosen_level = int(
        clarified.get("comparison_show_level")
        or pm_spec.get("__selected_compare_level__")
        or 0
    )
    show_level = chosen_level if 1 <= chosen_level <= 5 else 1
    yoy_requested = is_yoy_requested(str(state.get("user_query") or ""), clarified)
    base_level = 1
    compare_level = show_level if 1 <= show_level <= 5 else 1

    base_meta = compare_level_meta(
        compare_db=compare_db,
        common_db=common_db,
        show_level=base_level,
    )
    compare_meta = compare_level_meta(
        compare_db=compare_db,
        common_db=common_db,
        show_level=compare_level,
    )

    calendar_year = int(anchor["calendar_year"])
    base_year_tag = f"Y{int(base_meta.get('source_year') or calendar_year)}"
    compare_year_tag = f"Y{int(compare_meta.get('source_year') or (calendar_year - 1))}"
    base_version_id = int(
        base_meta.get("source_version_id")
        or current_compare_show_level_version(common_db=common_db, show_level=base_level)
        or 0
    )
    compare_version_id = int(
        compare_meta.get("source_version_id")
        or current_compare_show_level_version(common_db=common_db, show_level=compare_level)
        or 0
    )
    selected_version_id = compare_version_id if yoy_requested else base_version_id
    version_source = (
        f"compare.db|基准L{base_level}: {base_year_tag}/V{base_version_id}；"
        f"比较L{compare_level}: {compare_year_tag}/V{compare_version_id}"
    )
    if not compare_db.exists():
        version_source = "compare.db 缺失（当前要求仅使用 compare 库）"

    return {
        "query_db_path": str(compare_db),
        "query_db_year": calendar_year,
        "query_version_id": selected_version_id,
        "query_version_source": version_source,
        "query_data_source": "compare_l1",
        "query_show_level": compare_level if yoy_requested else base_level,
        "query_base_show_level": base_level,
        "query_compare_show_level": compare_level,
        "query_year_tag": base_year_tag,
        "query_base_year_tag": base_year_tag,
        "query_compare_year_tag": compare_year_tag,
        "query_base_version_id": base_version_id,
        "query_compare_version_id": compare_version_id,
        "query_month_tag": anchor.get("month_tag"),
    }
