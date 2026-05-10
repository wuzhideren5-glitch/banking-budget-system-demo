from __future__ import annotations

import re


def parse_month_index(month_label: str) -> int:
    m = (month_label or "").strip()
    if not m:
        return 0
    digits = re.findall(r"\d+", m)
    if not digits:
        return 0
    return int(digits[0])
