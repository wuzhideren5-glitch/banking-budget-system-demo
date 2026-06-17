"""Execution-result response helpers for Agent budget queries."""

from __future__ import annotations

import re
from typing import Any


def should_allow_repeat_analysis(query: str) -> bool:
    return bool(re.search(r"(重新总结|再次分析|完整分析|复述|再说一遍)", query or ""))


def recent_assistant_context_for_execution(
    history: list[dict[str, Any]],
    *,
    allow_repeat: bool,
    max_history_messages: int = 8,
    max_assistant_messages: int = 3,
) -> list[str]:
    if not allow_repeat:
        return []
    return [
        str(item.get("content") or "").strip()
        for item in history[-max_history_messages:]
        if item.get("role") == "assistant" and str(item.get("content") or "").strip()
    ][-max_assistant_messages:]


def build_execution_fallback_reply(result: dict[str, Any]) -> str:
    row_count = int(result.get("row_count", 0) or 0)
    display_preview = list(result.get("display_preview_rows", []) or [])
    quality_note = str(result.get("data_quality_note", "") or "")
    return (
        f"已执行只读查询，返回 {row_count} 行结果。"
        "\n\n我先给出摘要："
        f"\n- 返回结果条数：{row_count}"
        f"\n- 数据说明：{quality_note}"
        f"\n- 样例前{min(3, len(display_preview))}行：{display_preview[:3]}"
    )


def build_execution_rewrite_payload(
    *,
    query: str,
    result: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    display_preview = list(result.get("display_preview_rows", []) or [])
    allow_repeat = should_allow_repeat_analysis(query)
    return {
        "user_query": query,
        "row_count": int(result.get("row_count", 0) or 0),
        "显示字段": list(result.get("display_columns", []) or []),
        "样例数据": display_preview[:8],
        "数据说明": str(result.get("data_quality_note", "") or ""),
        "recent_assistant_context": recent_assistant_context_for_execution(
            history,
            allow_repeat=allow_repeat,
        ),
        "allow_repeat_analysis": allow_repeat,
        "instruction": (
            "若用户本轮是调整展示格式/排版请求，请重点说明新版展示结构和关键结果，"
            "不要重复上一轮已讲过的完整分析结论。"
            "严格以当前 user_query 与本次 SQL 返回样例为边界，不要引用上一轮业务对象、科目或标题。"
            "在正文中引用结果数值时，金额统一使用千分位并保留2位小数；"
            "百分比统一保留2位小数并带 %。"
        ),
    }


def normalize_agent_analysis_reply_units(reply: str) -> str:
    return re.sub(r"万元", "亿元", str(reply or ""))
