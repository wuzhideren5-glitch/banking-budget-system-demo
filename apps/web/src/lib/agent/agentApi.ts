import { apiDelete, apiGet, apiPost, apiPostForm, buildApiUrl } from "@/lib/shared/api";

export type AgentChatMessageDto = {
  role: string;
  content: string;
  dialogue_id?: number;
};

export type AgentChatRequestDto = {
  message: string;
  history?: AgentChatMessageDto[];
  top_k?: number;
  last_dialogue_id?: number;
  pending_query_spec?: Record<string, unknown>;
};

export type AgentReplyOptionDto = {
  id: string;
  label: string;
};

export type AgentPivotSuggestionDto = {
  row_field_ids: string[];
  column_field_ids: string[];
  page_field_ids: string[];
  value_field_ids: string[];
  page_selections: Record<string, string>;
  /** 仅机构及产品指标 code，空格分隔，透视内 OR 搜索 */
  pivot_search_text?: string;
  explanation: string;
  confidence: number;
};

export type AgentChatResponseDto = {
  reply: string;
  intent_type: string;
  next_action: string;
  need_clarification: boolean;
  missing_slots: string[];
  clarification_options: Record<string, string[]>;
  assumptions: string[];
  suggested_sql: string | null;
  kb_context: Record<string, unknown>;
  executed: boolean;
  result_row_count: number;
  result_preview: Record<string, unknown>[];
  memory_id: string | null;
  reply_options?: AgentReplyOptionDto[];
  open_pivot_table?: boolean;
  pivot_suggestion?: AgentPivotSuggestionDto | null;
  dialogue_id?: number;
  pending_query_spec?: Record<string, unknown> | null;
};

export async function agentChat(body: AgentChatRequestDto): Promise<AgentChatResponseDto> {
  return apiPost<AgentChatResponseDto>("/api/agent/chat", body);
}

export type AgentDebugEventDto = {
  event_id: string;
  ts: string;
  kind: string;
  session_id: string;
  dialogue_id: number;
  turn_id: string;
  channel: string;
  user_query: string;
  purpose: string;
  model: string;
  input_full: Record<string, unknown> | null;
  output_full: string | null;
  error: string | null;
};

export type AgentDebugEventsResponseDto = {
  items: AgentDebugEventDto[];
};

export async function getAgentDebugEvents(limit = 200): Promise<AgentDebugEventsResponseDto> {
  return apiGet<AgentDebugEventsResponseDto>(`/api/system/agent-debug/events?limit=${encodeURIComponent(String(limit))}`);
}

export async function clearAgentDebugEvents(): Promise<void> {
  return apiDelete("/api/system/agent-debug/events");
}

export function buildAgentDebugStreamUrl(afterEventId?: string): string {
  const suffix = afterEventId ? `?after_event_id=${encodeURIComponent(afterEventId)}` : "";
  return buildApiUrl(`/api/system/agent-debug/stream${suffix}`);
}

export type AgentFeedbackRequestDto = {
  memory_id: string;
  satisfied: boolean;
  comment?: string;
};

export type AgentFeedbackResponseDto = {
  updated: boolean;
  memory_id: string;
};

export async function submitAgentFeedback(body: AgentFeedbackRequestDto): Promise<AgentFeedbackResponseDto> {
  return apiPost<AgentFeedbackResponseDto>("/api/agent/feedback", body);
}

export type AgentFileParseResponseDto = {
  filename: string;
  file_type: string;
  char_count: number;
  summary: string;
  key_points: string[];
  suggested_actions: string[];
  warnings: string[];
};

export async function parseAgentFile(file: File): Promise<AgentFileParseResponseDto> {
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<AgentFileParseResponseDto>("/api/agent/file/parse", formData);
}
