from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        text = str(value).strip()
    elif isinstance(value, int):
        text = str(value).strip()
    elif isinstance(value, float):
        text = str(int(value)).strip() if value.is_integer() else str(value).strip()
    else:
        text = str(value).strip()
    text = text.replace("\ufeff", "").replace("\u3000", " ").strip()
    return unicodedata.normalize("NFKC", text)


def normalize_metric_code(entity_code: str, raw_code: Any) -> str:
    code = normalize_text(raw_code).upper().replace(" ", "")
    owner = normalize_text(entity_code).upper()
    if not code:
        return ""
    if owner and not code.startswith(owner) and re.fullmatch(r"\d+", code):
        return f"{owner}{code}"
    return code


def dotted_metric_code(entity_code: str, raw_code: Any) -> str:
    code = normalize_metric_code(entity_code, raw_code)
    if not code:
        return ""
    if "." in code:
        return code
    owner = normalize_text(entity_code).upper()
    if owner and code.startswith(owner):
        prefix = owner
        remainder = code[len(owner) :]
    elif code.startswith(("AA", "AB")):
        prefix = code[:2]
        remainder = code[2:]
    else:
        prefix = code[:3]
        remainder = code[3:]
    parts = [prefix] + [
        remainder[idx : idx + 2]
        for idx in range(0, len(remainder), 2)
        if remainder[idx : idx + 2]
    ]
    return ".".join(parts)
