"""Materialize metric-tree parent values into budget_data."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

import aiosqlite

from app.budget_data_writer import (
    BudgetDataWriteItem,
    ROLLUP_RESULT_POLICY,
    delete_rollup_budget_data_rows,
    write_budget_data_items,
)
from app.formula_refs import extract_formula_codes
from app.services.formula_engine import calculate_formula_value, normalize_formula
from app.services.runtime_metric_refs import derive_runtime_ref_from_org_product_metric_code


@dataclass
class MetricTreeRollupSyncResult:
    created_accounts: int = 0
    updated_accounts: int = 0


@dataclass
class MetricTreeRollupRebuildResult:
    rollup_account_count: int = 0
    rollup_task_count: int = 0
    rollup_cell_count: int = 0
    written_cells: int = 0
    audit_items: list["MetricTreeRollupAuditItem"] = field(default_factory=list)
    audit_truncated: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MetricTreeRollupAuditItem:
    node_code: str
    target_data_acct_code: str
    scope_code: str
    method: str
    budget_actual: int
    period_count: int
    cell_count: int
    source_count: int
    source_codes: list[str] = field(default_factory=list)
    formula: str | None = None


@dataclass(frozen=True)
class MetricTreeRollupTask:
    node_code: str
    target_data_acct_code: str
    scope_code: str
    method: str
    budget_actual: int
    source_codes: tuple[str, ...] = ()
    source_refs: tuple[tuple[str, str], ...] = ()
    formula: str | None = None


@dataclass
class MetricTreeRollupPlan:
    product_codes: tuple[str, ...] = ()
    budget_actuals: tuple[int, ...] = ()
    period_ids: tuple[int, ...] = ()
    target_codes: tuple[str, ...] = ()
    source_codes: tuple[str, ...] = ()
    tasks: list[MetricTreeRollupTask] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def rollup_account_count(self) -> int:
        return len(self.target_codes)

    @property
    def rollup_task_count(self) -> int:
        return len(self.tasks)

    @property
    def rollup_cell_count(self) -> int:
        return len(self.tasks) * len(self.period_ids)

    def to_audit_items(self, max_items: int | None = 200) -> tuple[list[MetricTreeRollupAuditItem], bool]:
        tasks = self.tasks if max_items is None else self.tasks[:max_items]
        period_count = len(self.period_ids)
        items = [
            MetricTreeRollupAuditItem(
                node_code=task.node_code,
                target_data_acct_code=task.target_data_acct_code,
                scope_code=task.scope_code,
                method=task.method,
                budget_actual=task.budget_actual,
                period_count=period_count,
                cell_count=period_count,
                source_count=len(task.source_codes),
                source_codes=list(task.source_codes),
                formula=task.formula,
            )
            for task in tasks
        ]
        return items, max_items is not None and len(self.tasks) > max_items

    def to_result(self, *, max_audit_items: int | None = 200) -> MetricTreeRollupRebuildResult:
        audit_items, audit_truncated = self.to_audit_items(max_audit_items)
        return MetricTreeRollupRebuildResult(
            rollup_account_count=self.rollup_account_count,
            rollup_task_count=self.rollup_task_count,
            rollup_cell_count=self.rollup_cell_count,
            audit_items=audit_items,
            audit_truncated=audit_truncated,
            warnings=list(self.warnings),
        )


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _clean(value).upper()


def _node_depth(code: str) -> int:
    return code.count(".") + 1 if code else 0


def _normalize_rollup_flag(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) != 0
    text = _clean(value).lower()
    if not text:
        return False
    if text in {"0", "false", "否", "不", "no", "n", "不汇总", "无需汇总"}:
        return False
    return True


async def _load_metric_nodes(db: aiosqlite.Connection) -> dict[str, dict[str, Any]]:
    cur = await db.execute(
        """
        SELECT node_code, node_name, parent_code, node_type, level,
               COALESCE(product_code, '') AS product_code,
               COALESCE(logic_code, local_metric_code, '') AS logic_code,
               COALESCE(horizontal_rollup, 0) AS horizontal_rollup,
               COALESCE(vertical_rollup, 0) AS vertical_rollup
        FROM data_account_metric_node
        WHERE is_active = 1
        """
    )
    return {
        _upper(r[0]): {
            "code": _upper(r[0]),
            "name": _clean(r[1]),
            "parent": _upper(r[2]) or None,
            "node_type": _upper(r[3]),
            "level": int(r[4] or 0),
            "product_code": _upper(r[5]),
            "logic_code": _upper(r[6]),
            "horizontal_rollup": 1 if int(r[7] or 0) else 0,
            "vertical_rollup": 1 if int(r[8] or 0) else 0,
        }
        for r in await cur.fetchall()
        if _upper(r[0])
    }


# Retired: was used by the old _load_payload_rollup_flags that read from
# org_product_metric_table JSON payloads. Kept for reference only.
def _iter_payload_nodes(items: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    stack = [item for item in items if isinstance(item, dict)]
    while stack:
        node = stack.pop(0)
        result.append(node)
        children = node.get("children") if isinstance(node.get("children"), list) else []
        stack[0:0] = [child for child in children if isinstance(child, dict)]
    return result


async def _load_payload_rollup_flags(db: aiosqlite.Connection) -> dict[str, dict[str, bool]]:
    """Load horizontal/vertical rollup flags from data_account_metric_node.

    Previously read from the retired org_product_metric_table JSON payloads;
    now reads directly from the canonical metric node table.
    """
    flags: dict[str, dict[str, bool]] = {}
    node_table_exists = await (
        await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='data_account_metric_node'"
        )
    ).fetchone()
    if node_table_exists is None:
        return flags
    cur = await db.execute(
        """
        SELECT node_code, product_code, horizontal_rollup, vertical_rollup
        FROM data_account_metric_node
        WHERE is_active = 1
        """
    )
    for node_code, product_code_raw, horizontal_raw, vertical_raw in await cur.fetchall():
        code = derive_runtime_ref_from_org_product_metric_code(
            entity_code=str(product_code_raw or "").strip(),
            metric_code=node_code,
        )
        if not code:
            continue
        current = flags.setdefault(code, {"horizontal": False, "vertical": False})
        current["horizontal"] = current["horizontal"] or _normalize_rollup_flag(horizontal_raw)
        current["vertical"] = current["vertical"] or _normalize_rollup_flag(vertical_raw)
    return flags


def _children_by_parent(nodes: dict[str, dict[str, Any]]) -> dict[str | None, list[str]]:
    children: dict[str | None, list[str]] = {}
    for code, node in nodes.items():
        children.setdefault(node.get("parent"), []).append(code)
    for items in children.values():
        items.sort(key=lambda code: (_node_depth(code), code))
    return children


def _descendants(code: str, children_by_parent: dict[str | None, list[str]]) -> list[str]:
    result: list[str] = []
    for child in children_by_parent.get(code, []):
        result.append(child)
        result.extend(_descendants(child, children_by_parent))
    return result


async def _load_product_children(db: aiosqlite.Connection) -> dict[str, set[str]]:
    """Load product hierarchy: parent_code → {child product_codes}."""
    cur = await db.execute(
        "SELECT payload_json FROM org_product_tree_snapshot WHERE id = 1"
    )
    row = await cur.fetchone()
    if not row:
        return {}
    try:
        tree = json.loads(str(row[0] or "{}"))
    except Exception:
        return {}

    child_map: dict[str, set[str]] = {}

    def walk(node: dict, parent: str | None = None):
        code = _upper(node.get("code"))
        if parent and code:
            child_map.setdefault(parent, set()).add(code)
        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                walk(child, code if code else parent)

    for root_child in tree.get("children", []) or []:
        if isinstance(root_child, dict):
            walk(root_child)

    return child_map


async def _load_bindings(db: aiosqlite.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    cur = await db.execute(
        """
        SELECT b.metric_node_code, b.scope_type, b.scope_code, b.data_acct_code,
               d.data_acct_name, d.value_type, d.budget_formula, d.actual_formula,
               COALESCE(b.sort_order, 0)
        FROM data_account_metric_binding b
        JOIN data_account d ON d.data_acct_code = b.data_acct_code
        JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
        WHERE b.is_active = 1
          AND COALESCE(n.is_active, 1) = 1
        """
    )
    bindings: dict[tuple[str, str], dict[str, Any]] = {}
    for row in await cur.fetchall():
        metric_code = _upper(row[0])
        scope = _upper(row[2])
        if not metric_code or not scope:
            continue
        bindings[(metric_code, scope)] = {
            "metric_node_code": metric_code,
            "scope_type": _upper(row[1]) or ("CORP" if scope == "CORP" else "PRODUCT"),
            "scope_code": scope,
            "data_acct_code": _upper(row[3]),
            "data_acct_name": _clean(row[4]),
            "value_type": _clean(row[5]) or "金额",
            "budget_formula": row[6],
            "actual_formula": row[7],
            "sort_order": int(row[8] or 0),
        }
    return bindings


async def sync_metric_tree_rollup_accounts(
    db: aiosqlite.Connection,
    *,
    metric_node_codes: set[str] | None = None,
) -> MetricTreeRollupSyncResult:
    return MetricTreeRollupSyncResult()


def _collect_child_source_codes(
    node_code: str,
    scope_code: str,
    *,
    nodes: dict[str, dict[str, Any]],
    children: dict[str | None, list[str]],
    bindings: dict[tuple[str, str], dict[str, Any]],
) -> list[str]:
    result: list[str] = []

    def collect_from(child_code: str) -> None:
        child = nodes.get(child_code, {})
        binding = bindings.get((child_code, scope_code))
        if binding and (child.get("node_type") == "METRIC" or int(child.get("vertical_rollup") or 0) == 1):
            result.append(str(binding["data_acct_code"]))
            return
        for grand_child in children.get(child_code, []):
            collect_from(grand_child)

    for child in children.get(node_code, []):
        collect_from(child)
    return sorted(dict.fromkeys(result))


async def _period_ids_for_year(common_path: Path, budget_year: int) -> list[int]:
    async with aiosqlite.connect(common_path) as db:
        cur = await db.execute(
            "SELECT period_id FROM period WHERE year = ? ORDER BY period_id",
            (f"Y{int(budget_year)}",),
        )
        return [int(r[0]) for r in await cur.fetchall()]


def _normalize_plan_inputs(
    product_codes: list[str],
    budget_actuals: list[int],
) -> tuple[list[str], list[int]]:
    product_set = sorted({_upper(code) for code in product_codes if _upper(code)})
    actuals = sorted({int(item) for item in budget_actuals if int(item) in (0, 1)})
    return product_set, actuals


async def build_metric_tree_rollup_plan(
    *,
    common_path: Path,
    budget_year: int,
    product_codes: list[str],
    budget_actuals: list[int],
    sync_accounts: bool = True,
) -> MetricTreeRollupPlan:
    product_set, actuals = _normalize_plan_inputs(product_codes, budget_actuals)
    plan = MetricTreeRollupPlan(
        product_codes=tuple(product_set),
        budget_actuals=tuple(actuals),
    )
    if not product_set or not actuals:
        return plan

    async with aiosqlite.connect(common_path) as cdb:
        await cdb.execute("PRAGMA foreign_keys = ON")
        nodes = await _load_metric_nodes(cdb)
        children = _children_by_parent(nodes)
        bindings = await _load_bindings(cdb)
        product_children = await _load_product_children(cdb)

    period_ids = await _period_ids_for_year(common_path, budget_year)
    plan.period_ids = tuple(period_ids)
    if not period_ids:
        return plan

    product_set_upper = {_upper(c) for c in product_set}
    rollup_nodes = {
        code: node
        for code, node in nodes.items()
        if (
            int(node.get("horizontal_rollup") or 0) == 1
            and bool(product_children.get(_upper(node.get("product_code")), set()) & product_set_upper)
        )
        or (int(node.get("vertical_rollup") or 0) == 1 and children.get(code))
    }
    ordered_nodes = sorted(rollup_nodes, key=lambda code: (_node_depth(code), code), reverse=True)
    target_code_set: set[str] = set()
    plan_product_codes = set(product_set)
    for node_code in rollup_nodes:
        target_scopes = set(product_set)
        if int(nodes[node_code].get("horizontal_rollup") or 0) == 1:
            target_scope = _upper(nodes[node_code].get("product_code"))
            if target_scope:
                target_scopes = {target_scope}  # 横向汇总只用自身 scope
        plan_product_codes.update(target_scopes)
        for scope in sorted(target_scopes):
            if (node_code, scope) in bindings:
                target_code_set.add(str(bindings[(node_code, scope)]["data_acct_code"]))
            elif len(plan.warnings) < 50:
                plan.warnings.append(
                    f"{node_code}/{scope} 未在机构及产品指标表确认运行主键，已跳过汇总。"
                )
    target_codes = sorted(target_code_set)
    plan.target_codes = tuple(target_codes)
    plan.product_codes = tuple(sorted(plan_product_codes))
    if not target_codes:
        return plan

    all_source_codes: set[str] = set()
    by_local_code: dict[str, list[str]] = {}
    for code, node in nodes.items():
        local = _upper(node.get("logic_code"))
        product = _upper(node.get("product_code"))
        if local and product:
            by_local_code.setdefault(local, []).append(code)

    for node_code in ordered_nodes:
        target_scopes = set(product_set)
        if int(nodes[node_code].get("horizontal_rollup") or 0) == 1:
            target_scope = _upper(nodes[node_code].get("product_code"))
            if target_scope:
                target_scopes = {target_scope}  # 横向汇总只用自身 scope
        for scope in sorted(target_scopes):
            target = bindings.get((node_code, scope))
            if not target:
                if len(plan.warnings) < 50:
                    plan.warnings.append(
                        f"{node_code}/{scope} 未在机构及产品指标表确认运行主键，已跳过汇总。"
                    )
                continue
            target_code = str(target["data_acct_code"])
            if int(nodes[node_code].get("horizontal_rollup") or 0) == 1:
                local_code = _upper(nodes[node_code].get("logic_code"))
                source_refs: list[tuple[str, str]] = []
                for peer_code in sorted(by_local_code.get(local_code, [])):
                    peer_product = _upper(nodes.get(peer_code, {}).get("product_code"))
                    if not peer_product or peer_product == scope or peer_product not in product_set:
                        continue
                    # 横向汇总仅汇总直接子级机构（产品→群→全行）
                    node_product = _upper(nodes[node_code].get("product_code"))
                    peer_children = product_children.get(node_product, set())
                    if peer_children and peer_product not in peer_children:
                        continue
                    peer_binding = bindings.get((peer_code, peer_product))
                    if not peer_binding:
                        continue
                    source_refs.append((str(peer_binding["data_acct_code"]), peer_product))
                source_refs = sorted(dict.fromkeys(source_refs))
                if not source_refs:
                    continue  # 当前 product_set 下无直接子级，跳过
                source_codes = tuple(sorted({code for code, _product in source_refs}))
                all_source_codes.update(source_codes)
                for budget_actual in actuals:
                    plan.tasks.append(
                        MetricTreeRollupTask(
                            node_code=node_code,
                            target_data_acct_code=target_code,
                            scope_code=scope,
                            method="HORIZONTAL_SUM",
                            budget_actual=budget_actual,
                            source_codes=source_codes,
                            source_refs=tuple(source_refs),
                        )
                    )
            elif int(nodes[node_code].get("vertical_rollup") or 0) == 1:
                sources = tuple(
                    _collect_child_source_codes(
                        node_code,
                        scope,
                        nodes=nodes,
                        children=children,
                        bindings=bindings,
                    )
                )
                all_source_codes.update(sources)
                source_refs = tuple((source, scope) for source in sources)
                task_method = "SUM"
                for budget_actual in actuals:
                    plan.tasks.append(
                        MetricTreeRollupTask(
                            node_code=node_code,
                            target_data_acct_code=target_code,
                            scope_code=scope,
                            method=task_method,
                            budget_actual=budget_actual,
                            source_codes=sources,
                            source_refs=source_refs,
                        )
                    )

    all_source_codes.difference_update(target_codes)
    plan.source_codes = tuple(sorted(all_source_codes))
    return plan


async def rebuild_metric_tree_rollups(
    *,
    common_path: Path,
    budget_path: Path,
    budget_year: int,
    version_id: int,
    product_codes: list[str],
    budget_actuals: list[int],
) -> MetricTreeRollupRebuildResult:
    plan = await build_metric_tree_rollup_plan(
        common_path=common_path,
        budget_year=budget_year,
        product_codes=product_codes,
        budget_actuals=budget_actuals,
    )
    result = plan.to_result()
    if not plan.product_codes or not plan.budget_actuals:
        return result

    if not plan.period_ids or not plan.target_codes:
        return result

    base_values: dict[tuple[str, str, int, int], float] = {}
    if plan.source_codes:
        code_placeholders = ",".join("?" for _ in plan.source_codes)
        product_placeholders = ",".join("?" for _ in plan.product_codes)
        period_placeholders = ",".join("?" for _ in plan.period_ids)
        actual_placeholders = ",".join("?" for _ in plan.budget_actuals)
        async with aiosqlite.connect(budget_path) as bdb:
            await bdb.execute("PRAGMA foreign_keys = ON")
            cur = await bdb.execute(
                f"""
                SELECT data_acct_code, product_code, period_id, budget_actual, value
                FROM budget_data
                WHERE version_id = ?
                  AND data_acct_code IN ({code_placeholders})
                  AND product_code IN ({product_placeholders})
                  AND period_id IN ({period_placeholders})
                  AND budget_actual IN ({actual_placeholders})
                """,
                (
                    int(version_id),
                    *plan.source_codes,
                    *plan.product_codes,
                    *plan.period_ids,
                    *plan.budget_actuals,
                ),
            )
            for code_raw, product_raw, period_raw, actual_raw, value_raw in await cur.fetchall():
                base_values[(_upper(code_raw), _upper(product_raw), int(period_raw), int(actual_raw))] = float(value_raw or 0.0)

    computed: dict[tuple[str, str, int, int], float] = {}
    write_items: list[BudgetDataWriteItem] = []

    def lookup(code: str, product: str, period_id: int, budget_actual: int) -> float:
        key = (_upper(code), _upper(product), int(period_id), int(budget_actual))
        if key in computed:
            return computed[key]
        return base_values.get(key, 0.0)

    for task in plan.tasks:
        for period_id in plan.period_ids:
            if task.method == "SUM":
                value = sum(
                    lookup(source, source_product, period_id, task.budget_actual)
                    for source, source_product in (task.source_refs or tuple((source, task.scope_code) for source in task.source_codes))
                )
            elif task.method == "HORIZONTAL_SUM":
                value = sum(
                    lookup(source, source_product, period_id, task.budget_actual)
                    for source, source_product in task.source_refs
                )
            else:
                formula = task.formula or ""
                refs = {
                    ref: lookup(ref, task.scope_code, period_id, task.budget_actual)
                    for ref in extract_formula_codes(formula)
                }
                value = calculate_formula_value(formula, refs)
            computed[(task.target_data_acct_code, task.scope_code, period_id, task.budget_actual)] = float(value)
            write_items.append(
                BudgetDataWriteItem(
                    data_acct_code=task.target_data_acct_code,
                    product_code=task.scope_code,
                    period_id=period_id,
                    budget_actual=task.budget_actual,
                    version_id=int(version_id),
                    value=float(value),
                    source_ref=f"指标树汇总 {task.target_data_acct_code}/{task.scope_code}/period={period_id}",
                )
            )

    await delete_rollup_budget_data_rows(
        budget_path=budget_path,
        version_id=int(version_id),
        data_acct_codes=plan.target_codes,
        product_codes=plan.product_codes,
        budget_actuals=plan.budget_actuals,
    )

    if not write_items:
        return result

    write_result = await write_budget_data_items(
        budget_path=budget_path,
        common_path=common_path,
        items=write_items,
        policy=ROLLUP_RESULT_POLICY,
    )
    result.written_cells = int(write_result.saved_cells)
    result.warnings.extend(write_result.warnings)
    return result


async def estimate_metric_tree_rollups(
    *,
    common_path: Path,
    budget_year: int,
    product_codes: list[str],
    budget_actuals: list[int],
) -> MetricTreeRollupRebuildResult:
    plan = await build_metric_tree_rollup_plan(
        common_path=common_path,
        budget_year=budget_year,
        product_codes=product_codes,
        budget_actuals=budget_actuals,
    )
    return plan.to_result()
