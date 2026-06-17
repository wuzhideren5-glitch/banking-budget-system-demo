from __future__ import annotations

AMOUNT_UNIT_DIVISORS: dict[str, tuple[str, float]] = {
    "yuan": ("元", 1.0),
    "ten_thousand": ("万元", 10_000.0),
    "million": ("百万元", 1_000_000.0),
    "hundred_million": ("亿元", 100_000_000.0),
}

CHINESE_LABEL_TO_CODE: dict[str, str] = {
    label: code for code, (label, _divisor) in AMOUNT_UNIT_DIVISORS.items()
}


class ExpenseBudgetEntryAmountUnitError(ValueError):
    pass


def amount_unit_meta(amount_unit: str | None) -> tuple[str, float]:
    normalized = normalize_amount_unit_code(amount_unit)
    return AMOUNT_UNIT_DIVISORS[normalized]


def normalize_amount_unit_code(amount_unit: str | None) -> str:
    raw = str(amount_unit or "").strip()
    if not raw:
        raise ExpenseBudgetEntryAmountUnitError("导入预算时必须选择金额单位")
    lowered = raw.lower()
    if lowered in AMOUNT_UNIT_DIVISORS:
        return lowered
    if raw in CHINESE_LABEL_TO_CODE:
        return CHINESE_LABEL_TO_CODE[raw]
    raise ExpenseBudgetEntryAmountUnitError(f"不支持的金额单位：{raw}")


def resolve_budget_entry_amount_unit(*, form_value: str | None, query_value: str | None) -> str:
    return normalize_amount_unit_code(query_value or form_value)


def to_base_amount(amount: float, amount_unit: str) -> float:
    _label, factor = amount_unit_meta(amount_unit)
    return round(float(amount) * factor, 2)


def from_base_amount(amount: float, amount_unit: str) -> float:
    _label, divisor = amount_unit_meta(amount_unit)
    scaled = float(amount) / divisor
    if normalize_amount_unit_code(amount_unit) == "hundred_million":
        return round(scaled, 2)
    return round(scaled)


def amount_unit_options() -> list[dict[str, str]]:
    return [{"value": code, "label": label} for code, (label, _divisor) in AMOUNT_UNIT_DIVISORS.items()]
