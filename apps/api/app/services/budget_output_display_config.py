from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import HTTPException

from app.db_bootstrap.report_display import ensure_budget_output_display_item_schema
from app.core.db_paths import common_db_path
from app.schemas import (
    BudgetOutputDisplayConfigImportResponse,
    BudgetOutputDisplayConfigItemDto,
    BudgetOutputDisplayConfigResponse,
)
from app.services.budget_display_config_import import (
    apply_budget_display_config_import,
    build_budget_display_config_workbook,
    parse_budget_display_config_workbook,
)
from app.services.budget_display_structure import allocate_budget_display_row_key
from app.services.budget_output_display import (
    budget_display_candidate_to_dto,
    budget_display_config_item_to_dto,
    fetch_budget_display_config_candidates,
    fetch_budget_display_config_items,
)
from app.services.runtime_metric_refs import (
    load_confirmed_org_product_runtime_ref_codes,
    load_org_product_metric_refs_by_runtime_ref_code,
)


@dataclass(frozen=True)
class BudgetOutputDisplayConfigCreateCommand:
    data_acct_code: str | None = None
    display_name: str | None = None
    parent_row_key: str | None = None
    insert_after_row_key: str | None = None
    display_view: str = "TOTAL"
    sort_order: int | None = None
    org_product_ref: str | None = None
    org_product_entity_code: str | None = None
    org_product_table_name: str | None = None
    org_product_metric_code: str | None = None
    org_product_metric_name: str | None = None


@dataclass(frozen=True)
class BudgetOutputDisplayConfigUpdateCommand:
    data_acct_code: str | None = None
    display_name: str | None = None
    sort_order: int | None = None
    is_active: int | None = None


class BudgetOutputDisplayConfigError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class BudgetOutputDisplayConfigRebuildResult:
    ok: bool
    deleted_rows: int
    inserted_rows: int
    total_rows: int
    overview_rows: int
    product_rows: int


async def load_budget_output_display_config_response(
    *,
    common_path: Path | None = None,
) -> BudgetOutputDisplayConfigResponse:
    async with aiosqlite.connect(common_path or common_db_path()) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await ensure_budget_output_display_item_schema(db)
        item_rows = await fetch_budget_display_config_items(db, active_only=False)
        candidate_rows = await fetch_budget_display_config_candidates(db)
    return BudgetOutputDisplayConfigResponse(
        items=[budget_display_config_item_to_dto(row) for row in item_rows],
        candidates=[budget_display_candidate_to_dto(row) for row in candidate_rows],
    )


async def build_budget_output_display_config_export_workbook(
    *,
    common_path: Path | None = None,
):
    async with aiosqlite.connect(common_path or common_db_path()) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await ensure_budget_output_display_item_schema(db)
        item_rows = await fetch_budget_display_config_items(db, active_only=False)
        org_product_refs_by_data = await load_org_product_metric_refs_by_runtime_ref_code(db)
    return build_budget_display_config_workbook(item_rows, org_product_refs_by_data=org_product_refs_by_data)


async def apply_budget_output_display_config_import_upload(
    *,
    file_name: str,
    raw: bytes,
    mode: str,
    common_path: Path | None = None,
) -> BudgetOutputDisplayConfigImportResponse:
    if not raw:
        raise HTTPException(status_code=400, detail="导入文件为空")
    rows = parse_budget_display_config_workbook(file_name, raw)
    async with aiosqlite.connect(common_path or common_db_path()) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await ensure_budget_output_display_item_schema(db)
        result = await apply_budget_display_config_import(db, rows=rows, mode=mode)
    return BudgetOutputDisplayConfigImportResponse(**result)


def _display_row_key(display_view: str, node_code: str, logic_code: str) -> str:
    view = str(display_view or "").strip().upper()
    node = str(node_code or "").strip().upper()
    logic = str(logic_code or "").strip().upper()
    if view in {"TOTAL", "OVERVIEW"}:
        return f"{view}.{logic}" if logic else view
    return f"{view}.{logic}" if logic else view


def _display_parent_key(display_view: str, parent_code: str | None, product_code: str) -> str | None:
    parent = str(parent_code or "").strip().upper()
    product = str(product_code or "").strip().upper()
    if not parent or parent == product:
        return None
    suffix = parent.split(".", 1)[1] if "." in parent else ""
    if not suffix:
        return None
    return _display_row_key(display_view, parent, suffix)


async def rebuild_budget_output_display_config_from_org_product_metrics(
    *,
    common_path: Path | None = None,
    budget_path: Path | None = None,
) -> BudgetOutputDisplayConfigRebuildResult:
    async with aiosqlite.connect(common_path or common_db_path()) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await ensure_budget_output_display_item_schema(db)
        account_rows = await db.execute("SELECT data_acct_code FROM data_account")
        account_codes = {str(row["data_acct_code"] or "").strip().upper() for row in await account_rows.fetchall()}

        # 从 budget_data 获取实际有数据的编码，只建这些指标的行
        valid_total_codes: set[str] = set()      # AA 级编码（用于 TOTAL view）
        valid_product_codes: dict[str, set[str]] = {}  # {product_code: {node_code, ...}}（用于 PRODUCT view）
        valid_overview_suffixes: set[str] = set()  # 产品级数据中出现的 suffix（用于 OVERVIEW）

        if budget_path and budget_path.exists():
            async with aiosqlite.connect(budget_path) as bdb:
                bdb.row_factory = aiosqlite.Row
                bcur = await bdb.execute(
                    "SELECT DISTINCT data_acct_code, product_code FROM budget_data"
                )
                for row in await bcur.fetchall():
                    dac = str(row["data_acct_code"] or "").strip().upper()
                    pc = str(row["product_code"] or "").strip().upper()
                    if not dac or not pc:
                        continue
                    if pc == "AA":
                        valid_total_codes.add(dac)
                    else:
                        valid_product_codes.setdefault(pc, set()).add(dac)
                        suffix = dac.split(".", 1)[1] if "." in dac else dac
                        if suffix:
                            valid_overview_suffixes.add(suffix)
        else:
            # 没有 budget 数据时回退到原来的行为（全部编码）
            valid_total_codes = account_codes
            valid_product_codes = {}

        cur = await db.execute(
            """
            SELECT node_code, node_name, parent_code, product_code,
                   COALESCE(logic_code, local_metric_code, '') AS logic_code,
                   node_type, sort_order, level
            FROM data_account_metric_node
            WHERE is_active = 1
              AND COALESCE(product_code, '') <> ''
              AND COALESCE(logic_code, local_metric_code, '') <> ''
            ORDER BY product_code, level, sort_order, node_code
            """
        )
        node_rows = [dict(row) for row in await cur.fetchall()]

        before = await db.execute("SELECT COUNT(*) AS c FROM budget_output_display_item")
        deleted_rows = int((await before.fetchone())["c"] or 0)
        await db.execute("PRAGMA foreign_keys = OFF")
        await db.execute("DELETE FROM budget_output_display_item")

        inserted_rows = 0
        total_rows = 0
        overview_rows = 0
        product_rows = 0

        async def insert_item(
            *,
            display_view: str,
            row_key: str,
            parent_row_key: str | None,
            row: dict[str, Any],
        ) -> None:
            nonlocal inserted_rows, total_rows, overview_rows, product_rows
            node_code = str(row["node_code"] or "").strip().upper()
            product_code = str(row["product_code"] or "").strip().upper()
            data_acct_code = node_code if node_code in account_codes else None
            row_type = "METRIC" if data_acct_code else "GROUP"
            metric_name = str(row["node_name"] or node_code).strip()
            table_name = str(row.get("functional_group_code") or "").strip() or "机构及产品指标"
            await db.execute(
                """
                INSERT INTO budget_output_display_item(
                  row_key, display_view, parent_row_key, data_acct_code,
                  org_product_ref, org_product_entity_code, org_product_table_name,
                  org_product_metric_code, org_product_metric_name, row_type,
                  display_name, value_type, level, sort_order, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 1)
                """,
                (
                    row_key,
                    display_view,
                    parent_row_key,
                    data_acct_code,
                    f"{product_code}:{table_name}:{node_code}" if data_acct_code else None,
                    product_code if data_acct_code else None,
                    table_name if data_acct_code else None,
                    node_code if data_acct_code else None,
                    metric_name if data_acct_code else None,
                    row_type,
                    metric_name,
                    int(str(node_code).count(".") + 1),
                    int(row.get("sort_order") or 0),
                ),
            )
            inserted_rows += 1
            if display_view == "TOTAL":
                total_rows += 1
            elif display_view == "OVERVIEW":
                overview_rows += 1
            elif display_view.startswith("PRODUCT."):
                product_rows += 1

        for row in node_rows:
            product_code = str(row["product_code"] or "").strip().upper()
            node_code = str(row["node_code"] or "").strip().upper()
            logic_code = str(row["logic_code"] or "").strip().upper()
            if not product_code or not node_code or not logic_code:
                continue
            if product_code == "AA":
                # TOTAL: 只建 budget_data AA 产品中存在的编码
                if node_code in valid_total_codes:
                    row_key = _display_row_key("TOTAL", node_code, logic_code)
                    await insert_item(
                        display_view="TOTAL",
                        row_key=row_key,
                        parent_row_key=_display_parent_key("TOTAL", row.get("parent_code"), product_code),
                        row=row,
                    )
                    # OVERVIEW: 同样只建有 AA 数据的编码
                    row_key = _display_row_key("OVERVIEW", node_code, logic_code)
                    await insert_item(
                        display_view="OVERVIEW",
                        row_key=row_key,
                        parent_row_key=_display_parent_key("OVERVIEW", row.get("parent_code"), product_code),
                        row=row,
                    )
            else:
                # PRODUCT: 只建该产品在 budget_data 中存在的编码
                product_codes = valid_product_codes.get(product_code) if budget_path else None
                if product_codes is None or node_code in product_codes:
                    display_view = f"PRODUCT.{product_code}"
                    row_key = _display_row_key(display_view, node_code, logic_code)
                    await insert_item(
                        display_view=display_view,
                        row_key=row_key,
                        parent_row_key=_display_parent_key(display_view, row.get("parent_code"), product_code),
                        row=row,
                    )

        await db.commit()
        await db.execute("PRAGMA foreign_keys = ON")

async def rebuild_budget_output_display_config_from_excel(
    *,
    common_path: Path | None = None,
    budget_path: Path | None = None,
    codes_json_path: Path | None = None,
) -> BudgetOutputDisplayConfigRebuildResult:
    """基于 Excel「机构及产品指标表」重建展示配置。

    视图结构：
      TOTAL: 利润表 (GROUP) + 资产负债表 (GROUP)，指标来自对应 sheet
      OVERVIEW: 利润表指标（同 PROFIT）
      PRODUCT.{code}: 各产品全部指标
    """
    import json as _json

    if codes_json_path is None:
        codes_json_path = common_db_path().parent / "budget_display_codes.json"

    with open(codes_json_path) as f:
        view_codes = _json.load(f)

    profit_codes = view_codes["PROFIT"]      # [(code, name), ...]
    balance_codes = view_codes["BALANCE"]    # [(code, name), ...]
    product_codes = view_codes["PRODUCTS"]   # {product_code: [(code, name), ...]}

    all_aa_codes = set(c for c, _ in profit_codes) | set(c for c, _ in balance_codes)

    async with aiosqlite.connect(common_path or common_db_path()) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await ensure_budget_output_display_item_schema(db)

        # 获取 data_account 有效编码集合
        account_rows = await db.execute("SELECT data_acct_code FROM data_account")
        account_codes = {str(r["data_acct_code"] or "").strip().upper() for r in await account_rows.fetchall()}

        # 获取 budget_data 中存在的编码（用于 TOTAL view 过滤）
        valid_total_codes: set[str] = set()
        if budget_path and budget_path.exists():
            async with aiosqlite.connect(budget_path) as bdb:
                bdb.row_factory = aiosqlite.Row
                bcur = await bdb.execute(
                    "SELECT DISTINCT data_acct_code FROM budget_data WHERE product_code = 'AA'"
                )
                valid_total_codes = {str(r["data_acct_code"] or "").strip().upper() for r in await bcur.fetchall()}

        # 查询 data_account_metric_node 获取所有节点的元数据
        all_codes_list = sorted(all_aa_codes | set(
            c for codes in product_codes.values() for c, _ in codes
        ))
        placeholders = ",".join("?" for _ in all_codes_list)
        cur = await db.execute(
            f"""SELECT node_code, node_name, parent_code, product_code,
                       level, sort_order
                FROM data_account_metric_node
                WHERE node_code IN ({placeholders}) AND is_active = 1
                ORDER BY product_code, level, sort_order, node_code""",
            tuple(all_codes_list),
        )
        node_map: dict[str, dict[str, Any]] = {}
        for row in await cur.fetchall():
            node_map[str(row["node_code"]).strip().upper()] = dict(row)

        # 清空重建
        before = await db.execute("SELECT COUNT(*) AS c FROM budget_output_display_item")
        deleted_rows = int((await before.fetchone())[0] or 0)
        await db.execute("PRAGMA foreign_keys = OFF")
        await db.execute("DELETE FROM budget_output_display_item")

        inserted_rows = 0
        total_rows = 0
        overview_rows = 0
        product_rows = 0
        sort_counter = 0

        def make_row_dict(node_code: str, display_name: str) -> dict[str, Any]:
            """构造与旧 insert_item 兼容的 row dict"""
            node = node_map.get(node_code, {})
            return {
                "node_code": node_code,
                "node_name": display_name,
                "product_code": node.get("product_code") or "",
                "parent_code": node.get("parent_code") or "",
                "sort_order": node.get("sort_order") or 0,
                "level": node.get("level") or 1,
                "functional_group_code": "",
            }

        async def insert_row(
            display_view: str,
            row_key: str,
            parent_row_key: str | None,
            data_acct_code: str | None,
            display_name: str,
            row_type: str,
            level: int,
            sort_order: int,
            org_product_entity_code: str | None = None,
        ) -> None:
            nonlocal inserted_rows, total_rows, overview_rows, product_rows
            in_account = data_acct_code and data_acct_code in account_codes
            await db.execute(
                """INSERT OR IGNORE INTO budget_output_display_item(
                     row_key, display_view, parent_row_key, data_acct_code,
                     org_product_ref, org_product_entity_code, org_product_table_name,
                     org_product_metric_code, org_product_metric_name, row_type,
                     display_name, value_type, level, sort_order, is_active
                   ) VALUES (?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?, ?, NULL, ?, ?, 1)""",
                (
                    row_key, display_view, parent_row_key,
                    data_acct_code if in_account else None,
                    org_product_entity_code if (in_account and data_acct_code) else None,
                    data_acct_code if (in_account and data_acct_code) else None,
                    display_name if (in_account and data_acct_code) else None,
                    row_type, display_name,
                    level, sort_order,
                ),
            )
            inserted_rows += 1
            if display_view == "TOTAL":
                total_rows += 1
            elif display_view == "OVERVIEW":
                overview_rows += 1
            elif display_view.startswith("PRODUCT."):
                product_rows += 1

        # ===== TOTAL: 利润表 =====
        await insert_row(
            display_view="TOTAL", row_key="TOTAL.PROFIT", parent_row_key=None,
            data_acct_code=None, display_name="利润表", row_type="GROUP",
            level=0, sort_order=sort_counter,
        )
        sort_counter += 10
        profit_parent = "TOTAL.PROFIT"

        prev_level: dict[int, str | None] = {0: profit_parent}
        for code, name in profit_codes:
            level = int(str(code).count("."))
            parent = prev_level.get(level - 1, profit_parent)
            prev_level[level] = f"TOTAL.PROFIT.{code}"
            await insert_row(
                display_view="TOTAL", row_key=f"TOTAL.PROFIT.{code}",
                parent_row_key=parent, data_acct_code=code,
                display_name=name, row_type="METRIC" if code in account_codes else "GROUP",
                level=level + 1, sort_order=sort_counter,
            )
            sort_counter += 10

        # ===== TOTAL: 资产负债表 =====
        await insert_row(
            display_view="TOTAL", row_key="TOTAL.BALANCE", parent_row_key=None,
            data_acct_code=None, display_name="资产负债表", row_type="GROUP",
            level=0, sort_order=sort_counter,
        )
        sort_counter += 10
        balance_parent = "TOTAL.BALANCE"
        prev_level = {0: balance_parent}

        for code, name in balance_codes:
            level = int(str(code).count("."))
            parent = prev_level.get(level - 1, balance_parent)
            prev_level[level] = f"TOTAL.BALANCE.{code}"
            await insert_row(
                display_view="TOTAL", row_key=f"TOTAL.BALANCE.{code}",
                parent_row_key=parent, data_acct_code=code,
                display_name=name, row_type="METRIC" if code in account_codes else "GROUP",
                level=level + 1, sort_order=sort_counter,
            )
            sort_counter += 10

        # ===== OVERVIEW: 利润表指标 =====
        overview_sort = 0
        for code, name in profit_codes:
            await insert_row(
                display_view="OVERVIEW", row_key=f"OVERVIEW.{code}",
                parent_row_key=None, data_acct_code=code,
                display_name=name, row_type="METRIC" if code in account_codes else "GROUP",
                level=int(str(code).count(".")) + 1, sort_order=overview_sort,
            )
            overview_sort += 10

        # ===== PRODUCT: 各产品全部指标 =====
        for prod_code, items in product_codes.items():
            prod_sort = 0
            for code, name in items:
                await insert_row(
                    display_view=f"PRODUCT.{prod_code}",
                    row_key=f"PRODUCT.{prod_code}.{code}",
                    parent_row_key=None, data_acct_code=code,
                    display_name=name,
                    row_type="METRIC" if code in account_codes else "GROUP",
                    level=int(str(code).count(".")) + 1, sort_order=prod_sort,
                    org_product_entity_code=prod_code,
                )
                prod_sort += 10

        await db.commit()
        await db.execute("PRAGMA foreign_keys = ON")

    return BudgetOutputDisplayConfigRebuildResult(
        ok=True,
        deleted_rows=deleted_rows,
        inserted_rows=inserted_rows,
        total_rows=total_rows,
        overview_rows=overview_rows,
        product_rows=product_rows,
    )


async def apply_budget_output_display_config_item_create(
    command: BudgetOutputDisplayConfigCreateCommand,
    *,
    common_path: Path | None = None,
) -> BudgetOutputDisplayConfigItemDto:
    async with aiosqlite.connect(common_path or common_db_path()) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        row = await create_budget_output_display_item(db, command)
    return budget_display_config_item_to_dto(row)


async def apply_budget_output_display_config_item_update(
    row_key: str,
    command: BudgetOutputDisplayConfigUpdateCommand,
    *,
    common_path: Path | None = None,
) -> BudgetOutputDisplayConfigItemDto:
    async with aiosqlite.connect(common_path or common_db_path()) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        row = await update_budget_output_display_item(db, row_key, command)
    return budget_display_config_item_to_dto(row)


async def apply_budget_output_display_config_item_delete(
    row_key: str,
    *,
    common_path: Path | None = None,
) -> dict[str, bool]:
    async with aiosqlite.connect(common_path or common_db_path()) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        return await delete_budget_output_display_item(db, row_key)


async def _load_bound_runtime_metric_source(
    db: aiosqlite.Connection,
    data_acct_code: str,
) -> aiosqlite.Row:
    confirmed_codes = await load_confirmed_org_product_runtime_ref_codes(db)
    normalized_code = str(data_acct_code or "").strip().upper()
    if normalized_code not in confirmed_codes:
        raise BudgetOutputDisplayConfigError(
            404,
            "该指标未在机构及产品指标主表中确认，不能作为预算展示配置来源",
        )
    cur = await db.execute(
        """
        SELECT d.data_acct_code, d.data_acct_name, d.value_type,
               b.metric_node_code, b.scope_type, b.scope_code
        FROM data_account d
        JOIN data_account_metric_binding b ON b.data_acct_code = d.data_acct_code AND b.is_active = 1
        WHERE d.data_acct_code = ?
        """,
        (normalized_code,),
    )
    source = await cur.fetchone()
    if source is None:
        raise BudgetOutputDisplayConfigError(404, "机构及产品指标编码不存在或未绑定机构及产品指标树")
    return source


async def _load_display_config_item(db: aiosqlite.Connection, row_key: str) -> dict[str, Any]:
    rows = await fetch_budget_display_config_items(db, active_only=False)
    for row in rows:
        if str(row["row_key"]) == row_key:
            return row
    raise BudgetOutputDisplayConfigError(404, "展示科目不存在")


def _normalize_org_product_identity(command: BudgetOutputDisplayConfigCreateCommand) -> dict[str, str | None]:
    org_product_ref = (command.org_product_ref or "").strip()
    entity_code = (command.org_product_entity_code or "").strip().upper()
    table_name = (command.org_product_table_name or "").strip()
    metric_code = (command.org_product_metric_code or "").strip().upper()
    metric_name = (command.org_product_metric_name or "").strip()
    if org_product_ref:
        parts = org_product_ref.split(":", 2)
        if len(parts) == 3:
            entity_code = entity_code or parts[0].strip().upper()
            table_name = table_name or parts[1].strip()
            metric_code = metric_code or parts[2].strip().upper()
    elif entity_code and table_name and metric_code:
        org_product_ref = f"{entity_code}:{table_name}:{metric_code}"
    return {
        "org_product_ref": org_product_ref or None,
        "org_product_entity_code": entity_code or None,
        "org_product_table_name": table_name or None,
        "org_product_metric_code": metric_code or None,
        "org_product_metric_name": metric_name or None,
    }


async def create_budget_output_display_item(
    db: aiosqlite.Connection,
    command: BudgetOutputDisplayConfigCreateCommand,
) -> dict[str, Any]:
    await ensure_budget_output_display_item_schema(db)
    data_acct_code = (command.data_acct_code or "").strip().upper()
    source = await _load_bound_runtime_metric_source(db, data_acct_code) if data_acct_code else None
    display_name = (command.display_name or (source["data_acct_name"] if source else "")).strip()
    if not display_name:
        raise BudgetOutputDisplayConfigError(400, "展示名称不能为空")

    parent_row_key = (command.parent_row_key or "").strip() or None
    insert_after_row_key = (command.insert_after_row_key or "").strip() or None
    display_view = command.display_view.strip().upper() or "TOTAL"
    level = 1
    if insert_after_row_key:
        cur = await db.execute(
            """
            SELECT row_key, display_view, parent_row_key, level, sort_order
            FROM budget_output_display_item
            WHERE row_key = ? AND is_active = 1
            """,
            (insert_after_row_key,),
        )
        after_row = await cur.fetchone()
        if after_row is None:
            raise BudgetOutputDisplayConfigError(404, "插入位置不存在")
        display_view = str(after_row["display_view"])
        parent_row_key = after_row["parent_row_key"]
        level = int(after_row["level"] or 1)
        sort_order = int(after_row["sort_order"] or 0) + 1
        await db.execute(
            """
            UPDATE budget_output_display_item
            SET sort_order = sort_order + 1, updated_at = CURRENT_TIMESTAMP
            WHERE display_view = ?
              AND COALESCE(parent_row_key, '') = COALESCE(?, '')
              AND sort_order >= ?
            """,
            (display_view, parent_row_key, sort_order),
        )
    elif parent_row_key:
        cur = await db.execute(
            """
            SELECT row_key, display_view, level
            FROM budget_output_display_item
            WHERE row_key = ? AND is_active = 1
            """,
            (parent_row_key,),
        )
        parent = await cur.fetchone()
        if parent is None:
            raise BudgetOutputDisplayConfigError(404, "父级展示科目不存在")
        display_view = str(parent["display_view"])
        level = int(parent["level"] or 1) + 1

    if insert_after_row_key:
        pass
    elif command.sort_order is None:
        cur = await db.execute(
            """
            SELECT COALESCE(MAX(sort_order), 0) + 10
            FROM budget_output_display_item
            WHERE display_view = ? AND COALESCE(parent_row_key, '') = COALESCE(?, '')
            """,
            (display_view, parent_row_key),
        )
        sort_order = int((await cur.fetchone())[0] or 10)
    else:
        sort_order = int(command.sort_order)

    row_type = "METRIC" if data_acct_code else "GROUP"
    org_product_identity = _normalize_org_product_identity(command) if data_acct_code else {
        "org_product_ref": None,
        "org_product_entity_code": None,
        "org_product_table_name": None,
        "org_product_metric_code": None,
        "org_product_metric_name": None,
    }
    row_key = await allocate_budget_display_row_key(
        db,
        display_view=display_view,
        parent_row_key=parent_row_key,
    )
    await db.execute(
        """
        INSERT INTO budget_output_display_item(
          row_key, display_view, parent_row_key, data_acct_code,
          org_product_ref, org_product_entity_code, org_product_table_name,
          org_product_metric_code, org_product_metric_name, row_type,
          display_name, value_type, level, sort_order, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(row_key) DO UPDATE SET
          parent_row_key = excluded.parent_row_key,
          data_acct_code = excluded.data_acct_code,
          org_product_ref = excluded.org_product_ref,
          org_product_entity_code = excluded.org_product_entity_code,
          org_product_table_name = excluded.org_product_table_name,
          org_product_metric_code = excluded.org_product_metric_code,
          org_product_metric_name = excluded.org_product_metric_name,
          row_type = excluded.row_type,
          display_name = excluded.display_name,
          value_type = excluded.value_type,
          level = excluded.level,
          sort_order = excluded.sort_order,
          is_active = 1,
          updated_at = CURRENT_TIMESTAMP
        """,
        (
            row_key,
            display_view,
            parent_row_key,
            data_acct_code or None,
            org_product_identity["org_product_ref"],
            org_product_identity["org_product_entity_code"],
            org_product_identity["org_product_table_name"],
            org_product_identity["org_product_metric_code"],
            org_product_identity["org_product_metric_name"],
            row_type,
            display_name,
            source["value_type"] if source else None,
            level,
            sort_order,
        ),
    )
    await db.commit()
    return await _load_display_config_item(db, row_key)


async def update_budget_output_display_item(
    db: aiosqlite.Connection,
    row_key: str,
    command: BudgetOutputDisplayConfigUpdateCommand,
) -> dict[str, Any]:
    await ensure_budget_output_display_item_schema(db)
    updates: list[str] = []
    params: list[Any] = []
    if command.data_acct_code is not None:
        data_acct_code = command.data_acct_code.strip().upper()
        if not data_acct_code:
            updates.extend([
                "data_acct_code = NULL",
                "org_product_ref = NULL",
                "org_product_entity_code = NULL",
                "org_product_table_name = NULL",
                "org_product_metric_code = NULL",
                "org_product_metric_name = NULL",
                "row_type = 'GROUP'",
                "value_type = NULL",
            ])
        else:
            source = await _load_bound_runtime_metric_source(db, data_acct_code)
            updates.extend([
                "data_acct_code = ?",
                "org_product_ref = NULL",
                "org_product_entity_code = NULL",
                "org_product_table_name = NULL",
                "org_product_metric_code = NULL",
                "org_product_metric_name = NULL",
                "row_type = 'METRIC'",
                "value_type = ?",
            ])
            params.extend([data_acct_code, source["value_type"]])
    if command.display_name is not None:
        display_name = command.display_name.strip()
        if not display_name:
            raise BudgetOutputDisplayConfigError(400, "展示名称不能为空")
        updates.append("display_name = ?")
        params.append(display_name)
    if command.sort_order is not None:
        updates.append("sort_order = ?")
        params.append(int(command.sort_order))
    if command.is_active is not None:
        updates.append("is_active = ?")
        params.append(int(command.is_active))
    if not updates:
        raise BudgetOutputDisplayConfigError(400, "没有可更新字段")

    cur = await db.execute("SELECT row_key FROM budget_output_display_item WHERE row_key = ?", (row_key,))
    if await cur.fetchone() is None:
        raise BudgetOutputDisplayConfigError(404, "展示科目不存在")
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(row_key)
    await db.execute(
        f"UPDATE budget_output_display_item SET {', '.join(updates)} WHERE row_key = ?",
        tuple(params),
    )
    await db.commit()
    return await _load_display_config_item(db, row_key)


async def delete_budget_output_display_item(db: aiosqlite.Connection, row_key: str) -> dict[str, bool]:
    await ensure_budget_output_display_item_schema(db)
    cur = await db.execute("SELECT row_key FROM budget_output_display_item WHERE row_key = ?", (row_key,))
    if await cur.fetchone() is None:
        raise BudgetOutputDisplayConfigError(404, "展示科目不存在")
    await db.execute("DELETE FROM budget_output_display_item WHERE row_key = ?", (row_key,))
    await db.commit()
    return {"ok": True}
