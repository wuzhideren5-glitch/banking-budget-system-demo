"""Read-model assembly for the expense forecast table."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal


ScopeType = Literal["entity", "group", "owner"]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _month_cell(
    *,
    month: int,
    value: float,
    source: str,
    editable: bool = False,
    rule_configured: bool = False,
    rule_scheme: str | None = None,
    value_source: str = "manual",
    has_override: bool = False,
    system_value: float | None = None,
    override_value: float | None = None,
    override_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "month": month,
        "value": value,
        "source": source,
        "editable": editable,
        "rule_configured": rule_configured,
        "rule_scheme": rule_scheme,
        "value_source": value_source,
        "has_override": has_override,
        "system_value": system_value,
        "override_value": override_value,
        "override_reason": override_reason,
    }


def build_expense_forecast_scope_view_model(
    *,
    year: int,
    forecast_version: str,
    scope_type: ScopeType,
    scope_value: str,
    subject_rows: list[dict[str, Any]],
    owners: list[str],
    actual_cutoff_month: int,
    effective_manage_by_id: dict[int, str],
    actual_map: dict[tuple[str, str, int], float],
    annual_budget_map: dict[tuple[str, str], float],
    forecast_map: dict[tuple[str, int, int], float],
    rule_map: dict[tuple[str, int], dict[str, Any]],
    calc_result_map: dict[tuple[str, int, int], dict[str, Any]],
    override_map: dict[tuple[str, int, int], dict[str, Any]],
    annual_input_map: dict[tuple[str, int, str], float],
) -> dict[str, Any]:
    owner_set = set(owners)
    row_by_id = {int(row["id"]): row for row in subject_rows}
    children_by_parent: dict[int | None, list[int]] = defaultdict(list)
    for row in subject_rows:
        children_by_parent[row["parent_id"]].append(int(row["id"]))

    aggregated_cache: dict[int, tuple[list[dict[str, Any]], dict[str, Any], bool]] = {}

    def zero_cells(editable: bool = False) -> list[dict[str, Any]]:
        return [
            _month_cell(
                month=month,
                value=0.0,
                source="forecast",
                editable=editable,
                value_source="aggregate",
            )
            for month in range(1, 13)
        ]

    def permitted_owners(subject_name: str) -> list[str]:
        matched_ids = [int(row["id"]) for row in subject_rows if row["subject_name"] == subject_name]
        manage_department = ""
        if matched_ids:
            manage_department = effective_manage_by_id.get(matched_ids[0], "")
        if not manage_department:
            return owners
        if manage_department in owner_set:
            return [manage_department]
        return []

    def aggregate(node_id: int) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
        cached = aggregated_cache.get(node_id)
        if cached is not None:
            return cached
        row = row_by_id[node_id]
        children = children_by_parent.get(node_id, [])
        result = zero_cells(editable=False)
        row_permitted_owners = permitted_owners(row["subject_name"])
        has_visible_child = False
        owner_rule = None
        effective_owner = row_permitted_owners[0] if len(row_permitted_owners) == 1 else ""
        if effective_owner:
            owner_rule = rule_map.get((effective_owner, int(node_id)))
        self_editable = (
            scope_type == "owner"
            and bool(row["is_leaf"])
            and not row["formula_text"]
            and bool(row_permitted_owners)
        )
        annual_budget = round(
            sum(float(annual_budget_map.get((owner_name, row["subject_name"]), 0.0)) for owner_name in row_permitted_owners),
            2,
        )
        business_submission = round(
            sum(
                float(annual_input_map.get((owner_name, node_id, "business_submission"), 0.0))
                for owner_name in row_permitted_owners
            ),
            2,
        )
        capital_advice = round(
            sum(
                float(
                    annual_input_map.get(
                        (owner_name, node_id, "capital_advice"),
                        annual_budget_map.get((owner_name, row["subject_name"]), 0.0),
                    )
                )
                for owner_name in row_permitted_owners
            ),
            2,
        )

        for month in range(1, 13):
            actual_value = sum(
                float(actual_map.get((owner_name, row["subject_name"], month), 0.0))
                for owner_name in row_permitted_owners
            )
            forecast_value = sum(
                float(forecast_map.get((owner_name, node_id, month), 0.0))
                for owner_name in row_permitted_owners
            )
            override = override_map.get((effective_owner, int(node_id), month)) if effective_owner else None
            calc_result = calc_result_map.get((effective_owner, int(node_id), month)) if effective_owner else None
            editable = (
                scope_type == "owner"
                and bool(row["is_leaf"])
                and not row["formula_text"]
                and bool(row_permitted_owners)
                and month > actual_cutoff_month
                and (
                    owner_rule is None
                    or _text(owner_rule.get("scheme_code")) == "MANUAL"
                    or bool(owner_rule.get("allow_manual_override"))
                )
            )
            source = "actual" if month <= actual_cutoff_month else "forecast"
            value_source = "actual"
            if month > actual_cutoff_month:
                if not bool(row["is_leaf"]):
                    value_source = "aggregate"
                elif override is not None:
                    value_source = "override"
                else:
                    value_source = "manual"
            result[month - 1] = _month_cell(
                month=month,
                value=actual_value if source == "actual" else forecast_value,
                source=source,
                editable=editable,
                rule_configured=owner_rule is not None,
                rule_scheme=_text(owner_rule.get("scheme_code")) if owner_rule else None,
                value_source=value_source,
                has_override=override is not None,
                system_value=override["system_value"] if override else (calc_result["calc_value"] if calc_result else None),
                override_value=override["override_value"] if override else None,
                override_reason=override["override_reason"] if override else None,
            )

        for child_id in children:
            child_cells, child_metrics, child_visible = aggregate(child_id)
            has_visible_child = has_visible_child or child_visible
            if not child_visible:
                continue
            for idx in range(12):
                result[idx] = _month_cell(
                    month=result[idx]["month"],
                    value=result[idx]["value"] + child_cells[idx]["value"],
                    source=result[idx]["source"],
                    editable=False,
                    value_source="aggregate",
                )
            annual_budget = round(annual_budget + float(child_metrics["annual_budget"]), 2)
            business_submission = round(
                business_submission + float(child_metrics["business_submission"]),
                2,
            )
            capital_advice = round(capital_advice + float(child_metrics["capital_advice"]), 2)
        self_visible = bool(row_permitted_owners) and (
            bool(row["is_leaf"]) or any(abs(cell["value"]) > 1e-9 for cell in result)
        )
        visible = has_visible_child or self_visible
        metrics = {
            "annual_budget": annual_budget,
            "business_submission": business_submission,
            "capital_advice": capital_advice,
            "capital_advice_gap": round(capital_advice - business_submission, 2),
            "business_submission_editable": self_editable,
            "capital_advice_editable": self_editable,
            "rule_configured": owner_rule is not None,
            "rule_scheme": _text(owner_rule.get("scheme_code")) if owner_rule else None,
            "allow_manual_override": bool(owner_rule.get("allow_manual_override")) if owner_rule else False,
            "rule_id": int(owner_rule["id"]) if owner_rule else None,
        }
        aggregated_cache[node_id] = (result, metrics, visible)
        return result, metrics, visible

    ordered_rows: list[dict[str, Any]] = []

    def walk(parent_id: int | None) -> None:
        for node_id in children_by_parent.get(parent_id, []):
            row = row_by_id[node_id]
            cells, metrics, visible = aggregate(node_id)
            if not visible:
                continue
            total_value = round(sum(float(cell["value"]) for cell in cells), 2)
            annual_budget = round(float(metrics["annual_budget"]), 2)
            ordered_rows.append(
                {
                    "id": node_id,
                    "parent_id": row["parent_id"],
                    "level_number": row["level_number"],
                    "subject_name": row["subject_name"],
                    "formula_text": row["formula_text"],
                    "sort_order": row["sort_order"],
                    "is_leaf": bool(row["is_leaf"]),
                    "months": cells,
                    "total_value": total_value,
                    "annual_budget": annual_budget,
                    "forecast_budget_gap": round(total_value - annual_budget, 2),
                    "budget_execution_rate": round(total_value / annual_budget, 6) if annual_budget else None,
                    "business_submission": round(float(metrics["business_submission"]), 2),
                    "capital_advice": round(float(metrics["capital_advice"]), 2),
                    "capital_advice_gap": round(float(metrics["capital_advice_gap"]), 2),
                    "business_submission_editable": bool(metrics["business_submission_editable"]),
                    "capital_advice_editable": bool(metrics["capital_advice_editable"]),
                    "rule_configured": bool(metrics["rule_configured"]),
                    "rule_scheme": metrics["rule_scheme"],
                    "allow_manual_override": bool(metrics["allow_manual_override"]),
                    "rule_id": metrics["rule_id"],
                }
            )
            walk(node_id)

    walk(None)
    return {
        "year": year,
        "forecast_version": forecast_version,
        "scope_type": scope_type,
        "scope_value": scope_value,
        "actual_cutoff_month": actual_cutoff_month,
        "rows": ordered_rows,
    }


def build_expense_forecast_subject_owner_view_model(
    *,
    year: int,
    forecast_version: str,
    scope_type: ScopeType,
    scope_value: str,
    actual_cutoff_month: int,
    subject_id: int,
    subject_name: str,
    owners: list[str],
    normalized_manage_department: str,
    actual_map: dict[tuple[str, str, int], float],
    annual_budget_map: dict[tuple[str, str], float],
    forecast_map: dict[tuple[str, int, int], float],
    rule_map: dict[tuple[str, int], dict[str, Any]],
    calc_result_map: dict[tuple[str, int, int], dict[str, Any]],
    override_map: dict[tuple[str, int, int], dict[str, Any]],
    annual_input_map: dict[tuple[str, int, str], float],
) -> dict[str, Any]:
    ordered_rows: list[dict[str, Any]] = []
    for owner_name in owners:
        owner_rule = rule_map.get((owner_name, int(subject_id)))
        months: list[dict[str, Any]] = []
        for month in range(1, 13):
            actual_value = float(actual_map.get((owner_name, subject_name, month), 0.0))
            forecast_value = float(forecast_map.get((owner_name, int(subject_id), month), 0.0))
            override = override_map.get((owner_name, int(subject_id), month))
            calc_result = calc_result_map.get((owner_name, int(subject_id), month))
            source = "actual" if month <= actual_cutoff_month else "forecast"
            months.append(
                _month_cell(
                    month=month,
                    value=round(actual_value if source == "actual" else forecast_value, 2),
                    source=source,
                    editable=(
                        month > actual_cutoff_month
                        and (
                            owner_rule is None
                            or _text(owner_rule.get("scheme_code")) == "MANUAL"
                            or bool(owner_rule.get("allow_manual_override"))
                        )
                    ),
                    rule_configured=owner_rule is not None,
                    rule_scheme=_text(owner_rule.get("scheme_code")) if owner_rule else None,
                    value_source=(
                        "actual"
                        if month <= actual_cutoff_month
                        else "override"
                        if override is not None
                        else "manual"
                    ),
                    has_override=override is not None,
                    system_value=override["system_value"] if override else (calc_result["calc_value"] if calc_result else None),
                    override_value=override["override_value"] if override else None,
                    override_reason=override["override_reason"] if override else None,
                )
            )

        annual_budget = round(float(annual_budget_map.get((owner_name, subject_name), 0.0)), 2)
        business_submission = round(
            float(annual_input_map.get((owner_name, int(subject_id), "business_submission"), 0.0)),
            2,
        )
        capital_advice = round(
            float(
                annual_input_map.get(
                    (owner_name, int(subject_id), "capital_advice"),
                    annual_budget,
                )
            ),
            2,
        )
        total_value = round(sum(float(cell["value"]) for cell in months), 2)
        ordered_rows.append(
            {
                "owner_name": owner_name,
                "subject_id": int(subject_id),
                "subject_name": subject_name,
                "months": months,
                "total_value": total_value,
                "annual_budget": annual_budget,
                "forecast_budget_gap": round(total_value - annual_budget, 2),
                "budget_execution_rate": round(total_value / annual_budget, 6) if annual_budget else None,
                "business_submission": business_submission,
                "capital_advice": capital_advice,
                "capital_advice_gap": round(capital_advice - business_submission, 2),
                "business_submission_editable": owner_name == normalized_manage_department or not normalized_manage_department,
                "capital_advice_editable": owner_name == normalized_manage_department or not normalized_manage_department,
                "rule_configured": owner_rule is not None,
                "rule_scheme": _text(owner_rule.get("scheme_code")) if owner_rule else None,
                "allow_manual_override": bool(owner_rule.get("allow_manual_override")) if owner_rule else False,
                "rule_id": int(owner_rule["id"]) if owner_rule else None,
            }
        )

    return {
        "year": year,
        "forecast_version": forecast_version,
        "scope_type": scope_type,
        "scope_value": scope_value,
        "actual_cutoff_month": actual_cutoff_month,
        "subject_id": int(subject_id),
        "subject_name": subject_name,
        "rows": ordered_rows,
    }
