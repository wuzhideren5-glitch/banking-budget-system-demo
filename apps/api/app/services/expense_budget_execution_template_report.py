"""Template-mode read model for expense budget execution reports."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.services.expense_budget_execution_framework import (
    FrameworkContext,
    effective_manage_departments,
    matches_template_scope,
    scope_allows_manage_department,
    text,
)
from app.services.expense_budget_execution_metrics import (
    filter_tree_by_keyword,
    filter_zero_metric_tree,
    metric_payload,
    new_month_values,
)


@dataclass(frozen=True)
class TemplateReportModel:
    subject_tree: list[dict[str, Any]]


def filter_template_subject_tree_by_scope(
    nodes: list[dict[str, Any]],
    *,
    ctx: FrameworkContext,
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for node in nodes:
        child_nodes = filter_template_subject_tree_by_scope(
            list(node.get("children", [])),
            ctx=ctx,
            selected_entity=selected_entity,
            selected_group=selected_group,
            selected_owner=selected_owner,
        )
        node_visible = scope_allows_manage_department(
            ctx=ctx,
            manage_department=text(node.get("effective_manage_department")),
            selected_entity=selected_entity,
            selected_group=selected_group,
            selected_owner=selected_owner,
        )
        if node_visible or child_nodes:
            next_node = dict(node)
            next_node["children"] = child_nodes
            filtered.append(next_node)
    return filtered


def build_template_subject_tree(
    subject_rows: list[dict[str, Any]],
    current_subject_monthly_totals: dict[str, list[float]],
    budget_subject_totals: dict[str, float],
    previous_year_subject_monthly_totals: dict[str, list[float]],
    previous_year_subject_totals: dict[str, float],
    effective_manage_by_id: dict[int, str],
    current_month: int,
) -> list[dict[str, Any]]:
    node_map: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for row in subject_rows:
        node_map[int(row["id"])] = {
            "id": int(row["id"]),
            "parent_id": row["parent_id"],
            "level_number": int(row["level_number"]),
            "level_label": text(row["level_label"]) or f'{int(row["level_number"])}级',
            "subject_name": text(row["subject_name"]),
            "manage_department": text(row.get("manage_department")) or None,
            "effective_manage_department": text(effective_manage_by_id.get(int(row["id"]), "")) or None,
            "formula_text": text(row.get("formula_text")) or None,
            "sort_order": int(row.get("sort_order") or 0),
            "children": [],
        }
    for row in subject_rows:
        node = node_map[int(row["id"])]
        parent_id = row["parent_id"]
        if parent_id is not None and int(parent_id) in node_map:
            node_map[int(parent_id)]["children"].append(node)
        else:
            roots.append(node)

    def sort_nodes(nodes: list[dict[str, Any]]) -> None:
        nodes.sort(key=lambda item: (int(item["sort_order"]), int(item["id"])))
        for child in nodes:
            sort_nodes(list(child["children"]))

    consumed_current_subjects: set[str] = set()
    consumed_budget_subjects: set[str] = set()
    consumed_previous_subjects: set[str] = set()

    def direct_month_values(source: dict[str, list[float]], subject_name: str, consumed: set[str]) -> tuple[list[float], bool]:
        if subject_name in consumed:
            return new_month_values(), False
        values = source.get(subject_name)
        if values is None:
            return new_month_values(), False
        consumed.add(subject_name)
        return [round(float(value or 0.0), 2) for value in values[:12]] + [0.0] * max(0, 12 - len(values)), True

    def direct_amount(source: dict[str, float], subject_name: str, consumed: set[str]) -> tuple[float, bool]:
        if subject_name in consumed:
            return 0.0, False
        if subject_name not in source:
            return 0.0, False
        consumed.add(subject_name)
        return round(float(source.get(subject_name) or 0.0), 2), True

    def fill_metrics(node: dict[str, Any]) -> dict[str, Any]:
        subject_name = node["subject_name"]
        monthly_actuals, has_direct_current = direct_month_values(
            current_subject_monthly_totals,
            subject_name,
            consumed_current_subjects,
        )
        previous_year_monthly_actuals, has_direct_previous_monthly = direct_month_values(
            previous_year_subject_monthly_totals,
            subject_name,
            consumed_previous_subjects,
        )
        annual_budget, has_direct_budget = direct_amount(
            budget_subject_totals,
            subject_name,
            consumed_budget_subjects,
        )
        last_year_actual = round(sum(previous_year_monthly_actuals), 2) if has_direct_previous_monthly else 0.0
        if not has_direct_previous_monthly:
            last_year_actual, has_direct_previous_total = direct_amount(
                previous_year_subject_totals,
                subject_name,
                consumed_previous_subjects,
            )
        else:
            has_direct_previous_total = True
        filled_children: list[dict[str, Any]] = []
        for child in list(node["children"]):
            child_filled = fill_metrics(child)
            filled_children.append(child_filled)
            child_monthly_actuals = list(child_filled.get("monthly_actuals", new_month_values()))
            child_previous_year_monthly_actuals = list(
                child_filled.get("previous_year_monthly_actuals", new_month_values())
            )
            if not has_direct_current:
                monthly_actuals = [
                    round(monthly_actuals[idx] + child_monthly_actuals[idx], 2)
                    for idx in range(12)
                ]
            if not has_direct_previous_monthly and not has_direct_previous_total:
                previous_year_monthly_actuals = [
                    round(previous_year_monthly_actuals[idx] + child_previous_year_monthly_actuals[idx], 2)
                    for idx in range(12)
                ]
                last_year_actual += float(child_filled["last_year_actual"])
            if not has_direct_budget:
                annual_budget += float(child_filled["annual_budget"])
        next_node = dict(node)
        next_node.update(metric_payload(monthly_actuals, annual_budget, last_year_actual, current_month))
        next_node["previous_year_monthly_actuals"] = [
            round(value, 2) for value in previous_year_monthly_actuals
        ]
        next_node["is_leaf"] = len(filled_children) == 0
        next_node["children"] = filled_children
        return next_node

    sort_nodes(roots)
    return [fill_metrics(node) for node in roots]


def build_template_report_model(
    *,
    ctx: FrameworkContext,
    subject_rows: list[dict[str, Any]],
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    previous_year_subject_monthly_totals: dict[str, list[float]],
    previous_year_subject_totals: dict[str, float],
    current_month: int,
    current_subject_monthly_totals_override: dict[str, list[float]] | None = None,
    budget_subject_totals_override: dict[str, float] | None = None,
    selected_entity: str = "",
    selected_group: str = "",
    selected_owner: str = "",
    include_zero_rows: bool = False,
    keyword: str = "",
) -> TemplateReportModel:
    current_subject_monthly_totals: dict[str, list[float]] = defaultdict(new_month_values)
    if current_subject_monthly_totals_override is not None:
        for budget_subject, month_values in current_subject_monthly_totals_override.items():
            for idx in range(min(current_month, len(month_values), 12)):
                current_subject_monthly_totals[budget_subject][idx] += round(float(month_values[idx] or 0.0), 2)
    else:
        for (owner_name, budget_subject), month_values in actual_by_owner.items():
            if not matches_template_scope(
                ctx=ctx,
                owner_name=owner_name,
                selected_entity=selected_entity,
                selected_group=selected_group,
                selected_owner=selected_owner,
            ):
                continue
            for idx in range(current_month):
                current_subject_monthly_totals[budget_subject][idx] += round(float(month_values[idx] or 0.0), 2)

    budget_subject_totals: dict[str, float] = defaultdict(float)
    if budget_subject_totals_override is not None:
        for budget_subject, amount in budget_subject_totals_override.items():
            budget_subject_totals[budget_subject] += round(float(amount or 0.0), 2)
    else:
        for (owner_name, budget_subject), amount in budget_by_owner.items():
            if not matches_template_scope(
                ctx=ctx,
                owner_name=owner_name,
                selected_entity=selected_entity,
                selected_group=selected_group,
                selected_owner=selected_owner,
            ):
                continue
            budget_subject_totals[budget_subject] += round(float(amount or 0.0), 2)

    effective_manage_by_id, _effective_manage_by_name = effective_manage_departments(subject_rows)
    subject_tree = build_template_subject_tree(
        subject_rows,
        {k: [round(item, 2) for item in values] for k, values in current_subject_monthly_totals.items()},
        {k: round(v, 2) for k, v in budget_subject_totals.items()},
        previous_year_subject_monthly_totals,
        previous_year_subject_totals,
        effective_manage_by_id,
        current_month,
    )
    scoped_tree = filter_template_subject_tree_by_scope(
        subject_tree,
        ctx=ctx,
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
    )
    zero_filtered_tree = filter_zero_metric_tree(
        scoped_tree,
        include_zero_rows=include_zero_rows,
    )
    filtered_tree = filter_tree_by_keyword(zero_filtered_tree, keyword)
    return TemplateReportModel(subject_tree=filtered_tree)
