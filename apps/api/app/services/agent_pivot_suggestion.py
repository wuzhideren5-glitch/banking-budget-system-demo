"""Pivot suggestion builders for Agent budget analysis."""
from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from app.metric_tree_paths import metric_display_level
from app.services.agent_analysis_filters import norm_code_name_list
from app.services.agent_compare_version import current_compare_show_level_version


def metric_anchor_level_from_pm(
    pm_query_spec: Mapping[str, Any] | None,
    *,
    common_db: Path,
) -> int | None:
    """
    Return the shallowest display level locked by metric_nodes.
    Multi-metric locks expand rows from this level to L5 + data account.
    """
    if not isinstance(pm_query_spec, Mapping) or not common_db.is_file():
        return None
    levels: list[int] = []
    try:
        with sqlite3.connect(str(common_db)) as conn:
            cur = conn.cursor()
            for item in pm_query_spec.get("metric_nodes") or []:
                if not isinstance(item, Mapping):
                    continue
                code = str(item.get("code") or "").strip()
                name = str(item.get("name") or "").strip()
                row = None
                if code:
                    cur.execute(
                        "SELECT node_code, level FROM data_account_metric_node WHERE node_code = ? AND is_active = 1",
                        (code,),
                    )
                    row = cur.fetchone()
                elif name:
                    cur.execute(
                        "SELECT node_code, level FROM data_account_metric_node WHERE node_name = ? AND is_active = 1",
                        (name,),
                    )
                    row = cur.fetchone()
                if row is not None:
                    level = metric_display_level(str(row[0] or ""), int(row[1] or 0))
                    if 1 <= level <= 5:
                        levels.append(level)
    except Exception:
        return None
    return min(levels) if levels else None


def pivot_search_codes_from_pm(pm_query_spec: Mapping[str, Any] | None) -> str:
    """Return metric/data-account codes for the pivot search box OR filter."""
    if not isinstance(pm_query_spec, Mapping):
        return ""
    out: list[str] = []
    seen: set[str] = set()
    for key in ("metric_nodes", "data_accounts"):
        for item in pm_query_spec.get(key) or []:
            if not isinstance(item, Mapping):
                continue
            code = str(item.get("code") or "").strip()
            if code and code not in seen:
                seen.add(code)
                out.append(code)
    return " ".join(out)


def first_locked_dim_token(entries: Any) -> str:
    """Prefer name, then code, for frontend fuzzy page-field matching."""
    if not isinstance(entries, list):
        return ""
    for item in entries:
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or "").strip()
        if name:
            return name
        if code:
            return code
    return ""


def version_selection_token_from_query(query: str, query_version_id: int) -> str:
    """
    Token for frontend version_display fuzzy matching.
    Prefer an explicit version in the query, then the resolved context version.
    """
    q = query or ""
    match = re.search(r"(?:版本(?:号|id)?|version)\s*[:：#]?\s*(\d{1,8})", q, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"\bV\s*[:：#]?\s*(\d{1,8})\b", q, flags=re.IGNORECASE)
    if match:
        return f"版本号：{int(match.group(1))}"
    if int(query_version_id or 0) > 0:
        return f"版本号：{int(query_version_id)}"
    return "全部"


def version_selection_token_from_id(query_version_id: int) -> str:
    if int(query_version_id or 0) > 0:
        return f"版本号：{int(query_version_id)}"
    return "全部"


def pivot_suggestion_row_field_ids(
    pm_query_spec: Mapping[str, Any] | None,
    query: str,
    *,
    common_db: Path,
) -> list[str]:
    spec = pm_query_spec if isinstance(pm_query_spec, Mapping) else {}
    anchor = metric_anchor_level_from_pm(spec, common_db=common_db)
    if anchor is not None:
        return [f"metric_level{i}" for i in range(anchor, 6)] + ["data_code_name"]
    if norm_code_name_list(spec.get("data_accounts")):
        return ["data_code_name"]
    if norm_code_name_list(spec.get("departments")):
        return ["dept_level1", "dept_level2", "dept_level3"]
    if norm_code_name_list(spec.get("products")):
        return ["product_code_name"]
    return [f"metric_level{i}" for i in range(1, 6)] + ["data_code_name"]


def pivot_suggestion_column_field_ids(query: str, clarified_slots: Mapping[str, Any] | None) -> list[str]:
    slots = clarified_slots if isinstance(clarified_slots, Mapping) else {}
    granularity = str(slots.get("granularity", "") or "")
    if "quarter" in granularity or re.search(r"(按季|季度)", query):
        return ["quarter", "budget_actual"]
    if ("year" in granularity or re.search(r"(按年|各年度|分年|年度汇总|多年度)", query)) and not re.search(
        r"(按月|每月|分月|月度|月份|近.*个月|未来.*个月)", query
    ):
        return ["year", "budget_actual"]
    return ["month", "budget_actual"]


def pivot_suggestion_page_field_ids(pm_query_spec: Mapping[str, Any] | None) -> list[str]:
    spec = pm_query_spec if isinstance(pm_query_spec, Mapping) else {}
    page_fields: list[str] = ["year", "version_display"]
    if norm_code_name_list(spec.get("departments")):
        page_fields.extend(["dept_level1", "dept_level2", "dept_level3"])
    if norm_code_name_list(spec.get("products")):
        page_fields.append("product_code_name")
    return list(dict.fromkeys(page_fields))


def normalize_dept_token_for_pivot(token: str) -> str:
    text = re.sub(r"\s+", "", str(token or "").strip())
    if not text:
        return ""
    for suffix in ("部门", "事业部", "业务条线", "条线", "部"):
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


def build_pivot_suggestion(
    state: Mapping[str, Any],
    *,
    runtime_config: Mapping[str, Any] | None,
    common_db: Path,
    current_year: int,
) -> dict[str, Any] | None:
    if str(state.get("intent_type", "general")) != "budget":
        return None
    if str(state.get("budget_query_kind", "analysis") or "analysis") != "analysis":
        return None

    query = str(state.get("user_query", "") or "")
    clarified = state.get("clarified_slots") if isinstance(state.get("clarified_slots"), Mapping) else {}
    pm = state.get("pm_query_spec") if isinstance(state.get("pm_query_spec"), Mapping) else {}
    row_field_ids = pivot_suggestion_row_field_ids(pm, query, common_db=common_db)
    column_field_ids = pivot_suggestion_column_field_ids(query, clarified)
    page_field_ids = pivot_suggestion_page_field_ids(pm)
    value_field_ids = ["value"]
    query_year = int(state.get("query_db_year") or current_year)
    query_version_id = int(state.get("query_version_id") or 0)
    query_base_version_id = int(state.get("query_base_version_id") or 0)
    data_source = str(state.get("query_data_source") or "budget")
    show_level = int(state.get("query_show_level") or 1)
    base_year_tag = str(state.get("query_base_year_tag") or "").strip()
    if data_source == "compare_l1" and query_version_id <= 0:
        query_version_id = current_compare_show_level_version(
            common_db=common_db,
            show_level=show_level if show_level > 0 else 1,
        )
    year_tag = str(state.get("query_year_tag") or "").strip() or f"Y{query_year}"
    if data_source == "compare_l1":
        if base_year_tag:
            year_tag = base_year_tag
        if query_base_version_id > 0:
            query_version_id = query_base_version_id
    dept_token = first_locked_dim_token(pm.get("departments") if isinstance(pm, Mapping) else None)
    dept_token = normalize_dept_token_for_pivot(dept_token)
    product_token = first_locked_dim_token(pm.get("products") if isinstance(pm, Mapping) else None)
    page_selections: dict[str, str] = {
        "year": year_tag,
        "version_display": (
            version_selection_token_from_id(query_version_id)
            if data_source == "compare_l1"
            else version_selection_token_from_query(query, query_version_id)
        ),
    }
    if dept_token:
        for dept_field in ("dept_level1", "dept_level2", "dept_level3"):
            if dept_field in page_field_ids:
                page_selections[dept_field] = dept_token
    if product_token:
        page_selections["product_code_name"] = product_token

    pivot_cfg = runtime_config.get("pivot", {}) if isinstance(runtime_config, Mapping) else {}
    base_conf = float(pivot_cfg.get("base_confidence", 0.6))
    pivot_search_text = pivot_search_codes_from_pm(pm)
    confidence = min(0.95, base_conf + 0.1 + (0.04 if pivot_search_text else 0.0))
    reason_bits = [
        "行按已锁指标树最浅层展开到末级+机构及产品指标编码（或仅指标/部门/产品）",
        "列为时间 + 预算/实际",
        "页为年度 + 版本号及名称（并按已锁部门/产品自动加页筛选）",
    ]
    if pivot_search_text:
        reason_bits.append("已预填指标/数据 code 到透视搜索框")
    explanation = (
        f"建议使用「多年度对比透视表」：行（{' 、'.join(row_field_ids)}），"
        f"列（{' 、'.join(column_field_ids)}），页（{' 、'.join(page_field_ids)}），值 value。"
    )
    explanation = f"{explanation} 说明：{';'.join(reason_bits)}。"
    if pivot_search_text:
        explanation = f"{explanation} 预填 code：{pivot_search_text}"
    return {
        "row_field_ids": row_field_ids,
        "column_field_ids": column_field_ids,
        "page_field_ids": page_field_ids,
        "value_field_ids": value_field_ids,
        "page_selections": page_selections,
        "pivot_search_text": pivot_search_text,
        "explanation": explanation,
        "confidence": round(max(confidence, 0.0), 2),
    }


def should_recommend_pivot(
    state: Mapping[str, Any],
    pivot_suggestion: Mapping[str, Any] | None,
    *,
    pivot_config: Mapping[str, Any] | None = None,
) -> bool:
    if not pivot_suggestion:
        return False
    cfg = pivot_config if isinstance(pivot_config, Mapping) else {}
    recommend_all_analysis = bool(cfg.get("recommend_all_analysis", True))
    if recommend_all_analysis and str(state.get("budget_query_kind", "analysis") or "analysis") == "analysis":
        return True
    if bool(state.get("prefer_pivot_view", False)):
        return True
    if str(state.get("budget_query_kind", "analysis") or "analysis") != "analysis":
        return False
    query = str(state.get("user_query", "") or "")
    score = 0
    if re.search(r"(按月|按季|按年|趋势|同比|环比)", query):
        score += 1
    if re.search(r"(部门|产品|科目|分布|结构|对比|差异)", query):
        score += 1
    if re.search(r"(预算.?实际|预实|版本)", query):
        score += 1
    min_score = int(cfg.get("recommend_min_score", 2))
    min_conf = float(cfg.get("recommend_min_confidence", 0.72))
    conf = float(pivot_suggestion.get("confidence", 0.0) or 0.0)
    return score >= min_score or conf >= min_conf


def build_plan_reply_options(state: Mapping[str, Any], *, recommend_pivot: bool) -> list[dict[str, str]]:
    """Return next-step buttons after query planning."""
    sql_opt = {"id": "sql_query", "label": "1）执行只读 SQL 查询（按当前规划口径）"}
    query_kind = str(state.get("budget_query_kind", "analysis") or "analysis")
    if query_kind == "metadata" or not recommend_pivot:
        return [sql_opt]
    pivot_opt = {"id": "open_pivot_table", "label": "2）打开数据透视表，自行拖拽行列与筛选查看"}
    both_opt = {
        "id": "sql_and_pivot",
        "label": "3）两者都做：执行 SQL 并打开数据透视表",
    }
    if bool(state.get("prefer_pivot_view", False)):
        return [pivot_opt, both_opt, sql_opt]
    return [sql_opt, pivot_opt, both_opt]


def append_reply_options_footer(reply: str, options: list[dict[str, str]]) -> str:
    if not options:
        return reply
    lines = "\n".join(f"{option.get('label', '')}" for option in options if option.get("label"))
    return (
        f"{reply.rstrip()}\n\n"
        "---\n"
        "**请选择下一步：**\n"
        f"{lines}\n\n"
        "你也可以使用本条回复下方的按钮直接操作。"
    )
