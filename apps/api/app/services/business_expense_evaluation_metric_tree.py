"""Canonical metric tree under *.91 业务支出评估 (2026-06 restructure).

Independent from *.90 业务及管理费.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

BUSINESS_EXPENSE_EVALUATION_ROOTS: tuple[str, ...] = (
    "A.91",
    "A01.91",
    "A02.91",
    "A03.91",
    "A04.91",
    "A05.91",
    "B.91",
    "B01.91",
    "B02.91",
    "C.91",
    "C01.91",
    "C02.91",
    "AA.91",
    "D.91",
    "D01.91",
    "E.91",
    "E01.91",
    "F.91",
    "F01.91",
)

# Shared subtree under each *.91 root.
# Tuple: suffix, name, node_type, sort_order, parent_suffix, value_type (METRIC only).
_EVALUATION_SUFFIX_ROWS: tuple[tuple[str, str, str, int, str, str | None], ...] = (
    ("01", "客户经营指标", "GROUP", 10, "", None),
    ("01.01", "客户营销与投入", "GROUP", 10, "01", None),
    ("01.01.001", "新客营销支出", "METRIC", 10, "01.01", "金额"),
    ("01.01.002", "存客营销支出", "METRIC", 20, "01.01", "金额"),
    ("01.01.003", "新开通客户投入", "METRIC", 30, "01.01", "金额"),
    ("01.01.004", "新发放投入", "METRIC", 40, "01.01", "金额"),
    ("01.02", "客户规模与数量", "GROUP", 20, "01", None),
    ("01.02.101", "LUM规模", "GROUP", 10, "01.02", None),
    ("01.02.102", "AuM规模", "GROUP", 20, "01.02", None),
    ("01.02.103", "客户数量", "GROUP", 30, "01.02", None),
    ("01.02.001", "新客日均LUM", "METRIC", 10, "01.02.101", "金额"),
    ("01.02.002", "存客日均LUM", "METRIC", 20, "01.02.101", "金额"),
    ("01.02.005", "新发放LUM", "METRIC", 30, "01.02.101", "金额"),
    ("01.02.006", "新发放LUM（标服）", "METRIC", 40, "01.02.101", "金额"),
    ("01.02.010", "日均LUM", "METRIC", 50, "01.02.101", "金额"),
    ("01.02.007", "存客日均AuM", "METRIC", 10, "01.02.102", "金额"),
    ("01.02.008", "新客AuM余额", "METRIC", 20, "01.02.102", "金额"),
    ("01.02.011", "日均AuM", "METRIC", 30, "01.02.102", "金额"),
    ("01.02.003", "新开通客户数", "METRIC", 10, "01.02.103", "数量"),
    ("01.02.004", "平均有效客户数", "METRIC", 20, "01.02.103", "数量"),
    ("01.02.009", "MFAU客户数", "METRIC", 30, "01.02.103", "数量"),
    ("01.03", "客户回收与催收", "GROUP", 30, "01", None),
    ("01.03.001", "内催回收额", "METRIC", 10, "01.03", "金额"),
    ("01.03.002", "M6-压降金额", "METRIC", 20, "01.03", "金额"),
    ("01.03.003", "M7+现金回收额", "METRIC", 30, "01.03", "金额"),
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
    value_type: str | None = None


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


def build_business_expense_evaluation_nodes(root: str) -> list[MetricTreeNodeSpec]:
    if root not in BUSINESS_EXPENSE_EVALUATION_ROOTS:
        raise ValueError(f"unsupported expense evaluation root: {root}")
    product_code = _product_code_from_root(root)
    nodes: list[MetricTreeNodeSpec] = [
        MetricTreeNodeSpec(
            node_code=root,
            node_name="业务支出评估",
            parent_code=product_code,
            product_code=product_code,
            local_metric_code="91",
            level=root.count(".") + 1,
            node_type="GROUP",
            sort_order=5020,
        )
    ]
    for suffix, name, node_type, sort_order, parent_suffix, value_type in _EVALUATION_SUFFIX_ROWS:
        node_code = _node_code_for_root(root, suffix)
        parent_code = _parent_code_for_root(root, parent_suffix)
        local_metric_code = f"91.{suffix}" if suffix else "91"
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
                value_type=value_type,
            )
        )
    return nodes


def all_business_expense_evaluation_nodes() -> list[MetricTreeNodeSpec]:
    rows: list[MetricTreeNodeSpec] = []
    for root in BUSINESS_EXPENSE_EVALUATION_ROOTS:
        rows.extend(build_business_expense_evaluation_nodes(root))
    return rows


def business_expense_evaluation_metric_codes() -> set[str]:
    return {node.node_code for node in all_business_expense_evaluation_nodes()}


def business_expense_evaluation_leaf_codes() -> set[str]:
    return {
        node.node_code
        for node in all_business_expense_evaluation_nodes()
        if node.node_type == "METRIC"
    }


def is_under_business_expense_evaluation_root(code: str) -> bool:
    normalized = str(code or "").strip().upper()
    return any(
        normalized == root or normalized.startswith(f"{root}.")
        for root in BUSINESS_EXPENSE_EVALUATION_ROOTS
    )


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
    value_type = node.value_type or "金额"
    return (
        f"data_account,{node.node_code},{node.node_name},data_account,{node.node_code},,"
        f"{value_type},{scope},active,{verified}"
    )


def metric_node_allows_manual_entry(node: MetricTreeNodeSpec) -> int:
    return 1 if node.node_type == "METRIC" else 0
