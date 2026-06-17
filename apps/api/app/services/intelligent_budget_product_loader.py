"""从数据库加载产品配置，替代硬编码的 _default_product_profiles()."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.services.intelligent_budget_solver import IntelligentBudgetProductProfile
from app.services.org_product_metric_runtime_snapshot import (
    load_org_product_metric_payload_from_runtime_tree,
    load_org_product_metric_table_rows_from_runtime_tree,
)


def load_product_profiles_from_db(
    *,
    common_db_path: str | Path,
    budget_db_path: str | Path,
    version_id: int | None = None,
    budget_actual: int = 0,  # 0=预算, 1=实际
) -> list[IntelligentBudgetProductProfile]:
    """从运行指标树 + budget_data 读取产品配置。

    每个产品取 12 个月数据的年化合计。
    """
    common = sqlite3.connect(str(common_db_path))
    common.row_factory = sqlite3.Row

    budget = sqlite3.connect(str(budget_db_path))
    budget.row_factory = sqlite3.Row

    try:
        # 1. 读取所有有业务状况表的产品
        entities = [
            {"entity_code": row["entity_code"], "entity_name": row["entity_name"]}
            for row in load_org_product_metric_table_rows_from_runtime_tree(common)
            if row["table_name"] == "业务状况表"
            and row["entity_code"] not in ("A", "AA", "AB", "B", "C", "D", "E", "F")
        ]

        # 2. 确定 version_id
        if version_id is None:
            vrow = budget.execute(
                "SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1"
            ).fetchone()
            version_id = int(vrow["version_id"]) if vrow else 1

        # 3. 为每个产品读预算数据并计算关键指标
        profiles: list[IntelligentBudgetProductProfile] = []

        for entity in entities:
            ec = entity["entity_code"]
            en = entity["entity_name"]

            # 读取全年合计值
            metric_values = _read_product_metric_totals(
                budget, common, ec, version_id, budget_actual
            )

            ls = metric_values.get("loan_scale", 0) or 0
            yi = metric_values.get("interest_income", 0) or 0
            rc = metric_values.get("risk_cost", 0) or 0
            ex = metric_values.get("expense", 0) or 0
            pf = metric_values.get("profit", 0) or 0

            # 非贷款产品: 用对应的业务规模替代 loan_scale
            # A02 微账户 → 存款日均 (.13)  A04 财富 → 管理资产日均 (.13)  F01 司库 → 同业资产日均 (.25)
            yield_rate = 0.05  # 默认值，后续会覆盖
            is_non_loan = ec in ("A02", "A04", "F01")

            if is_non_loan and ls == 0:
                managed = metric_values.get("managed_scale", 0) or 0
                interbank = metric_values.get("interbank_daily_avg", 0) or 0
                # 非贷产品的业务规模仅用于计算收益率，不计入贷款总量
                biz_scale = managed if managed > 0 else interbank
                if biz_scale > 0:
                    # 从利润反推隐含收益率
                    ftp = metric_values.get("ftp_income", 0) or 0
                    fee = metric_values.get("fee_income", 0) or 0
                    iexp = metric_values.get("interest_expense", 0) or 0
                    if ec == "A02":
                        # 存款: 收益率 ≈ (FTP收入 - 利息支出) / 存款规模
                        net_ftp = ftp - iexp
                        yield_rate = net_ftp / biz_scale if net_ftp > 0 else pf * 0.35 / biz_scale
                    elif ec == "A04":
                        # 财富: 收益率 = 手续费收入 / 管理规模
                        yield_rate = fee / biz_scale if fee > 0 else pf * 0.75 / biz_scale
                    elif ec == "F01":
                        # 司库: 收益率 = (同业利息收入 - 同业利息支出) / 同业规模
                        net_int = yi - iexp
                        yield_rate = net_int / biz_scale if net_int > 0 else pf * 0.30 / biz_scale

            # 判断是否贷款类产品
            has_loan_data = bool(
                metric_values.get("loan_scale", 0)
                or metric_values.get("loan_balance", 0)
                or metric_values.get("interest_income", 0)
            )

            # 如果贷款规模为 0 但有利息收入，反推规模 (假设约6%收益率)
            # 仅对贷款类产品做反推，非贷款和纯成本中心不适用
            if ls == 0 and yi > 0 and has_loan_data and not is_non_loan:
                ls = yi / 0.06
            # 如果贷款规模仍为 0 但有正利润，用利润反推 (假设约2%利润率)
            # 亏损/成本中心不反推
            if ls == 0 and pf > 0 and has_loan_data and not is_non_loan:
                ls = abs(pf) / 0.02
            np = metric_values.get("npl_balance", 0) or 0
            pv = metric_values.get("provision_balance", 0) or 0

            # 计算比率，避免除零
            if is_non_loan:
                # 非贷产品风险极低，固定成本率
                yield_rate = max(yield_rate, 0.001)
                risk_cost_rate = 0.0005
            else:
                yield_rate = yi / ls if ls > 0 else 0.05
                risk_cost_rate = rc / ls if ls > 0 else 0.015

            # 如果 DB 中所有关键指标均为 0，使用基于产品类型的合理默认值
            if ls == 0 and pf == 0 and yi == 0:
                defaults = _product_defaults(ec, en)
                ls = defaults["loan_scale"]
                yield_rate = defaults["yield_rate"]
                ex = defaults["expense_amount"]
                pf = defaults["profit"]
                np = defaults["npl_balance"]
                pv = defaults["provision_balance"]
                risk_cost_rate = defaults["risk_cost_rate"]

            profiles.append(
                IntelligentBudgetProductProfile(
                    product_code=ec,
                    product_name=en,
                    loan_scale=round(ls, 2),
                    yield_rate=round(yield_rate, 6),
                    expense_amount=round(ex, 2),
                    opening_npl_balance=round(np, 2),
                    opening_provision_balance=round(pv, 2),
                    risk_cost_rate=round(risk_cost_rate, 6),
                    baseline_profit_contribution=round(pf, 2),
                )
            )

        return profiles

    finally:
        common.close()
        budget.close()


def _product_defaults(entity_code: str, entity_name: str) -> dict[str, float]:
    """当 DB 无数据时，根据产品类型提供合理默认值（基于微众银行实际量级）。

    单位统一为元。非贷款产品不设虚拟贷款规模。
    """
    # 按产品代码精确配比，避免前缀聚合导致总量虚高
    # 格式: (业务规模_元, 收益率, 费用_元, 不良余额_元, 拨备余额_元, 风险成本率, 利润_元)
    # 非贷款产品 (A02/A04/F01) 的业务规模为对应业务的规模（非贷款）
    by_product: dict[str, tuple] = {
        # 零售/消费金融
        "A01": (200_000_000_000, 0.085,  8_000_000_000, 3_500_000_000, 4_200_000_000, 0.017, 8_400_000_000),  # 微粒贷 2000亿
        "A03": (50_000_000_000,  0.078,  2_500_000_000,   900_000_000, 1_100_000_000, 0.018, 1_900_000_000),  # 汽车金融 500亿
        "A05": (6_000_000_000,   0.105,    400_000_000,   100_000_000,   120_000_000, 0.017,   100_000_000),  # 小鹅 60亿
        # 非贷款零售
        "A02": (300_000_000_000, 0.012,  1_200_000_000,           0,           0, 0.0005, 6_000_000_000),  # 微账户存款 3000亿
        "A04": (400_000_000_000, 0.008,  2_000_000_000,           0,           0, 0.0005, 6_200_000_000),  # 财富管理 4000亿
        # 对公/金融市场
        "B01": (150_000_000_000, 0.058,  8_000_000_000, 2_000_000_000, 2_500_000_000, 0.013, 5_900_000_000),  # 企业金融 1500亿
        "B02": (30_000_000_000,  0.045,  2_000_000_000,   400_000_000,   500_000_000, 0.012,   800_000_000),  # 金融市场 300亿
        # 支撑/成本中心
        "C01": (2_500_000_000,   0.035,    800_000_000,    30_000_000,    40_000_000, 0.010,  -300_000_000),  # 国内业务 25亿
        "C02": (0,               0.000,  2_000_000_000,           0,           0, 0.000, -1_100_000_000),  # 国内研发 纯成本
        "D01": (4_000_000_000,   0.042,  1_500_000_000,    60_000_000,    80_000_000, 0.013,  -200_000_000),  # 国际业务 40亿
        "E01": (1_800_000_000,   0.038,    600_000_000,    25_000_000,    30_000_000, 0.011,   -10_000_000),  # 导流 18亿
        "F01": (100_000_000_000, 0.028,  3_000_000_000,           0,           0, 0.003, 3_100_000_000),  # 司库 1000亿
    }

    defaults = by_product.get(entity_code)
    if defaults is None:
        # 未知产品回退到保守值
        prefix = entity_code[0] if entity_code else "A"
        fallback = {
            "A": (200_000_000_000, 0.080,  8_000_000_000, 3_000_000_000, 3_500_000_000, 0.015, 7_000_000_000),
            "B": (100_000_000_000, 0.050,  5_000_000_000, 1_500_000_000, 1_800_000_000, 0.012, 4_000_000_000),
            "C": (2_000_000_000,   0.030,  1_000_000_000,    30_000_000,    35_000_000, 0.010,  -500_000_000),
            "D": (4_000_000_000,   0.040,  1_500_000_000,    60_000_000,    70_000_000, 0.012,  -200_000_000),
            "E": (1_500_000_000,   0.035,    600_000_000,    20_000_000,    25_000_000, 0.010,   -50_000_000),
            "F": (80_000_000_000,  0.025,  2_500_000_000,           0,           0, 0.003, 2_000_000_000),
        }
        defaults = fallback.get(prefix, fallback["A"])

    ls, yr, ex, np, pv, rc, pf = defaults

    return {
        "loan_scale": float(ls),
        "yield_rate": float(yr),
        "expense_amount": float(ex),
        "npl_balance": float(np),
        "provision_balance": float(pv),
        "risk_cost_rate": float(rc),
        "profit": float(pf),
    }


def _read_product_metric_totals(
    budget: sqlite3.Connection,
    common: sqlite3.Connection,
    entity_code: str,
    version_id: int,
    budget_actual: int,
) -> dict[str, float]:
    """读取产品的高层指标 - 递归汇总子节点。"""
    # 读取所有 budget_data 行
    rows = budget.execute(
        """SELECT data_acct_code, SUM(value) as total
           FROM budget_data
           WHERE product_code = ?
             AND version_id = ?
             AND budget_actual = ?
           GROUP BY data_acct_code""",
        (entity_code, version_id, budget_actual),
    ).fetchall()

    all_values: dict[str, float] = {}
    for r in rows:
        val = float(r["total"] or 0)
        if val != 0:
            all_values[r["data_acct_code"]] = val

    # 递归求和: code 的值 = 自身值 + 所有子节点值之和
    def _rollup(code: str) -> float:
        total = all_values.get(code, 0.0)
        prefix = code + "."
        for k, v in all_values.items():
            if k.startswith(prefix) and k != code:
                total += v
        return total

    # 目标指标映射 (code → key)
    targets = {
        f"{entity_code}.11": "loan_scale",
        f"{entity_code}.10": "loan_balance",
        f"{entity_code}.14": "interest_income",
        f"{entity_code}.02": "risk_cost",
        f"{entity_code}.05": "expense",
        f"{entity_code}.09": "profit",
        # 非贷款产品扩展
        f"{entity_code}.13": "managed_scale",      # 存款日均 / 管理资产日均
        f"{entity_code}.24": "interbank_balance",   # 同业资产余额
        f"{entity_code}.25": "interbank_daily_avg", # 同业资产日均
        f"{entity_code}.16": "interest_expense",     # 利息支出
        f"{entity_code}.17": "ftp_income",           # FTP收入
        f"{entity_code}.01.02": "fee_income",        # 手续费收入
        # 不良与拨备 (.20 = NPL余额, .21 = 拨备余额)
        f"{entity_code}.20": "npl_balance",
        f"{entity_code}.21": "provision_balance",
    }

    result: dict[str, float] = {}
    for code, key in targets.items():
        val = _rollup(code)
        if val == 0 and key == "loan_scale":
            # 贷款日均可能用余额替代
            balance_code = f"{entity_code}.10"
            val = _rollup(balance_code)
        result[key] = val

    return result


def _compute_from_formula_tree(
    common: sqlite3.Connection,
    budget: sqlite3.Connection,
    entity_code: str,
    version_id: int,
    budget_actual: int,
) -> dict[str, float]:
    """当 budget_data 高层值为 0 时，从公式树 + 叶子数据重新计算。"""
    data = load_org_product_metric_payload_from_runtime_tree(
        common,
        entity_code=entity_code,
        table_name="业务状况表",
    )
    if not data:
        return {}
    metrics = data.get("metrics", [])

    # 构建 code → (formula, children_codes) 映射
    formula_map: dict[str, str] = {}
    children_map: dict[str, list[str]] = {}

    def _walk(nodes: list[dict]):
        for node in nodes:
            code = node["code"]
            fm = (node.get("formula") or "").strip()
            if fm:
                formula_map[code] = fm
            ch = [c["code"] for c in node.get("children", [])]
            if ch:
                children_map[code] = ch
            _walk(node.get("children", []))

    _walk(metrics)

    # 读取所有叶子节点的 budget_data
    all_codes = list(formula_map.keys()) + [
        c for children in children_map.values() for c in children
    ]
    all_codes = list(set(all_codes))

    if not all_codes:
        return {}

    # 批量读取
    placeholders = ", ".join("?" for _ in all_codes)
    rows = budget.execute(
        f"""SELECT data_acct_code, SUM(value) as total
           FROM budget_data
           WHERE product_code = ?
             AND version_id = ?
             AND budget_actual = ?
             AND data_acct_code IN ({placeholders})
           GROUP BY data_acct_code""",
        (entity_code, version_id, budget_actual, *all_codes),
    ).fetchall()

    leaf_values: dict[str, float] = {}
    for r in rows:
        leaf_values[r["data_acct_code"]] = float(r["total"] or 0)

    # 递归求值：从叶子向上计算
    evaluated: dict[str, float] = {}

    def _eval_code(code: str) -> float:
        if code in evaluated:
            return evaluated[code]

        # 有直接值就直接用
        if code in leaf_values and leaf_values[code] != 0:
            evaluated[code] = leaf_values[code]
            return leaf_values[code]

        # 有公式就求公式
        fm = formula_map.get(code, "")
        if fm:
            # 先递归求子节点
            child_vals: dict[str, float] = {}
            for child in children_map.get(code, []):
                child_vals[child] = _eval_code(child)
            val = _eval_formula(fm, child_vals)
            evaluated[code] = val
            return val

        # 子节点求和
        children = children_map.get(code, [])
        if children:
            val = sum(_eval_code(c) for c in children)
            evaluated[code] = val
            return val

        evaluated[code] = 0.0
        return 0.0

    # 目标指标
    targets = {
        "loan_scale": f"{entity_code}.11",
        "interest_income": f"{entity_code}.14",
        "risk_cost": f"{entity_code}.02",
        "expense": f"{entity_code}.05",
        "profit": f"{entity_code}.09",
    }

    result: dict[str, float] = {}
    for key, code in targets.items():
        result[key] = _eval_code(code)

    return result


def _eval_formula(formula: str, values: dict[str, float]) -> float:
    """简单公式求值，支持 + - * / 和括号。"""
    import ast

    formula = formula.strip()
    if not formula:
        return 0.0

    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError:
        return 0.0

    def _eval(node) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            return float(values.get(node.id, 0.0))
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right if right != 0 else 0.0
            raise ValueError("unsupported op")
        if isinstance(node, ast.UnaryOp):
            val = _eval(node.operand)
            if isinstance(node.op, ast.USub):
                return -val
            return val
        return 0.0

    try:
        return _eval(tree)
    except Exception:
        return 0.0
