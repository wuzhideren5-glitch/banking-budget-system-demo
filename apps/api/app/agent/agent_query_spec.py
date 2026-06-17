"""Current Agent query-spec contract.

The Agent query spec is a small read-model contract over the current
org-product metric runtime references, department, product, and period axes.
Unknown fields are not part of the runtime contract and are not carried forward
between turns.
"""
from __future__ import annotations

from typing import Any


QUERY_SPEC_LIST_AXES = ("metric_nodes", "data_accounts", "departments", "products")
QUERY_SPEC_SCALAR_FIELDS = (
    "period_description",
    "year",
    "quarter",
    "month",
    "query_focus",
    "comparison_type",
    "metric_expand_mode",
    "__base_user_query__",
)
QUERY_SPEC_INTERNAL_FIELDS = (
    "__metric_binding_gap__",
    "__metric_binding_ambiguous__",
    "__require_compare_level__",
    "__selected_compare_level__",
)


def normalise_current_query_spec(query_spec: dict[str, Any] | None) -> dict[str, Any]:
    source = query_spec if isinstance(query_spec, dict) else {}
    out: dict[str, Any] = {}
    for key in QUERY_SPEC_SCALAR_FIELDS + QUERY_SPEC_INTERNAL_FIELDS:
        if key in source:
            out[key] = source[key]
    for key in QUERY_SPEC_LIST_AXES:
        value = source.get(key)
        out[key] = list(value) if isinstance(value, list) else []
    return out


def merge_current_query_specs(
    base: dict[str, Any] | None,
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(base, dict):
        merged.update(base)
    if isinstance(override, dict):
        merged.update(override)
    return normalise_current_query_spec(merged)
