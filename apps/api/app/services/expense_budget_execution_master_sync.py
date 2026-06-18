"""Master-data sync helpers for expense budget execution framework imports."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
from app.core.db_paths import common_db_path
from app.services.expense_budget_execution_framework import (
    ParsedFramework,
    group_sort_key,
    should_exclude_budget_department_row,
    text,
    upsert_sync_meta,
)
from app.services.org_product_metric_runtime_snapshot import load_org_product_metric_table_rows_from_runtime_tree
from app.services.runtime_metric_refs import derive_runtime_ref_from_org_product_metric_code


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


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    keys = getattr(row, "keys", None)
    if callable(keys) and key in keys():
        return row[key]
    return row[index]


def _uses_mysql_path(path: Path | str) -> bool:
    try:
        candidate = Path(path).expanduser().resolve()
    except TypeError:
        return False
    temp_root = Path(tempfile.gettempdir()).expanduser().resolve()
    try:
        candidate.relative_to(temp_root)
        return False
    except ValueError:
        pass
    data_dir = Path(settings.data_dir).expanduser().resolve()
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    return candidate.name == "common.db"


def _mysql_sql(sql: str) -> str:
    return sql.replace("?", "%s")


async def _fetch_all_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_all(_mysql_sql(sql), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, params).fetchall()


async def _table_exists_for_path(db_path: Path, table_name: str) -> bool:
    if _uses_mysql_path(db_path):
        row = await get_pool().fetch_one(
            """
            SELECT 1 AS exists_flag
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
            LIMIT 1
            """,
            (table_name,),
        )
        return bool(row)
    with sqlite3.connect(db_path) as db:
        return bool(
            db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
        )


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
    db_path = common_db_path()
    rows: list[Any] = []
    if await _table_exists_for_path(db_path, "data_account_metric_node"):
        rows = await _fetch_all_for_path(
            db_path,
            """
            SELECT node_code, node_name, product_code, metric_table_name, value_type
            FROM data_account_metric_node
            WHERE is_active = 1
              AND runtime_account_enabled = 1
              AND COALESCE(product_code, '') <> ''
              AND COALESCE(metric_table_name, '') <> ''
            ORDER BY product_code, metric_table_name, node_code
            """,
        )
    subjects: dict[str, dict[str, Any]] = {}
    for row in rows:
        node_code = _row_value(row, "node_code", 0)
        node_name = _row_value(row, "node_name", 1)
        product_code = _row_value(row, "product_code", 2)
        table_name = _row_value(row, "metric_table_name", 3)
        value_type = _row_value(row, "value_type", 4)
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
    if subjects:
        return subjects

    if _uses_mysql_path(db_path):
        return subjects

    conn = sqlite3.connect(db_path)
    try:
        table_rows = load_org_product_metric_table_rows_from_runtime_tree(conn)
    finally:
        conn.close()
    for table_row in table_rows:
        entity_code = _normalize_metric_ref(table_row.get("entity_code"))
        table_name = text(table_row.get("table_name"))
        try:
            payload = json.loads(str(table_row.get("payload_json") or "{}"))
        except Exception:
            continue
        stack = [item for item in payload.get("metrics", []) if isinstance(item, dict)]
        while stack:
            node = stack.pop(0)
            children = node.get("children")
            if isinstance(children, list):
                stack[0:0] = [child for child in children if isinstance(child, dict)]
            subject_name = text(node.get("name"))
            metric_ref = derive_runtime_ref_from_org_product_metric_code(
                entity_code=entity_code,
                metric_code=node.get("code"),
            )
            if not metric_ref:
                for key in ("data_acct_code", "metric_node_code"):
                    candidate = _normalize_metric_ref(node.get(key))
                    if candidate.startswith(f"{entity_code}."):
                        metric_ref = candidate
                        break
            if not subject_name or not metric_ref:
                continue
            subjects.setdefault(
                subject_name,
                {
                    "metric_code": metric_ref,
                    "value_type": text(node.get("value_type")) or "金额",
                    "source": f"{entity_code}/{table_name}",
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


async def _backup_master_tables() -> Path:
    common_path = common_db_path()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = common_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    if not _uses_mysql_path(common_path):
        backup_path = backup_dir / f"common_before_expense_framework_{timestamp}.db"
        shutil.copy2(common_path, backup_path)
        return backup_path

    backup_path = backup_dir / f"mysql_dept_account_before_expense_framework_{timestamp}.json"
    dept_rows = await get_pool().fetch_all(
        """
        SELECT dept_code, dept_name, entity_name, parent_code, level, is_leaf
        FROM dept_account
        ORDER BY dept_code
        """
    )
    backup_path.write_text(
        json.dumps(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "source": "mysql.dept_account",
                "rows": dept_rows,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return backup_path


async def _apply_master_plan_rows_mysql(plan: FrameworkMasterPlan) -> None:
    async with get_pool().acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM dept_account")
                if plan.dept_rows:
                    await cur.executemany(
                        """
                        INSERT INTO dept_account(dept_code, dept_name, entity_name, parent_code, level, is_leaf)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        plan.dept_rows,
                    )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


def _apply_master_plan_rows_sqlite(plan: FrameworkMasterPlan) -> None:
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


async def _apply_master_plan_rows(plan: FrameworkMasterPlan) -> None:
    if _uses_mysql_path(common_db_path()):
        await _apply_master_plan_rows_mysql(plan)
    else:
        _apply_master_plan_rows_sqlite(plan)


async def apply_framework_master_plan(
    parsed: ParsedFramework,
    plan: FrameworkMasterPlan,
) -> FrameworkMasterApplyResult:
    backup_path = await _backup_master_tables()
    await _apply_master_plan_rows(plan)
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
