from __future__ import annotations

import contextvars
from datetime import date, datetime, timedelta, timezone
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from app.deepseek_client import DeepseekClient
from app.agent_memory import ConversationMemoryStore
from app.agent_prompt_assets import get_product_manager_intent_assets
from app.agent_product_intent import (
    format_query_spec_locked_dimensions_block,
    incomplete_clarification_text,
    merge_reply_disclaimer,
    query_spec_to_requirement_override,
    run_product_manager_intent,
    run_product_manager_intent_rule_fallback,
    should_apply_pm_prefill,
)
from app.agent_query import ReadOnlySqlExecutor
from app.knowledge_base import KnowledgeBaseService
from app.db_paths import budget_db_path, common_db_path, compare_db_path
from app.config import settings

try:
    from langgraph.graph import END, START, StateGraph

    HAS_LANGGRAPH = True
except Exception:
    HAS_LANGGRAPH = False
    END = "__end__"
    START = "__start__"
    StateGraph = None


class AgentState(TypedDict, total=False):
    user_query: str
    history: list[dict[str, Any]]
    top_k: int
    intent_type: str
    kb_context: dict[str, Any]
    slot_status: dict[str, bool]
    missing_slots: list[str]
    clarification_options: dict[str, list[str]]
    assumptions: list[str]
    clarified_slots: dict[str, Any]
    clarification_rounds: int
    need_clarification: bool
    next_action: str
    suggested_sql: str | None
    wants_execute: bool
    inherit_history_slots: bool
    budget_query_kind: str
    prefer_pivot_view: bool
    executed_result: dict[str, Any] | None
    memory_id: str | None
    reply: str
    reply_options: NotRequired[list[dict[str, str]]]
    open_pivot_table: NotRequired[bool]
    pivot_suggestion: NotRequired[dict[str, Any] | None]
    pm_route: NotRequired[str | None]
    pm_query_spec: NotRequired[dict[str, Any] | None]
    pm_requirement_override: NotRequired[dict[str, Any] | None]
    dialogue_id: NotRequired[int]
    pending_query_spec_out: NotRequired[dict[str, Any] | None]
    query_db_path: NotRequired[str]
    query_db_year: NotRequired[int]
    query_version_id: NotRequired[int]
    query_version_source: NotRequired[str]
    query_data_source: NotRequired[str]
    query_show_level: NotRequired[int | None]
    query_base_show_level: NotRequired[int | None]
    query_compare_show_level: NotRequired[int | None]
    query_base_year_tag: NotRequired[str | None]
    query_compare_year_tag: NotRequired[str | None]
    query_base_version_id: NotRequired[int | None]
    query_compare_version_id: NotRequired[int | None]
    query_year_tag: NotRequired[str | None]
    query_month_tag: NotRequired[str | None]
    comparison_version_options: NotRequired[list[str]]
    is_lightweight_social: NotRequired[bool]
    lightweight_social_score: NotRequired[float]
    lightweight_social_signals: NotRequired[list[str]]


class AgentGraphService:
    def __init__(
        self,
        kb_service: KnowledgeBaseService,
        query_executor: ReadOnlySqlExecutor,
        memory_store: ConversationMemoryStore,
        deepseek_client: DeepseekClient | None = None,
        debug_trace_store: Any | None = None,
    ):
        self.kb_service = kb_service
        self.query_executor = query_executor
        self.memory_store = memory_store
        self.deepseek_client = deepseek_client
        self.debug_trace_store = debug_trace_store
        self._trace_context_var: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
            "agent_trace_context", default={}
        )
        self.runtime_config_path = self.kb_service.paths.root / "generated" / "agent_runtime_config.json"
        self.intent_router_config_path = self.kb_service.paths.root / "generated" / "intent_router_config.json"
        self.intent_trace_path = self.kb_service.paths.root / "generated" / "intent_router_trace.jsonl"
        self.runtime_config = self._load_runtime_config()
        self.intent_router_config = dict(self.runtime_config.get("intent_router", {}))
        strong_terms, weak_terms = self._build_domain_lexicon()
        self.domain_terms_strong = strong_terms
        self.domain_terms_weak = weak_terms
        self.semantic_budget_corpus = self._build_semantic_budget_corpus()
        self._graph = self._build_graph() if HAS_LANGGRAPH else None

    def _emit_llm_trace_event(
        self,
        *,
        purpose: str,
        input_data: dict[str, Any],
        output_text: str | None = None,
        error: str | None = None,
    ) -> None:
        if self.debug_trace_store is None:
            return
        ctx = self._trace_context_var.get() or {}
        try:
            self.debug_trace_store.append_event(
                {
                    "kind": "llm_call",
                    "session_id": str(ctx.get("session_id") or "unknown"),
                    "dialogue_id": int(ctx.get("dialogue_id") or 0),
                    "turn_id": str(ctx.get("turn_id") or ""),
                    "channel": str(ctx.get("channel") or "web"),
                    "user_query": str(ctx.get("user_query") or ""),
                    "purpose": purpose,
                    "model": str((self.deepseek_client.model if self.deepseek_client else "") or ""),
                    "input_full": input_data,
                    "output_full": output_text,
                    "error": error,
                }
            )
        except Exception:
            return

    @staticmethod
    def _default_runtime_config() -> dict[str, Any]:
        return {
            "intent_router": {
                "semantic_budget_threshold_high": 0.78,
                "semantic_budget_threshold_mid": 0.65,
                "enable_llm_arbiter": True,
                "trace_enabled": True,
                "trace_max_query_chars": 200,
            },
            "general_answer": {
                "temperature": 0.45,
                "max_tokens": 900,
                "enable_shorten": False,
                "shorten_target_ratio": 0.5,
                "shorten_min_chars": 90,
                "shorten_max_chars": 260,
            },
            "pivot": {
                "recommend_all_analysis": True,
                "recommend_min_score": 2,
                "recommend_min_confidence": 0.72,
                "auto_open_on_execute_when_preferred": True,
                "base_confidence": 0.6,
            },
            "product_manager_intent": {
                "enable": True,
                "history_decay": 0.7,
                "max_history_messages": 24,
            },
        }

    @staticmethod
    def _is_simple_greeting_query(query: str) -> bool:
        q = (query or "").strip().lower()
        if not q:
            return False
        # 若同句包含预算查询意图（如“你好，帮我看下本月预算差异”），不按纯问候处理。
        if AgentGraphService._looks_like_budget_query(q):
            return False
        qc = re.sub(r"[\s\.,，。!！?？~～:：;；、\-_]+", "", q)
        if not qc:
            return False
        greeting_patterns = [
            # 基础问候
            r"^(你好|您好|哈喽|嗨|hi|hello|hey|yo|早安|早上好|上午好|中午好|下午好|晚上好|晚安)$",
            # 在线确认/寒暄
            r"^(在吗|在不在|有人吗|忙吗|你忙吗|忙不忙|方便吗|有空吗|有空聊吗|在干嘛|干嘛呢)$",
            # 能力询问（常见首句）
            r"^(能咨询问题吗|可以咨询问题吗|可以问问题吗|能问问题吗|能聊聊吗|你是谁|你能干什么|你可以做什么)$",
            # 中文语境高频寒暄
            r"^(吃了吗|吃饭了吗|吃过了吗|饭吃了吗|辛苦了|辛苦啦|累不累|累了吗|今天怎么样|最近怎么样|最近还好吗|还好吗)$",
            # 加语气词变体
            r"^(你好呀|你好啊|您好呀|您好啊|哈喽呀|嗨呀|hi呀|hello呀|hey呀)$",
        ]
        return any(re.fullmatch(p, qc) is not None for p in greeting_patterns)

    @staticmethod
    def _is_greeting_then_budget_query(query: str) -> bool:
        """
        识别“前半句问候 + 后半句预算问题”。
        例如：早上好，帮我看企业金融近三个月净利息收入。
        """
        q = (query or "").strip()
        if not q:
            return False
        # 先快速判断整句是否预算域，避免误伤普通寒暄。
        if not AgentGraphService._looks_like_budget_query(q):
            return False
        # 按常见分隔符切片，允许前两片是问候，后续片段是预算问题。
        parts = [p.strip() for p in re.split(r"[，,。！？!?；;:：\n]+", q) if p.strip()]
        if len(parts) < 2:
            return False
        lead = parts[0]
        if not AgentGraphService._is_simple_greeting_query(lead):
            return False
        tail = " ".join(parts[1:]).strip()
        return bool(tail and AgentGraphService._looks_like_budget_query(tail))

    def _deep_update(self, base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v
        return base

    def _load_runtime_config(self) -> dict[str, Any]:
        cfg = self._default_runtime_config()
        try:
            path = self.runtime_config_path
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._deep_update(cfg, loaded)
            else:
                # 兼容旧版 intent_router_config.json，并入新配置。
                if self.intent_router_config_path.exists():
                    legacy = json.loads(self.intent_router_config_path.read_text(encoding="utf-8"))
                    if isinstance(legacy, dict):
                        self._deep_update(cfg, {"intent_router": legacy})
                path.write_text(
                    json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        except Exception:
            return cfg
        return cfg

    @staticmethod
    def _map_pm_missing_aspects(aspects: list[Any]) -> list[str]:
        out: list[str] = []
        for a in aspects or []:
            s = str(a).strip()
            if s == "time":
                out.append("time_period")
            elif s == "org_product":
                out.append("business_scope")
            elif s == "metric_scope":
                out.append("metric_scope")
            elif s in ("time_period", "business_scope", "comparison_type", "comparison_version", "granularity", "metric_scope"):
                out.append(s)
        seen: set[str] = set()
        res: list[str] = []
        for x in out:
            if x not in seen:
                seen.add(x)
                res.append(x)
        return res

    def _pm_short_circuit(
        self,
        *,
        reply: str,
        intent_type: str,
        next_action: str,
        dialogue_id: int,
        need_clarification: bool = False,
        missing_slots: list[str] | None = None,
        clarification_options: dict[str, list[str]] | None = None,
        pending_query_spec: dict[str, Any] | None = None,
        is_lightweight_social: bool = False,
        lightweight_social_score: float = 0.0,
        lightweight_social_signals: list[str] | None = None,
    ) -> dict[str, Any]:
        cleaned_reply = self._strip_reply_markdown_stars(reply)
        return {
            "reply": cleaned_reply,
            "intent_type": intent_type,
            "next_action": next_action,
            "need_clarification": need_clarification,
            "missing_slots": missing_slots or [],
            "clarification_options": clarification_options or {},
            "assumptions": [],
            "suggested_sql": None,
            "kb_context": {},
            "executed_result": None,
            "memory_id": None,
            "reply_options": [],
            "open_pivot_table": False,
            "pivot_suggestion": None,
            "dialogue_id": dialogue_id,
            "pending_query_spec": pending_query_spec,
            "is_lightweight_social": is_lightweight_social,
            "lightweight_social_score": lightweight_social_score,
            "lightweight_social_signals": lightweight_social_signals or [],
        }

    @staticmethod
    def _normalize_for_match(text: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", (text or "").lower())

    @staticmethod
    def _is_valid_domain_term(term: str) -> bool:
        t = (term or "").strip()
        if len(t) < 2 or len(t) > 40:
            return False
        if re.fullmatch(r"\d+", t):
            return False
        return True

    def _build_domain_lexicon(self) -> tuple[set[str], set[str]]:
        strong: set[str] = set()
        weak: set[str] = set()
        # Common weak tokens from budget domain.
        weak_seed = {
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
            "产品科目",
            "报告科目",
            "数据科目",
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
        weak.update(self._normalize_for_match(x) for x in weak_seed)

        # Add synonyms from term-synonyms KB as strong terms.
        try:
            synonym_rows = self.kb_service._read_csv_rows(
                self.kb_service.paths.synonyms_seed
                if self.kb_service.paths.synonyms_seed.exists()
                else self.kb_service.paths.synonyms_template
            )
            for row in synonym_rows:
                for key in ("term", "normalized_name", "normalized_code"):
                    token = self._normalize_for_match(str(row.get(key, "")))
                    if self._is_valid_domain_term(token):
                        strong.add(token)
        except Exception:
            pass

        # Add data dictionary names/codes as strong terms.
        try:
            dd_rows = self.kb_service._read_csv_rows(self.kb_service.paths.data_semantics)
            for row in dd_rows:
                for key in ("entity_code", "entity_name", "entity_type"):
                    token = self._normalize_for_match(str(row.get(key, "")))
                    if self._is_valid_domain_term(token):
                        strong.add(token)
        except Exception:
            pass

        # Load mapped table/field names from KB mapping file.
        try:
            mapping_path = (
                self.kb_service.paths.root
                / "01_data_semantics"
                / "field_table_name_mapping_zh.json"
            )
            if mapping_path.exists():
                import json

                mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
                for name in (mapping.get("table_name_mapping", {}) or {}).values():
                    n = self._normalize_for_match(str(name))
                    if self._is_valid_domain_term(n):
                        weak.add(n)
                for name in (mapping.get("field_name_mapping", {}) or {}).values():
                    n = self._normalize_for_match(str(name))
                    if self._is_valid_domain_term(n):
                        weak.add(n)
        except Exception:
            pass

        # Load concrete domain entities (departments/products/accounts) as strong terms.
        try:
            cpath = common_db_path()
            if cpath.exists():
                with sqlite3.connect(cpath) as conn:
                    conn.row_factory = sqlite3.Row
                    sqls = [
                        "SELECT dept_code AS code, dept_name AS name FROM dept_account",
                        "SELECT product_code AS code, product_name AS name FROM product_type",
                        "SELECT data_acct_code AS code, data_acct_name AS name FROM data_account",
                        "SELECT report_acct_code AS code, report_acct_name AS name FROM report_account",
                    ]
                    for sql in sqls:
                        for row in conn.execute(sql).fetchall():
                            code = self._normalize_for_match(str(row["code"] or ""))
                            name = self._normalize_for_match(str(row["name"] or ""))
                            if self._is_valid_domain_term(code):
                                strong.add(code)
                            if self._is_valid_domain_term(name):
                                strong.add(name)
        except Exception:
            pass

        # Pull budget summary level labels as strong terms for better first-turn intent routing.
        try:
            bpath = budget_db_path(settings.budget_year)
            if bpath.exists():
                with sqlite3.connect(bpath) as conn:
                    fields = [
                        "report_level1",
                        "report_level2",
                        "report_level3",
                        "dept_level1",
                        "dept_level2",
                        "dept_level3",
                        "data_code_name",
                        "product_code_name",
                    ]
                    for f in fields:
                        sql = (
                            f"SELECT DISTINCT {f} AS v FROM budget_summary "
                            f"WHERE {f} IS NOT NULL AND TRIM({f}) != '' LIMIT 2000"
                        )
                        for row in conn.execute(sql).fetchall():
                            val = self._normalize_for_match(str(row[0] or ""))
                            if self._is_valid_domain_term(val):
                                strong.add(val)
        except Exception:
            pass

        # Safety: remove ultra-generic tokens from strong lexicon.
        for stop in ["系统", "数据", "数据库", "分析", "管理", "银行", "预算"]:
            strong.discard(self._normalize_for_match(stop))
        weak = {w for w in weak if self._is_valid_domain_term(w)}
        strong = {s for s in strong if self._is_valid_domain_term(s)}
        return strong, weak

    def _domain_hit_profile(self, text: str) -> dict[str, int]:
        q_raw = (text or "").strip()
        q = self._normalize_for_match(q_raw)
        if not q:
            return {"strong_hits": 0, "weak_hits": 0}
        strong_hits = sum(1 for term in self.domain_terms_strong if term and term in q)
        weak_hits = sum(1 for term in self.domain_terms_weak if term and term in q)
        return {"strong_hits": strong_hits, "weak_hits": weak_hits}

    @staticmethod
    def _char_ngrams(text: str, n: int = 2) -> set[str]:
        t = (text or "").strip()
        if not t:
            return set()
        if len(t) <= n:
            return {t}
        return {t[i : i + n] for i in range(0, len(t) - n + 1)}

    def _build_semantic_budget_corpus(self) -> list[dict[str, Any]]:
        seed_terms: set[str] = set()
        seed_terms.update(self.domain_terms_strong)
        seed_terms.update(self.domain_terms_weak)
        try:
            synonym_rows = self.kb_service._read_csv_rows(
                self.kb_service.paths.synonyms_seed
                if self.kb_service.paths.synonyms_seed.exists()
                else self.kb_service.paths.synonyms_template
            )
            for row in synonym_rows:
                for key in ("term", "normalized_name", "normalized_code"):
                    token = self._normalize_for_match(str(row.get(key, "")))
                    if self._is_valid_domain_term(token):
                        seed_terms.add(token)
        except Exception:
            pass

        corpus: list[dict[str, Any]] = []
        for term in sorted(seed_terms):
            grams = self._char_ngrams(term)
            if not grams:
                continue
            corpus.append({"term": term, "grams": grams})
        return corpus

    def _semantic_budget_retrieve(self, query: str) -> dict[str, Any]:
        q_norm = self._normalize_for_match(query)
        if not q_norm:
            return {"score": 0.0, "top_matches": []}
        q_grams = self._char_ngrams(q_norm)
        if not q_grams:
            return {"score": 0.0, "top_matches": []}

        ranked: list[tuple[float, str]] = []
        for item in self.semantic_budget_corpus:
            term = item["term"]
            grams = item["grams"]
            if not term or not grams:
                continue
            if len(term) >= 2 and term in q_norm:
                score = 0.99
            else:
                inter = len(q_grams & grams)
                if inter == 0:
                    continue
                score = (2.0 * inter) / (len(q_grams) + len(grams))
            ranked.append((float(score), term))

        ranked.sort(key=lambda x: x[0], reverse=True)
        top = ranked[:5]
        max_score = top[0][0] if top else 0.0
        return {
            "score": round(max_score, 4),
            "top_matches": [
                {"term": term, "score": round(score, 4)}
                for score, term in top
            ],
        }

    def _llm_intent_arbitrate(
        self,
        query: str,
        rule_intent: str,
        semantic_score: float,
        semantic_matches: list[dict[str, Any]],
    ) -> str:
        if not self.deepseek_client or not self.deepseek_client.is_enabled():
            return rule_intent
        system_prompt = (
            "你是银行预算系统的意图判别器。"
            "只能输出 budget 或 general 其中一个词，不要输出其他内容。"
            "若问题涉及银行预算管理、科目、部门、产品、预算执行、资负、信贷经营指标，优先 budget。"
        )
        user_prompt = (
            f"query: {query}\n"
            f"rule_intent: {rule_intent}\n"
            f"semantic_score: {semantic_score}\n"
            f"semantic_matches: {semantic_matches}\n"
            "请输出最终意图：budget 或 general。"
        )
        out = self.deepseek_client.chat_completion(
            system_prompt,
            user_prompt,
            temperature=0.0,
            max_tokens=10,
        )
        self._emit_llm_trace_event(
            purpose="intent_arbitrate",
            input_data={
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": 0.0,
                "max_tokens": 10,
            },
            output_text=out,
        )
        text = (out or "").strip().lower()
        if "budget" in text:
            return "budget"
        if "general" in text:
            return "general"
        return rule_intent

    def _write_intent_trace(self, record: dict[str, Any]) -> None:
        if not bool(self.intent_router_config.get("trace_enabled", True)):
            return
        try:
            self.intent_trace_path.parent.mkdir(parents=True, exist_ok=True)
            with self.intent_trace_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _llm_rewrite(
        self,
        purpose: str,
        payload: dict[str, Any],
        fallback: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> str:
        if not self.deepseek_client or not self.deepseek_client.is_enabled():
            return fallback
        purpose_constraints = {
            "plan_query": (
                "当前阶段仅完成查询规划，尚未执行查询。不要写“已查询”“已执行完成”。"
                "必须在回复**靠前位置**原样体现输入中的「已锁定的查询维度」一段（含报告/数据/部门/产品科目 code｜name 及时间），"
                "再写查询规划要点；不要省略或改写已给出的科目代码与名称。"
            ),
            "clarify": "当前阶段为澄清，尚未执行查询。不要输出已查询结论。",
            "analysis_from_sql_result": (
                "请结合当前用户问题与最近对话上下文输出分析。"
                "若本轮需求是“重排版/改展示方式”，优先说明展示结构调整与新增差异，"
                "不要重复前文已经分析过的结论，除非用户明确要求重新完整分析。"
            ),
            "general_answer": (
                "当前阶段不读取预算数据库，不要表述为已查询数据库。"
                "必须先尽最大努力直接回答用户问题，不要先拒答或先说超出范围。"
                "若输入 JSON 中 is_lightweight_question=true："
                "请仅做自然短回复（1-3句），不要输出“关键要点/可执行建议”等结构化小标题或列表。"
                "若 is_lightweight_question=false："
                "再使用完整结构（先结论，再2-4条要点，最后1-3条建议）。"
                "若问题涉及实时/权威统计且你无法确认最新值，要明确说明“基于通用知识给出参考”。"
            ),
            "domain_knowledge_answer": (
                "当前问题属于银行/财务专业问答（非预算库查询）。"
                "必须先直接回答用户问题本身，不要先做身份边界声明（边界声明由外层统一追加）。"
                "对于数量/规模类问题：给出“口径说明+参考范围/典型数量级+为何会波动”。"
                "若无法确认实时精确值，明确说明“基于通用知识给出参考区间”，并给出权威查询路径。"
                "若输入 JSON 中 is_lightweight_question=true，则改为 1-3 句自然短答，不要结构化清单。"
                "否则输出结构：1) 一句话结论；2) 2-4 条关键口径；3) 1-2 条下一步建议。"
            ),
        }
        style_constraints = {
            "general_answer": (
                "当回答非预算专业问答时，在不改变用户沟通意图和事实正确性的前提下，"
                "尽量使用更丰富、自然、有温度的中文表达，避免句式和开场重复，"
                "不要让用户感到模板化或千篇一律。"
                "避免回答过短；通常不少于180字，必要时可适度举1个贴近银行预算场景的小例子。"
            ),
            "domain_knowledge_answer": (
                "语言要专业但不生硬，避免空泛套话。"
                "不要只说“无法回答”后结束，至少给出可用的口径框架和近似参考。"
                "尽量给出分类拆解，让用户立刻可用于汇报或继续提问。"
            ),
        }
        system_prompt = (
            "你叫“管衡”，是银行预算部门的数字员工。你的风格亲切、专业、乐于助人。"
            "请基于输入数据输出简洁、专业、可执行的中文回复。"
            "不要输出思维链，不要编造不存在的数据。"
            "不要输出 SQL 原文，不要输出英文字段名或数据库表名，全部改为自然中文业务表达。"
            f"{purpose_constraints.get(purpose, '')}"
            f"{style_constraints.get(purpose, '')}"
        )
        user_prompt = (
            f"任务: {purpose}\n"
            "输入(JSON):\n"
            f"{payload}\n\n"
            "请直接输出面向用户的话术。"
        )
        rewritten = self.deepseek_client.chat_completion(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self._emit_llm_trace_event(
            purpose=f"rewrite:{purpose}",
            input_data={
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "payload": payload,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            output_text=rewritten,
        )
        return rewritten or fallback

    @staticmethod
    def _looks_like_budget_query(text: str) -> bool:
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

    @staticmethod
    def _is_general_chitchat(text: str) -> bool:
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

    @staticmethod
    def _is_followup_constraint_like(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        # Typical follow-up fragments that补充口径 without repeating "预算" keyword.
        return bool(
            re.search(
                r"(20\d{2}|一季度|二季度|三季度|四季度|按月|按季|按年|同比|环比|预算与实际差异|个人金融部|企业金融部|普惠金融部|按全部部门|按当前口径|按刚才口径|按上述口径)",
                t,
            )
        )

    @staticmethod
    def _is_brief_acknowledgement(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        return bool(
            re.fullmatch(
                r"(好|好的|好呀|行|可以|继续|收到|明白|确认|按这个来|就这样)(吧|呢|哈)?[。！!，,\s]*",
                t,
            )
        )

    @staticmethod
    def _has_pending_budget_plan(history: list[dict[str, str]]) -> bool:
        if not history:
            return False
        recent_assistant = [
            m.get("content", "")
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

    @staticmethod
    def _is_budget_analysis_intent(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        return bool(
            re.search(
                r"(分析|查询|统计|对比|差异|偏差|执行|重跑|重算|汇总|趋势|钻取|看一下|看下|看.*数据|预算执行|预实|口径|多少|几个|几条|数量|占比|总数|规模|收入|利息|费用|利润|拨备|净息差|nim|roe|部门|产品|科目|支行|贷款|存款|资产|负债|月度|季度|年度|报表|明细|图表|测算|预测|模拟|目标求解|滚动预算|版本|导出|展示)",
                t,
            )
        )

    @staticmethod
    def _is_budget_metadata_query(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        return bool(
            re.search(
                r"(数据库|库里|系统里|系统中).*(多少|几个|几条|数量|总数|占比|分布|覆盖)|(多少|几个|几条|数量|总数).*(部门|科目|产品|记录|数据)",
                t,
            )
        )

    @staticmethod
    def _is_contextual_budget_followup(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        # 识别“这些/上面/刚才”这类承接上下文的预算补充请求。
        return bool(
            re.search(
                r"(这些|上述|上面|刚才|前面|上一条).*(部门|科目|产品|数据|结果)|(列出来|清单|列表|明细|展开|给我看)",
                t,
            )
        )

    @staticmethod
    def _is_layout_adjust_request(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        return bool(
            re.search(
                r"(排版|重排|重新排版|格式|展示方式|展示格式|字段顺序|表头|两列|分两列|分列|并列展示|横向展示|列展示|口径.*两列|预算.*实际.*两列)",
                t,
            )
        )

    @staticmethod
    def _is_pivot_view_request(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        return bool(re.search(r"(数据透视表|透视表|透视图|pivot)", t, flags=re.IGNORECASE))

    @staticmethod
    def _is_budget_knowledge_question(text: str) -> bool:
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

    @staticmethod
    def _lightweight_compact_typo_normalize(compact: str) -> str:
        """
        轻聊天识别前的轻量归一化：
        1) 统一句末疑问语气词（吗/嘛/么/麽）
        2) 去掉结尾语气助词（呀/啊/哈/啦/呢）
        """
        out = compact
        if len(out) <= 24:
            out = re.sub(r"[嘛么麽]$", "吗", out)
            out = re.sub(r"(呀|啊|哈|啦|呢)+$", "", out)
        return out

    @staticmethod
    def _detect_lightweight_social_signal(text: str) -> dict[str, Any]:
        t = (text or "").strip().lower()
        if not t:
            return {"is_lightweight_social": False, "score": 0.0, "signals": [], "compact": "", "normalized": ""}
        compact = re.sub(r"[\s\.,，。!！?？~～:：;；、\-_]+", "", t)
        if not compact:
            return {"is_lightweight_social": False, "score": 0.0, "signals": [], "compact": "", "normalized": ""}
        normalized = AgentGraphService._lightweight_compact_typo_normalize(compact)
        signals: list[str] = []
        score = 0.0

        if AgentGraphService._looks_like_budget_query(t):
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
        for p in exact_patterns:
            if re.fullmatch(p, normalized):
                score += 0.8
                signals.append("exact_greeting_pattern")
                break
        for p in state_patterns:
            if re.fullmatch(p, normalized):
                score += 0.8
                signals.append("state_question_pattern")
                break

        soft_tokens = ("你好", "您好", "哈喽", "嗨", "hi", "hello", "在吗", "吃了吗", "饿", "困", "忙吗", "有空吗")
        if any(tok in normalized for tok in soft_tokens):
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

    @staticmethod
    def _is_lightweight_social_question(text: str) -> bool:
        """
        轻量问候/轻问题：允许自然短答，不要求“关键要点/可执行建议”结构化输出。
        """
        return bool(AgentGraphService._detect_lightweight_social_signal(text).get("is_lightweight_social"))

    @staticmethod
    def _sanitize_lightweight_reply(reply: str, fallback: str) -> str:
        """
        轻问题场景的兜底：若模型仍输出“关键要点/建议”等模板化长文，回退短答。
        """
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

    @staticmethod
    def _strip_reply_markdown_stars(reply: str) -> str:
        """
        统一去掉回复中的 Markdown 星号样式，避免前端看到 **标题** 等标记。
        """
        r = (reply or "").strip()
        if not r:
            return ""
        # **标题** / *标题* -> 标题
        r = re.sub(r"\*\*(.*?)\*\*", r"\1", r, flags=re.DOTALL)
        r = re.sub(r"(?<!\*)\*(?!\*)(.*?)\*(?<!\*)", r"\1", r, flags=re.DOTALL)
        # Markdown 列表 "* " -> "- "
        r = re.sub(r"(?m)^\s*\*\s+", "- ", r)
        # 兜底清掉残留星号
        r = r.replace("*", "")
        return r.strip()

    @staticmethod
    def _is_execute_only_command(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        if re.fullmatch(
            r"(确认|缺省|默认|听你的|听你安排|你看着办吧?|就这样吧?|按你说的|按你说的来|照你说的|照你说的来|按你意思|你决定吧?|你定吧?|你来定)",
            t,
        ):
            return True
        return bool(
            re.search(
                r"(按默认假设执行|直接执行|开始执行|确认执行|按你说的执行|按我选择执行|按我的选择执行|按我选择分析|执行查询|开始查询|直接查|重跑|重算|执行吧|听你的来|按你说的办|你看着办)",
                t,
            )
        )

    @staticmethod
    def _resolve_numeric_option_reply(query: str, history: list[dict[str, str]]) -> str:
        """
        用户仅回复数字（如“1/2/3”）时，映射到上一条助手消息中的编号选项文本，
        降低“我已选第1项却被继续追问”的概率。
        """
        q = (query or "").strip()
        if not q:
            return q
        m = re.fullmatch(r"(?:选(?:项)?\s*)?([1-9]\d?)\s*[\.、\)]?", q)
        if not m:
            return q
        idx = int(m.group(1))
        if idx <= 0:
            return q
        last_assistant = ""
        for msg in reversed(history or []):
            if msg.get("role") == "assistant":
                last_assistant = str(msg.get("content") or "")
                if last_assistant.strip():
                    break
        if not last_assistant:
            return q
        options: dict[int, str] = {}
        for line in last_assistant.splitlines():
            mm = re.match(r"^\s*([1-9]\d?)\s*[\.\)、]\s*(.+?)\s*$", line.strip())
            if not mm:
                continue
            no = int(mm.group(1))
            text = mm.group(2).strip()
            if no not in options and text:
                options[no] = text
        chosen = options.get(idx)
        if not chosen:
            return q
        report_codes = re.findall(r"报告科目\s*([A-Z]\d{4,})", last_assistant, flags=re.IGNORECASE)
        data_code_groups = re.findall(
            r"数据科目\s*([A-Z]\d{3,}(?:/[A-Z]\d{3,})*)",
            last_assistant,
            flags=re.IGNORECASE,
        )
        data_codes: list[str] = []
        for grp in data_code_groups:
            parts = [p.strip().upper() for p in str(grp).split("/") if p.strip()]
            for p in parts:
                if p not in data_codes:
                    data_codes.append(p)

        hint_bits: list[str] = []
        # 常见选项语义：1=汇总口径（优先报告科目），2=数据细项（优先数据科目）。
        if idx == 1 and report_codes:
            hint_bits.append(f"按报告科目 {report_codes[0].upper()} 汇总口径")
        if idx == 2 and data_codes:
            hint_bits.append(f"按数据科目 {'/'.join(data_codes)} 细项口径")
        if idx == 3 and "净利息" in last_assistant:
            hint_bits.append("按净利息收入汇总口径")

        hint_suffix = f"；{'；'.join(hint_bits)}" if hint_bits else ""
        return f"我选择第{idx}项：{chosen}{hint_suffix}"

    def _last_budget_query_from_history(self, history: list[dict[str, str]]) -> str:
        for msg in reversed(history):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            text = str(content or "").strip()
            if not text:
                continue
            # 跳过纯选项/编号回复，避免“确认执行”回溯到“我选择第2项/L2”等中间文本。
            if re.fullmatch(r"[1-9]\d*", text):
                continue
            if re.fullmatch(r"[Ll]\s*[1-5]", text):
                continue
            if re.search(r"^我选择第\d+项", text):
                continue
            if self._looks_like_budget_query(content):
                return content
        return ""

    def _effective_query(self, state: AgentState) -> str:
        current_query = self._resolve_numeric_option_reply(
            state.get("user_query", ""),
            state.get("history", []),
        )
        pm_spec = state.get("pm_query_spec") if isinstance(state.get("pm_query_spec"), dict) else {}
        base_query = str(pm_spec.get("__base_user_query__") or "").strip()
        # 选择题回复（如“1 / L2 / 我选择第1项...”）仅用于补槽，不应覆盖真实业务查询文本。
        if base_query and (
            re.fullmatch(r"[1-9]\d*", str(state.get("user_query", "")).strip())
            or re.fullmatch(r"[Ll]\s*[1-5]", str(state.get("user_query", "")).strip())
            or re.search(r"^我选择第\d+项[:：]", current_query)
        ):
            return base_query
        if self._is_execute_only_command(current_query):
            if base_query:
                return base_query
            previous = self._last_budget_query_from_history(state.get("history", []))
            if previous:
                return previous
        return current_query

    def _intent_router(self, state: AgentState) -> AgentState:
        query = state.get("user_query", "")
        light_signal = self._detect_lightweight_social_signal(query)
        is_light_social = bool(light_signal.get("is_lightweight_social"))
        wants_execute = self._is_execute_only_command(query)
        history = state.get("history", [])
        has_budget_history = any(
            self._looks_like_budget_query(m.get("content", "")) or ("缺失要素" in m.get("content", ""))
            for m in history[-8:]
            if m.get("role") in {"assistant", "user"}
        )
        current_is_budget_domain = self._looks_like_budget_query(query)
        current_is_budget_analysis = self._is_budget_analysis_intent(query)
        current_is_budget_metadata = self._is_budget_metadata_query(query)
        current_is_contextual_followup = self._is_contextual_budget_followup(query)
        current_is_layout_adjust = self._is_layout_adjust_request(query)
        current_is_pivot_request = self._is_pivot_view_request(query)
        current_is_brief_ack = self._is_brief_acknowledgement(query)
        has_pending_budget_plan = self._has_pending_budget_plan(history)
        pivot_request_in_history = any(
            self._is_pivot_view_request(m.get("content", ""))
            for m in history[-10:]
            if m.get("role") == "user"
        )
        domain_hits = self._domain_hit_profile(query)
        current_is_budget_knowledge = current_is_budget_domain and self._is_budget_knowledge_question(query) and not current_is_budget_analysis
        current_is_chitchat = self._is_general_chitchat(query) or is_light_social
        current_is_followup = self._is_followup_constraint_like(query)
        rule_intent = "general"
        rule_reason = "fallback_general"
        rule_confidence = 0.45

        if current_is_chitchat and not wants_execute:
            rule_intent = "general"
            rule_reason = "chitchat"
            rule_confidence = 0.98
        elif domain_hits["strong_hits"] >= 1 or domain_hits["weak_hits"] >= 2:
            # In this banking-budget product, domain-hit questions should go budget flow.
            rule_intent = "budget"
            rule_reason = "domain_lexicon_hit"
            rule_confidence = 0.97
        elif current_is_budget_knowledge:
            # Keep knowledge-only fallback only when no domain lexicon hit.
            rule_intent = "general"
            rule_reason = "budget_knowledge_without_domain_hit"
            rule_confidence = 0.72
        elif current_is_budget_analysis and current_is_budget_domain:
            rule_intent = "budget"
            rule_reason = "budget_analysis_intent"
            rule_confidence = 0.95
        elif current_is_budget_domain and bool(re.search(r"(数据|数据库|多少|数量|总数|占比|分布)", query)):
            rule_intent = "budget"
            rule_reason = "budget_metadata_intent"
            rule_confidence = 0.94
        elif has_budget_history and current_is_layout_adjust:
            rule_intent = "budget"
            rule_reason = "budget_history_layout_adjust"
            rule_confidence = 0.95
            wants_execute = True
        elif has_budget_history and current_is_brief_ack:
            rule_intent = "budget"
            rule_reason = "budget_history_brief_ack"
            rule_confidence = 0.95
            wants_execute = has_pending_budget_plan
        elif has_budget_history and current_is_contextual_followup:
            rule_intent = "budget"
            rule_reason = "budget_history_contextual_followup"
            rule_confidence = 0.93
        elif wants_execute and has_budget_history:
            rule_intent = "budget"
            rule_reason = "budget_history_execute_only"
            rule_confidence = 0.95
        elif has_budget_history and current_is_followup:
            rule_intent = "budget"
            rule_reason = "budget_history_constraint_followup"
            rule_confidence = 0.90

        intent_type = rule_intent
        semantic = self._semantic_budget_retrieve(query)
        semantic_score = float(semantic.get("score", 0.0) or 0.0)
        semantic_matches = semantic.get("top_matches", [])
        high = float(self.intent_router_config.get("semantic_budget_threshold_high", 0.78))
        mid = float(self.intent_router_config.get("semantic_budget_threshold_mid", 0.65))
        enable_llm_arbiter = bool(self.intent_router_config.get("enable_llm_arbiter", True))
        arbiter_reason = "rule_only"

        if intent_type == "general" and not current_is_chitchat:
            if semantic_score >= high:
                intent_type = "budget"
                arbiter_reason = "semantic_high_override"
            elif semantic_score >= mid and enable_llm_arbiter:
                llm_intent = self._llm_intent_arbitrate(
                    query=query,
                    rule_intent=rule_intent,
                    semantic_score=semantic_score,
                    semantic_matches=semantic_matches,
                )
                intent_type = llm_intent
                arbiter_reason = (
                    "llm_arbiter_budget"
                    if llm_intent == "budget"
                    else "llm_arbiter_keep_general"
                )

        # 布局调整类诉求（如“预算和实际排两列”）在已有预算上下文下应直接触发重查执行。
        if has_budget_history and current_is_layout_adjust:
            intent_type = "budget"
            wants_execute = True
            arbiter_reason = "layout_adjust_force_execute"
        inherit_history_slots = bool(
            has_budget_history
            and (
                current_is_followup
                or current_is_contextual_followup
                or current_is_brief_ack
                or wants_execute
                or current_is_layout_adjust
            )
        )
        budget_query_kind = "metadata" if current_is_budget_metadata else "analysis"
        if has_budget_history and current_is_contextual_followup and bool(re.search(r"(部门|科目|产品|清单|列表|列出来|明细)", query)):
            budget_query_kind = "metadata"
        # 元数据查询（例如“数据库里有多少个部门的数据”）默认直接执行，不强制用户再点执行。
        if intent_type == "budget" and budget_query_kind == "metadata":
            wants_execute = True
        prefer_pivot_view = bool(
            current_is_pivot_request
            or (
                pivot_request_in_history
                and (
                    current_is_followup
                    or current_is_contextual_followup
                    or current_is_brief_ack
                    or wants_execute
                )
            )
        )

        if state.get("pm_route") == "data_query_ready":
            intent_type = "budget"

        self._write_intent_trace(
            {
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "query": query[: int(self.intent_router_config.get("trace_max_query_chars", 200))],
                "has_budget_history": has_budget_history,
                "has_pending_budget_plan": has_pending_budget_plan,
                "inherit_history_slots": inherit_history_slots,
                "rule": {
                    "intent": rule_intent,
                    "reason": rule_reason,
                    "confidence": rule_confidence,
                    "domain_hits": domain_hits,
                },
                "semantic": {
                    "score": semantic_score,
                    "top_matches": semantic_matches,
                    "threshold_high": high,
                    "threshold_mid": mid,
                },
                "arbiter_reason": arbiter_reason,
                "final": {
                    "intent": intent_type,
                    "budget_query_kind": budget_query_kind,
                    "wants_execute": wants_execute,
                    "prefer_pivot_view": prefer_pivot_view,
                    "is_lightweight_social": is_light_social,
                    "lightweight_social_score": float(light_signal.get("score", 0.0) or 0.0),
                    "lightweight_social_signals": list(light_signal.get("signals") or []),
                },
            }
        )
        return {
            "intent_type": intent_type,
            "wants_execute": wants_execute,
            "inherit_history_slots": inherit_history_slots,
            "budget_query_kind": budget_query_kind,
            "prefer_pivot_view": prefer_pivot_view,
            "is_lightweight_social": is_light_social,
            "lightweight_social_score": float(light_signal.get("score", 0.0) or 0.0),
            "lightweight_social_signals": list(light_signal.get("signals") or []),
        }

    def _general_answer(self, state: AgentState) -> AgentState:
        query = state.get("user_query", "").strip()
        is_light_social = bool(
            state.get("is_lightweight_social")
            if state.get("is_lightweight_social") is not None
            else self._detect_lightweight_social_signal(query).get("is_lightweight_social")
        )
        general_cfg = self.runtime_config.get("general_answer", {})
        temperature = float(general_cfg.get("temperature", 0.45))
        max_tokens = int(general_cfg.get("max_tokens", 900))
        enable_shorten = bool(general_cfg.get("enable_shorten", False))
        shorten_target_ratio = float(general_cfg.get("shorten_target_ratio", 0.5))
        shorten_min_chars = int(general_cfg.get("shorten_min_chars", 90))
        shorten_max_chars = int(general_cfg.get("shorten_max_chars", 260))
        reply = self._build_general_answer_body(
            query=query,
            temperature=temperature,
            max_tokens=max_tokens,
            is_lightweight_social=is_light_social,
        )
        if enable_shorten:
            reply = self._shorten_general_reply(
                reply,
                target_ratio=shorten_target_ratio,
                min_chars=shorten_min_chars,
                max_chars=shorten_max_chars,
            )
        if not is_light_social:
            reply = (
                f"{reply}\n\n"
                "说明：我是“管衡”，聚焦财务预算编制与分析。"
                "若你希望，我可以把上面的建议进一步落到预算场景，给出可执行的分析口径和下一步动作。"
            )
        return {
            "next_action": "general_answer",
            "need_clarification": False,
            "missing_slots": [],
            "assumptions": [],
            "suggested_sql": None,
            "reply": reply,
            "reply_options": [],
        }

    def _build_general_answer_body(
        self,
        *,
        query: str,
        temperature: float = 0.45,
        max_tokens: int = 900,
        is_lightweight_social: bool | None = None,
    ) -> str:
        is_light = (
            bool(is_lightweight_social)
            if is_lightweight_social is not None
            else self._is_lightweight_social_question(query)
        )
        if is_light:
            short_fallback = "哈哈，收到你的关心啦，我在线，有预算问题随时叫我。"
            rewritten = self._llm_rewrite(
                "general_answer",
                {
                    "query": query,
                    "agent_name": "管衡",
                    "is_lightweight_question": True,
                    "requirement": "这是轻量寒暄/小问题，请只用1-2句自然短答，不要分点，不要建议清单。",
                },
                short_fallback,
                temperature=min(temperature, 0.35),
                max_tokens=min(max_tokens, 120),
            )
            return self._sanitize_lightweight_reply(rewritten, short_fallback)
        fallback_reply = self._build_general_fallback_answer(query)
        return self._llm_rewrite(
            "general_answer",
            {
                "query": query,
                "agent_name": "管衡",
                "is_lightweight_question": False,
                "requirement": (
                    "请基于通用知识高质量回答："
                    "1) 先给结论；2) 给关键原理/要点；3) 给可执行建议。"
                    "对预算知识类问题可给基础框架与常见误区，语言自然有温度。"
                ),
            },
            fallback_reply,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _build_domain_knowledge_answer_body(
        self,
        *,
        query: str,
        temperature: float = 0.35,
        max_tokens: int = 1200,
        is_lightweight_social: bool | None = None,
    ) -> str:
        is_light = (
            bool(is_lightweight_social)
            if is_lightweight_social is not None
            else self._is_lightweight_social_question(query)
        )
        if is_light:
            short_fallback = "我在呢，状态良好。要不你直接说想查的预算口径，我马上帮你。"
            rewritten = self._llm_rewrite(
                "domain_knowledge_answer",
                {
                    "query": query,
                    "is_lightweight_question": True,
                    "requirement": "这是轻量寒暄，请1-2句简短自然回答，不要关键要点和建议列表。",
                },
                short_fallback,
                temperature=min(temperature, 0.3),
                max_tokens=min(max_tokens, 120),
            )
            return self._sanitize_lightweight_reply(rewritten, short_fallback)
        fallback_reply = self._build_general_fallback_answer(query)
        return self._llm_rewrite(
            "domain_knowledge_answer",
            {
                "query": query,
                "is_lightweight_question": False,
                "requirement": (
                    "这是银行/财务专业问答，但不是预算数据库查询。"
                    "请给出具体、可用、可复述的专业答复。"
                ),
            },
            fallback_reply,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @staticmethod
    def _shorten_general_reply(
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

        # Keep the first few complete sentences to avoid awkward truncation.
        chunks = re.split(r"(?<=[。！？!?])", raw)
        kept = ""
        for chunk in chunks:
            if not chunk.strip():
                continue
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

    @staticmethod
    def _build_general_fallback_answer(query: str) -> str:
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

    def _kb_context(self, state: AgentState) -> AgentState:
        query = self._effective_query(state)
        top_k = int(state.get("top_k", 5) or 5)
        return {"kb_context": self.kb_service.search_context(query=query, top_k=top_k)}

    @staticmethod
    def _is_explicit_year_comparison(query: str) -> bool:
        q = str(query or "")
        if not q:
            return False
        if re.search(r"(预算.?实际|预实|差异)", q):
            return False
        if re.search(r"(?:比较|对比|相比)\s*20\d{2}\s*年?", q):
            return True
        if re.search(r"(?:和|与|跟)\s*20\d{2}\s*年?", q) and re.search(r"(比较|对比|相比|比)", q):
            return True
        years = set(re.findall(r"20\d{2}", q))
        return len(years) >= 2 and bool(re.search(r"(比较|对比|相比|比)", q))

    @staticmethod
    def _extract_compare_target_year(query: str) -> int | None:
        q = str(query or "")
        if not q:
            return None
        if not AgentGraphService._is_explicit_year_comparison(q):
            return None
        m = re.search(r"(?:和|与|跟)\s*(20\d{2})\s*年?", q)
        if m:
            return int(m.group(1))
        m = re.search(r"(?:比较|对比|相比)\s*(20\d{2})\s*年?", q)
        if m:
            return int(m.group(1))
        years = [int(y) for y in re.findall(r"20\d{2}", q)]
        if not years:
            return None
        return min(years) if len(set(years)) >= 2 else None

    @staticmethod
    def _extract_slot_status(query: str) -> dict[str, bool]:
        q = query.lower()
        has_time = bool(
            re.search(
                r"(20\d{2}|y20\d{2}|q[1-4]|m\d{2}|本月|本季度|本年|去年|今年|一季度|二季度|三季度|四季度|"
                r"最近一个?月|近一个?月|近一月|上个?月(?!年))",
                q,
            )
        )
        has_entity = bool(re.search(r"(科目|部门|产品|贷款|存款|资产|负债|利润|收入|支出)", q))
        has_comparison = bool(re.search(r"(同比|环比|对比|较|vs|预算.?实际|差异)", q))
        has_granularity = bool(re.search(r"(明细|汇总|按月|按季|按年|钻取|层级)", q))
        return {
            "time_period": has_time,
            "business_scope": has_entity,
            "comparison_type": has_comparison,
            "granularity": has_granularity,
        }

    @staticmethod
    def _slot_status_from_structured_slots(slots: dict[str, Any]) -> dict[str, bool]:
        return {
            "time_period": bool(slots.get("time_period") or slots.get("time_granularity_hint")),
            "business_scope": bool(slots.get("business_scope")),
            # 需求更新：比较项可选；缺省可不比较，不作为阻塞缺口。
            "comparison_type": True,
            "granularity": bool(slots.get("granularity") or slots.get("time_granularity_hint")),
        }

    @staticmethod
    def _extract_structured_slots(query: str) -> dict[str, Any]:
        q = query or ""
        slots: dict[str, Any] = {}

        m_year = re.search(r"(20\d{2})", q)
        if m_year:
            slots["time_period"] = f"Y{m_year.group(1)}"
        elif re.search(r"(最近一个?月|近一个?月|近一月|上个?月(?!年|方|下))", q):
            lm = AgentGraphService._last_completed_calendar_month()
            slots["time_period"] = f"{lm['year_tag']} {lm['month_tag']}"
        elif re.search(r"(本年|今年)", q):
            slots["time_period"] = "current_year"

        if re.search(r"(一季度|q1|Q1)", q):
            slots["time_granularity_hint"] = "Q1"
        elif re.search(r"(二季度|q2|Q2)", q):
            slots["time_granularity_hint"] = "Q2"
        elif re.search(r"(三季度|q3|Q3)", q):
            slots["time_granularity_hint"] = "Q3"
        elif re.search(r"(四季度|q4|Q4)", q):
            slots["time_granularity_hint"] = "Q4"

        for dep in ["个人金融部", "企业金融部", "普惠金融部", "科技事业部", "司库部门", "境外金融部"]:
            if dep in q:
                slots["business_scope"] = dep
                break
        if "department" not in slots and "business_scope" not in slots and "部门" in q:
            slots["business_scope"] = "部门维度"

        if re.search(r"(预算.?实际|预实|差异)", q):
            slots["comparison_type"] = "budget_vs_actual"
        elif ("同比" in q) or AgentGraphService._is_explicit_year_comparison(q):
            slots["comparison_type"] = "yoy"
        elif "环比" in q:
            slots["comparison_type"] = "mom"
        lvl_match = (
            re.search(r"\b[Ll]\s*([1-5])\b", q)
            or re.search(r"\b(?:show[_\s-]?level|level)\s*([1-5])\b", q, flags=re.I)
            or re.search(r"层级\s*([1-5])", q)
        )
        if lvl_match:
            try:
                slots["comparison_show_level"] = int(lvl_match.group(1))
            except Exception:
                pass

        if re.search(r"(按月|月度)", q):
            slots["granularity"] = "month"
        elif re.search(r"(按季|季度)", q):
            slots["granularity"] = "quarter"
        elif re.search(r"(按年|年度)", q):
            slots["granularity"] = "year"
        elif "明细" in q:
            slots["granularity"] = "detail"
        elif "汇总" in q:
            slots["granularity"] = "summary"

        return slots

    @staticmethod
    def _load_compare_version_options() -> list[tuple[int, int, int, str]]:
        """
        返回 [(show_level, source_year, source_version_id, source_version_name)]，按 level 排序。
        优先从 compare.db 读取，缺失时回退 common/edit_show_version 配置。
        """
        options: list[tuple[int, int, int, str]] = []
        cpath = compare_db_path()
        if cpath.exists():
            try:
                with sqlite3.connect(cpath) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        """
                        SELECT show_level, source_year, source_version_id, source_version_name
                        FROM compare_budget_summary
                        WHERE show_level BETWEEN 1 AND 5
                        GROUP BY show_level, source_year, source_version_id, source_version_name
                        ORDER BY show_level ASC
                        """
                    ).fetchall()
                for r in rows:
                    sl = int(r["show_level"] or 0)
                    if sl < 1 or sl > 5:
                        continue
                    sy = int(r["source_year"] or 0)
                    sv = int(r["source_version_id"] or 0)
                    sn = str(r["source_version_name"] or f"V{sv}")
                    if sv <= 0:
                        continue
                    options.append((sl, sy, sv, sn))
            except Exception:
                options = []
        if options:
            dedup: dict[int, tuple[int, int, int, str]] = {}
            for row in options:
                dedup[row[0]] = row
            return [dedup[k] for k in sorted(dedup.keys())]
        try:
            with sqlite3.connect(common_db_path()) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT e.edit_show_sign AS show_level, d.year AS source_year, e.version_id AS source_version_id, d.data_file_name
                    FROM edit_show_version e
                    JOIN databases d ON d.id = e.data_file_id
                    WHERE e.edit_show_sign BETWEEN 1 AND 5
                    ORDER BY e.edit_show_sign ASC
                    """
                ).fetchall()
            for r in rows:
                sl = int(r["show_level"] or 0)
                sy = int(r["source_year"] or 0)
                sv = int(r["source_version_id"] or 0)
                sn = f"{str(r['data_file_name'] or '').strip()} / V{sv}"
                if sl < 1 or sl > 5 or sv <= 0:
                    continue
                options.append((sl, sy, sv, sn))
        except Exception:
            pass
        return options

    def _compare_version_choice_hint(self, show_level: int) -> str:
        level = int(show_level or 0)
        if level < 1 or level > 5:
            return ""
        meta = self._compare_level_meta(level)
        if meta:
            sy = int(meta.get("source_year") or 0)
            sv = int(meta.get("source_version_id") or 0)
            sn = str(meta.get("source_version_name") or "").strip()
            if sv > 0:
                return f"已选择同比版本：L{level}（{sy}年 / V{sv} {sn}）。"
        return f"已选择同比版本：L{level}。"

    def _contextual_slots_from_history(self, history: list[dict[str, str]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        # Only use recent user turns as context to avoid stale drift.
        recent_user_msgs = [m.get("content", "") for m in history if m.get("role") == "user"][-8:]
        for text in recent_user_msgs:
            slots = self._extract_structured_slots(text)
            # "latest mention wins" for most slots.
            merged.update(slots)
        return merged

    @staticmethod
    def _extract_compare_show_level_from_text(text: str) -> int | None:
        t = str(text or "").strip()
        if not t:
            return None
        m = re.search(r"\b[Ll]\s*([1-5])\b", t)
        if m:
            return int(m.group(1))
        m = re.search(r"\b(?:show[_\s-]?level|level)\s*([1-5])\b", t, flags=re.I)
        if m:
            return int(m.group(1))
        m = re.fullmatch(r"[1-5]", t)
        if m:
            return int(m.group(0))
        return None

    def _requirement_check(self, state: AgentState) -> AgentState:
        query = self._effective_query(state)
        history = state.get("history", [])
        query_kind = state.get("budget_query_kind", "analysis")
        inherit_history_slots = bool(state.get("inherit_history_slots", False))
        pm_ctx = state.get("pm_query_spec") if isinstance(state.get("pm_query_spec"), dict) else {}

        if query_kind == "metadata":
            # 系统元数据统计问题不需要四槽位澄清，直接进入查询执行链路。
            return {
                "slot_status": {
                    "time_period": True,
                    "business_scope": True,
                    "comparison_type": True,
                    "granularity": True,
                },
                "clarified_slots": {},
                "missing_slots": [],
                "assumptions": [],
                "need_clarification": False,
                "clarification_rounds": 0,
            }

        override = state.get("pm_requirement_override")
        if isinstance(override, dict) and override:
            return {
                "slot_status": dict(override.get("slot_status") or {}),
                "clarified_slots": dict(override.get("clarified_slots") or {}),
                "missing_slots": list(override.get("missing_slots") or []),
                "assumptions": list(override.get("assumptions") or []),
                "need_clarification": bool(override.get("need_clarification", False)),
                "clarification_rounds": int(override.get("clarification_rounds", 0)),
            }

        query_slot_status = self._extract_slot_status(query)
        history_slots = self._contextual_slots_from_history(history) if inherit_history_slots else {}
        current_slots = self._extract_structured_slots(query)

        clarified_slots = {**history_slots, **current_slots}
        # 当前轮明确是“按某年份比较”且未显式选择 Lx 时，不继承历史 compare level，避免串到上一轮。
        if self._is_explicit_year_comparison(query) and int(current_slots.get("comparison_show_level") or 0) <= 0:
            clarified_slots.pop("comparison_show_level", None)
        if int(clarified_slots.get("comparison_show_level") or 0) <= 0 and isinstance(pm_ctx, dict):
            pending_level = int(pm_ctx.get("__selected_compare_level__") or 0)
            if 1 <= pending_level <= 5:
                clarified_slots["comparison_show_level"] = pending_level
            elif bool(pm_ctx.get("__require_compare_level__", False)):
                lv = self._extract_compare_show_level_from_text(query)
                if lv is not None:
                    clarified_slots["comparison_show_level"] = lv
        yoy_requested = (
            "同比" in query
            or str(clarified_slots.get("comparison_type", "")).strip().lower() == "yoy"
            or int((pm_ctx or {}).get("__selected_compare_level__") or 0) in {1, 2, 3, 4, 5}
            or bool((pm_ctx or {}).get("__require_compare_level__", False))
        )
        compare_show_level = int(clarified_slots.get("comparison_show_level") or 0)
        compare_opts_raw = self._load_compare_version_options() if yoy_requested else []
        target_compare_year = self._extract_compare_target_year(query) if yoy_requested else None
        if target_compare_year is not None:
            filtered = [x for x in compare_opts_raw if int(x[1]) == int(target_compare_year)]
            if filtered:
                compare_opts_raw = filtered
        compare_opts_text = [
            f"L{sl}（{sy}年 / V{sv} {sn}）" for sl, sy, sv, sn in compare_opts_raw
        ]
        contextual_slot_status = self._slot_status_from_structured_slots(clarified_slots)
        slot_status = {
            "time_period": bool(query_slot_status["time_period"] or contextual_slot_status["time_period"]),
            "business_scope": bool(query_slot_status["business_scope"] or contextual_slot_status["business_scope"]),
            # 比较项默认可缺省（不比较），不再触发反复确认。
            "comparison_type": True,
            # 仅当用户明确要求同比时，才强制要求“同比版本（L1-L5）”。
            "comparison_version": (not yoy_requested) or (1 <= compare_show_level <= 5),
            "granularity": bool(query_slot_status["granularity"] or contextual_slot_status["granularity"]),
        }
        missing = [k for k, ok in slot_status.items() if not ok]

        assumptions: list[str] = []
        if "time_period" in missing:
            assumptions.append("默认按当前预算年度 Y2026 分析")
        if "comparison_type" in missing:
            assumptions.append("默认不做比较分析，仅输出单口径结果")
        if "granularity" in missing:
            assumptions.append("默认按月汇总粒度展示")

        wants_execute = bool(state.get("wants_execute", False))
        need_clarification = len(missing) > 0 and (
            (not wants_execute) or ("comparison_version" in missing)
        )
        history_clarify_count = sum(
            1 for m in history if m.get("role") == "assistant" and "缺失要素" in m.get("content", "")
        )
        clarification_rounds = max(int(state.get("clarification_rounds", 0)), history_clarify_count)
        if wants_execute and clarification_rounds == 0 and history:
            # In practice, user often sends "按默认假设执行" after a clarify turn;
            # assistant wording may be LLM-rewritten and not contain fixed markers.
            clarification_rounds = 1
        if need_clarification:
            clarification_rounds += 1
        return {
            "slot_status": slot_status,
            "clarified_slots": clarified_slots,
            "missing_slots": missing,
            "assumptions": assumptions,
            "need_clarification": need_clarification,
            "clarification_rounds": clarification_rounds,
            "comparison_version_options": compare_opts_text,
        }

    def _clarify(self, state: AgentState) -> AgentState:
        missing = state.get("missing_slots", [])
        assumptions = state.get("assumptions", [])
        option_map: dict[str, list[str]] = {
            "comparison_type": ["同比", "环比", "预算与实际差异"],
            "comparison_version": state.get("comparison_version_options", []) or [],
            "granularity": ["按月", "按季", "按年", "看明细", "先看汇总"],
            "time_period": ["2026年一季度", "2026年全年", "本年度", "最近三个月"],
            "business_scope": ["个人金融部", "企业金融部", "普惠金融部", "按全部部门"],
        }
        clarification_options = {k: option_map.get(k, []) for k in missing}
        missing_text = "、".join(missing) if missing else "无"
        assumption_text = "\n".join(f"- {a}" for a in assumptions) if assumptions else "- 无"
        fallback_reply = (
            "我已经理解你的问题是预算分析类请求，但当前查询条件还不完整。\n"
            f"缺失要素：{missing_text}\n\n"
            "请优先补充上面缺失要素中的任意一项，我会在已有信息基础上继续推理。\n\n"
            "我可以按以下默认假设直接开始：\n"
            f"{assumption_text}\n\n"
            "请回复：\n"
            "1) “按默认假设执行”；或\n"
            "2) 补充你希望的时间、对象、对比方式、粒度。\n\n"
            "如果你暂时不补充额外信息，直接回复“确认”或“缺省”，我会按当前理解直接查询。"
        )
        reply = self._llm_rewrite(
            "clarify",
            {
                "missing_slots": missing,
                "assumptions": assumptions,
                "user_query": state.get("user_query", ""),
            },
            fallback_reply,
        )
        default_execute_hint = "如果你暂时不补充额外信息，直接回复“确认”或“缺省”，我会按当前理解直接查询。"
        if "comparison_version" in missing:
            version_options = state.get("comparison_version_options", []) or []
            if version_options:
                numbered = "\n".join(f"{i + 1}. {txt}" for i, txt in enumerate(version_options))
                compare_hint = (
                    "你要求同比分析，请先选择 compare 版本（可回复编号）：\n"
                    f"{numbered}\n\n"
                    "例如：回复“1”表示选择 L1。"
                )
                reply = f"{reply.rstrip()}\n\n{compare_hint}"
        if default_execute_hint not in reply:
            reply = f"{reply.rstrip()}\n\n{default_execute_hint}"
        return {
            "next_action": "clarify",
            "suggested_sql": None,
            "clarification_options": clarification_options,
            "reply": reply,
            "reply_options": [],
        }

    @staticmethod
    def _parse_requested_year(text: str) -> int | None:
        m = re.search(r"(20\d{2})", text or "")
        if not m:
            return None
        return int(m.group(1))

    @staticmethod
    def _last_completed_calendar_month() -> dict[str, Any]:
        """自然月上一月（相对服务器当前真实日期）。"""
        today = date.today()
        if today.month == 1:
            y, m = today.year - 1, 12
        else:
            y, m = today.year, today.month - 1
        return {"calendar_year": y, "year_tag": f"Y{y}", "month_tag": f"M{m:02d}"}

    def _resolve_analysis_time_anchor(self, state: AgentState) -> dict[str, Any]:
        """分析类问题的时间轴：自然语言、PM 结构化槽位、缺省年度。"""
        query = self._effective_query(state)
        clarified: dict[str, Any] = state.get("clarified_slots", {}) or {}
        pm = state.get("pm_query_spec")
        ex = self.query_executor

        if isinstance(pm, dict):
            y_raw = str(pm.get("year") or "").strip()
            m_raw = str(pm.get("month") or "").strip()
            cal_y = 0
            ym = re.match(r"Y(20\d{2})", y_raw, flags=re.I)
            if ym:
                cal_y = int(ym.group(1))
            if cal_y and m_raw:
                mm = re.match(r"M(\d{2})", m_raw, flags=re.I)
                if mm and 1 <= int(mm.group(1)) <= 12:
                    return {
                        "calendar_year": cal_y,
                        "year_tag": f"Y{cal_y}",
                        "month_tag": f"M{int(mm.group(1)):02d}",
                    }

        if re.search(r"最近一个?月|近一个?月|近一月|上个?月(?!年|方|下)", query):
            return self._last_completed_calendar_month()

        # 月份区间（如 1-2月）不锚定单月，避免后续 SQL 被 month=M01 等条件意外收窄。
        span = re.search(r"([1-9]|1[0-2])\s*月?\s*[-~到至]\s*([1-9]|1[0-2])\s*月", query)
        if span:
            y = self._parse_requested_year(query) or int(settings.budget_year)
            return {"calendar_year": y, "year_tag": f"Y{y}", "month_tag": None}

        mi = ex._extract_month_index_from_text(query)
        m_year = re.search(r"(20\d{2})年?\s*(\d{1,2})月", query) or re.search(
            r"(20\d{2}).*?(\d{1,2})月", query
        )
        if m_year and mi:
            y = int(m_year.group(1))
            if 1 <= mi <= 12:
                return {
                    "calendar_year": y,
                    "year_tag": f"Y{y}",
                    "month_tag": f"M{mi:02d}",
                }
        if mi is not None and 1 <= mi <= 12:
            y = self._parse_requested_year(query) or int(settings.budget_year)
            return {
                "calendar_year": y,
                "year_tag": f"Y{y}",
                "month_tag": f"M{mi:02d}",
            }

        py = self._parse_requested_year(query) or self._parse_requested_year(
            str(clarified.get("time_period", "") or "")
        )
        if py:
            return {"calendar_year": py, "year_tag": f"Y{py}", "month_tag": None}

        by = int(settings.budget_year)
        return {"calendar_year": by, "year_tag": f"Y{by}", "month_tag": None}

    @staticmethod
    def _compare_scope_from_query(query: str) -> str:
        """在 compare_budget_summary 上收紧产品/指标口径，避免对全行误 SUM。"""
        q = query or ""
        conds: list[str] = []
        for kw in ("车车贷", "开鑫贷", "企企贷", "企小乐", "开心小账户", "金市", "司库"):
            if kw in q:
                conds.append(f"INSTR(IFNULL(product_code_name,''), '{kw}') > 0")
                break
        # 贷款/信贷：避免无关键词时刷出全表 L1（如存放同业日均等）
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

    @staticmethod
    def _sql_escape_literal(s: str) -> str:
        return (s or "").replace("'", "''")

    @staticmethod
    def _norm_code_name_list(items: Any) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if not isinstance(items, list):
            return out
        for it in items:
            if not isinstance(it, dict):
                continue
            c = str(it.get("code") or "").strip()
            n = str(it.get("name") or "").strip()
            if not c and not n:
                continue
            out.append({"code": c, "name": n})
        return out

    @classmethod
    def _text_match_or_sql(cls, field_expr: str, terms: list[str]) -> str:
        cleaned: list[str] = []
        seen: set[str] = set()
        for t in terms:
            v = str(t or "").strip()
            if not v:
                continue
            if v in seen:
                continue
            seen.add(v)
            cleaned.append(v)
        if not cleaned:
            return ""
        conds = [f"INSTR({field_expr}, '{cls._sql_escape_literal(t)}') > 0" for t in cleaned]
        return " AND (" + " OR ".join(conds) + ")"

    @staticmethod
    def _expand_org_terms(terms: list[str]) -> list[str]:
        """组织名称匹配扩展：兼容“汽车金融部”与“汽车金融”等口径写法。"""
        out: list[str] = []
        seen: set[str] = set()
        suffixes = ("部门", "事业部", "业务条线", "条线", "部")
        for raw in terms:
            t = str(raw or "").strip()
            if not t:
                continue
            variants = {t}
            compact = re.sub(r"\s+", "", t)
            variants.add(compact)
            for sfx in suffixes:
                if compact.endswith(sfx) and len(compact) > len(sfx):
                    variants.add(compact[: -len(sfx)])
            for v in variants:
                if not v or v in seen:
                    continue
                seen.add(v)
                out.append(v)
        return out

    @classmethod
    def _dimension_filters_from_pm_query_spec(cls, pm_query_spec: dict[str, Any] | None) -> str:
        """将 PM 结构化维度映射为 SQL 过滤条件（报告/数据/部门/产品）。"""
        if not isinstance(pm_query_spec, dict):
            return ""

        report_entries = cls._norm_code_name_list(pm_query_spec.get("report_accounts"))
        data_entries = cls._norm_code_name_list(pm_query_spec.get("data_accounts"))
        dept_entries = cls._norm_code_name_list(pm_query_spec.get("departments"))
        product_entries = cls._norm_code_name_list(pm_query_spec.get("products"))

        report_terms: list[str] = []
        for e in report_entries:
            if e["code"]:
                report_terms.append(e["code"])
            if e["name"]:
                report_terms.append(e["name"])
        data_terms: list[str] = []
        for e in data_entries:
            if e["code"]:
                data_terms.append(e["code"])
            if e["name"]:
                data_terms.append(e["name"])
        dept_terms: list[str] = []
        for e in dept_entries:
            if e["code"]:
                dept_terms.append(e["code"])
            if e["name"]:
                dept_terms.append(e["name"])
        dept_terms = cls._expand_org_terms(dept_terms)
        product_terms: list[str] = []
        for e in product_entries:
            if e["code"]:
                product_terms.append(e["code"])
            if e["name"]:
                product_terms.append(e["name"])

        report_expr = "IFNULL(report_level1,'')||IFNULL(report_level2,'')||IFNULL(report_level3,'')||IFNULL(report_level4,'')||IFNULL(report_level5,'')"
        data_expr = "IFNULL(data_code_name,'')"
        dept_expr = "IFNULL(dept_level1,'')||IFNULL(dept_level2,'')||IFNULL(dept_level3,'')"
        product_expr = "IFNULL(product_code_name,'')"

        return "".join(
            [
                cls._text_match_or_sql(report_expr, report_terms),
                cls._text_match_or_sql(data_expr, data_terms),
                cls._text_match_or_sql(dept_expr, dept_terms),
                cls._text_match_or_sql(product_expr, product_terms),
            ]
        )

    @staticmethod
    def _pm_has_metric_lock(pm_query_spec: dict[str, Any] | None) -> bool:
        if not isinstance(pm_query_spec, dict):
            return False
        report_entries = pm_query_spec.get("report_accounts")
        data_entries = pm_query_spec.get("data_accounts")
        return bool(isinstance(report_entries, list) and report_entries) or bool(
            isinstance(data_entries, list) and data_entries
        )

    @staticmethod
    def _pm_report_locked_without_data(pm_query_spec: dict[str, Any] | None) -> bool:
        if not isinstance(pm_query_spec, dict):
            return False
        report_entries = pm_query_spec.get("report_accounts")
        data_entries = pm_query_spec.get("data_accounts")
        has_report = bool(isinstance(report_entries, list) and report_entries)
        has_data = bool(isinstance(data_entries, list) and data_entries)
        return has_report and not has_data

    @staticmethod
    def _pm_report_scope_label(pm_query_spec: dict[str, Any] | None) -> str:
        if not isinstance(pm_query_spec, dict):
            return ""
        reports = pm_query_spec.get("report_accounts")
        if not isinstance(reports, list) or not reports:
            return ""
        first = reports[0] if isinstance(reports[0], dict) else {}
        code = str(first.get("code") or "").strip()
        name = str(first.get("name") or "").strip()
        if code and name:
            return f"{code} {name}"
        return code or name

    @classmethod
    def _pm_dimension_terms(cls, pm_query_spec: dict[str, Any] | None) -> dict[str, list[str]]:
        if not isinstance(pm_query_spec, dict):
            return {"report": [], "data": [], "dept": [], "product": []}
        out: dict[str, list[str]] = {"report": [], "data": [], "dept": [], "product": []}
        mapping = {
            "report_accounts": "report",
            "data_accounts": "data",
            "departments": "dept",
            "products": "product",
        }
        for src_key, dst_key in mapping.items():
            for e in cls._norm_code_name_list(pm_query_spec.get(src_key)):
                if e["code"]:
                    out[dst_key].append(e["code"])
                if e["name"]:
                    out[dst_key].append(e["name"])
        # 去重保序
        for k, vals in out.items():
            seen: set[str] = set()
            deduped: list[str] = []
            for v in vals:
                if v in seen:
                    continue
                seen.add(v)
                deduped.append(v)
            out[k] = deduped
        return out

    @classmethod
    def _sql_missing_pm_dimensions(cls, sql: str, pm_query_spec: dict[str, Any] | None) -> list[str]:
        """检查 SQL 是否覆盖了 PM 已锁定的关键维度 terms。"""
        terms = cls._pm_dimension_terms(pm_query_spec)
        missing: list[str] = []
        sql_text = sql or ""
        labels = {
            "report": "报告科目",
            "data": "数据科目",
            "dept": "部门科目",
            "product": "产品科目",
        }
        for dim_key in ("report", "data", "dept", "product"):
            dim_terms = terms.get(dim_key) or []
            if not dim_terms:
                continue
            # 命中任一 term 即认为该维度已在 SQL 中体现
            covered = any(f"'{cls._sql_escape_literal(t)}'" in sql_text for t in dim_terms)
            if not covered:
                missing.append(labels[dim_key])
        return missing

    def _dept_filter_sql_from_state(self, state: AgentState | None, query: str) -> str:
        """按 pm_query_spec 中的部门或问句中的条线关键词收紧 dept_level*（不依赖用户写「部门」二字）。"""
        conds: list[str] = []
        pm = state.get("pm_query_spec") if state is not None else None
        pm_has_departments = False
        if isinstance(pm, dict):
            pm_depts = pm.get("departments") or []
            pm_has_departments = bool(isinstance(pm_depts, list) and pm_depts)
            raw_terms: list[str] = []
            for d in pm_depts:
                if not isinstance(d, dict):
                    continue
                code = str(d.get("code") or "").strip()
                name = str(d.get("name") or "").strip()
                if code:
                    raw_terms.append(code)
                if name:
                    raw_terms.append(name)
            for name in self._expand_org_terms(raw_terms):
                if len(name) < 2:
                    continue
                lit = self._sql_escape_literal(name)
                conds.append(
                    f"INSTR(IFNULL(dept_level1,'')||IFNULL(dept_level2,'')||IFNULL(dept_level3,''), '{lit}') > 0"
                )
        # 已由 PM 结构化部门维度生成过滤条件时，不再叠加 fallback，避免双重 AND 过窄。
        if pm_has_departments:
            return ""
        q = query or ""
        if not conds and not pm_has_departments:
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

    @classmethod
    def _recent_n_complete_month_tags(cls, n: int) -> list[tuple[str, str]]:
        tags: list[tuple[str, str]] = []
        d = date.today().replace(day=1)
        for _ in range(max(1, n)):
            prev_month_end = d - timedelta(days=1)
            tags.append((f"Y{prev_month_end.year}", f"M{prev_month_end.month:02d}"))
            d = prev_month_end.replace(day=1)
        return tags

    @staticmethod
    def _zh_number_to_int(token: str) -> int | None:
        """中文数字（最多两位，常见时间表达）转整数。"""
        t = str(token or "").strip()
        if not t:
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
        if t == "十":
            return 10
        if "十" in t:
            left, right = t.split("十", 1)
            if left == "":
                tens = 1
            else:
                lv = mapping.get(left)
                if lv is None:
                    return None
                tens = lv
            if right == "":
                ones = 0
            else:
                ov = mapping.get(right)
                if ov is None:
                    return None
                ones = ov
            return tens * 10 + ones
        if all(ch in mapping for ch in t):
            # 常见一位数字，兼容「两」等写法
            if len(t) == 1:
                return mapping[t]
            # 保守处理，多位按逐位拼接（如 "一二" => 12）
            try:
                return int("".join(str(mapping[ch]) for ch in t))
            except Exception:
                return None
        return None

    @classmethod
    def _recent_complete_month_window_n(cls, period_desc: str) -> int | None:
        """
        解析相对月份窗口：最近/近 N 个月（完整月）。
        例如：最近三个月、近6个月、最近半年。
        """
        t = re.sub(r"\s+", "", str(period_desc or ""))
        if not t:
            return None
        if re.search(r"(最近|近)半年", t):
            return 6
        m_digit = re.search(r"(最近|近)(\d{1,2})个?月", t)
        if m_digit:
            n = int(m_digit.group(2))
            return n if 1 <= n <= 36 else None
        m_zh = re.search(r"(最近|近)([一二两三四五六七八九十]{1,3})个?月", t)
        if m_zh:
            n = cls._zh_number_to_int(m_zh.group(2))
            if n is not None and 1 <= n <= 36:
                return n
        return None

    @classmethod
    def _recent_n_complete_quarter_tags(cls, n: int) -> list[tuple[str, str]]:
        """
        最近 N 个完整季度（标准 Q1~Q4）：以当前所在季度为锚，向前回推已结束季度。
        例如当前在 2026-04（Q2）时，n=1 => Y2026,Q1；n=2 => Y2026,Q1 + Y2025,Q4。
        """
        tags: list[tuple[str, str]] = []
        today = date.today()
        y = today.year
        current_q = ((today.month - 1) // 3) + 1
        q = current_q - 1
        if q <= 0:
            q = 4
            y -= 1
        for _ in range(max(1, n)):
            tags.append((f"Y{y}", f"Q{q}"))
            q -= 1
            if q <= 0:
                q = 4
                y -= 1
        return tags

    @classmethod
    def _recent_complete_quarter_window_n(cls, period_desc: str) -> int | None:
        """
        解析相对季度窗口：最近/近 N 个季度（完整标准季度）。
        例如：最近一个季度、近两季度、最近2个季度。
        """
        t = re.sub(r"\s+", "", str(period_desc or ""))
        if not t:
            return None
        m_digit = re.search(r"(最近|近)(\d{1,2})个?季(?:度)?", t)
        if m_digit:
            n = int(m_digit.group(2))
            return n if 1 <= n <= 12 else None
        m_zh = re.search(r"(最近|近)([一二两三四五六七八九十]{1,3})个?季(?:度)?", t)
        if m_zh:
            n = cls._zh_number_to_int(m_zh.group(2))
            if n is not None and 1 <= n <= 12:
                return n
        # 未显式给数字时，默认 1 个季度（如“最近一个季度/近一季度/最近季度”）。
        if re.search(r"(最近|近)(一个|1个|一)?季(?:度)?", t):
            return 1
        return None

    @classmethod
    def _pm_time_filter_sql(cls, pm_query_spec: dict[str, Any] | None) -> str:
        if not isinstance(pm_query_spec, dict):
            return ""
        year_raw = str(pm_query_spec.get("year") or "").strip()
        quarter_raw = str(pm_query_spec.get("quarter") or "").strip().upper()
        month_raw = str(pm_query_spec.get("month") or "").strip().upper()
        period_desc = str(pm_query_spec.get("period_description") or "").strip()

        # 先处理相对季度（最近/近 N 个季度），避免被仅有 year 的条件“放大”为全年。
        recent_q_n = cls._recent_complete_quarter_window_n(period_desc)
        if recent_q_n is not None:
            yq = cls._recent_n_complete_quarter_tags(recent_q_n)
            by_year_q: dict[str, list[str]] = {}
            for y, q in yq:
                by_year_q.setdefault(y, []).append(q)
            or_parts_q: list[str] = []
            for y, quarters in by_year_q.items():
                if year_raw and re.match(r"Y20\d{2}$", year_raw, flags=re.I) and y != year_raw.upper():
                    continue
                quarter_in = ",".join(f"'{cls._sql_escape_literal(q)}'" for q in quarters)
                or_parts_q.append(f"(year = '{cls._sql_escape_literal(y)}' AND quarter IN ({quarter_in}))")
            if or_parts_q:
                return " AND (" + " OR ".join(or_parts_q) + ")"

        # 再处理相对月份窗口（最近/近 N 个月），避免被仅有 year 的条件“放大”为全年。
        recent_n = cls._recent_complete_month_window_n(period_desc)
        if recent_n is not None:
            ym = cls._recent_n_complete_month_tags(recent_n)
            by_year: dict[str, list[str]] = {}
            for y, m in ym:
                by_year.setdefault(y, []).append(m)
            or_parts: list[str] = []
            for y, months in by_year.items():
                # 若 query_spec 指定了年度，且与相对月份窗口跨年中的某年不一致，则跳过该年分支
                if year_raw and re.match(r"Y20\d{2}$", year_raw, flags=re.I) and y != year_raw.upper():
                    continue
                month_in = ",".join(f"'{cls._sql_escape_literal(m)}'" for m in months)
                or_parts.append(f"(year = '{cls._sql_escape_literal(y)}' AND month IN ({month_in}))")
            if or_parts:
                return " AND (" + " OR ".join(or_parts) + ")"

        # 形如“1-3月 / 1至3月 / 1到3月”也按月区间过滤。
        span = re.search(r"([1-9]|1[0-2])\s*月?\s*[-~到至]\s*([1-9]|1[0-2])\s*月", period_desc)
        if span:
            m1 = int(span.group(1))
            m2 = int(span.group(2))
            lo, hi = (m1, m2) if m1 <= m2 else (m2, m1)
            y = year_raw.upper() if re.match(r"Y20\d{2}$", year_raw, flags=re.I) else f"Y{date.today().year}"
            month_in = ",".join(f"'M{m:02d}'" for m in range(lo, hi + 1))
            return f" AND (year = '{cls._sql_escape_literal(y)}' AND month IN ({month_in}))"

        conds: list[str] = []
        if year_raw and re.match(r"Y20\d{2}$", year_raw, flags=re.I):
            conds.append(f"year = '{cls._sql_escape_literal(year_raw.upper())}'")
        if quarter_raw and re.match(r"Q[1-4]$", quarter_raw):
            conds.append(f"quarter = '{quarter_raw}'")
        if month_raw and re.match(r"M(0[1-9]|1[0-2])$", month_raw):
            conds.append(f"month = '{month_raw}'")

        if not conds:
            return ""
        return " AND " + " AND ".join(conds)

    def _analysis_fact_filters(self, state: AgentState | None, query: str) -> str:
        """compare / budget_summary 共用：科目范围 + 条线部门（与飞书/Web 规划 SQL 一致）。"""
        pm = state.get("pm_query_spec") if state is not None else None
        pm_dim_filters = self._dimension_filters_from_pm_query_spec(pm if isinstance(pm, dict) else None)
        pm_time_filter = self._pm_time_filter_sql(pm if isinstance(pm, dict) else None)
        # 仅当 PM 尚未锁定指标维（报告/数据）时，才回退到关键词启发式，避免覆盖结构化口径。
        keyword_metric_filter = "" if self._pm_has_metric_lock(pm if isinstance(pm, dict) else None) else self._compare_scope_from_query(query)
        dept_fallback_filter = self._dept_filter_sql_from_state(state, query)
        return f"{pm_dim_filters}{pm_time_filter}{keyword_metric_filter}{dept_fallback_filter}"

    @staticmethod
    def _current_compare_show_level_version(show_level: int = 1) -> int:
        """读取 common.db 中 compare 展示层当前配置版本（edit_show_sign=show_level）。"""
        cdb = common_db_path()
        if not cdb.exists():
            return 0
        try:
            with sqlite3.connect(cdb) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT version_id
                    FROM edit_show_version
                    WHERE edit_show_sign = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (int(show_level),),
                ).fetchone()
                if not row:
                    return 0
                return int(row["version_id"] or 0)
        except Exception:
            return 0

    def _compare_level_meta(self, show_level: int) -> dict[str, Any]:
        level = int(show_level or 0)
        if not (1 <= level <= 5):
            return {}
        selected_version = self._current_compare_show_level_version(level)
        if selected_version > 0:
            cpath = compare_db_path()
            if cpath.exists():
                try:
                    with sqlite3.connect(cpath) as conn:
                        conn.row_factory = sqlite3.Row
                        row = conn.execute(
                            """
                            SELECT source_year, source_version_id, source_version_name
                            FROM compare_budget_summary
                            WHERE show_level = ? AND source_version_id = ?
                            ORDER BY source_year DESC
                            LIMIT 1
                            """,
                            (level, selected_version),
                        ).fetchone()
                    if row:
                        return {
                            "show_level": level,
                            "source_year": int(row["source_year"] or 0),
                            "source_version_id": int(row["source_version_id"] or 0),
                            "source_version_name": str(row["source_version_name"] or "").strip(),
                        }
                except Exception:
                    pass
            return {
                "show_level": level,
                "source_year": 0,
                "source_version_id": int(selected_version),
                "source_version_name": "",
            }
        for sl, sy, sv, sn in self._load_compare_version_options():
            if int(sl) == level:
                return {
                    "show_level": level,
                    "source_year": int(sy or 0),
                    "source_version_id": int(sv or 0),
                    "source_version_name": str(sn or "").strip(),
                }
        return {}

    @staticmethod
    def _strip_year_constraints(scope_sql: str) -> str:
        """
        同比查询需要对“基准年/比较年”分别绑定，先移除统一时间过滤中的 year 约束，
        仅保留 month/quarter 与维度过滤，避免比较侧被锁死到基准年。
        """
        if not scope_sql:
            return ""
        s = str(scope_sql)
        s = re.sub(
            r"\(\s*year\s*=\s*'Y20\d{2}'\s+AND\s+(month|quarter)\s+IN\s*\(([^)]*)\)\s*\)",
            r"(\1 IN (\2))",
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(r"\s+AND\s+year\s*=\s*'Y20\d{2}'", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\(\s*year\s*=\s*'Y20\d{2}'\s*\)", "", s, flags=re.IGNORECASE)
        return s

    @staticmethod
    def _is_yoy_requested(query: str, clarified: dict[str, Any] | None) -> bool:
        ctype = str((clarified or {}).get("comparison_type") or "").strip().lower()
        return (
            ctype == "yoy"
            or bool(re.search(r"(同比|去年同期|对比去年|yoy)", query, flags=re.IGNORECASE))
            or AgentGraphService._is_explicit_year_comparison(query)
        )

    def _resolve_query_context(self, state: AgentState) -> dict[str, Any]:
        # 统一口径：机器人预算查询默认走 compare 库（L1 展示层）。
        cpath = compare_db_path()
        anchor = self._resolve_analysis_time_anchor(state)
        clarified = state.get("clarified_slots", {}) or {}
        pm_spec = state.get("pm_query_spec") if isinstance(state.get("pm_query_spec"), dict) else {}
        chosen_level = int(
            clarified.get("comparison_show_level")
            or pm_spec.get("__selected_compare_level__")
            or 0
        )
        show_level = chosen_level if 1 <= chosen_level <= 5 else 1
        yoy_requested = self._is_yoy_requested(str(state.get("user_query") or ""), clarified)
        base_level = 1
        compare_level = show_level if 1 <= show_level <= 5 else 1
        base_meta = self._compare_level_meta(base_level)
        compare_meta = self._compare_level_meta(compare_level)
        base_year_tag = f"Y{int(base_meta.get('source_year') or anchor['calendar_year'])}"
        compare_year_tag = f"Y{int(compare_meta.get('source_year') or (anchor['calendar_year'] - 1))}"
        base_version_id = int(base_meta.get("source_version_id") or self._current_compare_show_level_version(base_level) or 0)
        compare_version_id = int(
            compare_meta.get("source_version_id") or self._current_compare_show_level_version(compare_level) or 0
        )
        selected_version_id = compare_version_id if yoy_requested else base_version_id
        version_source = (
            f"compare.db|基准L{base_level}: {base_year_tag}/V{base_version_id}；"
            f"比较L{compare_level}: {compare_year_tag}/V{compare_version_id}"
        )
        if cpath.exists():
            return {
                "query_db_path": str(cpath),
                "query_db_year": int(anchor["calendar_year"]),
                "query_version_id": selected_version_id,
                "query_version_source": version_source,
                "query_data_source": "compare_l1",
                "query_show_level": compare_level if yoy_requested else base_level,
                "query_base_show_level": base_level,
                "query_compare_show_level": compare_level,
                "query_year_tag": base_year_tag,
                "query_base_year_tag": base_year_tag,
                "query_compare_year_tag": compare_year_tag,
                "query_base_version_id": base_version_id,
                "query_compare_version_id": compare_version_id,
                "query_month_tag": anchor.get("month_tag"),
            }
        yb = int(anchor["calendar_year"])
        return {
            "query_db_path": str(cpath),
            "query_db_year": yb,
            "query_version_id": selected_version_id,
            "query_version_source": "compare.db 缺失（当前要求仅使用 compare 库）",
            "query_data_source": "compare_l1",
            "query_show_level": compare_level if yoy_requested else base_level,
            "query_base_show_level": base_level,
            "query_compare_show_level": compare_level,
            "query_year_tag": base_year_tag,
            "query_base_year_tag": base_year_tag,
            "query_compare_year_tag": compare_year_tag,
            "query_base_version_id": base_version_id,
            "query_compare_version_id": compare_version_id,
            "query_month_tag": anchor.get("month_tag"),
        }

    def _suggest_sql_compare_l1(
        self,
        query: str,
        *,
        year_tag: str,
        month_tag: str | None,
        show_level: int,
        state: AgentState | None = None,
    ) -> str:
        scope = self._analysis_fact_filters(state, query)
        pm = state.get("pm_query_spec") if state is not None and isinstance(state.get("pm_query_spec"), dict) else None
        clarified = state.get("clarified_slots", {}) if state is not None else {}
        scope_has_time_filter = bool(re.search(r"\b(month|quarter)\s+in\s*\(|\b(month|quarter)\s*=", scope, flags=re.I))
        yoy_requested = self._is_yoy_requested(query, clarified)
        compare_level = int((clarified or {}).get("comparison_show_level") or show_level or 1)
        compare_level = compare_level if 1 <= compare_level <= 5 else 1
        base_level = 1
        base_year_tag = str((state or {}).get("query_base_year_tag") or year_tag or "").strip() or year_tag
        compare_year_tag = str((state or {}).get("query_compare_year_tag") or "").strip()
        if not compare_year_tag:
            meta = self._compare_level_meta(compare_level)
            compare_year = int(meta.get("source_year") or 0)
            if compare_year > 0:
                compare_year_tag = f"Y{compare_year}"
            else:
                m = re.search(r"Y(\d{4})", base_year_tag)
                by = int(m.group(1)) if m else date.today().year
                compare_year_tag = f"Y{max(by - 1, 2000)}"
        if yoy_requested:
            scope_yoy = self._strip_year_constraints(scope)
            gran = str((clarified or {}).get("granularity") or "").strip().lower()
            time_col = "month"
            if ("quarter" in gran) or re.search(r"(按季|季度)", query):
                time_col = "quarter"
            elif ("year" in gran) or (re.search(r"(按年|年度)", query) and not re.search(r"(按月|每月|月份|月度)", query)):
                time_col = "year"
            ms = f" AND month = '{month_tag}'" if (time_col == "month" and month_tag and not scope_has_time_filter) else ""
            base_where = f"show_level = {base_level} AND year = '{base_year_tag}'{ms}{scope_yoy}"
            compare_where = f"show_level = {compare_level} AND year = '{compare_year_tag}'{ms}{scope_yoy}"
            if "部门" in query:
                dim = "dept_level1"
            elif "科目" in query:
                dim = "data_code_name"
            elif "产品" in query:
                dim = "product_code_name"
            else:
                dim = ""
            dim_select = f"b.{dim}, " if dim else ""
            dim_group = f"{dim}, {time_col}" if dim else f"{time_col}"
            dim_join = f"b.{dim} = c.{dim} AND " if dim else ""
            order_by = f"b.{dim}, b.{time_col}" if dim else f"b.{time_col}"
            month_type_cols = (
                "CASE WHEN COALESCE(b.base_budget_actual, 0) = 1 THEN '实际' ELSE '预算' END AS '基准口径', "
                "CASE WHEN COALESCE(c.compare_budget_actual, 0) = 1 THEN '实际' ELSE '预算' END AS '比较口径', "
                if time_col == "month"
                else ""
            )
            return (
                "WITH base AS ("
                f"SELECT {dim_group}, SUM(value) AS base_value, MAX(budget_actual) AS base_budget_actual "
                f"FROM compare_budget_summary WHERE {base_where} "
                f"GROUP BY {dim_group}"
                "), cmp AS ("
                f"SELECT {dim_group}, SUM(value) AS compare_value, MAX(budget_actual) AS compare_budget_actual "
                f"FROM compare_budget_summary WHERE {compare_where} "
                f"GROUP BY {dim_group}"
                ") "
                f"SELECT {dim_select}b.{time_col}, "
                "COALESCE(b.base_value, 0) AS '基准值', "
                "COALESCE(c.compare_value, 0) AS '比较值', "
                f"{month_type_cols}"
                "COALESCE(b.base_value, 0) - COALESCE(c.compare_value, 0) AS '同比变化量', "
                "CASE "
                "WHEN ABS(COALESCE(c.compare_value, 0)) < 1e-9 THEN NULL "
                "ELSE ROUND((COALESCE(b.base_value, 0) - COALESCE(c.compare_value, 0)) / ABS(c.compare_value) * 100.0, 2) "
                "END AS '同比变化比例(%)' "
                "FROM base b LEFT JOIN cmp c "
                f"ON {dim_join}b.{time_col} = c.{time_col} "
                f"ORDER BY {order_by} "
                "LIMIT 5000"
            )
        comparison_type = str((clarified or {}).get("comparison_type") or "").strip().lower()
        compare_requested = bool(
            re.search(r"(预算.?实际|预实|差异|偏差|同比|环比|对比|比较|vs)", query)
            or comparison_type in {"budget_vs_actual", "yoy", "mom"}
        )
        prefer_report_agg = self._pm_report_locked_without_data(pm)
        report_scope_label = self._pm_report_scope_label(pm)
        report_scope_sql = (
            f"'{self._sql_escape_literal(report_scope_label)}' AS report_scope, "
            if report_scope_label
            else ""
        )
        ms = f" AND month = '{month_tag}'" if month_tag and not scope_has_time_filter else ""
        w = f"show_level = {int(show_level)} AND year = '{year_tag}'{ms}{scope}"
        if prefer_report_agg:
            if compare_requested or re.search(r"(预算.*实际.*两列|口径.*两列|分两列|并列展示|列展示)", query):
                if "部门" in query:
                    return (
                        f"SELECT {report_scope_sql}dept_level1, month, "
                        f"SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                        f"SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                        f"FROM compare_budget_summary WHERE {w} "
                        "GROUP BY dept_level1, month "
                        "ORDER BY dept_level1, month "
                        "LIMIT 5000"
                    )
                if "产品" in query:
                    return (
                        f"SELECT {report_scope_sql}product_code_name, month, "
                        f"SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                        f"SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                        f"FROM compare_budget_summary WHERE {w} "
                        "GROUP BY product_code_name, month "
                        "ORDER BY product_code_name, month "
                        "LIMIT 5000"
                    )
                return (
                    f"SELECT {report_scope_sql}month, "
                    f"SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                    f"SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                    f"FROM compare_budget_summary WHERE {w} "
                    "GROUP BY month "
                    "ORDER BY month "
                    "LIMIT 5000"
                )
            if "部门" in query:
                return (
                    f"SELECT {report_scope_sql}dept_level1, month, SUM(value) AS total_value "
                    f"FROM compare_budget_summary WHERE {w} "
                    "GROUP BY dept_level1, month "
                    "ORDER BY dept_level1, month "
                    "LIMIT 5000"
                )
            if "产品" in query:
                return (
                    f"SELECT {report_scope_sql}product_code_name, month, SUM(value) AS total_value "
                    f"FROM compare_budget_summary WHERE {w} "
                    "GROUP BY product_code_name, month "
                    "ORDER BY product_code_name, month "
                    "LIMIT 5000"
                )
            return (
                f"SELECT {report_scope_sql}month, SUM(value) AS total_value "
                f"FROM compare_budget_summary WHERE {w} "
                "GROUP BY month "
                "ORDER BY month "
                "LIMIT 5000"
            )
        if compare_requested or re.search(r"(预算.*实际.*两列|口径.*两列|分两列|并列展示|列展示)", query):
            if "部门" in query:
                return (
                    f"SELECT dept_level1, month, "
                    f"SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                    f"SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                    f"FROM compare_budget_summary WHERE {w} "
                    "GROUP BY dept_level1, month "
                    "ORDER BY dept_level1, month "
                    "LIMIT 5000"
                )
            if "科目" in query:
                return (
                    f"SELECT data_code_name, month, "
                    f"SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                    f"SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                    f"FROM compare_budget_summary WHERE {w} "
                    "GROUP BY data_code_name, month "
                    "ORDER BY data_code_name, month "
                    "LIMIT 5000"
                )
            return (
                f"SELECT month, "
                f"SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                f"SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                f"FROM compare_budget_summary WHERE {w} "
                "GROUP BY month "
                "ORDER BY month "
                "LIMIT 5000"
            )
        if "部门" in query:
            return (
                f"SELECT dept_level1, month, SUM(value) AS total_value "
                f"FROM compare_budget_summary WHERE {w} "
                "GROUP BY dept_level1, month "
                "ORDER BY dept_level1, month "
                "LIMIT 5000"
            )
        if "科目" in query:
            return (
                f"SELECT data_code_name, month, SUM(value) AS total_value "
                f"FROM compare_budget_summary WHERE {w} "
                "GROUP BY data_code_name, month "
                "ORDER BY data_code_name, month "
                "LIMIT 5000"
            )
        return (
            "SELECT data_code_name, product_code_name, month, SUM(value) AS total_value "
            f"FROM compare_budget_summary WHERE {w} "
            "GROUP BY data_code_name, product_code_name, month "
            "ORDER BY data_code_name, month "
            "LIMIT 5000"
        )

    def _suggest_sql(
        self,
        query: str,
        *,
        query_kind: str = "analysis",
        query_year: int,
        version_id: int,
        data_source: str = "budget",
        year_tag: str | None = None,
        month_tag: str | None = None,
        show_level: int = 1,
        state: AgentState | None = None,
    ) -> str:
        resolved_yt = (year_tag or f"Y{int(query_year)}").strip()
        mtag = (month_tag or "").strip() or None
        month_sql = f" AND month = '{mtag}'" if mtag else ""
        vfilter = f"version_id = {int(version_id)}"
        pm = state.get("pm_query_spec") if state is not None and isinstance(state.get("pm_query_spec"), dict) else None
        prefer_report_agg = self._pm_report_locked_without_data(pm)
        report_scope_label = self._pm_report_scope_label(pm)
        report_scope_sql = (
            f"'{self._sql_escape_literal(report_scope_label)}' AS report_scope, "
            if report_scope_label
            else ""
        )
        fact_extra = self._analysis_fact_filters(state, query) if query_kind == "analysis" else ""
        # 元数据与清单：按统一口径走 compare L1 展示层。
        if query_kind == "metadata":
            if data_source == "compare_l1":
                w_meta = f"show_level = {int(show_level)} AND year = '{resolved_yt}'{month_sql}"
                wants_list = bool(re.search(r"(列出来|清单|列表|明细|名称|有哪些|全部)", query))
                if "部门" in query:
                    if wants_list:
                        return (
                            "SELECT DISTINCT COALESCE(dept_level3, dept_level2, dept_level1) AS dept_name "
                            "FROM compare_budget_summary "
                            f"WHERE {w_meta} AND COALESCE(dept_level3, dept_level2, dept_level1) IS NOT NULL "
                            "ORDER BY dept_name "
                            "LIMIT 5000"
                        )
                    return (
                        "SELECT COUNT(DISTINCT COALESCE(dept_level3, dept_level2, dept_level1)) AS dept_count "
                        "FROM compare_budget_summary "
                        f"WHERE {w_meta} AND COALESCE(dept_level3, dept_level2, dept_level1) IS NOT NULL "
                        "LIMIT 1"
                    )
                if "产品" in query:
                    if wants_list:
                        return (
                            "SELECT DISTINCT product_code_name "
                            "FROM compare_budget_summary "
                            f"WHERE {w_meta} AND product_code_name IS NOT NULL AND TRIM(product_code_name) != '' "
                            "ORDER BY product_code_name "
                            "LIMIT 5000"
                        )
                    return (
                        "SELECT COUNT(DISTINCT product_code_name) AS product_count "
                        "FROM compare_budget_summary "
                        f"WHERE {w_meta} AND product_code_name IS NOT NULL AND TRIM(product_code_name) != '' "
                        "LIMIT 1"
                    )
                if "科目" in query:
                    if wants_list:
                        return (
                            "SELECT DISTINCT data_code_name "
                            "FROM compare_budget_summary "
                            f"WHERE {w_meta} AND data_code_name IS NOT NULL AND TRIM(data_code_name) != '' "
                            "ORDER BY data_code_name "
                            "LIMIT 5000"
                        )
                    return (
                        "SELECT COUNT(DISTINCT data_code_name) AS acct_count "
                        "FROM compare_budget_summary "
                        f"WHERE {w_meta} AND data_code_name IS NOT NULL AND TRIM(data_code_name) != '' "
                        "LIMIT 1"
                    )
                return (
                    "SELECT COUNT(*) AS total_rows "
                    "FROM compare_budget_summary "
                    f"WHERE {w_meta} "
                    "LIMIT 1"
                )
            wants_list = bool(re.search(r"(列出来|清单|列表|明细|名称|有哪些|全部)", query))
            if "部门" in query:
                if wants_list:
                    return (
                        "SELECT DISTINCT COALESCE(dept_level3, dept_level2, dept_level1) AS dept_name "
                        "FROM budget_summary "
                        f"WHERE {vfilter} AND COALESCE(dept_level3, dept_level2, dept_level1) IS NOT NULL "
                        "ORDER BY dept_name "
                        "LIMIT 5000"
                    )
                return (
                    "SELECT COUNT(DISTINCT COALESCE(dept_level3, dept_level2, dept_level1)) AS dept_count "
                    "FROM budget_summary "
                    f"WHERE {vfilter} AND COALESCE(dept_level3, dept_level2, dept_level1) IS NOT NULL "
                    "LIMIT 1"
                )
            if "产品" in query:
                if wants_list:
                    return (
                        "SELECT DISTINCT product_code_name "
                        "FROM budget_summary "
                        f"WHERE {vfilter} AND product_code_name IS NOT NULL AND TRIM(product_code_name) != '' "
                        "ORDER BY product_code_name "
                        "LIMIT 5000"
                    )
                return (
                    "SELECT COUNT(DISTINCT product_code_name) AS product_count "
                    "FROM budget_summary "
                    f"WHERE {vfilter} AND product_code_name IS NOT NULL AND TRIM(product_code_name) != '' "
                    "LIMIT 1"
                )
            if "科目" in query:
                if wants_list:
                    return (
                        "SELECT DISTINCT data_code_name "
                        "FROM budget_summary "
                        f"WHERE {vfilter} AND data_code_name IS NOT NULL AND TRIM(data_code_name) != '' "
                        "ORDER BY data_code_name "
                        "LIMIT 5000"
                    )
                return (
                    "SELECT COUNT(DISTINCT data_code_name) AS acct_count "
                    "FROM budget_summary "
                    f"WHERE {vfilter} AND data_code_name IS NOT NULL AND TRIM(data_code_name) != '' "
                    "LIMIT 1"
                )
            return (
                "SELECT COUNT(*) AS total_rows "
                "FROM budget_summary "
                f"WHERE {vfilter} "
                "LIMIT 1"
            )
        if data_source == "compare_l1" and query_kind == "analysis":
            return self._suggest_sql_compare_l1(
                query,
                year_tag=resolved_yt,
                month_tag=mtag,
                show_level=show_level,
                state=state,
            )
        if prefer_report_agg:
            if re.search(r"(预算.*实际.*两列|口径.*两列|分两列|并列展示|列展示)", query):
                if "部门" in query:
                    return (
                        f"SELECT {report_scope_sql}dept_level1, month, "
                        "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                        "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                        "FROM budget_summary "
                        f"WHERE {vfilter}{fact_extra} AND year = '{resolved_yt}'{month_sql} "
                        "GROUP BY dept_level1, month "
                        "ORDER BY dept_level1, month "
                        "LIMIT 5000"
                    )
                if "产品" in query:
                    return (
                        f"SELECT {report_scope_sql}product_code_name, month, "
                        "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                        "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                        "FROM budget_summary "
                        f"WHERE {vfilter}{fact_extra} AND year = '{resolved_yt}'{month_sql} "
                        "GROUP BY product_code_name, month "
                        "ORDER BY product_code_name, month "
                        "LIMIT 5000"
                    )
                return (
                    f"SELECT {report_scope_sql}month, "
                    "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                    "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                    "FROM budget_summary "
                    f"WHERE {vfilter}{fact_extra} AND year = '{resolved_yt}'{month_sql} "
                    "GROUP BY month "
                    "ORDER BY month "
                    "LIMIT 5000"
                )
            if "部门" in query:
                return (
                    f"SELECT {report_scope_sql}dept_level1, month, budget_actual, SUM(value) AS total_value "
                    "FROM budget_summary "
                    f"WHERE {vfilter}{fact_extra} AND year = '{resolved_yt}'{month_sql} "
                    "GROUP BY dept_level1, month, budget_actual "
                    "ORDER BY dept_level1, month "
                    "LIMIT 5000"
                )
            if "产品" in query:
                return (
                    f"SELECT {report_scope_sql}product_code_name, month, budget_actual, SUM(value) AS total_value "
                    "FROM budget_summary "
                    f"WHERE {vfilter}{fact_extra} AND year = '{resolved_yt}'{month_sql} "
                    "GROUP BY product_code_name, month, budget_actual "
                    "ORDER BY product_code_name, month "
                    "LIMIT 5000"
                )
            return (
                f"SELECT {report_scope_sql}month, budget_actual, SUM(value) AS total_value "
                "FROM budget_summary "
                f"WHERE {vfilter}{fact_extra} AND year = '{resolved_yt}'{month_sql} "
                "GROUP BY month, budget_actual "
                "ORDER BY month "
                "LIMIT 5000"
            )
        if re.search(r"(预算.*实际.*两列|口径.*两列|分两列|并列展示|列展示)", query):
            if "部门" in query:
                return (
                    "SELECT dept_level1, month, "
                    "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                    "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                    "FROM budget_summary "
                    f"WHERE {vfilter}{fact_extra} AND year = '{resolved_yt}'{month_sql} "
                    "GROUP BY dept_level1, month "
                    "ORDER BY dept_level1, month "
                    "LIMIT 5000"
                )
            if "科目" in query:
                return (
                    "SELECT data_code_name, month, "
                    "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                    "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                    "FROM budget_summary "
                    f"WHERE {vfilter}{fact_extra} AND year = '{resolved_yt}'{month_sql} "
                    "GROUP BY data_code_name, month "
                    "ORDER BY data_code_name, month "
                    "LIMIT 5000"
                )
            return (
                "SELECT month, "
                "SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值', "
                "SUM(CASE WHEN budget_actual = 1 THEN value ELSE 0 END) AS '实际值' "
                "FROM budget_summary "
                f"WHERE {vfilter}{fact_extra} AND year = '{resolved_yt}'{month_sql} "
                "GROUP BY month "
                "ORDER BY month "
                "LIMIT 5000"
            )
        if "部门" in query:
            return (
                "SELECT dept_level1, month, budget_actual, SUM(value) AS total_value "
                "FROM budget_summary "
                f"WHERE {vfilter}{fact_extra} AND year = '{resolved_yt}'{month_sql} "
                "GROUP BY dept_level1, month, budget_actual "
                "ORDER BY dept_level1, month "
                "LIMIT 5000"
            )
        if "科目" in query:
            return (
                "SELECT data_code_name, month, budget_actual, SUM(value) AS total_value "
                "FROM budget_summary "
                f"WHERE {vfilter}{fact_extra} AND year = '{resolved_yt}'{month_sql} "
                "GROUP BY data_code_name, month, budget_actual "
                "ORDER BY data_code_name, month "
                "LIMIT 5000"
            )
        return (
            "SELECT month, budget_actual, SUM(value) AS total_value "
            "FROM budget_summary "
            f"WHERE {vfilter}{fact_extra} AND year = '{resolved_yt}'{month_sql} "
            "GROUP BY month, budget_actual "
            "ORDER BY month "
            "LIMIT 5000"
        )

    @classmethod
    def _pm_locked_report_anchor_level(cls, pm: dict[str, Any] | None) -> int | None:
        """
        已锁定报告科目在 report_account 中的最浅 level（1-5）；无法解析到目录则 None。
        多科目锁定时取 min(level)，行区从该层展开到 5 级 + 数据科目。
        """
        if not isinstance(pm, dict):
            return None
        path = common_db_path()
        if not path.is_file():
            return None
        levels: list[int] = []
        try:
            conn = sqlite3.connect(str(path))
            cur = conn.cursor()
            for it in pm.get("report_accounts") or []:
                if not isinstance(it, dict):
                    continue
                c = str(it.get("code") or "").strip()
                n = str(it.get("name") or "").strip()
                row = None
                if c:
                    cur.execute("SELECT level FROM report_account WHERE report_acct_code = ?", (c,))
                    row = cur.fetchone()
                elif n:
                    cur.execute("SELECT level FROM report_account WHERE report_acct_name = ?", (n,))
                    row = cur.fetchone()
                if row is not None:
                    lv = int(row[0] or 0)
                    if 1 <= lv <= 5:
                        levels.append(lv)
            conn.close()
        except Exception:
            return None
        if not levels:
            return None
        return min(levels)

    @staticmethod
    def _pivot_search_codes_from_pm(pm: dict[str, Any] | None) -> str:
        """仅取 query_spec 中报告/数据科目的 code，供透视表搜索框做 OR 过滤（空格连接）。"""
        if not isinstance(pm, dict):
            return ""
        out: list[str] = []
        seen: set[str] = set()
        for key in ("report_accounts", "data_accounts"):
            for it in pm.get(key) or []:
                if not isinstance(it, dict):
                    continue
                c = str(it.get("code") or "").strip()
                if c and c not in seen:
                    seen.add(c)
                    out.append(c)
        return " ".join(out)

    @staticmethod
    def _first_locked_dim_token(entries: Any) -> str:
        """优先返回 name，其次 code；供前端在页字段选项中做模糊匹配。"""
        if not isinstance(entries, list):
            return ""
        for it in entries:
            if not isinstance(it, dict):
                continue
            c = str(it.get("code") or "").strip()
            n = str(it.get("name") or "").strip()
            if n:
                return n
            if c:
                return c
        return ""

    @staticmethod
    def _version_selection_token_from_query(query: str, query_version_id: int) -> str:
        """
        版本筛选 token（供前端 version_display 选项模糊匹配）：
        - 优先取问句中的显式版本号
        - 其次取上下文版本 ID
        """
        q = query or ""
        m = re.search(r"(?:版本(?:号|id)?|version)\s*[:：#]?\s*(\d{1,8})", q, flags=re.IGNORECASE)
        if not m:
            m = re.search(r"\bV\s*[:：#]?\s*(\d{1,8})\b", q, flags=re.IGNORECASE)
        if m:
            return f"版本号：{int(m.group(1))}"
        if int(query_version_id or 0) > 0:
            return f"版本号：{int(query_version_id)}"
        return "全部"

    @staticmethod
    def _version_selection_token_from_id(query_version_id: int) -> str:
        if int(query_version_id or 0) > 0:
            return f"版本号：{int(query_version_id)}"
        return "全部"

    def _pivot_suggestion_row_field_ids(self, pm: dict[str, Any] | None, query: str) -> list[str]:
        p = pm if isinstance(pm, dict) else {}
        anchor = self._pm_locked_report_anchor_level(p)
        if anchor is not None:
            return [f"report_level{i}" for i in range(anchor, 6)] + ["data_code_name"]
        if self._norm_code_name_list(p.get("data_accounts")):
            return ["data_code_name"]
        if self._norm_code_name_list(p.get("departments")):
            return ["dept_level1", "dept_level2", "dept_level3"]
        if self._norm_code_name_list(p.get("products")):
            return ["product_code_name"]
        return [f"report_level{i}" for i in range(1, 6)] + ["data_code_name"]

    @staticmethod
    def _pivot_suggestion_column_field_ids(query: str, clarified: dict[str, Any] | None) -> list[str]:
        cl = clarified or {}
        g = str(cl.get("granularity", "") or "")
        if "quarter" in g or re.search(r"(按季|季度)", query):
            return ["quarter", "budget_actual"]
        if ("year" in g or re.search(r"(按年|各年度|分年|年度汇总|多年度)", query)) and not re.search(
            r"(按月|每月|分月|月度|月份|近.*个月|未来.*个月)", query
        ):
            return ["year", "budget_actual"]
        return ["month", "budget_actual"]

    @staticmethod
    def _pivot_suggestion_page_field_ids(pm: dict[str, Any] | None) -> list[str]:
        p = pm if isinstance(pm, dict) else {}
        page_fields: list[str] = ["year", "version_display"]
        if AgentGraphService._norm_code_name_list(p.get("departments")):
            page_fields.extend(["dept_level1", "dept_level2", "dept_level3"])
        if AgentGraphService._norm_code_name_list(p.get("products")):
            page_fields.append("product_code_name")
        return list(dict.fromkeys(page_fields))

    @staticmethod
    def _normalize_dept_token_for_pivot(token: str) -> str:
        t = re.sub(r"\s+", "", str(token or "").strip())
        if not t:
            return ""
        for sfx in ("部门", "事业部", "业务条线", "条线", "部"):
            if t.endswith(sfx) and len(t) > len(sfx):
                return t[: -len(sfx)]
        return t

    def _build_pivot_suggestion(self, state: AgentState) -> dict[str, Any] | None:
        if str(state.get("intent_type", "general")) != "budget":
            return None
        if str(state.get("budget_query_kind", "analysis") or "analysis") != "analysis":
            return None

        query = str(state.get("user_query", "") or "")
        clarified: dict[str, Any] = state.get("clarified_slots", {}) or {}
        pm = state.get("pm_query_spec") if isinstance(state.get("pm_query_spec"), dict) else {}
        row_field_ids = self._pivot_suggestion_row_field_ids(pm, query)
        column_field_ids = self._pivot_suggestion_column_field_ids(query, clarified)
        page_field_ids = self._pivot_suggestion_page_field_ids(pm)
        value_field_ids = ["value"]
        qy = int(state.get("query_db_year") or settings.budget_year)
        qver = int(state.get("query_version_id") or 0)
        qver_base = int(state.get("query_base_version_id") or 0)
        qds = str(state.get("query_data_source") or "budget")
        qsl = int(state.get("query_show_level") or 1)
        qbase_ytag = str(state.get("query_base_year_tag") or "").strip()
        if qds == "compare_l1" and qver <= 0:
            qver = self._current_compare_show_level_version(qsl if qsl > 0 else 1)
        ytag = str(state.get("query_year_tag") or "").strip() or f"Y{qy}"
        if qds == "compare_l1":
            if qbase_ytag:
                ytag = qbase_ytag
            if qver_base > 0:
                qver = qver_base
        dept_token = self._first_locked_dim_token(pm.get("departments") if isinstance(pm, dict) else None)
        dept_token = self._normalize_dept_token_for_pivot(dept_token)
        product_token = self._first_locked_dim_token(pm.get("products") if isinstance(pm, dict) else None)
        page_selections: dict[str, str] = {
            "year": ytag,
            # 同比透视页字段必须与基准期间对齐，避免“基准年度 + 比较版本”导致空结果。
            "version_display": (
                self._version_selection_token_from_id(qver)
                if qds == "compare_l1"
                else self._version_selection_token_from_query(query, qver)
            ),
        }
        if dept_token:
            for dept_field in ("dept_level1", "dept_level2", "dept_level3"):
                if dept_field in page_field_ids:
                    page_selections[dept_field] = dept_token
        if product_token:
            page_selections["product_code_name"] = product_token
        pivot_cfg = self.runtime_config.get("pivot", {})
        base_conf = float(pivot_cfg.get("base_confidence", 0.6))
        pivot_search_text = self._pivot_search_codes_from_pm(pm)
        conf = min(0.95, base_conf + 0.1 + (0.04 if pivot_search_text else 0.0))
        reason_bits = [
            "行按已锁报告最浅层展开到末级+数据科目（或仅数据/部门/产品）",
            "列为时间 + 预算/实际",
            "页为年度 + 版本号及名称（并按已锁部门/产品自动加页筛选）",
        ]
        if pivot_search_text:
            reason_bits.append("已预填报告/数据 code 到透视搜索框")
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
            "confidence": round(max(conf, 0.0), 2),
        }

    @staticmethod
    def _should_recommend_pivot(
        state: AgentState,
        pivot_suggestion: dict[str, Any] | None,
        pivot_cfg: dict[str, Any] | None = None,
    ) -> bool:
        if not pivot_suggestion:
            return False
        cfg = pivot_cfg or {}
        # 需求更新：预算分析类问题默认可全量开启；可通过配置关闭。
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

    def _build_plan_reply_options(self, state: AgentState, recommend_pivot: bool) -> list[dict[str, str]]:
        """在查询规划完成后给出后续动作：分析类按需建议透视，元数据类仅建议 SQL。"""
        sql_opt = {"id": "sql_query", "label": "1）执行只读 SQL 查询（按当前规划口径）"}
        qk = str(state.get("budget_query_kind", "analysis") or "analysis")
        if qk == "metadata" or not recommend_pivot:
            return [sql_opt]
        pivot_opt = {"id": "open_pivot_table", "label": "2）打开数据透视表，自行拖拽行列与筛选查看"}
        both_opt = {
            "id": "sql_and_pivot",
            "label": "3）两者都做：执行 SQL 并打开数据透视表",
        }
        if bool(state.get("prefer_pivot_view", False)):
            # 用户已明确要透视表时，默认把透视相关选项前置。
            return [pivot_opt, both_opt, sql_opt]
        return [sql_opt, pivot_opt, both_opt]

    def _append_reply_options_footer(self, reply: str, options: list[dict[str, str]]) -> str:
        if not options:
            return reply
        lines = "\n".join(f"{o.get('label', '')}" for o in options if o.get("label"))
        return (
            f"{reply.rstrip()}\n\n"
            "---\n"
            "**请选择下一步：**\n"
            f"{lines}\n\n"
            "你也可以使用本条回复下方的按钮直接操作。"
        )

    def _plan_query(self, state: AgentState) -> AgentState:
        query = self._effective_query(state)
        query_kind = str(state.get("budget_query_kind", "analysis") or "analysis")
        qctx = self._resolve_query_context(state)
        query_year = int(qctx.get("query_db_year") or settings.budget_year)
        version_id = int(qctx.get("query_version_id") or 0)
        data_src = str(qctx.get("query_data_source") or "budget")
        ytag = str(qctx.get("query_year_tag") or f"Y{query_year}")
        mtag = qctx.get("query_month_tag")
        mtag_str = str(mtag).strip() if mtag is not None else None
        sl = int(qctx.get("query_show_level") or 1)
        clarified_slots = state.get("clarified_slots", {}) or {}
        selected_compare_level = int(clarified_slots.get("comparison_show_level") or 0)
        yoy_requested = self._is_yoy_requested(query, clarified_slots if isinstance(clarified_slots, dict) else {})
        if data_src == "compare_l1":
            qdb = str(qctx.get("query_db_path") or "").strip()
            if not qdb or not Path(qdb).exists():
                return {
                    "next_action": "plan_query",
                    "need_clarification": True,
                    "suggested_sql": None,
                    "reply": (
                        "当前要求使用 compare 多年度对比库查询，但尚未检测到 compare.db。\n"
                        "请先在系统中完成 compare 同步（或刷新 compare 数据）后再执行查询。"
                    ),
                    "reply_options": [],
                    "pivot_suggestion": None,
                    "wants_execute": False,
                    **qctx,
                }
        suggested_sql = self._suggest_sql(
            query,
            query_kind=query_kind,
            query_year=query_year,
            version_id=version_id,
            data_source=data_src,
            year_tag=ytag,
            month_tag=mtag_str,
            show_level=sl,
            state=state,
        )
        pm_query_spec = state.get("pm_query_spec") if isinstance(state.get("pm_query_spec"), dict) else None
        missing_dims = (
            self._sql_missing_pm_dimensions(suggested_sql, pm_query_spec)
            if query_kind == "analysis" and pm_query_spec
            else []
        )
        if missing_dims:
            miss_txt = "、".join(missing_dims)
            guard_reply = (
                "为避免口径偏离，系统在执行前做了维度一致性校验。\n\n"
                f"检测到当前 SQL 尚未完整覆盖已锁定维度：{miss_txt}。\n"
                "请补充或确认上述维度后，我将按同一口径重新生成 SQL 并执行。"
            )
            return {
                "next_action": "plan_query",
                "need_clarification": True,
                "suggested_sql": None,
                "reply": guard_reply,
                "reply_options": [],
                "pivot_suggestion": None,
                "wants_execute": False,
                **qctx,
            }
        confirm_hint = "请回复“确认执行”后开始执行查询。"
        locked_block = format_query_spec_locked_dimensions_block(
            state.get("pm_query_spec") if isinstance(state.get("pm_query_spec"), dict) else None
        )
        period_desc = ""
        pm_query_spec_for_period = state.get("pm_query_spec") if isinstance(state.get("pm_query_spec"), dict) else {}
        if isinstance(pm_query_spec_for_period, dict):
            period_desc = str(pm_query_spec_for_period.get("period_description") or "").strip()
        base_period_text = f"{str(qctx.get('query_base_year_tag') or ytag)}{(' ' + period_desc) if period_desc else ''}".strip()
        compare_period_text = f"{str(qctx.get('query_compare_year_tag') or '')}{(' ' + period_desc) if period_desc else ''}".strip()
        compare_locked_block = ""
        compare_plan_block = ""
        if data_src == "compare_l1" and yoy_requested and 1 <= selected_compare_level <= 5:
            compare_locked_block = (
                "## 同比期间\n"
                f"- 基准期间：{base_period_text}\n"
                f"- 比较期间：{compare_period_text}\n"
            )
            compare_plan_block = (
                "## 查询规划要点（同比）\n"
                f"1. 基准区间按 {base_period_text} 聚合；\n"
                f"2. 比较区间按 {compare_period_text} 聚合；\n"
                "3. 输出包含：基准值、比较值、同比变化量、同比变化比例(%)。"
            )
        fallback_reply = (
            "我已根据你的描述完成查询规划，下一步可直接执行只读查询。\n\n"
            f"查询上下文：{qctx.get('query_version_source')}；年度={query_year}；版本ID={version_id}\n\n"
            "打开数据透视表时，将按已锁维度自动配置：\n"
            "- 行：报告层级（从锁定层到末级）+ 数据科目，或仅数据/部门/产品；\n"
            "- 列：时间（月或季或年）+ 预算/实际；\n"
            "- 页：年度 + 版本号及名称；并预填报告/数据科目 code 到透视搜索。\n\n"
            f"如你确认当前口径，可直接回复“按默认假设执行”或点击“按当前口径重跑”开始分析。\n{confirm_hint}"
        )
        reply = self._llm_rewrite(
            "plan_query",
            {
                "query": query,
                "slot_status": state.get("slot_status", {}),
                "suggested_sql": suggested_sql,
                "query_context": qctx,
                "locked_dimensions_markdown": locked_block,
                "comparison_period_markdown": compare_locked_block,
            },
            fallback_reply,
        )
        if locked_block:
            # 固定仅注入一次，避免 LLM 改写与 fallback 拼装造成重复展示。
            locked_header = "## 已锁定的查询维度"
            rtxt = reply or ""
            first_pos = rtxt.find(locked_header)
            if first_pos >= 0:
                second_pos = rtxt.find(locked_header, first_pos + len(locked_header))
                if second_pos >= 0:
                    rtxt = rtxt[:second_pos].rstrip()
                reply = rtxt
            if locked_header not in (reply or ""):
                reply = f"{locked_block}\n\n{(reply or '').lstrip()}"
        if "确认执行" not in reply and "开始执行查询" not in reply:
            reply = f"{reply.rstrip()}\n\n{confirm_hint}"
        if compare_locked_block and "## 同比期间" not in reply:
            reply = f"{compare_locked_block}\n\n{reply.lstrip()}"
        if compare_plan_block and "## 查询规划要点（同比）" not in reply:
            reply = f"{compare_plan_block}\n\n{reply.lstrip()}"
        if data_src == "compare_l1" and 1 <= selected_compare_level <= 5:
            choose_hint = self._compare_version_choice_hint(selected_compare_level)
            if choose_hint and "已选择同比版本：" not in reply:
                reply = f"{choose_hint}\n\n{reply.lstrip()}"
        pivot_cfg = self.runtime_config.get("pivot", {})
        state_for_pivot: AgentState = {**state, **qctx}
        pivot_suggestion = self._build_pivot_suggestion(state_for_pivot)
        recommend_pivot = self._should_recommend_pivot(state_for_pivot, pivot_suggestion, pivot_cfg=pivot_cfg)
        reply_options = self._build_plan_reply_options(state_for_pivot, recommend_pivot=recommend_pivot)
        # 透视说明仅由前端「管衡推荐透视视角」卡片展示 pivot_suggestion.explanation，避免正文重复。
        reply = self._append_reply_options_footer(reply, reply_options)
        return {
            "next_action": "plan_query",
            "need_clarification": False,
            "suggested_sql": suggested_sql,
            "reply": reply,
            "reply_options": reply_options,
            "pivot_suggestion": pivot_suggestion if recommend_pivot else None,
            **qctx,
        }

    def _execute_query(self, state: AgentState) -> AgentState:
        sql = (state.get("suggested_sql") or "").strip()
        pivot_cfg = self.runtime_config.get("pivot", {})
        should_open_pivot = bool(
            bool(pivot_cfg.get("auto_open_on_execute_when_preferred", True))
            and state.get("prefer_pivot_view", False)
            and str(state.get("budget_query_kind", "analysis") or "analysis") == "analysis"
        )
        if not sql:
            return {
                "next_action": "execute_query",
                "executed_result": None,
                "reply": "当前没有可执行 SQL，请先完成查询规划。",
                "reply_options": [],
                "open_pivot_table": False,
            }
        try:
            qdb = state.get("query_db_path")
            qver = int(state.get("query_version_id") or 0)
            qds = str(state.get("query_data_source") or "budget")
            qsl = int(state.get("query_show_level") or 0)
            qbase_sl = int(state.get("query_base_show_level") or 1)
            qcmp_sl = int(state.get("query_compare_show_level") or qsl or 1)
            if qds == "compare_l1":
                forced_levels: int | list[int]
                if qcmp_sl > 0 and qcmp_sl != qbase_sl:
                    forced_levels = [qbase_sl, qcmp_sl]
                else:
                    forced_levels = qsl if qsl > 0 else 1
                result = self.query_executor.execute(
                    sql,
                    budget_db_path=Path(str(qdb)) if qdb else None,
                    forced_version_id=None,
                    forced_show_level=forced_levels,
                    sql_profile="compare",
                )
            else:
                result = self.query_executor.execute(
                    sql,
                    budget_db_path=Path(str(qdb)) if qdb else None,
                    forced_version_id=qver if qver > 0 else None,
                    sql_profile="budget",
                )
            row_count = result.get("row_count", 0)
            display_preview = result.get("display_preview_rows", [])
            quality_note = result.get("data_quality_note", "")
            history = state.get("history", [])
            query = state.get("user_query", "")
            allow_repeat = bool(re.search(r"(重新总结|再次分析|完整分析|复述|再说一遍)", query))
            # 默认不向重写模型注入上一轮助手文本，避免跨轮“口径/对象”串场。
            # 仅当用户明确要求“再次总结/复述”时，才复用少量近期上下文。
            recent_assistant_msgs = (
                [
                    m.get("content", "").strip()
                    for m in history[-8:]
                    if m.get("role") == "assistant" and m.get("content", "").strip()
                ][-3:]
                if allow_repeat
                else []
            )
            fallback_reply = (
                f"已执行只读查询，返回 {row_count} 行结果。"
                "\n\n我先给出摘要："
                f"\n- 返回结果条数：{row_count}"
                f"\n- 数据说明：{quality_note}"
                f"\n- 样例前{min(3, len(display_preview))}行：{display_preview[:3]}"
            )
            reply = self._llm_rewrite(
                "analysis_from_sql_result",
                {
                    "user_query": query,
                    "row_count": row_count,
                    "显示字段": result.get("display_columns", []),
                    "样例数据": display_preview[:8],
                    "数据说明": quality_note,
                    "recent_assistant_context": recent_assistant_msgs,
                    "allow_repeat_analysis": allow_repeat,
                    "instruction": (
                        "若用户本轮是调整展示格式/排版请求，请重点说明新版展示结构和关键结果，"
                        "不要重复上一轮已讲过的完整分析结论。"
                        "严格以当前 user_query 与本次 SQL 返回样例为边界，不要引用上一轮业务对象、科目或标题。"
                        "在正文中引用结果数值时，金额统一使用千分位并保留2位小数；"
                        "百分比统一保留2位小数并带 %。"
                    ),
                },
                fallback_reply,
            )
            # 预算工具金额单位统一使用“亿元”，避免 LLM 偶发输出“万元”。
            reply = re.sub(r"万元", "亿元", str(reply or ""))
            pivot_for_open = self._build_pivot_suggestion(state) if should_open_pivot else None
            return {
                "next_action": "execute_query",
                "executed_result": result,
                "reply": reply,
                "reply_options": [],
                "open_pivot_table": should_open_pivot,
                "pivot_suggestion": pivot_for_open,
            }
        except Exception as e:
            return {
                "next_action": "execute_query",
                "executed_result": None,
                "reply": f"查询执行失败：{e}",
                "reply_options": [],
                "open_pivot_table": False,
                "pivot_suggestion": None,
            }

    def _save_memory(self, state: AgentState) -> AgentState:
        summary = state.get("reply", "")
        final_requirement = {
            "slot_status": state.get("slot_status", {}),
            "missing_slots": state.get("missing_slots", []),
            "clarified_slots": state.get("clarified_slots", {}),
            "assumptions": state.get("assumptions", []),
        }
        pivot_config = {
            "rows": ["dept_level1" if "部门" in state.get("user_query", "") else "data_code_name"],
            "columns": ["month"],
            "pages": ["budget_actual", "version_name"],
            "filters": {
                "year": (state.get("clarified_slots", {}) or {}).get("time_period", "Y2026"),
            },
        }
        memory_id = self.memory_store.append(
            user_query=state.get("user_query", ""),
            intent_type=state.get("intent_type", "budget"),
            next_action=state.get("next_action", ""),
            suggested_sql=state.get("suggested_sql"),
            analysis_summary=summary,
            executed_result=state.get("executed_result"),
            final_requirement=final_requirement,
            pivot_config=pivot_config,
            clarification_rounds=int(state.get("clarification_rounds", 0)),
        )
        return {"memory_id": memory_id}

    def _route_after_intent(self, state: AgentState) -> str:
        return "general_answer" if state.get("intent_type") == "general" else "kb_context"

    def _route_after_requirement(self, state: AgentState) -> str:
        return "clarify" if state.get("need_clarification") else "plan_query"

    def _route_after_plan(self, state: AgentState) -> str:
        return "execute_query" if state.get("wants_execute") else "save_memory"

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("intent_router", self._intent_router)
        builder.add_node("general_answer", self._general_answer)
        builder.add_node("kb_context", self._kb_context)
        builder.add_node("requirement_check", self._requirement_check)
        builder.add_node("clarify", self._clarify)
        builder.add_node("plan_query", self._plan_query)
        builder.add_node("execute_query", self._execute_query)
        builder.add_node("save_memory", self._save_memory)

        builder.add_edge(START, "intent_router")
        builder.add_conditional_edges(
            "intent_router",
            self._route_after_intent,
            {"general_answer": "general_answer", "kb_context": "kb_context"},
        )
        builder.add_edge("kb_context", "requirement_check")
        builder.add_conditional_edges(
            "requirement_check",
            self._route_after_requirement,
            {"clarify": "clarify", "plan_query": "plan_query"},
        )
        builder.add_conditional_edges(
            "plan_query",
            self._route_after_plan,
            {"execute_query": "execute_query", "save_memory": "save_memory"},
        )
        builder.add_edge("execute_query", "save_memory")
        builder.add_edge("general_answer", END)
        builder.add_edge("clarify", END)
        builder.add_edge("save_memory", END)
        return builder.compile()

    def _invoke_fallback_from_state(self, state: AgentState) -> dict[str, Any]:
        s: AgentState = dict(state)
        s.update(self._intent_router(s))
        if s.get("intent_type") == "general":
            s.update(self._general_answer(s))
            return dict(s)
        s.update(self._kb_context(s))
        s.update(self._requirement_check(s))
        if s.get("need_clarification"):
            s.update(self._clarify(s))
        else:
            s.update(self._plan_query(s))
            if s.get("wants_execute"):
                s.update(self._execute_query(s))
            s.update(self._save_memory(s))
        return dict(s)

    def chat(
        self,
        query: str,
        history: list[dict[str, Any]] | None = None,
        top_k: int = 5,
        dialogue_state: dict[str, Any] | None = None,
        trace_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        history = history or []
        query = self._resolve_numeric_option_reply(query, history)
        dialogue_state = dialogue_state or {}
        last_did = int(dialogue_state.get("last_dialogue_id") or 0)
        pending = dialogue_state.get("pending_query_spec")
        if not isinstance(pending, dict):
            pending = None
        turn_id = datetime.now(timezone.utc).strftime("t_%Y%m%dT%H%M%S_%f")
        tctx = dict(trace_context or {})
        tctx.setdefault("session_id", str(tctx.get("session_id") or "web_unknown"))
        tctx.setdefault("channel", str(tctx.get("channel") or "web"))
        tctx["dialogue_id"] = last_did
        tctx["turn_id"] = turn_id
        tctx["user_query"] = query
        self._trace_context_var.set(tctx)
        # 执行口令优先：用户回复“确认/缺省/听你的...”且已有待查清单时，
        # 直接按 pending + 缺省策略执行，避免被 PM incomplete 再次追问。
        if self._is_execute_only_command(query) and isinstance(pending, dict) and pending:
            base_state: AgentState = {
                # 保留本轮口令（如“确认执行/缺省”），让 intent_router 能保持 wants_execute=True；
                # 真实分析问句由 _effective_query 基于历史自动回溯。
                "user_query": query,
                "history": history,
                "top_k": top_k,
                "wants_execute": True,
                "pm_route": "data_query_ready",
                "pm_query_spec": pending,
                "pm_requirement_override": query_spec_to_requirement_override(pending),
            }
            if self._graph is not None:
                out = dict(self._graph.invoke(base_state))
            else:
                out = self._invoke_fallback_from_state(base_state)
            out.setdefault("dialogue_id", max(1, last_did))
            out.setdefault("pending_query_spec", pending)
            if isinstance(out.get("reply"), str):
                out["reply"] = self._strip_reply_markdown_stars(out.get("reply", ""))
            return out
        social_signal = self._detect_lightweight_social_signal(query)
        is_light_social = bool(social_signal.get("is_lightweight_social"))
        light_score = float(social_signal.get("score", 0.0) or 0.0)
        light_signals = list(social_signal.get("signals") or [])

        pm_cfg = self.runtime_config.get("product_manager_intent", {})
        pm: dict[str, Any] | None = None
        kb_root = self.kb_service.paths.root
        if bool(pm_cfg.get("enable", True)):
            pm = run_product_manager_intent(
                self.deepseek_client,
                kb_root=kb_root,
                query=query,
                history=history,
                last_dialogue_id=last_did,
                pending_query_spec=pending,
                decay=float(pm_cfg.get("history_decay", 0.7)),
                max_history_messages=int(pm_cfg.get("max_history_messages", 24)),
                debug_hook=lambda event: self._emit_llm_trace_event(
                    purpose=str(event.get("purpose") or "pm_intent"),
                    input_data=dict(event.get("input") or {}),
                    output_text=str(event.get("output") or ""),
                ),
            )
            if pm is None:
                pm = run_product_manager_intent_rule_fallback(
                    kb_root=kb_root,
                    query=query,
                    history=history,
                    last_dialogue_id=last_did,
                    pending_query_spec=pending,
                )

        if pm:
            route = str(pm.get("route") or "")
            if route == "off_topic" and self._is_greeting_then_budget_query(query):
                # 问候+预算问题：忽略 off_topic 误判，回到预算主流程做完整判定。
                route = "mixed_greeting_budget"
            if route == "off_topic" and bool(re.search(r"(银行|金融|财务|净息差|利率|监管|央行|货币政策)", query)):
                # LLM 分类偶发偏差时，强制纠偏到专业非预算问答。
                route = "domain_knowledge"
            d_out = int(pm.get("dialogue_id") or max(1, last_did))
            # 同比分析时，先要求用户从 compare 展示层 L1-L5 选择同比版本。
            if route in {"data_query_ready", "data_query_incomplete"}:
                pending_qs = pending if isinstance(pending, dict) else {}
                require_compare_level = bool(pending_qs.get("__require_compare_level__", False))
                parsed_slots = self._extract_structured_slots(query)
                yoy_requested = self._is_yoy_requested(
                    query,
                    {"comparison_type": parsed_slots.get("comparison_type")},
                ) or require_compare_level
                selected_level = parsed_slots.get("comparison_show_level")
                if not selected_level:
                    selected_level = self._extract_compare_show_level_from_text(query)
                if yoy_requested and not selected_level:
                    rows = self._load_compare_version_options()
                    target_compare_year = self._extract_compare_target_year(query)
                    if target_compare_year is not None:
                        filtered_rows = [x for x in rows if int(x[1]) == int(target_compare_year)]
                        if filtered_rows:
                            rows = filtered_rows
                    options = [f"L{sl}（{sy}年 / V{sv} {sn}）" for sl, sy, sv, sn in rows]
                    numbered = "\n".join(f"{i + 1}. {txt}" for i, txt in enumerate(options)) if options else ""
                    hint = (
                        "你要求做同比分析，请先选择 compare 版本（L1-L5）。\n"
                        "可直接回复编号或 Lx（例如：1 或 L1）。"
                    )
                    if numbered:
                        hint = f"{hint}\n\n{numbered}"
                    next_pending = dict(pending_qs or {})
                    next_pending.update(dict(pm.get("query_spec") or {}))
                    next_pending["__require_compare_level__"] = True
                    if str((pending_qs or {}).get("__base_user_query__") or "").strip():
                        next_pending["__base_user_query__"] = str((pending_qs or {}).get("__base_user_query__") or "").strip()
                    elif not str(next_pending.get("__base_user_query__") or "").strip():
                        next_pending["__base_user_query__"] = str(query or "")
                    mapped_missing = [m for m in self._map_pm_missing_aspects(list(pm.get("missing_aspects") or [])) if m != "comparison_type"]
                    if "comparison_version" not in mapped_missing:
                        mapped_missing.insert(0, "comparison_version")
                    return self._pm_short_circuit(
                        reply=hint,
                        intent_type="budget",
                        next_action="product_intent_clarify",
                        dialogue_id=d_out,
                        need_clarification=True,
                        missing_slots=mapped_missing,
                        clarification_options={"comparison_version": options},
                        pending_query_spec=next_pending,
                        is_lightweight_social=is_light_social,
                        lightweight_social_score=light_score,
                        lightweight_social_signals=light_signals,
                    )
                if yoy_requested and selected_level:
                    next_pending = dict(pending_qs or {})
                    next_pending.update(dict(pm.get("query_spec") or {}))
                    next_pending["__require_compare_level__"] = False
                    next_pending["__selected_compare_level__"] = int(selected_level)
                    if str((pending_qs or {}).get("__base_user_query__") or "").strip():
                        next_pending["__base_user_query__"] = str((pending_qs or {}).get("__base_user_query__") or "").strip()
                    elif not str(next_pending.get("__base_user_query__") or "").strip():
                        next_pending["__base_user_query__"] = str(query or "")
                    pm["query_spec"] = next_pending
            if route == "sensitive":
                _, _, pm_msgs, _ = get_product_manager_intent_assets(kb_root)
                return self._pm_short_circuit(
                    reply=str(pm_msgs.get("sensitive_reply") or "我们还是换个话题吧"),
                    intent_type="general",
                    next_action="product_intent_blocked",
                    dialogue_id=d_out,
                    is_lightweight_social=is_light_social,
                    lightweight_social_score=light_score,
                    lightweight_social_signals=light_signals,
                )
            if route == "off_topic":
                if self._is_simple_greeting_query(query):
                    _, _, pm_msgs, _ = get_product_manager_intent_assets(kb_root)
                    return self._pm_short_circuit(
                        reply=str(pm_msgs.get("greeting_reply") or "你好，我在。可咨询预算相关问题。"),
                        intent_type="general",
                        next_action="product_intent_greeting",
                        dialogue_id=d_out,
                        is_lightweight_social=is_light_social,
                        lightweight_social_score=light_score,
                        lightweight_social_signals=light_signals,
                    )
                general_cfg = self.runtime_config.get("general_answer", {})
                body = self._build_general_answer_body(
                    query=query,
                    temperature=float(general_cfg.get("temperature", 0.45)),
                    max_tokens=int(general_cfg.get("max_tokens", 900)),
                    is_lightweight_social=is_light_social,
                )
                reply_off = (
                    body.strip()
                    if is_light_social
                    else merge_reply_disclaimer(kb_root, "off_topic", body)
                )
                return self._pm_short_circuit(
                    reply=reply_off,
                    intent_type="general",
                    next_action="product_intent_off_topic",
                    dialogue_id=d_out,
                    is_lightweight_social=is_light_social,
                    lightweight_social_score=light_score,
                    lightweight_social_signals=light_signals,
                )
            if route == "domain_knowledge":
                general_cfg = self.runtime_config.get("general_answer", {})
                body = self._build_domain_knowledge_answer_body(
                    query=query,
                    temperature=max(0.2, min(float(general_cfg.get("temperature", 0.35)), 0.45)),
                    max_tokens=max(1000, int(general_cfg.get("max_tokens", 1200))),
                    is_lightweight_social=is_light_social,
                )
                reply_dom = (
                    body.strip()
                    if is_light_social
                    else merge_reply_disclaimer(kb_root, "domain_knowledge", body)
                )
                return self._pm_short_circuit(
                    reply=reply_dom,
                    intent_type="general",
                    next_action="product_intent_domain_knowledge",
                    dialogue_id=d_out,
                    is_lightweight_social=is_light_social,
                    lightweight_social_score=light_score,
                    lightweight_social_signals=light_signals,
                )
            if route == "data_query_incomplete":
                qspec_pm = pm.get("query_spec") if isinstance(pm.get("query_spec"), dict) else {}
                qspec_pending = pending if isinstance(pending, dict) else {}
                qspec = dict(qspec_pending)
                qspec.update(dict(qspec_pm))
                return self._pm_short_circuit(
                    reply=incomplete_clarification_text(kb_root, str(pm.get("clarification_message") or "")),
                    intent_type="budget",
                    next_action="product_intent_clarify",
                    dialogue_id=d_out,
                    need_clarification=True,
                    missing_slots=self._map_pm_missing_aspects(list(pm.get("missing_aspects") or [])),
                    pending_query_spec=qspec,
                    is_lightweight_social=is_light_social,
                    lightweight_social_score=light_score,
                    lightweight_social_signals=light_signals,
                )

        initial_extras: dict[str, Any] = {}
        if pm and should_apply_pm_prefill(pm):
            qspec_pending = pending if isinstance(pending, dict) else {}
            qspec_pm = pm.get("query_spec") if isinstance(pm.get("query_spec"), dict) else {}
            qspec_merged = dict(qspec_pending)
            qspec_merged.update(dict(qspec_pm))
            initial_extras["pm_route"] = "data_query_ready"
            initial_extras["pm_query_spec"] = qspec_merged
            initial_extras["pm_requirement_override"] = query_spec_to_requirement_override(
                qspec_merged or {}
            )
        initial_extras["is_lightweight_social"] = is_light_social
        initial_extras["lightweight_social_score"] = light_score
        initial_extras["lightweight_social_signals"] = light_signals

        base_state: AgentState = {
            "user_query": query,
            "history": history,
            "top_k": top_k,
            **initial_extras,
        }
        if self._graph is not None:
            out = dict(self._graph.invoke(base_state))
        else:
            out = self._invoke_fallback_from_state(base_state)

        if pm and should_apply_pm_prefill(pm):
            out["dialogue_id"] = int(pm.get("dialogue_id") or max(1, last_did))
            qspec_pending = pending if isinstance(pending, dict) else {}
            qspec_pm = pm.get("query_spec") if isinstance(pm.get("query_spec"), dict) else {}
            qspec = dict(qspec_pending)
            qspec.update(dict(qspec_pm))
            out["pending_query_spec"] = qspec
        else:
            out.setdefault("dialogue_id", max(1, last_did))
            out.setdefault("pending_query_spec", pending)
        if isinstance(out.get("reply"), str):
            out["reply"] = self._strip_reply_markdown_stars(out.get("reply", ""))
        return out
