"""Time-anchor helpers for Agent budget queries."""

from __future__ import annotations

from datetime import date
import re
from typing import Any, Callable


MonthExtractor = Callable[[str], int | None]


def parse_requested_year(text: str) -> int | None:
    match = re.search(r"(20\d{2})", text or "")
    if not match:
        return None
    return int(match.group(1))


def last_completed_calendar_month(today: date | None = None) -> dict[str, Any]:
    """Return the previous natural calendar month."""
    current = today or date.today()
    if current.month == 1:
        year, month = current.year - 1, 12
    else:
        year, month = current.year, current.month - 1
    return {"calendar_year": year, "year_tag": f"Y{year}", "month_tag": f"M{month:02d}"}


def resolve_agent_analysis_time_anchor(
    state: dict[str, Any],
    *,
    effective_query: str,
    budget_year: int,
    extract_month_index: MonthExtractor,
    today: date | None = None,
) -> dict[str, Any]:
    """Resolve the year/month anchor used by Agent analysis queries."""
    query = effective_query or ""
    clarified = state.get("clarified_slots", {}) if isinstance(state.get("clarified_slots"), dict) else {}
    pm_spec = state.get("pm_query_spec") if isinstance(state.get("pm_query_spec"), dict) else {}

    y_raw = str(pm_spec.get("year") or "").strip()
    m_raw = str(pm_spec.get("month") or "").strip()
    year_match = re.match(r"Y(20\d{2})", y_raw, flags=re.I)
    if year_match and m_raw:
        month_match = re.match(r"M(\d{2})", m_raw, flags=re.I)
        if month_match and 1 <= int(month_match.group(1)) <= 12:
            year = int(year_match.group(1))
            month = int(month_match.group(1))
            return {"calendar_year": year, "year_tag": f"Y{year}", "month_tag": f"M{month:02d}"}

    if re.search(r"最近一个?月|近一个?月|近一月|上个?月(?!年|方|下)", query):
        return last_completed_calendar_month(today)

    span = re.search(r"([1-9]|1[0-2])\s*月?\s*[-~到至]\s*([1-9]|1[0-2])\s*月", query)
    if span:
        year = parse_requested_year(query) or int(budget_year)
        return {"calendar_year": year, "year_tag": f"Y{year}", "month_tag": None}

    month_index = extract_month_index(query)
    month_year = re.search(r"(20\d{2})年?\s*(\d{1,2})月", query) or re.search(
        r"(20\d{2}).*?(\d{1,2})月",
        query,
    )
    if month_year and month_index:
        year = int(month_year.group(1))
        if 1 <= month_index <= 12:
            return {"calendar_year": year, "year_tag": f"Y{year}", "month_tag": f"M{month_index:02d}"}

    if month_index is not None and 1 <= month_index <= 12:
        year = parse_requested_year(query) or int(budget_year)
        return {"calendar_year": year, "year_tag": f"Y{year}", "month_tag": f"M{month_index:02d}"}

    year = parse_requested_year(query) or parse_requested_year(str(clarified.get("time_period") or ""))
    if year:
        return {"calendar_year": year, "year_tag": f"Y{year}", "month_tag": None}

    return {"calendar_year": int(budget_year), "year_tag": f"Y{int(budget_year)}", "month_tag": None}
