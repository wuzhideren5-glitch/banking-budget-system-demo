#!/usr/bin/env python3
"""导出产品经理意图提示词所需的“科目层级图”静态快照。

输出两份文件：
1) product_manager_intent_catalog.md   -> 给大模型直接阅读（树状+映射）
2) catalog_graph.json                  -> 给程序/审阅使用（结构化图）
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.db_paths import common_db_path  # noqa: E402

PROMPT_DIR = REPO_ROOT / "knowledge_base" / "06_agent_prompts"
MD_OUT = PROMPT_DIR / "product_manager_intent_catalog.md"
JSON_OUT = PROMPT_DIR / "catalog_graph.json"


@dataclass
class TreeNode:
    code: str
    name: str
    parent_code: str | None
    level: int
    is_leaf: bool
    children: list[str]


def _fetch_rows(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    return list(conn.execute(sql).fetchall())


def _build_tree(nodes: dict[str, TreeNode]) -> list[str]:
    roots: list[str] = []
    for code, node in nodes.items():
        p = (node.parent_code or "").strip()
        if not p or p not in nodes:
            roots.append(code)
        else:
            nodes[p].children.append(code)
    for node in nodes.values():
        node.children.sort()
    roots.sort()
    return roots


def _detect_cycle(nodes: dict[str, TreeNode]) -> list[str]:
    state: dict[str, int] = {}
    path: list[str] = []
    cycle: list[str] = []

    def dfs(code: str) -> bool:
        nonlocal cycle
        s = state.get(code, 0)
        if s == 1:
            if code in path:
                i = path.index(code)
                cycle = path[i:] + [code]
            else:
                cycle = [code, code]
            return True
        if s == 2:
            return False
        state[code] = 1
        path.append(code)
        for ch in nodes[code].children:
            if dfs(ch):
                return True
        path.pop()
        state[code] = 2
        return False

    for c in sorted(nodes.keys()):
        if state.get(c, 0) == 0 and dfs(c):
            return cycle
    return []


def _to_data_detail(
    data_code: str,
    data_info: dict[str, dict[str, Any]],
    products: dict[str, str],
) -> dict[str, Any]:
    row = data_info.get(data_code, {})
    applies_all = bool(row.get("applies_to_all_products", 0))
    p_code = str(row.get("product_code") or "").strip()
    if applies_all:
        scope = {"type": "ALL", "product_code": None, "product_name": None}
    elif p_code:
        scope = {"type": "SINGLE", "product_code": p_code, "product_name": products.get(p_code)}
    else:
        scope = {"type": "UNKNOWN", "product_code": None, "product_name": None}
    return {
        "code": data_code,
        "name": str(row.get("data_acct_name") or data_code),
        "value_type": str(row.get("value_type") or ""),
        "product_scope": scope,
    }


def _render_report_tree_md(
    roots: list[str],
    nodes: dict[str, TreeNode],
    report_to_data: dict[str, list[str]],
    data_info: dict[str, dict[str, Any]],
    products: dict[str, str],
    out: list[str],
    depth: int = 0,
    code: str | None = None,
) -> None:
    if code is None:
        for r in roots:
            _render_report_tree_md(roots, nodes, report_to_data, data_info, products, out, 0, r)
        return
    node = nodes[code]
    indent = "  " * depth
    leaf_flag = " [leaf]" if node.is_leaf else ""
    out.append(f"{indent}- {node.code} {node.name}{leaf_flag}")
    mapped = report_to_data.get(node.code, [])
    if mapped:
        out.append(f"{indent}  - 映射数据科目:")
        for dc in mapped:
            d = _to_data_detail(dc, data_info, products)
            scope = d["product_scope"]
            if scope["type"] == "ALL":
                scope_txt = "ALL_PRODUCTS"
            elif scope["type"] == "SINGLE":
                scope_txt = f"{scope['product_code']} {scope['product_name'] or ''}".strip()
            else:
                scope_txt = "UNKNOWN"
            out.append(
                f"{indent}    - {d['code']} {d['name']} "
                f"(value_type={d['value_type']}, product_scope={scope_txt})"
            )
    for ch in node.children:
        _render_report_tree_md(roots, nodes, report_to_data, data_info, products, out, depth + 1, ch)


def _dept_effective_products(
    code: str,
    nodes: dict[str, TreeNode],
    dept_to_product: dict[str, list[str]],
    memo: dict[str, set[str]],
) -> set[str]:
    if code in memo:
        return memo[code]
    s = set(dept_to_product.get(code, []))
    for ch in nodes[code].children:
        s.update(_dept_effective_products(ch, nodes, dept_to_product, memo))
    memo[code] = s
    return s


def _render_dept_tree_md(
    roots: list[str],
    nodes: dict[str, TreeNode],
    dept_to_product: dict[str, list[str]],
    products: dict[str, str],
    out: list[str],
    depth: int = 0,
    code: str | None = None,
    eff_memo: dict[str, set[str]] | None = None,
) -> None:
    if eff_memo is None:
        eff_memo = {}
    if code is None:
        for r in roots:
            _render_dept_tree_md(roots, nodes, dept_to_product, products, out, 0, r, eff_memo)
        return
    node = nodes[code]
    indent = "  " * depth
    leaf_flag = " [leaf]" if node.is_leaf else ""
    out.append(f"{indent}- {node.code} {node.name}{leaf_flag}")
    direct = dept_to_product.get(node.code, [])
    if direct:
        out.append(f"{indent}  - 直接授权产品:")
        for pc in direct:
            out.append(f"{indent}    - {pc} {products.get(pc, '')}".rstrip())
    effective = sorted(_dept_effective_products(node.code, nodes, dept_to_product, eff_memo))
    if effective:
        out.append(f"{indent}  - 有效产品集合(含下级继承):")
        for pc in effective:
            out.append(f"{indent}    - {pc} {products.get(pc, '')}".rstrip())
    for ch in node.children:
        _render_dept_tree_md(roots, nodes, dept_to_product, products, out, depth + 1, ch, eff_memo)


def _render_markdown(
    *,
    source_db: Path,
    counts: dict[str, int],
    report_roots: list[str],
    report_nodes: dict[str, TreeNode],
    report_to_data: dict[str, list[str]],
    data_info: dict[str, dict[str, Any]],
    dept_roots: list[str],
    dept_nodes: dict[str, TreeNode],
    dept_to_product: dict[str, list[str]],
    products: dict[str, str],
    warnings: list[str],
) -> str:
    out: list[str] = []
    out.append("<!-- 本快照由 backend/scripts/export_product_manager_catalog_prompt.py 生成 -->")
    out.append("")
    out.append(f"- generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    out.append(f"- source_db: `{source_db}`")
    out.append(
        "- counts: "
        f"report_accounts={counts['report_accounts']}, "
        f"data_accounts={counts['data_accounts']}, "
        f"report_data_mappings={counts['report_data_mappings']}, "
        f"dept_accounts={counts['dept_accounts']}, "
        f"products={counts['products']}, "
        f"dept_product_mappings={counts['dept_product_mappings']}"
    )
    if warnings:
        out.append("- warnings:")
        for w in warnings:
            out.append(f"  - {w}")
    out.append("")
    out.append("## 一、报告科目树（含报告->数据映射）")
    _render_report_tree_md(report_roots, report_nodes, report_to_data, data_info, products, out)
    out.append("")
    out.append("## 二、部门科目树（含部门->产品授权）")
    _render_dept_tree_md(dept_roots, dept_nodes, dept_to_product, products, out)
    return "\n".join(out).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export hierarchical catalog graph for prompt usage.")
    parser.add_argument("--pretty-json", action="store_true", help="Pretty print JSON output")
    args = parser.parse_args()

    db_path = common_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"common.db 不存在：{db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    warnings: list[str] = []

    report_rows = _fetch_rows(
        conn,
        """
        SELECT report_acct_code, report_acct_name, parent_code, level, is_leaf
        FROM report_account
        ORDER BY report_acct_code
        """,
    )
    data_rows = _fetch_rows(
        conn,
        """
        SELECT data_acct_code, data_acct_name, value_type, product_code, applies_to_all_products
        FROM data_account
        ORDER BY data_acct_code
        """,
    )
    map_rows = _fetch_rows(
        conn,
        """
        SELECT report_acct_code, data_acct_code
        FROM report_data_mapping
        ORDER BY report_acct_code, data_acct_code
        """,
    )
    dept_rows = _fetch_rows(
        conn,
        """
        SELECT dept_code, dept_name, parent_code, level, is_leaf
        FROM dept_account
        ORDER BY dept_code
        """,
    )
    product_rows = _fetch_rows(
        conn,
        """
        SELECT product_code, product_name
        FROM product_type
        ORDER BY product_code
        """,
    )
    dept_map_rows = _fetch_rows(
        conn,
        """
        SELECT dept_code, product_code
        FROM dept_product_mapping
        ORDER BY dept_code, product_code
        """,
    )
    conn.close()

    report_nodes: dict[str, TreeNode] = {}
    for r in report_rows:
        code = str(r["report_acct_code"])
        report_nodes[code] = TreeNode(
            code=code,
            name=str(r["report_acct_name"] or code),
            parent_code=str(r["parent_code"] or "").strip() or None,
            level=int(r["level"] or 0),
            is_leaf=bool(int(r["is_leaf"] or 0)),
            children=[],
        )
    report_roots = _build_tree(report_nodes)
    report_cycle = _detect_cycle(report_nodes)
    if report_cycle:
        warnings.append(f"report_account 检测到环: {' -> '.join(report_cycle)}")

    data_info: dict[str, dict[str, Any]] = {}
    for r in data_rows:
        code = str(r["data_acct_code"])
        data_info[code] = {
            "data_acct_name": str(r["data_acct_name"] or code),
            "value_type": str(r["value_type"] or ""),
            "product_code": str(r["product_code"] or ""),
            "applies_to_all_products": int(r["applies_to_all_products"] or 0),
        }

    products = {str(r["product_code"]): str(r["product_name"] or "") for r in product_rows}

    report_to_data: dict[str, list[str]] = defaultdict(list)
    for r in map_rows:
        rc = str(r["report_acct_code"])
        dc = str(r["data_acct_code"])
        report_to_data[rc].append(dc)
        if rc not in report_nodes:
            warnings.append(f"report_data_mapping 引用了不存在的 report_acct_code: {rc}")
        if dc not in data_info:
            warnings.append(f"report_data_mapping 引用了不存在的 data_acct_code: {dc}")
    for k in report_to_data:
        report_to_data[k] = sorted(set(report_to_data[k]))

    dept_nodes: dict[str, TreeNode] = {}
    for r in dept_rows:
        code = str(r["dept_code"])
        dept_nodes[code] = TreeNode(
            code=code,
            name=str(r["dept_name"] or code),
            parent_code=str(r["parent_code"] or "").strip() or None,
            level=int(r["level"] or 0),
            is_leaf=bool(int(r["is_leaf"] or 0)),
            children=[],
        )
    dept_roots = _build_tree(dept_nodes)
    dept_cycle = _detect_cycle(dept_nodes)
    if dept_cycle:
        warnings.append(f"dept_account 检测到环: {' -> '.join(dept_cycle)}")

    dept_to_product: dict[str, list[str]] = defaultdict(list)
    for r in dept_map_rows:
        dc = str(r["dept_code"])
        pc = str(r["product_code"])
        dept_to_product[dc].append(pc)
        if dc not in dept_nodes:
            warnings.append(f"dept_product_mapping 引用了不存在的 dept_code: {dc}")
        if pc not in products:
            warnings.append(f"dept_product_mapping 引用了不存在的 product_code: {pc}")
    for k in dept_to_product:
        dept_to_product[k] = sorted(set(dept_to_product[k]))

    counts = {
        "report_accounts": len(report_rows),
        "data_accounts": len(data_rows),
        "report_data_mappings": len(map_rows),
        "dept_accounts": len(dept_rows),
        "products": len(product_rows),
        "dept_product_mappings": len(dept_map_rows),
    }

    graph: dict[str, Any] = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_db_path": str(db_path),
        "counts": counts,
        "warnings": warnings,
        "report_roots": report_roots,
        "report_nodes": {
            c: {
                "code": n.code,
                "name": n.name,
                "parent_code": n.parent_code,
                "level": n.level,
                "is_leaf": n.is_leaf,
                "children": n.children,
                "mapped_data_accounts": report_to_data.get(c, []),
            }
            for c, n in report_nodes.items()
        },
        "data_accounts": {
            c: {
                "code": c,
                "name": d["data_acct_name"],
                "value_type": d["value_type"],
                "product_code": d["product_code"] or None,
                "applies_to_all_products": bool(d["applies_to_all_products"]),
            }
            for c, d in data_info.items()
        },
        "dept_roots": dept_roots,
        "dept_nodes": {
            c: {
                "code": n.code,
                "name": n.name,
                "parent_code": n.parent_code,
                "level": n.level,
                "is_leaf": n.is_leaf,
                "children": n.children,
                "direct_products": dept_to_product.get(c, []),
            }
            for c, n in dept_nodes.items()
        },
        "products": products,
    }

    md_text = _render_markdown(
        source_db=db_path,
        counts=counts,
        report_roots=report_roots,
        report_nodes=report_nodes,
        report_to_data=report_to_data,
        data_info=data_info,
        dept_roots=dept_roots,
        dept_nodes=dept_nodes,
        dept_to_product=dept_to_product,
        products=products,
        warnings=warnings,
    )
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text(md_text, encoding="utf-8")
    if args.pretty_json:
        JSON_OUT.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        JSON_OUT.write_text(json.dumps(graph, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote {MD_OUT}")
    print(f"Wrote {JSON_OUT}")
    print(f"Counts: {counts}")
    if warnings:
        print("Warnings:")
        for w in warnings:
            print(f"- {w}")


if __name__ == "__main__":
    main()
