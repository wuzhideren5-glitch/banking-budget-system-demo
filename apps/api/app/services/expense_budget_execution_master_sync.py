"""Master-data sync helpers for expense budget execution framework imports."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil
import sqlite3
from typing import Any

import aiosqlite

from app.core.db_paths import common_db_path
from app.services.expense_budget_execution_framework import (
    ParsedFramework,
    group_sort_key,
    should_exclude_budget_department_row,
    text,
    upsert_sync_meta,
)


MetricSubjectMatch = tuple[str, str, str]
DeptAccountInsert = tuple[str, str, str, str | None, int, int]


@dataclass(frozen=True)
class FrameworkMasterPlan:
    dept_rows: list[DeptAccountInsert]
    metric_subject_matches: list[MetricSubjectMatch]
    matched_subjects: int
    new_subjects: list[str]
    unmatched_existing_subjects: list[str]

    @property
    def affected_rows(self) -> int:
        return len(self.dept_rows)


@dataclass(frozen=True)
class FrameworkMasterApplyResult:
    backup_file: Path
    plan: FrameworkMasterPlan

    @property
    def affected_rows(self) -> int:
        return self.plan.affected_rows


def _build_dept_rows(parsed: ParsedFramework) -> list[DeptAccountInsert]:
    filtered_budget_departments = [
        row for row in parsed.budget_departments if not should_exclude_budget_department_row(row)
    ]
    entity_order: list[str] = []
    groups_by_entity: dict[str, list[str]] = defaultdict(list)
    owners_by_entity_group: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in filtered_budget_departments:
        if row.entity_name not in entity_order:
            entity_order.append(row.entity_name)
        if row.group_name not in groups_by_entity[row.entity_name]:
            groups_by_entity[row.entity_name].append(row.group_name)
        entity_group_key = (row.entity_name, row.group_name)
        if row.owner_name not in owners_by_entity_group[entity_group_key]:
            owners_by_entity_group[entity_group_key].append(row.owner_name)

    dept_rows: list[DeptAccountInsert] = []
    group_seq = 0
    for entity_name in entity_order:
        for group_name in sorted(groups_by_entity[entity_name], key=group_sort_key):
            group_seq += 1
            group_code = f"Y{group_seq}"
            dept_rows.append((group_code, group_name, entity_name, None, 1, 0))
            owner_names = owners_by_entity_group[(entity_name, group_name)]
            for owner_idx, owner_name in enumerate(owner_names, start=1):
                owner_code = f"{group_code}{owner_idx:02d}"
                dept_rows.append((owner_code, owner_name, entity_name, group_code, 2, 1))
    return dept_rows


def _normalize_metric_ref(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _iter_metric_nodes(metrics: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    stack = list(metrics)
    while stack:
        node = stack.pop(0)
        if not isinstance(node, dict):
            continue
        rows.append(node)
        children = node.get("children")
        if isinstance(children, list):
            stack[0:0] = [child for child in children if isinstance(child, dict)]
    return tuple(rows)


async def _load_confirmed_org_product_metric_subjects() -> dict[str, dict[str, Any]]:
    async with aiosqlite.connect(common_db_path()) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT node_code, node_name, product_code, metric_table_name, value_type
            FROM data_account_metric_node
            WHERE is_active = 1
              AND runtime_account_enabled = 1
              AND COALESCE(product_code, '') <> ''
              AND COALESCE(metric_table_name, '') <> ''
            ORDER BY product_code, metric_table_name, node_code
            """
        )
        rows = await cur.fetchall()
    subjects: dict[str, dict[str, Any]] = {}
    for node_code, node_name, product_code, table_name, value_type in rows:
        subject_name = text(node_name)
        metric_ref = _normalize_metric_ref(node_code)
        if not subject_name or not metric_ref:
            continue
        subjects.setdefault(
            subject_name,
            {
                "metric_code": metric_ref,
                "value_type": text(value_type) or "金额",
                "source": f"{text(product_code)}/{text(table_name)}",
            },
        )
    return subjects


def build_framework_master_plan_from_metric_subjects(
    parsed: ParsedFramework,
    confirmed_subjects_by_name: dict[str, dict[str, Any]],
) -> FrameworkMasterPlan:
    matched_subjects = 0
    new_subjects: list[str] = []
    metric_subject_matches: list[MetricSubjectMatch] = []
    framework_subject_names = {text(subject.budget_subject) for subject in parsed.subjects}
    for subject in parsed.subjects:
        subject_name = text(subject.budget_subject)
        existing = confirmed_subjects_by_name.get(subject_name)
        if existing is not None:
            matched_subjects += 1
            metric_subject_matches.append(
                (str(existing["metric_code"]), subject_name, str(existing.get("value_type") or "金额"))
            )
        else:
            new_subjects.append(subject_name)

    unmatched_existing_subjects = sorted(
        name for name in confirmed_subjects_by_name.keys() if name not in framework_subject_names
    )
    return FrameworkMasterPlan(
        dept_rows=_build_dept_rows(parsed),
        metric_subject_matches=metric_subject_matches,
        matched_subjects=matched_subjects,
        new_subjects=new_subjects,
        unmatched_existing_subjects=unmatched_existing_subjects,
    )


async def build_framework_master_plan(parsed: ParsedFramework) -> FrameworkMasterPlan:
    return build_framework_master_plan_from_metric_subjects(
        parsed,
        await _load_confirmed_org_product_metric_subjects(),
    )


def build_framework_master_preview_payload(
    parsed: ParsedFramework,
    plan: FrameworkMasterPlan,
) -> dict[str, Any]:
    return {
        "source_file": str(parsed.source_file),
        "framework": {
            "group_count": len({(row.entity_name, row.group_name) for row in parsed.budget_departments}),
            "owner_count": len({(row.entity_name, row.group_name, row.owner_name) for row in parsed.budget_departments}),
            "budget_department_count": len(parsed.budget_departments),
            "product_department_count": 0,
            "subject_count": len(parsed.subjects),
        },
        "master_preview": {
            "dept_rows": len(plan.dept_rows),
            "matched_subjects": plan.matched_subjects,
            "new_subjects": len(plan.new_subjects),
            "unmatched_existing_subjects": len(plan.unmatched_existing_subjects),
            "sample_new_subjects": plan.new_subjects[:10],
            "sample_unmatched_existing_subjects": plan.unmatched_existing_subjects[:10],
        },
    }


def build_framework_master_apply_payload(
    result: FrameworkMasterApplyResult,
) -> dict[str, Any]:
    plan = result.plan
    return {
        "backup_file": str(result.backup_file),
        "dept_rows": len(plan.dept_rows),
        "matched_metric_subjects": len(plan.metric_subject_matches),
        "matched_subjects": plan.matched_subjects,
        "new_subjects": len(plan.new_subjects),
        "unmatched_existing_subjects": len(plan.unmatched_existing_subjects),
        "sample_new_subjects": plan.new_subjects[:10],
        "sample_unmatched_existing_subjects": plan.unmatched_existing_subjects[:10],
    }


def _backup_common_db() -> Path:
    common_path = common_db_path()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = common_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"common_before_expense_framework_{timestamp}.db"
    shutil.copy2(common_path, backup_path)
    return backup_path


def _apply_master_plan_rows(plan: FrameworkMasterPlan) -> None:
    conn = sqlite3.connect(common_db_path())
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN")
        conn.execute("DELETE FROM dept_account")
        conn.executemany(
            """
            INSERT INTO dept_account(dept_code, dept_name, entity_name, parent_code, level, is_leaf)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            plan.dept_rows,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def apply_framework_master_plan(
    parsed: ParsedFramework,
    plan: FrameworkMasterPlan,
) -> FrameworkMasterApplyResult:
    backup_path = _backup_common_db()
    _apply_master_plan_rows(plan)
    await upsert_sync_meta(
        "master_apply",
        str(parsed.source_file),
        plan.affected_rows,
        note=(
            f"部门{len(plan.dept_rows)}行；"
            f"指标匹配{plan.matched_subjects}项；"
            f"新增指标待机构及产品维护{len(plan.new_subjects)}个"
        ),
    )
    return FrameworkMasterApplyResult(backup_file=backup_path, plan=plan)
