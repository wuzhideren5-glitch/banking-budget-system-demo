"""Query-mode read model for expense budget execution reports."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.services.expense_budget_execution_framework import (
    FrameworkContext,
    default_entity_name,
    default_group_name,
    effective_manage_departments,
    entity_for_group,
    entity_for_owner,
    matches_template_scope,
    norm_key,
    subject_visible_for_scope,
)
from app.services.expense_budget_execution_metrics import month_over_month_metrics, new_month_values


@dataclass(frozen=True)
class QueryReportModel:
    rows: list[dict[str, Any]]


def _build_report_rows(
    *,
    perspective: str,
    ctx: FrameworkContext,
    actual_map: dict[tuple[str, str], list[float]],
    budget_map: dict[tuple[str, str], float],
    effective_manage_by_name: dict[str, list[str]],
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
    keyword: str,
    include_zero_rows: bool,
    current_month: int,
) -> list[dict[str, Any]]:
    keyword_text = norm_key(keyword)
    all_keys = sorted(set(actual_map.keys()) | set(budget_map.keys()), key=lambda item: (item[0], item[1]))
    rows: list[dict[str, Any]] = []
    for dimension_value, budget_subject in all_keys:
        if not subject_visible_for_scope(
            ctx=ctx,
            manage_departments=effective_manage_by_name.get(budget_subject, []),
            selected_entity=selected_entity,
            selected_group=selected_group,
            selected_owner=selected_owner,
        ):
            continue
        monthly_actuals = [round(v, 2) for v in list(actual_map.get((dimension_value, budget_subject), new_month_values()))]
        annual_budget = round(float(budget_map.get((dimension_value, budget_subject), 0.0)), 2)
        cumulative_actual = round(sum(monthly_actuals), 2)
        month_over_month, month_over_month_rate = month_over_month_metrics(monthly_actuals, current_month)
        if not include_zero_rows and cumulative_actual == 0 and annual_budget == 0:
            continue

        if perspective == "entity":
            entity_name = dimension_value
            group_name = ""
            owner_name = ""
        elif perspective == "group":
            entity_name = entity_for_group(dimension_value, ctx)
            group_name = dimension_value
            owner_name = ""
        else:
            entity_name = entity_for_owner(dimension_value, ctx)
            owner_name = dimension_value
            group_name = ctx.owner_to_group.get(owner_name, default_group_name(entity_name))

        searchable = " ".join(
            [
                perspective,
                dimension_value,
                entity_name,
                group_name,
                owner_name,
                budget_subject,
            ]
        )
        if keyword_text and keyword_text not in norm_key(searchable):
            continue

        rows.append(
            {
                "perspective": perspective,
                "dimension_value": dimension_value,
                "entity_name": entity_name,
                "group_name": group_name,
                "owner_dept": owner_name,
                "budget_subject": budget_subject,
                "monthly_actuals": monthly_actuals,
                "cumulative_actual": cumulative_actual,
                "annual_budget": annual_budget,
                "execution_rate": round(cumulative_actual / annual_budget, 6) if annual_budget else None,
                "month_over_month": month_over_month,
                "month_over_month_rate": month_over_month_rate,
            }
        )
    return rows


def _aggregate_report_maps_by_scope(
    *,
    ctx: FrameworkContext,
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
) -> tuple[
    dict[tuple[str, str], list[float]],
    dict[tuple[str, str], list[float]],
    dict[tuple[str, str], list[float]],
    dict[tuple[str, str], float],
    dict[tuple[str, str], float],
    dict[tuple[str, str], float],
]:
    actual_by_entity: dict[tuple[str, str], list[float]] = defaultdict(new_month_values)
    actual_by_group: dict[tuple[str, str], list[float]] = defaultdict(new_month_values)
    filtered_actual_by_owner: dict[tuple[str, str], list[float]] = defaultdict(new_month_values)
    budget_by_entity: dict[tuple[str, str], float] = defaultdict(float)
    budget_by_group: dict[tuple[str, str], float] = defaultdict(float)
    filtered_budget_by_owner: dict[tuple[str, str], float] = defaultdict(float)

    for (owner_name, budget_subject), month_values in actual_by_owner.items():
        if not matches_template_scope(
            ctx=ctx,
            owner_name=owner_name,
            selected_entity=selected_entity,
            selected_group=selected_group,
            selected_owner=selected_owner,
        ):
            continue
        entity_name = ctx.owner_to_entity.get(owner_name, default_entity_name())
        group_name = ctx.owner_to_group.get(owner_name, default_group_name(entity_name))
        filtered_actual_by_owner[(owner_name, budget_subject)] = [
            round(float(value or 0.0), 2) for value in month_values
        ]
        target_entity = actual_by_entity[(entity_name, budget_subject)]
        target_group = actual_by_group[(group_name, budget_subject)]
        for idx, amount in enumerate(month_values):
            numeric = round(float(amount or 0.0), 2)
            target_entity[idx] += numeric
            target_group[idx] += numeric

    for (owner_name, budget_subject), amount in budget_by_owner.items():
        if not matches_template_scope(
            ctx=ctx,
            owner_name=owner_name,
            selected_entity=selected_entity,
            selected_group=selected_group,
            selected_owner=selected_owner,
        ):
            continue
        entity_name = ctx.owner_to_entity.get(owner_name, default_entity_name())
        group_name = ctx.owner_to_group.get(owner_name, default_group_name(entity_name))
        numeric = round(float(amount or 0.0), 2)
        filtered_budget_by_owner[(owner_name, budget_subject)] += numeric
        budget_by_entity[(entity_name, budget_subject)] += numeric
        budget_by_group[(group_name, budget_subject)] += numeric

    return (
        actual_by_entity,
        actual_by_group,
        filtered_actual_by_owner,
        budget_by_entity,
        budget_by_group,
        filtered_budget_by_owner,
    )


def build_query_report_model(
    *,
    ctx: FrameworkContext,
    subject_rows: list[dict[str, Any]],
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    perspective: str,
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
    keyword: str,
    include_zero_rows: bool,
    current_month: int,
) -> QueryReportModel:
    (
        filtered_actual_by_entity,
        filtered_actual_by_group,
        filtered_actual_by_owner,
        filtered_budget_by_entity,
        filtered_budget_by_group,
        filtered_budget_by_owner,
    ) = _aggregate_report_maps_by_scope(
        ctx=ctx,
        actual_by_owner=actual_by_owner,
        budget_by_owner=budget_by_owner,
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
    )
    _effective_manage_by_id, effective_manage_by_name = effective_manage_departments(subject_rows)
    if perspective == "entity":
        actual_map = filtered_actual_by_entity
        budget_map = filtered_budget_by_entity
    elif perspective == "group":
        actual_map = filtered_actual_by_group
        budget_map = filtered_budget_by_group
    else:
        actual_map = filtered_actual_by_owner
        budget_map = filtered_budget_by_owner
    rows = _build_report_rows(
        perspective=perspective,
        ctx=ctx,
        actual_map=actual_map,
        budget_map=budget_map,
        effective_manage_by_name=effective_manage_by_name,
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
        keyword=keyword,
        include_zero_rows=include_zero_rows,
        current_month=current_month,
    )
    return QueryReportModel(rows=rows)
