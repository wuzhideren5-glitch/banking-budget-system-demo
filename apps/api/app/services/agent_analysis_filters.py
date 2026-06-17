"""SQL filter helpers for Agent budget analysis read models."""
from __future__ import annotations

from datetime import date, timedelta
import re
from typing import Any, Mapping


def sql_escape_literal(value: str) -> str:
    return (value or "").replace("'", "''")


def norm_code_name_list(items: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or "").strip()
        if not code and not name:
            continue
        out.append({"code": code, "name": name})
    return out


def text_match_or_sql(field_expr: str, terms: list[str]) -> str:
    cleaned: list[str] = []
    seen: set[str] = set()
    for term in terms:
        value = str(term or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    if not cleaned:
        return ""
    conds = [f"INSTR({field_expr}, '{sql_escape_literal(term)}') > 0" for term in cleaned]
    return " AND (" + " OR ".join(conds) + ")"


def expand_org_terms(terms: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    suffixes = ("部门", "事业部", "业务条线", "条线", "部")
    for raw in terms:
        term = str(raw or "").strip()
        if not term:
            continue
        variants = {term}
        compact = re.sub(r"\s+", "", term)
        variants.add(compact)
        for suffix in suffixes:
            if compact.endswith(suffix) and len(compact) > len(suffix):
                variants.add(compact[: -len(suffix)])
        for variant in variants:
            if not variant or variant in seen:
                continue
            seen.add(variant)
            out.append(variant)
    return out


def compare_scope_from_query(query: str) -> str:
    q = query or ""
    conds: list[str] = []
    for keyword in ("车车贷", "开鑫贷", "企企贷", "企小乐", "开心小账户", "金市", "司库"):
        if keyword in q:
            conds.append(f"INSTR(IFNULL(product_code_name,''), '{keyword}') > 0")
            break
    loanish = (
        "贷款" in q
        or ("信贷" in q and "信用卡" not in q)
        or "授信" in q
        or "放贷款" in q
    )
    if re.search(r"(贷款规模|管理贷款|贷款日均|规模日均|余额|日均|规模)", q):
        conds.append(
            "(INSTR(IFNULL(data_code_name,''), '日均') > 0 "
            "OR INSTR(IFNULL(data_code_name,''), '管理贷款') > 0 "
            "OR INSTR(IFNULL(data_code_name,''), '贷款') > 0 "
            "OR INSTR(IFNULL(data_code_name,''), '信贷') > 0)"
        )
    elif loanish and "存款" not in q:
        conds.append(
            "(INSTR(IFNULL(data_code_name,''), '贷款') > 0 "
            "OR INSTR(IFNULL(data_code_name,''), '信贷') > 0)"
        )
    if not conds:
        return ""
    return " AND " + " AND ".join(conds)


def dimension_filters_from_pm_query_spec(pm_query_spec: dict[str, Any] | None) -> str:
    if not isinstance(pm_query_spec, dict):
        return ""

    data_entries = norm_code_name_list(pm_query_spec.get("data_accounts"))
    dept_entries = norm_code_name_list(pm_query_spec.get("departments"))
    product_entries = norm_code_name_list(pm_query_spec.get("products"))

    data_terms: list[str] = []
    for entry in data_entries:
        if entry["code"]:
            data_terms.append(entry["code"])
        if entry["name"]:
            data_terms.append(entry["name"])

    dept_terms: list[str] = []
    for entry in dept_entries:
        if entry["code"]:
            dept_terms.append(entry["code"])
        if entry["name"]:
            dept_terms.append(entry["name"])
    dept_terms = expand_org_terms(dept_terms)

    product_terms: list[str] = []
    for entry in product_entries:
        if entry["code"]:
            product_terms.append(entry["code"])
        if entry["name"]:
            product_terms.append(entry["name"])

    data_expr = "IFNULL(data_code_name,'')"
    dept_expr = "IFNULL(dept_level1,'')||IFNULL(dept_level2,'')||IFNULL(dept_level3,'')"
    product_expr = "IFNULL(product_code_name,'')"

    return "".join(
        [
            text_match_or_sql(data_expr, data_terms),
            text_match_or_sql(dept_expr, dept_terms),
            text_match_or_sql(product_expr, product_terms),
        ]
    )


def pm_has_metric_lock(pm_query_spec: dict[str, Any] | None) -> bool:
    if not isinstance(pm_query_spec, dict):
        return False
    metric_entries = pm_query_spec.get("metric_nodes")
    data_entries = pm_query_spec.get("data_accounts")
    return bool(isinstance(metric_entries, list) and metric_entries) or bool(
        isinstance(data_entries, list) and data_entries
    )


def pm_metric_locked_without_data(pm_query_spec: dict[str, Any] | None) -> bool:
    if not isinstance(pm_query_spec, dict):
        return False
    metric_entries = pm_query_spec.get("metric_nodes")
    data_entries = pm_query_spec.get("data_accounts")
    has_metric = bool(isinstance(metric_entries, list) and metric_entries)
    has_data = bool(isinstance(data_entries, list) and data_entries)
    return has_metric and not has_data


def pm_metric_scope_label(pm_query_spec: dict[str, Any] | None) -> str:
    if not isinstance(pm_query_spec, dict):
        return ""
    metrics = pm_query_spec.get("metric_nodes")
    if not isinstance(metrics, list) or not metrics:
        return ""
    first = metrics[0] if isinstance(metrics[0], dict) else {}
    code = str(first.get("code") or "").strip()
    name = str(first.get("name") or "").strip()
    if code and name:
        return f"{code} {name}"
    return code or name


def pm_dimension_terms(pm_query_spec: dict[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(pm_query_spec, dict):
        return {"metric": [], "data": [], "dept": [], "product": []}
    out: dict[str, list[str]] = {"metric": [], "data": [], "dept": [], "product": []}
    mapping = {
        "metric_nodes": "metric",
        "data_accounts": "data",
        "departments": "dept",
        "products": "product",
    }
    for src_key, dst_key in mapping.items():
        for entry in norm_code_name_list(pm_query_spec.get(src_key)):
            if entry["code"]:
                out[dst_key].append(entry["code"])
            if entry["name"]:
                out[dst_key].append(entry["name"])
    for key, values in out.items():
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        out[key] = deduped
    return out


def sql_missing_pm_dimensions(sql: str, pm_query_spec: dict[str, Any] | None) -> list[str]:
    terms = pm_dimension_terms(pm_query_spec)
    missing: list[str] = []
    sql_text = sql or ""
    labels = {
        "metric": "指标节点",
        "data": "机构及产品指标编码",
        "dept": "部门科目",
        "product": "机构及产品",
    }
    for dim_key in ("metric", "data", "dept", "product"):
        dim_terms = terms.get(dim_key) or []
        if not dim_terms:
            continue
        covered = any(f"'{sql_escape_literal(term)}'" in sql_text for term in dim_terms)
        if not covered:
            missing.append(labels[dim_key])
    return missing


def dept_filter_sql(pm_query_spec: dict[str, Any] | None, query: str) -> str:
    conds: list[str] = []
    pm_has_departments = False
    if isinstance(pm_query_spec, dict):
        pm_depts = pm_query_spec.get("departments") or []
        pm_has_departments = bool(isinstance(pm_depts, list) and pm_depts)
        raw_terms: list[str] = []
        for dept in pm_depts:
            if not isinstance(dept, dict):
                continue
            code = str(dept.get("code") or "").strip()
            name = str(dept.get("name") or "").strip()
            if code:
                raw_terms.append(code)
            if name:
                raw_terms.append(name)
        for name in expand_org_terms(raw_terms):
            if len(name) < 2:
                continue
            literal = sql_escape_literal(name)
            conds.append(
                f"INSTR(IFNULL(dept_level1,'')||IFNULL(dept_level2,'')||IFNULL(dept_level3,''), '{literal}') > 0"
            )
    if pm_has_departments:
        return ""

    q = query or ""
    if not conds:
        if re.search(r"(企业金融|企金)(?!城)", q) or "企业金融部" in q:
            conds.append(
                "INSTR(IFNULL(dept_level1,'')||IFNULL(dept_level2,'')||IFNULL(dept_level3,''), '企业金融') > 0"
            )
        elif "个金" in q or "个人金融" in q or "个人金融部" in q:
            conds.append(
                "INSTR(IFNULL(dept_level1,'')||IFNULL(dept_level2,'')||IFNULL(dept_level3,''), '个人金融') > 0"
            )
        elif "普惠金融" in q or (re.search(r"小微(?!型|企业信用信息)", q) and "信用卡" not in q):
            conds.append(
                "INSTR(IFNULL(dept_level1,'')||IFNULL(dept_level2,'')||IFNULL(dept_level3,''), '普惠') > 0"
            )
    if not conds:
        return ""
    return " AND (" + " OR ".join(conds) + ")"


def recent_n_complete_month_tags(n: int, *, today: date | None = None) -> list[tuple[str, str]]:
    tags: list[tuple[str, str]] = []
    current = (today or date.today()).replace(day=1)
    for _ in range(max(1, n)):
        prev_month_end = current - timedelta(days=1)
        tags.append((f"Y{prev_month_end.year}", f"M{prev_month_end.month:02d}"))
        current = prev_month_end.replace(day=1)
    return tags


def zh_number_to_int(token: str) -> int | None:
    text = str(token or "").strip()
    if not text:
        return None
    mapping = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if text == "十":
        return 10
    if "十" in text:
        left, right = text.split("十", 1)
        if left == "":
            tens = 1
        else:
            left_value = mapping.get(left)
            if left_value is None:
                return None
            tens = left_value
        if right == "":
            ones = 0
        else:
            right_value = mapping.get(right)
            if right_value is None:
                return None
            ones = right_value
        return tens * 10 + ones
    if all(ch in mapping for ch in text):
        if len(text) == 1:
            return mapping[text]
        try:
            return int("".join(str(mapping[ch]) for ch in text))
        except Exception:
            return None
    return None


def recent_complete_month_window_n(period_desc: str) -> int | None:
    text = re.sub(r"\s+", "", str(period_desc or ""))
    if not text:
        return None
    if re.search(r"(最近|近)半年", text):
        return 6
    m_digit = re.search(r"(最近|近)(\d{1,2})个?月", text)
    if m_digit:
        n = int(m_digit.group(2))
        return n if 1 <= n <= 36 else None
    m_zh = re.search(r"(最近|近)([一二两三四五六七八九十]{1,3})个?月", text)
    if m_zh:
        n = zh_number_to_int(m_zh.group(2))
        if n is not None and 1 <= n <= 36:
            return n
    return None


def recent_n_complete_quarter_tags(n: int, *, today: date | None = None) -> list[tuple[str, str]]:
    tags: list[tuple[str, str]] = []
    current = today or date.today()
    year = current.year
    current_q = ((current.month - 1) // 3) + 1
    quarter = current_q - 1
    if quarter <= 0:
        quarter = 4
        year -= 1
    for _ in range(max(1, n)):
        tags.append((f"Y{year}", f"Q{quarter}"))
        quarter -= 1
        if quarter <= 0:
            quarter = 4
            year -= 1
    return tags


def recent_complete_quarter_window_n(period_desc: str) -> int | None:
    text = re.sub(r"\s+", "", str(period_desc or ""))
    if not text:
        return None
    m_digit = re.search(r"(最近|近)(\d{1,2})个?季(?:度)?", text)
    if m_digit:
        n = int(m_digit.group(2))
        return n if 1 <= n <= 12 else None
    m_zh = re.search(r"(最近|近)([一二两三四五六七八九十]{1,3})个?季(?:度)?", text)
    if m_zh:
        n = zh_number_to_int(m_zh.group(2))
        if n is not None and 1 <= n <= 12:
            return n
    if re.search(r"(最近|近)(一个|1个|一)?季(?:度)?", text):
        return 1
    return None


def pm_time_filter_sql(
    pm_query_spec: dict[str, Any] | None,
    *,
    today: date | None = None,
) -> str:
    if not isinstance(pm_query_spec, dict):
        return ""
    year_raw = str(pm_query_spec.get("year") or "").strip()
    quarter_raw = str(pm_query_spec.get("quarter") or "").strip().upper()
    month_raw = str(pm_query_spec.get("month") or "").strip().upper()
    period_desc = str(pm_query_spec.get("period_description") or "").strip()

    recent_q_n = recent_complete_quarter_window_n(period_desc)
    if recent_q_n is not None:
        year_quarters = recent_n_complete_quarter_tags(recent_q_n, today=today)
        by_year_q: dict[str, list[str]] = {}
        for year, quarter in year_quarters:
            by_year_q.setdefault(year, []).append(quarter)
        or_parts_q: list[str] = []
        for year, quarters in by_year_q.items():
            if year_raw and re.match(r"Y20\d{2}$", year_raw, flags=re.I) and year != year_raw.upper():
                continue
            quarter_in = ",".join(f"'{sql_escape_literal(quarter)}'" for quarter in quarters)
            or_parts_q.append(f"(year = '{sql_escape_literal(year)}' AND quarter IN ({quarter_in}))")
        if or_parts_q:
            return " AND (" + " OR ".join(or_parts_q) + ")"

    recent_n = recent_complete_month_window_n(period_desc)
    if recent_n is not None:
        year_months = recent_n_complete_month_tags(recent_n, today=today)
        by_year: dict[str, list[str]] = {}
        for year, month in year_months:
            by_year.setdefault(year, []).append(month)
        or_parts: list[str] = []
        for year, months in by_year.items():
            if year_raw and re.match(r"Y20\d{2}$", year_raw, flags=re.I) and year != year_raw.upper():
                continue
            month_in = ",".join(f"'{sql_escape_literal(month)}'" for month in months)
            or_parts.append(f"(year = '{sql_escape_literal(year)}' AND month IN ({month_in}))")
        if or_parts:
            return " AND (" + " OR ".join(or_parts) + ")"

    span = re.search(r"([1-9]|1[0-2])\s*月?\s*[-~到至]\s*([1-9]|1[0-2])\s*月", period_desc)
    if span:
        m1 = int(span.group(1))
        m2 = int(span.group(2))
        lo, hi = (m1, m2) if m1 <= m2 else (m2, m1)
        current = today or date.today()
        year = year_raw.upper() if re.match(r"Y20\d{2}$", year_raw, flags=re.I) else f"Y{current.year}"
        month_in = ",".join(f"'M{month:02d}'" for month in range(lo, hi + 1))
        return f" AND (year = '{sql_escape_literal(year)}' AND month IN ({month_in}))"

    conds: list[str] = []
    if year_raw and re.match(r"Y20\d{2}$", year_raw, flags=re.I):
        conds.append(f"year = '{sql_escape_literal(year_raw.upper())}'")
    if quarter_raw and re.match(r"Q[1-4]$", quarter_raw):
        conds.append(f"quarter = '{quarter_raw}'")
    if month_raw and re.match(r"M(0[1-9]|1[0-2])$", month_raw):
        conds.append(f"month = '{month_raw}'")

    if not conds:
        return ""
    return " AND " + " AND ".join(conds)


def analysis_fact_filters(
    state: Mapping[str, Any] | None,
    query: str,
    *,
    today: date | None = None,
) -> str:
    pm = state.get("pm_query_spec") if state is not None else None
    pm = pm if isinstance(pm, dict) else None
    pm_dim_filters = dimension_filters_from_pm_query_spec(pm)
    pm_time_filter = pm_time_filter_sql(pm, today=today)
    keyword_metric_filter = "" if pm_has_metric_lock(pm) else compare_scope_from_query(query)
    dept_fallback_filter = dept_filter_sql(pm, query)
    return f"{pm_dim_filters}{pm_time_filter}{keyword_metric_filter}{dept_fallback_filter}"
