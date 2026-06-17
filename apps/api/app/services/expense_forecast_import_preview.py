"""Preview decision logic for expense forecast imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.services.expense_forecast_data_context import build_expense_forecast_effective_manage_departments
from app.services.expense_forecast_import_parser import ExpenseForecastImportParseError
from app.services.expense_forecast_import_plan import (
    ExpenseForecastImportPlanError,
    build_expense_forecast_import_plan,
    parse_expense_forecast_import_rows_for_plan,
)


@dataclass
class ExpenseForecastImportPreviewEvaluation:
    insertable_cells: int = 0
    updatable_cells: int = 0
    skipped_cells: int = 0
    error_cells: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)
    normalized_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ExpenseForecastImportPreviewWorkflowResult:
    file_name: str
    import_mode: str
    actual_cutoff_month: int
    preview_count: int
    insertable_cells: int
    updatable_cells: int
    skipped_cells: int
    error_cells: int
    items: list[dict[str, Any]]
    normalized_rows: list[dict[str, Any]]


class ExpenseForecastImportPreviewWorkflowError(ValueError):
    """Raised when an import preview request cannot be evaluated."""


class ExpenseForecastImportPreviewSource(Protocol):
    async def load_subject_lookup(self) -> tuple[dict[int, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        ...

    async def resolve_scope_owners(self, scope_type: str, scope_value: str) -> list[str]:
        ...

    async def load_actual_cutoff_month(self, year: int) -> int:
        ...

    async def load_manage_department_map(self) -> dict[str, str]:
        ...

    async def load_forecast_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], float]:
        ...

    async def load_rule_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int], dict[str, Any]]:
        ...

    async def load_annual_input_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, str], float]:
        ...

    async def load_calc_result_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], dict[str, Any]]:
        ...


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _field_label(field_name: str, month: int | None = None) -> str:
    if field_name == "month_forecast":
        return f"M{int(month or 0)}"
    if field_name == "business_submission":
        return "业务报送"
    return "资划建议"


def evaluate_expense_forecast_import_preview(
    *,
    parsed_rows: list[dict[str, Any]],
    import_mode: str,
    actual_cutoff_month: int,
    is_group_import: bool,
    scope_value: str,
    target_group_name: str,
    preview_owner_names: list[str],
    by_name: dict[str, list[dict[str, Any]]],
    selected_subject: dict[str, Any] | None,
    effective_manage_by_name: dict[str, list[str]],
    forecast_map: dict[tuple[str, int, int], float],
    rule_map: dict[tuple[str, int], dict[str, Any]],
    annual_input_map: dict[tuple[str, int, str], float],
    calc_result_map: dict[tuple[str, int, int], dict[str, Any]],
) -> ExpenseForecastImportPreviewEvaluation:
    result = ExpenseForecastImportPreviewEvaluation()

    for item in parsed_rows:
        row_no = int(item["row_number"])
        owner_name = _text(item.get("owner_name")) if is_group_import else (_text(item.get("owner_name")) or _text(scope_value))
        subject_name = _text(item["budget_subject"])
        field_name = _text(item["field_name"]) or "month_forecast"
        month = int(item["month"]) if item.get("month") is not None else None
        field_label = _text(item["field_label"]) or _field_label(field_name, month)
        value = float(item["value"])
        row_error = item.get("error")
        preview_owner_name = owner_name if is_group_import else None

        if is_group_import and not owner_name:
            result.skipped_cells += 1
            result.items.append(
                {
                    "row_number": row_no,
                    "owner_name": None,
                    "budget_subject": subject_name,
                    "field_name": field_name,
                    "field_label": field_label,
                    "month": month,
                    "value": value,
                    "action": "skipped",
                    "message": "当前行未识别到费用归属部门，已按事业群汇总/标题行忽略",
                }
            )
            continue

        if row_error:
            result.error_cells += 1
            result.items.append(
                {
                    "row_number": row_no,
                    "owner_name": preview_owner_name,
                    "budget_subject": subject_name,
                    "field_name": field_name,
                    "field_label": field_label,
                    "month": month,
                    "value": value,
                    "action": "error",
                    "message": _text(row_error),
                }
            )
            continue

        if field_name == "month_forecast" and month is not None and month <= actual_cutoff_month:
            result.skipped_cells += 1
            result.items.append(
                {
                    "row_number": row_no,
                    "owner_name": preview_owner_name,
                    "budget_subject": subject_name,
                    "field_name": "month_forecast",
                    "field_label": field_label,
                    "month": month,
                    "value": value,
                    "action": "skipped",
                    "message": "该月份已有实际数，不能导入预估",
                }
            )
            continue

        if is_group_import and owner_name not in preview_owner_names:
            result.error_cells += 1
            result.items.append(
                {
                    "row_number": row_no,
                    "owner_name": owner_name,
                    "budget_subject": subject_name,
                    "field_name": field_name,
                    "field_label": field_label,
                    "month": month,
                    "value": value,
                    "action": "error",
                    "message": f"费用归属部门“{owner_name}”不属于事业群“{target_group_name}”",
                }
            )
            continue

        if selected_subject is not None:
            matched = selected_subject
        else:
            matched_rows = by_name.get(subject_name, [])
            if not matched_rows:
                result.error_cells += 1
                result.items.append(
                    {
                        "row_number": row_no,
                        "owner_name": preview_owner_name,
                        "budget_subject": subject_name,
                        "field_name": field_name,
                        "field_label": field_label,
                        "month": month,
                        "value": value,
                        "action": "error",
                        "message": "预算科目不存在",
                    }
                )
                continue
            if len(matched_rows) > 1:
                result.error_cells += 1
                result.items.append(
                    {
                        "row_number": row_no,
                        "owner_name": preview_owner_name,
                        "budget_subject": subject_name,
                        "field_name": field_name,
                        "field_label": field_label,
                        "month": month,
                        "value": value,
                        "action": "error",
                        "message": "预算科目名称不唯一，请改为页面手工录入",
                    }
                )
                continue
            matched = matched_rows[0]

        if not bool(matched["is_leaf"]) or matched["formula_text"]:
            result.skipped_cells += 1
            result.items.append(
                {
                    "row_number": row_no,
                    "owner_name": preview_owner_name,
                    "budget_subject": subject_name,
                    "field_name": field_name,
                    "field_label": field_label,
                    "month": month,
                    "value": value,
                    "action": "skipped",
                    "message": "当前预算科目不可录入，已忽略",
                }
            )
            continue

        normalized_manage_departments = effective_manage_by_name.get(subject_name, [])
        if normalized_manage_departments and owner_name not in normalized_manage_departments:
            result.skipped_cells += 1
            result.items.append(
                {
                    "row_number": row_no,
                    "owner_name": preview_owner_name,
                    "budget_subject": subject_name,
                    "field_name": field_name,
                    "field_label": field_label,
                    "month": month,
                    "value": value,
                    "action": "skipped",
                    "message": f"该预算科目仅归口管理部门“{normalized_manage_departments[0]}”可录入，本次导入已忽略",
                }
            )
            continue

        subject_id = int(matched["id"])
        if field_name == "month_forecast":
            existing = forecast_map.get((owner_name, subject_id, int(month or 0)))
        else:
            existing = annual_input_map.get((owner_name, subject_id, field_name))

        action = "inserted"
        message = None
        if existing is not None:
            if import_mode == "append":
                action = "skipped"
                message = "追加模式下保留已有预估值"
                result.skipped_cells += 1
            else:
                action = "updated"
                result.updatable_cells += 1
        else:
            result.insertable_cells += 1

        owner_rule = rule_map.get((owner_name, subject_id), {})
        result.items.append(
            {
                "row_number": row_no,
                "owner_name": preview_owner_name,
                "budget_subject": subject_name,
                "field_name": field_name,
                "field_label": field_label,
                "month": month,
                "value": value,
                "action": action,
                "message": (
                    "将按人工覆盖导入自动预测"
                    if action != "skipped" and field_name == "month_forecast" and owner_rule.get("scheme_code") != "MANUAL"
                    else message
                ),
            }
        )
        result.normalized_rows.append(
            {
                "scope_value": owner_name,
                "subject_id": subject_id,
                "budget_subject": subject_name,
                "field_name": field_name,
                "field_label": field_label,
                "month": month,
                "value": value,
                "action": action,
                "rule_id": int(owner_rule.get("id") or 0),
                "rule_scheme": _text(owner_rule.get("scheme_code")),
                "system_value": float(calc_result_map.get((owner_name, subject_id, int(month or 0)), {}).get("calc_value", 0.0)),
            }
        )

    return result


async def build_expense_forecast_import_preview_from_source(
    *,
    file_name: str,
    raw: bytes,
    year: int,
    forecast_version: str,
    scope_type: str,
    scope_value: str,
    import_mode: str,
    group_name: str,
    compile_mode: str,
    subject_id: int | None,
    all_owner_scope_value: str,
    source: ExpenseForecastImportPreviewSource,
) -> ExpenseForecastImportPreviewWorkflowResult:
    by_id, by_name = await source.load_subject_lookup()
    try:
        import_plan = await build_expense_forecast_import_plan(
            scope_type=scope_type,  # type: ignore[arg-type]
            scope_value=scope_value,
            group_name=group_name,
            compile_mode=compile_mode,
            subject_id=subject_id,
            subjects_by_id=by_id,
            all_owner_scope_value=all_owner_scope_value,
            resolve_scope_owners=source.resolve_scope_owners,  # type: ignore[arg-type]
        )
        parsed_rows = parse_expense_forecast_import_rows_for_plan(raw=raw, plan=import_plan)
    except (ExpenseForecastImportPlanError, ExpenseForecastImportParseError) as exc:
        raise ExpenseForecastImportPreviewWorkflowError(str(exc)) from exc

    allowed_owner_names = import_plan.allowed_owner_names
    actual_cutoff_month = await source.load_actual_cutoff_month(year)
    manage_department_map = await source.load_manage_department_map()
    _effective_manage_by_id, effective_manage_by_name = build_expense_forecast_effective_manage_departments(
        list(by_id.values()),
        manage_department_map,
    )
    forecast_map = await source.load_forecast_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=allowed_owner_names,
    )
    rule_map = await source.load_rule_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=allowed_owner_names,
    )
    annual_input_map = await source.load_annual_input_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=allowed_owner_names,
    )
    calc_result_map = await source.load_calc_result_map(
        year=year,
        forecast_version=forecast_version,
        owner_names=allowed_owner_names,
    )
    preview = evaluate_expense_forecast_import_preview(
        parsed_rows=parsed_rows,
        import_mode=import_mode,
        actual_cutoff_month=actual_cutoff_month,
        is_group_import=import_plan.is_group_import,
        scope_value=_text(scope_value),
        target_group_name=import_plan.target_group_name,
        preview_owner_names=allowed_owner_names,
        by_name=by_name,
        selected_subject=import_plan.selected_subject,
        effective_manage_by_name=effective_manage_by_name,
        forecast_map=forecast_map,
        rule_map=rule_map,
        annual_input_map=annual_input_map,
        calc_result_map=calc_result_map,
    )
    return ExpenseForecastImportPreviewWorkflowResult(
        file_name=file_name,
        import_mode=import_mode,
        actual_cutoff_month=actual_cutoff_month,
        preview_count=min(len(preview.items), 200),
        insertable_cells=preview.insertable_cells,
        updatable_cells=preview.updatable_cells,
        skipped_cells=preview.skipped_cells,
        error_cells=preview.error_cells,
        items=preview.items[:200],
        normalized_rows=preview.normalized_rows,
    )
