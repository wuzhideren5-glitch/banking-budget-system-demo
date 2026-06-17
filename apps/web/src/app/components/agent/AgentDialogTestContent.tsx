import { useEffect, useRef, useState } from "react";

import {
  buildAgentDebugStreamUrl,
  clearAgentDebugEvents,
  getAgentDebugEvents,
  type AgentDebugEventDto,
} from "@/lib/agent/agentApi";

const MAX_ITEMS = 600;

function fmtTime(ts: string): string {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function normalizeEscapedNewlines(text: string): string {
  let s = String(text || "");
  // 递进反转义：兼容 \\n、\\\\n 等多层转义场景。
  for (let i = 0; i < 4; i += 1) {
    const next = s
      .replace(/\\\\r\\\\n/g, "\n")
      .replace(/\\\\n/g, "\n")
      .replace(/\\\\r/g, "\n")
      .replace(/\\\\t/g, "\t")
      .replace(/\\r\\n/g, "\n")
      .replace(/\\n/g, "\n")
      .replace(/\\r/g, "\n")
      .replace(/\\t/g, "\t");
    if (next === s) break;
    s = next;
  }
  return s;
}

function normalizeObjectNewlines(input: unknown): unknown {
  if (typeof input === "string") {
    return normalizeEscapedNewlines(input);
  }
  if (Array.isArray(input)) {
    return input.map((x) => normalizeObjectNewlines(x));
  }
  if (input && typeof input === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(input as Record<string, unknown>)) {
      out[k] = normalizeObjectNewlines(v);
    }
    return out;
  }
  return input;
}

function toDisplayInputText(input: unknown): string {
  const normalized = normalizeObjectNewlines(input ?? {});
  const raw = typeof normalized === "string" ? normalized : JSON.stringify(normalized, null, 2);
  return normalizeEscapedNewlines(raw);
}

export function AgentDialogTestContent() {
  const [items, setItems] = useState<AgentDebugEventDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [streamOnline, setStreamOnline] = useState(false);
  const [err, setErr] = useState<string>("");
  const [clearing, setClearing] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const cursorRef = useRef<string>("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setErr("");
      try {
        const resp = await getAgentDebugEvents(180);
        if (cancelled) return;
        const loaded = resp.items ?? [];
        setItems(loaded);
        cursorRef.current = loaded.length > 0 ? String(loaded[loaded.length - 1]?.event_id || "") : "";
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let es: EventSource | null = null;
    let retryTimer: number | null = null;
    let stopped = false;

    const connect = () => {
      es = new EventSource(buildAgentDebugStreamUrl(cursorRef.current), {
        withCredentials: true,
      });
      const onTrace = (ev: MessageEvent<string>) => {
        try {
          const payload = JSON.parse(ev.data) as AgentDebugEventDto;
          cursorRef.current = String(payload.event_id || cursorRef.current || "");
          setItems((prev) => {
            const next = [...prev, payload];
            return next.length > MAX_ITEMS ? next.slice(next.length - MAX_ITEMS) : next;
          });
        } catch {
          // ignore malformed events
        }
      };
      es.addEventListener("trace", onTrace as EventListener);
      es.onopen = () => {
        setStreamOnline(true);
        setErr("");
      };
      es.onerror = () => {
        setStreamOnline(false);
        setErr("实时流断开，自动重连中…");
        es?.close();
        if (!stopped) {
          retryTimer = window.setTimeout(connect, 1200);
        }
      };
    };

    connect();
    return () => {
      stopped = true;
      if (retryTimer != null) window.clearTimeout(retryTimer);
      es?.close();
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items.length]);

  return (
    <div className="bb-page">
      <div className="bb-toolbar justify-between">
        <div className="bb-page-title text-xs">Agent对话测试（实时LLM进出全文）</div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={clearing}
            onClick={async () => {
              setClearing(true);
              setErr("");
              try {
                await clearAgentDebugEvents();
                setItems([]);
                cursorRef.current = "";
              } catch (e) {
                setErr(e instanceof Error ? e.message : "清空失败");
              } finally {
                setClearing(false);
              }
            }}
            className={`bb-btn h-7 px-2 text-[11px] ${
              clearing
                ? "bb-btn-secondary cursor-not-allowed"
                : "bb-btn-danger"
            }`}
            title="一键清除当前调试窗口与后端调试日志"
          >
            清空对话
          </button>
          <div className={`bb-grid-chip font-medium ${streamOnline ? "text-[var(--bb-success)]" : "text-[var(--bb-warning)]"}`}>
            {streamOnline ? "实时连接中" : "连接中断/重连中"}
          </div>
        </div>
      </div>
      {loading && <div className="bb-status-banner text-[var(--bb-text-muted)]">加载历史调试记录中…</div>}
      {err && <div className="bb-status-banner bb-status-banner-warning">{err}</div>}
      <div className="bb-panel flex-1 overflow-auto p-2 space-y-2">
        {items.length === 0 && !loading && (
          <div className="text-xs text-gray-500 p-2">暂无调试数据，触发一次Agent对话后会实时显示。</div>
        )}
        {items.map((it) => (
          <div key={it.event_id} className="bb-card bg-[var(--bb-bg-subtle)]">
            <div className="text-[11px] text-gray-700">
              [{fmtTime(it.ts)}] [{it.channel}] [{it.purpose}] session={it.session_id} turn={it.turn_id}
            </div>
            <div className="mt-1 text-[11px] text-gray-600">用户问题：{it.user_query || "（空）"}</div>
            <div className="mt-2 text-[11px] font-medium text-blue-700">--- 大模型输入内容 ---</div>
            <pre className="bb-code-block mt-1">
              {toDisplayInputText(it.input_full)}
            </pre>
            <div className="mt-2 text-[11px] font-medium text-emerald-700">--- 大模型输出内容 ---</div>
            <pre className="bb-code-block mt-1">
              {normalizeEscapedNewlines(it.output_full || "（空输出）")}
            </pre>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
