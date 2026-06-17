from __future__ import annotations

import contextvars
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from app.integrations.deepseek_client import DeepseekClient
from app.agent.agent_memory import ConversationMemoryStore
from app.agent.agent_prompt_assets import get_product_manager_intent_assets
from app.agent.agent_product_intent import (
    format_query_spec_locked_dimensions_block,
    incomplete_clarification_text,
    merge_reply_disclaimer,
    query_spec_to_requirement_override,
    run_product_manager_intent,
    run_product_manager_intent_rule_fallback,
    should_apply_pm_prefill,
)
from app.agent.agent_query_spec import merge_current_query_specs, normalise_current_query_spec
from app.agent.agent_query import ReadOnlySqlExecutor
from app.knowledge_base import KnowledgeBaseService
from app.services.agent_analysis_filters import sql_missing_pm_dimensions
from app.services.agent_budget_summary_sql import suggest_budget_summary_sql, suggest_metadata_sql
from app.services.agent_conversation_text import (
    effective_agent_query,
    is_execute_only_command,
    resolve_numeric_option_reply,
    strip_reply_markdown_stars,
)
from app.services.agent_compare_version import (
    compare_version_choice_hint,
    is_yoy_requested,
)
from app.services.agent_compare_clarification import (
    map_pm_missing_aspects,
    resolve_compare_version_clarification,
)
from app.services.agent_compare_sql import suggest_compare_l1_sql
from app.services.agent_domain_lexicon import AgentDomainLexicon
from app.services.agent_execution_response import (
    build_execution_fallback_reply,
    build_execution_rewrite_payload,
    normalize_agent_analysis_reply_units,
)
from app.services.agent_general_response import (
    build_general_fallback_answer,
    shorten_general_reply,
)
from app.services.agent_intent_signals import (
    has_pending_budget_plan,
    is_brief_acknowledgement,
    is_budget_analysis_intent,
    is_budget_knowledge_question,
    is_budget_metadata_query,
    is_contextual_budget_followup,
    is_followup_constraint_like,
    is_general_chitchat,
    is_greeting_then_budget_query,
    is_layout_adjust_request,
    is_pivot_view_request,
    is_simple_greeting_query,
    looks_like_budget_query,
)
from app.services.agent_memory_payload import build_agent_memory_append_payload
from app.services.agent_pivot_suggestion import (
    append_reply_options_footer,
    build_pivot_suggestion,
    build_plan_reply_options,
    should_recommend_pivot,
)
from app.services.agent_query_context import resolve_compare_query_context
from app.services.agent_requirement_check import build_agent_requirement_check
from app.services.agent_social_signal import (
    detect_lightweight_social_signal,
    is_lightweight_social_question,
    sanitize_lightweight_reply,
)
from app.services.agent_time_context import (
    resolve_agent_analysis_time_anchor,
)
from app.core.db_paths import budget_db_path, common_db_path, compare_db_path
from app.core.config import settings

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
        intent_trace_path: Path | None = None,
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
        self.intent_trace_path = intent_trace_path or (settings.agent_log_dir / "intent_router_trace.jsonl")
        self.runtime_config = self._load_runtime_config()
        self.intent_router_config = dict(self.runtime_config.get("intent_router", {}))
        self.domain_lexicon = AgentDomainLexicon.load(
            kb_service=self.kb_service,
            common_db=common_db_path(),
            budget_db=budget_db_path(settings.budget_year),
        )
        self.domain_terms_strong = self.domain_lexicon.strong_terms
        self.domain_terms_weak = self.domain_lexicon.weak_terms
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
                path.write_text(
                    json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        except Exception:
            return cfg
        return cfg

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
        cleaned_reply = strip_reply_markdown_stars(reply)
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
                "必须在回复**靠前位置**原样体现输入中的「已锁定的查询维度」一段（含指标树节点/机构及产品指标编码/部门科目/机构及产品 code｜name 及时间），"
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

    def _effective_query(self, state: AgentState) -> str:
        return effective_agent_query(
            state,
            budget_query_detector=looks_like_budget_query,
        )

    def _intent_router(self, state: AgentState) -> AgentState:
        query = state.get("user_query", "")
        light_signal = detect_lightweight_social_signal(
            query,
            budget_query_detector=looks_like_budget_query,
        )
        is_light_social = bool(light_signal.get("is_lightweight_social"))
        wants_execute = is_execute_only_command(query)
        history = state.get("history", [])
        has_budget_history = any(
            looks_like_budget_query(m.get("content", "")) or ("缺失要素" in m.get("content", ""))
            for m in history[-8:]
            if m.get("role") in {"assistant", "user"}
        )
        current_is_budget_domain = looks_like_budget_query(query)
        current_is_budget_analysis = is_budget_analysis_intent(query)
        current_is_budget_metadata = is_budget_metadata_query(query)
        current_is_contextual_followup = is_contextual_budget_followup(query)
        current_is_layout_adjust = is_layout_adjust_request(query)
        current_is_pivot_request = is_pivot_view_request(query)
        current_is_brief_ack = is_brief_acknowledgement(query)
        pending_budget_plan = has_pending_budget_plan(history)
        pivot_request_in_history = any(
            is_pivot_view_request(m.get("content", ""))
            for m in history[-10:]
            if m.get("role") == "user"
        )
        domain_hits = self.domain_lexicon.domain_hit_profile(query)
        current_is_budget_knowledge = current_is_budget_domain and is_budget_knowledge_question(query) and not current_is_budget_analysis
        current_is_chitchat = is_general_chitchat(query) or is_light_social
        current_is_followup = is_followup_constraint_like(query)
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
            wants_execute = pending_budget_plan
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
        semantic = self.domain_lexicon.semantic_budget_retrieve(query)
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
                "has_pending_budget_plan": pending_budget_plan,
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
            else detect_lightweight_social_signal(
                query,
                budget_query_detector=looks_like_budget_query,
            ).get("is_lightweight_social")
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
            reply = shorten_general_reply(
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
            else is_lightweight_social_question(
                query,
                budget_query_detector=looks_like_budget_query,
            )
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
            return sanitize_lightweight_reply(rewritten, short_fallback)
        fallback_reply = build_general_fallback_answer(query)
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
            else is_lightweight_social_question(
                query,
                budget_query_detector=looks_like_budget_query,
            )
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
            return sanitize_lightweight_reply(rewritten, short_fallback)
        fallback_reply = build_general_fallback_answer(query)
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

    def _kb_context(self, state: AgentState) -> AgentState:
        query = self._effective_query(state)
        top_k = int(state.get("top_k", 5) or 5)
        return {"kb_context": self.kb_service.search_context(query=query, top_k=top_k)}

    def _requirement_check(self, state: AgentState) -> AgentState:
        query = self._effective_query(state)
        history = state.get("history", [])
        query_kind = state.get("budget_query_kind", "analysis")
        inherit_history_slots = bool(state.get("inherit_history_slots", False))
        pm_ctx = state.get("pm_query_spec") if isinstance(state.get("pm_query_spec"), dict) else {}
        return build_agent_requirement_check(
            state,
            query=query,
            query_kind=str(query_kind or "analysis"),
            history=history,
            inherit_history_slots=inherit_history_slots,
            pm_query_spec=pm_ctx,
            budget_year=int(settings.budget_year),
            compare_db=compare_db_path(),
            common_db=common_db_path(),
        )

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

    def _resolve_analysis_time_anchor(self, state: AgentState) -> dict[str, Any]:
        return resolve_agent_analysis_time_anchor(
            state,
            effective_query=self._effective_query(state),
            budget_year=int(settings.budget_year),
            extract_month_index=self.query_executor._extract_month_index_from_text,
        )

    def _resolve_query_context(self, state: AgentState) -> dict[str, Any]:
        anchor = self._resolve_analysis_time_anchor(state)
        return resolve_compare_query_context(
            state,
            anchor=anchor,
            compare_db=compare_db_path(),
            common_db=common_db_path(),
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
        if query_kind == "metadata":
            return suggest_metadata_sql(
                query,
                data_source=data_source,
                version_id=version_id,
                year_tag=resolved_yt,
                month_tag=mtag,
                show_level=show_level,
            )
        if data_source == "compare_l1" and query_kind == "analysis":
            return suggest_compare_l1_sql(
                query,
                year_tag=resolved_yt,
                month_tag=mtag,
                show_level=show_level,
                state=state,
                compare_db=compare_db_path(),
                common_db=common_db_path(),
            )
        return suggest_budget_summary_sql(
            query,
            version_id=version_id,
            year_tag=resolved_yt,
            month_tag=mtag,
            state=state,
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
        yoy_requested = is_yoy_requested(query, clarified_slots if isinstance(clarified_slots, dict) else {})
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
            sql_missing_pm_dimensions(suggested_sql, pm_query_spec)
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
            "- 行：指标层级（从锁定层到末级）+ 机构及产品指标编码，或仅指标/部门/产品；\n"
            "- 列：时间（月或季或年）+ 预算/实际；\n"
            "- 页：年度 + 版本号及名称；并预填指标 code 到透视搜索。\n\n"
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
            choose_hint = compare_version_choice_hint(
                compare_db=compare_db_path(),
                common_db=common_db_path(),
                show_level=selected_compare_level,
            )
            if choose_hint and "已选择同比版本：" not in reply:
                reply = f"{choose_hint}\n\n{reply.lstrip()}"
        pivot_cfg = self.runtime_config.get("pivot", {})
        state_for_pivot: AgentState = {**state, **qctx}
        pivot_suggestion = build_pivot_suggestion(
            state_for_pivot,
            runtime_config=self.runtime_config,
            common_db=common_db_path(),
            current_year=int(settings.budget_year),
        )
        recommend_pivot = should_recommend_pivot(
            state_for_pivot,
            pivot_suggestion,
            pivot_config=pivot_cfg,
        )
        reply_options = build_plan_reply_options(state_for_pivot, recommend_pivot=recommend_pivot)
        # 透视说明仅由前端「管衡推荐透视视角」卡片展示 pivot_suggestion.explanation，避免正文重复。
        reply = append_reply_options_footer(reply, reply_options)
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
            history = state.get("history", [])
            query = state.get("user_query", "")
            fallback_reply = build_execution_fallback_reply(result)
            reply = self._llm_rewrite(
                "analysis_from_sql_result",
                build_execution_rewrite_payload(query=query, result=result, history=history),
                fallback_reply,
            )
            reply = normalize_agent_analysis_reply_units(reply)
            pivot_for_open = (
                build_pivot_suggestion(
                    state,
                    runtime_config=self.runtime_config,
                    common_db=common_db_path(),
                    current_year=int(settings.budget_year),
                )
                if should_open_pivot
                else None
            )
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
        payload = build_agent_memory_append_payload(state, budget_year=int(settings.budget_year))
        memory_id = self.memory_store.append(**payload)
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
        query = resolve_numeric_option_reply(query, history)
        dialogue_state = dialogue_state or {}
        last_did = int(dialogue_state.get("last_dialogue_id") or 0)
        pending = dialogue_state.get("pending_query_spec")
        if not isinstance(pending, dict):
            pending = None
        else:
            pending = normalise_current_query_spec(pending)
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
        if is_execute_only_command(query) and isinstance(pending, dict) and pending:
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
                out["reply"] = strip_reply_markdown_stars(out.get("reply", ""))
            return out
        social_signal = detect_lightweight_social_signal(
            query,
            budget_query_detector=looks_like_budget_query,
        )
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
            if route == "off_topic" and is_greeting_then_budget_query(query):
                # 问候+预算问题：忽略 off_topic 误判，回到预算主流程做完整判定。
                route = "mixed_greeting_budget"
            if route == "off_topic" and bool(re.search(r"(银行|金融|财务|净息差|利率|监管|央行|货币政策)", query)):
                # LLM 分类偶发偏差时，强制纠偏到专业非预算问答。
                route = "domain_knowledge"
            d_out = int(pm.get("dialogue_id") or max(1, last_did))
            compare_decision = resolve_compare_version_clarification(
                query,
                route=route,
                pm=pm,
                pending_query_spec=pending,
                compare_db=compare_db_path(),
                common_db=common_db_path(),
            )
            if compare_decision.get("action") == "clarify":
                return self._pm_short_circuit(
                    reply=str(compare_decision.get("reply") or ""),
                    intent_type="budget",
                    next_action="product_intent_clarify",
                    dialogue_id=d_out,
                    need_clarification=True,
                    missing_slots=list(compare_decision.get("missing_slots") or []),
                    clarification_options=dict(compare_decision.get("clarification_options") or {}),
                    pending_query_spec=dict(compare_decision.get("pending_query_spec") or {}),
                    is_lightweight_social=is_light_social,
                    lightweight_social_score=light_score,
                    lightweight_social_signals=light_signals,
                )
            if compare_decision.get("action") == "selected":
                pm["query_spec"] = dict(compare_decision.get("query_spec") or {})
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
                if is_simple_greeting_query(query):
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
                qspec = merge_current_query_specs(qspec_pending, qspec_pm)
                return self._pm_short_circuit(
                    reply=incomplete_clarification_text(kb_root, str(pm.get("clarification_message") or "")),
                    intent_type="budget",
                    next_action="product_intent_clarify",
                    dialogue_id=d_out,
                    need_clarification=True,
                    missing_slots=map_pm_missing_aspects(list(pm.get("missing_aspects") or [])),
                    pending_query_spec=qspec,
                    is_lightweight_social=is_light_social,
                    lightweight_social_score=light_score,
                    lightweight_social_signals=light_signals,
                )

        initial_extras: dict[str, Any] = {}
        if pm and should_apply_pm_prefill(pm):
            qspec_pending = pending if isinstance(pending, dict) else {}
            qspec_pm = pm.get("query_spec") if isinstance(pm.get("query_spec"), dict) else {}
            qspec_merged = merge_current_query_specs(qspec_pending, qspec_pm)
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
            qspec = merge_current_query_specs(qspec_pending, qspec_pm)
            out["pending_query_spec"] = qspec
        else:
            out.setdefault("dialogue_id", max(1, last_did))
            out.setdefault("pending_query_spec", normalise_current_query_spec(pending) if isinstance(pending, dict) else None)
        if isinstance(out.get("reply"), str):
            out["reply"] = strip_reply_markdown_stars(out.get("reply", ""))
        return out
