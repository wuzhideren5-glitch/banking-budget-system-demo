"""Subject-mode read model for expense budget execution reports."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.services.expense_budget_execution_framework import (
    FrameworkContext,
    ParsedFramework,
    build_template_scope_options,
    default_group_name,
    entity_for_owner,
    entity_sort_key,
    group_sort_key,
    text,
)
from app.services.expense_budget_execution_metrics import (
    filter_tree_by_keyword,
    filter_zero_metric_tree,
    month_over_month_metrics,
    new_month_values,
)


@dataclass(frozen=True)
class SubjectReportModel:
    selected_subject_id: int | None
    subject_scope_tree: list[dict[str, Any]]
    subject_tree: list[dict[str, Any]]


def build_subject_scope_tree(subject_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    node_map: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for row in subject_rows:
        node_map[int(row["id"])] = {
            "id": int(row["id"]),
            "parent_id": row["parent_id"],
            "level_number": int(row["level_number"]),
            "level_label": text(row["level_label"]) or f'{int(row["level_number"])}级',
            "subject_name": text(row["subject_name"]),
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

    sort_nodes(roots)
    return roots


def collect_subject_names_by_selected_node(
    subject_rows: list[dict[str, Any]],
    selected_subject_id: int | None,
) -> tuple[int | None, set[str]]:
    children_by_parent: dict[int | None, list[int]] = defaultdict(list)
    subject_name_by_id: dict[int, str] = {}
    for row in subject_rows:
        subject_id = int(row["id"])
        parent_id = int(row["parent_id"]) if row["parent_id"] is not None else None
        children_by_parent[parent_id].append(subject_id)
        subject_name_by_id[subject_id] = text(row["subject_name"])
    if selected_subject_id is None or selected_subject_id not in subject_name_by_id:
        return None, set(subject_name_by_id.values())

    subject_names: set[str] = set()

    def _walk(subject_id: int) -> None:
        subject_name = subject_name_by_id.get(subject_id)
        if subject_name:
            subject_names.add(subject_name)
        for child_id in children_by_parent.get(subject_id, []):
            _walk(child_id)

    _walk(selected_subject_id)
    return selected_subject_id, subject_names


def build_subject_department_tree(
    *,
    ctx: FrameworkContext,
    parsed: ParsedFramework,
    actual_by_owner: dict[str, list[float]],
    budget_by_owner: dict[str, float],
    previous_year_actual_by_owner: dict[str, list[float]],
    current_month: int,
    selected_entity: str = "",
) -> list[dict[str, Any]]:
    owner_scope_rows = [
        item
        for item in build_template_scope_options(parsed)
        if (not selected_entity or item["entity_name"] == selected_entity)
    ]
    scope_keys = {
        (item["entity_name"], item["group_name"], item["owner_dept"])
        for item in owner_scope_rows
    }
    for owner_name in sorted(
        set(actual_by_owner.keys()) | set(budget_by_owner.keys()) | set(previous_year_actual_by_owner.keys()),
        key=lambda name: (len(name), name),
    ):
        entity_name = entity_for_owner(owner_name, ctx)
        if selected_entity and entity_name != selected_entity:
            continue
        group_name = ctx.owner_to_group.get(
            owner_name,
            default_group_name(entity_name),
        )
        scope_keys.add((entity_name, group_name, owner_name))

    groups_by_entity: dict[str, list[str]] = defaultdict(list)
    owners_by_entity_group: dict[tuple[str, str], list[str]] = defaultdict(list)
    for entity_name, group_name, owner_name in sorted(
        scope_keys,
        key=lambda item: (entity_sort_key(item[0]), group_sort_key(item[1]), len(item[2]), item[2]),
    ):
        if entity_name not in groups_by_entity or group_name not in groups_by_entity[entity_name]:
            groups_by_entity[entity_name].append(group_name)
        if owner_name not in owners_by_entity_group[(entity_name, group_name)]:
            owners_by_entity_group[(entity_name, group_name)].append(owner_name)

    node_id = 0

    def next_id() -> int:
        nonlocal node_id
        node_id += 1
        return node_id

    def metrics_from_values(
        monthly_actuals: list[float],
        annual_budget: float,
        previous_year_monthly_actuals: list[float],
    ) -> dict[str, Any]:
        current_actual = round(sum(monthly_actuals[:current_month]), 2)
        last_year_actual = round(sum(previous_year_monthly_actuals[:current_month]), 2)
        yoy_change = round(current_actual - last_year_actual, 2)
        month_over_month, month_over_month_rate = month_over_month_metrics(monthly_actuals, current_month)
        return {
            "monthly_actuals": [round(amount, 2) for amount in monthly_actuals],
            "previous_year_monthly_actuals": [round(amount, 2) for amount in previous_year_monthly_actuals],
            "current_actual": current_actual,
            "annual_budget": round(float(annual_budget or 0.0), 2),
            "budget_progress": round(current_actual / annual_budget, 6) if annual_budget else None,
            "yoy_change": yoy_change,
            "yoy_rate": round(yoy_change / last_year_actual, 6) if last_year_actual else None,
            "month_over_month": month_over_month,
            "month_over_month_rate": month_over_month_rate,
            "last_year_actual": last_year_actual,
        }

    def owner_node(owner_name: str) -> dict[str, Any]:
        metrics = metrics_from_values(
            actual_by_owner.get(owner_name, new_month_values()),
            budget_by_owner.get(owner_name, 0.0),
            previous_year_actual_by_owner.get(owner_name, new_month_values()),
        )
        return {
            "id": next_id(),
            "parent_id": None,
            "level_number": 3,
            "level_label": "费用归属部门",
            "subject_name": owner_name,
            "formula_text": None,
            "sort_order": 0,
            "is_leaf": True,
            **metrics,
            "children": [],
        }

    roots: list[dict[str, Any]] = []
    for entity_name in sorted(groups_by_entity.keys(), key=entity_sort_key):
        group_nodes: list[dict[str, Any]] = []
        for group_name in sorted(groups_by_entity[entity_name], key=group_sort_key):
            owner_nodes = [
                owner_node(owner_name)
                for owner_name in sorted(
                    owners_by_entity_group[(entity_name, group_name)],
                    key=lambda name: (len(name), name),
                )
            ]
            group_monthly = new_month_values()
            group_previous = new_month_values()
            group_budget = 0.0
            for child in owner_nodes:
                for idx, amount in enumerate(child["monthly_actuals"]):
                    group_monthly[idx] += amount
                for idx, amount in enumerate(child["previous_year_monthly_actuals"]):
                    group_previous[idx] += amount
                group_budget += float(child["annual_budget"] or 0.0)
            group_metrics = metrics_from_values(group_monthly, group_budget, group_previous)
            group_node = {
                "id": next_id(),
                "parent_id": None,
                "level_number": 2,
                "level_label": "事业群",
                "subject_name": group_name,
                "formula_text": None,
                "sort_order": 0,
                "is_leaf": False,
                **group_metrics,
                "children": owner_nodes,
            }
            for child in owner_nodes:
                child["parent_id"] = group_node["id"]
            group_nodes.append(group_node)

        entity_monthly = new_month_values()
        entity_previous = new_month_values()
        entity_budget = 0.0
        for child in group_nodes:
            for idx, amount in enumerate(child["monthly_actuals"]):
                entity_monthly[idx] += amount
            for idx, amount in enumerate(child["previous_year_monthly_actuals"]):
                entity_previous[idx] += amount
            entity_budget += float(child["annual_budget"] or 0.0)
        entity_metrics = metrics_from_values(entity_monthly, entity_budget, entity_previous)
        entity_node = {
            "id": next_id(),
            "parent_id": None,
            "level_number": 1,
            "level_label": "主体",
            "subject_name": entity_name,
            "formula_text": None,
            "sort_order": 0,
            "is_leaf": False,
            **entity_metrics,
            "children": group_nodes,
        }
        for child in group_nodes:
            child["parent_id"] = entity_node["id"]
        roots.append(entity_node)
    return roots


def build_subject_report_model(
    *,
    ctx: FrameworkContext,
    parsed: ParsedFramework,
    subject_rows: list[dict[str, Any]],
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    previous_year_actual_by_owner_subject: dict[tuple[str, str], list[float]],
    current_month: int,
    selected_entity: str = "",
    selected_subject_id: int | None = None,
    include_zero_rows: bool = False,
    keyword: str = "",
) -> SubjectReportModel:
    subject_scope_tree = build_subject_scope_tree(subject_rows)
    normalized_selected_subject_id, selected_subject_names = collect_subject_names_by_selected_node(
        subject_rows,
        selected_subject_id,
    )
    current_actual_by_owner: dict[str, list[float]] = defaultdict(new_month_values)
    current_budget_by_owner: dict[str, float] = defaultdict(float)
    previous_year_actual_by_owner: dict[str, list[float]] = defaultdict(new_month_values)
    for (owner_name, budget_subject), month_values in actual_by_owner.items():
        if selected_entity and entity_for_owner(owner_name, ctx) != selected_entity:
            continue
        if budget_subject not in selected_subject_names:
            continue
        for idx, amount in enumerate(month_values):
            current_actual_by_owner[owner_name][idx] += round(float(amount or 0.0), 2)
    for (owner_name, budget_subject), amount in budget_by_owner.items():
        if selected_entity and entity_for_owner(owner_name, ctx) != selected_entity:
            continue
        if budget_subject not in selected_subject_names:
            continue
        current_budget_by_owner[owner_name] += round(float(amount or 0.0), 2)
    for (owner_name, budget_subject), month_values in previous_year_actual_by_owner_subject.items():
        if selected_entity and entity_for_owner(owner_name, ctx) != selected_entity:
            continue
        if budget_subject not in selected_subject_names:
            continue
        for idx, amount in enumerate(month_values):
            previous_year_actual_by_owner[owner_name][idx] += round(float(amount or 0.0), 2)

    subject_tree = build_subject_department_tree(
        ctx=ctx,
        parsed=parsed,
        actual_by_owner=current_actual_by_owner,
        budget_by_owner=current_budget_by_owner,
        previous_year_actual_by_owner=previous_year_actual_by_owner,
        current_month=current_month,
        selected_entity=selected_entity,
    )
    zero_filtered_tree = filter_zero_metric_tree(
        subject_tree,
        include_zero_rows=include_zero_rows,
    )
    filtered_tree = filter_tree_by_keyword(zero_filtered_tree, keyword)
    return SubjectReportModel(
        selected_subject_id=normalized_selected_subject_id,
        subject_scope_tree=subject_scope_tree,
        subject_tree=filtered_tree,
    )
