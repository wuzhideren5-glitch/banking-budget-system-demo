"""Text-resolution helpers for Agent conversation turns."""

from __future__ import annotations

import re
from typing import Any, Callable


BudgetQueryDetector = Callable[[str], bool]


def strip_reply_markdown_stars(reply: str) -> str:
    """Remove Markdown star emphasis before returning replies to the UI."""
    text = (reply or "").strip()
    if not text:
        return ""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\*)\*(?!\*)(.*?)\*(?<!\*)", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"(?m)^\s*\*\s+", "- ", text)
    text = text.replace("*", "")
    return text.strip()


def is_execute_only_command(text: str) -> bool:
    query = (text or "").strip()
    if not query:
        return False
    if re.fullmatch(
        r"(确认|缺省|默认|听你的|听你安排|你看着办吧?|就这样吧?|按你说的|按你说的来|照你说的|照你说的来|按你意思|你决定吧?|你定吧?|你来定)",
        query,
    ):
        return True
    return bool(
        re.search(
            r"(按默认假设执行|直接执行|开始执行|确认执行|按你说的执行|按我选择执行|按我的选择执行|按我选择分析|执行查询|开始查询|直接查|重跑|重算|执行吧|听你的来|按你说的办|你看着办)",
            query,
        )
    )


def resolve_numeric_option_reply(query: str, history: list[dict[str, Any]]) -> str:
    """
    Map a numeric-only user reply to the latest numbered assistant option.

    This keeps a reply like "1" from losing the original option text and
    preserves the current metric-tree/data-account identity hint when present.
    """
    text = (query or "").strip()
    if not text:
        return text
    match = re.fullmatch(r"(?:选(?:项)?\s*)?([1-9]\d?)\s*[\.、\)]?", text)
    if not match:
        return text
    index = int(match.group(1))
    if index <= 0:
        return text
    last_assistant = ""
    for msg in reversed(history or []):
        if msg.get("role") == "assistant":
            last_assistant = str(msg.get("content") or "")
            if last_assistant.strip():
                break
    if not last_assistant:
        return text

    options: dict[int, str] = {}
    for line in last_assistant.splitlines():
        option_match = re.match(r"^\s*([1-9]\d?)\s*[\.\)、]\s*(.+?)\s*$", line.strip())
        if not option_match:
            continue
        option_no = int(option_match.group(1))
        option_text = option_match.group(2).strip()
        if option_no not in options and option_text:
            options[option_no] = option_text
    chosen = options.get(index)
    if not chosen:
        return text

    metric_codes = re.findall(
        r"(?:指标节点|指标)\s*([0-9]{2}(?:\.[0-9]{2,3})*)",
        last_assistant,
        flags=re.IGNORECASE,
    )
    data_code_groups = re.findall(
        r"机构及产品指标编码\s*([A-Z]\d{3,}(?:/[A-Z]\d{3,})*)",
        last_assistant,
        flags=re.IGNORECASE,
    )
    data_codes: list[str] = []
    for group in data_code_groups:
        parts = [part.strip().upper() for part in str(group).split("/") if part.strip()]
        for part in parts:
            if part not in data_codes:
                data_codes.append(part)

    hint_bits: list[str] = []
    if index == 1 and metric_codes:
        hint_bits.append(f"按指标节点 {metric_codes[0].upper()} 汇总口径")
    if index == 2 and data_codes:
        hint_bits.append(f"按机构及产品指标编码 {'/'.join(data_codes)} 细项口径")
    if index == 3 and "净利息" in last_assistant:
        hint_bits.append("按净利息收入汇总口径")

    hint_suffix = f"；{'；'.join(hint_bits)}" if hint_bits else ""
    return f"我选择第{index}项：{chosen}{hint_suffix}"


def last_budget_query_from_history(
    history: list[dict[str, Any]],
    *,
    budget_query_detector: BudgetQueryDetector,
) -> str:
    for msg in reversed(history or []):
        if msg.get("role") != "user":
            continue
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        if re.fullmatch(r"[1-9]\d*", content):
            continue
        if re.fullmatch(r"[Ll]\s*[1-5]", content):
            continue
        if re.search(r"^我选择第\d+项", content):
            continue
        if budget_query_detector(content):
            return content
    return ""


def effective_agent_query(
    state: dict[str, Any],
    *,
    budget_query_detector: BudgetQueryDetector,
) -> str:
    current_query = resolve_numeric_option_reply(
        str(state.get("user_query") or ""),
        list(state.get("history") or []),
    )
    pm_spec = state.get("pm_query_spec") if isinstance(state.get("pm_query_spec"), dict) else {}
    base_query = str(pm_spec.get("__base_user_query__") or "").strip()
    raw_query = str(state.get("user_query") or "").strip()
    if base_query and (
        re.fullmatch(r"[1-9]\d*", raw_query)
        or re.fullmatch(r"[Ll]\s*[1-5]", raw_query)
        or re.search(r"^我选择第\d+项[:：]", current_query)
    ):
        return base_query
    if is_execute_only_command(current_query):
        if base_query:
            return base_query
        previous = last_budget_query_from_history(
            list(state.get("history") or []),
            budget_query_detector=budget_query_detector,
        )
        if previous:
            return previous
    return current_query
