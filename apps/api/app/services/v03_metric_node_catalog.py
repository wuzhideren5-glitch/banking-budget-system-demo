"""v03 org-product metric node catalog helpers (restore + workbook maintenance)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# When the same ``node_code`` appears on multiple metric tables in v03, the row
# on the higher-priority table owns the runtime ``metric_table_name`` / metadata.
METRIC_TABLE_CANONICAL_PRIORITY: dict[str, int] = {
    "资产负债表（余额）": 100,
    "资产负债表（日均）": 95,
    "利息净收入表": 90,
    "业务状况表": 85,
    "损益表": 80,
    "资产质量表": 75,
}

# Implicit GROUP nodes referenced by children but often omitted in v03 rows.
IMPLICIT_GROUP_PARENTS: dict[str, tuple[str | None, str]] = {
    "AA.24": ("AA.32.01", "资产负债表（余额）"),
    "AA.26": ("AA.33.01", "资产负债表（余额）"),
    "AA.25": ("AA.35.01", "资产负债表（日均）"),
    "AA.27": ("AA.36.01", "资产负债表（日均）"),
    "AA.14.02": ("AA.14", "利息净收入表"),
    "AA.16.02": ("AA.16", "利息净收入表"),
}

# Duplicate mirror rows in v03 that must not define runtime identity (canonical elsewhere).
V03_MIRROR_DUPLICATE_ROWS: tuple[tuple[str, str], ...] = (
    ("AA利息净收入表", "AA.25.05"),
    ("AA利息净收入表", "AA.27.05"),
)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def metric_table_priority(table_name: str) -> int:
    return METRIC_TABLE_CANONICAL_PRIORITY.get(_norm(table_name), 0)


def is_v03_stale_node_code(code: str) -> bool:
    """Return True when a v03 code must not be restored (legacy / rebuilt branches)."""
    normalized = _norm(code).upper()
    if not normalized or normalized == "科目代码":
        return True
    parts = normalized.split(".")
    if len(parts) < 2:
        return False
    second = parts[1]
    if second == "05" and not normalized.startswith("A01.14"):
        return True
    if second in {"99", "90", "91"}:
        return True
    return False


def is_v03_mirror_duplicate_row(sheet_name: str, node_code: str) -> bool:
    key = (_norm(sheet_name), _norm(node_code).upper())
    return key in V03_MIRROR_DUPLICATE_ROWS


def parent_code(node_code: str) -> str | None:
    normalized = _norm(node_code).upper()
    if "." not in normalized:
        return None
    return normalized.rsplit(".", 1)[0]


def code_depth(node_code: str) -> int:
    return _norm(node_code).count(".") + 1


def product_code(node_code: str) -> str:
    normalized = _norm(node_code).upper()
    if "." not in normalized:
        return normalized
    return normalized.split(".", 1)[0]


def local_metric_code(node_code: str) -> str:
    normalized = _norm(node_code).upper()
    if "." not in normalized:
        return ""
    return normalized.split(".", 1)[1]


def choose_canonical_table_name(existing: str, candidate: str) -> str:
    existing_norm = _norm(existing)
    candidate_norm = _norm(candidate)
    if not existing_norm:
        return candidate_norm
    if not candidate_norm:
        return existing_norm
    if metric_table_priority(candidate_norm) > metric_table_priority(existing_norm):
        return candidate_norm
    return existing_norm


def merge_v03_node_payload(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "table_name":
            merged[key] = choose_canonical_table_name(_norm(existing.get(key)), _norm(value))
            continue
        if value in (None, ""):
            continue
        if not merged.get(key):
            merged[key] = value
    return merged


@dataclass(frozen=True)
class ImplicitGroupSpec:
    node_code: str
    parent_code: str | None
    metric_table_name: str
    node_name: str
    level: int
    node_type: str = "GROUP"


def implicit_group_spec(node_code: str) -> ImplicitGroupSpec | None:
    normalized = _norm(node_code).upper()
    spec = IMPLICIT_GROUP_PARENTS.get(normalized)
    if not spec:
        return None
    parent, table_name = spec
    return ImplicitGroupSpec(
        node_code=normalized,
        parent_code=parent,
        metric_table_name=table_name,
        node_name=normalized,
        level=code_depth(normalized),
    )


def infer_implicit_groups_for_codes(node_codes: set[str]) -> list[ImplicitGroupSpec]:
    needed: dict[str, ImplicitGroupSpec] = {}
    for code in sorted(node_codes):
        parent = parent_code(code)
        while parent:
            if parent not in node_codes:
                spec = implicit_group_spec(parent)
                if spec:
                    needed[parent] = spec
            parent = parent_code(parent)
    return [needed[key] for key in sorted(needed, key=lambda item: (code_depth(item), item))]


def repair_implicit_group_nodes(conn: Any) -> int:
    """Fix implicit GROUP nodes (and their direct children) when v03 rows used wrong table."""
    updated = 0
    with conn.cursor() as cur:
        for group_code, (expected_parent, table_name) in IMPLICIT_GROUP_PARENTS.items():
            cur.execute(
                """
                UPDATE data_account_metric_node
                SET parent_code = %s,
                    metric_table_name = %s,
                    functional_group_code = %s,
                    node_type = 'GROUP',
                    updated_at = CURRENT_TIMESTAMP
                WHERE node_code = %s
                """,
                (expected_parent, table_name, table_name, group_code),
            )
            updated += int(cur.rowcount or 0)
            cur.execute(
                """
                UPDATE data_account_metric_node
                SET metric_table_name = %s,
                    functional_group_code = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE parent_code = %s
                """,
                (table_name, table_name, group_code),
            )
            updated += int(cur.rowcount or 0)
    conn.commit()
    return updated
