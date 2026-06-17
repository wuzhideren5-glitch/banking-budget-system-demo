"""Workflow helpers for expense forecast rule import preview and apply."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from app.services.expense_forecast_rule_import import (
    build_expense_forecast_rule_import_payload,
    parse_expense_forecast_rule_import_workbook,
)


class ExpenseForecastRuleImportPreviewSource(Protocol):
    async def load_subject_lookup(self) -> tuple[dict[int, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        ...

    async def load_org_product_refs_by_runtime_ref_code(self) -> dict[str, tuple[str, ...]]:
        ...

    async def load_rule_rows(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str] | None = None,
        subject_id: int | None = None,
    ) -> list[dict[str, Any]]:
        ...


class ExpenseForecastRuleImportApplySource(ExpenseForecastRuleImportPreviewSource, Protocol):
    async def save_rule(self, *, rule: Mapping[str, Any], rule_id: int | None) -> Any:
        ...


@dataclass(frozen=True)
class ExpenseForecastRuleImportPreviewWorkflowResult:
    preview_count: int
    insertable_rules: int
    updatable_rules: int
    skipped_rules: int
    error_rules: int
    items: list[dict[str, Any]]


@dataclass(frozen=True)
class ExpenseForecastRuleImportApplyWorkflowResult:
    inserted_rules: int
    updated_rules: int
    skipped_rules: int
    error_rules: int


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _scheme_display(row: Mapping[str, Any]) -> str:
    return _text(row.get("scheme_label")) or _text(row.get("scheme_code"))


def _parse_org_product_ref_label(label: str) -> tuple[str, str, str, str]:
    source_ref, _, metric_name = _text(label).partition(" ")
    parts = source_ref.split(":", 2)
    if len(parts) != 3:
        return "", "", source_ref, metric_name
    return parts[0], parts[1], parts[2], metric_name


def _org_product_variable_index(
    refs_by_runtime_ref_code: Mapping[str, tuple[str, ...] | list[str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for data_acct_code, refs in refs_by_runtime_ref_code.items():
        clean_data_acct_code = _text(data_acct_code).upper()
        if not clean_data_acct_code:
            continue
        for label in refs:
            entity_code, table_name, metric_code, metric_name = _parse_org_product_ref_label(_text(label))
            if not entity_code or not metric_code:
                continue
            rows.append(
                {
                    "data_acct_code": clean_data_acct_code,
                    "entity_code": entity_code,
                    "table_name": table_name,
                    "metric_code": metric_code,
                    "metric_name": metric_name,
                    "source_ref": f"{entity_code}:{table_name}:{metric_code}",
                }
            )
    return rows


def _org_product_lookup_error(item: Mapping[str, Any]) -> ValueError:
    raw_ref = _text(item.get("org_product_ref"))
    raw_code = _text(item.get("org_product_metric_code")) or _text(item.get("source_key"))
    return ValueError(f"机构产品指标引用不存在或不唯一: {raw_ref or raw_code or '空值'}")


def _resolve_org_product_variable(
    item: Mapping[str, Any],
    *,
    candidates: list[dict[str, str]],
) -> dict[str, Any]:
    raw_ref = _text(item.get("org_product_ref"))
    raw_metric_code = _text(item.get("org_product_metric_code"))
    if _text(item.get("source_type")) == "org_product_metric":
        raw_metric_code = raw_metric_code or _text(item.get("source_key"))
    raw_entity_code = _text(item.get("org_product_entity_code")) or _text(item.get("source_subkey"))
    raw_table_name = _text(item.get("org_product_table_name"))

    matches = candidates
    if raw_ref:
        matches = [candidate for candidate in matches if candidate["source_ref"] == raw_ref]
    if raw_metric_code:
        metric_code = raw_metric_code.upper()
        matches = [candidate for candidate in matches if candidate["metric_code"].upper() == metric_code]
    if raw_entity_code:
        entity_code = raw_entity_code.upper()
        matches = [candidate for candidate in matches if candidate["entity_code"].upper() == entity_code]
    if raw_table_name:
        matches = [candidate for candidate in matches if candidate["table_name"] == raw_table_name]
    if len(matches) != 1:
        raise _org_product_lookup_error(item)

    match = matches[0]
    resolved = {
        key: value
        for key, value in dict(item).items()
        if not key.startswith("org_product_") and key not in {"org_product_ref"}
    }
    resolved["source_type"] = "metric_tree"
    resolved["source_key"] = match["data_acct_code"]
    resolved["source_subkey"] = match["entity_code"]
    if not _text(resolved.get("variable_name")):
        resolved["variable_name"] = match["metric_name"] or match["metric_code"]
    return resolved


def resolve_org_product_variables(
    variables: list[dict[str, Any]],
    *,
    org_product_refs_by_runtime_ref_code: Mapping[str, tuple[str, ...] | list[str]] | None = None,
) -> list[dict[str, Any]]:
    candidates = _org_product_variable_index(org_product_refs_by_runtime_ref_code or {})
    confirmed_data_codes = {candidate["data_acct_code"].upper() for candidate in candidates}
    resolved_variables: list[dict[str, Any]] = []
    for item in variables:
        if (
            _text(item.get("org_product_ref"))
            or _text(item.get("org_product_metric_code"))
            or _text(item.get("source_type")) == "org_product_metric"
        ):
            resolved_variables.append(_resolve_org_product_variable(item, candidates=candidates))
        elif _text(item.get("source_type")) == "metric_tree" and _text(item.get("source_key")):
            source_key = _text(item.get("source_key")).upper()
            if source_key not in confirmed_data_codes:
                raise ValueError(f"机构及产品指标编码未在机构产品指标中确认: {source_key}")
            resolved_variables.append(dict(item))
        else:
            resolved_variables.append(dict(item))
    return resolved_variables


def _leaf_subject_id(row: Mapping[str, Any], subject_by_name: Mapping[str, list[dict[str, Any]]]) -> int | None:
    candidates = subject_by_name.get(_text(row.get("subject_name")), [])
    leaf_candidates = [item for item in candidates if bool(item.get("is_leaf"))]
    if len(leaf_candidates) != 1:
        return None
    return int(leaf_candidates[0]["id"])


def _existing_rule_keys(existing_rows: list[Mapping[str, Any]]) -> set[tuple[int, str, str, int]]:
    return {
        (
            int(item["forecast_year"]),
            _text(item["forecast_version"]),
            _text(item["owner_name"]),
            int(item["subject_id"]),
        )
        for item in existing_rows
    }


def _preview_item(
    row: Mapping[str, Any],
    *,
    action: str,
    message: str | None = None,
) -> dict[str, Any]:
    return {
        "row_number": int(row["row_number"]),
        "owner_name": _text(row.get("owner_name")),
        "subject_name": _text(row.get("subject_name")),
        "scheme_code": _scheme_display(row),
        "action": action,
        "message": message,
    }


def _rule_payload(
    row: Mapping[str, Any],
    *,
    subject_id: int,
    params: list[dict[str, Any]],
    variables: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "forecast_year": int(row["forecast_year"]),
        "forecast_version": _text(row["forecast_version"]),
        "owner_name": _text(row["owner_name"]),
        "subject_id": int(subject_id),
        "scheme_code": row["scheme_code"],
        "enabled": bool(row["enabled"]),
        "allow_manual_override": bool(row["allow_manual_override"]),
        "auto_refresh_enabled": bool(row["auto_refresh_enabled"]),
        "manual_recalc_enabled": bool(row["manual_recalc_enabled"]),
        "metric_source_priority": row["metric_source_priority"],
        "effective_from_month": int(row["effective_from_month"]),
        "effective_to_month": int(row["effective_to_month"]),
        "priority": int(row["priority"]),
        "remark": _text(row.get("remark")) or None,
        "params": params,
        "variables": variables,
    }


def preview_expense_forecast_rule_import_rows(
    rows: list[dict[str, Any]],
    *,
    subject_by_name: Mapping[str, list[dict[str, Any]]],
    existing_rows: list[dict[str, Any]],
    org_product_refs_by_runtime_ref_code: Mapping[str, tuple[str, ...] | list[str]] | None = None,
    item_limit: int = 200,
) -> dict[str, Any]:
    existing_keys = _existing_rule_keys(existing_rows)
    items: list[dict[str, Any]] = []
    insertable = 0
    updatable = 0
    errors = 0

    for row in rows:
        try:
            _, variables = build_expense_forecast_rule_import_payload(row)
            resolve_org_product_variables(
                variables,
                org_product_refs_by_runtime_ref_code=org_product_refs_by_runtime_ref_code,
            )
        except ValueError as exc:
            errors += 1
            items.append(_preview_item(row, action="error", message=str(exc)))
            continue

        subject_id = _leaf_subject_id(row, subject_by_name)
        if subject_id is None:
            errors += 1
            items.append(_preview_item(row, action="error", message="预算科目不存在或不是叶子科目"))
            continue

        key = (
            int(row["forecast_year"]),
            _text(row["forecast_version"]),
            _text(row["owner_name"]),
            int(subject_id),
        )
        action = "update" if key in existing_keys else "insert"
        if action == "update":
            updatable += 1
        else:
            insertable += 1
        items.append(_preview_item(row, action=action))

    return {
        "preview_count": len(items),
        "insertable_rules": insertable,
        "updatable_rules": updatable,
        "skipped_rules": 0,
        "error_rules": errors,
        "items": items[:item_limit],
    }


async def apply_expense_forecast_rule_import_rows(
    rows: list[dict[str, Any]],
    *,
    subject_by_name: Mapping[str, list[dict[str, Any]]],
    source: ExpenseForecastRuleImportApplySource,
    org_product_refs_by_runtime_ref_code: Mapping[str, tuple[str, ...] | list[str]] | None = None,
) -> dict[str, int]:
    inserted = 0
    updated = 0
    errors = 0

    for row in rows:
        try:
            raw_params, raw_variables = build_expense_forecast_rule_import_payload(row)
            raw_variables = resolve_org_product_variables(
                raw_variables,
                org_product_refs_by_runtime_ref_code=org_product_refs_by_runtime_ref_code,
            )
            subject_id = _leaf_subject_id(row, subject_by_name)
            if subject_id is None:
                raise ValueError("预算科目不存在或不是叶子科目")
        except ValueError:
            errors += 1
            continue

        rule = _rule_payload(
            row,
            subject_id=subject_id,
            params=raw_params,
            variables=raw_variables,
        )
        existing = await source.load_rule_rows(
            year=int(row["forecast_year"]),
            forecast_version=_text(row["forecast_version"]),
            owner_names=[_text(row["owner_name"])],
            subject_id=subject_id,
        )
        await source.save_rule(rule=rule, rule_id=int(existing[0]["id"]) if existing else None)
        if existing:
            updated += 1
        else:
            inserted += 1

    return {
        "inserted_rules": inserted,
        "updated_rules": updated,
        "skipped_rules": 0,
        "error_rules": errors,
    }


async def preview_expense_forecast_rule_import_workbook(
    *,
    raw: bytes,
    default_year: int,
    default_version: str,
    source: ExpenseForecastRuleImportPreviewSource,
) -> ExpenseForecastRuleImportPreviewWorkflowResult:
    rows = parse_expense_forecast_rule_import_workbook(
        raw,
        default_year=default_year,
        default_version=default_version,
    )
    _, subject_by_name = await source.load_subject_lookup()
    org_product_refs = await source.load_org_product_refs_by_runtime_ref_code()
    existing_rows = await source.load_rule_rows(year=default_year, forecast_version=default_version)
    preview = preview_expense_forecast_rule_import_rows(
        rows,
        subject_by_name=subject_by_name,
        existing_rows=existing_rows,
        org_product_refs_by_runtime_ref_code=org_product_refs,
    )
    return ExpenseForecastRuleImportPreviewWorkflowResult(
        preview_count=int(preview["preview_count"]),
        insertable_rules=int(preview["insertable_rules"]),
        updatable_rules=int(preview["updatable_rules"]),
        skipped_rules=int(preview["skipped_rules"]),
        error_rules=int(preview["error_rules"]),
        items=list(preview["items"]),
    )


async def apply_expense_forecast_rule_import_workbook(
    *,
    raw: bytes,
    default_year: int,
    default_version: str,
    source: ExpenseForecastRuleImportApplySource,
) -> ExpenseForecastRuleImportApplyWorkflowResult:
    rows = parse_expense_forecast_rule_import_workbook(
        raw,
        default_year=default_year,
        default_version=default_version,
    )
    _, subject_by_name = await source.load_subject_lookup()
    org_product_refs = await source.load_org_product_refs_by_runtime_ref_code()
    result = await apply_expense_forecast_rule_import_rows(
        rows,
        subject_by_name=subject_by_name,
        source=source,
        org_product_refs_by_runtime_ref_code=org_product_refs,
    )
    return ExpenseForecastRuleImportApplyWorkflowResult(
        inserted_rules=int(result["inserted_rules"]),
        updated_rules=int(result["updated_rules"]),
        skipped_rules=int(result["skipped_rules"]),
        error_rules=int(result["error_rules"]),
    )
