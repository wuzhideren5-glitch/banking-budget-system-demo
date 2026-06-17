"""Selector context for expense budget execution report read models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.expense_budget_execution_framework import (
    FrameworkContext,
    ParsedFramework,
    build_template_scope_options,
    group_sort_key,
    list_available_entities,
    text,
)


@dataclass(frozen=True)
class ExpenseReportEntityContext:
    available_entities: list[str]
    selected_entity: str

    def payload_fields(self) -> dict[str, Any]:
        return {
            "available_entities": self.available_entities,
            "selected_entity_name": self.selected_entity,
        }


@dataclass(frozen=True)
class ExpenseReportScopeContext:
    template_scope_options: list[dict[str, str]]
    available_entities: list[str]
    available_groups: list[str]
    available_owner_departments: list[str]
    selected_entity: str
    selected_group: str
    selected_owner: str

    def payload_fields(self) -> dict[str, Any]:
        return {
            "available_entities": self.available_entities,
            "available_groups": self.available_groups,
            "available_owner_departments": self.available_owner_departments,
            "template_scope_options": self.template_scope_options,
            "selected_entity_name": self.selected_entity,
            "selected_group_name": self.selected_group,
            "selected_owner_dept": self.selected_owner,
        }

    def selected_scope_note_parts(self, *, include_permission_note: bool = False) -> list[str]:
        parts: list[str] = []
        if self.selected_entity:
            parts.append(f"当前主体筛选：{self.selected_entity}。")
        if self.selected_group:
            parts.append(f"当前事业群筛选：{self.selected_group}。")
        if self.selected_owner:
            parts.append(f"当前费用归属部门筛选：{self.selected_owner}。")
        if include_permission_note and (self.selected_entity or self.selected_group or self.selected_owner):
            parts.append("对已设置归口管理部门的预算科目，仅展示当前筛选部门范围内有权限查看的科目。")
        return parts


def build_report_entity_context(
    ctx: FrameworkContext,
    *,
    entity_name: str = "",
) -> ExpenseReportEntityContext:
    return ExpenseReportEntityContext(
        available_entities=list_available_entities(ctx),
        selected_entity=text(entity_name),
    )


def build_report_scope_context(
    ctx: FrameworkContext,
    parsed: ParsedFramework,
    *,
    entity_name: str = "",
    group_name: str = "",
    owner_dept: str = "",
) -> ExpenseReportScopeContext:
    template_scope_options = build_template_scope_options(parsed)
    selected_entity = text(entity_name)
    selected_group = text(group_name)
    selected_owner = text(owner_dept)
    available_groups = sorted(
        {
            item["group_name"]
            for item in template_scope_options
            if item["group_name"] and (not selected_entity or item["entity_name"] == selected_entity)
        },
        key=group_sort_key,
    )
    available_owner_departments = sorted(
        {
            item["owner_dept"]
            for item in template_scope_options
            if item["owner_dept"]
            and (not selected_entity or item["entity_name"] == selected_entity)
            and (not selected_group or item["group_name"] == selected_group)
        },
        key=lambda name: (len(name), name),
    )
    return ExpenseReportScopeContext(
        template_scope_options=template_scope_options,
        available_entities=list_available_entities(ctx),
        available_groups=available_groups,
        available_owner_departments=available_owner_departments,
        selected_entity=selected_entity,
        selected_group=selected_group,
        selected_owner=selected_owner,
    )
