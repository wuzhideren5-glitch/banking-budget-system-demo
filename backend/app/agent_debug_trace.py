from __future__ import annotations

import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AgentDebugTraceStore:
    """In-process trace store with jsonl persistence + realtime polling."""

    def __init__(self, path: Path, *, max_in_memory: int = 4000):
        self.path = path
        self.max_in_memory = max(200, int(max_in_memory))
        self._lock = threading.Lock()
        self._events: deque[dict[str, Any]] = deque(maxlen=self.max_in_memory)
        self._seq = int(time.time() * 1000)
        self._load_recent_from_file(limit=min(self.max_in_memory, 1500))

    def _next_id(self) -> str:
        self._seq += 1
        return f"evt_{self._seq}"

    def _load_recent_from_file(self, *, limit: int) -> None:
        if not self.path.exists():
            return
        try:
            lines = self.path.read_text(encoding="utf-8", errors="ignore").splitlines()
            tail = lines[-max(1, int(limit)) :]
            for ln in tail:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    ev = json.loads(ln)
                except Exception:
                    continue
                if isinstance(ev, dict):
                    self._events.append(ev)
                    eid = str(ev.get("event_id") or "")
                    if eid.startswith("evt_"):
                        try:
                            self._seq = max(self._seq, int(eid.split("_", 1)[1]))
                        except Exception:
                            pass
        except Exception:
            return

    def append_event(self, event: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(event or {})
        enriched.setdefault("ts", _iso_now())
        with self._lock:
            enriched["event_id"] = self._next_id()
            self._events.append(enriched)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(enriched, ensure_ascii=False) + "\n")
            except Exception:
                # Keep runtime unaffected even if trace persistence fails.
                pass
        return enriched

    def list_recent(self, *, limit: int = 200) -> list[dict[str, Any]]:
        n = max(1, min(int(limit), 2000))
        with self._lock:
            items = list(self._events)
        return items[-n:]

    def list_since(self, *, after_event_id: str | None, limit: int = 200) -> list[dict[str, Any]]:
        n = max(1, min(int(limit), 2000))
        with self._lock:
            items = list(self._events)
        if not after_event_id:
            return items[-n:]
        pos = -1
        for i, ev in enumerate(items):
            if str(ev.get("event_id") or "") == after_event_id:
                pos = i
                break
        if pos < 0:
            return items[-n:]
        return items[pos + 1 : pos + 1 + n]

    def clear_all(self) -> None:
        with self._lock:
            self._events.clear()
            self._seq = int(time.time() * 1000)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text("", encoding="utf-8")
            except Exception:
                # Keep runtime unaffected even if clear persistence fails.
                pass
