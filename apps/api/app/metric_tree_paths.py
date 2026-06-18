from __future__ import annotations

import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
from typing import Any, Iterable

from app.core.database import get_pool


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


async def _fetch_all_from_db(db: Any, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    cur = await db.execute(sql, params)
    return list(await cur.fetchall())


def _normalize_codes(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []
    return sorted({str(v or "").strip().upper() for v in values if str(v or "").strip()})


def build_metric_path(
    metric_node_code: str,
    node_map: dict[str, dict[str, Any]],
) -> list[str]:
    path: list[str] = []
    seen: set[str] = set()
    cur = metric_node_code.strip().upper()
    while cur and cur not in seen:
        seen.add(cur)
        node = node_map.get(cur)
        if not node:
            path.append(cur)
            break
        path.append(f"{cur} {node['name']}".strip())
        cur = str(node.get("parent") or "").strip().upper()
    path.reverse()
    return path


def metric_display_level(code: str, fallback_level: int) -> int:
    if code == "00":
        return 0
    if "." in code or code.isdigit():
        return code.count(".") + 1
    return max(1, int(fallback_level or 1) - 1)


def metric_node_is_minus(name: str) -> bool:
    return name.startswith(("减：", "减:")) or name in {"FTP成本", "利息支出", "手续费支出"}


def load_active_metric_node_map_sync(db: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = db.execute(
        """
        SELECT node_code, node_name, parent_code, level, sort_order
        FROM data_account_metric_node
        WHERE is_active = 1
        """
    ).fetchall()
    return {
        str(row[0]).strip().upper(): {
            "name": str(row[1] or "").strip(),
            "parent": str(row[2]).strip().upper() if row[2] is not None else None,
            "level": int(row[3] or 0),
            "sort_order": int(row[4] or 0),
        }
        for row in rows
        if str(row[0] or "").strip()
    }


async def load_metric_paths_for_data_accounts(
    db: Any,
    data_acct_codes: Iterable[str],
    *,
    scope_codes: Iterable[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    data_codes = _normalize_codes(data_acct_codes)
    if not data_codes:
        return {}

    node_sql = """
    SELECT node_code, node_name, parent_code, level, sort_order
    FROM data_account_metric_node
    WHERE is_active = 1
    """
    node_rows = (
        await get_pool().fetch_all(node_sql)
        if db is None
        else await _fetch_all_from_db(db, node_sql)
    )
    node_map = {
        str(_row_value(r, "node_code", 0)).strip().upper(): {
            "name": str(_row_value(r, "node_name", 1) or "").strip(),
            "parent": (
                str(_row_value(r, "parent_code", 2)).strip().upper()
                if _row_value(r, "parent_code", 2) is not None
                else None
            ),
            "level": int(_row_value(r, "level", 3) or 0),
            "sort_order": int(_row_value(r, "sort_order", 4) or 0),
        }
        for r in node_rows
    }

    placeholder = "%s" if db is None else "?"
    data_placeholders = ",".join([placeholder] * len(data_codes))
    params: list[Any] = [*data_codes]
    scope_sql = ""
    scopes = _normalize_codes(scope_codes)
    if scopes:
        scope_placeholders = ",".join([placeholder] * len(scopes))
        scope_sql = f"""
          AND UPPER(COALESCE(b.scope_code, '')) IN ({scope_placeholders})
        """
        params.extend(scopes)

    binding_sql = f"""
    SELECT b.metric_node_code,
           b.data_acct_code,
           COALESCE(n.sort_order, 999999) AS node_sort_order,
           COALESCE(b.sort_order, 999999) AS binding_sort_order,
           COALESCE(n.level, 999999) AS node_level
    FROM data_account_metric_binding b
    LEFT JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
    WHERE UPPER(b.data_acct_code) IN ({data_placeholders})
      AND b.is_active = 1
      AND COALESCE(n.is_active, 1) = 1
      {scope_sql}
    ORDER BY node_sort_order, binding_sort_order, node_level, b.metric_node_code, b.scope_code, b.data_acct_code
    """
    binding_rows = (
        await get_pool().fetch_all(binding_sql, tuple(params))
        if db is None
        else await _fetch_all_from_db(db, binding_sql, tuple(params))
    )

    result: dict[str, list[dict[str, Any]]] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for row in binding_rows:
        metric_code = str(_row_value(row, "metric_node_code", 0) or "").strip().upper()
        data_code = str(_row_value(row, "data_acct_code", 1) or "").strip().upper()
        if not metric_code or not data_code:
            continue
        pair = (data_code, metric_code)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        metric_path = build_metric_path(metric_code, node_map)
        result.setdefault(data_code, []).append(
            {
                "metric_node_code": metric_code,
                "metric_path": metric_path,
            }
        )
    return result


async def load_metric_tree_with_data_accounts(db: Any | None = None) -> list[dict[str, Any]]:
    node_sql = """
    SELECT node_code, node_name, parent_code, level, node_type, sort_order
    FROM data_account_metric_node
    WHERE is_active = 1
    ORDER BY level, sort_order, node_code
    """
    node_rows = (
        await get_pool().fetch_all(node_sql)
        if db is None
        else await _fetch_all_from_db(db, node_sql)
    )
    children_by_parent: dict[str | None, list[str]] = {}
    sort_order_by_code: dict[str, int] = {}
    nodes: dict[str, dict[str, Any]] = {}
    for row in node_rows:
        code_raw = _row_value(row, "node_code", 0)
        name_raw = _row_value(row, "node_name", 1)
        parent_raw = _row_value(row, "parent_code", 2)
        level_raw = _row_value(row, "level", 3)
        node_type_raw = _row_value(row, "node_type", 4)
        sort_raw = _row_value(row, "sort_order", 5)
        code = str(code_raw or "").strip().upper()
        if not code or code == "00":
            continue
        parent_code = str(parent_raw or "").strip().upper() or None
        if parent_code == "00":
            parent_code = None
        name = str(name_raw or "").strip()
        sort_order = int(sort_raw or 0)
        sort_order_by_code[code] = sort_order
        children_by_parent.setdefault(parent_code, []).append(code)
        nodes[code] = {
            "type": "metric",
            "code": code,
            "name": name,
            "parent_code": parent_code,
            "node_type": str(node_type_raw or "").strip().upper(),
            "level": metric_display_level(code, int(level_raw or 1)),
            "is_summary": 1,
            "is_minus": 1 if metric_node_is_minus(name) else 0,
            "children": [],
        }

    roots: list[dict[str, Any]] = []
    for code, node in nodes.items():
        parent_code = node.get("parent_code")
        if parent_code and parent_code in nodes and parent_code != code:
            nodes[parent_code]["children"].append(node)
        else:
            roots.append(node)

    binding_sql = """
    SELECT b.metric_node_code,
           b.data_acct_code,
           COALESCE(d.data_acct_name, '') AS data_acct_name,
           COALESCE(d.value_type, '') AS value_type,
           COALESCE(d.budget_formula, '') AS budget_formula,
           COALESCE(d.actual_formula, '') AS actual_formula,
           COALESCE(b.sort_order, 0) AS sort_order,
           COALESCE(b.scope_code, '') AS scope_code
    FROM data_account_metric_binding b
    JOIN data_account d ON d.data_acct_code = b.data_acct_code
    LEFT JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
    WHERE b.is_active = 1
      AND COALESCE(n.is_active, 1) = 1
    ORDER BY COALESCE(n.sort_order, 999999), b.metric_node_code, b.sort_order, b.scope_code, b.data_acct_code
    """
    binding_rows = (
        await get_pool().fetch_all(binding_sql)
        if db is None
        else await _fetch_all_from_db(db, binding_sql)
    )
    seen_bindings: set[tuple[str, str, str]] = set()
    for row in binding_rows:
        metric_code = str(_row_value(row, "metric_node_code", 0) or "").strip().upper()
        data_code = str(_row_value(row, "data_acct_code", 1) or "").strip().upper()
        scope_code = str(_row_value(row, "scope_code", 7) or "").strip().upper()
        parent = nodes.get(metric_code)
        if not parent or not data_code:
            continue
        key = (metric_code, data_code, scope_code)
        if key in seen_bindings:
            continue
        seen_bindings.add(key)
        data_name = str(_row_value(row, "data_acct_name", 2) or "").strip()
        parent["children"].append(
            {
                "type": "data",
                "id": f"{metric_code}:{data_code}:{scope_code or len(parent['children'])}",
                "code": data_code,
                "name": f"{data_code} {data_name}".strip() if data_name else data_code,
                "scope_code": scope_code,
                "value_type": str(_row_value(row, "value_type", 3) or ""),
                "budget_formula": str(_row_value(row, "budget_formula", 4) or ""),
                "actual_formula": str(_row_value(row, "actual_formula", 5) or ""),
                "sort_order": int(_row_value(row, "sort_order", 6) or 0),
            }
        )

    def sort_rec(items: list[dict[str, Any]]) -> None:
        items.sort(
            key=lambda node: (
                1 if node.get("type") == "data" else 0,
                int(node.get("sort_order", sort_order_by_code.get(str(node.get("code", "")), 0)) or 0),
                str(node.get("code", "")),
                str(node.get("scope_code", "")),
            )
        )
        for item in items:
            sort_rec(item.get("children") or [])

    sort_rec(roots)
    return roots
