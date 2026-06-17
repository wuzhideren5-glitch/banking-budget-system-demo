from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from app.agent.agent_prompt_assets import get_product_manager_intent_assets
from app.agent.agent_query_spec import normalise_current_query_spec
from app.core.db_paths import common_db_path
from app.integrations.deepseek_client import DeepseekClient
from app.services.org_product_runtime_catalog import org_product_runtime_products_cte


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


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").lower())


def _wants_metric_breakdown(query: str) -> bool:
    return bool(re.search(r"(明细|结构|构成|拆分|拆开|分项|逐项)", query or ""))


def _merge_metric_entries(target: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> None:
    seen = {str(x.get("code") or "").strip() for x in target if isinstance(x, dict) and x.get("code")}
    for it in incoming:
        c = str(it.get("code") or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        target.append(dict(it))


def _normalise_current_query_axes(query_spec: dict[str, Any] | None) -> dict[str, Any]:
    """Keep query specs on the current metric/data/department/product axes."""
    return normalise_current_query_spec(query_spec)


def _metric_descendants(cur: sqlite3.Cursor, root_codes: set[str]) -> set[str]:
    cur.execute("SELECT node_code, parent_code FROM data_account_metric_node WHERE is_active = 1")
    children: dict[str, list[str]] = defaultdict(list)
    for code, parent in cur.fetchall():
        c = str(code or "").strip()
        p = str(parent or "").strip()
        if c:
            children[p].append(c)
    return _tree_descendants(root_codes, children)


def _parent_codes_from_metric_ref(code: str) -> set[str]:
    out: set[str] = set()
    current = str(code or "").strip().upper()
    while "." in current:
        current = current.rsplit(".", 1)[0]
        if current:
            out.add(current)
    return out


def _confirmed_org_product_runtime_refs(cur: sqlite3.Cursor) -> tuple[set[str], set[str]]:
    """Return runtime refs confirmed by the org-product metric runtime tree."""
    metric_refs: set[str] = set()
    data_refs: set[str] = set()
    try:
        source_rows = cur.execute(
            """
            SELECT node_code
            FROM data_account_metric_node
            WHERE is_active = 1
              AND runtime_account_enabled = 1
              AND COALESCE(product_code, '') <> ''
            """
        ).fetchall()
    except sqlite3.Error:
        return metric_refs, data_refs

    for source in source_rows:
        data_ref = str(source[0] or "").strip().upper()
        if not data_ref:
            continue
        metric_refs.add(data_ref)
        metric_refs.update(_parent_codes_from_metric_ref(data_ref))
        data_refs.add(data_ref)
    return metric_refs, data_refs


def _metric_has_children(cur: sqlite3.Cursor, node_code: str) -> bool:
    cur.execute(
        "SELECT 1 FROM data_account_metric_node WHERE parent_code = ? AND is_active = 1 LIMIT 1",
        (node_code,),
    )
    return cur.fetchone() is not None


def _query_scope_codes(qs: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("products",):
        for it in qs.get(key) or []:
            if not isinstance(it, dict):
                continue
            c = str(it.get("code") or "").strip()
            if c and c not in out:
                out.append(c)
    return out


def _expanded_product_scope_codes(cur: sqlite3.Cursor, scope_codes: list[str]) -> set[str]:
    selected = {str(code or "").strip().upper() for code in scope_codes if str(code or "").strip()}
    if not selected:
        return set()
    try:
        rows = cur.execute(
            f"""
            {org_product_runtime_products_cte()}
            SELECT product_code, parent_code
            FROM org_product_runtime_products
            WHERE product_code <> ''
            """
        ).fetchall()
    except sqlite3.Error:
        return selected

    children: dict[str, list[str]] = defaultdict(list)
    all_codes: set[str] = set()
    for code, parent in rows:
        child_code = str(code or "").strip().upper()
        parent_code = str(parent or "").strip().upper()
        if not child_code:
            continue
        all_codes.add(child_code)
        children[parent_code].append(child_code)

    expanded = {code for code in selected if code in all_codes or code == "CORP"}
    stack = [code for code in selected if code in all_codes]
    while stack:
        code = stack.pop()
        for child in children.get(code, []):
            if child in expanded:
                continue
            expanded.add(child)
            stack.append(child)
    return expanded or selected


def _lookup_metric_nodes(cur: sqlite3.Cursor, query: str, limit: int = 5) -> list[dict[str, Any]]:
    q_norm = _norm_text(query)
    if not q_norm:
        return []
    confirmed_metric_refs, _ = _confirmed_org_product_runtime_refs(cur)
    if not confirmed_metric_refs:
        return []
    metric_tokens = [
        token
        for token in ("净利息收入", "利息收入", "营业收入", "业务及管理费", "管理费", "费用", "利润", "收入", "贷款规模", "余额", "规模")
        if token in (query or "")
    ]
    cur.execute(
        """
        SELECT node_code, node_name, parent_code, level, node_type
        FROM data_account_metric_node
        WHERE is_active = 1
        ORDER BY level ASC, LENGTH(node_name) ASC, sort_order, node_code
        """
    )
    exact: list[dict[str, Any]] = []
    contained: list[dict[str, Any]] = []
    token_fuzzy: list[dict[str, Any]] = []
    for row in cur.fetchall():
        code = str(row[0] or "").strip()
        name = str(row[1] or "").strip()
        if not code or not name:
            continue
        if code.upper() not in confirmed_metric_refs:
            continue
        n_norm = _norm_text(name)
        if not n_norm:
            continue
        item = {
            "code": code,
            "name": name,
            "level": int(row[3] or 0),
            "node_type": str(row[4] or ""),
        }
        if n_norm == q_norm:
            exact.append(item)
        elif n_norm in q_norm:
            contained.append(item)
        elif any(_norm_text(token) in n_norm for token in metric_tokens):
            token_fuzzy.append(item)
    if exact or contained:
        return (exact + contained)[:limit]
    return token_fuzzy[:1]


def _bindings_for_metric_nodes(
    cur: sqlite3.Cursor,
    *,
    node_codes: list[str],
    scope_codes: list[str],
    include_descendants: bool,
) -> list[dict[str, Any]]:
    metric_codes: set[str] = set(node_codes)
    if include_descendants:
        metric_codes = _metric_descendants(cur, metric_codes)
    if not metric_codes:
        return []
    _, confirmed_data_refs = _confirmed_org_product_runtime_refs(cur)
    if not confirmed_data_refs:
        return []
    scope_filter = _expanded_product_scope_codes(cur, scope_codes)
    scope_filter.add("CORP")
    placeholders_metric = ",".join("?" for _ in metric_codes)
    placeholders_scope = ",".join("?" for _ in scope_filter)
    cur.execute(
        f"""
        SELECT b.data_acct_code AS binding_code, b.metric_node_code, b.scope_type, b.scope_code,
               b.data_acct_code, d.data_acct_name, d.value_type
        FROM data_account_metric_binding b
        JOIN data_account d ON d.data_acct_code = b.data_acct_code
        WHERE b.is_active = 1
          AND b.metric_node_code IN ({placeholders_metric})
          AND b.scope_code IN ({placeholders_scope})
        ORDER BY b.scope_type DESC, b.scope_code, b.sort_order, b.data_acct_code
        """,
        tuple(metric_codes) + tuple(scope_filter),
    )
    return [
        {
            "binding_code": str(row[0] or ""),
            "metric_node_code": str(row[1] or ""),
            "scope_type": str(row[2] or ""),
            "scope_code": str(row[3] or ""),
            "product_code": str(row[3] or "") if str(row[2] or "") == "PRODUCT" else "",
            "data_acct_code": str(row[4] or ""),
            "data_acct_name": str(row[5] or ""),
            "value_type": str(row[6] or ""),
        }
        for row in cur.fetchall()
        if str(row[4] or "").strip().upper() in confirmed_data_refs
    ]


def apply_metric_tree_query_axis(query: str, query_spec: dict[str, Any] | None) -> dict[str, Any]:
    """指标树优先：自然语言先锁 metric_node，再按产品/范围解析机构及产品指标编码。"""
    qs = _normalise_current_query_axes(query_spec)
    qs.pop("__metric_binding_gap__", None)
    qs.pop("__metric_binding_ambiguous__", None)

    db_path = common_db_path()
    if not db_path.is_file():
        return qs

    try:
        conn = sqlite3.connect(str(db_path))
    except Exception:
        return qs

    try:
        cur = conn.cursor()
        metric_nodes = [x for x in qs.get("metric_nodes") or [] if isinstance(x, dict)]
        if not metric_nodes:
            metric_nodes = _lookup_metric_nodes(cur, query)
            _merge_metric_entries(qs["metric_nodes"], metric_nodes)
        else:
            _merge_metric_entries(qs["metric_nodes"], metric_nodes)

        locked_nodes = [str(x.get("code") or "").strip() for x in qs.get("metric_nodes") or [] if isinstance(x, dict)]
        locked_nodes = [x for x in locked_nodes if x]
        if not locked_nodes:
            return qs

        wants_detail = _wants_metric_breakdown(query)
        has_non_leaf = any(_metric_has_children(cur, code) for code in locked_nodes)
        include_descendants = has_non_leaf
        bindings = _bindings_for_metric_nodes(
            cur,
            node_codes=locked_nodes,
            scope_codes=_query_scope_codes(qs),
            include_descendants=include_descendants,
        )
        if not bindings:
            qs["__metric_binding_gap__"] = {
                "metric_nodes": qs.get("metric_nodes") or [],
                "products": qs.get("products") or [],
                "reason": "当前产品或范围下尚未配置该指标的机构及产品指标编码",
            }
            return qs

        if not has_non_leaf and len(bindings) > 1:
            qs["__metric_binding_ambiguous__"] = {
                "metric_nodes": qs.get("metric_nodes") or [],
                "bindings": bindings,
                "reason": "同一叶子指标存在多个可用机构及产品指标编码",
            }
            return qs

        if has_non_leaf and wants_detail:
            qs["metric_expand_mode"] = "children"
        elif has_non_leaf:
            qs["metric_expand_mode"] = "summary"

        data_entries = list(qs.get("data_accounts") or [])
        _merge_code_entries(
            data_entries,
            [
                {"code": b["data_acct_code"], "name": b["data_acct_name"]}
                for b in bindings
                if b.get("data_acct_code")
            ],
        )
        qs["data_accounts"] = data_entries
    finally:
        conn.close()

    return qs


_WHOLE_BANK_OK = re.compile(r"(全行|全辖|整体汇总|全表|不区分部门|不区分产品|不限定产品|整个银行)")
_ORG_NARROW_HINT = re.compile(
    r"(汽车金融|车贷|个金|个人金融|企业金融|普惠金融|对公|小微|"
    r"司库|金市|金融市场|开鑫贷|车车贷|企企贷|企小乐|开心小账户|"
    r"泛开鑫贷|开心账户|条线|分行|支行)"
)


def enrich_query_spec_with_org_hints(
    kb_root: Path, query: str, query_spec: dict[str, Any] | None
) -> dict[str, Any]:
    """按关键词规则补全 departments / products，避免只锁指标编码、漏组织维。"""
    qs = _normalise_current_query_axes(query_spec)
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
    - 已锁定指标树节点时，去掉绑定到该指标子树下的机构及产品指标编码；
    - 已锁定部门科目（可解析到 dept_account.code）时，去掉归属部门落在该部门子树下的机构及产品。
    """
    qs = _normalise_current_query_axes(query_spec)

    db_path = common_db_path()
    if not db_path.is_file():
        return qs

    try:
        conn = sqlite3.connect(str(db_path))
    except Exception:
        return qs

    try:
        cur = conn.cursor()

        # --- 指标树 -> 数据：data_account_metric_binding + 指标子树 ---
        cur.execute(
            """
            SELECT node_code, parent_code
            FROM data_account_metric_node
            WHERE is_active = 1
            """
        )
        metric_children: dict[str, list[str]] = defaultdict(list)
        for code, parent in cur.fetchall():
            c = str(code or "").strip()
            if not c:
                continue
            p = str(parent or "").strip()
            metric_children[p].append(c)

        locked_metric: set[str] = set()
        for it in qs.get("metric_nodes") or []:
            if not isinstance(it, dict):
                continue
            c = str(it.get("code") or "").strip()
            n = str(it.get("name") or "").strip()
            if c and _lookup_one(
                cur,
                "SELECT 1 FROM data_account_metric_node WHERE node_code = ? AND is_active = 1",
                c,
            ):
                locked_metric.add(c)
            elif n:
                node_code = _lookup_one(
                    cur,
                    "SELECT node_code FROM data_account_metric_node WHERE node_name = ? AND is_active = 1",
                    n,
                )
                if node_code:
                    locked_metric.add(node_code)

        if locked_metric:
            covered_metrics = _tree_descendants(locked_metric, metric_children)
            cur.execute(
                """
                SELECT metric_node_code, data_acct_code
                FROM data_account_metric_binding
                WHERE is_active = 1
                """
            )
            covered_data: set[str] = set()
            for metric_node, data in cur.fetchall():
                node = str(metric_node or "").strip()
                d = str(data or "").strip()
                if node in covered_metrics and d:
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
    qs = apply_metric_tree_query_axis(query, qs)
    pm["query_spec"] = qs

    depts = qs.get("departments") if isinstance(qs.get("departments"), list) else []
    prods = qs.get("products") if isinstance(qs.get("products"), list) else []
    metric_nodes = qs.get("metric_nodes") if isinstance(qs.get("metric_nodes"), list) else []
    data_accounts = qs.get("data_accounts") if isinstance(qs.get("data_accounts"), list) else []
    has_org = bool(depts or prods)
    has_metric_node = bool(metric_nodes)
    has_data_leaf = bool(data_accounts)
    has_dept_parent = bool(depts)

    q = query or ""

    # 上级口径优先：已锁指标树节点时不再追问指标编码；已锁部门时不再追问产品。
    miss = [str(x) for x in (pm.get("missing_aspects") or []) if x]
    if has_metric_node:
        miss = [x for x in miss if x != "metric_scope"]
    if has_dept_parent:
        miss = [x for x in miss if x != "org_product"]
    pm["missing_aspects"] = miss

    # 若仅因上述下级追问导致 incomplete，且时间已可执行，则直接转 ready。
    if str(pm.get("route") or "") == "data_query_incomplete":
        if not miss and _query_spec_has_time(qs) and (has_metric_node or has_data_leaf):
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
                    "已识别为条线/分行业务类问题，但尚未锁定「部门科目」或「机构及产品」。"
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


def _has_metric_node(qs: dict[str, Any]) -> bool:
    for a in qs.get("metric_nodes") or []:
        if isinstance(a, dict) and str(a.get("code") or "").strip():
            return True
    return False


def _needs_fine_interest_income_data_account(user_query: str) -> bool:
    """用户要「利息收入」细项而非净息汇总时，需机构及产品指标 code（与 metric_rules 一致）。"""
    q = (user_query or "").replace(" ", "")
    if "非息" in q or "非利息" in q:
        return False
    if "净利息" in q or "利息净" in q:
        return False
    if "利息收入" in q or "外部利息" in q:
        return True
    return False


def apply_product_manager_metric_gate(_kb_root: Path, query: str, pm: dict[str, Any]) -> dict[str, Any]:
    """在组织维校验之后：时间可执行性、利息收入细项与指标编码锁定等。"""
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

    if isinstance(qs.get("__metric_binding_gap__"), dict):
        pm["route"] = "data_query_incomplete"
        miss = [str(x) for x in (pm.get("missing_aspects") or []) if x]
        if "metric_binding" not in miss:
            miss.append("metric_binding")
        pm["missing_aspects"] = miss
        gap = qs.get("__metric_binding_gap__") or {}
        nodes = gap.get("metric_nodes") if isinstance(gap, dict) else []
        node_text = "、".join(
            f"{str(x.get('code') or '').strip()} {str(x.get('name') or '').strip()}".strip()
            for x in nodes or []
            if isinstance(x, dict)
        )
        pm["clarification_message"] = (
            f"已识别指标树节点{('：' + node_text) if node_text else ''}，"
            "但当前产品或范围下尚未形成可用的机构及产品指标编码。"
            "这属于配置缺失，不应按 0 或空结果解读。请先到机构及产品指标维护唯一指标体系。"
        )
        return pm

    if isinstance(qs.get("__metric_binding_ambiguous__"), dict):
        pm["route"] = "data_query_incomplete"
        miss = [str(x) for x in (pm.get("missing_aspects") or []) if x]
        if "metric_binding" not in miss:
            miss.append("metric_binding")
        pm["missing_aspects"] = miss
        amb = qs.get("__metric_binding_ambiguous__") or {}
        bindings = amb.get("bindings") if isinstance(amb, dict) else []
        choices = []
        for b in bindings or []:
            if not isinstance(b, dict):
                continue
            code = str(b.get("data_acct_code") or "").strip()
            name = str(b.get("data_acct_name") or "").strip()
            scope = str(b.get("scope_code") or "").strip()
            if code or name:
                choices.append(f"{code}｜{name}（{scope}）")
        pm["clarification_message"] = (
            "已识别到同一叶子指标存在多个可用机构及产品指标编码，请先选择具体指标编码后再执行查询。\n"
            + "\n".join(f"- {x}" for x in choices[:8])
        ).strip()
        return pm

    if _needs_fine_interest_income_data_account(query) and not (_has_data_account_code(qs) or _has_metric_node(qs)):
        pm["route"] = "data_query_incomplete"
        miss = [str(x) for x in (pm.get("missing_aspects") or []) if x]
        if "metric_scope" not in miss:
            miss.append("metric_scope")
        pm["missing_aspects"] = miss
        if not str(pm.get("clarification_message") or "").strip():
            pm["clarification_message"] = (
                "您提到「利息收入」类细项：本系统在报告较粗层级多为「净利息收入」等汇总；"
                "若要看**细分利息收入**，请在机构及产品指标中指定具体 code（如清单中对应指标），"
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

    append_section("指标树节点", "metric_nodes")
    append_section("机构及产品指标编码", "data_accounts")
    append_section("部门科目", "departments")
    append_section("机构及产品", "products")
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


def _iter_metric_payload_nodes(metrics: Any) -> list[dict[str, Any]]:
    if not isinstance(metrics, list):
        return []
    rows: list[dict[str, Any]] = []
    stack = [item for item in metrics if isinstance(item, dict)]
    while stack:
        node = stack.pop(0)
        rows.append(node)
        children = node.get("children")
        if isinstance(children, list):
            stack[0:0] = [child for child in children if isinstance(child, dict)]
    return rows


def _confirmed_org_product_metric_digest_rows(
    cur: sqlite3.Cursor,
    *,
    limit: int = 800,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    try:
        source_rows = cur.execute(
            """
            SELECT node_code, node_name, product_code, metric_table_name, value_type
            FROM data_account_metric_node
            WHERE is_active = 1
              AND runtime_account_enabled = 1
              AND COALESCE(product_code, '') <> ''
              AND COALESCE(metric_table_name, '') <> ''
            ORDER BY product_code, metric_table_name, node_code
            """
        ).fetchall()
    except sqlite3.Error:
        return []

    for source in source_rows:
        entity_code = str(source["product_code"] or "").strip().upper()
        table_name = str(source["metric_table_name"] or "").strip()
        data_ref = str(source["node_code"] or "").strip().upper()
        if not entity_code or not table_name or not data_ref:
            continue
        key = (entity_code, table_name, data_ref)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "entity_code": entity_code,
                "table_name": table_name,
                "source_code": data_ref,
                "metric_node_code": data_ref,
                "data_acct_code": data_ref,
                "name": str(source["node_name"] or data_ref).strip(),
                "value_type": str(source["value_type"] or "").strip() or "金额",
            }
        )
        if len(rows) >= limit:
            return rows
    return rows


def build_catalog_digest(common_db: Path, *, max_chars: int | None = 14_000) -> str:
    """从 common.db 生成机构及产品指标/部门/产品摘要；超长时截断并保留统计头。"""
    if not common_db.exists():
        return "（当前环境未找到 common.db，无法加载科目清单。）"

    lines: list[str] = []
    try:
        conn = sqlite3.connect(common_db)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        nc = cur.execute("SELECT COUNT(*) FROM data_account_metric_node WHERE is_active = 1").fetchone()[0]
        bc = cur.execute("SELECT COUNT(*) FROM data_account_metric_binding WHERE is_active = 1").fetchone()[0]
        dc = cur.execute("SELECT COUNT(*) FROM data_account").fetchone()[0]
        dec = cur.execute("SELECT COUNT(*) FROM dept_account").fetchone()[0]
        pc = cur.execute(
            f"""
            {org_product_runtime_products_cte()}
            SELECT COUNT(*)
            FROM org_product_runtime_products
            WHERE product_code <> '' AND product_name <> ''
            """
        ).fetchone()[0]
        lines.append(
            f"【统计】指标节点 {nc} 条；指标绑定 {bc} 条；运行取数编码 {dc} 条；部门科目 {dec} 条；"
            f"机构及产品节点 {pc} 条。"
        )
        confirmed_metric_rows = _confirmed_org_product_metric_digest_rows(cur)
        lines.append("【机构及产品指标编码】指标编码|名称|值类型|产品/机构|表名|运行取数编码（AI 自动取指标优先使用，节选）")
        for row in confirmed_metric_rows:
            metric_code = row["source_code"] or row["data_acct_code"]
            lines.append(
                "  "
                f"{metric_code}|{row['name']}|{row['value_type']}|"
                f"{row['entity_code']}|{row['table_name']}|{row['data_acct_code']}"
            )

        lines.append("【部门科目】代码|名称|层级（节选）")
        for row in cur.execute(
            "SELECT dept_code, dept_name, level FROM dept_account ORDER BY dept_code LIMIT 400"
        ):
            lines.append(f"  {row['dept_code']}|{row['dept_name']}|{row['level']}")

        lines.append("【机构及产品】代码|名称（节选）")
        for row in cur.execute(
            f"""
            {org_product_runtime_products_cte()}
            SELECT product_code, product_name
            FROM org_product_runtime_products
            WHERE product_code <> '' AND product_name <> ''
            ORDER BY product_code
            LIMIT 400
            """
        ):
            lines.append(f"  {row['product_code']}|{row['product_name']}")

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
    p = _normalise_current_query_axes(pending_query_spec)
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
    if not has_metric and not (p.get("metric_nodes") or p.get("data_accounts") or p.get("query_focus")):
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
        "metric_nodes": p.get("metric_nodes") or [],
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
    for a in query_spec.get("metric_nodes") or []:
        if isinstance(a, dict):
            c = str(a.get("code") or "").strip()
            n = str(a.get("name") or "").strip()
            acct_bits.append(f"指标:{n}({c})" if c else f"指标:{n}")
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
        "metric_nodes": query_spec.get("metric_nodes") or [],
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
