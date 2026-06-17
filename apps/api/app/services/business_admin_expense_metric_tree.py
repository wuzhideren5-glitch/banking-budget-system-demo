"""Canonical metric tree under *.90 业务及管理费 (2026-06 restructure)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# Roots that carry 业务及管理费 under each product prefix.
BUSINESS_ADMIN_EXPENSE_ROOTS: tuple[str, ...] = (
    "A.90",
    "A01.90",
    "A02.90",
    "A03.90",
    "A04.90",
    "A05.90",
    "B.90",
    "B01.90",
    "B02.90",
    "C.90",
    "C01.90",
    "C02.90",
    "AA.90",
    "D.90",
    "D01.90",
    "E.90",
    "E01.90",
    "F.90",
    "F01.90",
)

# Shared category subtree under 直接费用(01) / 间接费用(02).
_EXPENSE_CATEGORY_SUFFIX_ROWS: tuple[tuple[str, str, str, int, str], ...] = (
    # ---- 人力（不含IT) ----
    ("01", "人力（不含IT)", "GROUP", 10, ""),
    ("01.001", "业务人力", "METRIC", 10, "01"),
    ("01.002", "特别人力", "METRIC", 20, "01"),
    # ---- 业务费用 ----
    ("02", "业务费用", "GROUP", 20, ""),
    ("02.01", "营销", "METRIC", 10, "02"),
    ("02.02", "运营", "METRIC", 20, "02"),
    # ---- IT (L4=xx GROUP, L5=00x METRIC) ----
    ("03", "IT", "GROUP", 30, ""),
    ("03.01", "IT人力", "GROUP", 10, "03"),
    ("03.01.001", "IT常规人力", "METRIC", 10, "03.01"),
    ("03.01.002", "IT特别人力", "METRIC", 20, "03.01"),
    ("03.02", "科技", "METRIC", 30, "03"),
    ("03.03", "IT职场", "METRIC", 40, "03"),
    ("03.04", "IT日常", "METRIC", 50, "03"),
    # ---- 职场 ----
    ("04", "职场", "METRIC", 40, ""),
    # ---- 日常 ----
    ("05", "日常", "METRIC", 50, ""),
)


def _expense_branch_rows(
    branch_code: str,
    branch_name: str,
    *,
    branch_sort: int,
) -> tuple[tuple[str, str, str, int, str], ...]:
    rows: list[tuple[str, str, str, int, str]] = [
        (branch_code, branch_name, "GROUP", branch_sort, ""),
    ]
    for rel_suffix, name, node_type, sort_order, parent_rel in _EXPENSE_CATEGORY_SUFFIX_ROWS:
        suffix = f"{branch_code}.{rel_suffix}"
        parent_suffix = branch_code if not parent_rel else f"{branch_code}.{parent_rel}"
        rows.append((suffix, name, node_type, sort_order, parent_suffix))
    return tuple(rows)


_BUSINESS_ADMIN_EXPENSE_SUFFIX_ROWS: tuple[tuple[str, str, str, int, str], ...] = (
    *_expense_branch_rows("01", "直接费用", branch_sort=10),
    *_expense_branch_rows("02", "间接费用", branch_sort=20),
)


@dataclass(frozen=True)
class MetricTreeNodeSpec:
    node_code: str
    node_name: str
    parent_code: str
    product_code: str
    local_metric_code: str
    level: int
    node_type: str
    sort_order: int


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _node_code_for_root(root: str, suffix: str) -> str:
    return f"{root}.{suffix}" if suffix else root


def _parent_code_for_root(root: str, parent_suffix: str) -> str:
    if not parent_suffix:
        return root
    return _node_code_for_root(root, parent_suffix)


def _product_code_from_root(root: str) -> str:
    return root.split(".", 1)[0]


def _scope_label(product_code: str) -> str:
    return f"scope=PRODUCT:{product_code}"


def build_business_admin_expense_nodes(root: str) -> list[MetricTreeNodeSpec]:
    if root not in BUSINESS_ADMIN_EXPENSE_ROOTS:
        raise ValueError(f"unsupported expense root: {root}")
    product_code = _product_code_from_root(root)
    nodes: list[MetricTreeNodeSpec] = [
        MetricTreeNodeSpec(
            node_code=root,
            node_name="业务及管理费",
            parent_code=product_code,
            product_code=product_code,
            local_metric_code="90",
            level=root.count(".") + 1,
            node_type="GROUP",
            sort_order=9000,
        )
    ]
    for suffix, name, node_type, sort_order, parent_suffix in _BUSINESS_ADMIN_EXPENSE_SUFFIX_ROWS:
        node_code = _node_code_for_root(root, suffix)
        parent_code = _parent_code_for_root(root, parent_suffix)
        local_metric_code = f"90.{suffix}" if suffix else "90"
        nodes.append(
            MetricTreeNodeSpec(
                node_code=node_code,
                node_name=name,
                parent_code=parent_code,
                product_code=product_code,
                local_metric_code=local_metric_code,
                level=node_code.count(".") + 1,
                node_type=node_type,
                sort_order=sort_order,
            )
        )
    return nodes


def all_business_admin_expense_nodes() -> list[MetricTreeNodeSpec]:
    rows: list[MetricTreeNodeSpec] = []
    for root in BUSINESS_ADMIN_EXPENSE_ROOTS:
        rows.extend(build_business_admin_expense_nodes(root))
    return rows


def business_admin_expense_metric_codes() -> set[str]:
    return {node.node_code for node in all_business_admin_expense_nodes()}


def business_admin_expense_leaf_codes() -> set[str]:
    return {node.node_code for node in all_business_admin_expense_nodes() if node.node_type == "METRIC"}


def is_under_business_admin_expense_root(code: str) -> bool:
    normalized = str(code or "").strip().upper()
    return any(
        normalized == root or normalized.startswith(f"{root}.")
        for root in BUSINESS_ADMIN_EXPENSE_ROOTS
    )


def is_legacy_expense_hr_or_non_hr_branch(code: str) -> bool:
    """True for *.90.02 / *.91 expense branches (not *.90.01.02 indirect subtree)."""
    normalized = str(code or "").strip().upper()
    if not normalized:
        return False
    parts = normalized.split(".")
    for idx, part in enumerate(parts):
        if part not in ("90", "91") or idx + 1 >= len(parts):
            continue
        if part == "91":
            return True
        if part == "90" and parts[idx + 1] == "02":
            return True
    return False


def metric_node_csv_row(node: MetricTreeNodeSpec, *, verified_at: str | None = None) -> str:
    verified = verified_at or _iso_now()
    description = (
        f"product={node.product_code}; local={node.local_metric_code}; "
        f"functional_group=; type={node.node_type}"
    )
    return (
        f"metric_node,{node.node_code},{node.node_name},data_account_metric_node,"
        f"{node.parent_code},{node.level},,{description},active,{verified}"
    )


def data_account_csv_row(node: MetricTreeNodeSpec, *, verified_at: str | None = None) -> str:
    verified = verified_at or _iso_now()
    scope = _scope_label(node.product_code)
    return (
        f"data_account,{node.node_code},{node.node_name},data_account,{node.node_code},,"
        f"金额,{scope},active,{verified}"
    )
