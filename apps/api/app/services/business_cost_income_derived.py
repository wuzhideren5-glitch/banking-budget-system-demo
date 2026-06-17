"""Derived-value rules for BCIR items (manual entry vs auto-calculated)."""
from __future__ import annotations

from typing import Any, Literal

DerivedOp = Literal["add", "sub", "ledger_ops_net"]
BusinessCostIncomeEntryMode = Literal["manual", "manual_preferred", "computed", "rollup", "binding", "indicator"]
BusinessCostIncomeManualEntryMode = Literal["disabled", "manual", "manual_preferred"]

# These input leaves allow manual entry and override the bound/auto value.
PREFERRED_MANUAL_BCIR_INPUT_ITEM_NAMES: frozenset[str] = frozenset(
    {
        "营销费用",
        "积分",
        "运营费用",
        "存款保险费（减项）",
    }
)

# These input leaves remain manual/supplemental entry items.
SUPPLEMENTAL_BCIR_INPUT_ITEM_NAMES: frozenset[str] = frozenset(
    {
        "专项费用",
        "专项运营",
        "内催费用",
        "其他风险运营",
        "销售人力费用",
        "新客营销支出",
        "存客营销支出",
        "新开通客户投入",
        "新发放投入",
    }
)

MANUAL_BCIR_INPUT_ITEM_NAMES: frozenset[str] = frozenset(
    {*PREFERRED_MANUAL_BCIR_INPUT_ITEM_NAMES, *SUPPLEMENTAL_BCIR_INPUT_ITEM_NAMES}
)

# These output leaves allow manual entry and override the bound/auto value.
PREFERRED_MANUAL_BCIR_OUTPUT_ITEM_NAMES: frozenset[str] = frozenset(
    {
        "营业收入",
        "营业收入（还原）",
        "日均LUM",
        "日均AuM",
    }
)

# These output leaves remain supplemental/manual-entry items.
SUPPLEMENTAL_BCIR_OUTPUT_ITEM_NAMES: frozenset[str] = frozenset(
    {
        "内催回收额",
        "新客日均LUM",
        "存客日均LUM",
        "新发放LUM",
        "新发放LUM（标服）",
        "存客日均AuM",
        "新客AuM余额",
        "平均有效客户数",
        "新开通客户数",
        "MFAU客户数",
    }
)

MANUAL_BCIR_OUTPUT_ITEM_NAMES: frozenset[str] = frozenset(
    {*PREFERRED_MANUAL_BCIR_OUTPUT_ITEM_NAMES, *SUPPLEMENTAL_BCIR_OUTPUT_ITEM_NAMES}
)

# Product-local metric suffixes for 运营费用（不含存款保险费） ledger bridge.
LEDGER_OPS_EXPENSE_SUFFIX = "05.01.01.02.002"
LEDGER_DEPOSIT_INSURANCE_SUFFIX = "01.02.05.01.028"

# Applied in order; each step may read values produced by earlier steps.
INPUT_DERIVED_SPECS: tuple[tuple[str, DerivedOp, tuple[str, ...]], ...] = (
    ("风险运营费用", "add", ("内催费用", "其他风险运营")),
    ("运营费用（不含存款保险费）", "ledger_ops_net", ()),
    ("客户运营费用", "sub", ("运营费用（不含存款保险费）", "风险运营费用")),
    ("其他客户运营", "sub", ("客户运营费用", "专项费用")),
    ("营销支出", "add", ("营销费用", "积分", "销售人力费用")),
    ("业务支出", "add", ("营销支出", "运营费用（不含存款保险费）")),
)

B_LINE_INPUT_DERIVED_SPECS: tuple[tuple[str, DerivedOp, tuple[str, ...]], ...] = (
    ("风险运营费用", "add", ("内催费用", "其他风险运营")),
    ("其他客户运营", "sub", ("客户运营费用", "专项运营")),
    ("运营费用（不含存款保险费）", "add", ("客户运营费用", "风险运营费用")),
    ("营销支出", "add", ("营销费用", "积分", "销售人力费用")),
    ("营销支出（客户维度）", "add", ("新客营销支出", "存客营销支出")),
    ("业务支出合计", "add", ("营销支出", "运营费用（不含存款保险费）")),
)

A_LINE_EXTENDED_DERIVED_SPECS: tuple[tuple[str, DerivedOp, tuple[str, ...]], ...] = (
    ("营销支出（客户维度）", "add", ("新客营销支出", "存客营销支出")),
)

DERIVED_INPUT_ITEM_NAMES: frozenset[str] = frozenset(
    name
    for specs in (INPUT_DERIVED_SPECS, B_LINE_INPUT_DERIVED_SPECS, A_LINE_EXTENDED_DERIVED_SPECS)
    for name, _op, _refs in specs
)


def _input_derived_specs(name_to_id: dict[str, int]) -> tuple[tuple[str, DerivedOp, tuple[str, ...]], ...]:
    if "业务支出合计" in name_to_id:
        return B_LINE_INPUT_DERIVED_SPECS
    if "营销支出（客户维度）" in name_to_id:
        return (*INPUT_DERIVED_SPECS, *A_LINE_EXTENDED_DERIVED_SPECS)
    return INPUT_DERIVED_SPECS


def bcir_input_entry_mode(item_name: str, *, has_children: bool) -> str:
    name = str(item_name or "").strip()
    if name in PREFERRED_MANUAL_BCIR_INPUT_ITEM_NAMES:
        return "manual_preferred"
    if name in SUPPLEMENTAL_BCIR_INPUT_ITEM_NAMES:
        return "manual"
    if name in DERIVED_INPUT_ITEM_NAMES:
        return "computed"
    if has_children:
        return "rollup"
    if name:
        return "binding"
    return "rollup"


def bcir_output_entry_mode(item_name: str, *, has_children: bool) -> str:
    name = str(item_name or "").strip()
    if has_children:
        return "rollup"
    if name in PREFERRED_MANUAL_BCIR_OUTPUT_ITEM_NAMES:
        return "manual_preferred"
    if name in SUPPLEMENTAL_BCIR_OUTPUT_ITEM_NAMES:
        return "manual"
    if name:
        return "binding"
    return "rollup"


def bcir_item_entry_mode(
    section: str,
    item_name: str,
    *,
    has_children: bool,
) -> BusinessCostIncomeEntryMode:
    normalized_section = str(section or "").strip()
    if normalized_section == "input":
        return bcir_input_entry_mode(item_name, has_children=has_children)
    if normalized_section == "output":
        return bcir_output_entry_mode(item_name, has_children=has_children)
    return "indicator"


def default_bcir_manual_entry_mode(
    section: str,
    item_name: str,
    *,
    has_children: bool,
) -> BusinessCostIncomeManualEntryMode:
    entry_mode = bcir_item_entry_mode(section, item_name, has_children=has_children)
    if entry_mode == "manual_preferred":
        return "manual_preferred"
    if entry_mode == "manual":
        return "manual"
    return "disabled"


def effective_bcir_item_entry_mode(
    section: str,
    item_name: str,
    *,
    has_children: bool,
    manual_entry_mode: str | None,
) -> BusinessCostIncomeEntryMode:
    normalized_manual = str(manual_entry_mode or "").strip().lower()
    if normalized_manual == "manual_preferred":
        return "manual_preferred"
    if normalized_manual == "manual":
        return "manual"
    if normalized_manual == "disabled":
        base_mode = bcir_item_entry_mode(section, item_name, has_children=has_children)
        if base_mode in {"manual", "manual_preferred"}:
            if has_children:
                return "rollup"
            return "binding" if str(item_name or "").strip() else "rollup"
        return base_mode
    return bcir_item_entry_mode(section, item_name, has_children=has_children)


def is_manual_bcir_input_item(item_name: str) -> bool:
    return str(item_name or "").strip() in MANUAL_BCIR_INPUT_ITEM_NAMES


def is_manual_bcir_output_item(item_name: str) -> bool:
    return str(item_name or "").strip() in MANUAL_BCIR_OUTPUT_ITEM_NAMES


def is_manual_bcir_item(section: str, item_name: str, *, has_children: bool = False) -> bool:
    return bcir_item_entry_mode(section, item_name, has_children=has_children) in {
        "manual",
        "manual_preferred",
    }


def is_manual_bcir_item_for_mode(
    section: str,
    item_name: str,
    *,
    has_children: bool = False,
    manual_entry_mode: str | None,
) -> bool:
    return effective_bcir_item_entry_mode(
        section,
        item_name,
        has_children=has_children,
        manual_entry_mode=manual_entry_mode,
    ) in {"manual", "manual_preferred"}


def _item_amount(
    aggregates: dict[tuple[str, int, str], float],
    *,
    section: str,
    item_id: int,
    field: str,
) -> float:
    return float(aggregates.get((section, item_id, field), 0.0) or 0.0)


def _resolve_item_id(
    name_to_id: dict[str, int],
    ref_name: str,
) -> int | None:
    item_id = name_to_id.get(str(ref_name or "").strip())
    return int(item_id) if item_id is not None else None


def _ledger_ops_net_amount(
    aggregates: dict[tuple[str, int, str], float],
    *,
    section: str,
    name_to_id: dict[str, int],
    field: str,
) -> float:
    ops_id = _resolve_item_id(name_to_id, "运营费用")
    deposit_id = _resolve_item_id(name_to_id, "存款保险费（减项）")
    if ops_id is None or deposit_id is None:
        return 0.0
    ops_amount = _item_amount(aggregates, section=section, item_id=ops_id, field=field)
    deposit_amount = _item_amount(aggregates, section=section, item_id=deposit_id, field=field)
    if abs(ops_amount) < 1e-12 and abs(deposit_amount) < 1e-12:
        stored_id = _resolve_item_id(name_to_id, "运营费用（不含存款保险费）")
        if stored_id is not None:
            return _item_amount(aggregates, section=section, item_id=stored_id, field=field)
        return 0.0
    return ops_amount - deposit_amount


def _derive_amount(
    op: DerivedOp,
    refs: tuple[str, ...],
    *,
    section: str,
    name_to_id: dict[str, int],
    aggregates: dict[tuple[str, int, str], float],
    field: str,
) -> float:
    if op == "ledger_ops_net":
        return _ledger_ops_net_amount(aggregates, section=section, name_to_id=name_to_id, field=field)
    ref_ids = [_resolve_item_id(name_to_id, ref) for ref in refs]
    if any(item_id is None for item_id in ref_ids):
        return 0.0
    amounts = [
        _item_amount(aggregates, section=section, item_id=int(item_id), field=field)
        for item_id in ref_ids
        if item_id is not None
    ]
    if op == "add":
        return sum(amounts)
    if op == "sub" and len(amounts) >= 2:
        return amounts[0] - amounts[1]
    return 0.0


def apply_bcir_input_derived_values(
    items: list[dict[str, Any]],
    aggregates: dict[tuple[str, int, str], float],
    *,
    month_cells: dict[tuple[str, int, str], float] | None = None,
    last_year_actuals: dict[tuple[str, int], float] | None = None,
    report_month: int | None = None,
) -> None:
    """Fill computed input item amounts in-place; manual leaves stay as stored."""
    input_items = [item for item in items if str(item.get("section")) == "input"]
    name_to_id = {str(item["name"]): int(item["id"]) for item in input_items}
    derived_specs = _input_derived_specs(name_to_id)

    for field in ("actual", "budget", "forecast"):
        for name, op, refs in derived_specs:
            item_id = name_to_id.get(name)
            if item_id is None:
                continue
            amount = _derive_amount(
                op,
                refs,
                section="input",
                name_to_id=name_to_id,
                aggregates=aggregates,
                field=field,
            )
            aggregates[("input", item_id, field)] = round(float(amount), 6)

    if month_cells is not None and report_month is not None:
        for field in ("actual", "budget", "forecast"):
            for name, op, refs in derived_specs:
                item_id = name_to_id.get(name)
                if item_id is None:
                    continue
                amount = _derive_amount(
                    op,
                    refs,
                    section="input",
                    name_to_id=name_to_id,
                    aggregates=month_cells,
                    field=field,
                )
                month_cells[("input", item_id, field)] = round(float(amount), 6)

    if last_year_actuals is not None:
        ly_field_map: dict[tuple[str, int, str], float] = {
            (str(section), int(item_id), "actual"): float(value or 0.0)
            for (section, item_id), value in last_year_actuals.items()
        }
        for name, op, refs in derived_specs:
            item_id = name_to_id.get(name)
            if item_id is None:
                continue
            amount = _derive_amount(
                op,
                refs,
                section="input",
                name_to_id=name_to_id,
                aggregates=ly_field_map,
                field="actual",
            )
            last_year_actuals[("input", item_id)] = round(float(amount), 6)


def uses_derived_input_amount(item_name: str) -> bool:
    return str(item_name or "").strip() in DERIVED_INPUT_ITEM_NAMES
