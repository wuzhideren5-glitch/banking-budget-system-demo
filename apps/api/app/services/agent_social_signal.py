"""Lightweight social signal helpers for Agent routing."""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


def normalize_lightweight_social_compact(compact: str) -> str:
    """
    Normalize short Chinese social probes before matching:
    1) align terminal question particles;
    2) drop terminal mood particles.
    """
    out = compact
    if len(out) <= 24:
        out = re.sub(r"[嘛么麽]$", "吗", out)
        out = re.sub(r"(呀|啊|哈|啦|呢)+$", "", out)
    return out


def detect_lightweight_social_signal(
    text: str,
    *,
    budget_query_detector: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    t = (text or "").strip().lower()
    if not t:
        return {"is_lightweight_social": False, "score": 0.0, "signals": [], "compact": "", "normalized": ""}
    compact = re.sub(r"[\s\.,，。!！?？~～:：;；、\-_]+", "", t)
    if not compact:
        return {"is_lightweight_social": False, "score": 0.0, "signals": [], "compact": "", "normalized": ""}
    normalized = normalize_lightweight_social_compact(compact)
    signals: list[str] = []
    score = 0.0

    if budget_query_detector is not None and budget_query_detector(t):
        signals.append("budget_like_query")
        return {
            "is_lightweight_social": False,
            "score": 0.0,
            "signals": signals,
            "compact": compact,
            "normalized": normalized,
        }

    if len(normalized) <= 12:
        score += 0.2
        signals.append("short_text")

    if normalized != compact:
        score += 0.15
        signals.append("normalized_particle")

    exact_patterns = [
        r"^(你好|您好|哈喽|嗨|hi|hello|hey|yo|早安|早上好|上午好|中午好|下午好|晚上好|晚安)$",
        r"^(在吗|在不在|有人吗|忙吗|你忙吗|有空吗|方便吗|在干嘛|干嘛呢)$",
        r"^(你是谁|你叫什么|你能干什么|你可以做什么)$",
    ]
    state_patterns = [
        r"^(开心吗|你开心吗|你会开心吗|你累吗|你累不累|吃了吗|吃饭了吗|最近还好吗|还好吗|(你)?饿(了)?吗|(你)?困(了)?吗)$",
        r"^(在吗|在不在|好吗|还好吗|忙吗|有空吗|方便吗)$",
    ]
    for pattern in exact_patterns:
        if re.fullmatch(pattern, normalized):
            score += 0.8
            signals.append("exact_greeting_pattern")
            break
    for pattern in state_patterns:
        if re.fullmatch(pattern, normalized):
            score += 0.8
            signals.append("state_question_pattern")
            break

    soft_tokens = ("你好", "您好", "哈喽", "嗨", "hi", "hello", "在吗", "吃了吗", "饿", "困", "忙吗", "有空吗")
    if any(token in normalized for token in soft_tokens):
        score += 0.25
        signals.append("social_token_hit")

    is_light = score >= 0.85 and len(normalized) <= 24
    return {
        "is_lightweight_social": is_light,
        "score": round(min(score, 1.0), 3),
        "signals": signals,
        "compact": compact,
        "normalized": normalized,
    }


def is_lightweight_social_question(
    text: str,
    *,
    budget_query_detector: Callable[[str], bool] | None = None,
) -> bool:
    return bool(
        detect_lightweight_social_signal(
            text,
            budget_query_detector=budget_query_detector,
        ).get("is_lightweight_social")
    )


def sanitize_lightweight_reply(reply: str, fallback: str) -> str:
    r = (reply or "").strip()
    if not r:
        return fallback
    templated = re.search(
        r"(关键要点|可执行建议|\*\*结论\*\*|\*\*关键要点\*\*|\*\*可执行建议\*\*|结论\s*[：:]|^\s*1[\.\)、]|^\s*-\s)",
        r,
        flags=re.MULTILINE,
    )
    if len(r) <= 90 and not templated:
        return r
    if templated:
        return fallback
    return r[:90].rstrip("，,；;、 ") + "。"
