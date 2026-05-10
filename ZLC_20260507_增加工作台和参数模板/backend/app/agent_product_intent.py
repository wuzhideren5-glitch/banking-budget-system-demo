from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from app.agent_prompt_assets import get_product_manager_intent_assets
from app.db_paths import common_db_path
from app.deepseek_client import DeepseekClient


def _org_hints_path(kb_root: Path) -> Path:
    return kb_root / "06_agent_prompts" / "product_manager_intent_org_hints.json"


def load_org_hint_rules(kb_root: Path) -> list[dict[str, Any]]:
    p = _org_hints_path(kb_root)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        rules = data.get("rules")
        return list(rules) if isinstance(rules, list) else []
    except Exception:
        return []


def _normalize_code_entry_list(items: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        c = str(it.get("code") or "").strip()
        if not c:
            continue
        out.append({"code": c, "name": str(it.get("name") or "").strip()})
    return out


def _merge_code_entries(target: list[dict[str, str]], incoming: list[dict[str, str]]) -> None:
    seen = {str(x.get("code") or "").strip() for x in target if x.get("code")}
    for it in incoming:
        c = str(it.get("code") or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        target.append({"code": c, "name": str(it.get("name") or "")})


_WHOLE_BANK_OK = re.compile(r"(全行|全辖|整体汇总|全表|不区分部门|不区分产品|不限定产品|整个银行)")
_ORG_NARROW_HINT = re.compile(
    r"(汽车金融|车贷|个金|个人金融|企业金融|普惠金融|对公|小微|"
    r"司库|金市|金融市场|开鑫贷|车车贷|企企贷|企小乐|开心小账户|"
    r"泛开鑫贷|开心账户|条线|分行|支行)"
)


def enrich_query_spec_with_org_hints(
    kb_root: Path, query: str, query_spec: dict[str, Any] | None
) -> dict[str, Any]:
    """按关键词规则补全 departments / products，避免只锁数据科目、漏组织维。"""
    qs: dict[str, Any] = dict(query_spec or {})
    for k in ("report_accounts", "data_accounts", "departments", "products"):
        if k not in qs or not isinstance(qs[k], list):
            qs[k] = []
    q = query or ""
    for rule in load_org_hint_rules(kb_root):
        kws = rule.get("keywords") or []
        if not isinstance(kws, list) or not any(str(kw) in q for kw in kws):
            continue
        _merge_code_entries(qs["departments"], _normalize_code_entry_list(rule.get("departments")))
        _merge_code_entries(qs["products"], _normalize_code_entry_list(rule.get("products")))
    return qs


def _tree_descendants(root_codes: set[str], children_by_parent: dict[str, list[str]]) -> set[str]:
    out: set[str] = set()
    stack = [c for c in root_codes if c]
    while stack:
        u = stack.pop()
        if u in out:
            continue
        out.add(u)
        for v in children_by_parent.get(u, []):
            if v not in out:
                stack.append(v)
    return out


def _lookup_one(cur: sqlite3.Cursor, sql: str, param: str) -> str | None:
    cur.execute(sql, (param,))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else None


def prune_redundant_child_dimensions_in_query_spec(query_spec: dict[str, Any]) -> dict[str, Any]:
    """
    维度层级简化（与系统目录一致时生效）：
    - 已锁定报告科目（可解析到 report_account.code）时，去掉映射到该报告子树下的数据科目；
    - 已锁定部门科目（可解析到 dept_account.code）时，去掉归属部门落在该部门子树下的产品科目。
    """
    qs: dict[str, Any] = dict(query_spec or {})
    for k in ("report_accounts", "data_accounts", "departments", "products"):
        raw = qs.get(k)
        qs[k] = list(raw) if isinstance(raw, list) else []

    db_path = common_db_path()
    if not db_path.is_file():
        return qs

    try:
        conn = sqlite3.connect(str(db_path))
    except Exception:
        return qs

    try:
        cur = conn.cursor()

        # --- 报告 -> 数据：report_data_mapping + report_account 子树 ---
        cur.execute("SELECT report_acct_code, parent_code FROM report_account")
        rpt_children: dict[str, list[str]] = defaultdict(list)
        for code, parent in cur.fetchall():
            c = str(code or "").strip()
            if not c:
                continue
            p = str(parent or "").strip()
            rpt_children[p].append(c)

        locked_report: set[str] = set()
        for it in qs.get("report_accounts") or []:
            if not isinstance(it, dict):
                continue
            c = str(it.get("code") or "").strip()
            n = str(it.get("name") or "").strip()
            if c and _lookup_one(cur, "SELECT 1 FROM report_account WHERE report_acct_code = ?", c):
                locked_report.add(c)
            elif n:
                rc = _lookup_one(cur, "SELECT report_acct_code FROM report_account WHERE report_acct_name = ?", n)
                if rc:
                    locked_report.add(rc)

        if locked_report:
            covered_reports = _tree_descendants(locked_report, rpt_children)
            cur.execute("SELECT report_acct_code, data_acct_code FROM report_data_mapping")
            covered_data: set[str] = set()
            for rpt, data in cur.fetchall():
                r = str(rpt or "").strip()
                d = str(data or "").strip()
                if r in covered_reports and d:
                    covered_data.add(d)

            new_data: list[dict[str, str]] = []
            for it in qs.get("data_accounts") or []:
                if not isinstance(it, dict):
                    continue
                dc = str(it.get("code") or "").strip()
                if not dc:
                    dn = str(it.get("name") or "").strip()
                    if dn:
                        dc = _lookup_one(
                            cur, "SELECT data_acct_code FROM data_account WHERE data_acct_name = ?", dn
                        ) or ""
                if dc and dc in covered_data:
                    continue
                new_data.append(it)
            qs["data_accounts"] = new_data

        # --- 部门 -> 产品：dept_product_mapping + dept_account 子树 ---
        cur.execute("SELECT dept_code, parent_code FROM dept_account")
        dept_children: dict[str, list[str]] = defaultdict(list)
        for code, parent in cur.fetchall():
            c = str(code or "").strip()
            if not c:
                continue
            p = str(parent or "").strip()
            dept_children[p].append(c)

        locked_dept: set[str] = set()
        for it in qs.get("departments") or []:
            if not isinstance(it, dict):
                continue
            c = str(it.get("code") or "").strip()
            n = str(it.get("name") or "").strip()
            if c and _lookup_one(cur, "SELECT 1 FROM dept_account WHERE dept_code = ?", c):
                locked_dept.add(c)
            elif n:
                dcode = _lookup_one(cur, "SELECT dept_code FROM dept_account WHERE dept_name = ?", n)
                if dcode:
                    locked_dept.add(dcode)

        if locked_dept:
            covered_depts = _tree_descendants(locked_dept, dept_children)
            cur.execute("SELECT product_code, dept_code FROM dept_product_mapping")
            prod_to_dept = {str(r[0] or "").strip(): str(r[1] or "").strip() for r in cur.fetchall() if r[0]}

            new_prods: list[dict[str, str]] = []
            for it in qs.get("products") or []:
                if not isinstance(it, dict):
                    continue
                pc = str(it.get("code") or "").strip()
                if not pc:
                    pn = str(it.get("name") or "").strip()
                    if pn:
                        pc = _lookup_one(cur, "SELECT product_code FROM product_type WHERE product_name = ?", pn) or ""
                dept_of_p = prod_to_dept.get(pc, "")
                if pc and dept_of_p and dept_of_p in covered_depts:
                    continue
                new_prods.append(it)
            qs["products"] = new_prods
    finally:
        conn.close()

    return qs


def apply_product_manager_org_postprocess(kb_root: Path, query: str, pm: dict[str, Any]) -> dict[str, Any]:
    """合并组织维提示词规则后，再校验：条线语境下必须能锁部门或产品。"""
    if not isinstance(pm, dict):
        return pm
    route = str(pm.get("route") or "")
    if route not in ("data_query_ready", "data_query_incomplete"):
        return pm

    qs = pm.get("query_spec")
    if not isinstance(qs, dict):
        qs = {}
    qs = enrich_query_spec_with_org_hints(kb_root, query, qs)
    qs = prune_redundant_child_dimensions_in_query_spec(qs)
    pm["query_spec"] = qs

    depts = qs.get("departments") if isinstance(qs.get("departments"), list) else []
    prods = qs.get("products") if isinstance(qs.get("products"), list) else []
    reports = qs.get("report_accounts") if isinstance(qs.get("report_accounts"), list) else []
    data_accounts = qs.get("data_accounts") if isinstance(qs.get("data_accounts"), list) else []
    has_org = bool(depts or prods)
    has_report_parent = bool(reports)
    has_data_leaf = bool(data_accounts)
    has_dept_parent = bool(depts)

    q = query or ""

    # 上级口径优先：已锁上级时不再追问下级（报告→数据；部门→产品）。
    miss = [str(x) for x in (pm.get("missing_aspects") or []) if x]
    if has_report_parent:
        miss = [x for x in miss if x != "metric_scope"]
    if has_dept_parent:
        miss = [x for x in miss if x != "org_product"]
    pm["missing_aspects"] = miss

    # 若仅因上述下级追问导致 incomplete，且时间已可执行，则直接转 ready。
    if str(pm.get("route") or "") == "data_query_incomplete":
        if not miss and _query_spec_has_time(qs) and (has_report_parent or has_data_leaf):
            pm["route"] = "data_query_ready"
            pm["clarification_message"] = ""

    if route == "data_query_ready" and _ORG_NARROW_HINT.search(q) and not _WHOLE_BANK_OK.search(q):
        if not has_org:
            pm["route"] = "data_query_incomplete"
            miss = [str(x) for x in (pm.get("missing_aspects") or []) if x]
            if "org_product" not in miss:
                miss.append("org_product")
            pm["missing_aspects"] = miss
            if not str(pm.get("clarification_message") or "").strip():
                pm["clarification_message"] = (
                    "已识别为条线/分行业务类问题，但尚未锁定「部门科目」或「产品科目」。"
                    "请补充具体部门或产品（可与上表科目代码/名称一致），或说明需要按**全行**汇总。"
                )
    return apply_product_manager_metric_gate(kb_root, query, pm)


def _query_spec_has_time(qs: dict[str, Any]) -> bool:
    if str(qs.get("period_description") or "").strip():
        return True
    for k in ("year", "quarter", "month"):
        if str(qs.get(k) or "").strip():
            return True
    return False


def _has_data_account_code(qs: dict[str, Any]) -> bool:
    for a in qs.get("data_accounts") or []:
        if isinstance(a, dict) and str(a.get("code") or "").strip():
            return True
    return False


def _needs_fine_interest_income_data_account(user_query: str) -> bool:
    """用户要「利息收入」细项而非净息汇总时，需数据科目 code（与 metric_rules 一致）。"""
    q = (user_query or "").replace(" ", "")
    if "非息" in q or "非利息" in q:
        return False
    if "净利息" in q or "利息净" in q:
        return False
    if "利息收入" in q or "外部利息" in q:
        return True
    return False


def apply_product_manager_metric_gate(_kb_root: Path, query: str, pm: dict[str, Any]) -> dict[str, Any]:
    """在组织维校验之后：时间可执行性、利息收入细项与数据科目锁定等。"""
    if not isinstance(pm, dict):
        return pm
    if str(pm.get("route") or "") != "data_query_ready":
        return pm
    qs = pm.get("query_spec")
    if not isinstance(qs, dict):
        qs = {}
        pm["query_spec"] = qs

    if not _query_spec_has_time(qs):
        pm["route"] = "data_query_incomplete"
        miss = [str(x) for x in (pm.get("missing_aspects") or []) if x]
        if "time" not in miss:
            miss.append("time")
        pm["missing_aspects"] = miss
        if not str(pm.get("clarification_message") or "").strip():
            pm["clarification_message"] = (
                "查询时间范围尚不明确。请补充年度、季度或月份，或用自然语言描述期间（如「过去三个月」对应的具体月份/年度）。"
            )
        return pm

    if _needs_fine_interest_income_data_account(query) and not _has_data_account_code(qs):
        pm["route"] = "data_query_incomplete"
        miss = [str(x) for x in (pm.get("missing_aspects") or []) if x]
        if "metric_scope" not in miss:
            miss.append("metric_scope")
        pm["missing_aspects"] = miss
        if not str(pm.get("clarification_message") or "").strip():
            pm["clarification_message"] = (
                "您提到「利息收入」类细项：本系统在报告较粗层级多为「净利息收入」等汇总；"
                "若要看**细分利息收入**，请在数据科目中指定具体 code（如清单中对应科目），"
                "或改问「净利息收入/利息净收入」汇总口径。"
            )
        return pm
    return pm


def format_query_spec_locked_dimensions_block(query_spec: dict[str, Any] | None) -> str:
    """供查询规划等步骤使用：列出 query_spec 中已填代码与名称。"""
    qs = query_spec if isinstance(query_spec, dict) else {}
    lines: list[str] = ["## 已锁定的查询维度（系统内 code｜name）"]

    def append_section(title: str, key: str) -> None:
        lines.append(f"**{title}**")
        items = qs.get(key)
        if not isinstance(items, list) or not items:
            lines.append("- （未指定）")
            return
        any_row = False
        for it in items:
            if not isinstance(it, dict):
                continue
            c = str(it.get("code") or "").strip()
            n = str(it.get("name") or "").strip()
            if not c and not n:
                continue
            any_row = True
            lines.append(f"- {c}｜{n}" if c and n else f"- {c or n}")
        if not any_row:
            lines.append("- （未指定）")

    append_section("报告科目", "report_accounts")
    append_section("数据科目", "data_accounts")
    append_section("部门科目", "departments")
    append_section("产品科目", "products")
    lines.append("**时间范围**")
    pd = str(qs.get("period_description") or "").strip()
    y = str(qs.get("year") or "").strip()
    qn = str(qs.get("quarter") or "").strip()
    mo = str(qs.get("month") or "").strip()
    bits = [x for x in (pd, y, qn, mo) if x]
    if bits:
        lines.append(f"- {'；'.join(bits)}")
    else:
        lines.append("- （未指定）")
    return "\n".join(lines).strip()


def build_catalog_digest(common_db: Path, *, max_chars: int | None = 14_000) -> str:
    """从 common.db 生成报告/数据/部门/产品及授权组合摘要；超长时截断并保留统计头。"""
    if not common_db.exists():
        return "（当前环境未找到 common.db，无法加载科目清单。）"

    lines: list[str] = []
    try:
        conn = sqlite3.connect(common_db)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        rc = cur.execute("SELECT COUNT(*) FROM report_account").fetchone()[0]
        dc = cur.execute("SELECT COUNT(*) FROM data_account").fetchone()[0]
        dec = cur.execute("SELECT COUNT(*) FROM dept_account").fetchone()[0]
        pc = cur.execute("SELECT COUNT(*) FROM product_type").fetchone()[0]
        mc = cur.execute("SELECT COUNT(*) FROM dept_product_mapping").fetchone()[0]
        lines.append(
            f"【统计】报告科目 {rc} 条；数据科目 {dc} 条；部门科目 {dec} 条；"
            f"产品科目 {pc} 条；部门-产品授权组合（dept_product_mapping）{mc} 条。"
        )
        lines.append("【报告科目】代码|名称|层级（节选，按代码排序）")
        for row in cur.execute(
            "SELECT report_acct_code, report_acct_name, level FROM report_account ORDER BY report_acct_code LIMIT 800"
        ):
            lines.append(f"  {row['report_acct_code']}|{row['report_acct_name']}|{row['level']}")

        lines.append("【数据科目】代码|名称|值类型（节选，按代码排序）")
        for row in cur.execute(
            "SELECT data_acct_code, data_acct_name, value_type FROM data_account ORDER BY data_acct_code LIMIT 800"
        ):
            lines.append(f"  {row['data_acct_code']}|{row['data_acct_name']}|{row['value_type']}")

        lines.append("【部门科目】代码|名称|层级（节选）")
        for row in cur.execute(
            "SELECT dept_code, dept_name, level FROM dept_account ORDER BY dept_code LIMIT 400"
        ):
            lines.append(f"  {row['dept_code']}|{row['dept_name']}|{row['level']}")

        lines.append("【产品科目】代码|名称（节选）")
        for row in cur.execute(
            "SELECT product_code, product_name FROM product_type ORDER BY product_code LIMIT 400"
        ):
            lines.append(f"  {row['product_code']}|{row['product_name']}")

        lines.append("【部门-产品授权组合】序号 部门代码|部门名称|产品代码|产品名称（遍历 mapping 表，按部门、产品排序）")
        n = 0
        for row in cur.execute(
            """
            SELECT d.dept_code, d.dept_name, p.product_code, p.product_name
            FROM dept_product_mapping m
            JOIN dept_account d ON d.dept_code = m.dept_code
            JOIN product_type p ON p.product_code = m.product_code
            ORDER BY d.dept_code, p.product_code
            """
        ):
            n += 1
            lines.append(
                f"  {n}. {row['dept_code']}|{row['dept_name']}|{row['product_code']}|{row['product_name']}"
            )
        conn.close()
    except Exception as exc:
        return f"（加载科目清单时出错：{exc}）"

    text = "\n".join(lines)
    if max_chars is None or len(text) <= max_chars:
        return text
    return (
        text[: max_chars - 80]
        + f"\n……（已截断，总长度超限，仅展示前约 {max_chars} 字符；完整数据以系统配置为准）"
    )


def dialogue_weight(dialogue_id: int, max_dialogue_id: int, decay: float) -> float:
    if dialogue_id < 1:
        dialogue_id = 1
    if max_dialogue_id < 1:
        max_dialogue_id = 1
    exp = max(0, max_dialogue_id - dialogue_id)
    return round(100.0 * (decay**exp), 4)


def build_weighted_transcript(
    history: list[dict[str, Any]],
    *,
    last_dialogue_id: int,
    decay: float,
    max_messages: int,
    empty_placeholder: str,
) -> str:
    """将历史对话按 dialogue_id 与衰减权重格式化；未标注 id 的消息视为属于 last_dialogue_id。"""
    max_id = last_dialogue_id if last_dialogue_id > 0 else 1
    rows: list[str] = []
    tail = history[-max_messages:] if max_messages > 0 else history
    for m in tail:
        role = str(m.get("role", "")).strip()
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        label = "用户" if role == "user" else "智能体"
        try:
            did = int(m.get("dialogue_id") or max_id)
        except (TypeError, ValueError):
            did = max_id
        w = dialogue_weight(did, max_id, decay)
        rows.append(f"[对话ID={did} 权重={w}] {label}：{content}")
    return "\n".join(rows) if rows else empty_placeholder


def _parse_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw)
    if m:
        try:
            obj = json.loads(m.group(1))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    m2 = re.search(r"\{[\s\S]*\}", raw)
    if m2:
        try:
            obj = json.loads(m2.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _local_sensitive_hint(text: str, keywords: list[str]) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in keywords)


def _looks_like_finance_domain(text: str) -> bool:
    t = (text or "").lower()
    keys = (
        "银行",
        "金融",
        "财务",
        "预算",
        "资产",
        "负债",
        "利润",
        "收入",
        "成本",
        "费用",
        "净息差",
        "roe",
        "nim",
    )
    return any(k in t for k in keys)


def _looks_like_data_query(text: str) -> bool:
    t = (text or "").lower()
    has_action = bool(re.search(r"(查询|分析|统计|对比|同比|环比|趋势|明细|汇总|看看|列出|有多少|数量|分布|占比)", t))
    has_subject = bool(re.search(r"(预算|实际|科目|部门|产品|报表|数据|金额|资产|负债|利润|收入|费用)", t))
    has_time = bool(
        re.search(r"(20\d{2}|本月|本季度|本年|全年|上半年|下半年|一季度|二季度|三季度|四季度|最近|近\d+月)", t)
    )
    # 数据分析通常至少有“动作+对象”，或已给出时间并带对象。
    return (has_action and has_subject) or (has_time and has_subject)


def _build_rule_query_spec(query: str, pending_query_spec: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    q = query or ""
    p = pending_query_spec if isinstance(pending_query_spec, dict) else {}
    year_match = re.search(r"(20\d{2})", q)
    quarter_match = re.search(r"(一季度|二季度|三季度|四季度|q[1-4])", q.lower())
    month_match = re.search(r"(\d{1,2})月", q)
    has_org = bool(re.search(r"(部门|条线|支行|产品|业务)", q))
    has_metric = bool(re.search(r"(收入|利润|成本|费用|资产|负债|科目|预算|实际|差异|规模)", q))
    has_time = bool(year_match or quarter_match or month_match or re.search(r"(本月|本季度|本年|全年|最近)", q))

    year = f"Y{year_match.group(1)}" if year_match else str(p.get("year") or "")
    quarter = quarter_match.group(1) if quarter_match else str(p.get("quarter") or "")
    month = f"M{int(month_match.group(1)):02d}" if month_match else str(p.get("month") or "")
    period_desc = " ".join(x for x in [year, quarter, month] if x).strip() or str(p.get("period_description") or "")

    missing: list[str] = []
    if not has_time and not period_desc:
        missing.append("time")
    if not has_org and not (p.get("departments") or p.get("products")):
        missing.append("org_product")
    if not has_metric and not (p.get("report_accounts") or p.get("data_accounts") or p.get("query_focus")):
        missing.append("metric_scope")

    query_focus = "unclear"
    if re.search(r"(收入|利润|成本|费用|损益|净利)", q):
        query_focus = "profit_loss"
    elif re.search(r"(规模|余额|资产|负债|数量|户数|业务量)", q):
        query_focus = "business_scale"

    spec: dict[str, Any] = {
        "period_description": period_desc,
        "year": year,
        "quarter": quarter,
        "month": month,
        "report_accounts": p.get("report_accounts") or [],
        "data_accounts": p.get("data_accounts") or [],
        "departments": p.get("departments") or [],
        "products": p.get("products") or [],
        "query_focus": query_focus,
    }
    return spec, missing


def run_product_manager_intent_rule_fallback(
    *,
    kb_root: Path,
    query: str,
    history: list[dict[str, Any]],
    last_dialogue_id: int,
    pending_query_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    """当 LLM 不可用或分类输出异常时，使用规则兜底以满足提示词路由要求。"""
    _, _, msgs, _ = get_product_manager_intent_assets(kb_root)
    raw_kw = msgs.get("sensitive_local_keywords")
    keywords = [str(x) for x in raw_kw] if isinstance(raw_kw, list) else []
    q = (query or "").strip()
    has_pending = bool(isinstance(pending_query_spec, dict) and pending_query_spec)
    is_cont = has_pending and bool(re.search(r"(继续|补充|再|按|确认|执行|好的|行|可以|改成|换成|加上)", q))

    if is_cont:
        dialogue_id = last_dialogue_id if last_dialogue_id > 0 else 1
    else:
        dialogue_id = (last_dialogue_id + 1) if last_dialogue_id > 0 else 1

    if _local_sensitive_hint(q, keywords):
        return apply_product_manager_org_postprocess(
            kb_root,
            q,
            {
                "is_continuation": is_cont,
                "dialogue_id": dialogue_id,
                "route": "sensitive",
                "answer_body": "",
                "clarification_message": "",
                "missing_aspects": [],
                "query_spec": pending_query_spec or {},
            },
        )

    if not _looks_like_finance_domain(q):
        return apply_product_manager_org_postprocess(
            kb_root,
            q,
            {
                "is_continuation": is_cont,
                "dialogue_id": dialogue_id,
                "route": "off_topic",
                "answer_body": "",
                "clarification_message": "",
                "missing_aspects": [],
                "query_spec": pending_query_spec or {},
            },
        )

    if _looks_like_data_query(q):
        spec, missing = _build_rule_query_spec(q, pending_query_spec)
        if missing:
            return apply_product_manager_org_postprocess(
                kb_root,
                q,
                {
                    "is_continuation": is_cont,
                    "dialogue_id": dialogue_id,
                    "route": "data_query_incomplete",
                    "answer_body": "",
                    "clarification_message": "",
                    "missing_aspects": missing,
                    "query_spec": spec,
                },
            )
        return apply_product_manager_org_postprocess(
            kb_root,
            q,
            {
                "is_continuation": is_cont,
                "dialogue_id": dialogue_id,
                "route": "data_query_ready",
                "answer_body": "",
                "clarification_message": "",
                "missing_aspects": [],
                "query_spec": spec,
            },
        )

    return apply_product_manager_org_postprocess(
        kb_root,
        q,
        {
            "is_continuation": is_cont,
            "dialogue_id": dialogue_id,
            "route": "domain_knowledge",
            "answer_body": "",
            "clarification_message": "",
            "missing_aspects": [],
            "query_spec": pending_query_spec or {},
        },
    )


def build_classifier_user_prompt(
    *,
    kb_root: Path,
    weighted_transcript: str,
    current_query: str,
    last_dialogue_id: int,
    pending_query_spec: dict[str, Any] | None,
) -> str:
    _, user_tmpl, _msgs, catalog_static = get_product_manager_intent_assets(kb_root)
    pending = json.dumps(pending_query_spec, ensure_ascii=False) if pending_query_spec else "null"
    last_text = str(last_dialogue_id) if last_dialogue_id > 0 else "尚无（按 0 处理）"
    return (
        user_tmpl.replace("<<<PM_CATALOG_DIGEST>>>", catalog_static)
        .replace("<<<PM_WEIGHTED_TRANSCRIPT>>>", weighted_transcript)
        .replace("<<<PM_PENDING_QUERY_SPEC>>>", pending)
        .replace("<<<PM_CURRENT_QUERY>>>", current_query.strip())
        .replace("<<<PM_LAST_DIALOGUE_ID_TEXT>>>", last_text)
    )


def run_product_manager_intent(
    client: DeepseekClient | None,
    *,
    kb_root: Path,
    query: str,
    history: list[dict[str, Any]],
    last_dialogue_id: int,
    pending_query_spec: dict[str, Any] | None,
    decay: float = 0.7,
    max_history_messages: int = 24,
    debug_hook: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any] | None:
    if not client or not client.is_enabled():
        return None
    system_prompt, _, msgs, _ = get_product_manager_intent_assets(kb_root)
    raw_kw = msgs.get("sensitive_local_keywords")
    keywords = [str(x) for x in raw_kw] if isinstance(raw_kw, list) else []
    if _local_sensitive_hint(query, keywords):
        did = max(1, last_dialogue_id) if last_dialogue_id > 0 else 1
        return {
            "is_continuation": False,
            "dialogue_id": did,
            "route": "sensitive",
            "answer_body": "",
            "clarification_message": "",
            "missing_aspects": [],
            "query_spec": {},
        }

    empty_line = str(msgs.get("empty_transcript_line") or "（尚无历史对话）")
    transcript = build_weighted_transcript(
        history,
        last_dialogue_id=last_dialogue_id if last_dialogue_id > 0 else 1,
        decay=decay,
        max_messages=max_history_messages,
        empty_placeholder=empty_line,
    )
    user_prompt = build_classifier_user_prompt(
        kb_root=kb_root,
        weighted_transcript=transcript,
        current_query=query.strip(),
        last_dialogue_id=last_dialogue_id,
        pending_query_spec=pending_query_spec,
    )
    raw = client.chat_completion(
        system_prompt,
        user_prompt,
        temperature=0.1,
        max_tokens=1_800,
    )
    if debug_hook is not None:
        try:
            debug_hook(
                {
                    "purpose": "pm_intent_classifier",
                    "input": {
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt,
                        "temperature": 0.1,
                        "max_tokens": 1800,
                    },
                    "output": raw,
                }
            )
        except Exception:
            pass
    parsed = _parse_json_object(raw or "")
    if not parsed:
        return None

    route = str(parsed.get("route") or "").strip()
    if route not in {
        "sensitive",
        "off_topic",
        "domain_knowledge",
        "data_query_incomplete",
        "data_query_ready",
    }:
        return None

    is_cont = bool(parsed.get("is_continuation"))
    try:
        did = int(parsed.get("dialogue_id"))
    except (TypeError, ValueError):
        did = last_dialogue_id

    if is_cont:
        did = last_dialogue_id if last_dialogue_id > 0 else max(1, did)
    else:
        if last_dialogue_id > 0:
            did = max(last_dialogue_id + 1, did)
        else:
            did = max(1, did)
    if did < 1:
        did = 1

    qspec = parsed.get("query_spec")
    if not isinstance(qspec, dict):
        qspec = {}

    return apply_product_manager_org_postprocess(
        kb_root,
        query,
        {
            "is_continuation": is_cont,
            "dialogue_id": did,
            "route": route,
            "answer_body": str(parsed.get("answer_body") or "").strip(),
            "clarification_message": str(parsed.get("clarification_message") or "").strip(),
            "missing_aspects": list(parsed.get("missing_aspects") or []),
            "query_spec": qspec,
        },
    )


def merge_reply_disclaimer(kb_root: Path, route: str, answer_body: str) -> str:
    _, _, msgs, _ = get_product_manager_intent_assets(kb_root)
    off = str(msgs.get("disclaimer_off_topic") or "")
    dom = str(msgs.get("disclaimer_domain_knowledge") or "")
    body = (answer_body or "").strip()
    if route == "off_topic":
        return f"{off}\n\n{body}" if body else off
    if route == "domain_knowledge":
        return f"{dom}\n\n{body}" if body else dom
    return body


def incomplete_clarification_text(kb_root: Path, message: str) -> str:
    _, _, msgs, _ = get_product_manager_intent_assets(kb_root)
    tail = str(msgs.get("default_incomplete_tail") or "")
    fallback = str(msgs.get("incomplete_fallback_base") or "为准确查询预算数据，还需要您补充若干条件。")
    base = (message or "").strip()
    if not base:
        base = fallback
    if "缺省" not in base and "默认" not in base:
        base = base + tail
    default_hint = "如果你暂时不补充额外信息，直接回复“确认”或“缺省”，我会按当前理解直接查询。"
    if default_hint in base:
        return base
    return f"{base.rstrip()}\n\n{default_hint}"


def query_spec_to_requirement_override(query_spec: dict[str, Any]) -> dict[str, Any]:
    """产品经理意图「可查询」时，跳过四槽位澄清，直接进入规划/执行链路。"""
    base = query_spec_to_pm_prefill(query_spec)
    clarified = base.get("clarified_slots") or {}
    return {
        "slot_status": {
            "time_period": True,
            "business_scope": True,
            "comparison_type": True,
            "granularity": True,
        },
        "clarified_slots": clarified,
        "missing_slots": [],
        "assumptions": [],
        "need_clarification": False,
        "clarification_rounds": 0,
    }


def query_spec_to_pm_prefill(query_spec: dict[str, Any]) -> dict[str, Any]:
    """将分类器输出的 query_spec 转为 requirement_check / 下游可用的 clarified_slots。"""
    parts: list[str] = []
    pd = str(query_spec.get("period_description") or "").strip()
    if pd:
        parts.append(pd)
    y = str(query_spec.get("year") or "").strip()
    q = str(query_spec.get("quarter") or "").strip()
    mo = str(query_spec.get("month") or "").strip()
    if y:
        parts.append(y)
    if q:
        parts.append(q)
    if mo:
        parts.append(mo)
    time_period = " ".join(parts).strip()

    dept_bits: list[str] = []
    for d in query_spec.get("departments") or []:
        if isinstance(d, dict):
            c = str(d.get("code") or "").strip()
            n = str(d.get("name") or "").strip()
            dept_bits.append(f"{n}({c})" if c else n)
    prod_bits: list[str] = []
    for p in query_spec.get("products") or []:
        if isinstance(p, dict):
            c = str(p.get("code") or "").strip()
            n = str(p.get("name") or "").strip()
            prod_bits.append(f"{n}({c})" if c else n)

    acct_bits: list[str] = []
    for a in query_spec.get("report_accounts") or []:
        if isinstance(a, dict):
            c = str(a.get("code") or "").strip()
            n = str(a.get("name") or "").strip()
            acct_bits.append(f"报告:{n}({c})" if c else f"报告:{n}")
    for a in query_spec.get("data_accounts") or []:
        if isinstance(a, dict):
            c = str(a.get("code") or "").strip()
            n = str(a.get("name") or "").strip()
            acct_bits.append(f"数据:{n}({c})" if c else f"数据:{n}")

    focus = str(query_spec.get("query_focus") or "").strip()
    scope_parts = dept_bits + prod_bits
    business_scope = "；".join(scope_parts) if scope_parts else ""
    metric_line = "；".join(acct_bits) if acct_bits else ""
    if focus:
        metric_line = f"{metric_line}；查询焦点:{focus}" if metric_line else f"查询焦点:{focus}"

    selected_level = int(query_spec.get("__selected_compare_level__") or 0)
    q_comp = str(query_spec.get("comparison_type") or "").strip().lower()
    inferred_comp = "yoy" if (1 <= selected_level <= 5 or q_comp == "yoy") else "none"
    clarified: dict[str, Any] = {
        "time_period": time_period,
        "business_scope": business_scope,
        "comparison_type": inferred_comp,
        "granularity": "monthly",
        "query_focus": focus,
        "report_accounts": query_spec.get("report_accounts") or [],
        "data_accounts": query_spec.get("data_accounts") or [],
        "departments": query_spec.get("departments") or [],
        "products": query_spec.get("products") or [],
        "metric_summary": metric_line,
    }
    if 1 <= selected_level <= 5:
        clarified["comparison_show_level"] = selected_level
    return {"clarified_slots": clarified}


def should_apply_pm_prefill(pm: dict[str, Any] | None) -> bool:
    if not pm:
        return False
    return pm.get("route") == "data_query_ready"
