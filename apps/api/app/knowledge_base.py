from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RETIRED_KNOWLEDGE_RESOURCE_MARKERS = (
    "report_accounts",
    "report_account",
    "report_data_mapping",
    "retired_report_axis",
    "legacy_report_code",
    "报告科目",
    "报告:",
    "driver_category",
    "driver_indicator",
    "driver_product",
    "driver_account_mapping",
    "driver_source_priority",
    "driver_module",
    "driver_expr",
    "driver_first",
    "control_item_subject_mapping",
    "control_item_code",
    "control_item_name",
    "control_dept_code",
    "pivot_aggregate_rule",
    "needs_calc",
)


@dataclass
class KnowledgeBasePaths:
    root: Path
    data_semantics: Path
    metrics_seed: Path
    metrics_template: Path
    conversation_seed: Path
    conversation_template: Path
    synonyms_seed: Path
    synonyms_template: Path
    analysis_templates: Path
    build_report: Path


class KnowledgeBaseService:
    def __init__(self, knowledge_base_root: Path):
        kb_root = knowledge_base_root
        self.paths = KnowledgeBasePaths(
            root=kb_root,
            data_semantics=kb_root / "01_data_semantics" / "data_dictionary_seed.csv",
            metrics_seed=kb_root / "02_metric_definitions" / "metric_catalog_seed.yaml",
            metrics_template=kb_root / "02_metric_definitions" / "metric_catalog_template.yaml",
            conversation_seed=kb_root / "03_conversation_memory" / "memory_record_seed.jsonl",
            conversation_template=kb_root / "03_conversation_memory" / "memory_record_template.jsonl",
            synonyms_seed=kb_root / "04_term_synonyms" / "synonyms_seed.csv",
            synonyms_template=kb_root / "04_term_synonyms" / "synonyms_template.csv",
            analysis_templates=kb_root / "05_analysis_templates" / "analysis_template_library.md",
            build_report=kb_root / "generated" / "kb_build_report.json",
        )

    def _read_csv_rows(self, path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [dict(r) for r in reader]

    @staticmethod
    def _current_entity_code_index(data_rows: list[dict[str, str]]) -> set[tuple[str, str]]:
        current_types = {"dept_account", "org_product", "data_account", "metric_node"}
        out: set[tuple[str, str]] = set()
        for row in data_rows:
            entity_type = str(row.get("entity_type") or "").strip()
            entity_code = str(row.get("entity_code") or "").strip().upper()
            if entity_type in current_types and entity_code:
                out.add((entity_type, entity_code))
        return out

    def _current_synonym_rows(
        self,
        data_rows: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        source_rows = self._read_csv_rows(
            self.paths.synonyms_seed if self.paths.synonyms_seed.exists() else self.paths.synonyms_template
        )
        data_rows = data_rows if data_rows is not None else self._read_csv_rows(self.paths.data_semantics)
        current_codes = self._current_entity_code_index(data_rows)
        current_types = {"dept_account", "org_product", "data_account", "metric_node"}
        rows: list[dict[str, str]] = []
        for row in source_rows:
            self._assert_current_resource_row(row)
            normalized_type = str(row.get("normalized_type") or "").strip()
            normalized_code = str(row.get("normalized_code") or "").strip().upper()
            if normalized_type in current_types and (normalized_type, normalized_code) not in current_codes:
                continue
            rows.append(row)
        return rows

    def read_current_synonym_rows(self) -> list[dict[str, str]]:
        return self._current_synonym_rows()

    def read_data_semantics_rows(self) -> list[dict[str, str]]:
        return self._read_csv_rows(self.paths.data_semantics)

    def _read_jsonl_rows(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError:
                continue
        return rows

    def _read_metric_records(self) -> list[dict[str, str]]:
        path = self.paths.metrics_seed if self.paths.metrics_seed.exists() else self.paths.metrics_template
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8")
        # Lightweight parser for current YAML structure.
        chunks = re.split(r"\n\s*-\s+metric_id:\s*", text)
        records: list[dict[str, str]] = []
        for chunk in chunks[1:]:
            lines = chunk.splitlines()
            metric_id = lines[0].strip().strip('"').strip("'")
            metric_name = ""
            business_definition = ""
            for line in lines[1:]:
                if "metric_name:" in line and not metric_name:
                    metric_name = line.split("metric_name:", 1)[1].strip().strip('"').strip("'")
                if "business_definition:" in line and not business_definition:
                    business_definition = (
                        line.split("business_definition:", 1)[1].strip().strip('"').strip("'")
                    )
                if metric_name and business_definition:
                    break
            records.append(
                {
                    "metric_id": metric_id,
                    "metric_name": metric_name,
                    "business_definition": business_definition,
                }
            )
        return records

    @staticmethod
    def _normalize(s: str) -> str:
        return re.sub(r"\s+", "", (s or "").lower())

    @staticmethod
    def _assert_current_resource_row(row: dict[str, Any]) -> None:
        text = KnowledgeBaseService._normalize(json.dumps(row, ensure_ascii=False))
        for marker in RETIRED_KNOWLEDGE_RESOURCE_MARKERS:
            if marker in text:
                raise RuntimeError(f"Agent 知识资源包含已退休业务口径：{marker}")

    def _keyword_score(self, query: str, text: str) -> int:
        q = self._normalize(query)
        t = self._normalize(text)
        if not q or not t:
            return 0
        if q in t:
            return 100
        query_tokens = [tok for tok in re.split(r"[,\s，。；;]+", query) if tok.strip()]
        score = 0
        for tok in query_tokens:
            nt = self._normalize(tok)
            if nt and nt in t:
                score += 15
        return score

    def _best_rows(
        self,
        rows: list[dict[str, Any]],
        query: str,
        candidate_fields: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        ranked: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            combined = " ".join(str(row.get(f, "")) for f in candidate_fields)
            score = self._keyword_score(query, combined)
            if score > 0:
                ranked.append((score, row))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in ranked[:top_k]]

    def search_context(self, query: str, top_k: int = 5) -> dict[str, Any]:
        top_k = max(1, min(top_k, 20))
        data_rows = self._read_csv_rows(self.paths.data_semantics)
        synonym_rows = self._current_synonym_rows(data_rows)
        metric_rows = self._read_metric_records()
        memory_rows = self._read_jsonl_rows(
            self.paths.conversation_seed
            if self.paths.conversation_seed.exists()
            else self.paths.conversation_template
        )
        for row in memory_rows:
            self._assert_current_resource_row(row)

        matched_data = self._best_rows(
            data_rows,
            query,
            ["entity_code", "entity_name", "entity_type", "description"],
            top_k,
        )
        matched_synonyms = self._best_rows(
            synonym_rows,
            query,
            ["term", "normalized_name", "normalized_code", "domain"],
            top_k,
        )
        matched_metrics = self._best_rows(
            metric_rows,
            query,
            ["metric_id", "metric_name", "business_definition"],
            top_k,
        )
        matched_memories = self._best_rows(
            memory_rows,
            query,
            ["user_question", "analysis_summary", "embedding_text"],
            top_k,
        )

        template_excerpt = ""
        if self.paths.analysis_templates.exists():
            template_excerpt = self.paths.analysis_templates.read_text(encoding="utf-8")[:3000]

        return {
            "query": query,
            "matches": {
                "data_semantics": matched_data,
                "synonyms": matched_synonyms,
                "metrics": matched_metrics,
                "conversation_memories": matched_memories,
            },
            "analysis_template_excerpt": template_excerpt,
        }

    def stats(self) -> dict[str, Any]:
        report = {}
        if self.paths.build_report.exists():
            try:
                report = json.loads(self.paths.build_report.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                report = {}

        return {
            "knowledge_base_root": str(self.paths.root),
            "exists": self.paths.root.exists(),
            "files": {
                "data_semantics_seed": str(self.paths.data_semantics),
                "synonyms_seed": str(self.paths.synonyms_seed),
                "metrics_seed": str(self.paths.metrics_seed),
                "conversation_seed": str(self.paths.conversation_seed),
                "analysis_templates": str(self.paths.analysis_templates),
            },
            "counts": {
                "data_semantics": len(self._read_csv_rows(self.paths.data_semantics)),
                "synonyms": len(self._current_synonym_rows()),
                "metrics": len(self._read_metric_records()),
                "conversation_memories": len(
                    self._read_jsonl_rows(
                        self.paths.conversation_seed
                        if self.paths.conversation_seed.exists()
                        else self.paths.conversation_template
                    )
                ),
            },
            "build_report": report,
        }
