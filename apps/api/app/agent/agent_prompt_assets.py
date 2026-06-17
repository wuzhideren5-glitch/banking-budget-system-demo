from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ASSET_CACHE: dict[str, Any] = {}


def _prompts_dir(kb_root: Path) -> Path:
    return kb_root / "06_agent_prompts"


def _asset_mtime_sum(kb_root: Path) -> float:
    base = _prompts_dir(kb_root)
    total = 0.0
    for name in (
        "product_manager_intent_system.md",
        "product_manager_intent_user.md",
        "product_manager_intent_messages.json",
        "product_manager_intent_catalog.md",
        "product_manager_intent_metric_rules.md",
        "product_manager_intent_org_hints.json",
    ):
        p = base / name
        try:
            total += p.stat().st_mtime
        except OSError:
            total += 0.0
    return total


def load_product_manager_intent_assets(kb_root: Path) -> tuple[str, str, dict[str, Any], str]:
    """从 resources/knowledge_base/06_agent_prompts 加载产品经理意图分类所需文案、模板与静态科目快照。"""
    base = _prompts_dir(kb_root)
    system_path = base / "product_manager_intent_system.md"
    user_path = base / "product_manager_intent_user.md"
    msg_path = base / "product_manager_intent_messages.json"
    catalog_path = base / "product_manager_intent_catalog.md"
    metric_rules_path = base / "product_manager_intent_metric_rules.md"
    if not system_path.is_file() or not user_path.is_file() or not msg_path.is_file():
        raise FileNotFoundError(
            f"缺少 Agent 提示词文件，请检查目录是否存在且包含："
            f"{system_path.name}、{user_path.name}、{msg_path.name}（路径：{base}）"
        )
    if not catalog_path.is_file():
        raise FileNotFoundError(
            f"缺少静态科目快照 {catalog_path.name}。请将科目导出到该文件，或运行："
            f"机构及产品指标导出流程（路径：{catalog_path}）"
        )
    system = system_path.read_text(encoding="utf-8").strip()
    user_tmpl = user_path.read_text(encoding="utf-8")
    db_catalog = catalog_path.read_text(encoding="utf-8").strip()
    rules_text = ""
    if metric_rules_path.is_file():
        rules_text = metric_rules_path.read_text(encoding="utf-8").strip()
    if rules_text:
        catalog_static = f"{rules_text}\n\n---\n\n{db_catalog}".strip()
    else:
        catalog_static = db_catalog
    messages = json.loads(msg_path.read_text(encoding="utf-8"))
    if not isinstance(messages, dict):
        raise ValueError(f"{msg_path} 根节点必须是 JSON 对象")
    return system, user_tmpl, messages, catalog_static


def get_product_manager_intent_assets(kb_root: Path) -> tuple[str, str, dict[str, Any], str]:
    """按文件 mtime 做进程内缓存；修改任意提示词或科目快照后同进程内下一次请求重新加载。"""
    key = str(kb_root.resolve())
    mt = _asset_mtime_sum(kb_root)
    cached = _ASSET_CACHE.get(key)
    if cached and cached.get("mt") == mt:
        return cached["system"], cached["user_tmpl"], cached["messages"], cached["catalog_static"]
    system, user_tmpl, messages, catalog_static = load_product_manager_intent_assets(kb_root)
    _ASSET_CACHE[key] = {
        "mt": mt,
        "system": system,
        "user_tmpl": user_tmpl,
        "messages": messages,
        "catalog_static": catalog_static,
    }
    return system, user_tmpl, messages, catalog_static
