"""Detect runtime metric reference codes inside formula strings and display labels."""
from __future__ import annotations

import re

PRODUCT_CODE = r"[A-Z][A-Z0-9]*"
LOCAL_METRIC_NODE_CODE = (
    r"(?:"
    r"\d{2}\.\d{2}\.\d{2}\.\d{2}\.\d{3}|"
    r"\d{2}\.\d{2}\.\d{3}|"
    r"\d{2}\.\d{2}\.\d{2}\.\d{2}|"
    r"\d{2}\.\d{2}\.\d{2}|"
    r"\d{2}\.\d{2}|"
    r"\d{2}"
    r")"
)
PRODUCT_SCOPED_RUNTIME_METRIC_REF_CODE = rf"{PRODUCT_CODE}\.{LOCAL_METRIC_NODE_CODE}"
OFFICIAL_RUNTIME_METRIC_REF_CODE = PRODUCT_SCOPED_RUNTIME_METRIC_REF_CODE
RUNTIME_METRIC_REF_CODE_RE = re.compile(
    rf"(?<![A-Z0-9.]){OFFICIAL_RUNTIME_METRIC_REF_CODE}(?![A-Z0-9.])"
)
ANGLE_RUNTIME_METRIC_REF_CODE_RE = re.compile(rf"<\s*({OFFICIAL_RUNTIME_METRIC_REF_CODE})[^>]*>")


def extract_formula_codes(formula: str | None) -> set[str]:
    return {code.upper() for code in RUNTIME_METRIC_REF_CODE_RE.findall(formula or "")}


def extract_runtime_metric_ref_code(text: str | None) -> str | None:
    match = RUNTIME_METRIC_REF_CODE_RE.search((text or "").strip().upper())
    return match.group(0) if match else None


def formulas_reference_code(budget_formula: str | None, actual_formula: str | None, code: str) -> bool:
    blob = f"{budget_formula or ''} {actual_formula or ''}"
    target = (code or "").strip().upper()
    return bool(target) and target in extract_formula_codes(blob)
