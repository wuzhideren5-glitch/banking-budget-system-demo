"""Budget subject normalization helpers for expense budget execution reports."""
from __future__ import annotations

from app.services.expense_budget_execution_framework import text

BUDGET_DISPLAY_ALIASES: dict[str, str] = {
    "部门内部会议费": "部门会议费",
    "诉讼律师费": "律师及诉讼费",
    "办公资产摊销及折旧": "日常资产摊销及折旧",
    "资产摊销及折旧": "日常资产摊销及折旧",
    "全行工作会议": "全行性会议费",
    "商标域名资产摊销及折旧": "商标域名",
}


def normalize_budget_subject_name(subject_name: str) -> str:
    raw = text(subject_name)
    if not raw:
        return ""
    return BUDGET_DISPLAY_ALIASES.get(raw, raw)
