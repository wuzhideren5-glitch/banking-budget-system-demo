"""Convert Excel-native cell formulas in 取数公式 column to org-product metric formula text."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

_CROSS_SHEET_CELL_RE = re.compile(
    r"(?:'([^']+)'|([^'!+\-*/(),\s]+))!(\$?)([A-Z]{1,3})(\$?)(\d+)",
    re.IGNORECASE,
)
_CELL_RANGE_RE = re.compile(
    r"(?:'([^']+)'|([^'!+\-*/(),\s]+))!(\$?)([A-Z]{1,3})(\$?)(\d+):(\$?)([A-Z]{1,3})(\$?)(\d+)",
    re.IGNORECASE,
)
_LOCAL_RANGE_RE = re.compile(
    r"(?<![A-Z0-9.])(\$?)([A-Z]{1,3})(\$?)(\d+):(\$?)([A-Z]{1,3})(\$?)(\d+)(?![(])",
    re.IGNORECASE,
)
_CROSS_SHEET_RANGE_RE = _CELL_RANGE_RE
_LOCAL_CELL_RE = re.compile(
    r"(?<![A-Z0-9.])(\$?)([A-Z]{1,3})(\$?)(\d+)(?![:(])",
    re.IGNORECASE,
)
_SUPPORTED_FUNCS = {"SUM", "AVG", "MAX", "MIN"}


class ExcelFormulaConvertError(ValueError):
    pass


@dataclass
class SheetFormulaContext:
    sheet_name: str
    sheet_key: str
    entity_code: str
    table_name: str
    row_display_codes: dict[int, str] = field(default_factory=dict)


def format_metric_code_for_display(entity_code: str, raw_code: str) -> str:
    owner = str(entity_code or "").strip().upper()
    code = str(raw_code or "").strip().upper().replace(" ", "")
    if not owner or not code:
        return code
    if not code.startswith(owner):
        return code
    remainder = code[len(owner) :]
    if not remainder:
        return owner
    if not re.fullmatch(r"[0-9A-Z]+", remainder):
        return code
    chunks = [remainder[i : i + 2] for i in range(0, len(remainder), 2)]
    return f"{owner}.{'.'.join(chunks)}"


def normalize_sheet_lookup_key(title: str) -> str:
    key = re.sub(r"[\s_\u200b-\u200d\ufeff]+", "", str(title or "").strip())
    return key.replace("（", "(").replace("）", ")")


def build_sheet_formula_context(
    sheet_name: str,
    entity_code: str,
    table_name: str,
    header_row_idx: int,
    code_col: int,
    row_values_fn: Callable[[int, int], Any],
    normalize_code_fn: Callable[[str, Any], str],
    row_limit: int,
) -> SheetFormulaContext:
    row_display_codes: dict[int, str] = {}
    owner = str(entity_code or "").strip().upper()
    for row_idx in range(header_row_idx + 1, row_limit + 1):
        raw = row_values_fn(row_idx, code_col)
        code = normalize_code_fn(owner, raw)
        if not code:
            continue
        row_display_codes[row_idx] = format_metric_code_for_display(owner, code)
    return SheetFormulaContext(
        sheet_name=str(sheet_name or "").strip(),
        sheet_key=normalize_sheet_lookup_key(sheet_name),
        entity_code=owner,
        table_name=str(table_name or "").strip(),
        row_display_codes=row_display_codes,
    )


def index_sheet_contexts(contexts: list[SheetFormulaContext]) -> dict[str, SheetFormulaContext]:
    out: dict[str, SheetFormulaContext] = {}
    for ctx in contexts:
        out[ctx.sheet_key] = ctx
        if ctx.sheet_name:
            out[normalize_sheet_lookup_key(ctx.sheet_name)] = ctx
    return out


def _lookup_context(sheet_ref: str | None, current: SheetFormulaContext, index: dict[str, SheetFormulaContext]) -> SheetFormulaContext:
    if not sheet_ref:
        return current
    key = normalize_sheet_lookup_key(sheet_ref)
    ctx = index.get(key)
    if ctx is None:
        raise ExcelFormulaConvertError(f"未找到工作表「{sheet_ref}」的科目映射，请确认该 sheet 在同一 Excel 中且命名标准")
    return ctx


def _resolve_row_code(ctx: SheetFormulaContext, row_idx: int, *, ref_label: str) -> str:
    code = ctx.row_display_codes.get(row_idx)
    if not code:
        raise ExcelFormulaConvertError(f"{ref_label} 第 {row_idx} 行未找到科目代码")
    return code


def _to_system_ref(
    target_ctx: SheetFormulaContext,
    row_idx: int,
    *,
    current: SheetFormulaContext,
    ref_label: str,
) -> str:
    code = _resolve_row_code(target_ctx, row_idx, ref_label=ref_label)
    if target_ctx.entity_code == current.entity_code and target_ctx.table_name == current.table_name:
        return code
    if target_ctx.entity_code == current.entity_code:
        return f"{target_ctx.table_name}/{code}"
    return f"{target_ctx.entity_code}/{target_ctx.table_name}/{code}"


def _expand_range_rows(start_col: str, start_row: int, end_col: str, end_row: int) -> list[tuple[str, int]]:
    if start_col.upper() != end_col.upper():
        raise ExcelFormulaConvertError(f"暂不支持跨列区域引用：{start_col}{start_row}:{end_col}{end_row}")
    lo, hi = sorted((start_row, end_row))
    col = start_col.upper()
    return [(col, r) for r in range(lo, hi + 1)]


def _convert_cross_sheet_range(match: re.Match[str], *, current: SheetFormulaContext, index: dict[str, SheetFormulaContext]) -> str:
    sheet_ref = match.group(1) or match.group(2)
    start_col = match.group(4)
    start_row = int(match.group(6))
    end_col = match.group(8)
    end_row = int(match.group(10))
    target_ctx = _lookup_context(sheet_ref, current, index)
    cells = _expand_range_rows(start_col, start_row, end_col, end_row)
    refs = [
        _to_system_ref(target_ctx, row, current=current, ref_label=f"{sheet_ref}!{col}{row}")
        for col, row in cells
    ]
    return ",".join(refs)


def _convert_local_range(match: re.Match[str], *, current: SheetFormulaContext, index: dict[str, SheetFormulaContext]) -> str:
    start_col = match.group(2)
    start_row = int(match.group(4))
    end_col = match.group(6)
    end_row = int(match.group(8))
    cells = _expand_range_rows(start_col, start_row, end_col, end_row)
    refs = [
        _to_system_ref(current, row, current=current, ref_label=f"{col}{row}")
        for col, row in cells
    ]
    return ",".join(refs)


def _convert_cross_sheet_cell(match: re.Match[str], *, current: SheetFormulaContext, index: dict[str, SheetFormulaContext]) -> str:
    sheet_ref = match.group(1) or match.group(2)
    row_idx = int(match.group(6))
    col = match.group(4).upper()
    target_ctx = _lookup_context(sheet_ref, current, index)
    return _to_system_ref(target_ctx, row_idx, current=current, ref_label=f"{sheet_ref}!{col}{row_idx}")


def _convert_local_cell(match: re.Match[str], *, current: SheetFormulaContext, index: dict[str, SheetFormulaContext]) -> str:
    row_idx = int(match.group(4))
    col = match.group(2).upper()
    return _to_system_ref(current, row_idx, current=current, ref_label=f"{col}{row_idx}")


def convert_excel_formula_to_system(
    formula: str,
    *,
    current: SheetFormulaContext,
    all_contexts: dict[str, SheetFormulaContext],
) -> str:
    text = str(formula or "").strip()
    if not text:
        return ""
    if not text.startswith("="):
        return text

    expr = text[1:].strip()
    if not expr:
        return ""

    expr = (
        expr.replace("＋", "+")
        .replace("－", "-")
        .replace("×", "*")
        .replace("÷", "/")
        .replace("（", "(")
        .replace("）", ")")
        .replace("，", ",")
    )

    placeholders: dict[str, str] = {}

    def _stash(replacement: str) -> str:
        key = f"__REF_{len(placeholders)}__"
        placeholders[key] = replacement
        return key

    def _sub_cross_range(m: re.Match[str]) -> str:
        return _stash(_convert_cross_sheet_range(m, current=current, index=all_contexts))

    def _sub_local_range(m: re.Match[str]) -> str:
        return _stash(_convert_local_range(m, current=current, index=all_contexts))

    def _sub_cross_cell(m: re.Match[str]) -> str:
        return _stash(_convert_cross_sheet_cell(m, current=current, index=all_contexts))

    def _sub_local_cell(m: re.Match[str]) -> str:
        return _stash(_convert_local_cell(m, current=current, index=all_contexts))

    expr = _CROSS_SHEET_RANGE_RE.sub(_sub_cross_range, expr)
    expr = _CROSS_SHEET_CELL_RE.sub(_sub_cross_cell, expr)
    expr = _LOCAL_RANGE_RE.sub(_sub_local_range, expr)
    expr = _LOCAL_CELL_RE.sub(_sub_local_cell, expr)

    for key, value in placeholders.items():
        expr = expr.replace(key, value)

    def _upper_func(m: re.Match[str]) -> str:
        name = m.group(1).upper()
        if name in _SUPPORTED_FUNCS:
            return f"{name}("
        return m.group(0)

    expr = re.sub(r"([A-Za-z_][A-Za-z0-9_]*)\(", _upper_func, expr)
    expr = re.sub(r"\s*([+\-*])\s*", r" \1 ", expr)
    expr = re.sub(r"\s+", " ", expr).strip()
    return expr
