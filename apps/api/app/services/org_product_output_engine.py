from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

from app.routers.org_product_helpers import *
from app.services.annual_aggregation import MONTHLY_AGG_RULES, compute_annual


def _load_org_product_direct_children(conn: sqlite3.Connection) -> dict[str, tuple[str, ...]]:
    """机构树：父级 entity_code -> 直接下级 entity_code 列表。"""
    _ensure_org_product_tree_table(conn)
    row = conn.execute("SELECT payload_json FROM org_product_tree_snapshot WHERE id=1").fetchone()
    if not row or not row[0]:
        return {}
    try:
        tree = json.loads(row[0])
    except Exception:
        return {}

    child_map: dict[str, set[str]] = {}

    def walk(node: dict[str, Any], parent_code: str | None = None) -> None:
        code = _normalize_text(node.get("code")).upper()
        if parent_code and code:
            child_map.setdefault(parent_code, set()).add(code)
        for child in list(node.get("children") or []):
            if isinstance(child, dict):
                walk(child, code if code else parent_code)

    root = tree if isinstance(tree, dict) else {}
    for child in list(root.get("children") or []):
        if isinstance(child, dict):
            walk(child)

    return {key: tuple(sorted(values)) for key, values in child_map.items()}


class OrgProductOutputEntityEngine:
    """单机构单表的预测输出计算（含横向/纵向汇总与跨机构引用）。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        entity_code: str,
        entity_name: str,
        table_name: str,
        year: int,
        version_id: int,
        child_map: dict[str, tuple[str, ...]],
        get_peer_engine: Callable[[str, str], OrgProductOutputEntityEngine],
    ) -> None:
        self.conn = conn
        self.entity_code = _normalize_text(entity_code).upper()
        self.entity_name = _normalize_text(entity_name)
        self.table_name = _normalize_text(table_name)
        self.year = int(year)
        self.version_id = int(version_id)
        self.child_map = child_map
        self.get_peer_engine = get_peer_engine

        table_rows = [
            row
            for row in load_org_product_metric_table_rows_from_runtime_tree(conn)
            if str(row.get("entity_code") or "").strip().upper() == self.entity_code
            and str(row.get("table_name") or "").strip() == self.table_name
        ]
        payload_json = table_rows[0]["payload_json"] if table_rows else "{}"
        try:
            table_obj = json.loads(payload_json or "{}")
        except Exception:
            table_obj = {}

        nodes = list(table_obj.get("metrics") or [])
        flat = _flatten_metric_nodes([n for n in nodes if isinstance(n, dict)])
        self.children_by_code: dict[str, list[str]] = {}

        def collect_children_by_code(items: list[dict[str, Any]]) -> None:
            for item in items:
                if not isinstance(item, dict):
                    continue
                parent_code = _normalize_text(item.get("code"))
                children = [c for c in list(item.get("children") or []) if isinstance(c, dict)]
                if parent_code:
                    self.children_by_code[parent_code] = [
                        _normalize_text(c.get("code")) for c in children if _normalize_text(c.get("code"))
                    ]
                collect_children_by_code(children)

        collect_children_by_code([n for n in nodes if isinstance(n, dict)])

        self.metrics = [
            {
                "id": str(x.get("id") or ""),
                "levelLabel": _normalize_text(x.get("levelLabel")),
                "nature": _normalize_nature(x.get("nature")),
                "code": _normalize_text(x.get("code")),
                "name": _normalize_text(x.get("name")),
                "formula": _normalize_text(x.get("formula")),
                "formula_budget_annual": _normalize_text(x.get("formula_budget_annual")),
                "formula_forecast_annual": _normalize_text(x.get("formula_forecast_annual")),
                "formula_actual": _normalize_text(x.get("formula_actual")),
                "formula_forecast": _normalize_text(x.get("formula_forecast")),
                "formula_note": _normalize_text(x.get("formula_note")),
                "annual_agg_rule": _normalize_text(x.get("annual_agg_rule")).upper(),
                "value_type": _normalize_metric_value_type(x.get("value_type"), x.get("nature")),
                "horizontal_rollup": _normalize_rollup_flag(x.get("horizontal_rollup")),
                "vertical_rollup": _normalize_rollup_flag(x.get("vertical_rollup")),
                "allow_manual_entry": _normalize_allow_manual_entry(x.get("allow_manual_entry"), 1),
                "calc_role": _normalize_calc_role(
                    x.get("calc_role"),
                    allow_manual_entry=x.get("allow_manual_entry"),
                ),
                "logic_code": _derive_metric_logic_code(self.entity_code, x.get("code"), x.get("logic_code")),
            }
            for x in flat
            if _normalize_text(x.get("code")) and _normalize_text(x.get("name"))
        ]
        self.metric_by_code = {m["code"]: m for m in self.metrics}
        self.logic_to_code: dict[str, str] = {}
        for metric in self.metrics:
            logic = _normalize_text(metric.get("logic_code")).upper()
            code = metric.get("code") or ""
            if not logic:
                continue
            existing = self.logic_to_code.get(logic)
            if not existing or code.count(".") < existing.count("."):
                self.logic_to_code[logic] = code

        cur_snap = conn.execute(
            """
            SELECT payload_json, month_index
            FROM org_product_data_entry_snapshot_v2
            WHERE entity_code=? AND year=? AND version_id=? AND table_name=?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (self.entity_code, self.year, self.version_id, self.table_name),
        )
        snap_row = cur_snap.fetchone()
        snap_obj = json.loads(snap_row[0]) if snap_row and snap_row[0] else None
        self.rolling_month = 3
        if snap_row and snap_row[1] is not None:
            try:
                self.rolling_month = max(1, min(12, int(snap_row[1])))
            except Exception:
                self.rolling_month = 3
        elif isinstance(snap_obj, dict) and snap_obj.get("month_index") is not None:
            try:
                self.rolling_month = max(1, min(12, int(snap_obj.get("month_index"))))
            except Exception:
                self.rolling_month = 3

        entry_metrics = list((snap_obj or {}).get("metrics") or []) if isinstance(snap_obj, dict) else []
        self.entry_by_code: dict[str, list[float | None]] = {}
        self.entry_annual_by_code: dict[str, float | None] = {}
        for r in entry_metrics:
            if not isinstance(r, dict):
                continue
            mc = str(r.get("metric_code") or "").strip()
            mid = str(r.get("metric_id") or "").strip()
            key = mc or mid
            if not key:
                continue
            v = r.get("values") if isinstance(r.get("values"), dict) else {}
            self.entry_by_code[key] = [_parse_data_entry_month_value(v, m) for m in range(1, 13)]
            self.entry_annual_by_code[key] = _parse_data_entry_annual_value(v)

        self.month_cache: dict[tuple[str, int], tuple[float, str | None]] = {}
        self.month_visiting: set[tuple[str, int]] = set()
        self.month_results: dict[str, tuple[list[float], list[str | None]]] | None = None
        self.annual_cache: dict[str, float | None] = {}
        self.annual_visiting: set[str] = set()

    def _resolve_ref_value(self, ref: str, month_idx: int) -> tuple[float, str | None]:
        if "/" in ref:
            parts = ref.split("/")
            if len(parts) == 2:
                ref_table_name, ref_code = parts[0], parts[1]
                if ref_table_name == self.table_name:
                    val, err = self.compute_metric_value(ref_code, month_idx)
                    return float(val), err
                peer = self.get_peer_engine(self.entity_code, ref_table_name)
                val, err = peer.compute_metric_value(ref_code, month_idx)
                return float(val), err
            if len(parts) != 3:
                return 0.0, "#REF!"
            ref_entity_code, ref_table_name, ref_code = parts[0], parts[1], parts[2]
            if ref_entity_code == self.entity_code and ref_table_name == self.table_name:
                val, err = self.compute_metric_value(ref_code, month_idx)
                return float(val), err
            peer = self.get_peer_engine(ref_entity_code, ref_table_name)
            val, err = peer.compute_metric_value(ref_code, month_idx)
            return float(val), err
        val, err = self.compute_metric_value(ref, month_idx)
        return float(val), err

    def _compute_horizontal_rollup(self, meta: dict[str, Any], month_idx: int) -> tuple[float, str | None] | None:
        if not _normalize_rollup_flag(meta.get("horizontal_rollup")):
            return None
        logic = _normalize_text(meta.get("logic_code")).upper()
        if not logic:
            return None
        child_entities = self.child_map.get(self.entity_code, ())
        if not child_entities:
            return None

        total = 0.0
        child_err: str | None = None
        found_any = False
        for child_entity in child_entities:
            peer = self.get_peer_engine(child_entity, self.table_name)
            peer_code = peer.logic_to_code.get(logic)
            if not peer_code:
                continue
            val, err = peer.compute_metric_value(peer_code, month_idx)
            total += float(val)
            found_any = True
            if err and not child_err:
                child_err = err
        if not found_any:
            return None
        return total, child_err

    def compute_metric_value(self, code_key: str, month_idx: int) -> tuple[float, str | None]:
        k = (code_key, month_idx)
        if k in self.month_cache:
            return self.month_cache[k]
        if k in self.month_visiting:
            return 0.0, "#CYCLE!"
        self.month_visiting.add(k)
        try:
            meta = self.metric_by_code.get(code_key)
            if not meta:
                base = self.entry_by_code.get(code_key)
                if base is not None:
                    v = base[month_idx - 1]
                    self.month_cache[k] = (float(v) if v is not None else 0.0), None
                    return self.month_cache[k]
                self.month_cache[k] = (0.0, None)
                return self.month_cache[k]

            entry_val = _lookup_entry_month_value(self.entry_by_code, code_key, meta, month_idx)
            if _org_product_month_value_from_entry(meta, entry_val):
                self.month_cache[k] = (float(entry_val), None)
                return self.month_cache[k]

            horizontal = self._compute_horizontal_rollup(meta, month_idx)
            if horizontal is not None:
                self.month_cache[k] = horizontal
                return self.month_cache[k]

            calc_role = _normalize_calc_role(
                meta.get("calc_role"),
                allow_manual_entry=meta.get("allow_manual_entry"),
            )
            formula = _resolve_metric_formula_for_month(meta, month_idx, self.rolling_month)
            if formula and calc_role != "entry":
                expr = _prepare_metric_formula_expression(formula)
                refs = _extract_metric_formula_refs(expr)
                ref_values: dict[str, float] = {}
                ref_err: str | None = None
                for r in refs:
                    v, err = self._resolve_ref_value(r, month_idx)
                    ref_values[r] = float(v)
                    if err and not ref_err:
                        ref_err = err
                val, calc_err = _try_calculate_metric_formula_value(expr, ref_values)
                final_err = calc_err or ref_err
                self.month_cache[k] = (float(val), final_err)
                return self.month_cache[k]

            if _normalize_rollup_flag(meta.get("vertical_rollup")):
                child_codes = self.children_by_code.get(code_key) or []
                if child_codes:
                    total = 0.0
                    child_err: str | None = None
                    for child_code in child_codes:
                        v, err = self.compute_metric_value(child_code, month_idx)
                        total += float(v)
                        if err and not child_err:
                            child_err = err
                    self.month_cache[k] = (total, child_err)
                    return self.month_cache[k]

            if entry_val is not None and calc_role != "formula":
                self.month_cache[k] = (float(entry_val), None)
                return self.month_cache[k]
            self.month_cache[k] = (0.0, None)
            return self.month_cache[k]
        finally:
            self.month_visiting.discard(k)

    def compute_metric_annual(self, code_key: str) -> float | None:
        if code_key in self.annual_cache:
            return self.annual_cache[code_key]
        if code_key in self.annual_visiting:
            return None
        meta = self.metric_by_code.get(code_key)
        if self.month_results is None:
            self.ensure_month_results()
        months_pack = self.month_results.get(code_key) if self.month_results else None
        if not months_pack:
            self.annual_cache[code_key] = None
            return None
        months, _errs = months_pack
        month_vals: list[float | None] = list(months)

        if not meta:
            self.annual_cache[code_key] = _annual_summary_by_nature("", month_vals, self.year)
            return self.annual_cache[code_key]

        annual_entry = _lookup_entry_annual_value(self.entry_annual_by_code, code_key, meta)
        if _org_product_annual_value_from_entry(meta, annual_entry):
            self.annual_cache[code_key] = float(annual_entry)
            return self.annual_cache[code_key]

        if _normalize_rollup_flag(meta.get("horizontal_rollup")):
            logic = _normalize_text(meta.get("logic_code")).upper()
            child_entities = self.child_map.get(self.entity_code, ())
            if logic and child_entities:
                self.annual_visiting.add(code_key)
                try:
                    total = 0.0
                    found_any = False
                    for child_entity in child_entities:
                        peer = self.get_peer_engine(child_entity, self.table_name)
                        peer_code = peer.logic_to_code.get(logic)
                        if not peer_code:
                            continue
                        av = peer.compute_metric_annual(peer_code)
                        if av is not None:
                            total += float(av)
                            found_any = True
                    if found_any:
                        self.annual_cache[code_key] = total
                        return self.annual_cache[code_key]
                finally:
                    self.annual_visiting.discard(code_key)

        nature = str(meta.get("nature") or "")
        formula = str(meta.get("formula") or "").strip()
        formula_budget_annual = str(meta.get("formula_budget_annual") or "").strip()
        annual_agg_rule = str(meta.get("annual_agg_rule") or "").strip().upper()

        use_formula, annual_formula = _resolve_annual_formula_recompute(
            nature=nature,
            formula=formula,
            formula_budget_annual=formula_budget_annual,
            formula_forecast_annual=str(meta.get("formula_forecast_annual") or "").strip(),
            annual_agg_rule=annual_agg_rule,
        )
        if _org_product_should_use_annual_formula(meta, use_formula=use_formula):
            self.annual_visiting.add(code_key)
            try:
                expr = _prepare_metric_formula_expression(annual_formula)
                refs = _extract_metric_formula_refs(expr)
                ref_values: dict[str, float] = {}
                for r in refs:
                    if "/" in r:
                        parts = r.split("/")
                        if len(parts) == 2:
                            ref_table_name, ref_code = parts[0], parts[1]
                            if ref_table_name == self.table_name:
                                av = self.compute_metric_annual(ref_code)
                            else:
                                peer = self.get_peer_engine(self.entity_code, ref_table_name)
                                av = peer.compute_metric_annual(ref_code)
                            ref_values[r] = float(av) if av is not None else 0.0
                            continue
                        if len(parts) != 3:
                            ref_values[r] = 0.0
                            continue
                        ref_entity_code, ref_table_name, ref_code = parts
                        if ref_entity_code == self.entity_code and ref_table_name == self.table_name:
                            av = self.compute_metric_annual(ref_code)
                        else:
                            peer = self.get_peer_engine(ref_entity_code, ref_table_name)
                            av = peer.compute_metric_annual(ref_code)
                        ref_values[r] = float(av) if av is not None else 0.0
                    else:
                        av = self.compute_metric_annual(r)
                        ref_values[r] = float(av) if av is not None else 0.0
                val, _calc_err = _try_calculate_metric_formula_value(expr, ref_values)
                self.annual_cache[code_key] = float(val)
                return self.annual_cache[code_key]
            finally:
                self.annual_visiting.discard(code_key)

        if annual_agg_rule in MONTHLY_AGG_RULES:
            month_floats = [float(x) if x is not None else 0.0 for x in month_vals]
            self.annual_cache[code_key] = compute_annual(month_floats, annual_agg_rule)
            return self.annual_cache[code_key]

        if _should_use_vertical_rollup_annual(meta):
            child_codes = self.children_by_code.get(code_key) or []
            if child_codes:
                self.annual_visiting.add(code_key)
                try:
                    total = 0.0
                    found_any = False
                    for child_code in child_codes:
                        av = self.compute_metric_annual(child_code)
                        if av is not None:
                            total += float(av)
                            found_any = True
                    self.annual_cache[code_key] = total if found_any else None
                    return self.annual_cache[code_key]
                finally:
                    self.annual_visiting.discard(code_key)

        self.annual_cache[code_key] = _annual_summary_by_nature(nature, month_vals, self.year)
        return self.annual_cache[code_key]

    def ensure_month_results(self) -> None:
        if self.month_results is not None:
            return
        out: dict[str, tuple[list[float], list[str | None]]] = {}
        for metric in self.metrics:
            code_key = metric["code"]
            computed = [self.compute_metric_value(code_key, mi) for mi in range(1, 13)]
            months = [float(v) for v, _ in computed]
            month_errors = [err for _, err in computed]
            out[code_key] = (months, month_errors)
        self.month_results = out

    def build_output_rows(self) -> list[dict[str, Any]]:
        self.ensure_month_results()
        assert self.month_results is not None
        out_rows: list[dict[str, Any]] = []
        for metric in self.metrics:
            code_key = metric["code"]
            months, month_errors = self.month_results[code_key]
            annual = self.compute_metric_annual(code_key)
            formula = str(metric.get("formula") or "").strip()
            out_rows.append(
                {
                    "id": metric["id"],
                    "levelLabel": metric["levelLabel"],
                    "nature": metric["nature"],
                    "code": metric["code"],
                    "name": metric["name"],
                    "value_type": metric["value_type"],
                    "formula": formula,
                    "months": months,
                    "month_errors": month_errors,
                    "annual": annual,
                    "annual_method": _annual_method_label(
                        metric.get("nature") or "",
                        formula,
                        str(metric.get("annual_agg_rule") or ""),
                    ),
                }
            )
        return out_rows


class OrgProductOutputRunEngine:
    def __init__(self, conn: sqlite3.Connection, *, year: int, version_id: int) -> None:
        self.conn = conn
        self.year = int(year)
        self.version_id = int(version_id)
        self.child_map = _load_org_product_direct_children(conn)
        self._engines: dict[tuple[str, str], OrgProductOutputEntityEngine] = {}
        self._entity_name_by_code: dict[str, str] = {}

    def _remember_entity_name(self, entity_code: str, entity_name: str) -> None:
        code = _normalize_text(entity_code).upper()
        name = _normalize_text(entity_name)
        if code and name:
            self._entity_name_by_code[code] = name

    def get_engine(self, entity_code: str, table_name: str) -> OrgProductOutputEntityEngine:
        ec = _normalize_text(entity_code).upper()
        tn = _normalize_text(table_name)
        key = (ec, tn)
        if key not in self._engines:
            self._engines[key] = OrgProductOutputEntityEngine(
                self.conn,
                entity_code=ec,
                entity_name=self._entity_name_by_code.get(ec, ""),
                table_name=tn,
                year=self.year,
                version_id=self.version_id,
                child_map=self.child_map,
                get_peer_engine=lambda peer_ec, peer_tn: self.get_engine(peer_ec, peer_tn),
            )
        return self._engines[key]

    def run_entity(self, entity_code: str, entity_name: str, table_name: str) -> dict[str, Any]:
        ec = _normalize_text(entity_code).upper()
        tn = _normalize_text(table_name)
        self._remember_entity_name(ec, entity_name)
        engine = self.get_engine(ec, tn)
        engine.entity_name = _normalize_text(entity_name) or engine.entity_name
        return {
            "entity_code": ec,
            "entity_name": engine.entity_name or self._entity_name_by_code.get(ec, ""),
            "table_name": tn,
            "rows": engine.build_output_rows(),
        }
