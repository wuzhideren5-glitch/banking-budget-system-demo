from __future__ import annotations

from typing import Iterable


def expense_budget_adjusted_amount(amount: float | None, adjustment_amount: float | None) -> float:
    return round(float(amount or 0.0) + float(adjustment_amount or 0.0), 2)


def is_bank_wide_total_owner_label(owner_name_raw: str) -> bool:
    """Return True for imported bank-wide subtotal rows such as 「全行合计」."""
    raw = str(owner_name_raw or "").strip()
    if not raw:
        return False
    return "合计" in raw and ("全行" in raw or raw.endswith("合计"))


def resolve_expense_budget_subject_total(
    entries: Iterable[tuple[str, int, float]],
) -> float:
    """Resolve one budget subject amount from matched import rows.

    Priority:
    1. Bank-wide subtotal rows (e.g. 全行合计) when present for the subject.
    2. Matched department rows (owner_matched = 1).
    3. Remaining subject-matched rows as a fallback.
    """
    bank_wide_total = 0.0
    department_total = 0.0
    fallback_total = 0.0
    for owner_name_raw, owner_matched, adjusted_amount in entries:
        amount = round(float(adjusted_amount or 0.0), 2)
        if amount == 0.0:
            continue
        fallback_total += amount
        if int(owner_matched) == 1:
            department_total += amount
            continue
        if is_bank_wide_total_owner_label(owner_name_raw):
            bank_wide_total += amount
    if bank_wide_total:
        return round(bank_wide_total, 2)
    if department_total:
        return round(department_total, 2)
    return round(fallback_total, 2)
