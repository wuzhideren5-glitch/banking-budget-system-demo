"""Text signal helpers for Agent intent routing."""

from __future__ import annotations

import re
from typing import Any


def looks_like_budget_query(text: str) -> bool:
    budget_keywords = [
        "预算",
        "实际",
        "预实",
        "收入",
        "利息",
        "费用",
        "利润",
        "nim",
        "roe",
        "科目",
        "部门",
        "产品",
        "支行",
        "信贷",
        "贷款",
        "存款",
        "资产",
        "负债",
        "授信",
        "经营请款",
        "资产负债",
        "净息差",
        "净利差",
        "不良",
        "拨备",
        "风险成本",
        "ftp",
        "月度",
        "季度",
        "年度",
        "同比",
        "环比",
        "趋势",
        "预算执行",
        "差异",
        "透视",
        "财务",
        "报表",
        "明细",
        "汇总",
        "分析",
        "图表",
        "测算",
        "预测",
        "模拟",
        "目标求解",
        "滚动预算",
        "版本",
        "导出",
        "查询",
        "展示",
        "对比",
        "version",
        "budget",
        "actual",
    ]
    t = text.lower()
    return any(k.lower() in t for k in budget_keywords)


def is_simple_greeting_query(query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return False
    if looks_like_budget_query(q):
        return False
    qc = re.sub(r"[\s\.,，。!！?？~～:：;；、\-_]+", "", q)
    if not qc:
        return False
    greeting_patterns = [
        r"^(你好|您好|哈喽|嗨|hi|hello|hey|yo|早安|早上好|上午好|中午好|下午好|晚上好|晚安)$",
        r"^(在吗|在不在|有人吗|忙吗|你忙吗|忙不忙|方便吗|有空吗|有空聊吗|在干嘛|干嘛呢)$",
        r"^(能咨询问题吗|可以咨询问题吗|可以问问题吗|能问问题吗|能聊聊吗|你是谁|你能干什么|你可以做什么)$",
        r"^(吃了吗|吃饭了吗|吃过了吗|饭吃了吗|辛苦了|辛苦啦|累不累|累了吗|今天怎么样|最近怎么样|最近还好吗|还好吗)$",
        r"^(你好呀|你好啊|您好呀|您好啊|哈喽呀|嗨呀|hi呀|hello呀|hey呀)$",
    ]
    return any(re.fullmatch(p, qc) is not None for p in greeting_patterns)


def is_greeting_then_budget_query(query: str) -> bool:
    q = (query or "").strip()
    if not q:
        return False
    if not looks_like_budget_query(q):
        return False
    parts = [p.strip() for p in re.split(r"[，,。！？!?；;:：\n]+", q) if p.strip()]
    if len(parts) < 2:
        return False
    lead = parts[0]
    if not is_simple_greeting_query(lead):
        return False
    tail = " ".join(parts[1:]).strip()
    return bool(tail and looks_like_budget_query(tail))


def is_general_chitchat(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    general_keywords = [
        "天气",
        "你好",
        "hello",
        "hi",
        "吃饭",
        "笑话",
        "翻译",
        "写代码",
        "python",
        "旅游",
        "新闻",
        "电影",
        "音乐",
        "你是谁",
        "几点",
        "日期",
    ]
    return any(k in t for k in general_keywords)


def is_followup_constraint_like(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(
        re.search(
            r"(20\d{2}|一季度|二季度|三季度|四季度|按月|按季|按年|同比|环比|预算与实际差异|个人金融部|企业金融部|普惠金融部|按全部部门|按当前口径|按刚才口径|按上述口径)",
            t,
        )
    )


def is_brief_acknowledgement(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(
        re.fullmatch(
            r"(好|好的|好呀|行|可以|继续|收到|明白|确认|按这个来|就这样)(吧|呢|哈)?[。！!，,\s]*",
            t,
        )
    )


def has_pending_budget_plan(history: list[dict[str, Any]]) -> bool:
    if not history:
        return False
    recent_assistant = [
        str(m.get("content") or "")
        for m in history[-8:]
        if m.get("role") == "assistant"
    ]
    if not recent_assistant:
        return False
    latest = recent_assistant[-1]
    has_execution_done = bool(re.search(r"(已执行只读查询|返回\s*\d+\s*行)", latest))
    if has_execution_done:
        return False
    planning_signals = [
        "分析口径规划如下",
        "后续步骤",
        "下一步可直接执行",
        "按当前口径重跑",
        "按默认假设执行",
        "缺失要素",
        "请回复",
    ]
    return any(any(sig in msg for sig in planning_signals) for msg in recent_assistant)


def is_budget_analysis_intent(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(
        re.search(
            r"(分析|查询|统计|对比|差异|偏差|执行|重跑|重算|汇总|趋势|钻取|看一下|看下|看.*数据|预算执行|预实|口径|多少|几个|几条|数量|占比|总数|规模|收入|利息|费用|利润|拨备|净息差|nim|roe|部门|产品|科目|支行|贷款|存款|资产|负债|月度|季度|年度|报表|明细|图表|测算|预测|模拟|目标求解|滚动预算|版本|导出|展示)",
            t,
        )
    )


def is_budget_metadata_query(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(
        re.search(
            r"(数据库|库里|系统里|系统中).*(多少|几个|几条|数量|总数|占比|分布|覆盖)|(多少|几个|几条|数量|总数).*(部门|科目|产品|记录|数据)",
            t,
        )
    )


def is_contextual_budget_followup(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(
        re.search(
            r"(这些|上述|上面|刚才|前面|上一条).*(部门|科目|产品|数据|结果)|(列出来|清单|列表|明细|展开|给我看)",
            t,
        )
    )


def is_layout_adjust_request(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(
        re.search(
            r"(排版|重排|重新排版|格式|展示方式|展示格式|字段顺序|表头|两列|分两列|分列|并列展示|横向展示|列展示|口径.*两列|预算.*实际.*两列)",
            t,
        )
    )


def is_pivot_view_request(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(re.search(r"(数据透视表|透视表|透视图|pivot)", t, flags=re.IGNORECASE))


def is_budget_knowledge_question(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    knowledge_patterns = [
        r"是什么",
        r"有哪些",
        r"为什么",
        r"怎么做",
        r"如何",
        r"需要关注",
        r"注意事项",
        r"区别",
        r"原则",
        r"方法",
        r"流程",
        r"建议",
        r"常见问题",
    ]
    return any(re.search(p, t) for p in knowledge_patterns)
