"""飞书长连接机器人：接收消息、用户绑定、调用预算智能体并回复。"""

from __future__ import annotations

import asyncio
import json
import re
import ssl
import threading

import lark_oapi as lark
import lark_oapi.ws.client as lark_ws_mod
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1
from lark_oapi.api.im.v1.model.reply_message_request import ReplyMessageRequest
from lark_oapi.api.im.v1.model.reply_message_request_body import ReplyMessageRequestBody
from lark_oapi.core.enum import LogLevel
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.ws.client import Client as FeishuWsClient

from app.agent_graph import AgentGraphService
from app.config import settings
from app.db_paths import common_db_path
from app.feishu_store import get_user_id_for_open_id, try_bind_with_password

_history_lock = threading.Lock()
_message_history: dict[str, list[dict[str, str]]] = {}
_processed_ids_lock = threading.Lock()
_processed_message_ids: set[str] = set()
_pending_option_lock = threading.Lock()
_pending_text_options: dict[str, list[dict[str, str]]] = {}

_MAX_HISTORY_TURNS = 10
_MAX_REPLY_CHARS = 12000
_MAX_DEDUPE_IDS = 4000
_MAX_PENDING_OPTIONS = 30


def _parse_numeric_option_index(user_text: str) -> int | None:
    text = (user_text or "").strip()
    if not text:
        return None
    trans = str.maketrans("０１２３４５６７８９", "0123456789")
    t = text.translate(trans).strip()
    m = re.fullmatch(r"(?:选|选项)?\s*([1-9]\d?)\s*[\.、\)）]?\s*", t)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _patch_websockets_insecure_if_needed() -> None:
    """公司代理/自建 CA 导致 WSS 校验失败时，可临时关闭校验（见 settings.feishu_insecure_ssl）。"""
    if not settings.feishu_insecure_ssl:
        return
    import websockets

    _orig = websockets.connect

    def connect(uri, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs.setdefault("ssl", ctx)
        return _orig(uri, *args, **kwargs)

    websockets.connect = connect  # type: ignore[method-assign]


def _history_key(open_id: str, chat_id: str) -> str:
    return f"{open_id}:{chat_id}"


def _append_history(open_id: str, chat_id: str, role: str, content: str) -> None:
    key = _history_key(open_id, chat_id)
    with _history_lock:
        h = _message_history.setdefault(key, [])
        h.append({"role": role, "content": content})
        if len(h) > _MAX_HISTORY_TURNS * 2:
            h[:] = h[-_MAX_HISTORY_TURNS * 2 :]


def _history_snapshot(open_id: str, chat_id: str) -> list[dict[str, str]]:
    key = _history_key(open_id, chat_id)
    with _history_lock:
        return list(_message_history.get(key, []))


def _set_pending_options(open_id: str, chat_id: str, options: list[dict[str, str]]) -> None:
    key = _history_key(open_id, chat_id)
    with _pending_option_lock:
        if options:
            _pending_text_options[key] = options[:_MAX_PENDING_OPTIONS]
        else:
            _pending_text_options.pop(key, None)


def _get_pending_options(open_id: str, chat_id: str) -> list[dict[str, str]]:
    key = _history_key(open_id, chat_id)
    with _pending_option_lock:
        return list(_pending_text_options.get(key, []))


def _consume_numeric_option(open_id: str, chat_id: str, user_text: str) -> tuple[str, str | None]:
    idx = _parse_numeric_option_index(user_text)
    if idx is None:
        return user_text, None
    options = _get_pending_options(open_id, chat_id)
    if not options:
        # 不阻断：交给 Agent 基于历史上下文再次识别编号选项。
        return user_text, None
    if not (1 <= idx <= len(options)):
        return "", f"选项 {idx} 超出范围，请回复 1 到 {len(options)} 之间的数字。"
    chosen = options[idx - 1]
    mapped_query = str(chosen.get("query_text") or "").strip()
    if not mapped_query:
        return "", "该选项暂不可执行，请重新描述你的需求。"
    label = str(chosen.get("label") or f"选项{idx}")
    return mapped_query, f"已选择：{idx}）{label}"


def _build_text_options_and_footer(result: dict[str, object]) -> tuple[list[dict[str, str]], str]:
    menu: list[dict[str, str]] = []
    lines: list[str] = []

    reply_options = result.get("reply_options")
    if isinstance(reply_options, list):
        for item in reply_options:
            if not isinstance(item, dict):
                continue
            oid = str(item.get("id") or "").strip()
            label = str(item.get("label") or "").strip()
            if not oid or not label:
                continue
            if oid == "sql_query":
                query_text = "确认执行"
            elif oid == "open_pivot_table":
                query_text = "请打开数据透视表"
            elif oid == "sql_and_pivot":
                query_text = "确认执行并打开数据透视表"
            else:
                query_text = label
            menu.append({"label": label, "query_text": query_text, "kind": "reply_option"})

    clarification_options = result.get("clarification_options")
    if isinstance(clarification_options, dict):
        for slot in sorted(clarification_options.keys()):
            raw_opts = clarification_options.get(slot)
            if not isinstance(raw_opts, list):
                continue
            for opt in raw_opts:
                text = str(opt or "").strip()
                if not text:
                    continue
                menu.append({"label": f"{slot}: {text}", "query_text": text, "kind": "clarification_option"})

    if not menu:
        return [], ""
    for i, item in enumerate(menu, start=1):
        lines.append(f"{i}）{item['label']}")
    footer = "可直接回复数字选择：\n" + "\n".join(lines)
    return menu, footer


def _build_runtime_trace_text(result: dict[str, object]) -> str:
    intent = str(result.get("intent_type") or "unknown")
    next_action = str(result.get("next_action") or "unknown")
    need_clar = bool(result.get("need_clarification", False))
    missing = [str(x) for x in (result.get("missing_slots") or []) if str(x).strip()]
    executed = bool(result.get("executed_result"))
    row_count = int((result.get("executed_result") or {}).get("row_count", 0))

    lines = ["【Agent处理轨迹】"]
    lines.append(f"1）意图识别：{intent}")
    if need_clar:
        miss_txt = "、".join(missing) if missing else "信息不完整"
        lines.append(f"2）需求校验：需澄清（缺失：{miss_txt}）")
        lines.append("3）节点路由：clarify（待你补充后继续）")
        lines.append("4）结果生成：已返回澄清问题")
        return "\n".join(lines)

    lines.append("2）需求校验：通过")
    lines.append(f"3）节点路由：{next_action}")
    if executed:
        lines.append(f"4）只读执行：完成（返回 {row_count} 行）")
    else:
        lines.append("4）只读执行：未执行（当前为规划/通用问答）")
    lines.append("5）结果生成：完成")
    return "\n".join(lines)


def _strip_runtime_trace_section(text: str) -> str:
    s = str(text or "")
    # 宽匹配清理“Agent处理轨迹”区块：兼容方括号/冒号/Markdown 标题等变体写法。
    s = re.sub(
        r"\n?\s*(?:[#>*\-\s]*)?(?:【?\s*Agent处理轨迹\s*】?\s*[:：]?)\s*[\s\S]*?(?=(?:\n可直接回复数字选择：)|\Z)",
        "\n",
        s,
        flags=re.IGNORECASE,
    )
    # 兜底：若仍残留关键词，直接去除关键词行，避免最终对用户可见。
    s = re.sub(r"(?im)^\s*[#>*\-\s]*【?\s*Agent处理轨迹\s*】?\s*[:：]?\s*$", "", s)
    return s.strip()


def _dedupe_message(message_id: str) -> bool:
    """若已处理过则返回 True（应跳过）。"""
    if not message_id:
        return False
    with _processed_ids_lock:
        if message_id in _processed_message_ids:
            return True
        _processed_message_ids.add(message_id)
        if len(_processed_message_ids) > _MAX_DEDUPE_IDS:
            _processed_message_ids.clear()
        return False


def _build_lark_client() -> lark.Client:
    return (
        lark.Client.builder()
        .app_id(settings.feishu_app_id)
        .app_secret(settings.feishu_app_secret)
        .domain(settings.feishu_domain)
        .log_level(LogLevel.INFO)
        .build()
    )


def _reply_text(client: lark.Client, message_id: str, text: str) -> None:
    text = _strip_runtime_trace_section(text)
    body = (
        ReplyMessageRequestBody.builder()
        .msg_type("text")
        .content(json.dumps({"text": text}, ensure_ascii=False))
        .build()
    )
    req = ReplyMessageRequest.builder().message_id(message_id).request_body(body).build()
    resp = client.im.v1.message.reply(req)
    if not resp.success():
        msg = getattr(resp, "msg", None) or ""
        raise RuntimeError(f"feishu reply failed: code={resp.code} msg={msg}")


def _parse_incoming_text(content: str | None) -> str | None:
    if not content:
        return None
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and "text" in data:
        return str(data.get("text") or "").strip()
    return None


def _handle_bind_command(open_id: str, text: str) -> tuple[bool, str | None]:
    """返回 (是否命中绑定命令, 提示文案)。"""
    parts = text.strip().split(None, 2)
    if len(parts) < 1 or parts[0] != "绑定":
        return False, None
    if len(parts) < 3:
        return True, '用法：发送「绑定 用户名 日常登录密码」（密码中请勿含空格）。'
    user_name, password = parts[1], parts[2]
    ok, msg = try_bind_with_password(common_db_path(), open_id, user_name, password)
    return True, msg if ok else msg


def _run_agent_and_reply(
    agent: AgentGraphService,
    client: lark.Client,
    message_id: str,
    open_id: str,
    chat_id: str,
    user_text: str,
) -> None:
    try:
        _reply_text(
            client,
            message_id,
            "已收到，Agent 正在后台处理。\n"
            "当前进度：\n"
            "1）意图识别\n"
            "2）需求校验\n"
            "3）节点路由\n"
            "4）执行/生成\n"
            "请稍候…",
        )
        effective_text, pick_notice = _consume_numeric_option(open_id, chat_id, user_text)
        if not effective_text:
            _reply_text(client, message_id, pick_notice or "输入无效，请重试。")
            return
        hist_before = _history_snapshot(open_id, chat_id)
        result = agent.chat(
            query=effective_text,
            history=hist_before,
            top_k=5,
            trace_context={
                "channel": "feishu",
                "session_id": f"feishu:{open_id}:{chat_id}",
                "user_name": open_id,
            },
        )
        reply = str(result.get("reply") or "").strip() or "（无回复内容）"
        reply = _strip_runtime_trace_section(reply)
        options, menu_footer = _build_text_options_and_footer(result)
        _set_pending_options(open_id, chat_id, options)
        if pick_notice:
            reply = f"{pick_notice}\n\n{reply}"
        if menu_footer:
            reply = f"{reply.rstrip()}\n\n{menu_footer}"
        if len(reply) > _MAX_REPLY_CHARS:
            reply = reply[: _MAX_REPLY_CHARS] + "\n…（内容过长已截断）"
        if effective_text != user_text:
            _append_history(open_id, chat_id, "user", f"{user_text}（对应：{effective_text}）")
        else:
            _append_history(open_id, chat_id, "user", user_text)
        _append_history(open_id, chat_id, "assistant", reply)
        _reply_text(client, message_id, reply)
    except Exception as e:
        _reply_text(client, message_id, f"处理失败：{e}")


def _on_message_receive(agent: AgentGraphService, client: lark.Client, event: P2ImMessageReceiveV1) -> None:
    try:
        data = event.event
        if not data or not data.message or not data.sender:
            return
        msg = data.message
        sender = data.sender
        if (sender.sender_type or "").lower() in {"app"}:
            return
        if _dedupe_message(str(msg.message_id or "")):
            return
        if (msg.message_type or "") != "text":
            _reply_text(client, str(msg.message_id), "暂仅支持文本消息。")
            return
        open_id = None
        if sender.sender_id is not None:
            open_id = sender.sender_id.open_id
        if not open_id:
            return
        text = _parse_incoming_text(msg.content)
        if not text:
            return
        mid = str(msg.message_id or "")
        cid = str(msg.chat_id or "")

        hit, bind_msg = _handle_bind_command(open_id, text)
        if hit:
            _reply_text(client, mid, bind_msg or "")
            return

        user_id = get_user_id_for_open_id(common_db_path(), open_id)
        if user_id is None:
            _reply_text(
                client,
                mid,
                "尚未绑定预算账号。请使用系统登录名与日常登录密码发送：\n"
                "绑定 你的用户名 你的密码\n"
                "（密码中请勿含空格；也可由管理员在系统后台绑定。）",
            )
            return

        def job() -> None:
            _run_agent_and_reply(agent, client, mid, open_id, cid, text)

        threading.Thread(target=job, daemon=True).start()
    except Exception:
        # 事件回调需尽快返回；异常已在内部尽量回复
        pass


def start_feishu_background(agent_service: AgentGraphService) -> None:
    """在独立线程中启动飞书 WebSocket 客户端（阻塞式）。"""
    if not settings.feishu_enabled:
        return
    if not (settings.feishu_app_id and settings.feishu_app_secret):
        return

    rest_client = _build_lark_client()

    def run() -> None:
        # lark_oapi.ws.client 在 import 时绑定了全局 asyncio loop，与 Uvicorn(uvloop) 冲突。
        # 在本线程内使用独立事件循环，并替换 SDK 模块级 loop，避免 run_until_complete 报错。
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        lark_ws_mod.loop = new_loop

        _patch_websockets_insecure_if_needed()

        def do_receive(ev: P2ImMessageReceiveV1) -> None:
            _on_message_receive(agent_service, rest_client, ev)

        handler = (
            EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(do_receive)
            .build()
        )

        ws = FeishuWsClient(
            settings.feishu_app_id,
            settings.feishu_app_secret,
            log_level=LogLevel.INFO,
            event_handler=handler,
            domain=settings.feishu_domain,
        )
        ws.start()

    threading.Thread(target=run, name="feishu-ws", daemon=True).start()
