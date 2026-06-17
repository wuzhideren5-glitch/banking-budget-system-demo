"""Agent domain lexicon for budget intent routing."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from app.knowledge_base import KnowledgeBaseService
from app.services.org_product_metric_runtime_snapshot import load_org_product_metric_table_rows_from_runtime_tree
from app.services.org_product_runtime_catalog import org_product_runtime_products_cte
from app.services.runtime_metric_refs import derive_runtime_ref_from_org_product_metric_code


WEAK_BUDGET_TERMS = {
    "预算",
    "实际",
    "预实",
    "收入",
    "利息",
    "费用",
    "利润",
    "nim",
    "roe",
    "预算执行",
    "预算差异",
    "预算编制",
    "预算汇总",
    "预算明细",
    "支行",
    "存款",
    "资产",
    "负债",
    "月度",
    "季度",
    "年度",
    "趋势",
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
    "部门科目",
    "指标节点",
    "机构及产品指标",
    "机构及产品指标编码",
    "一级部门",
    "二级部门",
    "三级部门",
    "信贷业务",
    "信贷",
    "贷款业务",
    "经营请款",
    "经营预算",
    "预算管控",
    "预算执行进度",
    "预算偏差",
    "预算口径",
    "财务口径",
    "业务口径",
    "授信",
    "授信规模",
    "贷款规模",
    "贷款余额",
    "贷款收益率",
    "净息差",
    "净利差",
    "风险成本",
    "拨备",
    "拨备覆盖率",
    "不良贷款",
    "不良率",
    "迁徙率",
    "核销",
    "回收",
    "资产负债",
    "资产结构",
    "负债结构",
    "资本占用",
    "资本充足率",
    "流动性",
    "久期",
    "ftp",
    "内部资金转移定价",
    "手续费收入",
    "利息收入",
    "利息支出",
    "营业收入",
    "营业成本",
    "业务及管理费",
    "税金及附加",
    "净利润",
    "条线预算",
    "条线经营",
    "普惠业务",
    "个金业务",
    "对公业务",
    "小微业务",
    "零售业务",
    "司库",
    "同业业务",
    "存贷比",
    "资产收益率",
    "成本收入比",
}

GENERIC_STRONG_STOP_WORDS = {"系统", "数据", "数据库", "分析", "管理", "银行", "预算"}
SYNONYM_FIELDS = ("term", "normalized_name", "normalized_code")
DATA_DICTIONARY_FIELDS = ("entity_code", "entity_name", "entity_type")
CURRENT_ENTITY_SQLS = (
    "SELECT dept_code AS code, dept_name AS name FROM dept_account",
    f"""
    {org_product_runtime_products_cte()}
    SELECT product_code AS code, product_name AS name
    FROM org_product_runtime_products
    WHERE product_code <> '' AND product_name <> ''
    """,
)
BUDGET_SUMMARY_LABEL_FIELDS = (
    "metric_level1",
    "metric_level2",
    "metric_level3",
    "dept_level1",
    "dept_level2",
    "dept_level3",
    "data_code_name",
    "product_code_name",
)


def normalize_for_match(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", (text or "").lower())


def is_valid_domain_term(term: str) -> bool:
    text = (term or "").strip()
    if len(text) < 2 or len(text) > 40:
        return False
    if re.fullmatch(r"\d+", text):
        return False
    return True


def char_ngrams(text: str, n: int = 2) -> set[str]:
    value = (text or "").strip()
    if not value:
        return set()
    if len(value) <= n:
        return {value}
    return {value[i : i + n] for i in range(0, len(value) - n + 1)}


def _add_normalized_fields(
    target: set[str],
    row: dict[str, Any],
    fields: tuple[str, ...],
) -> None:
    for field in fields:
        token = normalize_for_match(str(row.get(field, "")))
        if is_valid_domain_term(token):
            target.add(token)


def _load_mapping_terms(kb_service: KnowledgeBaseService) -> set[str]:
    terms: set[str] = set()
    mapping_path = kb_service.paths.root / "01_data_semantics" / "field_table_name_mapping_zh.json"
    if not mapping_path.exists():
        return terms
    try:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        for name in (mapping.get("table_name_mapping", {}) or {}).values():
            token = normalize_for_match(str(name))
            if is_valid_domain_term(token):
                terms.add(token)
        for name in (mapping.get("field_name_mapping", {}) or {}).values():
            token = normalize_for_match(str(name))
            if is_valid_domain_term(token):
                terms.add(token)
    except Exception:
        return terms
    return terms


def _load_current_entity_terms(common_path: Path) -> set[str]:
    terms: set[str] = set()
    if not common_path.exists():
        return terms
    try:
        with sqlite3.connect(common_path) as conn:
            conn.row_factory = sqlite3.Row
            for sql in CURRENT_ENTITY_SQLS:
                for row in conn.execute(sql).fetchall():
                    code = normalize_for_match(str(row["code"] or ""))
                    name = normalize_for_match(str(row["name"] or ""))
                    if is_valid_domain_term(code):
                        terms.add(code)
                    if is_valid_domain_term(name):
                        terms.add(name)
    except Exception:
        return terms
    return terms


def _org_product_children(metric: dict[str, Any]) -> list[dict[str, Any]]:
    children = metric.get("children")
    return [item for item in children if isinstance(item, dict)] if isinstance(children, list) else []


def _load_org_product_metric_terms(common_path: Path) -> set[str]:
    terms: set[str] = set()
    if not common_path.exists():
        return terms
    try:
        with sqlite3.connect(common_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = load_org_product_metric_table_rows_from_runtime_tree(conn)
    except Exception:
        return terms

    for row in rows:
        entity_code = str(row["entity_code"] or "").strip().upper()
        table_name = str(row["table_name"] or "").strip()
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except Exception:
            continue
        metrics = payload.get("metrics")
        stack = [item for item in metrics if isinstance(item, dict)] if isinstance(metrics, list) else []
        while stack:
            metric = stack.pop(0)
            stack.extend(_org_product_children(metric))
            metric_code = str(metric.get("code") or "").strip()
            runtime_ref = derive_runtime_ref_from_org_product_metric_code(
                entity_code=entity_code,
                metric_code=metric_code,
            )
            if not runtime_ref:
                continue
            fields = [
                entity_code,
                table_name,
                metric_code,
                metric.get("name"),
                runtime_ref,
            ]
            for field in fields:
                token = normalize_for_match(str(field or ""))
                if is_valid_domain_term(token):
                    terms.add(token)
            metric_code = normalize_for_match(str(metric.get("code") or ""))
            source_ref = normalize_for_match(f"{entity_code}{table_name}{metric_code}")
            if is_valid_domain_term(source_ref):
                terms.add(source_ref)
    return terms


def _load_budget_summary_terms(budget_path: Path) -> set[str]:
    terms: set[str] = set()
    if not budget_path.exists():
        return terms
    try:
        with sqlite3.connect(budget_path) as conn:
            for field in BUDGET_SUMMARY_LABEL_FIELDS:
                sql = (
                    f"SELECT DISTINCT {field} AS v FROM budget_summary "
                    f"WHERE {field} IS NOT NULL AND TRIM({field}) != '' LIMIT 2000"
                )
                for row in conn.execute(sql).fetchall():
                    token = normalize_for_match(str(row[0] or ""))
                    if is_valid_domain_term(token):
                        terms.add(token)
    except Exception:
        return terms
    return terms


def _build_semantic_budget_corpus(seed_terms: set[str]) -> list[dict[str, Any]]:
    corpus: list[dict[str, Any]] = []
    for term in sorted(seed_terms):
        grams = char_ngrams(term)
        if grams:
            corpus.append({"term": term, "grams": grams})
    return corpus


@dataclass(frozen=True)
class AgentDomainLexicon:
    strong_terms: set[str]
    weak_terms: set[str]
    semantic_budget_corpus: list[dict[str, Any]]

    @classmethod
    def load(
        cls,
        *,
        kb_service: KnowledgeBaseService,
        common_db: Path,
        budget_db: Path,
    ) -> "AgentDomainLexicon":
        strong: set[str] = set()
        weak = {normalize_for_match(term) for term in WEAK_BUDGET_TERMS}

        try:
            for row in kb_service.read_current_synonym_rows():
                _add_normalized_fields(strong, row, SYNONYM_FIELDS)
        except Exception:
            pass

        try:
            for row in kb_service.read_data_semantics_rows():
                _add_normalized_fields(strong, row, DATA_DICTIONARY_FIELDS)
        except Exception:
            pass

        weak.update(_load_mapping_terms(kb_service))
        strong.update(_load_current_entity_terms(common_db))
        strong.update(_load_org_product_metric_terms(common_db))
        strong.update(_load_budget_summary_terms(budget_db))

        for stop_word in GENERIC_STRONG_STOP_WORDS:
            strong.discard(normalize_for_match(stop_word))
        weak = {term for term in weak if is_valid_domain_term(term)}
        strong = {term for term in strong if is_valid_domain_term(term)}

        corpus_terms = set(strong)
        corpus_terms.update(weak)
        return cls(
            strong_terms=strong,
            weak_terms=weak,
            semantic_budget_corpus=_build_semantic_budget_corpus(corpus_terms),
        )

    def domain_hit_profile(self, text: str) -> dict[str, int]:
        query = normalize_for_match((text or "").strip())
        if not query:
            return {"strong_hits": 0, "weak_hits": 0}
        strong_hits = sum(1 for term in self.strong_terms if term and term in query)
        weak_hits = sum(1 for term in self.weak_terms if term and term in query)
        return {"strong_hits": strong_hits, "weak_hits": weak_hits}

    def semantic_budget_retrieve(self, query: str) -> dict[str, Any]:
        normalized_query = normalize_for_match(query)
        if not normalized_query:
            return {"score": 0.0, "top_matches": []}
        query_grams = char_ngrams(normalized_query)
        if not query_grams:
            return {"score": 0.0, "top_matches": []}

        ranked: list[tuple[float, str]] = []
        for item in self.semantic_budget_corpus:
            term = item["term"]
            grams = item["grams"]
            if not term or not grams:
                continue
            if len(term) >= 2 and term in normalized_query:
                score = 0.99
            else:
                inter = len(query_grams & grams)
                if inter == 0:
                    continue
                score = (2.0 * inter) / (len(query_grams) + len(grams))
            ranked.append((float(score), term))

        ranked.sort(key=lambda x: x[0], reverse=True)
        top_matches = ranked[:5]
        max_score = top_matches[0][0] if top_matches else 0.0
        return {
            "score": round(max_score, 4),
            "top_matches": [
                {"term": term, "score": round(score, 4)}
                for score, term in top_matches
            ],
        }
