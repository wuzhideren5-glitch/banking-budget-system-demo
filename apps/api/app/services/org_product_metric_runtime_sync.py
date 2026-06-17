"""Sync org/product metric payloads into the runtime metric identity tables."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
from typing import Any

from app.services.org_product_runtime_catalog import org_product_runtime_products_cte
from app.services.runtime_metric_refs import (
    compact_org_product_metric_code,
    derive_runtime_ref_from_org_product_metric_code,
)
from app.services.org_product_metric_runtime_snapshot import (
    load_org_product_metric_payload_from_runtime_tree,
    load_org_product_metric_table_rows_from_runtime_tree,
)

LOCAL_METRIC_CODE_PATTERN = r"\d{2}(?:\.\d{2})*(?:\.\d{3})?"
PRODUCT_ROOT_RE = re.compile(r"^[A-Z][A-Z0-9]*$")
PRODUCT_PREFIXED_METRIC_CODE_RE = re.compile(
    rf"^[A-Z][A-Z0-9]*\.{LOCAL_METRIC_CODE_PATTERN}$"
)


# ─── 异常类与数据类 ───

class OrgProductMetricRuntimeSyncError(ValueError):
    """Raised when org/product metric refs cannot become the runtime key."""


@dataclass(frozen=True)
class OrgProductMetricRuntimeSyncResult:
    normalized_refs: int = 0
    created_or_updated_nodes: int = 0
    created_or_updated_accounts: int = 0
    created_or_updated_bindings: int = 0


@dataclass(frozen=True)
class OrgProductMetricRuntimeMergeResult:
    merged_refs: int = 0
    touched_tables: int = 0
    normalized_refs: int = 0


@dataclass(frozen=True)
class _RuntimeMetricRef:
    code: str
    name: str
    value_type: str
    allow_manual_entry: int
    sort_order: int
    source_code: str
    horizontal_rollup: int
    vertical_rollup: int
    logic_code: str


# ─── 编码归一化与辅助函数 ───

def _normalize_code(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _is_product_root(code: str) -> bool:
    return PRODUCT_ROOT_RE.fullmatch(code) is not None


def _is_product_prefixed_metric_code(code: str) -> bool:
    return PRODUCT_PREFIXED_METRIC_CODE_RE.fullmatch(code) is not None


def _normalize_legacy_corp_ref(code: str) -> str:
    normalized = _normalize_code(code)
    if normalized.startswith("CORP."):
        return "AA." + normalized[len("CORP.") :]
    return normalized


def _split_display_code_name(value: Any) -> tuple[str, str]:
    text = _normalize_text(value)
    if not text:
        return "", ""
    parts = text.split(maxsplit=1)
    code = _normalize_legacy_corp_ref(parts[0])
    name = parts[1].strip() if len(parts) > 1 else ""
    return code, name


def _display_code_name(code: str, name: str) -> str:
    return f"{code} {name}".strip()


def _parent_code(code: str) -> str | None:
    if "." not in code:
        return None
    return code.rsplit(".", 1)[0]


def _product_code(code: str) -> str:
    return code.split(".", 1)[0]


def _local_metric_code(code: str) -> str:
    return code.split(".", 1)[1] if "." in code else ""


def _derive_runtime_ref_from_metric_code(*, entity_code: str, metric_code: Any) -> str:
    return derive_runtime_ref_from_org_product_metric_code(
        entity_code=entity_code,
        metric_code=metric_code,
    )


def _level(code: str) -> int:
    return code.count(".") + 1


def _scope_type(code: str) -> str:
    return "CORP" if _product_code(code) == "CORP" else "PRODUCT"


def _compact_org_product_metric_code(code: str) -> str:
    normalized = _normalize_code(code)
    if not _is_product_prefixed_metric_code(normalized):
        return ""
    return compact_org_product_metric_code(normalized)


def _level_label_for_node_level(level: int) -> str:
    labels = ("一级", "二级", "三级", "四级", "五级", "六级")
    index = max(0, min(len(labels) - 1, int(level or 2) - 2))
    return labels[index]


def _canonical_metric_table_name(value: Any) -> str:
    text = _normalize_text(value)
    if text in {"资产负债表(余额)", "资产负债表余额"}:
        return "资产负债表（余额）"
    if text in {"资产负债表(日均)", "资产负债表日均"}:
        return "资产负债表（日均）"
    if text in {"资产质量"}:
        return "资产质量表"
    if text in {"净利息收入表"}:
        return "利息净收入表"
    if text in {"业务状况表", "损益表", "资产负债表（余额）", "资产负债表（日均）", "资产质量表", "利息净收入表", "业务支出评估"}:
        return text
    return "业务状况表"


def _default_table_name_for_metric_code(code: str) -> str:
    return "业务状况表"


def _normalize_value_type(value: Any, nature: Any = "") -> str:
    text = _normalize_text(value)
    if text in {"金额", "百分比", "户数"}:
        return text
    nature_text = _normalize_text(nature)
    if nature_text in {"比例", "百分比", "率"}:
        return "百分比"
    if nature_text in {"户数", "人数", "笔数"}:
        return "户数"
    return "金额"


def _normalize_allow_manual_entry(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 0 if int(value) == 0 else 1
    text = _normalize_text(value).lower()
    if text in {"0", "false", "否", "不允许", "no", "n"}:
        return 0
    return 1


def _normalize_rollup_flag(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 0 if float(value) == 0 else 1
    text = _normalize_text(value).lower()
    if not text:
        return 0
    if text in {"0", "false", "否", "不", "no", "n", "不汇总", "无需汇总"}:
        return 0
    return 1


def _iter_metric_nodes(metrics: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    stack = list(metrics)
    while stack:
        node = stack.pop(0)
        if not isinstance(node, dict):
            continue
        rows.append(node)
        children = node.get("children")
        if isinstance(children, list):
            stack[0:0] = [child for child in children if isinstance(child, dict)]
    return tuple(rows)


def _payload_node_dedupe_key(node: dict[str, Any]) -> str:
    raw_code = _normalize_code(node.get("code"))
    entity = _product_code(raw_code)
    if entity == raw_code:
        match = re.match(r"^[A-Z]\d{2}", raw_code)
        entity = match.group(0) if match else entity
    code = _derive_runtime_ref_from_metric_code(
        entity_code=entity,
        metric_code=raw_code,
    ) or raw_code.replace(".", "")
    if code:
        return f"code:{code}"
    return ""


def _merge_duplicate_payload_node(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        "levelLabel",
        "nature",
        "code",
        "name",
        "value_type",
        "note",
        "formula",
        "formula_budget_annual",
        "formula_forecast_annual",
        "formula_actual",
        "formula_forecast",
        "formula_note",
        "entry_granularity",
        "logic_code",
    ):
        if target.get(key) in (None, "") and source.get(key) not in (None, ""):
            target[key] = source[key]
    for key in ("allow_manual_entry", "horizontal_rollup", "vertical_rollup"):
        if target.get(key) in (None, "") and source.get(key) not in (None, ""):
            target[key] = source[key]

    target_children = target.get("children")
    if not isinstance(target_children, list):
        target_children = []
        target["children"] = target_children
    source_children = source.get("children")
    if isinstance(source_children, list):
        target_children.extend(child for child in source_children if isinstance(child, dict))


def dedupe_org_product_metric_payload_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicate sibling metric nodes by their runtime ref or metric code."""
    deduped: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for raw_node in nodes:
        if not isinstance(raw_node, dict):
            continue
        node = raw_node
        children = node.get("children")
        node["children"] = dedupe_org_product_metric_payload_nodes(
            [child for child in children if isinstance(child, dict)]
        ) if isinstance(children, list) else []

        key = _payload_node_dedupe_key(node)
        if key and key in seen:
            existing = seen[key]
            node_is_canonical = _normalize_text(node.get("id")).startswith("canonical-")
            existing_is_canonical = _normalize_text(existing.get("id")).startswith("canonical-")
            if node_is_canonical and not existing_is_canonical:
                _merge_duplicate_payload_node(node, existing)
                idx = deduped.index(existing)
                deduped[idx] = node
                seen[key] = node
            else:
                _merge_duplicate_payload_node(existing, node)
            continue
        deduped.append(node)
        if key:
            seen[key] = node

    for node in deduped:
        children = node.get("children")
        if isinstance(children, list) and children:
            node["children"] = dedupe_org_product_metric_payload_nodes(
                [child for child in children if isinstance(child, dict)]
            )
    return deduped


def _payload_node_meta_by_code(metrics: list[dict[str, Any]], *, entity_code: str) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    entity = _normalize_code(entity_code)
    queue: list[tuple[dict[str, Any], str]] = [(node, "") for node in metrics if isinstance(node, dict)]
    while queue:
        node, parent_code = queue.pop(0)
        code = _derive_runtime_ref_from_metric_code(entity_code=entity, metric_code=node.get("code"))
        children = node.get("children")
        if isinstance(children, list):
            queue[0:0] = [
                (child, code)
                for child in children
                if isinstance(child, dict)
            ]
        if not code:
            continue
        logic_code = _normalize_code(node.get("logic_code"))
        if not logic_code and entity and code.startswith(f"{entity}."):
            logic_code = code[len(entity) + 1 :]
        meta[code] = {
            "name": _normalize_text(node.get("name")),
            "parent_code": parent_code,
            "horizontal_rollup": _normalize_rollup_flag(node.get("horizontal_rollup")),
            "vertical_rollup": _normalize_rollup_flag(node.get("vertical_rollup")),
            "logic_code": logic_code or _local_metric_code(code),
        }
    return meta


def _resolve_runtime_ref(node: dict[str, Any], *, entity_code: str, table_name: str) -> str:
    ref = _derive_runtime_ref_from_metric_code(
        entity_code=entity_code,
        metric_code=node.get("code"),
    )
    if not ref:
        node.pop("metric_node_code", None)
        node.pop("data_acct_code", None)
        node.pop("mapping_status", None)
        return ""
    node.pop("metric_node_code", None)
    node.pop("data_acct_code", None)
    node.pop("mapping_status", None)
    return ref


def normalize_org_product_metric_runtime_refs(
    metrics: list[dict[str, Any]],
    *,
    entity_code: str,
    table_name: str,
) -> tuple[_RuntimeMetricRef, ...]:
    refs: dict[str, _RuntimeMetricRef] = {}
    for sort_order, node in enumerate(_iter_metric_nodes(metrics), start=1):
        ref = _resolve_runtime_ref(node, entity_code=entity_code, table_name=table_name)
        if not ref:
            continue
        name = _normalize_text(node.get("name")) or ref
        refs[ref] = _RuntimeMetricRef(
            code=ref,
            name=name,
            value_type=_normalize_value_type(node.get("value_type"), node.get("nature")),
            allow_manual_entry=_normalize_allow_manual_entry(node.get("allow_manual_entry")),
            sort_order=sort_order,
            source_code=_normalize_text(node.get("code")),
            horizontal_rollup=_normalize_rollup_flag(node.get("horizontal_rollup")),
            vertical_rollup=_normalize_rollup_flag(node.get("vertical_rollup")),
            logic_code=_normalize_code(node.get("logic_code")) or _local_metric_code(ref),
        )
    return tuple(refs.values())


def _product_names(conn: sqlite3.Connection) -> dict[str, str]:
    try:
        return {
            _normalize_code(code): _normalize_text(name)
            for code, name in conn.execute(
                f"""
                {org_product_runtime_products_cte()}
                SELECT product_code, product_name
                FROM org_product_runtime_products
                WHERE product_code <> '' AND product_name <> ''
                """
            )
            if _normalize_code(code) and _normalize_text(name)
        }
    except sqlite3.Error:
        return {}


def _existing_node_names(conn: sqlite3.Connection) -> dict[str, str]:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='data_account_metric_node'"
    ).fetchone()
    if not row:
        return {}
    return {
        _normalize_code(code): _normalize_text(name)
        for code, name in conn.execute("SELECT node_code, node_name FROM data_account_metric_node")
        if _normalize_code(code) and _normalize_text(name)
    }


def _node_name(
    code: str,
    ref_names: dict[str, str],
    product_names: dict[str, str],
    existing_names: dict[str, str],
    child_names: dict[str, str] | None = None,
) -> str:
    """Return the best available name for a metric node.

    Priority: explicit name from payload → existing DB name → product name →
    code as fallback → child-name derivation.
    Implicit (auto-created) parent nodes always receive a valid name:
    - If the node has a code, use it as the name (``name = code``).
    - If code is also empty (degenerate case), derive from a child:
      ``name = f"[{child_name}的父节点]"``.
    """
    if code in ref_names and ref_names[code]:
        return ref_names[code]
    if code in existing_names and existing_names[code]:
        return existing_names[code]
    if _is_product_root(code):
        return product_names.get(code) or code
    # 隐式父节点（GROUP）：优先使用 code 作为名称。
    if code:
        return code
    # 极端情况：code 也为空，从子节点名称派生。
    if child_names:
        sample_child_name = next(iter(child_names.values()), "")
        if sample_child_name:
            return f"[{sample_child_name}的父节点]"
    # 最终兜底
    return "(未命名)"


def _all_node_codes(
    refs: tuple[_RuntimeMetricRef, ...],
    *,
    parent_by_code: dict[str, str],
) -> tuple[str, ...]:
    codes: set[str] = set()
    for ref in refs:
        code = ref.code
        while code:
            codes.add(code)
            code = parent_by_code.get(code) or _parent_code(code) or ""
    return tuple(sorted(codes, key=lambda item: (_level(item), item)))


def sync_org_product_metric_runtime_refs(
    conn: sqlite3.Connection,
    *,
    entity_code: str,
    table_name: str,
    metrics: list[dict[str, Any]],
) -> OrgProductMetricRuntimeSyncResult:
    metrics = dedupe_org_product_metric_payload_nodes(metrics)
    refs = normalize_org_product_metric_runtime_refs(metrics, entity_code=entity_code, table_name=table_name)
    if not refs:
        return OrgProductMetricRuntimeSyncResult()

    product_names = _product_names(conn)
    existing_names = _existing_node_names(conn)
    ref_names = {ref.code: ref.name for ref in refs}
    payload_meta = _payload_node_meta_by_code(metrics, entity_code=entity_code)
    parent_by_code = {
        code: _normalize_code(meta.get("parent_code"))
        for code, meta in payload_meta.items()
        if _normalize_code(meta.get("parent_code"))
    }
    bound_codes = {ref.code for ref in refs}
    parent_codes = {
        parent
        for ref in refs
        if (parent := parent_by_code.get(ref.code) or _parent_code(ref.code))
    }
    # Build child→name map so that implicit parents without a name can derive
    # one from their children (e.g. "[利息收入的父节点]").
    child_names: dict[str, str] = {
        ref.code: ref.name for ref in refs if ref.name
    }

    node_count = 0
    for node_code in _all_node_codes(refs, parent_by_code=parent_by_code):
        product_code = _product_code(node_code)
        local_code = _local_metric_code(node_code)
        meta = payload_meta.get(node_code, {})
        parent_code = parent_by_code.get(node_code) or _parent_code(node_code)
        logic_code = local_code
        horizontal_rollup = _normalize_rollup_flag(meta.get("horizontal_rollup"))
        vertical_rollup = _normalize_rollup_flag(meta.get("vertical_rollup"))
        node_type = "CATEGORY" if _is_product_root(node_code) else ("GROUP" if node_code in parent_codes else "METRIC")
        conn.execute(
            """
            INSERT INTO data_account_metric_node(
              node_code, node_name, parent_code, product_code, local_metric_code, logic_code,
              functional_group_code, metric_table_name, level, node_type, horizontal_rollup, vertical_rollup,
              sort_order, is_active, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(node_code) DO UPDATE SET
              node_name=excluded.node_name,
              parent_code=excluded.parent_code,
              product_code=excluded.product_code,
              local_metric_code=excluded.local_metric_code,
              logic_code=excluded.logic_code,
              functional_group_code=excluded.functional_group_code,
              metric_table_name=excluded.metric_table_name,
              level=excluded.level,
              node_type=CASE
                WHEN excluded.node_type='GROUP' AND data_account_metric_node.node_type='METRIC' THEN 'GROUP'
                WHEN excluded.node_type='CATEGORY' THEN 'CATEGORY'
                ELSE data_account_metric_node.node_type
              END,
              horizontal_rollup=excluded.horizontal_rollup,
              vertical_rollup=excluded.vertical_rollup,
              is_active=1,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                node_code,
                _node_name(node_code, ref_names, product_names, existing_names, child_names=child_names),
                parent_code,
                product_code,
                local_code,
                logic_code,
                _normalize_text(table_name),
                _canonical_metric_table_name(table_name),
                _level(node_code),
                node_type,
                horizontal_rollup,
                vertical_rollup,
                0 if _is_product_root(node_code) else _level(node_code) * 10,
                "来源：机构及产品指标主表同步",
            ),
        )
        node_count += 1

    account_count = 0
    for ref in refs:
        conn.execute(
            """
            UPDATE data_account_metric_node
            SET node_name=?,
                runtime_account_enabled=1,
                allow_manual_entry=?,
                value_type=?,
                remark=COALESCE(remark, ?),
                updated_at=CURRENT_TIMESTAMP
            WHERE node_code=?
            """,
            (
                ref.name,
                ref.allow_manual_entry,
                ref.value_type,
                f"来源：机构及产品指标主表同步；{entity_code}/{table_name}/{ref.source_code or ref.code}",
                ref.code,
            ),
        )
        account_count += 1
        bound_codes.add(ref.code)

    return OrgProductMetricRuntimeSyncResult(
        normalized_refs=len(bound_codes),
        created_or_updated_nodes=node_count,
        created_or_updated_accounts=account_count,
        created_or_updated_bindings=len(bound_codes),
    )


# ─── 运行指标同步主流程 ───

def sync_existing_org_product_metric_tables(conn: sqlite3.Connection) -> OrgProductMetricRuntimeSyncResult:
    """One-time migration: sync remaining rows from the retired org_product_metric_table
    into data_account_metric_node, then DROP the old table.

    NOTE: The old org_product_metric_table has been retired.  This function is
    kept as a no-op guard for backward compatibility — if the table no longer
    exists (as expected), it returns immediately.
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='org_product_metric_table'"
    ).fetchone()
    if not row:
        return OrgProductMetricRuntimeSyncResult()

    total = OrgProductMetricRuntimeSyncResult()
    rows = list(conn.execute(
        """
        SELECT entity_code, table_name, payload_json
        FROM org_product_metric_table
        ORDER BY entity_code, table_name
        """
    ))
    for entity_code, table_name, payload_json in rows:
        try:
            payload = json.loads(payload_json or "{}")
        except Exception as exc:
            raise OrgProductMetricRuntimeSyncError(
                f"{_normalize_code(entity_code)}/{_normalize_text(table_name)} 指标表 JSON 无法解析"
            ) from exc
        metrics = payload.get("metrics") if isinstance(payload, dict) else []
        if not isinstance(metrics, list):
            continue
        payload["metrics"] = dedupe_org_product_metric_payload_nodes(
            [item for item in metrics if isinstance(item, dict)]
        )
        result = sync_org_product_metric_runtime_refs(
            conn,
            entity_code=_normalize_code(entity_code),
            table_name=_normalize_text(table_name),
            metrics=payload["metrics"],
        )
        total = OrgProductMetricRuntimeSyncResult(
            normalized_refs=total.normalized_refs + result.normalized_refs,
            created_or_updated_nodes=total.created_or_updated_nodes + result.created_or_updated_nodes,
            created_or_updated_accounts=total.created_or_updated_accounts + result.created_or_updated_accounts,
            created_or_updated_bindings=total.created_or_updated_bindings + result.created_or_updated_bindings,
        )
    # Retired table: drop after successful migration.
    conn.execute("DROP TABLE IF EXISTS org_product_metric_table")
    return total


def normalize_org_product_metric_mapping_statuses(conn: sqlite3.Connection) -> int:
    """Normalize legacy/blank org-product metric mapping statuses.

    NOTE: The old org_product_metric_table has been retired.  This function is
    kept as a no-op guard for backward compatibility — if the table no longer
    exists (as expected), it returns 0 immediately.
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='org_product_metric_table'"
    ).fetchone()
    if not row:
        return 0

    updated_nodes = 0
    table_updates: list[tuple[str, str, str, str]] = []

    def normalize_nodes(nodes: list[dict[str, Any]]) -> None:
        nonlocal updated_nodes
        for node in nodes:
            if not isinstance(node, dict):
                continue
            children = node.get("children")
            if isinstance(children, list):
                normalize_nodes([child for child in children if isinstance(child, dict)])
            changed = False
            for legacy_key in ("mapping_status", "metric_node_code", "data_acct_code"):
                if legacy_key in node:
                    node.pop(legacy_key, None)
                    changed = True
            if changed:
                updated_nodes += 1

    rows = list(
        conn.execute(
            """
            SELECT entity_code, table_name, payload_json
            FROM org_product_metric_table
            ORDER BY entity_code, table_name
            """
        )
    )
    for entity_code, table_name, payload_json in rows:
        try:
            payload = json.loads(payload_json or "{}")
        except Exception:
            continue
        metrics = payload.get("metrics") if isinstance(payload, dict) else []
        if not isinstance(metrics, list):
            continue
        before = updated_nodes
        normalize_nodes([item for item in metrics if isinstance(item, dict)])
        if updated_nodes != before:
            payload["metrics"] = metrics
            table_updates.append((json.dumps(payload, ensure_ascii=False), str(entity_code), str(table_name)))

    for payload_json, entity_code, table_name in table_updates:
        conn.execute(
            """
            UPDATE org_product_metric_table
            SET payload_json=?, updated_at=CURRENT_TIMESTAMP
            WHERE entity_code=? AND table_name=?
            """,
            (payload_json, entity_code, table_name),
        )
    if table_updates:
        conn.commit()
    return updated_nodes


def _load_org_product_metric_ref_codes(conn: sqlite3.Connection) -> set[str]:
    return _collect_runtime_data_account_refs(conn)


def _collect_budget_data_account_refs(budget_paths: list[Path | str] | tuple[Path | str, ...]) -> set[str]:
    refs: set[str] = set()
    targets = (
        ("budget_data", "data_acct_code"),
        ("business_cost_income_item", "data_acct_code"),
        ("business_cost_income_source_mapping", "data_acct_code"),
    )
    for raw_path in budget_paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        conn = sqlite3.connect(path)
        try:
            current_tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            for table, column in targets:
                if table not in current_tables:
                    continue
                for (value,) in conn.execute(
                    f"""
                    SELECT DISTINCT {_quote_identifier(column)}
                    FROM {_quote_identifier(table)}
                    WHERE {_quote_identifier(column)} IS NOT NULL
                      AND TRIM({_quote_identifier(column)}) <> ''
                    """
                ):
                    code = _normalize_legacy_corp_ref(str(value or ""))
                    if _is_product_prefixed_metric_code(code):
                        refs.add(code)
        finally:
            conn.close()
    return refs


def normalize_legacy_corp_data_account_refs(
    database_paths: list[Path | str] | tuple[Path | str, ...],
) -> int:
    """Rewrite retired CORP metric refs to AA refs in fact/config tables."""
    targets = (
        ("budget_output_display_item", "data_acct_code"),
        ("budget_data", "data_acct_code"),
        ("business_cost_income_item", "data_acct_code"),
        ("business_cost_income_source_mapping", "data_acct_code"),
    )
    updated = 0
    for raw_path in database_paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        conn = sqlite3.connect(path)
        try:
            current_tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
            }
            for table, column in targets:
                if table not in current_tables:
                    continue
                rows = list(
                    conn.execute(
                        f"""
                        SELECT rowid, {_quote_identifier(column)}
                        FROM {_quote_identifier(table)}
                        WHERE {_quote_identifier(column)} LIKE 'CORP.%'
                        """
                    )
                )
                for rowid, value in rows:
                    normalized = _normalize_legacy_corp_ref(str(value or ""))
                    if normalized and normalized != str(value or "").strip().upper():
                        conn.execute(
                            f"""
                            UPDATE {_quote_identifier(table)}
                            SET {_quote_identifier(column)}=?
                            WHERE rowid=?
                            """,
                            (normalized, rowid),
                        )
                        updated += 1
            conn.commit()
        finally:
            conn.close()
    return updated


def normalize_read_model_data_code_names(
    database_paths: list[Path | str] | tuple[Path | str, ...],
) -> int:
    """Rewrite read-model display keys from retired CORP.* to AA.*."""
    targets = (
        "budget_summary",
        "budget_pivot_aggregate",
        "compare_budget_summary",
        "compare_pivot_aggregate",
    )
    updated = 0
    for raw_path in database_paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        conn = sqlite3.connect(path)
        try:
            current_tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
            }
            for table in targets:
                if table not in current_tables:
                    continue
                rows = list(
                    conn.execute(
                        f"""
                        SELECT rowid, data_code_name
                        FROM {_quote_identifier(table)}
                        WHERE data_code_name LIKE 'CORP.%'
                        """
                    )
                )
                for rowid, value in rows:
                    code, name = _split_display_code_name(value)
                    normalized = _display_code_name(code, name)
                    if normalized and normalized != _normalize_text(value):
                        conn.execute(
                            f"UPDATE {_quote_identifier(table)} SET data_code_name=? WHERE rowid=?",
                            (normalized, rowid),
                        )
                        updated += 1
            conn.commit()
        finally:
            conn.close()
    return updated


def _collect_read_model_data_code_refs(
    database_paths: list[Path | str] | tuple[Path | str, ...],
) -> dict[str, str]:
    refs: dict[str, str] = {}
    targets = (
        "budget_summary",
        "budget_pivot_aggregate",
        "compare_budget_summary",
        "compare_pivot_aggregate",
    )
    for raw_path in database_paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        conn = sqlite3.connect(path)
        try:
            current_tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
            }
            for table in targets:
                if table not in current_tables:
                    continue
                for (value,) in conn.execute(
                    f"""
                    SELECT DISTINCT data_code_name
                    FROM {_quote_identifier(table)}
                    WHERE data_code_name IS NOT NULL
                      AND TRIM(data_code_name) <> ''
                    """
                ):
                    code, name = _split_display_code_name(value)
                    if _is_product_prefixed_metric_code(code):
                        refs.setdefault(code, name or code)
        finally:
            conn.close()
    return refs


def _collect_runtime_data_account_refs(conn: sqlite3.Connection) -> set[str]:
    current_tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
    }
    if "data_account" not in current_tables:
        return set()
    return {
        code
        for (raw_code,) in conn.execute("SELECT data_acct_code FROM data_account")
        if (code := _normalize_legacy_corp_ref(str(raw_code or "")))
        and _is_product_prefixed_metric_code(code)
    }


def assert_all_runtime_metric_refs_are_confirmed_org_product_metrics(
    conn: sqlite3.Connection,
    *,
    budget_paths: list[Path | str] | tuple[Path | str, ...],
    read_model_paths: list[Path | str] | tuple[Path | str, ...],
) -> None:
    """Reject runtime refs that would require data-account/read-model backfill."""
    confirmed_refs = _load_org_product_metric_ref_codes(conn)
    runtime_refs = _collect_runtime_data_account_refs(conn)
    budget_refs = _collect_budget_data_account_refs(budget_paths)
    read_model_refs = set(_collect_read_model_data_code_refs(read_model_paths))
    missing = sorted((runtime_refs | budget_refs | read_model_refs) - confirmed_refs)
    if missing:
        preview = ", ".join(missing[:20])
        suffix = "" if len(missing) <= 20 else f" 等 {len(missing)} 条"
        raise OrgProductMetricRuntimeSyncError(
            "运行数据、预算事实或派生读模型引用了机构及产品指标主表未确认的指标；"
            "当前不再从兼容读模型/预算数据反向生成主数据，请先在机构及产品指标表维护："
            f"{preview}{suffix}"
        )


def _quote_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _metric_payload_index(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        _normalize_code(node.get("code")): node
        for node in _iter_metric_nodes([item for item in nodes if isinstance(item, dict)])
        if isinstance(node, dict) and _normalize_code(node.get("code"))
    }


def _sort_metric_payload_nodes(nodes: list[dict[str, Any]]) -> None:
    nodes.sort(key=lambda item: (_normalize_code(item.get("code")), _normalize_text(item.get("name"))))
    for node in nodes:
        children = node.get("children")
        if isinstance(children, list):
            _sort_metric_payload_nodes([item for item in children if isinstance(item, dict)])


def _upsert_metric_payload_node(
    *,
    roots: list[dict[str, Any]],
    index: dict[str, dict[str, Any]],
    parent_ref: str,
    node_ref: str,
    node: dict[str, Any],
) -> bool:
    existing = index.get(node_ref)
    changed = False
    if existing is None:
        parent = index.get(parent_ref)
        if parent is None:
            roots.append(node)
        else:
            children = parent.get("children")
            if not isinstance(children, list):
                children = []
                parent["children"] = children
            children.append(node)
        index[node_ref] = node
        return True

    node_is_canonical = _normalize_text(node.get("id")).startswith("canonical-")
    existing_is_canonical = _normalize_text(existing.get("id")).startswith("canonical-")
    if node_is_canonical and not existing_is_canonical:
        parent = index.get(parent_ref)
        if parent is None:
            roots.append(node)
        else:
            children = parent.get("children")
            if not isinstance(children, list):
                children = []
                parent["children"] = children
            children.append(node)
        index[node_ref] = node
        return True

    for legacy_key in ("metric_node_code", "data_acct_code", "mapping_status"):
        if legacy_key in existing:
            existing.pop(legacy_key, None)
            changed = True
    for key in ("value_type", "allow_manual_entry", "entry_granularity"):
        if existing.get(key) in (None, "") and node.get(key) not in (None, ""):
            existing[key] = node[key]
            changed = True
    return changed


def purge_legacy_corp_metric_master(conn: sqlite3.Connection) -> int:
    """Remove retired CORP entity/runtime rows after refs have been normalized to AA.

    NOTE: The old org_product_metric_table has been retired.  The guard for
    that table is kept for backward compatibility but will be a no-op when the
    table no longer exists.
    """
    current_tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    removed = 0
    if "org_product_metric_table" in current_tables:
        cur = conn.execute("DELETE FROM org_product_metric_table WHERE entity_code='CORP'")
        removed += int(cur.rowcount if cur.rowcount is not None and cur.rowcount > 0 else 0)
    if "data_account_metric_node" in current_tables:
        rows = [
            str(row[0] or "")
            for row in conn.execute(
                """
                SELECT node_code
                FROM data_account_metric_node
                WHERE node_code='CORP' OR node_code LIKE 'CORP.%'
                ORDER BY LENGTH(node_code) DESC
                """
            )
        ]
        for node_code in rows:
            cur = conn.execute("DELETE FROM data_account_metric_node WHERE node_code=?", (node_code,))
            removed += int(cur.rowcount if cur.rowcount is not None and cur.rowcount > 0 else 0)
    return removed


def _common_external_refs_with_prefix(conn: sqlite3.Connection, prefix: str) -> set[str]:
    current_tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    targets = (
        ("budget_output_display_item", "data_acct_code"),
        ("business_cost_income_item", "data_acct_code"),
        ("business_cost_income_source_mapping", "data_acct_code"),
    )
    refs: set[str] = set()
    for table, column in targets:
        if table not in current_tables:
            continue
        for (value,) in conn.execute(
            f"""
            SELECT DISTINCT {_quote_identifier(column)}
            FROM {_quote_identifier(table)}
            WHERE {_quote_identifier(column)} LIKE ?
            """,
            (f"{prefix}.%",),
        ):
            ref = _normalize_code(value)
            if ref:
                refs.add(ref)
    return refs


def purge_unreferenced_legacy_aa05_metric_master(
    conn: sqlite3.Connection,
    *,
    budget_paths: list[Path | str] | tuple[Path | str, ...],
    read_model_paths: list[Path | str] | tuple[Path | str, ...],
) -> int:
    """Remove the old AA.05 expense tree when no fact/read-model still references it."""
    prefix = "AA.05"
    external_refs = _common_external_refs_with_prefix(conn, prefix)
    external_refs.update(ref for ref in _collect_budget_data_account_refs(budget_paths) if ref.startswith(prefix + "."))
    external_refs.update(ref for ref in _collect_read_model_data_code_refs(read_model_paths) if ref.startswith(prefix + "."))
    if external_refs:
        return 0

    current_tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "data_account_metric_node" not in current_tables:
        return 0
    rows = [
        str(row[0] or "")
        for row in conn.execute(
            """
            SELECT node_code
            FROM data_account_metric_node
            WHERE node_code=? OR node_code LIKE ?
            ORDER BY LENGTH(node_code) DESC
            """,
            (prefix, f"{prefix}.%"),
        )
    ]
    removed = 0
    for node_code in rows:
        cur = conn.execute("DELETE FROM data_account_metric_node WHERE node_code=?", (node_code,))
        removed += int(cur.rowcount if cur.rowcount is not None and cur.rowcount > 0 else 0)
    return removed


def merge_canonical_expense_metric_trees_into_org_product_metrics(
    conn: sqlite3.Connection,
) -> OrgProductMetricRuntimeMergeResult:
    """Ensure canonical 05.01/05.02 expense trees live in the org/product metric master."""
    from app.services.business_admin_expense_metric_tree import all_business_admin_expense_nodes
    from app.services.business_admin_expense_metric_tree import BUSINESS_ADMIN_EXPENSE_ROOTS
    from app.services.business_expense_evaluation_metric_tree import all_business_expense_evaluation_nodes
    from app.services.business_expense_evaluation_metric_tree import BUSINESS_EXPENSE_EVALUATION_ROOTS
    from app.core.db_paths import compare_db_path, list_budget_database_files

    product_names = _product_names(conn)
    groups = (
        ("业务状况表", tuple(all_business_admin_expense_nodes())),
        ("业务支出评估", tuple(all_business_expense_evaluation_nodes())),
    )
    canonical_nodes = tuple(node for _, nodes in groups for node in nodes)
    root_codes = set(BUSINESS_ADMIN_EXPENSE_ROOTS) | set(BUSINESS_EXPENSE_EVALUATION_ROOTS)
    expected_codes = {str(node.node_code).strip().upper() for node in canonical_nodes} | root_codes
    external_ref_cache: dict[str, bool] = {}

    def is_under_canonical_root(code: str) -> bool:
        normalized = _normalize_code(code)
        return any(normalized == root or normalized.startswith(f"{root}.") for root in root_codes)

    def has_external_ref(code: str) -> bool:
        normalized = _normalize_code(code)
        if not normalized:
            return False
        if normalized in external_ref_cache:
            return external_ref_cache[normalized]
        if conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table' AND name='budget_output_display_item'
            """
        ).fetchone():
            row = conn.execute(
                """
                SELECT 1
                FROM budget_output_display_item
                WHERE data_acct_code=?
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            if row:
                external_ref_cache[normalized] = True
                return True
        data_targets = (
            ("budget_data", "data_acct_code"),
            ("business_cost_income_item", "data_acct_code"),
            ("business_cost_income_source_mapping", "data_acct_code"),
            ("budget_summary", "data_code_name"),
            ("budget_pivot_aggregate", "data_code_name"),
        )
        compare_targets = (
            ("compare_budget_summary", "data_code_name"),
            ("compare_pivot_aggregate", "data_code_name"),
        )
        paths = list(list_budget_database_files()) + [compare_db_path()]
        for path in paths:
            if not Path(path).exists():
                continue
            db = sqlite3.connect(path)
            try:
                current_tables = {
                    str(row[0])
                    for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                targets = compare_targets if Path(path).name == "compare.db" else data_targets
                for table, column in targets:
                    if table not in current_tables:
                        continue
                    if column == "data_code_name":
                        row = db.execute(
                            f"""
                            SELECT 1
                            FROM {_quote_identifier(table)}
                            WHERE {_quote_identifier(column)} LIKE ?
                            LIMIT 1
                            """,
                            (f"{normalized} %",),
                        ).fetchone()
                    else:
                        row = db.execute(
                            f"""
                            SELECT 1
                            FROM {_quote_identifier(table)}
                            WHERE {_quote_identifier(column)}=?
                            LIMIT 1
                            """,
                            (normalized,),
                        ).fetchone()
                    if row:
                        external_ref_cache[normalized] = True
                        return True
            finally:
                db.close()
        external_ref_cache[normalized] = False
        return False

    def payload_node_ref(node: dict[str, Any], entity_code: str = "") -> str:
        code = _normalize_code(node.get("code"))
        entity = _product_code(code) if "." in code else _normalize_code(entity_code)
        return (
            _derive_runtime_ref_from_metric_code(entity_code=entity, metric_code=node.get("code"))
            or _normalize_code(node.get("code"))
        )

    def payload_node_rank(node: dict[str, Any]) -> tuple[int, int]:
        node_id = _normalize_text(node.get("id"))
        code = _normalize_code(node.get("code"))
        rank = 0
        if node_id.startswith("canonical-"):
            rank += 8
        if "." in code:
            rank += 4
        if _normalize_text(node.get("name")):
            rank += 1
        return (rank, -len(str(code)))

    def prune_duplicate_payload_refs(entity_code: str, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best_by_ref: dict[str, dict[str, Any]] = {}
        for node in _iter_metric_nodes([item for item in nodes if isinstance(item, dict)]):
            ref = payload_node_ref(node, entity_code)
            if not ref or not is_under_canonical_root(ref):
                continue
            best = best_by_ref.get(ref)
            if best is None or payload_node_rank(node) > payload_node_rank(best):
                best_by_ref[ref] = node

        def walk(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            kept: list[dict[str, Any]] = []
            for node in items:
                children = node.get("children")
                if isinstance(children, list):
                    node["children"] = walk([child for child in children if isinstance(child, dict)])
                ref = payload_node_ref(node, entity_code)
                if ref and best_by_ref.get(ref) is not None and best_by_ref[ref] is not node:
                    continue
                kept.append(node)
            return kept

        return walk(nodes)

    def prune_obsolete_payload_nodes(entity_code: str, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept: list[dict[str, Any]] = []
        for node in nodes:
            children = node.get("children")
            if isinstance(children, list):
                node["children"] = prune_obsolete_payload_nodes(
                    entity_code,
                    [child for child in children if isinstance(child, dict)]
                )
            ref = payload_node_ref(node, entity_code)
            obsolete = (
                ref
                and is_under_canonical_root(ref)
                and ref not in expected_codes
                and not has_external_ref(ref)
            )
            if obsolete and not node.get("children"):
                continue
            kept.append(node)
        return kept
    payloads: dict[tuple[str, str], dict[str, Any]] = {}
    touched: set[tuple[str, str]] = set()
    merged_refs = 0

    def load_payload(entity_code: str, table_name: str) -> dict[str, Any]:
        key = (entity_code, table_name)
        if key in payloads:
            return payloads[key]
        # The old org_product_metric_table has been retired;
        # always load from the canonical runtime tree (data_account_metric_node).
        payload = load_org_product_metric_payload_from_runtime_tree(
            conn,
            entity_code=entity_code,
            table_name=table_name,
        ) or {}
        metrics = payload.get("metrics") if isinstance(payload, dict) else []
        if not isinstance(metrics, list):
            metrics = []
        original_node_count = len(_iter_metric_nodes([item for item in metrics if isinstance(item, dict)]))
        metrics = dedupe_org_product_metric_payload_nodes(
            [item for item in metrics if isinstance(item, dict)]
        )
        if len(_iter_metric_nodes(metrics)) != original_node_count:
            touched.add(key)
        payload = {
            "id": payload.get("id") if isinstance(payload, dict) and payload.get("id") else f"table-{table_name}",
            "name": table_name,
            "metrics": metrics,
        }
        payloads[key] = payload
        return payload

    for table_name, nodes in groups:
        for node in nodes:
            entity_code = _product_code(node.node_code)
            payload = load_payload(entity_code, table_name)
            roots = payload["metrics"]
            index = _metric_payload_index(roots)
            parent_ref = _normalize_code(node.parent_code) if node.parent_code else ""
            node_key = _normalize_code(node.node_code)
            node_id_key = _compact_org_product_metric_code(node.node_code) or node_key
            is_metric = str(node.node_type).upper() == "METRIC"
            payload_node = {
                "id": f"canonical-{node_id_key}",
                "levelLabel": _level_label_for_node_level(int(node.level or 0)),
                "nature": "其他",
                "code": node_key,
                "name": node.node_name,
                "value_type": getattr(node, "value_type", None) or "金额",
                "allow_manual_entry": 1 if is_metric else 0,
                "entry_granularity": "monthly",
                "note": "由规范费用指标树同步到机构及产品指标主表",
                "children": [],
            }
            if _upsert_metric_payload_node(
                roots=roots,
                index=index,
                parent_ref=parent_ref,
                node_ref=node_key,
                node=payload_node,
            ):
                touched.add((entity_code, table_name))
                if is_metric:
                    merged_refs += 1

    for entity_code, table_name in sorted(payloads):
        payload = payloads[(entity_code, table_name)]
        before_payload = json.dumps(payload.get("metrics") or [], ensure_ascii=False, sort_keys=True)
        payload["metrics"] = prune_obsolete_payload_nodes(
            entity_code,
            [item for item in payload["metrics"] if isinstance(item, dict)]
        )
        payload["metrics"] = prune_duplicate_payload_refs(
            entity_code,
            [item for item in payload["metrics"] if isinstance(item, dict)]
        )
        payload["metrics"] = dedupe_org_product_metric_payload_nodes(
            [item for item in payload["metrics"] if isinstance(item, dict)]
        )
        after_payload = json.dumps(payload.get("metrics") or [], ensure_ascii=False, sort_keys=True)
        if before_payload != after_payload:
            touched.add((entity_code, table_name))
        if (entity_code, table_name) not in touched:
            continue
        _sort_metric_payload_nodes(payload["metrics"])
        sync_org_product_metric_runtime_refs(
            conn,
            entity_code=entity_code,
            table_name=table_name,
            metrics=[item for item in payload["metrics"] if isinstance(item, dict)],
        )

    obsolete_codes = [
        str(row[0] or "").strip().upper()
        for root in sorted(root_codes)
        for row in conn.execute(
            """
            SELECT node_code
            FROM data_account_metric_node
            WHERE (node_code=? OR node_code LIKE ?)
            ORDER BY LENGTH(node_code) DESC
            """,
            (root, f"{root}.%"),
        )
        if str(row[0] or "").strip().upper() not in expected_codes
        and not has_external_ref(str(row[0] or ""))
    ]
    for code in obsolete_codes:
        child_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM data_account_metric_node WHERE parent_code=?",
                (code,),
            ).fetchone()[0]
            or 0
        )
        if child_count == 0:
            conn.execute("DELETE FROM data_account_metric_node WHERE node_code=?", (code,))

    for node in canonical_nodes:
        node_type = str(node.node_type).upper()
        conn.execute(
            """
            INSERT INTO data_account_metric_node(
              node_code, node_name, parent_code, product_code, local_metric_code, logic_code,
              functional_group_code, metric_table_name, level, node_type, horizontal_rollup, vertical_rollup,
              sort_order, is_active, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, 1, ?)
            ON CONFLICT(node_code) DO UPDATE SET
              node_name=excluded.node_name,
              parent_code=excluded.parent_code,
              product_code=excluded.product_code,
              local_metric_code=excluded.local_metric_code,
              logic_code=excluded.logic_code,
              functional_group_code=excluded.functional_group_code,
              metric_table_name=excluded.metric_table_name,
              level=excluded.level,
              node_type=excluded.node_type,
              sort_order=excluded.sort_order,
              is_active=1,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                node.node_code,
                node.node_name,
                node.parent_code,
                node.product_code,
                node.local_metric_code,
                node.local_metric_code,
                "业务支出评估" if ".91" in node.node_code else "业务状况表",
                "业务支出评估" if ".91" in node.node_code else "业务状况表",
                node.level,
                node_type,
                node.sort_order,
                "由规范费用指标树同步到机构及产品指标主表",
            ),
        )
        if node_type != "METRIC":
            continue
        value_type = getattr(node, "value_type", None) or "金额"
        conn.execute(
            """
            UPDATE data_account_metric_node
            SET node_name=?,
                runtime_account_enabled=1,
                value_type=?,
                allow_manual_entry=1,
                remark=COALESCE(remark, ?),
                updated_at=CURRENT_TIMESTAMP
            WHERE node_code=?
            """,
            (
                node.node_name,
                value_type,
                "由规范费用指标树同步到机构及产品指标主表",
                node.node_code,
            ),
        )
    return OrgProductMetricRuntimeMergeResult(
        merged_refs=merged_refs,
        touched_tables=len(touched),
    )
