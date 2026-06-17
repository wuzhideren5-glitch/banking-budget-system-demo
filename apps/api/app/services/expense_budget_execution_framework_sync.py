"""Framework preview and sync commands for expense budget execution."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.audit import write_operation_log
from app.services.expense_budget_execution_framework import (
    ParsedFramework,
    merge_framework_with_existing,
    persist_framework_snapshot,
)
from app.services.expense_budget_execution_master_sync import (
    apply_framework_master_plan,
    build_framework_master_apply_payload,
    build_framework_master_plan,
    build_framework_master_preview_payload,
)


AuditWriter = Callable[..., Awaitable[None]]


async def preview_expense_framework_sync(parsed: ParsedFramework) -> dict[str, Any]:
    merged = await merge_framework_with_existing(parsed)
    plan = await build_framework_master_plan(merged)
    return build_framework_master_preview_payload(merged, plan)


async def sync_expense_framework(
    parsed: ParsedFramework,
    *,
    apply_to_master_data: bool,
    audit_writer: AuditWriter = write_operation_log,
) -> dict[str, Any]:
    merged = await merge_framework_with_existing(parsed)
    await persist_framework_snapshot(merged)
    result: dict[str, Any] = {
        "source_file": str(merged.source_file),
        "framework_rows": {
            "budget_departments": len(merged.budget_departments),
            "product_departments": len(merged.product_departments),
            "subjects": len(merged.subjects),
        },
        "master_applied": False,
    }
    await audit_writer(
        action_type="IMPORT",
        action_desc="同步费用整体框架到内部表",
        target_table="expense_framework_*",
        affected_rows=len(merged.budget_departments) + len(merged.product_departments) + len(merged.subjects),
        after_data=result,
    )
    if apply_to_master_data:
        plan = await build_framework_master_plan(merged)
        master_apply = await apply_framework_master_plan(merged, plan)
        master_apply_payload = build_framework_master_apply_payload(master_apply)
        await audit_writer(
            action_type="UPDATE",
            action_desc="应用费用整体框架到部门主数据并校验机构及产品指标科目",
            target_table="dept_account",
            affected_rows=master_apply.affected_rows,
            after_data=master_apply_payload,
        )
        result["master_applied"] = True
        result["master_apply"] = master_apply_payload
    return result
