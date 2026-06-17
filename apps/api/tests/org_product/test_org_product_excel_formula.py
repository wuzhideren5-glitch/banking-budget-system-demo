"""Quick tests for Excel-native formula conversion."""
from app.org_product_excel_formula import (
    SheetFormulaContext,
    convert_excel_formula_to_system,
    format_metric_code_for_display,
    index_sheet_contexts,
    normalize_sheet_lookup_key,
)


def _ctx(sheet: str, entity: str, table: str, rows: dict[int, str]) -> SheetFormulaContext:
    display = {r: format_metric_code_for_display(entity, c) for r, c in rows.items()}
    return SheetFormulaContext(
        sheet_name=sheet,
        sheet_key=normalize_sheet_lookup_key(sheet),
        entity_code=entity,
        table_name=table,
        row_display_codes=display,
    )


def test_same_sheet_addition():
    current = _ctx("A01业务状况表", "A01", "业务状况表", {2: "A0101", 3: "A010101", 10: "A010102", 13: "A010103"})
    index = index_sheet_contexts([current])
    out = convert_excel_formula_to_system("=E3+E10+E13", current=current, all_contexts=index)
    assert out == "A01.01.01 + A01.01.02 + A01.01.03", out


def test_cross_sheet_sum():
    a01 = _ctx("A01业务状况表", "A01", "业务状况表", {2: "A0101"})
    a02 = _ctx("A02业务状况表", "A02", "业务状况表", {2: "A0201"})
    aa = _ctx("AA损益表", "AA", "损益表", {2: "AA46"})
    index = index_sheet_contexts([a01, a02, aa])
    out = convert_excel_formula_to_system(
        "=A01业务状况表!E2+A02业务状况表!E2",
        current=aa,
        all_contexts=index,
    )
    assert out == "A01/业务状况表/A01.01 + A02/业务状况表/A02.01", out


def test_sum_range():
    current = _ctx("A01业务状况表", "A01", "业务状况表", {2: "A0101", 3: "A010101", 4: "A010102"})
    index = index_sheet_contexts([current])
    out = convert_excel_formula_to_system("=SUM(E3:E4)", current=current, all_contexts=index)
    assert out == "SUM(A01.01.01,A01.01.02)", out


if __name__ == "__main__":
    test_same_sheet_addition()
    test_cross_sheet_sum()
    test_sum_range()
    print("ok")
