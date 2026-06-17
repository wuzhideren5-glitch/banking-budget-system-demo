"""Leadership target parsing boundary for intelligent budget simulation."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Callable, Dict


DeepSeekJsonProvider = Callable[[str], Dict[str, Any]]


SYSTEM_PROMPT = """你是银行预算模拟目标解析助手。只输出 JSON，不输出解释。
目标：把领导的自然语言经营目标解析成硬约束和偏好。
JSON schema:
{
  "hard_targets": {
    "min_net_profit_growth": 0.10,
    "max_npl_ratio": 0.012
  },
  "soft_preferences": ["稳健经营", "规模不冒进"]
}
规则：
1. 百分比必须转成小数，例如 10% 输出 0.10。
2. 不良率、风险水平若表达为上限，写入 max_npl_ratio。
3. 净利润增长、利润增长若表达为下限，写入 min_net_profit_growth。
4. 如果信息含糊，用银行预算常用默认：净利润增长 0.10，不良率 0.012。
5. 不要做方案排序，不要输出经营建议。
"""


@dataclass(frozen=True)
class ParsedIntelligentBudgetTarget:
    original_text: str
    min_net_profit_growth: float
    max_npl_ratio: float
    hard_targets: dict[str, float]
    soft_preferences: list[str] = field(default_factory=list)
    adjustable_factors: list[str] = field(default_factory=lambda: ["规模", "收益率", "费用", "风险"])
    requires_confirmation: bool = True
    warnings: list[str] = field(default_factory=list)


def _percent_after_keyword(text: str, keywords: list[str], default: float) -> float:
    for keyword in keywords:
        idx = text.find(keyword)
        if idx < 0:
            continue
        window = text[idx : idx + 40]
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", window)
        if match:
            return float(match.group(1)) / 100
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    return float(match.group(1)) / 100 if match else default


def _deterministic_parse(text: str, warnings: list[str] | None = None) -> ParsedIntelligentBudgetTarget:
    min_net_profit_growth = _percent_after_keyword(text, ["净利润", "利润"], 0.10)
    max_npl_ratio = _percent_after_keyword(text, ["不良率", "风险"], 0.012)
    preferences: list[str] = []
    if any(token in text for token in ["稳健", "不要太冒进", "别太冒进", "不激进"]):
        preferences.append("稳健经营")
    if any(token in text for token in ["规模不要", "规模别", "规模不"]):
        preferences.append("规模不冒进")
    if any(token in text for token in ["风险不要", "风险不能", "风险不"]):
        preferences.append("风险不激进")
    return ParsedIntelligentBudgetTarget(
        original_text=text,
        min_net_profit_growth=min_net_profit_growth,
        max_npl_ratio=max_npl_ratio,
        hard_targets={
            "min_net_profit_growth": min_net_profit_growth,
            "max_npl_ratio": max_npl_ratio,
        },
        soft_preferences=preferences or ["目标满足", "经营可接受"],
        warnings=warnings or [],
    )


def _json_from_model_text(raw: str) -> dict[str, Any]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("DeepSeek response is not a JSON object")
    return value


def build_deepseek_target_provider(deepseek_client: Any | None) -> DeepSeekJsonProvider | None:
    if deepseek_client is None or not getattr(deepseek_client, "is_enabled")():
        return None

    def provider(text: str) -> Dict[str, Any]:
        raw = deepseek_client.chat_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=text,
            temperature=0.1,
            max_tokens=500,
            timeout_seconds=6.0,
            max_attempts=1,
        )
        if not raw:
            raise ValueError("DeepSeek returned empty response")
        return _json_from_model_text(raw)

    return provider


def parse_leadership_target(
    text: str,
    *,
    deepseek_json_provider: DeepSeekJsonProvider | None = None,
) -> ParsedIntelligentBudgetTarget:
    original_text = str(text or "").strip()
    if not original_text:
        return _deterministic_parse("净利润增长10%，不良率控制在1.2%", warnings=["目标为空，已使用默认演示目标，请人工确认。"])
    if deepseek_json_provider is None:
        return _deterministic_parse(original_text)
    try:
        payload = deepseek_json_provider(original_text)
        hard_targets = payload.get("hard_targets") if isinstance(payload, dict) else None
        if not isinstance(hard_targets, dict):
            raise ValueError("DeepSeek response missing hard_targets")
        min_profit = float(hard_targets["min_net_profit_growth"])
        max_npl = float(hard_targets["max_npl_ratio"])
        soft_preferences = payload.get("soft_preferences", [])
        return ParsedIntelligentBudgetTarget(
            original_text=original_text,
            min_net_profit_growth=min_profit,
            max_npl_ratio=max_npl,
            hard_targets={
                "min_net_profit_growth": min_profit,
                "max_npl_ratio": max_npl,
            },
            soft_preferences=[str(item) for item in soft_preferences] or ["目标满足", "经营可接受"],
        )
    except Exception:
        return _deterministic_parse(
            original_text,
            warnings=["DeepSeek解析失败，已使用规则解析结果，请人工确认。"],
        )
