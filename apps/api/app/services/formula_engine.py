"""Formula parsing, validation, and calculation helpers."""
from __future__ import annotations

import ast

import app.core.aiosqlite_compat as aiosqlite
from fastapi import HTTPException

from app.formula_refs import (
    ANGLE_RUNTIME_METRIC_REF_CODE_RE,
    RUNTIME_METRIC_REF_CODE_RE,
    extract_formula_codes,
)


def normalize_formula(value: str | None) -> str:
    return (value or "").strip()


async def load_runtime_metric_scope_map(db: aiosqlite.Connection) -> dict[str, bool]:
    cur = await db.execute(
        """
        SELECT data_acct_code, scope_code
        FROM data_account_metric_binding
        WHERE is_active = 1
        """
    )
    rows = await cur.fetchall()
    return {str(r[0]).strip().upper(): str(r[1] or "").strip().upper() == "CORP" for r in rows if r[0]}


def validate_formula_reference_scope(
    *,
    formula: str | None,
    target_is_all: bool,
    scope_by_code: dict[str, bool],
    formula_label: str,
) -> None:
    normalized = normalize_formula(formula)
    if not normalized:
        return
    ref_codes = sorted(extract_formula_codes(normalized))
    if not ref_codes:
        return
    missing_codes = [code for code in ref_codes if code not in scope_by_code]
    if missing_codes:
        raise HTTPException(
            status_code=400,
            detail=f"{formula_label}引用了不存在的机构及产品指标编码：{', '.join(missing_codes)}",
        )


def formula_ref_aliases(formula: str | None) -> dict[str, str]:
    return {code: f"V{i}" for i, code in enumerate(sorted(extract_formula_codes(formula)), start=1)}


def prepare_formula_expression(formula: str | None, aliases: dict[str, str] | None = None) -> str:
    expr = normalize_formula(formula)
    if not expr:
        return ""
    aliases = aliases or {}
    expr = ANGLE_RUNTIME_METRIC_REF_CODE_RE.sub(
        lambda match: aliases.get(match.group(1).upper(), match.group(1)),
        expr,
    )
    expr = RUNTIME_METRIC_REF_CODE_RE.sub(lambda match: aliases.get(match.group(0).upper(), match.group(0)), expr)
    translate_map = str.maketrans({
        "（": "(",
        "）": ")",
        "，": ",",
        "＋": "+",
        "－": "-",
        "×": "*",
        "÷": "/",
    })
    return expr.translate(translate_map)


def _eval_formula_ast(node: ast.AST, values: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval_formula_ast(node.body, values)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError("公式包含非法常量")
    if isinstance(node, ast.Name):
        return float(values.get(node.id, 0.0))
    if isinstance(node, ast.BinOp):
        left = _eval_formula_ast(node.left, values)
        right = _eval_formula_ast(node.right, values)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("division by zero")
            return left / right
        raise ValueError("公式仅支持 + - * / 运算")
    if isinstance(node, ast.UnaryOp):
        val = _eval_formula_ast(node.operand, values)
        if isinstance(node.op, ast.UAdd):
            return +val
        if isinstance(node.op, ast.USub):
            return -val
        raise ValueError("公式一元运算不合法")
    if isinstance(node, ast.Call):
        if node.keywords:
            raise ValueError("函数调用不支持命名参数")
        if not isinstance(node.func, ast.Name):
            raise ValueError("函数调用不合法")
        fn = node.func.id.upper()
        args = [_eval_formula_ast(arg, values) for arg in node.args]
        if fn == "SUM":
            return float(sum(args))
        if fn == "AVG":
            return float(sum(args) / len(args)) if args else 0.0
        if fn == "MAX":
            return float(max(args)) if args else 0.0
        if fn == "MIN":
            return float(min(args)) if args else 0.0
        raise ValueError("仅支持 SUM/AVG/MAX/MIN 函数")
    raise ValueError("公式语法不合法")


def calculate_formula_value(formula: str | None, values: dict[str, float]) -> float:
    value, _ = try_calculate_formula_value(formula, values)
    return value


def try_calculate_formula_value(
    formula: str | None, values: dict[str, float]
) -> tuple[float, str | None]:
    aliases = formula_ref_aliases(formula)
    expression = prepare_formula_expression(formula, aliases)
    if not expression:
        return 0.0, None
    eval_values = {aliases.get(code, code): value for code, value in values.items()}
    try:
        parsed = ast.parse(expression, mode="eval")
        return float(_eval_formula_ast(parsed, eval_values)), None
    except ZeroDivisionError:
        return 0.0, "#DIV/0!"
    except Exception:
        return 0.0, "#ERROR!"
