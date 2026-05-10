"""Detect references to a data account code inside formula strings."""
from __future__ import annotations

import re

_CODE_RE = re.compile(r"[A-Z]\d{4}")


def extract_formula_codes(formula: str | None) -> set[str]:
    return set(_CODE_RE.findall(formula or ""))


def formulas_reference_code(budget_formula: str | None, actual_formula: str | None, code: str) -> bool:
    blob = f"{budget_formula or ''} {actual_formula or ''}"
    return code in _CODE_RE.findall(blob)
