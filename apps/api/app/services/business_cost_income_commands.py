"""Business cost-income ratio write commands and admin configuration service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import app.core.aiosqlite_compat as aiosqlite
from app.core.db_paths import budget_db_path, common_db_path
from app.services.business_cost_income_derived import (
    effective_bcir_item_entry_mode,
)
from app.services.business_cost_income_ratio import (
    amount_unit_meta,
    ensure_business_cost_income_tables,
    load_business_cost_income_indicators,
    load_business_cost_income_items,
    norm_dim,
    parse_year_month,
)
from app.services.runtime_metric_refs import (
    derive_runtime_ref_from_org_product_metric_code,
    load_confirmed_org_product_runtime_ref_codes,
)


VALUE_MODES = {"tree", "self", "self_and_tree"}
INDICATOR_FORMATS = {"ratio", "percent", "number"}
SOURCE_FIELDS = {"actual", "budget"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_product_code(value: str | None) -> str:
    return str(value or "").strip().upper()


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip()


def _normalize_value_mode(value: str | None, *, default: str = "tree") -> str:
    normalized = _normalize_text(value).lower() or default
    if normalized not in VALUE_MODES:
        raise ValueError(f"value_mode 不支持: {normalized}")
    return normalized


def _normalize_indicator_format(value: str | None) -> str:
    normalized = _normalize_text(value).lower()
    if normalized not in INDICATOR_FORMATS:
        raise ValueError(f"format 不支持: {normalized}")
    return normalized


def _normalize_manual_entry_mode(value: str | None) -> str:
    normalized = _normalize_text(value).lower() or "disabled"
    if normalized not in {"disabled", "manual", "manual_preferred"}:
        raise ValueError(f"manual_entry_mode 不支持: {normalized}")
    return normalized


def _normalize_indicator_topic_metric_node_code(value: str | None, *, product_code: str = "") -> str | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    _ = product_code
    return normalized


def _normalize_org_product_item_identity(
    *,
    org_product_ref: str | None = None,
    org_product_entity_code: str | None = None,
    org_product_table_name: str | None = None,
    org_product_metric_code: str | None = None,
    org_product_metric_name: str | None = None,
    product_code: str = "",
) -> dict[str, str]:
    ref = _normalize_text(org_product_ref)
    entity_code = _normalize_text(org_product_entity_code).upper()
    table_name = _normalize_text(org_product_table_name)
    metric_code = _normalize_text(org_product_metric_code).upper()
    metric_name = _normalize_text(org_product_metric_name)
    if ref:
        parts = ref.split(":", 2)
        if len(parts) == 3:
            entity_code = entity_code or parts[0].strip().upper()
            table_name = table_name or parts[1].strip()
            metric_code = metric_code or parts[2].strip().upper()
    elif entity_code and table_name and metric_code:
        ref = f"{entity_code}:{table_name}:{metric_code}"
    _ = product_code
    return {
        "org_product_ref": ref,
        "org_product_entity_code": entity_code,
        "org_product_table_name": table_name,
        "org_product_metric_code": metric_code,
        "org_product_metric_name": metric_name,
    }


def _runtime_ref_from_org_product_item_identity(identity: dict[str, str]) -> str:
    return derive_runtime_ref_from_org_product_metric_code(
        entity_code=identity.get("org_product_entity_code", ""),
        metric_code=identity.get("org_product_metric_code", ""),
    )


def _item_from_row(row: Any) -> dict[str, Any]:
    return {
        "id": int(row[0]),
        "product_code": str(row[1] or ""),
        "section": str(row[2]),
        "name": str(row[3]),
        "parent_id": int(row[4]) if row[4] is not None else None,
        "display_group": int(row[5] or 0) == 1,
        "data_acct_code": str(row[6] or ""),
        "org_product_ref": str(row[7] or ""),
        "org_product_entity_code": str(row[8] or ""),
        "org_product_table_name": str(row[9] or ""),
        "org_product_metric_code": str(row[10] or ""),
        "org_product_metric_name": str(row[11] or ""),
        "manual_entry_mode": str(row[12] or "disabled"),
        "value_mode": str(row[13] or "tree"),
        "sort_order": int(row[14] or 0),
        "enabled": int(row[15] or 0) == 1,
    }


def _indicator_from_row(row: Any) -> dict[str, Any]:
    return {
        "id": int(row[0]),
        "product_code": str(row[1] or ""),
        "name": str(row[2]),
        "parent_id": int(row[3]) if row[3] is not None else None,
        "display_group": int(row[4] or 0) == 1,
        "topic_metric_node_code": str(row[5] or "") or None,
        "numerator_section": str(row[6]),
        "numerator_item_id": int(row[7]),
        "numerator_value_mode": str(row[8] or "tree"),
        "denominator_section": str(row[9]),
        "denominator_item_id": int(row[10]),
        "denominator_value_mode": str(row[11] or "tree"),
        "format": str(row[12]),
        "annualize": int(row[13] or 0) == 1,
        "sort_order": int(row[14] or 0),
        "enabled": int(row[15] or 0) == 1,
    }


async def _ensure_runtime_metric_reference(
    data_acct_code: str,
    *,
    product_code: str,
) -> tuple[str, str]:
    normalized_code = _normalize_text(data_acct_code).upper()
    if not normalized_code:
        raise ValueError("普通细项必须选择机构及产品指标编码")
    async with aiosqlite.connect(common_db_path()) as cdb:
        await cdb.execute("PRAGMA foreign_keys = ON")
        confirmed_codes = await load_confirmed_org_product_runtime_ref_codes(cdb)
        if normalized_code not in confirmed_codes:
            raise ValueError("所选指标未在机构及产品指标主表中确认")
        cur = await cdb.execute(
            """
            SELECT d.data_acct_code, d.data_acct_name, COALESCE(b.scope_code, '')
            FROM data_account d
            LEFT JOIN data_account_metric_binding b
              ON b.data_acct_code = d.data_acct_code AND b.is_active = 1
            WHERE d.data_acct_code = ?
            LIMIT 1
            """,
            (normalized_code,),
        )
        row = await cur.fetchone()
    if row is None:
        raise ValueError("所选机构及产品指标编码不存在")
    scope_code = str(row[2] or "").strip().upper()
    if product_code and scope_code and scope_code not in {product_code, "CORP"}:
        raise ValueError("所选机构及产品指标编码不属于当前产品范围")
    return str(row[0]), str(row[1] or "").strip()


async def _ensure_item_reference(
    db: aiosqlite.Connection,
    *,
    section: str,
    item_id: int,
    label: str,
    product_code: str | None = None,
) -> dict[str, Any]:
    cur = await db.execute(
        """
        SELECT id, product_code, section, name, parent_id, display_group, data_acct_code,
               org_product_ref, org_product_entity_code, org_product_table_name,
               org_product_metric_code, org_product_metric_name,
               manual_entry_mode, value_mode, sort_order, enabled
        FROM business_cost_income_item
        WHERE id = ?
        """,
        (int(item_id),),
    )
    row = await cur.fetchone()
    if row is None:
        raise ValueError(f"{label}细项不存在")
    item = _item_from_row(row)
    if item["section"] != str(section):
        raise ValueError(f"{label}细项不属于所选分区")
    if product_code is not None and item["product_code"] != _normalize_product_code(product_code):
        raise ValueError(f"{label}细项不属于当前产品模板")
    return item


async def _replace_source_mappings(
    db: aiosqlite.Connection,
    *,
    item_id: int,
    data_acct_code: str,
    enabled: bool,
) -> None:
    await db.execute("DELETE FROM business_cost_income_source_mapping WHERE item_id = ?", (int(item_id),))
    if not data_acct_code:
        return
    for field in SOURCE_FIELDS:
        await db.execute(
            """
            INSERT INTO business_cost_income_source_mapping(
              item_id, field, data_acct_code, agg_method, filters_json, enabled
            ) VALUES (?, ?, ?, 'sum', '{}', ?)
            """,
            (int(item_id), field, data_acct_code, 1 if enabled else 0),
        )


async def list_business_cost_income_item_configs(year: int, *, product_code: str | None = None) -> list[dict[str, Any]]:
    await ensure_business_cost_income_tables(year)
    normalized_product = _normalize_product_code(product_code)
    async with aiosqlite.connect(budget_db_path(year)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        items = await load_business_cost_income_items(db, product_code=normalized_product)
    parent_ids = {int(item["parent_id"]) for item in items if item.get("parent_id") is not None}
    return [
        {
            "id": int(item["id"]),
            "product_code": str(item["product_code"] or ""),
            "section": str(item["section"]),
            "name": str(item["name"]),
            "parent_id": item.get("parent_id"),
            "display_group": bool(item.get("display_group")),
            "data_acct_code": str(item.get("data_acct_code") or ""),
            "org_product_ref": str(item.get("org_product_ref") or ""),
            "org_product_entity_code": str(item.get("org_product_entity_code") or ""),
            "org_product_table_name": str(item.get("org_product_table_name") or ""),
            "org_product_metric_code": str(item.get("org_product_metric_code") or ""),
            "org_product_metric_name": str(item.get("org_product_metric_name") or ""),
            "manual_entry_mode": str(item.get("manual_entry_mode") or "disabled"),
            "value_mode": str(item.get("value_mode") or "tree"),
            "sort_order": int(item["sort_order"]),
            "enabled": item["enabled"] == 1,
            "entry_mode": effective_bcir_item_entry_mode(
                str(item["section"]),
                str(item["name"]),
                has_children=int(item["id"]) in parent_ids,
                manual_entry_mode=str(item.get("manual_entry_mode") or "disabled"),
            ),
        }
        for item in items
    ]


async def list_business_cost_income_indicator_configs(
    year: int,
    *,
    product_code: str | None = None,
) -> list[dict[str, Any]]:
    await ensure_business_cost_income_tables(year)
    normalized_product = _normalize_product_code(product_code)
    async with aiosqlite.connect(budget_db_path(year)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        indicators = await load_business_cost_income_indicators(db, product_code=normalized_product)
    return [
        {
            "id": int(indicator["id"]),
            "product_code": str(indicator["product_code"] or ""),
            "name": str(indicator["name"]),
            "parent_id": indicator.get("parent_id"),
            "display_group": bool(indicator.get("display_group")),
            "topic_metric_node_code": indicator.get("topic_metric_node_code"),
            "numerator_section": str(indicator["numerator_section"]),
            "numerator_item_id": int(indicator["numerator_item_id"]),
            "numerator_value_mode": str(indicator.get("numerator_value_mode") or "tree"),
            "denominator_section": str(indicator["denominator_section"]),
            "denominator_item_id": int(indicator["denominator_item_id"]),
            "denominator_value_mode": str(indicator.get("denominator_value_mode") or "tree"),
            "format": str(indicator["format"]),
            "annualize": bool(indicator.get("annualize")),
            "sort_order": int(indicator["sort_order"]),
            "enabled": indicator["enabled"] == 1,
        }
        for indicator in indicators
    ]


async def upsert_business_cost_income_value(
    *,
    year_month: str,
    entity_name: str,
    group_name: str | None,
    product_code: str | None,
    amount_unit: str,
    item_section: str,
    item_id: int,
    field: str,
    value: float,
) -> dict[str, Any]:
    year, month = parse_year_month(year_month)
    entity = norm_dim(entity_name)
    if not entity:
        raise ValueError("主体不能为空")
    group = norm_dim(group_name)
    product = norm_dim(product_code)
    _label, divisor = amount_unit_meta(amount_unit)
    stored_value = float(value or 0.0) * divisor
    now = _iso_now()

    await ensure_business_cost_income_tables(year)
    async with aiosqlite.connect(budget_db_path(year)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        item_row = await _ensure_item_reference(db, section=item_section, item_id=int(item_id), label="录入")
        has_children = (
            await (
                await db.execute(
                    """
                    SELECT 1
                    FROM business_cost_income_item
                    WHERE parent_id = ?
                    LIMIT 1
                    """,
                    (int(item_id),),
                )
            ).fetchone()
        ) is not None
        entry_mode = effective_bcir_item_entry_mode(
            str(item_section),
            str(item_row["name"]),
            has_children=has_children,
            manual_entry_mode=str(item_row.get("manual_entry_mode") or "disabled"),
        )
        if entry_mode not in {"manual", "manual_preferred"}:
            raise ValueError(f"「{item_row['name']}」为自动计算项，不可手工录入")
        await db.execute(
            """
            INSERT INTO business_cost_income_value (
              year, month, entity_name, group_name, product_code,
              item_section, item_id, field, value, update_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (
              year, month,
              entity_name, group_name, product_code,
              item_section, item_id, field
            ) DO UPDATE SET value = excluded.value, update_time = excluded.update_time
            """,
            (
                year,
                month,
                entity,
                group,
                product,
                item_section,
                int(item_id),
                field,
                stored_value,
                now,
            ),
        )
        await db.commit()

    return {
        "updated": True,
        "after_data": {
            "year_month": year_month,
            "year": year,
            "month": month,
            "entity_name": entity,
            "group_name": group,
            "product_code": product,
            "amount_unit": amount_unit,
            "item_section": item_section,
            "item_id": int(item_id),
            "field": field,
            "input_value": float(value or 0.0),
            "stored_value": stored_value,
            "update_time": now,
        },
    }


async def create_business_cost_income_item(
    *,
    year: int,
    product_code: str | None = None,
    section: str,
    name: str,
    parent_id: int | None,
    display_group: bool = False,
    data_acct_code: str | None = None,
    org_product_ref: str | None = None,
    org_product_entity_code: str | None = None,
    org_product_table_name: str | None = None,
    org_product_metric_code: str | None = None,
    org_product_metric_name: str | None = None,
    manual_entry_mode: str = "disabled",
    value_mode: str = "tree",
    enabled: bool,
) -> dict[str, Any]:
    now = _iso_now()
    normalized_product = _normalize_product_code(product_code)
    section = str(section)
    item_name = _normalize_text(name)
    normalized_manual_entry_mode = _normalize_manual_entry_mode(manual_entry_mode)
    normalized_value_mode = _normalize_value_mode(value_mode)
    normalized_data_acct_code = ""
    org_product_identity = _normalize_org_product_item_identity(
        org_product_ref=org_product_ref,
        org_product_entity_code=org_product_entity_code,
        org_product_table_name=org_product_table_name,
        org_product_metric_code=org_product_metric_code,
        org_product_metric_name=org_product_metric_name,
        product_code=normalized_product,
    )
    if display_group:
        if not item_name:
            raise ValueError("展示分组名称不能为空")
        org_product_identity = _normalize_org_product_item_identity(product_code=normalized_product)
    elif _runtime_ref_from_org_product_item_identity(org_product_identity):
        normalized_data_acct_code, item_name = await _ensure_runtime_metric_reference(
            _runtime_ref_from_org_product_item_identity(org_product_identity),
            product_code=normalized_product,
        )
        if org_product_identity.get("org_product_metric_name"):
            item_name = org_product_identity["org_product_metric_name"]
    elif _normalize_text(data_acct_code):
        normalized_data_acct_code, item_name = await _ensure_runtime_metric_reference(
            str(data_acct_code or ""),
            product_code=normalized_product,
        )
        if org_product_identity.get("org_product_metric_name"):
            item_name = org_product_identity["org_product_metric_name"]
    else:
        org_product_identity = _normalize_org_product_item_identity(product_code=normalized_product)
    await ensure_business_cost_income_tables(year)

    async with aiosqlite.connect(budget_db_path(year)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        if parent_id is not None:
            parent_item = await _ensure_item_reference(
                db,
                section=section,
                item_id=int(parent_id),
                label="父级",
                product_code=normalized_product,
            )
            if parent_item["display_group"] is False and not display_group:
                # 允许挂到任意父级，只保留模板与分区校验
                pass
        cur = await db.execute(
            """
            SELECT COALESCE(MAX(sort_order), -1) + 1
            FROM business_cost_income_item
            WHERE product_code = ? AND section = ? AND parent_id IS ?
            """,
            (normalized_product, section, parent_id),
        )
        sort_order = int((await cur.fetchone())[0])
        await db.execute(
            """
            INSERT INTO business_cost_income_item(
              product_code, section, name, parent_id, display_group, data_acct_code,
              org_product_ref, org_product_entity_code, org_product_table_name,
              org_product_metric_code, org_product_metric_name,
              manual_entry_mode, value_mode, sort_order, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_product,
                section,
                item_name,
                parent_id,
                1 if display_group else 0,
                normalized_data_acct_code,
                org_product_identity["org_product_ref"],
                org_product_identity["org_product_entity_code"],
                org_product_identity["org_product_table_name"],
                org_product_identity["org_product_metric_code"],
                org_product_identity["org_product_metric_name"],
                normalized_manual_entry_mode,
                normalized_value_mode,
                sort_order,
                1 if enabled else 0,
            ),
        )
        cur = await db.execute("SELECT last_insert_rowid()")
        item_id = int((await cur.fetchone())[0])
        await _replace_source_mappings(
            db,
            item_id=item_id,
            data_acct_code=normalized_data_acct_code if not display_group else "",
            enabled=enabled,
        )
        await db.commit()

    item = {
        "id": item_id,
        "product_code": normalized_product,
        "section": section,
        "name": item_name,
        "parent_id": parent_id,
        "display_group": bool(display_group),
        "data_acct_code": normalized_data_acct_code,
        **org_product_identity,
        "manual_entry_mode": normalized_manual_entry_mode,
        "value_mode": normalized_value_mode,
        "sort_order": sort_order,
        "enabled": bool(enabled),
    }
    return {"item": item, "after_data": {**item, "update_time": now}}


async def update_business_cost_income_item(
    *,
    year: int,
    item_id: int,
    product_code: str | None = None,
    name: str,
    parent_id: int | None,
    display_group: bool = False,
    data_acct_code: str | None = None,
    org_product_ref: str | None = None,
    org_product_entity_code: str | None = None,
    org_product_table_name: str | None = None,
    org_product_metric_code: str | None = None,
    org_product_metric_name: str | None = None,
    manual_entry_mode: str = "disabled",
    value_mode: str = "tree",
    sort_order: int,
    enabled: bool,
) -> dict[str, Any]:
    await ensure_business_cost_income_tables(year)
    normalized_product = _normalize_product_code(product_code)
    parent_id_value = int(parent_id) if parent_id is not None else None
    item_name = _normalize_text(name)
    normalized_manual_entry_mode = _normalize_manual_entry_mode(manual_entry_mode)
    normalized_value_mode = _normalize_value_mode(value_mode)
    org_product_identity_provided = any(
        value is not None
        for value in (
            org_product_ref,
            org_product_entity_code,
            org_product_table_name,
            org_product_metric_code,
            org_product_metric_name,
        )
    )

    async with aiosqlite.connect(budget_db_path(year)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT id, product_code, section, name, parent_id, display_group, data_acct_code,
                   org_product_ref, org_product_entity_code, org_product_table_name,
                   org_product_metric_code, org_product_metric_name,
                   manual_entry_mode, value_mode, sort_order, enabled
            FROM business_cost_income_item
            WHERE id = ?
            """,
            (int(item_id),),
        )
        before_row = await cur.fetchone()
        if before_row is None:
            raise LookupError("细项不存在")
        before = _item_from_row(before_row)
        if before["product_code"] != normalized_product:
            raise ValueError("细项不属于当前产品模板")

        normalized_data_acct_code = ""
        org_product_identity = _normalize_org_product_item_identity(
            org_product_ref=org_product_ref,
            org_product_entity_code=org_product_entity_code,
            org_product_table_name=org_product_table_name,
            org_product_metric_code=org_product_metric_code,
            org_product_metric_name=org_product_metric_name,
            product_code=normalized_product,
        )
        if display_group:
            if not item_name:
                raise ValueError("展示分组名称不能为空")
            org_product_identity = _normalize_org_product_item_identity(product_code=normalized_product)
        elif _runtime_ref_from_org_product_item_identity(org_product_identity):
            normalized_data_acct_code, item_name = await _ensure_runtime_metric_reference(
                _runtime_ref_from_org_product_item_identity(org_product_identity),
                product_code=normalized_product,
            )
            if org_product_identity.get("org_product_metric_name"):
                item_name = org_product_identity["org_product_metric_name"]
        elif _normalize_text(data_acct_code or before["data_acct_code"]):
            normalized_data_acct_code, item_name = await _ensure_runtime_metric_reference(
                str(data_acct_code or before["data_acct_code"] or ""),
                product_code=normalized_product,
            )
            if not org_product_identity_provided:
                org_product_identity = {
                    "org_product_ref": str(before.get("org_product_ref") or ""),
                    "org_product_entity_code": str(before.get("org_product_entity_code") or ""),
                    "org_product_table_name": str(before.get("org_product_table_name") or ""),
                    "org_product_metric_code": str(before.get("org_product_metric_code") or ""),
                    "org_product_metric_name": str(before.get("org_product_metric_name") or ""),
                }
            if org_product_identity.get("org_product_metric_name"):
                item_name = org_product_identity["org_product_metric_name"]
        else:
            normalized_data_acct_code = ""
            org_product_identity = _normalize_org_product_item_identity(product_code=normalized_product)

        if parent_id_value is not None and parent_id_value == int(item_id):
            raise ValueError("不能将自己设为父级")
        if parent_id_value is not None:
            await _ensure_item_reference(
                db,
                section=before["section"],
                item_id=parent_id_value,
                label="父级",
                product_code=normalized_product,
            )
            cur = await db.execute(
                "SELECT id, parent_id FROM business_cost_income_item WHERE product_code = ? AND section = ?",
                (normalized_product, before["section"]),
            )
            tree_rows = await cur.fetchall()
            children_by_parent: dict[int, list[int]] = {}
            for row in tree_rows:
                if row[1] is not None:
                    children_by_parent.setdefault(int(row[1]), []).append(int(row[0]))
            descendants: set[int] = set()
            stack = list(children_by_parent.get(int(item_id), []))
            while stack:
                current = stack.pop()
                if current in descendants:
                    continue
                descendants.add(current)
                stack.extend(children_by_parent.get(current, []))
            if parent_id_value in descendants:
                raise ValueError("不能将当前细项移动到自己的下级节点下")

        target_sort_order = int(sort_order or 0)
        if parent_id_value != before["parent_id"]:
            if parent_id_value is None:
                cur = await db.execute(
                    """
                    SELECT COALESCE(MAX(sort_order), -1) + 1
                    FROM business_cost_income_item
                    WHERE product_code = ? AND section = ? AND parent_id IS NULL AND id <> ?
                    """,
                    (normalized_product, before["section"], int(item_id)),
                )
            else:
                cur = await db.execute(
                    """
                    SELECT COALESCE(MAX(sort_order), -1) + 1
                    FROM business_cost_income_item
                    WHERE product_code = ? AND section = ? AND parent_id = ? AND id <> ?
                    """,
                    (normalized_product, before["section"], parent_id_value, int(item_id)),
                )
            target_sort_order = int((await cur.fetchone())[0])

        await db.execute(
            """
            UPDATE business_cost_income_item
            SET name = ?, parent_id = ?, display_group = ?, data_acct_code = ?,
                org_product_ref = ?, org_product_entity_code = ?, org_product_table_name = ?,
                org_product_metric_code = ?, org_product_metric_name = ?,
                manual_entry_mode = ?, value_mode = ?, sort_order = ?, enabled = ?
            WHERE id = ?
            """,
            (
                item_name,
                parent_id_value,
                1 if display_group else 0,
                normalized_data_acct_code,
                org_product_identity["org_product_ref"],
                org_product_identity["org_product_entity_code"],
                org_product_identity["org_product_table_name"],
                org_product_identity["org_product_metric_code"],
                org_product_identity["org_product_metric_name"],
                normalized_manual_entry_mode,
                normalized_value_mode,
                target_sort_order,
                1 if enabled else 0,
                int(item_id),
            ),
        )
        await _replace_source_mappings(
            db,
            item_id=int(item_id),
            data_acct_code=normalized_data_acct_code if not display_group else "",
            enabled=enabled,
        )
        await db.commit()

    item = {
        "id": int(item_id),
        "product_code": normalized_product,
        "section": before["section"],
        "name": item_name,
        "parent_id": parent_id_value,
        "display_group": bool(display_group),
        "data_acct_code": normalized_data_acct_code,
        **org_product_identity,
        "manual_entry_mode": normalized_manual_entry_mode,
        "value_mode": normalized_value_mode,
        "sort_order": target_sort_order,
        "enabled": bool(enabled),
    }
    return {"item": item, "before_data": before, "after_data": item}


async def delete_business_cost_income_item(*, year: int, item_id: int) -> dict[str, Any]:
    await ensure_business_cost_income_tables(year)
    async with aiosqlite.connect(budget_db_path(year)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT id, product_code, section, name, parent_id, display_group, data_acct_code,
                   org_product_ref, org_product_entity_code, org_product_table_name,
                   org_product_metric_code, org_product_metric_name,
                   manual_entry_mode, value_mode, sort_order, enabled
            FROM business_cost_income_item
            WHERE id = ?
            """,
            (int(item_id),),
        )
        before_row = await cur.fetchone()
        if before_row is None:
            raise LookupError("细项不存在")
        before = _item_from_row(before_row)
        child_cur = await db.execute(
            "SELECT COUNT(*) FROM business_cost_income_item WHERE parent_id = ?",
            (int(item_id),),
        )
        child_count = int((await child_cur.fetchone())[0])
        if child_count > 0:
            raise ValueError(f"该细项有 {child_count} 个子项，请先删除或移动子项")
        await db.execute("DELETE FROM business_cost_income_item WHERE id = ?", (int(item_id),))
        await db.commit()
    return {"deleted": True, "before_data": before}


async def reorder_business_cost_income_items(*, year: int, item_ids: list[Any]) -> dict[str, Any]:
    if not item_ids or not isinstance(item_ids, list):
        raise ValueError("item_ids 必须是非空列表")
    now = _iso_now()
    await ensure_business_cost_income_tables(year)
    async with aiosqlite.connect(budget_db_path(year)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT id, product_code, section, parent_id
            FROM business_cost_income_item
            WHERE id IN ({})
            """.format(",".join("?" for _ in item_ids)),
            tuple(int(item_id) for item_id in item_ids),
        )
        rows = await cur.fetchall()
        if len(rows) != len(item_ids):
            raise ValueError("存在无效细项")
        parents = {(str(row[1]), str(row[2]), row[3]) for row in rows}
        if len(parents) != 1:
            raise ValueError("只能对同一产品、同一分区、同一父级下的细项排序")
        for idx, item_id in enumerate(item_ids):
            await db.execute(
                "UPDATE business_cost_income_item SET sort_order = ? WHERE id = ?",
                (idx, int(item_id)),
            )
        await db.commit()
    return {"reordered": True, "count": len(item_ids), "after_data": {"item_ids": item_ids, "update_time": now}}


async def create_business_cost_income_indicator(
    *,
    year: int,
    product_code: str | None = None,
    name: str,
    parent_id: int | None = None,
    display_group: bool = False,
    topic_metric_node_code: str | None = None,
    numerator_section: str,
    numerator_item_id: int,
    numerator_value_mode: str = "tree",
    denominator_section: str,
    denominator_item_id: int,
    denominator_value_mode: str = "tree",
    format: str,
    annualize: bool = False,
    sort_order: int,
    enabled: bool,
) -> dict[str, Any]:
    normalized_product = _normalize_product_code(product_code)
    indicator = {
        "product_code": normalized_product,
        "name": _normalize_text(name),
        "parent_id": int(parent_id) if parent_id is not None else None,
        "display_group": bool(display_group),
        "topic_metric_node_code": _normalize_indicator_topic_metric_node_code(
            topic_metric_node_code,
            product_code=normalized_product,
        ),
        "numerator_section": str(numerator_section),
        "numerator_item_id": int(numerator_item_id),
        "numerator_value_mode": _normalize_value_mode(numerator_value_mode),
        "denominator_section": str(denominator_section),
        "denominator_item_id": int(denominator_item_id),
        "denominator_value_mode": _normalize_value_mode(denominator_value_mode),
        "format": _normalize_indicator_format(format),
        "annualize": bool(annualize),
        "sort_order": int(sort_order or 0),
        "enabled": bool(enabled),
    }
    await ensure_business_cost_income_tables(year)
    async with aiosqlite.connect(budget_db_path(year)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await _ensure_item_reference(
            db,
            section=indicator["numerator_section"],
            item_id=indicator["numerator_item_id"],
            label="分子",
            product_code=normalized_product,
        )
        await _ensure_item_reference(
            db,
            section=indicator["denominator_section"],
            item_id=indicator["denominator_item_id"],
            label="分母",
            product_code=normalized_product,
        )
        if indicator["parent_id"] is not None:
            pcur = await db.execute(
                """
                SELECT id, product_code
                FROM business_cost_income_indicator
                WHERE id = ?
                """,
                (indicator["parent_id"],),
            )
            prow = await pcur.fetchone()
            if prow is None or str(prow[1] or "") != normalized_product:
                raise ValueError("父级指标不存在或不属于当前产品模板")
        await db.execute(
            """
            INSERT INTO business_cost_income_indicator(
              product_code, name, parent_id, display_group, topic_metric_node_code,
              numerator_section, numerator_item_id, numerator_value_mode,
              denominator_section, denominator_item_id, denominator_value_mode,
              format, annualize, sort_order, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                indicator["product_code"],
                indicator["name"],
                indicator["parent_id"],
                1 if indicator["display_group"] else 0,
                indicator["topic_metric_node_code"],
                indicator["numerator_section"],
                indicator["numerator_item_id"],
                indicator["numerator_value_mode"],
                indicator["denominator_section"],
                indicator["denominator_item_id"],
                indicator["denominator_value_mode"],
                indicator["format"],
                1 if indicator["annualize"] else 0,
                indicator["sort_order"],
                1 if indicator["enabled"] else 0,
            ),
        )
        cur = await db.execute("SELECT last_insert_rowid()")
        indicator["id"] = int((await cur.fetchone())[0])
        await db.commit()
    return {"indicator": indicator, "after_data": indicator}


async def update_business_cost_income_indicator(
    *,
    year: int,
    indicator_id: int,
    product_code: str | None = None,
    name: str,
    parent_id: int | None = None,
    display_group: bool = False,
    topic_metric_node_code: str | None = None,
    numerator_section: str,
    numerator_item_id: int,
    numerator_value_mode: str = "tree",
    denominator_section: str,
    denominator_item_id: int,
    denominator_value_mode: str = "tree",
    format: str,
    annualize: bool = False,
    sort_order: int,
    enabled: bool,
) -> dict[str, Any]:
    await ensure_business_cost_income_tables(year)
    normalized_product = _normalize_product_code(product_code)
    async with aiosqlite.connect(budget_db_path(year)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT id, product_code, name, parent_id, display_group, topic_metric_node_code,
                   numerator_section, numerator_item_id, numerator_value_mode,
                   denominator_section, denominator_item_id, denominator_value_mode,
                   format, annualize, sort_order, enabled
            FROM business_cost_income_indicator
            WHERE id = ?
            """,
            (int(indicator_id),),
        )
        before_row = await cur.fetchone()
        if before_row is None:
            raise LookupError("指标不存在")
        before = _indicator_from_row(before_row)
        if before["product_code"] != normalized_product:
            raise ValueError("指标不属于当前产品模板")
        indicator = {
            "id": int(indicator_id),
            "product_code": normalized_product,
            "name": _normalize_text(name),
            "parent_id": int(parent_id) if parent_id is not None else None,
            "display_group": bool(display_group),
            "topic_metric_node_code": _normalize_indicator_topic_metric_node_code(
                topic_metric_node_code,
                product_code=normalized_product,
            ),
            "numerator_section": str(numerator_section),
            "numerator_item_id": int(numerator_item_id),
            "numerator_value_mode": _normalize_value_mode(numerator_value_mode),
            "denominator_section": str(denominator_section),
            "denominator_item_id": int(denominator_item_id),
            "denominator_value_mode": _normalize_value_mode(denominator_value_mode),
            "format": _normalize_indicator_format(format),
            "annualize": bool(annualize),
            "sort_order": int(sort_order or 0),
            "enabled": bool(enabled),
        }
        await _ensure_item_reference(
            db,
            section=indicator["numerator_section"],
            item_id=indicator["numerator_item_id"],
            label="分子",
            product_code=normalized_product,
        )
        await _ensure_item_reference(
            db,
            section=indicator["denominator_section"],
            item_id=indicator["denominator_item_id"],
            label="分母",
            product_code=normalized_product,
        )
        if indicator["parent_id"] is not None:
            if indicator["parent_id"] == int(indicator_id):
                raise ValueError("不能将自己设为父级")
            pcur = await db.execute(
                "SELECT id, product_code, parent_id FROM business_cost_income_indicator WHERE id = ?",
                (indicator["parent_id"],),
            )
            prow = await pcur.fetchone()
            if prow is None or str(prow[1] or "") != normalized_product:
                raise ValueError("父级指标不存在或不属于当前产品模板")
        await db.execute(
            """
            UPDATE business_cost_income_indicator
            SET name = ?,
                parent_id = ?, display_group = ?, topic_metric_node_code = ?,
                numerator_section = ?, numerator_item_id = ?, numerator_value_mode = ?,
                denominator_section = ?, denominator_item_id = ?, denominator_value_mode = ?,
                format = ?, annualize = ?, sort_order = ?, enabled = ?
            WHERE id = ?
            """,
            (
                indicator["name"],
                indicator["parent_id"],
                1 if indicator["display_group"] else 0,
                indicator["topic_metric_node_code"],
                indicator["numerator_section"],
                indicator["numerator_item_id"],
                indicator["numerator_value_mode"],
                indicator["denominator_section"],
                indicator["denominator_item_id"],
                indicator["denominator_value_mode"],
                indicator["format"],
                1 if indicator["annualize"] else 0,
                indicator["sort_order"],
                1 if indicator["enabled"] else 0,
                int(indicator_id),
            ),
        )
        await db.commit()
    return {"indicator": indicator, "before_data": before, "after_data": indicator}


async def delete_business_cost_income_indicator(*, year: int, indicator_id: int) -> dict[str, Any]:
    await ensure_business_cost_income_tables(year)
    async with aiosqlite.connect(budget_db_path(year)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT id, product_code, name, parent_id, display_group, topic_metric_node_code,
                   numerator_section, numerator_item_id, numerator_value_mode,
                   denominator_section, denominator_item_id, denominator_value_mode,
                   format, annualize, sort_order, enabled
            FROM business_cost_income_indicator
            WHERE id = ?
            """,
            (int(indicator_id),),
        )
        before_row = await cur.fetchone()
        if before_row is None:
            raise LookupError("指标不存在")
        before = _indicator_from_row(before_row)
        await db.execute("DELETE FROM business_cost_income_indicator WHERE id = ?", (int(indicator_id),))
        await db.commit()
    return {"deleted": True, "before_data": before}


async def reorder_business_cost_income_indicators(*, year: int, indicator_ids: list[Any]) -> dict[str, Any]:
    if not indicator_ids or not isinstance(indicator_ids, list):
        raise ValueError("indicator_ids 必须是非空列表")
    now = _iso_now()
    await ensure_business_cost_income_tables(year)
    async with aiosqlite.connect(budget_db_path(year)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT id, product_code, parent_id
            FROM business_cost_income_indicator
            WHERE id IN ({})
            """.format(",".join("?" for _ in indicator_ids)),
            tuple(int(indicator_id) for indicator_id in indicator_ids),
        )
        rows = await cur.fetchall()
        if len(rows) != len(indicator_ids):
            raise ValueError("存在无效指标")
        parents = {(str(row[1]), row[2]) for row in rows}
        if len(parents) != 1:
            raise ValueError("只能对同一产品、同一父级下的指标排序")
        for idx, indicator_id in enumerate(indicator_ids):
            await db.execute(
                "UPDATE business_cost_income_indicator SET sort_order = ? WHERE id = ?",
                (idx, int(indicator_id)),
            )
        await db.commit()
    return {
        "reordered": True,
        "count": len(indicator_ids),
        "after_data": {"indicator_ids": indicator_ids, "update_time": now},
    }
