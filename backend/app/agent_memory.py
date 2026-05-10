from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ConversationMemoryStore:
    def __init__(self, repo_root: Path):
        self.file_path = (
            repo_root / "knowledge_base" / "03_conversation_memory" / "memory_runtime.jsonl"
        )

    def append(
        self,
        *,
        user_query: str,
        intent_type: str,
        next_action: str,
        suggested_sql: str | None,
        analysis_summary: str,
        executed_result: dict[str, Any] | None,
        final_requirement: dict[str, Any] | None = None,
        pivot_config: dict[str, Any] | None = None,
        clarification_rounds: int = 0,
        user_feedback: dict[str, Any] | None = None,
    ) -> str:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        memory_id = f"mem_runtime_{uuid4().hex[:12]}"
        record = {
            "memory_id": memory_id,
            "session_id": f"sess_{uuid4().hex[:10]}",
            "created_at": _now_iso(),
            "agent_profile": {
                "name": "管衡",
                "identity": "银行预算部门数字员工",
                "specialty": "预算编制与解读，强调专业与高效",
            },
            "intent": intent_type,
            "user_question": user_query,
            "clarification_rounds": clarification_rounds,
            "final_requirement": final_requirement or {},
            "pivot_config": pivot_config or {},
            "sql_executed": suggested_sql or "",
            "analysis_summary": analysis_summary,
            "user_feedback": user_feedback or {"satisfied": None, "comment": ""},
            "tags": [next_action, "runtime_auto_memory"],
            "embedding_text": f"{user_query}\n{analysis_summary}",
            "execution_result_meta": {
                "row_count": (executed_result or {}).get("row_count", 0),
                "columns": (executed_result or {}).get("columns", []),
            },
        }
        with self.file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return memory_id

    def update_feedback(self, memory_id: str, *, satisfied: bool, comment: str | None = None) -> bool:
        if not memory_id or not self.file_path.exists():
            return False

        lines = self.file_path.read_text(encoding="utf-8").splitlines()
        changed = False
        updated_lines: list[str] = []
        for line in lines:
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError:
                updated_lines.append(text)
                continue

            if record.get("memory_id") == memory_id:
                record["user_feedback"] = {
                    "satisfied": bool(satisfied),
                    "comment": (comment or "").strip(),
                    "updated_at": _now_iso(),
                }
                changed = True
            updated_lines.append(json.dumps(record, ensure_ascii=False))

        if changed:
            self.file_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
        return changed
