import {
  MessageSquare,
  Sparkles,
  Upload,
  Mic,
  AudioLines,
  Phone,
  Plus,
  History,
  Send,
  RotateCcw,
  ThumbsUp,
  ThumbsDown,
  Loader2,
  X,
  ChevronsLeft,
  ChevronRight,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";

import {
  agentChat,
  parseAgentFile,
  submitAgentFeedback,
  type AgentChatMessageDto,
  type AgentPivotSuggestionDto,
  type AgentReplyOptionDto,
} from "@/lib/agent/agentApi";

type UiMessage = AgentChatMessageDto & {
  dialogueId?: number;
  resultPreview?: Record<string, unknown>[];
  memoryId?: string | null;
  feedbackSubmitted?: boolean;
  needClarification?: boolean;
  clarificationOptions?: Record<string, string[]>;
  replyOptions?: AgentReplyOptionDto[];
  pivotSuggestion?: AgentPivotSuggestionDto | null;
};

/** 一条完整对话会话（可含多轮用户/助手消息） */
type ChatSessionRecord = {
  id: string;
  topic: string;
  /** 会话记录创建时间（点击「新对话」时） */
  createdAt: string;
  /** 本会话首条用户消息时间，尚无用户消息时为 null */
  firstUserAt: string | null;
  /** 最后一条消息时间 */
  lastMessageAt: string;
  messages: UiMessage[];
  /** 产品经理意图链路：上一轮返回的对话 ID */
  lastAgentDialogueId?: number;
  /** 待合并的查询条件（澄清/延续对话时由后端返回） */
  agentPendingQuerySpec?: Record<string, unknown> | null;
};

type BasicSpeechRecognitionAlternative = { transcript: string };
type BasicSpeechRecognitionResult = ArrayLike<BasicSpeechRecognitionAlternative> & { isFinal?: boolean };
type BasicSpeechRecognitionEvent = { results: ArrayLike<BasicSpeechRecognitionResult> };
type BasicSpeechRecognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: BasicSpeechRecognitionEvent) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type AgentWorkingStage = {
  id: string;
  label: string;
  desc: string;
};

const AGENT_WORKING_STAGES: AgentWorkingStage[] = [
  { id: "intent", label: "意图识别", desc: "判断通用问答、专业问答或预算数据分析请求" },
  { id: "context", label: "上下文整理", desc: "整合历史对话与约束，补全当前任务语境" },
  { id: "route", label: "节点路由", desc: "决定澄清、规划查询或直接生成回答" },
  { id: "reason", label: "推理与生成", desc: "调用大模型组织结论、要点与可执行建议" },
  { id: "finalize", label: "结果整理", desc: "整理输出格式并准备返回前端展示" },
];

const SMART_TEMPLATES = [
  "请分析2026年一季度个人金融部预算与实际差异，按月展示并给出主要原因。",
  "请对比企业金融部2026年上半年各月同比表现，指出波动最大的指标。",
  "请汇总普惠金融部本年度预算执行进度，并给出后续三个月管控建议。",
  "请按部门维度查看2026年全年收入类科目的预算执行差异。",
  "请按季度对比2026年预算和实际，并标出差异超过10%的项目。",
  "请先给出全行预算执行汇总，再下钻到差异前5的部门。",
  "请分析本年度最近三个月成本类指标环比变化，并给出解释。",
  "请按月展示科技事业部预算执行趋势，并识别异常月份。",
  "请比较个人金融部与企业金融部在2026年二季度的预算执行差异。",
  "请查看2026年全年关键科目明细，按预算与实际差异从高到低排序。",
  "请按当前口径重跑，并重点解释新增异常项。",
];

function buildWelcomeMessage(userDisplayName?: string): UiMessage {
  const name = (userDisplayName || "").trim();
  const salutation = name ? `${name}，你好` : "你好";
  return {
    role: "assistant",
    content:
      `${salutation}，我是管衡，是咱们预算部门的数字同事。很高兴认识你！\n\n` +
      "我最擅长预算编制、预算执行差异分析和口径解读。你可以直接告诉我想看的时间范围、业务对象、对比方式和分析粒度，我会尽量快速、清晰地给你结论。",
  };
}

function makeTopic(text: string): string {
  const trimmed = text.trim();
  return trimmed.length > 18 ? `${trimmed.slice(0, 18)}...` : trimmed;
}

function polishBudgetPrompt(text: string): string {
  const compact = text.trim().replace(/\s+/g, " ");
  if (!compact) return "";
  const normalized = compact.replace(/[。；;，,]+$/g, "");
  return `${normalized}。请按预算分析口径输出：时间范围、业务对象、对比方式、分析粒度，并给出可执行结论。`;
}

function newSessionId(): string {
  return `sess_${Date.now()}_${Math.random().toString(16).slice(2, 10)}`;
}

function deriveTopicFromMessages(msgs: UiMessage[]): string {
  const firstUser = msgs.find((m) => m.role === "user");
  if (firstUser?.content?.trim()) return makeTopic(firstUser.content);
  return "新对话";
}

function createEmptySession(userDisplayName?: string): ChatSessionRecord {
  const now = new Date().toISOString();
  return {
    id: newSessionId(),
    topic: "新对话",
    createdAt: now,
    firstUserAt: null,
    lastMessageAt: now,
    messages: [buildWelcomeMessage(userDisplayName)],
    lastAgentDialogueId: 0,
    agentPendingQuerySpec: null,
  };
}

function buildFlushedSession(
  prev: ChatSessionRecord[],
  currentSessionId: string,
  messages: UiMessage[],
): ChatSessionRecord[] {
  const now = new Date().toISOString();
  const idx = prev.findIndex((s) => s.id === currentSessionId);
  const firstUser = messages.find((m) => m.role === "user");
  const updated: ChatSessionRecord = {
    id: currentSessionId,
    topic: deriveTopicFromMessages(messages),
    createdAt: idx >= 0 ? prev[idx]!.createdAt : now,
    firstUserAt: firstUser ? (idx >= 0 ? prev[idx]!.firstUserAt ?? now : now) : idx >= 0 ? prev[idx]!.firstUserAt : null,
    lastMessageAt: now,
    messages: messages.slice(-80),
    lastAgentDialogueId: idx >= 0 ? prev[idx]!.lastAgentDialogueId ?? 0 : 0,
    agentPendingQuerySpec: idx >= 0 ? prev[idx]!.agentPendingQuerySpec ?? null : null,
  };
  if (idx >= 0) {
    const next = [...prev];
    next[idx] = updated;
    return next;
  }
  return [updated, ...prev];
}

type LoadedBundle = {
  currentSessionId: string;
  sessions: ChatSessionRecord[];
  messages: UiMessage[];
  input: string;
};

function loadInitialBundle(bundleKey: string, userDisplayName?: string): LoadedBundle {
  return freshSessionFromHistory(
    dropLeadingEmptyUnusedSessions(readStoredSessionsOnly(bundleKey)),
    userDisplayName,
  );
}

/** 仅用于启动时：从 localStorage 读出已有会话列表（无则空数组） */
function readStoredSessionsOnly(bundleKey: string): ChatSessionRecord[] {
  try {
    const raw = localStorage.getItem(bundleKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as { sessions?: ChatSessionRecord[] };
    return Array.isArray(parsed.sessions) ? parsed.sessions : [];
  } catch {
    return [];
  }
}

function isSessionEmptyPlaceholder(sess: ChatSessionRecord): boolean {
  const msgs = sess.messages ?? [];
  if (msgs.some((m) => m.role === "user")) return false;
  if (msgs.length === 0) return true;
  if (msgs.length === 1 && msgs[0]?.role === "assistant") return true;
  return false;
}

/** 去掉列表顶部仅含欢迎语、尚无用户发言的占位会话，避免每次打开堆积「新对话」 */
function dropLeadingEmptyUnusedSessions(sessions: ChatSessionRecord[]): ChatSessionRecord[] {
  let i = 0;
  while (i < sessions.length && isSessionEmptyPlaceholder(sessions[i]!)) {
    i += 1;
  }
  return i > 0 ? sessions.slice(i) : sessions;
}

function freshSessionFromHistory(
  priorSessions: ChatSessionRecord[],
  userDisplayName?: string,
): LoadedBundle {
  const newSess = createEmptySession(userDisplayName);
  const sessions = [newSess, ...priorSessions].slice(0, 80);
  return {
    currentSessionId: newSess.id,
    sessions,
    messages: newSess.messages,
    input: "",
  };
}

function formatSessionDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export type ChatBotProps = {
  /** 每用户 localStorage 键，如 `budget_agent_chat_bundle_v2__u3` */
  chatBundleStorageKey: string;
  /** 当前登录用户名（用于新对话首句称呼） */
  userDisplayName?: string;
  /** 用户选择「打开数据透视表」时由 App 打开对应页签 */
  onOpenPivotTable?: (suggestion?: AgentPivotSuggestionDto | null) => void;
  onExpandAssistantDouble?: () => void;
  onCollapseAssistant?: () => void;
  disableExpandAssistantDouble?: boolean;
};

export function ChatBot({
  chatBundleStorageKey,
  userDisplayName,
  onOpenPivotTable,
  onExpandAssistantDouble,
  onCollapseAssistant,
  disableExpandAssistantDouble = false,
}: ChatBotProps) {
  const [initialBundle] = useState(() =>
    loadInitialBundle(chatBundleStorageKey, userDisplayName),
  );
  const [currentSessionId, setCurrentSessionId] = useState(initialBundle.currentSessionId);
  const [sessions, setSessions] = useState<ChatSessionRecord[]>(initialBundle.sessions);
  const [messages, setMessages] = useState<UiMessage[]>(initialBundle.messages);
  const [input, setInput] = useState(initialBundle.input);
  const [sending, setSending] = useState(false);
  const [parsingFile, setParsingFile] = useState(false);
  const [smartModalOpen, setSmartModalOpen] = useState(false);
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [historyModalPreviewId, setHistoryModalPreviewId] = useState<string | null>(null);
  const [smartDraft, setSmartDraft] = useState("");
  const [voiceActive, setVoiceActive] = useState(false);
  const [phoneMode, setPhoneMode] = useState(false);
  const [selectedClarifications, setSelectedClarifications] = useState<Record<number, Record<string, string>>>({});
  const [agentStageIdx, setAgentStageIdx] = useState(0);
  const [agentWorkingSince, setAgentWorkingSince] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const recognitionRef = useRef<BasicSpeechRecognition | null>(null);
  const phoneModeRef = useRef(false);
  const voiceActiveRef = useRef(false);
  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;
  const canSend = useMemo(() => input.trim().length > 0 && !sending, [input, sending]);
  const sortedSessions = useMemo(
    () => [...sessions].sort((a, b) => (a.lastMessageAt < b.lastMessageAt ? 1 : -1)),
    [sessions],
  );
  const activeHistoryPreview = useMemo(() => {
    const pid = historyModalPreviewId ?? currentSessionId;
    return sessions.find((s) => s.id === pid) ?? null;
  }, [sessions, historyModalPreviewId, currentSessionId]);
  const slotLabels: Record<string, string> = {
    time_period: "时间范围",
    business_scope: "业务对象",
    comparison_type: "对比方式",
    comparison_version: "同比版本",
    metric_scope: "指标口径",
    granularity: "分析粒度",
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  useEffect(() => {
    phoneModeRef.current = phoneMode;
  }, [phoneMode]);

  useEffect(() => {
    voiceActiveRef.current = voiceActive;
  }, [voiceActive]);

  useEffect(() => {
    if (!sending) {
      setAgentStageIdx(0);
      setAgentWorkingSince(null);
      return;
    }
    const started = Date.now();
    setAgentWorkingSince(started);
    setAgentStageIdx(0);
    const timer = window.setInterval(() => {
      const elapsedMs = Date.now() - started;
      const idx = Math.min(
        AGENT_WORKING_STAGES.length - 1,
        Math.floor(elapsedMs / 1300),
      );
      setAgentStageIdx(idx);
    }, 250);
    return () => window.clearInterval(timer);
  }, [sending]);

  useEffect(() => {
    setSessions((prev) => {
      const merged = buildFlushedSession(prev, currentSessionId, messages);
      try {
        localStorage.setItem(
          chatBundleStorageKey,
          JSON.stringify({
            currentSessionId,
            sessions: merged.slice(0, 80),
            input,
          }),
        );
      } catch {
        // ignore quota errors
      }
      return merged;
    });
  }, [messages, input, currentSessionId, chatBundleStorageKey]);

  useEffect(() => {
    const SpeechRecognitionCtor = (window as Window & { webkitSpeechRecognition?: new () => BasicSpeechRecognition })
      .webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      return;
    }
    const recognition = new SpeechRecognitionCtor();
    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = false;
    recognitionRef.current = recognition;
    return () => {
      recognition.stop();
      recognitionRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!phoneMode) return;
    const last = messages[messages.length - 1];
    if (last?.role !== "assistant" || !last.content.trim()) return;
    const utterance = new SpeechSynthesisUtterance(last.content);
    utterance.lang = "zh-CN";
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  }, [messages, phoneMode]);

  const openHistoryModal = () => {
    setHistoryModalPreviewId(currentSessionId);
    setHistoryModalOpen(true);
  };

  const restoreSession = (id: string) => {
    if (id === currentSessionId) {
      setHistoryModalOpen(false);
      return;
    }
    const flushed = buildFlushedSession(sessionsRef.current, currentSessionId, messages);
    const target = flushed.find((s) => s.id === id);
    if (!target) return;
    setSessions(flushed);
    setCurrentSessionId(id);
    setMessages([...target.messages]);
    setInput("");
    setSelectedClarifications({});
    setHistoryModalOpen(false);
    try {
      localStorage.setItem(
        chatBundleStorageKey,
        JSON.stringify({
          currentSessionId: id,
          sessions: flushed.slice(0, 80),
          input: "",
        }),
      );
    } catch {
      // ignore
    }
  };

  const sendMessageWithText = async (rawMessage: string) => {
    const message = rawMessage.trim();
    if (!message || sending) return;
    const nextMessages: UiMessage[] = [...messages, { role: "user", content: message }];
    setMessages(nextMessages);
    setSending(true);
    try {
      const sess = sessionsRef.current.find((s) => s.id === currentSessionId);
      const histPayload: AgentChatMessageDto[] = nextMessages.slice(-12).map((m) => {
        const dto: AgentChatMessageDto = { role: m.role, content: m.content };
        if (m.dialogueId != null) dto.dialogue_id = m.dialogueId;
        return dto;
      });
      const resp = await agentChat({
        message,
        history: histPayload,
        top_k: 5,
        last_dialogue_id: sess?.lastAgentDialogueId ?? 0,
        pending_query_spec: sess?.agentPendingQuerySpec ?? undefined,
      });
      const extras: string[] = [];
      if (resp.need_clarification && resp.missing_slots.length > 0) {
        const missingZh = resp.missing_slots.map((s) => slotLabels[s] ?? s);
        extras.push(`缺失要素：${missingZh.join("、")}`);
      }
      if (resp.executed) {
        extras.push(`已执行只读查询，返回 ${resp.result_row_count} 行`);
      }
      const pivotSuggestion = resp.pivot_suggestion ?? null;
      if (resp.open_pivot_table) {
        onOpenPivotTable?.(pivotSuggestion);
        extras.push("已根据你的偏好自动打开数据透视表页签。");
      }
      const content = extras.length > 0 ? `${resp.reply}\n\n${extras.join("\n")}` : resp.reply;
      const replyOptions = Array.isArray(resp.reply_options) ? resp.reply_options : [];
      const did = resp.dialogue_id ?? 0;
      const pendingSpec = resp.pending_query_spec ?? null;
      setMessages((prev) => {
        const tagged = prev.map((m, i) => {
          if (i === prev.length - 1 && m.role === "user") {
            return { ...m, dialogueId: did };
          }
          return m;
        });
        const final: UiMessage[] = [
          ...tagged,
          {
            role: "assistant",
            content,
            resultPreview: resp.result_preview,
            memoryId: resp.memory_id,
            feedbackSubmitted: false,
            needClarification: resp.need_clarification,
            clarificationOptions: resp.clarification_options,
            replyOptions: replyOptions.length > 0 ? replyOptions : undefined,
            pivotSuggestion,
          },
        ];
        setSessions((sPrev) => {
          const flushed = buildFlushedSession(sPrev, currentSessionId, final);
          const ix = flushed.findIndex((x) => x.id === currentSessionId);
          if (ix < 0) return flushed;
          const nextSess = [...flushed];
          nextSess[ix] = {
            ...nextSess[ix]!,
            lastAgentDialogueId: did,
            agentPendingQuerySpec: pendingSpec,
          };
          return nextSess;
        });
        return final;
      });
    } catch (e) {
      const err = e instanceof Error ? e.message : "请求失败";
      setMessages((prev) => [...prev, { role: "assistant", content: `处理失败：${err}` }]);
    } finally {
      setSending(false);
    }
  };

  const startVoiceInput = () => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "当前浏览器不支持语音识别，请使用 Chrome 内核浏览器。" },
      ]);
      return;
    }
    if (voiceActiveRef.current) {
      voiceActiveRef.current = false;
      setVoiceActive(false);
      recognition.stop();
      return;
    }
    if (phoneModeRef.current) {
      window.speechSynthesis.cancel();
      setPhoneMode(false);
    }
    recognition.continuous = true;
    recognition.onresult = (event) => {
      const finalTexts: string[] = [];
      for (let i = 0; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (!result?.isFinal) continue;
        const text = result[0]?.transcript?.trim() ?? "";
        if (text) finalTexts.push(text);
      }
      if (finalTexts.length > 0) {
        setInput((prev) => (prev ? `${prev} ${finalTexts.join(" ")}` : finalTexts.join(" ")));
      }
    };
    recognition.onerror = (event) => {
      const err = event.error ?? "";
      if (err === "not-allowed" || err === "service-not-allowed") {
        voiceActiveRef.current = false;
        setVoiceActive(false);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "语音权限未开启，请在浏览器中允许麦克风访问后重试。" },
        ]);
      }
    };
    recognition.onend = () => {
      if (voiceActiveRef.current && !phoneModeRef.current) {
        try {
          recognition.start();
        } catch {
          window.setTimeout(() => {
            if (!voiceActiveRef.current || phoneModeRef.current) return;
            try {
              recognition.start();
            } catch {
              voiceActiveRef.current = false;
              setVoiceActive(false);
            }
          }, 350);
        }
      }
    };
    try {
      recognition.start();
      voiceActiveRef.current = true;
      setVoiceActive(true);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "语音识别启动失败，请稍后再试。" },
      ]);
    }
  };

  const togglePhoneMode = () => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "当前浏览器不支持电话语音模式，请使用 Chrome 内核浏览器。" },
      ]);
      return;
    }
    if (phoneMode) {
      recognition.stop();
      window.speechSynthesis.cancel();
      setPhoneMode(false);
      return;
    }
    if (voiceActiveRef.current) {
      voiceActiveRef.current = false;
      setVoiceActive(false);
      recognition.stop();
    }
    recognition.continuous = true;
    recognition.onresult = (event) => {
      const result = event.results[event.results.length - 1];
      const transcript = result?.[0]?.transcript?.trim() ?? "";
      if (!transcript) return;
      if (window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
      }
      if (result.isFinal) {
        void sendMessageWithText(transcript);
      }
    };
    recognition.onerror = () => {
      setPhoneMode(false);
    };
    recognition.onend = () => {
      if (phoneModeRef.current) {
        try {
          recognition.start();
        } catch {
          setPhoneMode(false);
        }
      }
    };
    recognition.start();
    setPhoneMode(true);
  };

  const onUploadClick = () => {
    uploadInputRef.current?.click();
  };

  const onFileSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || parsingFile) return;
    setParsingFile(true);
    try {
      const parsed = await parseAgentFile(file);
      const lines = [
        `已解析文件：${parsed.filename}（${parsed.file_type}）`,
        `文档摘要：${parsed.summary}`,
      ];
      if (parsed.key_points.length > 0) {
        lines.push(`关键点：\n${parsed.key_points.map((point, idx) => `${idx + 1}. ${point}`).join("\n")}`);
      }
      if (parsed.suggested_actions.length > 0) {
        lines.push(`建议操作：\n${parsed.suggested_actions.map((item) => `- ${item}`).join("\n")}`);
      }
      if (parsed.warnings.length > 0) {
        lines.push(`解析提示：\n${parsed.warnings.map((w) => `- ${w}`).join("\n")}`);
      }
      setMessages((prev) => [
        ...prev,
        { role: "user", content: `我上传了文件：${file.name}` },
        { role: "assistant", content: lines.join("\n\n") },
      ]);
    } catch (e) {
      const err = e instanceof Error ? e.message : "文件解析失败";
      setMessages((prev) => [...prev, { role: "assistant", content: `文件解析失败：${err}` }]);
    } finally {
      setParsingFile(false);
    }
  };

  const sendSmartDraft = async () => {
    const msg = smartDraft.trim();
    if (!msg) return;
    setSmartModalOpen(false);
    setSmartDraft("");
    await sendMessageWithText(msg);
  };

  const collectSelectedClarificationValues = (): { text: string; usedIndexes: number[] } => {
    const usedIndexes: number[] = [];
    const parts: string[] = [];
    for (const [idxStr, slotMap] of Object.entries(selectedClarifications)) {
      const idx = Number(idxStr);
      const values = Object.values(slotMap || {}).filter((v) => v.trim().length > 0);
      if (values.length > 0) {
        usedIndexes.push(idx);
        parts.push(...values);
      }
    }
    // 去重，避免重复选项拼接多次
    const uniq = Array.from(new Set(parts));
    return { text: uniq.join("，"), usedIndexes };
  };

  const sendMessage = async () => {
    const typed = input.trim();
    if (!typed || sending) return;
    const selected = collectSelectedClarificationValues();
    const message = selected.text ? `${selected.text}。${typed}` : typed;
    setInput("");
    await sendMessageWithText(message);
    if (selected.usedIndexes.length > 0) {
      setSelectedClarifications((prev) => {
        const next = { ...prev };
        for (const idx of selected.usedIndexes) {
          next[idx] = {};
        }
        return next;
      });
    }
  };

  const submitFeedback = async (index: number, satisfied: boolean) => {
    const msg = messages[index];
    if (!msg?.memoryId || msg.feedbackSubmitted) return;
    try {
      await submitAgentFeedback({
        memory_id: msg.memoryId,
        satisfied,
        comment: satisfied ? "用户点击满意" : "用户点击不满意",
      });
      setMessages((prev) =>
        prev.map((m, i) =>
          i === index
            ? {
                ...m,
                feedbackSubmitted: true,
                content: `${m.content}\n\n已记录反馈：${satisfied ? "满意" : "不满意"}`,
              }
            : m,
        ),
      );

      if (!satisfied) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content:
              "谢谢你及时告诉我你的感受，确实是我这次做得不够好，给你添麻烦了。\n\n我是管衡，还在持续学习和成长中。你指出的问题我会认真吸取，努力把后续分析做得更准确、更贴合你的需求。还请多多包涵，我们一起把结果打磨好。",
          },
        ]);
        const followup = "我对上一轮结果不满意，请基于当前上下文提出二次澄清问题，并在我补充后重跑查询。";
        await sendMessageWithText(followup);
      }
    } catch (e) {
      const err = e instanceof Error ? e.message : "反馈提交失败";
      setMessages((prev) => [...prev, { role: "assistant", content: `反馈提交失败：${err}` }]);
    }
  };

  const toggleClarificationOption = (msgIndex: number, slot: string, option: string) => {
    setSelectedClarifications((prev) => {
      const current = prev[msgIndex] ?? {};
      const selected = current[slot] === option ? "" : option;
      return {
        ...prev,
        [msgIndex]: {
          ...current,
          [slot]: selected,
        },
      };
    });
  };

  const sendSelectedClarifications = async (msgIndex: number) => {
    const selected = selectedClarifications[msgIndex] ?? {};
    const values = Object.values(selected).filter((v) => v.trim().length > 0);
    if (values.length === 0) return;
    const message = values.join("，");
    await sendMessageWithText(message);
    setSelectedClarifications((prev) => ({ ...prev, [msgIndex]: {} }));
  };

  const startNewConversation = () => {
    const newSess = createEmptySession(userDisplayName);
    const flushed = buildFlushedSession(sessionsRef.current, currentSessionId, messages);
    const next = [newSess, ...flushed.filter((s) => s.id !== newSess.id)];
    setSessions(next);
    setCurrentSessionId(newSess.id);
    setMessages([buildWelcomeMessage(userDisplayName)]);
    setInput("");
    setSelectedClarifications({});
    setSending(false);
    try {
      localStorage.setItem(
        chatBundleStorageKey,
        JSON.stringify({
          currentSessionId: newSess.id,
          sessions: next.slice(0, 80),
          input: "",
        }),
      );
    } catch {
      // ignore
    }
  };

  return (
    <div className="bb-agent-panel">
      <div className="bb-agent-header">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onExpandAssistantDouble}
              disabled={disableExpandAssistantDouble}
              className={`bb-icon-btn h-6 w-6 border border-[var(--bb-border)] ${
                disableExpandAssistantDouble
                  ? "bg-[var(--bb-bg-subtle)] text-[var(--bb-text-muted)] cursor-not-allowed"
                  : "bg-[var(--bb-bg-surface)] text-[var(--bb-text-muted)]"
              }`}
              title={disableExpandAssistantDouble ? "助手已处于最大宽度" : "双倍展开助手"}
            >
              <ChevronsLeft className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={onCollapseAssistant}
              className="bb-icon-btn h-6 w-6 border border-[var(--bb-border)] bg-[var(--bb-bg-surface)]"
              title="折叠助手"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
          <MessageSquare className="w-4 h-4 text-[var(--bb-primary)]" />
          <span className="text-xs font-semibold text-[var(--bb-text-strong)]">智能助手管衡</span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={startNewConversation}
            className="bb-btn bb-btn-primary h-7 px-2"
            title="新对话"
          >
            <Plus className="w-3 h-3" />
            <span>新对话</span>
          </button>
          <button
            type="button"
            onClick={openHistoryModal}
            className="bb-btn bb-btn-secondary h-7 px-2"
            title="历史对话"
          >
            <History className="w-3 h-3" />
            <span>历史</span>
          </button>
        </div>
      </div>

      <div className="bb-chat-scroll space-y-3">
        {messages.map((m, idx) => (
          <div
            key={`${m.role}-${idx}`}
            className={`bb-chat-message ${
              m.role === "user"
                ? "bb-chat-message-user"
                : "bb-chat-message-assistant"
            }`}
          >
            {m.content}
            {m.role === "assistant" && m.resultPreview && m.resultPreview.length > 0 && (
              <div className="bb-table-wrap mt-2 overflow-x-auto">
                <table className="bb-table bb-table-dense min-w-full text-[10px]">
                  <thead className="bg-gray-100 text-gray-600">
                    <tr>
                      {Object.keys(m.resultPreview[0]).map((col) => (
                        <th key={col} className="px-2 py-1 text-left font-medium whitespace-nowrap">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {m.resultPreview.slice(0, 8).map((row, rIdx) => (
                      <tr key={`row-${rIdx}`} className="border-t border-gray-200">
                        {Object.keys(m.resultPreview?.[0] ?? {}).map((col) => (
                          <td key={`${rIdx}-${col}`} className="px-2 py-1 whitespace-nowrap text-gray-700">
                            {String(row[col] ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {m.role === "assistant" &&
              m.needClarification &&
              m.clarificationOptions &&
              Object.keys(m.clarificationOptions).length > 0 && (
                <div className="mt-2 space-y-2">
                  {Object.entries(m.clarificationOptions).map(([slot, options]) => (
                    <div key={`${idx}-${slot}`} className="space-y-1">
                      <div className="text-[10px] text-gray-500">{slotLabels[slot] ?? slot}</div>
                      <div className="flex flex-wrap gap-1.5">
                        {options.map((option) => {
                          const active = selectedClarifications[idx]?.[slot] === option;
                          return (
                            <button
                              key={`${idx}-${slot}-${option}`}
                              onClick={() => toggleClarificationOption(idx, slot, option)}
                              className={`bb-btn h-6 px-2 text-[10px] ${
                                active
                                  ? "bb-btn-primary"
                                  : "bb-btn-secondary"
                              }`}
                              title={`补充${slot}`}
                            >
                              {option}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => void sendSelectedClarifications(idx)}
                      className="bb-btn bb-btn-secondary h-6 px-2 text-[10px]"
                      title="发送已选条件"
                    >
                      发送已选条件
                    </button>
                    <button
                      onClick={() => void sendMessageWithText("按默认假设执行")}
                      className="bb-btn bb-btn-warning h-6 px-2 text-[10px]"
                      title="按默认假设执行"
                    >
                      按默认执行
                    </button>
                  </div>
                </div>
              )}
            {m.role === "assistant" && m.pivotSuggestion && (
              <div className="bb-ai-card mt-2 p-2">
                <div className="text-[10px] font-medium">管衡推荐透视视角</div>
                <div className="mt-1 text-[10px] whitespace-pre-wrap">
                  {m.pivotSuggestion.explanation}
                </div>
                <div className="mt-1 text-[10px]">
                  置信度：{Math.round((m.pivotSuggestion.confidence ?? 0) * 100)}%
                </div>
              </div>
            )}
            {m.role === "assistant" && m.replyOptions && m.replyOptions.length > 0 && (
              <div className="mt-2 flex flex-col gap-1.5">
                <div className="text-[10px] text-gray-500">管衡建议的下一步</div>
                <div className="flex flex-wrap gap-1.5">
                  {m.replyOptions.map((opt) => {
                    if (opt.id === "sql_query") {
                      return (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => void sendMessageWithText("确认执行")}
                          className="bb-btn bb-btn-primary h-7 px-2.5 text-[10px]"
                          title="按当前规划执行只读 SQL"
                        >
                          {opt.label}
                        </button>
                      );
                    }
                    if (opt.id === "open_pivot_table") {
                      return (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => {
                            onOpenPivotTable?.(m.pivotSuggestion ?? null);
                            setMessages((prev) => [
                              ...prev,
                              {
                                role: "assistant",
                                content:
                                  "已为您打开「数据透视表」页签。您可在其中拖拽字段到行、列、页区域，并结合筛选查看预算汇总数据。",
                              },
                            ]);
                          }}
                          className="bb-btn bb-btn-secondary h-7 px-2.5 text-[10px]"
                          title="打开中间工作区的数据透视表"
                        >
                          {opt.label}
                        </button>
                      );
                    }
                    if (opt.id === "sql_and_pivot") {
                      return (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => {
                            onOpenPivotTable?.(m.pivotSuggestion ?? null);
                            void sendMessageWithText("确认执行");
                          }}
                          className="bb-btn h-7 border-[#d8d0ee] bg-[var(--bb-ai-soft)] px-2.5 text-[10px] text-[var(--bb-ai)]"
                          title="同时打开数据透视表并执行当前规划的只读 SQL"
                        >
                          {opt.label}
                        </button>
                      );
                    }
                    return (
                      <span key={opt.id} className="bb-grid-chip text-[10px]">
                        {opt.label}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}
            {m.role === "assistant" && m.memoryId && !m.feedbackSubmitted && (
              <div className="mt-2 flex items-center gap-2">
                <button
                  onClick={() => void submitFeedback(idx, true)}
                  className="bb-btn h-6 border-[#b7e2cc] bg-[var(--bb-success-soft)] px-2 text-[10px] text-[var(--bb-success)]"
                  title="满意"
                >
                  <ThumbsUp className="w-3 h-3" />
                  满意
                </button>
                <button
                  onClick={() => void submitFeedback(idx, false)}
                  className="bb-btn h-6 border-[#f3b2ad] bg-[var(--bb-danger-soft)] px-2 text-[10px] text-[var(--bb-danger)]"
                  title="不满意"
                >
                  <ThumbsDown className="w-3 h-3" />
                  不满意
                </button>
              </div>
            )}
          </div>
        ))}
        {sending && (
          <div className="bb-ai-card text-xs shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-blue-700 font-medium">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>管衡正在后台处理当前请求</span>
              </div>
              <span className="text-[10px] text-gray-500">
                {agentWorkingSince ? `已用时 ${Math.max(1, Math.floor((Date.now() - agentWorkingSince) / 1000))}s` : ""}
              </span>
            </div>
            <div className="mt-2 space-y-1.5">
              {AGENT_WORKING_STAGES.map((stage, idx) => {
                const done = idx < agentStageIdx;
                const active = idx === agentStageIdx;
                return (
                  <div
                    key={stage.id}
                    className={`rounded px-2 py-1 border ${
                      active
                        ? "border-blue-300 bg-blue-50"
                        : done
                          ? "border-emerald-200 bg-emerald-50"
                          : "border-gray-200 bg-gray-50"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`inline-block w-1.5 h-1.5 rounded-full ${
                          active ? "bg-blue-500" : done ? "bg-emerald-500" : "bg-gray-300"
                        }`}
                      />
                      <span
                        className={`text-[11px] ${
                          active ? "text-blue-700 font-medium" : done ? "text-emerald-700" : "text-gray-500"
                        }`}
                      >
                        {stage.label}
                      </span>
                    </div>
                    <div className="text-[10px] text-gray-500 mt-0.5">{stage.desc}</div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="bb-chat-input">
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void sendMessage();
              }
            }}
            placeholder="请输入你的预算分析问题"
            disabled={sending}
            className="bb-input flex-1"
          />
          <button
            disabled={!canSend}
            onClick={() => void sendMessage()}
            className={`bb-btn px-3 ${canSend ? "bb-btn-primary" : "bb-btn-secondary cursor-not-allowed"}`}
            title="发送"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="flex gap-1.5 justify-center">
          <button
            onClick={() => {
              setSmartModalOpen(true);
              if (!smartDraft) {
                setSmartDraft(SMART_TEMPLATES[0]);
              }
            }}
            className="bb-icon-btn bg-[var(--bb-bg-subtle)]"
            title="智能提问"
          >
            <Sparkles className="w-4 h-4" />
          </button>
          <button
            onClick={onUploadClick}
            disabled={parsingFile}
            className={`bb-icon-btn ${parsingFile ? "bg-[var(--bb-bg-subtle)] text-[var(--bb-text-muted)] cursor-not-allowed" : "bg-[var(--bb-bg-subtle)]"}`}
            title="上传文件"
          >
            {parsingFile ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          </button>
          <button
            onClick={startVoiceInput}
            className={`bb-icon-btn ${voiceActive ? "bg-[var(--bb-primary-soft)] text-[var(--bb-primary)] animate-pulse" : "bg-[var(--bb-bg-subtle)]"}`}
            title="语音输入"
          >
            {voiceActive ? <AudioLines className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
          </button>
          <button
            onClick={togglePhoneMode}
            className={`bb-icon-btn ${phoneMode ? "bg-[var(--bb-success-soft)] text-[var(--bb-success)]" : "bg-[var(--bb-bg-subtle)]"}`}
            title="电话交流"
          >
            <Phone className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={openHistoryModal}
            className="bb-icon-btn bg-[var(--bb-bg-subtle)]"
            title="历史对话"
          >
            <History className="w-4 h-4" />
          </button>
          <button
            onClick={() => void sendMessageWithText("请按当前已确认口径直接执行查询。")}
            disabled={sending}
            className={`bb-icon-btn ${
              sending
                ? "bg-[var(--bb-bg-subtle)] text-[var(--bb-text-muted)] cursor-not-allowed"
                : "bg-[var(--bb-bg-subtle)]"
            }`}
            title="按当前口径重跑"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>
        <input
          ref={uploadInputRef}
          type="file"
          className="hidden"
          onChange={(e) => void onFileSelected(e)}
          accept=".txt,.doc,.docx,.md,.xlsx,.xlsm,.xltx,.xltm,.html,.htm,.pdf,.png,.jpg,.jpeg,.webp,.bmp,.tiff"
        />
      </div>

      {smartModalOpen && (
        <div className="bb-modal-backdrop z-[100]">
          <div className="bb-modal w-[min(96vw,1600px)] h-[min(90vh,980px)]">
            <div className="bb-modal-header">
              <div className="bb-panel-title">智能问答模板</div>
              <button
                onClick={() => setSmartModalOpen(false)}
                className="bb-icon-btn h-7 w-7"
                title="关闭"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-3 flex-1 min-h-0 grid grid-cols-[1fr_560px] gap-3">
              <div className="bb-panel p-2 min-h-0 overflow-y-auto space-y-1.5">
                {SMART_TEMPLATES.map((tpl, idx) => (
                  <button
                    key={`tpl-${idx}`}
                    onClick={() => setSmartDraft(tpl)}
                    className="w-full rounded-[var(--bb-radius-sm)] bg-[var(--bb-bg-subtle)] px-2 py-1.5 text-left text-xs text-[var(--bb-text)] hover:bg-[var(--bb-primary-soft)]"
                    title="点击写入编辑框"
                  >
                    {tpl}
                  </button>
                ))}
              </div>
              <div className="min-h-0 flex gap-2">
                <textarea
                  value={smartDraft}
                  onChange={(e) => setSmartDraft(e.target.value)}
                  placeholder="可继续编辑模板问题"
                  className="bb-textarea flex-1 h-full min-h-0 resize-none"
                />
                <div className="flex flex-col gap-2">
                  <button
                    onClick={() => setSmartDraft((prev) => polishBudgetPrompt(prev))}
                    className="bb-btn bb-btn-secondary"
                    title="让AI帮你润色"
                  >
                    让AI帮你润色
                  </button>
                  <button
                    onClick={() => void sendSmartDraft()}
                    className="bb-btn bb-btn-primary"
                    title="发送"
                  >
                    发送
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {historyModalOpen && (
        <div className="bb-modal-backdrop z-[100]">
          <div className="bb-modal w-[min(96vw,1600px)] h-[min(90vh,980px)]">
            <div className="bb-modal-header">
              <div className="bb-panel-title">历史对话</div>
              <button
                type="button"
                onClick={() => setHistoryModalOpen(false)}
                className="bb-icon-btn h-7 w-7"
                title="关闭"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-3 flex-1 min-h-0 grid grid-cols-[minmax(280px,380px)_1fr] gap-3">
              <div className="bb-panel p-2 min-h-0 overflow-y-auto space-y-1.5">
                {sortedSessions.length === 0 && <div className="text-xs text-gray-500">暂无历史会话</div>}
                {sortedSessions.map((s) => {
                  const firstAt = s.firstUserAt ?? s.createdAt;
                  const isCurrent = s.id === currentSessionId;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onMouseEnter={() => setHistoryModalPreviewId(s.id)}
                      onClick={() => restoreSession(s.id)}
                      className={`w-full text-left px-2 py-1.5 text-xs rounded border ${
                        isCurrent
                          ? "bg-indigo-50 border-indigo-200 text-indigo-900"
                          : historyModalPreviewId === s.id
                            ? "bg-indigo-100/60 border-indigo-100 text-gray-800"
                            : "bg-gray-50 border-transparent text-gray-700 hover:bg-gray-100"
                      }`}
                      title="点击恢复该对话并继续"
                    >
                      <div className="font-medium">{s.topic}</div>
                      <div className="text-[10px] text-gray-500 mt-1 space-y-0.5">
                        <div>首次对话：{formatSessionDateTime(firstAt)}</div>
                        <div>最后对话：{formatSessionDateTime(s.lastMessageAt)}</div>
                        <div>共 {s.messages.length} 条消息{isCurrent ? " · 当前" : ""}</div>
                      </div>
                    </button>
                  );
                })}
              </div>
              <div className="bb-panel p-2 min-h-0 overflow-y-auto flex flex-col gap-2">
                <div className="text-[10px] text-gray-500 shrink-0">
                  预览（鼠标移到左侧条目可切换）。点击左侧条目将打开该会话并关闭此窗口。
                </div>
                {!activeHistoryPreview && <div className="text-xs text-gray-500">暂无预览</div>}
                {activeHistoryPreview?.messages.map((msg, idx) => (
                  <div
                    key={`history-preview-${activeHistoryPreview.id}-${idx}`}
                    className={`bb-chat-message px-2 py-1.5 text-xs ${
                      msg.role === "user"
                        ? "bb-chat-message-user"
                        : "bb-chat-message-assistant"
                    }`}
                  >
                    <span className="inline-block mb-1 text-[10px] text-gray-500">
                      {msg.role === "user" ? "用户" : "管衡"}
                    </span>
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>
                ))}
                {activeHistoryPreview && (
                  <button
                    type="button"
                    onClick={() => restoreSession(activeHistoryPreview.id)}
                    className="bb-btn bb-btn-primary mt-auto shrink-0"
                  >
                    打开此对话并继续
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
