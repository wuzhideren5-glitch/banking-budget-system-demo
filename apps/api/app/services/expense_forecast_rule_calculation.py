"""Rule-month calculation for the expense forecast table."""
from __future__ import annotations

import ast
import json
import math
from typing import Any, Awaitable, Callable


MetricSourceMonthLoader = Callable[[int, str, str | None], Awaitable[dict[int, float]]]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = _text(value).lower()
    return text in {"1", "true", "yes", "y", "on"}


def _json_loads(text: str | None, fallback: Any) -> Any:
    raw = _text(text)
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except Exception:
        return default


def _rule_param_lookup(params: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in params:
        group_name = _text(item.get("param_group") or "common")
        key = _text(item.get("param_key"))
        if not key:
            continue
        result[key] = _text(item.get("param_value"))
        result[f"{group_name}.{key}"] = _text(item.get("param_value"))
    return result


def _if_func(condition: Any, a: Any, b: Any) -> Any:
    return a if bool(condition) else b


_ALLOWED_EXPR_FUNCTIONS: dict[str, Any] = {
    "IF": _if_func,
    "MAX": lambda *args: max(float(v) for v in args) if args else 0.0,
    "MIN": lambda *args: min(float(v) for v in args) if args else 0.0,
    "ABS": lambda v: abs(float(v)),
    "ROUND": lambda v, n=2: round(float(v), int(n)),
    "CEIL": lambda v: math.ceil(float(v)),
    "FLOOR": lambda v: math.floor(float(v)),
}


def _eval_expr_node(node: ast.AST, variables: dict[str, Any]) -> float:
    if isinstance(node, ast.Expression):
        return _eval_expr_node(node.body, variables)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return float(node.value)
        raise ValueError("表达式仅支持数值常量")
    if isinstance(node, ast.Name):
        return float(variables.get(node.id, 0.0) or 0.0)
    if isinstance(node, ast.UnaryOp):
        value = _eval_expr_node(node.operand, variables)
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return value
        if isinstance(node.op, ast.Not):
            return 0.0 if value else 1.0
    if isinstance(node, ast.BinOp):
        left = _eval_expr_node(node.left, variables)
        right = _eval_expr_node(node.right, variables)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return 0.0 if abs(right) < 1e-9 else left / right
        if isinstance(node.op, ast.Mod):
            return 0.0 if abs(right) < 1e-9 else left % right
        if isinstance(node.op, ast.Pow):
            return left ** right
    if isinstance(node, ast.Compare):
        left = _eval_expr_node(node.left, variables)
        current = True
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_expr_node(comparator, variables)
            if isinstance(op, ast.Gt):
                current = current and (left > right)
            elif isinstance(op, ast.GtE):
                current = current and (left >= right)
            elif isinstance(op, ast.Lt):
                current = current and (left < right)
            elif isinstance(op, ast.LtE):
                current = current and (left <= right)
            elif isinstance(op, ast.Eq):
                current = current and (left == right)
            elif isinstance(op, ast.NotEq):
                current = current and (left != right)
            left = right
        return 1.0 if current else 0.0
    if isinstance(node, ast.BoolOp):
        values = [_eval_expr_node(item, variables) for item in node.values]
        if isinstance(node.op, ast.And):
            return 1.0 if all(values) else 0.0
        if isinstance(node.op, ast.Or):
            return 1.0 if any(values) else 0.0
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        func_name = node.func.id.upper()
        if func_name not in _ALLOWED_EXPR_FUNCTIONS:
            raise ValueError(f"不支持的函数: {func_name}")
        args = [_eval_expr_node(arg, variables) for arg in node.args]
        return float(_ALLOWED_EXPR_FUNCTIONS[func_name](*args))
    raise ValueError("表达式包含不支持的语法")


def _evaluate_expression(expression: str, variables: dict[str, Any]) -> float:
    expr = _text(expression)
    if not expr:
        return 0.0
    tree = ast.parse(expr, mode="eval")
    return round(float(_eval_expr_node(tree, variables)), 6)


def _solve_geometric_ratio(sum_value: float, start_value: float, periods: int) -> float | None:
    if periods <= 0 or abs(start_value) < 1e-9:
        return None
    target = float(sum_value)
    start = float(start_value)
    if target <= 0 or start <= 0:
        return None
    average = target / periods
    if abs(average - start) < 1e-9:
        return 1.0
    increasing = average > start
    if increasing:
        low = 1.0
        high = 2.0

        def seq_sum(ratio: float) -> float:
            if abs(ratio - 1.0) < 1e-9:
                return start * periods
            return start * ratio * ((ratio ** periods) - 1.0) / (ratio - 1.0)

        while seq_sum(high) < target and high < 100:
            high *= 1.5
    else:
        low = 1e-6
        high = 1.0

        def seq_sum(ratio: float) -> float:
            if abs(ratio - 1.0) < 1e-9:
                return start * periods
            return start * ratio * ((ratio ** periods) - 1.0) / (ratio - 1.0)

    for _ in range(100):
        mid = (low + high) / 2
        current = seq_sum(mid)
        if abs(current - target) < 1e-9:
            return mid
        if increasing:
            if current < target:
                low = mid
            else:
                high = mid
        else:
            if current > target:
                high = mid
            else:
                low = mid
    return (low + high) / 2


def _last_reference_value(
    *,
    owner_name: str,
    subject_id: int,
    subject_name: str,
    actual_cutoff_month: int,
    from_month: int,
    actual_map: dict[tuple[str, str, int], float],
    forecast_map: dict[tuple[str, int, int], float],
) -> tuple[float | None, str]:
    if actual_cutoff_month >= 1:
        actual_value = actual_map.get((owner_name, subject_name, actual_cutoff_month))
        if actual_value is not None:
            return float(actual_value), "actual"
    for month in range(from_month - 1, 0, -1):
        forecast_value = forecast_map.get((owner_name, subject_id, month))
        if forecast_value is not None:
            return float(forecast_value), "forecast"
    return None, "none"


async def _resolve_metric_variable_value(
    *,
    year: int,
    variable: dict[str, Any],
    month: int,
    annual_input_map: dict[tuple[str, int, str], float],
    actual_map: dict[tuple[str, str, int], float],
    forecast_map: dict[tuple[str, int, int], float],
    owner_name: str,
    subject_id: int,
    subject_name: str,
    load_metric_source_month_map: MetricSourceMonthLoader,
) -> float:
    source_type = _text(variable.get("source_type"))
    source_key = _text(variable.get("source_key"))
    source_subkey = _text(variable.get("source_subkey"))
    default_value = _safe_float(variable.get("default_value"), 0.0)
    if source_type == "constant":
        if source_key:
            return _safe_float(source_key, default_value)
        return default_value
    if source_type == "annual_field":
        field_name = source_key or "capital_advice"
        return float(annual_input_map.get((owner_name, subject_id, field_name), default_value))
    if source_type == "forecast_inline":
        if source_key in {"business_submission", "capital_advice"}:
            return float(annual_input_map.get((owner_name, subject_id, source_key), default_value))
        if source_key == "month_forecast":
            return float(forecast_map.get((owner_name, subject_id, month), default_value))
        return default_value
    if source_type == "actual":
        if source_subkey.lower() == "cumulative":
            return round(
                sum(float(actual_map.get((owner_name, subject_name, mi), 0.0)) for mi in range(1, month + 1)),
                6,
            )
        return float(actual_map.get((owner_name, subject_name, month), default_value))
    if source_type == "metric_tree":
        month_map = await load_metric_source_month_map(year, source_key, source_subkey or None)
        return float(month_map.get(month, default_value))
    return default_value


async def calculate_expense_forecast_rule_months(
    *,
    rule: dict[str, Any],
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    subject_name: str,
    actual_cutoff_month: int,
    annual_input_map: dict[tuple[str, int, str], float],
    actual_map: dict[tuple[str, str, int], float],
    forecast_map: dict[tuple[str, int, int], float],
    load_metric_source_month_map: MetricSourceMonthLoader,
) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    scheme_code = _text(rule.get("scheme_code"))
    params = _rule_param_lookup(rule.get("params", []))
    from_month = max(actual_cutoff_month + 1, _safe_int(rule.get("effective_from_month"), 1))
    to_month = min(12, _safe_int(rule.get("effective_to_month"), 12))
    months = [month for month in range(from_month, to_month + 1)]
    if not months or scheme_code == "MANUAL":
        return result
    if scheme_code == "RESIDUAL_ALLOC":
        capital_advice = float(
            annual_input_map.get(
                (owner_name, subject_id, "capital_advice"),
                annual_input_map.get((owner_name, subject_id, "business_submission"), 0.0),
            )
        )
        actual_cumulative = round(
            sum(float(actual_map.get((owner_name, subject_name, month), 0.0)) for month in range(1, actual_cutoff_month + 1)),
            2,
        )
        remaining = round(capital_advice - actual_cumulative, 2)
        allow_negative = _truthy(params.get("allow_negative"))
        if remaining < 0 and not allow_negative:
            remaining = 0.0
        allocation_mode = (_text(params.get("allocation_mode")) or "progressive").lower()
        weights: list[float] = []
        if allocation_mode == "custom":
            weight_json = _json_loads(params.get("weight_json"), [])
            if isinstance(weight_json, dict):
                weights = [_safe_float(weight_json.get(str(month)), 0.0) for month in months]
            elif isinstance(weight_json, list):
                weights = [_safe_float(weight_json[idx] if idx < len(weight_json) else 0.0, 0.0) for idx, _month in enumerate(months)]
        if allocation_mode == "progressive":
            curve_type = (_text(params.get("progressive_curve_type")) or "arithmetic").lower()
            future_avg = round(remaining / len(months), 6) if months else 0.0
            last_value, last_value_source = _last_reference_value(
                owner_name=owner_name,
                subject_id=subject_id,
                subject_name=subject_name,
                actual_cutoff_month=actual_cutoff_month,
                from_month=from_month,
                actual_map=actual_map,
                forecast_map=forecast_map,
            )
            if last_value is None:
                last_value = future_avg
            if abs(last_value - future_avg) < 1e-9:
                progression_direction = "flat"
            elif last_value < future_avg:
                progression_direction = "increase"
            else:
                progression_direction = "decrease"
            raw_values: list[float] = []
            if abs(remaining) < 1e-9:
                raw_values = [0.0 for _ in months]
            elif curve_type == "geometric":
                ratio = _solve_geometric_ratio(abs(remaining), abs(last_value), len(months))
                if ratio is None:
                    curve_type = "arithmetic"
                else:
                    sign = -1.0 if remaining < 0 else 1.0
                    raw_values = [sign * abs(last_value) * (ratio ** (idx + 1)) for idx, _month in enumerate(months)]
            if not raw_values:
                if len(months) == 1:
                    step = round(remaining - last_value, 6)
                else:
                    step = (remaining - len(months) * last_value) / (len(months) * (len(months) + 1) / 2)
                raw_values = [last_value + step * (idx + 1) for idx, _month in enumerate(months)]
            allocated_total = 0.0
            for idx, month in enumerate(months):
                value = round(raw_values[idx], 2)
                allocated_total = round(allocated_total + value, 2)
                if idx == len(months) - 1:
                    value = round(remaining - (allocated_total - value), 2)
                result[month] = {
                    "value": value,
                    "basis": json.dumps(
                        {
                            "scheme": scheme_code,
                            "capital_advice": capital_advice,
                            "actual_cumulative": actual_cumulative,
                            "remaining": remaining,
                            "allocation_mode": allocation_mode,
                            "curve_type": curve_type,
                            "last_reference_value": last_value,
                            "last_reference_source": last_value_source,
                            "future_average": future_avg,
                            "progression_direction": progression_direction,
                            "raw_value": round(raw_values[idx], 6),
                            "rounding_mode": "last_month_adjust",
                        },
                        ensure_ascii=False,
                    ),
                }
            return result
        if not weights or all(abs(item) < 1e-9 for item in weights):
            weights = [1.0 for _idx, _month in enumerate(months)]
        total_weight = sum(weights) or 1.0
        allocated_total = 0.0
        for idx, month in enumerate(months):
            value = round(remaining * weights[idx] / total_weight, 2)
            allocated_total = round(allocated_total + value, 2)
            if idx == len(months) - 1:
                value = round(remaining - (allocated_total - value), 2)
            result[month] = {
                "value": value,
                "basis": json.dumps(
                    {
                        "scheme": scheme_code,
                        "capital_advice": capital_advice,
                        "actual_cumulative": actual_cumulative,
                        "remaining": remaining,
                        "weight": weights[idx],
                        "allocation_mode": allocation_mode,
                        "rounding_mode": "last_month_adjust",
                    },
                    ensure_ascii=False,
                ),
            }
        return result
    if scheme_code == "METRIC_EXPR":
        expression = params.get("metric_expr.expression") or ""
        annual_capital = float(annual_input_map.get((owner_name, subject_id, "capital_advice"), 0.0))
        annual_business = float(annual_input_map.get((owner_name, subject_id, "business_submission"), 0.0))
        actual_cumulative = round(
            sum(float(actual_map.get((owner_name, subject_name, month), 0.0)) for month in range(1, actual_cutoff_month + 1)),
            2,
        )
        for idx, month in enumerate(months):
            variables: dict[str, Any] = {
                "month_index": month,
                "remaining_months": len(months) - idx,
                "capital_advice": annual_capital,
                "business_submission": annual_business,
                "actual_cumulative": actual_cumulative,
                "base_amount": annual_capital,
            }
            for variable in rule.get("variables", []):
                variables[_text(variable.get("variable_code"))] = await _resolve_metric_variable_value(
                    year=year,
                    variable=variable,
                    month=month,
                    annual_input_map=annual_input_map,
                    actual_map=actual_map,
                    forecast_map=forecast_map,
                    owner_name=owner_name,
                    subject_id=subject_id,
                    subject_name=subject_name,
                    load_metric_source_month_map=load_metric_source_month_map,
                )
            value = round(_evaluate_expression(expression, variables), 2)
            result[month] = {
                "value": value,
                "basis": json.dumps(
                    {
                        "scheme": scheme_code,
                        "expression": expression,
                        "variables": variables,
                    },
                    ensure_ascii=False,
                ),
            }
        return result
    return result
