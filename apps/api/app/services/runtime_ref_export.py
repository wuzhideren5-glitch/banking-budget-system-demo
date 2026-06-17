from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import aiosqlite
from openpyxl import Workbook
from openpyxl.styles import Font

from app.core.db_paths import common_db_path
from app.services.runtime_metric_refs import load_org_product_metric_refs_by_runtime_ref_code
from app.services.org_product_runtime_catalog import org_product_runtime_products_cte


RUNTIME_REF_EXPORT_HEADERS = (
    "指标路径",
    "机构及产品指标编码",
    "产品代码",
    "机构及产品指标主键",
    "机构及产品指标名称",
    "预算数计算公式",
    "实际数计算公式",
    "所属机构及产品代码",
    "所属机构及产品名称",
    "数值类型",
    "备注",
    "是否公式计算",
    "是否允许手工补录",
    "机构产品引用数量",
    "机构产品来源",
)

RUNTIME_REF_INTRO_ROWS = (
    ("定位", "机构及产品指标编码直接来自机构及产品指标体系主键，不作为独立配置入口"),
    ("唯一配置入口", "机构及产品指标"),
    ("主键规则", "兼容读模型编码与机构及产品指标编码保持同一业务含义"),
    ("导入限制", "本文件用于查看和核对机构及产品指标编码，不作为独立配置导入模板"),
)


async def _load_metric_path_labels(db: aiosqlite.Connection) -> dict[str, str]:
    cur = await db.execute(
        """
        SELECT node_code, node_name, parent_code
        FROM data_account_metric_node
        """
    )
    rows = await cur.fetchall()
    by_code = {
        str(r[0]): {
            "name": str(r[1] or ""),
            "parent": str(r[2]) if r[2] is not None else None,
        }
        for r in rows
    }
    memo: dict[str, str] = {}

    def path_for(code: str) -> str:
        if code in memo:
            return memo[code]
        node = by_code.get(code)
        if not node:
            memo[code] = ""
            return ""
        parent = node["parent"]
        parts = []
        if parent:
            parent_path = path_for(parent)
            if parent_path:
                parts.append(parent_path)
        parts.append(node["name"])
        memo[code] = " / ".join([p for p in parts if p])
        return memo[code]

    return {code: path_for(code) for code in by_code}


async def build_runtime_ref_export_workbook(db: aiosqlite.Connection) -> BytesIO:
    cur = await db.execute(
        f"""
        {org_product_runtime_products_cte()}
        SELECT d.data_acct_code, d.data_acct_name,
               d.budget_formula, d.actual_formula, d.value_type, d.remark,
               d.need_calc, d.formula_calc_mode, d.allow_manual_entry,
               b.metric_node_code, b.scope_code, p.product_name
        FROM data_account d
        LEFT JOIN data_account_metric_binding b ON b.data_acct_code = d.data_acct_code AND b.is_active = 1
        LEFT JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
        LEFT JOIN org_product_runtime_products p ON b.scope_type = 'PRODUCT' AND p.product_code = b.scope_code
        ORDER BY d.data_acct_code
        """
    )
    rows = await cur.fetchall()
    metric_path_labels = await _load_metric_path_labels(db)
    cur = await db.execute(
        """
        SELECT b.data_acct_code, b.metric_node_code, b.scope_code,
               b.data_acct_code
        FROM data_account_metric_binding b
        ORDER BY b.data_acct_code
        """
    )
    binding_rows = await cur.fetchall()
    org_product_refs_by_data = await load_org_product_metric_refs_by_runtime_ref_code(db)
    bindings_by_data: dict[str, list[tuple[str, str, str, str]]] = {}
    for br in binding_rows:
        binding_code = str(br[0] or "")
        metric_node_code = str(br[1] or "")
        scope_code = str(br[2] or "")
        data_code = str(br[3] or "")
        if not data_code:
            continue
        bindings_by_data.setdefault(data_code, []).append(
            (
                binding_code,
                metric_path_labels.get(metric_node_code, ""),
                metric_node_code,
                scope_code,
            )
        )

    return _build_workbook(rows, bindings_by_data, org_product_refs_by_data)


async def export_runtime_refs_workbook(common_db: Path | str | None = None) -> BytesIO:
    path = common_db if common_db is not None else common_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        return await build_runtime_ref_export_workbook(db)


def _build_workbook(
    rows: list[Any],
    bindings_by_data: dict[str, list[tuple[str, str, str, str]]],
    org_product_refs_by_data: dict[str, list[str]] | None = None,
) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "机构及产品指标编码清单"
    intro_ws = wb.create_sheet("运行说明", 0)
    intro_ws.cell(row=1, column=1, value="项目").font = Font(bold=True)
    intro_ws.cell(row=1, column=2, value="说明").font = Font(bold=True)
    for row_idx, (item, note) in enumerate(RUNTIME_REF_INTRO_ROWS, start=2):
        intro_ws.cell(row=row_idx, column=1, value=item)
        intro_ws.cell(row=row_idx, column=2, value=note)
    intro_ws.column_dimensions["A"].width = 18
    intro_ws.column_dimensions["B"].width = 88

    header_to_col = {h: idx for idx, h in enumerate(RUNTIME_REF_EXPORT_HEADERS, start=1)}
    for idx, header in enumerate(RUNTIME_REF_EXPORT_HEADERS, start=1):
        cell = ws.cell(row=1, column=idx, value=header)
        cell.font = Font(bold=True)

    row_idx = 2
    for r in rows:
        data_code = str(r[0] or "")
        org_product_refs = (org_product_refs_by_data or {}).get(data_code.upper(), [])
        row_bindings = bindings_by_data.get(data_code) or [("", "", "", "")]
        for _binding_code, metric_path, metric_node_code, scope_code in row_bindings:
            ws.cell(row=row_idx, column=header_to_col["指标路径"], value=metric_path)
            ws.cell(row=row_idx, column=header_to_col["机构及产品指标编码"], value=metric_node_code)
            ws.cell(row=row_idx, column=header_to_col["产品代码"], value=scope_code)
            ws.cell(row=row_idx, column=header_to_col["机构及产品指标主键"], value=r[0])
            ws.cell(row=row_idx, column=header_to_col["机构及产品指标名称"], value=r[1])
            ws.cell(row=row_idx, column=header_to_col["预算数计算公式"], value=r[2])
            ws.cell(row=row_idx, column=header_to_col["实际数计算公式"], value=r[3])
            prod_code = str(scope_code or "").strip()
            prod_name = "全行" if prod_code == "CORP" else str(r[11] or "")
            ws.cell(row=row_idx, column=header_to_col["所属机构及产品代码"], value=prod_code)
            ws.cell(row=row_idx, column=header_to_col["所属机构及产品名称"], value=prod_name)
            ws.cell(row=row_idx, column=header_to_col["数值类型"], value=r[4])
            ws.cell(row=row_idx, column=header_to_col["备注"], value=r[5])
            ws.cell(row=row_idx, column=header_to_col["是否公式计算"], value=int(r[7] or 0))
            ws.cell(row=row_idx, column=header_to_col["是否允许手工补录"], value=int(1 if r[8] is None else r[8]))
            ws.cell(row=row_idx, column=header_to_col["机构产品引用数量"], value=len(org_product_refs))
            ws.cell(row=row_idx, column=header_to_col["机构产品来源"], value="\n".join(org_product_refs))
            row_idx += 1

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
