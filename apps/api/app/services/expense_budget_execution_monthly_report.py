"""Monthly-section read model for expense budget execution reports."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.services.expense_budget_execution_framework import (
    FrameworkContext,
    ParsedFramework,
    build_template_scope_options,
    effective_manage_departments,
    group_sort_key,
    resolve_department_scope,
    text,
)
from app.services.expense_budget_execution_metrics import metric_payload, new_month_values

BUSINESS_FORCE_OPERATING_OWNER = "资产负债管理及企划部"
BUSINESS_FORCE_OPERATING_GROUP = "资源管理及管控职能群"
BUSINESS_HIDE_SUBTOTAL_OWNERS = {"办公室", "消费者权益保护部"}
IT_OTHER_SOURCE_OWNER = "行长室"
IT_OTHER_DISPLAY_LABEL = "其他"
IT_OTHER_PARENT_SUBJECT = "进项税小计"
DAILY_MANAGED_OTHER_SOURCE_OWNER = "行长室"
DAILY_MANAGED_OTHER_DISPLAY_LABEL = "其他"
DAILY_MANAGED_OTHER_PARENT_SUBJECT = "进项税小计"
DAILY_MANAGED_OTHER_EXCLUDED_DEPARTMENTS = {"公司治理部"}
DAILY_MANAGED_OTHER_SOURCE_SUBJECT_ALIASES = {
    "全行工作会议": ["全行性会议费"],
    "办公资产摊销及折旧": ["日常资产摊销及折旧"],
}
DAILY_MANAGED_FORCE_SUBJECT_SPECS = {
    "办公室": [
        ("资产摊销及折旧", ["日常资产摊销及折旧"]),
        ("全行性会议费", ["全行性会议费"]),
    ],
    "法律合规部": [
        ("资产摊销及折旧", ["日常资产摊销及折旧"]),
        ("商标域名", ["商标域名"]),
    ],
}
DAILY_OTHER_SUBJECT_SPECS = [
    ("业务招待费", ["业务招待费"]),
    ("差旅及会议费", ["差旅及会议费"]),
    ("非IT咨询费", ["非IT咨询费"]),
    ("日常外包服务费", ["日常外包服务费"]),
    ("协会费", ["协会费"]),
    ("部门经费", ["部门经费"]),
    ("部门会议费", ["部门会议费", "部门内部会议费"]),
    ("办公杂费", ["办公杂费"]),
]


@dataclass(frozen=True)
class MonthlyReportSections:
    business_rows: list[dict[str, Any]]
    it_rows: list[dict[str, Any]]
    managed_blocks: list[dict[str, Any]]
    daily_other_columns: list[str]
    daily_other_rows: list[dict[str, Any]]


@dataclass(frozen=True)
class DailyOtherMatrix:
    columns: list[str]
    source_subjects: set[str]
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class DailyMetricSections:
    managed_blocks: list[dict[str, Any]]
    other_columns: list[str]
    other_rows: list[dict[str, Any]]


def _selected_month_values(values: list[float], current_month: int) -> list[float]:
    return [round(float(values[idx] if idx < current_month else 0.0), 2) for idx in range(12)]


def resolve_monthly_subject_source_names(
    display_subject_name: str,
    aliases: dict[str, list[str]] | None = None,
) -> list[str]:
    subject_name = text(display_subject_name)
    if not subject_name:
        return []
    return list((aliases or {}).get(subject_name, [subject_name]))


def _metric_payload_for_scope(
    *,
    owners: list[str],
    subject_names: list[str],
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    previous_year_actual_by_owner_subject: dict[tuple[str, str], list[float]],
    current_month: int,
) -> dict[str, Any]:
    monthly_actuals = new_month_values()
    previous_year_monthly_actuals = new_month_values()
    annual_budget = 0.0
    for owner_name in owners:
        for subject_name in subject_names:
            current_values = actual_by_owner.get((owner_name, subject_name), new_month_values())
            previous_values = previous_year_actual_by_owner_subject.get((owner_name, subject_name), new_month_values())
            for idx in range(12):
                monthly_actuals[idx] += float(current_values[idx] or 0.0)
                previous_year_monthly_actuals[idx] += float(previous_values[idx] or 0.0)
            annual_budget += float(budget_by_owner.get((owner_name, subject_name), 0.0) or 0.0)
    scoped_monthly_actuals = _selected_month_values(monthly_actuals, current_month)
    scoped_previous_year_monthly_actuals = _selected_month_values(previous_year_monthly_actuals, current_month)
    payload = metric_payload(
        scoped_monthly_actuals,
        annual_budget,
        round(sum(scoped_previous_year_monthly_actuals), 2),
        current_month,
    )
    payload["monthly_actuals"] = scoped_monthly_actuals
    payload["previous_year_monthly_actuals"] = scoped_previous_year_monthly_actuals
    return payload


def _metric_row_has_amount(row: dict[str, Any]) -> bool:
    return any(
        abs(float(row.get(field) or 0.0)) > 0
        for field in ("current_actual", "annual_budget", "last_year_actual", "yoy_change")
    )


def _matrix_row_has_amount(row: dict[str, Any]) -> bool:
    if abs(float(row.get("actual_total") or 0.0)) > 0 or abs(float(row.get("budget_total") or 0.0)) > 0:
        return True
    return any(abs(float(value or 0.0)) > 0 for value in list(row.get("actuals", {}).values()) + list(row.get("budgets", {}).values()))


def _current_scope_label(
    *,
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
) -> str:
    if selected_owner:
        return selected_owner
    if selected_group:
        return selected_group
    if selected_entity:
        return selected_entity
    return "全行"


def _scoped_group_owner_items(
    *,
    parsed: ParsedFramework,
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
) -> list[tuple[str, str, list[str]]]:
    items = build_template_scope_options(parsed)
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for item in items:
        entity_name = text(item["entity_name"])
        group_name = text(item["group_name"])
        owner_name = text(item["owner_dept"])
        if selected_entity and entity_name != selected_entity:
            continue
        if selected_group and group_name != selected_group:
            continue
        if selected_owner and owner_name != selected_owner:
            continue
        key = (entity_name, group_name)
        if owner_name and owner_name not in grouped[key]:
            grouped[key].append(owner_name)
    return [
        (entity_name, group_name, owners)
        for (entity_name, group_name), owners in grouped.items()
        if owners
    ]


def _subject_catalog_index(
    subject_rows: list[dict[str, Any]],
) -> tuple[
    dict[int, dict[str, Any]],
    dict[int | None, list[int]],
    dict[str, dict[str, Any]],
]:
    row_by_id = {int(row["id"]): row for row in subject_rows}
    children_by_parent: dict[int | None, list[int]] = defaultdict(list)
    row_by_name: dict[str, dict[str, Any]] = {}
    for row in subject_rows:
        row_id = int(row["id"])
        parent_id = int(row["parent_id"]) if row["parent_id"] is not None else None
        children_by_parent[parent_id].append(row_id)
        subject_name = text(row.get("subject_name"))
        if subject_name and subject_name not in row_by_name:
            row_by_name[subject_name] = row
    return row_by_id, children_by_parent, row_by_name


def _collect_descendant_subject_rows(
    subject_rows: list[dict[str, Any]],
    root_subject_name: str,
) -> list[dict[str, Any]]:
    row_by_id, children_by_parent, row_by_name = _subject_catalog_index(subject_rows)
    root_row = row_by_name.get(text(root_subject_name))
    if not root_row:
        return []
    collected: list[dict[str, Any]] = []

    def _walk(node_id: int) -> None:
        for child_id in children_by_parent.get(node_id, []):
            child_row = row_by_id[child_id]
            collected.append(child_row)
            _walk(child_id)

    _walk(int(root_row["id"]))
    collected.sort(key=lambda row: (int(row.get("sort_order") or 0), int(row["id"])))
    return collected


def _build_metric_rows_for_scope(
    *,
    scope_items: list[tuple[str, str, list[str]]],
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
    subject_specs: list[tuple[str, list[str]]],
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    previous_year_actual_by_owner_subject: dict[tuple[str, str], list[float]],
    current_month: int,
    force_subject_labels_by_owner: dict[str, set[str]] | None = None,
    hide_subject_labels_by_owner: dict[str, set[str]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total_owners = [owner_name for _entity_name, _group_name, owners in scope_items for owner_name in owners]
    scope_label = _current_scope_label(
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
    )

    def append_rows(label: str, level: int, owners: list[str]) -> None:
        for subject_label, subject_names in subject_specs:
            if subject_label in (hide_subject_labels_by_owner or {}).get(label, set()):
                continue
            payload = _metric_payload_for_scope(
                owners=owners,
                subject_names=subject_names,
                actual_by_owner=actual_by_owner,
                budget_by_owner=budget_by_owner,
                previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
                current_month=current_month,
            )
            row = {
                "label": label,
                "subject_name": subject_label,
                "level": level,
                **payload,
            }
            if _metric_row_has_amount(row):
                rows.append(row)
            elif subject_label in (force_subject_labels_by_owner or {}).get(label, set()):
                rows.append(row)

    append_rows(scope_label, 0, total_owners)
    if not selected_owner:
        for _entity_name, group_name, owners in scope_items:
            if scope_label != group_name:
                append_rows(group_name, 1, owners)
            for owner_name in owners:
                if owner_name == group_name and len(owners) == 1:
                    continue
                append_rows(owner_name, 2, [owner_name])
    return rows


def _build_metric_matrix_rows_for_scope(
    *,
    scope_items: list[tuple[str, str, list[str]]],
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
    subject_names: list[str],
    subject_source_names_by_display: dict[str, list[str]] | None = None,
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    current_month: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total_owners = [owner_name for _entity_name, _group_name, owners in scope_items for owner_name in owners]
    scope_label = _current_scope_label(
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
    )

    def build_row(label: str, level: int, owners: list[str]) -> dict[str, Any]:
        actuals: dict[str, float] = {}
        monthly_actuals_by_subject: dict[str, list[float]] = {}
        budgets: dict[str, float] = {}
        progresses: dict[str, float | None] = {}
        monthly_actuals_total = new_month_values()
        for subject_name in subject_names:
            source_subject_names = resolve_monthly_subject_source_names(
                subject_name,
                subject_source_names_by_display,
            )
            payload = _metric_payload_for_scope(
                owners=owners,
                subject_names=source_subject_names,
                actual_by_owner=actual_by_owner,
                budget_by_owner=budget_by_owner,
                previous_year_actual_by_owner_subject={},
                current_month=current_month,
            )
            actuals[subject_name] = float(payload["current_actual"])
            monthly_actuals_by_subject[subject_name] = [
                round(float(value or 0.0), 2) for value in payload.get("monthly_actuals", new_month_values())
            ]
            budgets[subject_name] = float(payload["annual_budget"])
            progresses[subject_name] = payload["budget_progress"]
            for idx, amount in enumerate(payload.get("monthly_actuals", new_month_values())):
                monthly_actuals_total[idx] += float(amount or 0.0)
        actual_total = round(sum(actuals.values()), 2)
        budget_total = round(sum(budgets.values()), 2)
        return {
            "label": label,
            "level": level,
            "actuals": actuals,
            "monthly_actuals_by_subject": monthly_actuals_by_subject,
            "budgets": budgets,
            "progresses": progresses,
            "actual_total": actual_total,
            "budget_total": budget_total,
            "budget_progress_total": round(actual_total / budget_total, 6) if budget_total else None,
            "monthly_actuals_total": [round(value, 2) for value in monthly_actuals_total],
        }

    total_row = build_row(scope_label, 0, total_owners)
    if _matrix_row_has_amount(total_row):
        rows.append(total_row)
    if not selected_owner:
        for _entity_name, group_name, owners in scope_items:
            if scope_label != group_name:
                group_row = build_row(group_name, 1, owners)
                if _matrix_row_has_amount(group_row):
                    rows.append(group_row)
            for owner_name in owners:
                if owner_name == group_name and len(owners) == 1:
                    continue
                owner_row = build_row(owner_name, 2, [owner_name])
                if _matrix_row_has_amount(owner_row):
                    rows.append(owner_row)
    return rows


def _rename_scope_summary_rows(
    *,
    rows: list[dict[str, Any]],
    source_name: str,
    total_name: str,
    subtotal_name: str,
    owner_name: str,
    selected_group: str,
    selected_owner: str,
) -> list[dict[str, Any]]:
    renamed_rows: list[dict[str, Any]] = []
    for row in rows:
        subject_name = text(row.get("subject_name"))
        if subject_name != source_name:
            renamed_rows.append(row)
            continue
        next_subject_name = owner_name
        if row["level"] == 0 and not selected_group and not selected_owner:
            next_subject_name = total_name
        elif (row["level"] == 0 and bool(selected_group) and not selected_owner) or row["level"] == 1:
            next_subject_name = subtotal_name
        renamed_rows.append({**row, "subject_name": next_subject_name})
    return renamed_rows


def _build_business_metric_rows(
    *,
    scope_items: list[tuple[str, str, list[str]]],
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
    subject_rows: list[dict[str, Any]],
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    previous_year_actual_by_owner_subject: dict[tuple[str, str], list[float]],
    current_month: int,
) -> list[dict[str, Any]]:
    marketing_subject_names = ["营销费用"] + [
        text(row.get("subject_name"))
        for row in _collect_descendant_subject_rows(subject_rows, "营销费用")
        if text(row.get("subject_name"))
    ]
    operating_subject_names = ["运营费用"] + [
        text(row.get("subject_name"))
        for row in _collect_descendant_subject_rows(subject_rows, "运营费用")
        if text(row.get("subject_name"))
    ]
    marketing_subject_names = list(dict.fromkeys(marketing_subject_names))
    operating_subject_names = list(dict.fromkeys(operating_subject_names))
    rows = _build_metric_rows_for_scope(
        scope_items=scope_items,
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
        subject_specs=[
            ("营销费用", marketing_subject_names),
            ("运营费用", operating_subject_names),
            ("费用小计", marketing_subject_names + operating_subject_names),
        ],
        actual_by_owner=actual_by_owner,
        budget_by_owner=budget_by_owner,
        previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
        current_month=current_month,
        force_subject_labels_by_owner={
            BUSINESS_FORCE_OPERATING_GROUP: {"运营费用"},
            BUSINESS_FORCE_OPERATING_OWNER: {"运营费用"},
        },
        hide_subject_labels_by_owner={
            owner_name: {"费用小计"}
            for owner_name in BUSINESS_HIDE_SUBTOTAL_OWNERS
        },
    )
    return _rename_scope_summary_rows(
        rows=rows,
        source_name="费用小计",
        total_name="业务费用合计",
        subtotal_name="业务费用小计",
        owner_name="费用小计",
        selected_group=selected_group,
        selected_owner=selected_owner,
    )


def _build_it_metric_rows(
    *,
    scope_items: list[tuple[str, str, list[str]]],
    selected_group: str,
    selected_owner: str,
    subject_rows: list[dict[str, Any]],
    effective_manage_by_id: dict[int, str],
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    previous_year_actual_by_owner_subject: dict[tuple[str, str], list[float]],
    current_month: int,
) -> list[dict[str, Any]]:
    subject_rows_by_name = {
        text(row.get("subject_name")): row
        for row in subject_rows
        if text(row.get("subject_name"))
    }
    it_descendants = _collect_descendant_subject_rows(subject_rows, "IT费用")
    it_child_subject_names = [
        text(row.get("subject_name"))
        for row in it_descendants
        if text(row.get("subject_name"))
    ]
    it_subject_names = ["IT费用", *it_child_subject_names]
    it_subject_names = list(dict.fromkeys(it_subject_names))
    it_root_row = subject_rows_by_name.get("IT费用")
    it_owner_label = (
        text(effective_manage_by_id.get(int(it_root_row["id"]), "")) if it_root_row else ""
    ) or "IT费用"
    total_owners = [owner_name for _entity_name, _group_name, owners in scope_items for owner_name in owners]
    it_scope_owners = total_owners
    it_total_payload = _metric_payload_for_scope(
        owners=it_scope_owners,
        subject_names=it_subject_names,
        actual_by_owner=actual_by_owner,
        budget_by_owner=budget_by_owner,
        previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
        current_month=current_month,
    )
    rows: list[dict[str, Any]] = []
    for row in it_descendants:
        subject_name = text(row.get("subject_name"))
        if not subject_name:
            continue
        payload = _metric_payload_for_scope(
            owners=it_scope_owners,
            subject_names=[subject_name],
            actual_by_owner=actual_by_owner,
            budget_by_owner=budget_by_owner,
            previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
            current_month=current_month,
        )
        metric_row = {
            "label": it_owner_label,
            "subject_name": subject_name,
            "level": 1,
            **payload,
        }
        if _metric_row_has_amount(metric_row):
            rows.append(metric_row)
    it_total_row = {
        "label": it_owner_label,
        "subject_name": "IT费用小计" if selected_group and not selected_owner else "IT费用合计",
        "level": 1,
        **it_total_payload,
    }
    if _metric_row_has_amount(it_total_row):
        rows.insert(0, it_total_row)
    if IT_OTHER_SOURCE_OWNER in total_owners:
        it_other_total_payload = _metric_payload_for_scope(
            owners=[IT_OTHER_SOURCE_OWNER],
            subject_names=it_child_subject_names,
            actual_by_owner=actual_by_owner,
            budget_by_owner=budget_by_owner,
            previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
            current_month=current_month,
        )
        rows.append(
            {
                "label": IT_OTHER_DISPLAY_LABEL,
                "subject_name": IT_OTHER_PARENT_SUBJECT,
                "level": 1,
                **it_other_total_payload,
            }
        )
        for subject_name in it_child_subject_names:
            payload = _metric_payload_for_scope(
                owners=[IT_OTHER_SOURCE_OWNER],
                subject_names=[subject_name],
                actual_by_owner=actual_by_owner,
                budget_by_owner=budget_by_owner,
                previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
                current_month=current_month,
            )
            rows.append(
                {
                    "label": IT_OTHER_DISPLAY_LABEL,
                    "subject_name": subject_name,
                    "level": 1,
                    **payload,
                }
            )
    return rows


def _build_daily_managed_metric_rows(
    *,
    ctx: FrameworkContext,
    daily_descendants: list[dict[str, Any]],
    daily_other_source_subjects: set[str],
    effective_manage_by_id: dict[int, str],
    total_owners: list[str],
    selected_group: str,
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    previous_year_actual_by_owner_subject: dict[tuple[str, str], list[float]],
    current_month: int,
) -> list[dict[str, Any]]:
    managed_daily_rows = [
        row
        for row in daily_descendants
        if text(row.get("subject_name")) not in daily_other_source_subjects
    ]
    managed_by_department: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in managed_daily_rows:
        subject_id = int(row["id"])
        effective_manage_department = text(effective_manage_by_id.get(subject_id, ""))
        subject_name = text(row.get("subject_name"))
        if not effective_manage_department or not subject_name:
            continue
        if "外包服务费" in subject_name or "进项税转出" in subject_name:
            continue
        managed_by_department[effective_manage_department].append(row)
    daily_managed_other_subject_rows = sorted(
        [
            row
            for manage_department, rows in managed_by_department.items()
            if manage_department not in DAILY_MANAGED_OTHER_EXCLUDED_DEPARTMENTS
            for row in rows
        ],
        key=lambda item: (int(item.get("sort_order") or 0), int(item["id"])),
    )
    daily_managed_other_subject_names = list(
        dict.fromkeys(
            text(row.get("subject_name"))
            for row in daily_managed_other_subject_rows
            if text(row.get("subject_name"))
        )
    )

    managed_departments_by_group: dict[str, list[str]] = defaultdict(list)
    for manage_department in managed_by_department.keys():
        _entity_name, resolved_group_name, _owner_name = resolve_department_scope(
            ctx=ctx,
            department_name=manage_department,
        )
        group_name = resolved_group_name or selected_group or "未分组"
        if manage_department not in managed_departments_by_group[group_name]:
            managed_departments_by_group[group_name].append(manage_department)

    rows: list[dict[str, Any]] = []
    for group_name in sorted(managed_departments_by_group.keys(), key=group_sort_key):
        group_subject_names: list[str] = []
        group_department_rows: list[dict[str, Any]] = []
        for manage_department in sorted(managed_departments_by_group[group_name], key=lambda name: (len(name), name)):
            subject_entries = sorted(
                managed_by_department[manage_department],
                key=lambda item: (int(item.get("sort_order") or 0), int(item["id"])),
            )
            managed_subject_names: list[str] = []
            emitted_subject_labels: set[str] = set()
            for row in subject_entries:
                subject_name = text(row.get("subject_name"))
                if not subject_name:
                    continue
                managed_subject_names.append(subject_name)
                if subject_name not in group_subject_names:
                    group_subject_names.append(subject_name)
                payload = _metric_payload_for_scope(
                    owners=total_owners,
                    subject_names=[subject_name],
                    actual_by_owner=actual_by_owner,
                    budget_by_owner=budget_by_owner,
                    previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
                    current_month=current_month,
                )
                metric_row = {
                    "label": manage_department,
                    "subject_name": subject_name,
                    "level": 1,
                    **payload,
                }
                if _metric_row_has_amount(metric_row):
                    group_department_rows.append(metric_row)
                    emitted_subject_labels.add(subject_name)
            for display_subject_name, source_subject_names in DAILY_MANAGED_FORCE_SUBJECT_SPECS.get(manage_department, []):
                if display_subject_name in emitted_subject_labels:
                    continue
                payload = _metric_payload_for_scope(
                    owners=total_owners,
                    subject_names=source_subject_names,
                    actual_by_owner=actual_by_owner,
                    budget_by_owner=budget_by_owner,
                    previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
                    current_month=current_month,
                )
                metric_row = {
                    "label": manage_department,
                    "subject_name": display_subject_name,
                    "level": 1,
                    **payload,
                }
                group_department_rows.append(metric_row)
                emitted_subject_labels.add(display_subject_name)
                for source_subject_name in source_subject_names:
                    if source_subject_name not in managed_subject_names:
                        managed_subject_names.append(source_subject_name)
                    if source_subject_name not in group_subject_names:
                        group_subject_names.append(source_subject_name)
            subtotal_payload = _metric_payload_for_scope(
                owners=total_owners,
                subject_names=managed_subject_names,
                actual_by_owner=actual_by_owner,
                budget_by_owner=budget_by_owner,
                previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
                current_month=current_month,
            )
            subtotal_row = {
                "label": manage_department,
                "subject_name": "费用小计",
                "level": 1,
                **subtotal_payload,
            }
            if managed_subject_names and _metric_row_has_amount(subtotal_row):
                group_department_rows.append(subtotal_row)
        group_payload = _metric_payload_for_scope(
            owners=total_owners,
            subject_names=group_subject_names,
            actual_by_owner=actual_by_owner,
            budget_by_owner=budget_by_owner,
            previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
            current_month=current_month,
        )
        group_row = {
            "label": group_name,
            "subject_name": "日常费用合计",
            "level": 0,
            **group_payload,
        }
        if group_subject_names and _metric_row_has_amount(group_row):
            rows.append(group_row)
        rows.extend(group_department_rows)
    if DAILY_MANAGED_OTHER_SOURCE_OWNER in total_owners:
        other_total_subject_names = [
            source_subject
            for display_subject_name in daily_managed_other_subject_names
            for source_subject in resolve_monthly_subject_source_names(
                display_subject_name,
                DAILY_MANAGED_OTHER_SOURCE_SUBJECT_ALIASES,
            )
        ]
        other_total_payload = _metric_payload_for_scope(
            owners=[DAILY_MANAGED_OTHER_SOURCE_OWNER],
            subject_names=other_total_subject_names,
            actual_by_owner=actual_by_owner,
            budget_by_owner=budget_by_owner,
            previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
            current_month=current_month,
        )
        rows.append(
            {
                "label": DAILY_MANAGED_OTHER_DISPLAY_LABEL,
                "subject_name": DAILY_MANAGED_OTHER_PARENT_SUBJECT,
                "level": 1,
                **other_total_payload,
            }
        )
        for display_subject_name in daily_managed_other_subject_names:
            source_subject_names = resolve_monthly_subject_source_names(
                display_subject_name,
                DAILY_MANAGED_OTHER_SOURCE_SUBJECT_ALIASES,
            )
            payload = _metric_payload_for_scope(
                owners=[DAILY_MANAGED_OTHER_SOURCE_OWNER],
                subject_names=source_subject_names,
                actual_by_owner=actual_by_owner,
                budget_by_owner=budget_by_owner,
                previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
                current_month=current_month,
            )
            rows.append(
                {
                    "label": DAILY_MANAGED_OTHER_DISPLAY_LABEL,
                    "subject_name": display_subject_name,
                    "level": 1,
                    **payload,
                }
            )
    return rows


def _build_daily_topic_metric_blocks(
    *,
    scope_items: list[tuple[str, str, list[str]]],
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
    daily_descendants: list[dict[str, Any]],
    subject_rows_by_name: dict[str, dict[str, Any]],
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    previous_year_actual_by_owner_subject: dict[tuple[str, str], list[float]],
    current_month: int,
) -> list[dict[str, Any]]:
    tax_subject_names = sorted(
        {
            text(row.get("subject_name"))
            for row in daily_descendants
            if "进项税转出" in text(row.get("subject_name"))
        },
        key=lambda name: (
            int(subject_rows_by_name.get(name, {}).get("sort_order") or 0),
            name,
        ),
    )
    tax_rows = _build_metric_rows_for_scope(
        scope_items=scope_items,
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
        subject_specs=[("其他进项税转出", tax_subject_names)],
        actual_by_owner=actual_by_owner,
        budget_by_owner=budget_by_owner,
        previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
        current_month=current_month,
    )
    tax_rows = _rename_scope_summary_rows(
        rows=tax_rows,
        source_name="其他进项税转出",
        total_name="其他进项税转出合计",
        subtotal_name="其他进项税转出小计",
        owner_name="其他进项税转出",
        selected_group=selected_group,
        selected_owner=selected_owner,
    )

    return [
        {"title": "3.1.3 其他进项税转出", "rows": tax_rows},
    ]


def _build_daily_other_matrix(
    *,
    scope_items: list[tuple[str, str, list[str]]],
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    current_month: int,
) -> DailyOtherMatrix:
    columns = [display_name for display_name, _source_names in DAILY_OTHER_SUBJECT_SPECS]
    source_subjects = {
        source_name
        for _display_name, source_names in DAILY_OTHER_SUBJECT_SPECS
        for source_name in source_names
    }
    rows = _build_metric_matrix_rows_for_scope(
        scope_items=scope_items,
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
        subject_names=columns,
        subject_source_names_by_display=dict(DAILY_OTHER_SUBJECT_SPECS),
        actual_by_owner=actual_by_owner,
        budget_by_owner=budget_by_owner,
        current_month=current_month,
    )
    return DailyOtherMatrix(columns=columns, source_subjects=source_subjects, rows=rows)


def _build_daily_managed_blocks(
    *,
    managed_rows: list[dict[str, Any]],
    topic_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocks = [
        {"title": "3.1日常费用-分解至归口部门", "rows": managed_rows},
        *topic_blocks,
    ]
    return [block for block in blocks if block["rows"]]


def _build_daily_metric_sections(
    *,
    ctx: FrameworkContext,
    scope_items: list[tuple[str, str, list[str]]],
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
    subject_rows: list[dict[str, Any]],
    subject_rows_by_name: dict[str, dict[str, Any]],
    effective_manage_by_id: dict[int, str],
    total_owners: list[str],
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    previous_year_actual_by_owner_subject: dict[tuple[str, str], list[float]],
    current_month: int,
) -> DailyMetricSections:
    daily_other_matrix = _build_daily_other_matrix(
        scope_items=scope_items,
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
        actual_by_owner=actual_by_owner,
        budget_by_owner=budget_by_owner,
        current_month=current_month,
    )
    daily_descendants = _collect_descendant_subject_rows(subject_rows, "日常费用")
    managed_block_rows = _build_daily_managed_metric_rows(
        ctx=ctx,
        daily_descendants=daily_descendants,
        daily_other_source_subjects=daily_other_matrix.source_subjects,
        effective_manage_by_id=effective_manage_by_id,
        total_owners=total_owners,
        selected_group=selected_group,
        actual_by_owner=actual_by_owner,
        budget_by_owner=budget_by_owner,
        previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
        current_month=current_month,
    )
    daily_topic_blocks = _build_daily_topic_metric_blocks(
        scope_items=scope_items,
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
        daily_descendants=daily_descendants,
        subject_rows_by_name=subject_rows_by_name,
        actual_by_owner=actual_by_owner,
        budget_by_owner=budget_by_owner,
        previous_year_actual_by_owner_subject=previous_year_actual_by_owner_subject,
        current_month=current_month,
    )
    managed_blocks = _build_daily_managed_blocks(
        managed_rows=managed_block_rows,
        topic_blocks=daily_topic_blocks,
    )
    return DailyMetricSections(
        managed_blocks=managed_blocks,
        other_columns=daily_other_matrix.columns,
        other_rows=daily_other_matrix.rows,
    )


def build_monthly_report_sections(
    *,
    ctx: FrameworkContext,
    parsed: ParsedFramework,
    subject_rows: list[dict[str, Any]],
    actual_by_owner: dict[tuple[str, str], list[float]],
    budget_by_owner: dict[tuple[str, str], float],
    previous_year_actual_by_owner_subject: dict[tuple[str, str], list[float]],
    business_actual_by_owner: dict[tuple[str, str], list[float]] | None = None,
    business_previous_year_actual_by_owner_subject: dict[tuple[str, str], list[float]] | None = None,
    current_month: int,
    selected_entity: str,
    selected_group: str,
    selected_owner: str,
) -> MonthlyReportSections:
    business_actuals = business_actual_by_owner or actual_by_owner
    business_previous_actuals = business_previous_year_actual_by_owner_subject or previous_year_actual_by_owner_subject
    scope_items = _scoped_group_owner_items(
        parsed=parsed,
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
    )
    effective_manage_by_id, _effective_manage_by_name = effective_manage_departments(subject_rows)
    subject_rows_by_name = {
        text(row.get("subject_name")): row
        for row in subject_rows
        if text(row.get("subject_name"))
    }
    business_rows = _build_business_metric_rows(
        scope_items=scope_items,
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
        subject_rows=subject_rows,
        actual_by_owner=business_actuals,
        budget_by_owner=budget_by_owner,
        previous_year_actual_by_owner_subject=business_previous_actuals,
        current_month=current_month,
    )

    total_owners = [owner_name for _entity_name, _group_name, owners in scope_items for owner_name in owners]
    it_rows = _build_it_metric_rows(
        scope_items=scope_items,
        selected_group=selected_group,
        selected_owner=selected_owner,
        subject_rows=subject_rows,
        effective_manage_by_id=effective_manage_by_id,
        actual_by_owner=business_actuals,
        budget_by_owner=budget_by_owner,
        previous_year_actual_by_owner_subject=business_previous_actuals,
        current_month=current_month,
    )

    daily_sections = _build_daily_metric_sections(
        ctx=ctx,
        scope_items=scope_items,
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
        subject_rows=subject_rows,
        subject_rows_by_name=subject_rows_by_name,
        effective_manage_by_id=effective_manage_by_id,
        total_owners=total_owners,
        actual_by_owner=business_actuals,
        budget_by_owner=budget_by_owner,
        previous_year_actual_by_owner_subject=business_previous_actuals,
        current_month=current_month,
    )

    return MonthlyReportSections(
        business_rows=business_rows,
        it_rows=it_rows,
        managed_blocks=daily_sections.managed_blocks,
        daily_other_columns=daily_sections.other_columns,
        daily_other_rows=daily_sections.other_rows,
    )
