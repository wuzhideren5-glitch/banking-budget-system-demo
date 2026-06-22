"""Read org/product metric table payloads from the runtime metric tree."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
from typing import Any

from app.services.org_product_runtime_catalog import org_product_runtime_products_cte_for_conn
from app.services.runtime_metric_refs import compact_org_product_metric_code

_ORG_PRODUCT_FORMULA_CONFIG_KEY = "org_product_metric_formulas"


_PRODUCT_ROOT_RE = re.compile(r"^[A-Z][A-Z0-9]*$")

# 合法的指标表名白名单（仅 catalog 中注册的表名可作为分组键）。
_VALID_TABLE_NAMES_CACHE: set[str] | None = None
_RUNTIME_TREE_COLUMNS = (
    "node_code",
    "node_name",
    "parent_code",
    "local_metric_code",
    "logic_code",
    "level",
    "node_type",
    "horizontal_rollup",
    "vertical_rollup",
    "allow_manual_entry",
    "value_type",
    "nature",
    "budget_formula",
    "actual_formula",
    "budget_rule_config_json",
    "product_code",
    "metric_table_name",
    "sort_order",
    "annual_agg_rule",
)


def _valid_table_names(conn: sqlite3.Connection) -> set[str]:
    global _VALID_TABLE_NAMES_CACHE
    if _VALID_TABLE_NAMES_CACHE is not None:
        return _VALID_TABLE_NAMES_CACHE
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='org_product_metric_table_catalog'"
    ).fetchone()
    if not exists:
        # 测试/空库场景：回退到直接从 metric_table_name 取值
        return set()
    _VALID_TABLE_NAMES_CACHE = {
        _clean(row[0])
        for row in conn.execute("SELECT DISTINCT table_name FROM org_product_metric_table_catalog")
    }
    return _VALID_TABLE_NAMES_CACHE


def _resolve_table_name(conn: sqlite3.Connection, raw_table_name: str) -> str | None:
    """仅返回 catalog 中注册的有效表名，防止 "01"/"05" 等数字码成为伪表名。"""
    valid = _valid_table_names(conn)
    if not valid:
        # 无 catalog 时（测试/空库），允许所有非纯数字的表名通过
        if raw_table_name.isdigit():
            return None
        return raw_table_name
    return raw_table_name if raw_table_name in valid else None


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _clean(value).upper().replace(" ", "")


def _is_product_root(code: str) -> bool:
    return _PRODUCT_ROOT_RE.fullmatch(code) is not None


def _level_label(level: int) -> str:
    labels = ("一级", "二级", "三级", "四级", "五级", "六级")
    index = max(0, min(len(labels) - 1, int(level or 2) - 2))
    return labels[index]


def _product_names(conn: sqlite3.Connection) -> dict[str, str]:
    try:
        return {
            _upper(code): _clean(name)
            for code, name in conn.execute(
                f"""
                {org_product_runtime_products_cte_for_conn(conn)}
                SELECT product_code, product_name
                FROM org_product_runtime_products
                WHERE product_code <> '' AND product_name <> ''
                """
            )
            if _upper(code) and _clean(name)
        }
    except Exception:
        return {}


def _parse_org_product_formula_config(raw: Any) -> dict[str, str]:
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    payload = parsed.get(_ORG_PRODUCT_FORMULA_CONFIG_KEY)
    if not isinstance(payload, dict):
        return {}
    out: dict[str, str] = {}
    for key in ("formula_forecast", "formula_forecast_annual", "formula_note"):
        value = _clean(payload.get(key))
        if value:
            out[key] = value
    return out


def _runtime_tree_row_to_dict(row: sqlite3.Row | tuple[Any, ...]) -> dict[str, Any]:
    return {column: row[index] for index, column in enumerate(_RUNTIME_TREE_COLUMNS)}


def ensure_org_product_metric_table_payload(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS org_product_metric_table_payload (
            entity_code TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            table_id TEXT NOT NULL,
            table_name TEXT NOT NULL,
            payload_json LONGTEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (entity_code, table_name)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_org_product_metric_table_payload_entity
        ON org_product_metric_table_payload(entity_code)
        """
    )


def persist_org_product_metric_table_payload(
    conn: sqlite3.Connection,
    *,
    entity_code: str,
    entity_name: str,
    table_name: str,
    table_id: str,
    metrics: list[dict[str, Any]],
) -> None:
    """Persist the exact metric tree JSON saved from the UI (round-trip source of truth)."""
    entity = _upper(entity_code)
    table = _clean(table_name) or "业务状况表"
    if not entity:
        return
    ensure_org_product_metric_table_payload(conn)
    resolved_table_id = _clean(table_id) or f"table-{table}"
    payload = {
        "id": resolved_table_id,
        "name": table,
        "metrics": metrics,
    }
    updated_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO org_product_metric_table_payload
          (entity_code, entity_name, table_id, table_name, payload_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_code, table_name) DO UPDATE SET
          entity_name=excluded.entity_name,
          table_id=excluded.table_id,
          payload_json=excluded.payload_json,
          updated_at=excluded.updated_at
        """,
        (
            entity,
            _clean(entity_name) or entity,
            resolved_table_id,
            table,
            json.dumps(payload, ensure_ascii=False),
            updated_at,
        ),
    )


def _load_org_product_metric_table_rows_from_payload_table(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    exists = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name='org_product_metric_table_payload'
        """
    ).fetchone()
    if not exists:
        return []
    rows: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT entity_code, entity_name, table_id, table_name, payload_json
        FROM org_product_metric_table_payload
        ORDER BY entity_code, table_name
        """
    ).fetchall():
        entity_code = _upper(row[0])
        table_name = _clean(row[3])
        if not entity_code or not table_name:
            continue
        rows.append(
            {
                "entity_code": entity_code,
                "entity_name": _clean(row[1]) or entity_code,
                "table_id": _clean(row[2]) or f"table-{table_name}",
                "table_name": table_name,
                "payload_json": str(row[4] or "{}"),
            }
        )
    return rows


def _load_org_product_metric_table_rows_from_physical_table(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    exists = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name='org_product_metric_table'
        """
    ).fetchone()
    if not exists:
        return []
    columns = {
        _clean(row[1])
        for row in conn.execute("PRAGMA table_info(org_product_metric_table)").fetchall()
    }
    entity_name_expr = "entity_name" if "entity_name" in columns else "entity_code"
    table_id_expr = "table_id" if "table_id" in columns else "('table-' || table_name)"
    rows: list[dict[str, Any]] = []
    for row in conn.execute(
        f"""
        SELECT entity_code, {entity_name_expr}, {table_id_expr}, table_name, payload_json
        FROM org_product_metric_table
        ORDER BY entity_code, table_name
        """
    ).fetchall():
        entity_code = _upper(row[0])
        table_name = _clean(row[3])
        if not entity_code or not table_name:
            continue
        rows.append(
            {
                "entity_code": entity_code,
                "entity_name": _clean(row[1]) or entity_code,
                "table_id": _clean(row[2]) or f"table-{table_name}",
                "table_name": table_name,
                "payload_json": str(row[4] or "{}"),
            }
        )
    return rows


def _node_payload(row: dict[str, Any]) -> dict[str, Any]:
    code = _upper(row["node_code"])
    level = int(row["level"] or 0)
    compact = compact_org_product_metric_code(code)
    logic_code = _upper(row["logic_code"])
    if not logic_code and "." in code:
        logic_code = code.split(".", 1)[1]
    node = {
        "id": f"canonical-{compact or code}",
        "levelLabel": _level_label(level),
        "nature": _clean(row.get("nature")) or "其他",
        "code": code,
        "name": _clean(row["node_name"]) or code,
        "value_type": _clean(row["value_type"]) or "金额",
        "allow_manual_entry": int(row["allow_manual_entry"] or 0),
        "entry_granularity": "monthly",
        "logic_code": logic_code,
        "horizontal_rollup": int(row["horizontal_rollup"] or 0),
        "vertical_rollup": int(row["vertical_rollup"] or 0),
        "children": [],
    }
    budget_formula = _clean(row["budget_formula"])
    actual_formula = _clean(row["actual_formula"])
    if budget_formula:
        node["formula_budget_annual"] = budget_formula
    if actual_formula:
        node["formula_actual"] = actual_formula
        if not _clean(row.get("budget_formula")):
            node["formula"] = actual_formula
    extra_formulas = _parse_org_product_formula_config(row.get("budget_rule_config_json"))
    if extra_formulas.get("formula_forecast"):
        node["formula_forecast"] = extra_formulas["formula_forecast"]
    elif actual_formula and not budget_formula:
        node["formula_forecast"] = actual_formula
    if extra_formulas.get("formula_forecast_annual"):
        node["formula_forecast_annual"] = extra_formulas["formula_forecast_annual"]
    if extra_formulas.get("formula_note"):
        node["formula_note"] = extra_formulas["formula_note"]
    agg_rule = _clean(row.get("annual_agg_rule"))
    if agg_rule:
        node["annual_agg_rule"] = agg_rule
    return node


def load_org_product_metric_table_rows_from_runtime_tree(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Return org/product metric table rows for db-snapshot and bootstrap.

    Prefer the exact JSON saved at save-refresh time; fall back to rebuilding
    from data_account_metric_node when no payload snapshot exists yet.
    """
    payload_rows = _load_org_product_metric_table_rows_from_payload_table(conn)
    if payload_rows:
        return payload_rows

    exists = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view') AND name='data_account_metric_node'
        """
    ).fetchone()
    if not exists:
        return _load_org_product_metric_table_rows_from_physical_table(conn)

    try:
        rows = [
            _runtime_tree_row_to_dict(row)
            for row in conn.execute(
                """
                SELECT node_code, node_name, parent_code, local_metric_code, logic_code,
                       level, node_type, horizontal_rollup, vertical_rollup,
                       allow_manual_entry, value_type, nature, budget_formula, actual_formula,
                       budget_rule_config_json, product_code, metric_table_name, sort_order, annual_agg_rule
                FROM data_account_metric_node
                WHERE is_active = 1
                  AND COALESCE(product_code, '') <> ''
                  AND COALESCE(metric_table_name, '') <> ''
                  AND node_code <> product_code
                ORDER BY product_code, metric_table_name, level, sort_order, node_code
                """
            ).fetchall()
        ]
    except Exception:
        return _load_org_product_metric_table_rows_from_physical_table(conn)

    product_names = _product_names(conn)
    root_names = {
        _upper(code): _clean(name)
        for code, name in conn.execute(
            """
            SELECT node_code, node_name
            FROM data_account_metric_node
            WHERE is_active=1 AND parent_code IS NULL
            """
        )
        if _upper(code) and _clean(name)
    }

    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        product_code = _upper(row["product_code"])
        raw_table_name = _clean(row["metric_table_name"])
        if not product_code or not raw_table_name or _is_product_root(raw_table_name):
            continue
        table_name = _resolve_table_name(conn, raw_table_name)
        if not table_name:
            continue
        key = (product_code, table_name)
        group = groups.setdefault(
            key,
            {
                "entity_code": product_code,
                "entity_name": product_names.get(product_code) or root_names.get(product_code) or product_code,
                "table_id": f"table-{table_name}",
                "table_name": table_name,
                "nodes": {},
            },
        )
        node = _node_payload(row)
        group["nodes"][node["code"]] = {
            "payload": node,
            "parent_code": _upper(row["parent_code"]),
            "level": int(row["level"] or 0),
            "sort_order": int(row["sort_order"] or 0),
        }

    out: list[dict[str, Any]] = []
    for (entity_code, table_name), group in sorted(groups.items()):
        node_items: dict[str, dict[str, Any]] = group["nodes"]
        roots: list[dict[str, Any]] = []
        for code, item in node_items.items():
            parent_code = item["parent_code"]
            parent = node_items.get(parent_code)
            if parent is not None:
                parent["payload"]["children"].append(item["payload"])
            else:
                roots.append(item["payload"])

        def sort_nodes(items: list[dict[str, Any]]) -> None:
            items.sort(key=lambda node: (_upper(node.get("code")), _clean(node.get("name"))))
            for child in items:
                children = child.get("children")
                if isinstance(children, list):
                    sort_nodes(children)

        sort_nodes(roots)
        payload = {
            "id": group["table_id"],
            "name": table_name,
            "metrics": roots,
        }
        out.append(
            {
                "entity_code": entity_code,
                "entity_name": group["entity_name"],
                "table_id": group["table_id"],
                "table_name": table_name,
                "payload_json": json.dumps(payload, ensure_ascii=False),
            }
        )
    if out:
        return out
    return _load_org_product_metric_table_rows_from_physical_table(conn)


def load_org_product_metric_payload_from_runtime_tree(
    conn: sqlite3.Connection,
    *,
    entity_code: str,
    table_name: str,
) -> dict[str, Any] | None:
    entity = _upper(entity_code)
    table = _clean(table_name)
    for row in load_org_product_metric_table_rows_from_runtime_tree(conn):
        if row["entity_code"] == entity and row["table_name"] == table:
            try:
                return json.loads(str(row["payload_json"] or "{}"))
            except Exception:
                return None
    return None
