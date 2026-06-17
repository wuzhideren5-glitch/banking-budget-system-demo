"""General-answer text helpers for Agent replies."""

from __future__ import annotations

import re


def shorten_general_reply(
    text: str,
    *,
    target_ratio: float = 0.5,
    min_chars: int = 90,
    max_chars: int = 260,
) -> str:
    raw = (text or "").strip()
    if not raw:
        return raw
    target_len = max(min_chars, min(int(len(raw) * target_ratio), max_chars))
    if len(raw) <= target_len:
        return raw

    chunks = re.split(r"(?<=[。！？!?])", raw)
    kept = ""
    for chunk in chunks:
        if not chunk.strip():
            continue
        if len(chunk) > target_len and not kept:
            kept = raw[:target_len].rstrip("，,；;、 ")
            break
        if len(kept) + len(chunk) > target_len and kept:
            break
        kept += chunk
        if len(kept) >= target_len:
            break
    kept = kept.strip()
    if not kept:
        kept = raw[:target_len].rstrip("，,；;、 ")
    if kept[-1] not in "。！？!?":
        kept += "。"
    return kept


def build_general_fallback_answer(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return (
            "当然可以，我先给你一个简明回答：\n\n"
            "你可以先告诉我你最关心的目标（例如控成本、稳收入、看执行差异），"
            "我会按“核心结论 + 关键依据 + 可执行建议”给出更完整的回复。"
        )

    if "预算" in q and re.search(r"(关注|要点|问题|原则|建议|怎么做|如何)", q):
        return (
            "这是一个很好的问题。银行在编制财务预算时，通常要重点关注以下几个方面：\n\n"
            "1) 业务与战略一致性：预算目标要与年度经营目标、监管要求和风险偏好保持一致，"
            "避免“数字好看但不可执行”。\n"
            "2) 收入预算的可实现性：要拆解到客群、产品、渠道和区域，明确驱动因子（规模、价格、结构），"
            "并做基准/乐观/审慎情景测算。\n"
            "3) 成本费用的刚性与弹性：区分刚性成本与可控费用，设置降本抓手和责任口径，防止“一刀切”影响经营能力。\n"
            "4) 资产负债与资金成本联动：关注规模扩张与资本占用、FTP、利率波动、久期错配等对利润的传导影响。\n"
            "5) 风险与拨备前瞻：将不良、迁徙率、拨备覆盖、风险成本纳入预算假设，避免利润预算偏离真实风险。\n"
            "6) 执行监控机制：明确月度/季度滚动复盘机制，设置偏差阈值与纠偏动作，形成“预算-执行-复盘-修正”闭环。\n\n"
            "如果你愿意，我可以下一步按你所在条线（个金/对公/普惠等）给出一版可直接落地的预算关注清单。"
        )

    if re.search(r"(天气|气温|下雨|晴天|阴天)", q):
        return (
            "如果你是想看实时天气，建议优先用手机天气应用或气象网站获取当地最新数据。"
            "在无法联网的情况下，我可以先给你一个实用判断框架：\n\n"
            "1) 出门活动：优先关注降水概率、体感温度和风力；\n"
            "2) 通勤场景：看小时级降雨与早晚温差，决定是否带雨具和外套；\n"
            "3) 健康防护：高温天注意补水防晒，低温天注意保暖和呼吸道防护。\n\n"
            "你告诉我所在城市和出行时段，我可以按“穿衣+出行+风险提醒”给你一版更具体的建议。"
        )

    if "银行" in q and re.search(r"(多少|几家|数量)", q):
        return (
            "这个问题需要先明确统计口径。中国银行业机构数量会随时间和口径变化，"
            "常见口径包括政策性银行、国有大行、股份制银行、城商行、农商行、村镇银行、民营银行及外资行等。"
            "如果口径不同，结果会差异很大。\n\n"
            "建议你先确认三个点：\n"
            "1) 统计时点（例如截至某年末）；\n"
            "2) 是否按“法人机构”还是“营业网点”统计；\n"
            "3) 是否包含外资和村镇银行。\n\n"
            "在没有联网检索的前提下，我可以先给你各类银行的分类框架；"
            "若你提供统计口径，我再给你更接近可用的参考答案。"
        )

    if re.search(r"(是什么|为什么|如何|怎么|区别|优缺点)", q):
        return (
            f"关于“{q}”，我先给你一个通俗版回答：\n\n"
            "- 先看定义：明确概念边界，避免口径混用；\n"
            "- 再看原理：弄清影响结果的关键变量；\n"
            "- 最后看应用：结合真实场景给出可执行做法。\n\n"
            "如果你告诉我你的应用场景（例如汇报、方案设计、实际执行），我可以再给你更贴合的一版。"
        )

    return (
        f"我先基于通用知识给你一个尽量实用的回答：\n\n"
        f"关于“{q}”，建议你优先明确三个点：目标、口径和时间范围。"
        "先把问题从“泛问题”变成“可执行问题”，答案质量会明显提升。\n\n"
        "如果你愿意，我可以继续帮你把这个问题拆成 3-5 个可落地的步骤。"
    )
