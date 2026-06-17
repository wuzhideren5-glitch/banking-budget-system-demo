from __future__ import annotations

import re

from fastapi import HTTPException


PRODUCT_CODE_PATTERN = r"[A-Z][A-Z0-9]*"
PRODUCT_ROOT_NODE_PATTERN = PRODUCT_CODE_PATTERN
LOCAL_METRIC_NODE_PATTERN = r"\d{2}(?:\.\d{2})*(?:\.\d{3})?"
PRODUCT_SCOPED_METRIC_NODE_PATTERN = rf"{PRODUCT_CODE_PATTERN}\.{LOCAL_METRIC_NODE_PATTERN}"
METRIC_TREE_ANY_NODE_PATTERN = (
    rf"(?:{PRODUCT_ROOT_NODE_PATTERN}|{PRODUCT_SCOPED_METRIC_NODE_PATTERN})"
)
METRIC_TREE_ANY_NODE_RE = re.compile(rf"^{METRIC_TREE_ANY_NODE_PATTERN}$")
FORMAL_METRIC_NODE_RE = re.compile(rf"^{PRODUCT_SCOPED_METRIC_NODE_PATTERN}$")
METRIC_NODE_FORMAT_HINT = "产品前缀指标主键（如 A03.01.01.001 或 A.05.01.01.03.01.001）"


def clean_upper(value: str | None) -> str:
    return str(value or "").strip().upper()


def is_formal_metric_node_code(value: str | None) -> bool:
    return bool(FORMAL_METRIC_NODE_RE.fullmatch(str(value or "").strip().upper()))


def is_metric_tree_node_code(value: str | None) -> bool:
    return bool(METRIC_TREE_ANY_NODE_RE.fullmatch(str(value or "").strip().upper()))


def is_product_scoped_metric_node_code(value: str | None) -> bool:
    return bool(re.fullmatch(PRODUCT_SCOPED_METRIC_NODE_PATTERN, str(value or "").strip().upper()))


def is_product_root_metric_node_code(value: str | None) -> bool:
    code = str(value or "").strip().upper()
    return bool(code and re.fullmatch(PRODUCT_ROOT_NODE_PATTERN, code) and "." not in code)


def product_code_from_metric_node(metric_node_code: str | None) -> str | None:
    code = str(metric_node_code or "").strip().upper()
    if not is_product_scoped_metric_node_code(code):
        return None
    return code.split(".", 1)[0]


def local_metric_code_from_metric_node(metric_node_code: str | None) -> str | None:
    code = str(metric_node_code or "").strip().upper()
    if not is_product_scoped_metric_node_code(code):
        return None
    return code.split(".", 1)[1]


def product_code_from_metric_tree_node(node_code: str | None) -> str | None:
    code = str(node_code or "").strip().upper()
    if is_product_root_metric_node_code(code):
        return code
    return product_code_from_metric_node(code)


def local_metric_code_from_metric_tree_node(node_code: str | None) -> str | None:
    code = str(node_code or "").strip().upper()
    if is_product_root_metric_node_code(code):
        return None
    if is_product_scoped_metric_node_code(code):
        return code.split(".", 1)[1]
    return code or None


def product_code_from_runtime_metric_ref(runtime_ref_code: str | None) -> str | None:
    code = clean_upper(runtime_ref_code)
    if not code:
        return None
    return product_code_from_metric_node(code)


def official_runtime_metric_ref_code(metric_node_code: str, scope_code: str) -> str:
    metric_code = str(metric_node_code or "").strip().upper()
    scope = clean_upper(scope_code)
    if not is_formal_metric_node_code(metric_code):
        raise HTTPException(status_code=400, detail=f"正式指标编码必须为 {METRIC_NODE_FORMAT_HINT} 格式")
    metric_product = product_code_from_metric_node(metric_code)
    if scope and scope != metric_product:
        raise HTTPException(status_code=400, detail="产品编码与产品前缀指标主键不一致")
    return metric_code
