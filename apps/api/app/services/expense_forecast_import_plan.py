"""Request planning for expense forecast imports."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from app.services.expense_forecast_import_parser import (
    parse_expense_forecast_group_import_file,
    parse_expense_forecast_import_file,
    parse_expense_forecast_subject_import_file,
)


ScopeType = Literal["entity", "group", "owner"]
CompileMode = Literal["scope", "subject"]
ScopeOwnerResolver = Callable[[ScopeType, str], Awaitable[list[str]]]


class ExpenseForecastImportPlanError(ValueError):
    """Raised when an import request cannot be mapped to a current import contract."""


@dataclass(frozen=True)
class ExpenseForecastImportPlan:
    normalized_compile_mode: CompileMode
    is_group_import: bool
    target_group_name: str
    allowed_owner_names: list[str]
    selected_subject: dict[str, Any] | None
    scope_value: str


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_compile_mode(raw: Any) -> CompileMode:
    value = _text(raw).lower()
    if value in {"scope", "subject"}:
        return value  # type: ignore[return-value]
    return "scope"


async def build_expense_forecast_import_plan(
    *,
    scope_type: ScopeType,
    scope_value: str,
    group_name: str,
    compile_mode: str,
    subject_id: int | None,
    subjects_by_id: dict[int, dict[str, Any]],
    all_owner_scope_value: str,
    resolve_scope_owners: ScopeOwnerResolver,
) -> ExpenseForecastImportPlan:
    if scope_type != "owner":
        raise ExpenseForecastImportPlanError("费用预估导入仅支持在费用归属部门口径下执行")

    normalized_compile_mode = _normalize_compile_mode(compile_mode)
    normalized_scope_value = _text(scope_value)
    is_group_import = normalized_scope_value == all_owner_scope_value
    target_group_name = _text(group_name)
    allowed_owner_names = [normalized_scope_value]

    selected_subject: dict[str, Any] | None = None
    if normalized_compile_mode == "subject":
        if subject_id is None:
            raise ExpenseForecastImportPlanError("按预算科目导入缺少 subject_id")
        selected_subject = subjects_by_id.get(int(subject_id))
        if not selected_subject:
            raise ExpenseForecastImportPlanError("所选预算科目不存在")
        if not bool(selected_subject["is_leaf"]) or selected_subject["formula_text"]:
            raise ExpenseForecastImportPlanError("按预算科目导入仅支持选择末级叶子预算科目")

    if is_group_import:
        if not target_group_name:
            raise ExpenseForecastImportPlanError("“全部部门”导入缺少事业群参数")
        allowed_owner_names = await resolve_scope_owners("group", target_group_name)

    return ExpenseForecastImportPlan(
        normalized_compile_mode=normalized_compile_mode,
        is_group_import=is_group_import,
        target_group_name=target_group_name,
        allowed_owner_names=allowed_owner_names,
        selected_subject=selected_subject,
        scope_value=normalized_scope_value,
    )


def parse_expense_forecast_import_rows_for_plan(
    *,
    raw: bytes,
    plan: ExpenseForecastImportPlan,
) -> list[dict[str, Any]]:
    selected_subject_name = _text(plan.selected_subject["subject_name"]) if plan.selected_subject else ""
    if plan.is_group_import:
        if plan.normalized_compile_mode == "subject":
            return parse_expense_forecast_subject_import_file(
                raw,
                subject_name=selected_subject_name,
            )
        return parse_expense_forecast_group_import_file(raw, owner_names=plan.allowed_owner_names)
    if plan.normalized_compile_mode == "subject":
        return parse_expense_forecast_subject_import_file(
            raw,
            subject_name=selected_subject_name,
            default_owner_name=plan.scope_value,
        )
    return parse_expense_forecast_import_file(raw)
