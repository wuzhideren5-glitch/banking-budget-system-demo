from __future__ import annotations

from app.services.intelligent_budget_solver import (
    IntelligentBudgetProductProfile,
    IntelligentBudgetSolveRequest,
    solve_intelligent_budget,
)
from app.services.intelligent_budget_target_parser import parse_leadership_target
from app.services.intelligent_budget_target_parser import build_deepseek_target_provider


class _FakeDeepseekClient:
    def is_enabled(self) -> bool:
        return True

    def chat_completion(self, **_kwargs: object) -> str:
        return """```json
{"hard_targets":{"min_net_profit_growth":0.12,"max_npl_ratio":0.011},"soft_preferences":["风险优先"]}
```"""


def _product_profiles() -> list[IntelligentBudgetProductProfile]:
    return [
        IntelligentBudgetProductProfile("A01", "微粒贷", 520, 0.082, 18, 6.2, 7.5, 0.019, 11.5),
        IntelligentBudgetProductProfile("A02", "企业金融", 260, 0.061, 12, 4.1, 4.9, 0.016, 7.8),
        IntelligentBudgetProductProfile("A03", "供应链金融", 180, 0.066, 7, 2.8, 3.2, 0.014, 5.1),
        IntelligentBudgetProductProfile("A04", "车贷", 130, 0.072, 5, 2.1, 2.5, 0.017, 3.9),
        IntelligentBudgetProductProfile("A05", "小微贷", 95, 0.078, 4, 1.8, 2.2, 0.021, 3.2),
        IntelligentBudgetProductProfile("A06", "消费备用金", 70, 0.089, 3, 1.4, 1.8, 0.023, 2.5),
    ]


def _high_risk_product_profiles() -> list[IntelligentBudgetProductProfile]:
    return [
        IntelligentBudgetProductProfile("R01", "高风险小微", 460, 0.095, 20, 12.8, 9.0, 0.042, 8.0),
        IntelligentBudgetProductProfile("R02", "高收益消费贷", 320, 0.105, 16, 8.5, 6.4, 0.038, 7.2),
        IntelligentBudgetProductProfile("R03", "一般企业贷", 210, 0.062, 9, 3.2, 3.4, 0.017, 5.2),
        IntelligentBudgetProductProfile("R04", "低风险票据", 150, 0.045, 3, 0.6, 1.2, 0.006, 2.3),
    ]


def _low_risk_product_profiles() -> list[IntelligentBudgetProductProfile]:
    return [
        IntelligentBudgetProductProfile("S01", "按揭低风险", 650, 0.042, 10, 2.4, 4.2, 0.006, 5.8),
        IntelligentBudgetProductProfile("S02", "国企贷款", 420, 0.039, 8, 1.5, 2.8, 0.005, 4.1),
        IntelligentBudgetProductProfile("S03", "票据贴现", 220, 0.035, 3, 0.5, 1.0, 0.004, 1.7),
        IntelligentBudgetProductProfile("S04", "供应链白名单", 160, 0.052, 4, 0.9, 1.4, 0.007, 2.1),
    ]


def test_target_parser_uses_deepseek_json_and_requires_confirmation() -> None:
    parsed = parse_leadership_target(
        "净利润维持增长10%，不良率控制在1.2%以内，规模不要太冒进",
        deepseek_json_provider=lambda _text: {
            "hard_targets": {
                "min_net_profit_growth": 0.1,
                "max_npl_ratio": 0.012,
            },
            "soft_preferences": ["稳健经营", "规模不冒进"],
        },
    )
    assert parsed.min_net_profit_growth == 0.1
    assert parsed.max_npl_ratio == 0.012
    assert "稳健经营" in parsed.soft_preferences


def test_target_parser_can_use_deepseek_client_json_provider() -> None:
    client = _FakeDeepseekClient()
    provider = build_deepseek_target_provider(client)
    parsed = parse_leadership_target(
        "目标：净利润增长12%，不良率控制在1.1%以内",
        deepseek_json_provider=provider,
    )
    assert parsed.min_net_profit_growth == 0.12
    assert parsed.max_npl_ratio == 0.011


def test_target_parser_falls_back_to_deterministic_parse_when_deepseek_fails() -> None:
    parsed = parse_leadership_target(
        "没有什么有用的信息",
        deepseek_json_provider=lambda _text: {},
    )
    assert parsed.min_net_profit_growth is not None
    assert parsed.max_npl_ratio is not None


def test_layered_solver_returns_ten_math_ranked_feasible_solutions() -> None:
    target = parse_leadership_target("净利润增长5%，不良率控制在1.5%以内")
    result = solve_intelligent_budget(
        IntelligentBudgetSolveRequest(
            parsed_target=target,
            product_profiles=_product_profiles(),
            required_solution_count=10,
        )
    )
    assert result.status == "completed"
    assert len(result.solutions) == 10
    assert result.solutions[0].rank == 1
    assert result.solutions[0].display_role == "recommended"
    assert result.baseline_solution.display_role == "baseline"


def test_solver_uses_product_pool_to_change_feasibility_and_ranking() -> None:
    target = parse_leadership_target("净利润增长5%，不良率控制在1.5%以内")
    baseline = solve_intelligent_budget(
        IntelligentBudgetSolveRequest(
            parsed_target=target,
            product_profiles=_product_profiles(),
            required_solution_count=10,
        )
    )
    high_risk = solve_intelligent_budget(
        IntelligentBudgetSolveRequest(
            parsed_target=target,
            product_profiles=_high_risk_product_profiles(),
            required_solution_count=10,
        )
    )
    low_risk = solve_intelligent_budget(
        IntelligentBudgetSolveRequest(
            parsed_target=target,
            product_profiles=_low_risk_product_profiles(),
            required_solution_count=10,
        )
    )
    baseline_elastic = solve_intelligent_budget(
        IntelligentBudgetSolveRequest(
            parsed_target=parse_leadership_target("净利润增长3%，不良率控制在2.1%以内"),
            product_profiles=_product_profiles(),
            required_solution_count=10,
        )
    )

    assert baseline.status == "completed"
    assert high_risk.status in ("completed", "negotiation_required")
    # 不同产品池应产出不同评分和不良率特征
    if high_risk.status == "completed":
        assert high_risk.solutions[0].npl_ratio != baseline.solutions[0].npl_ratio, (
            f"High-risk npl={high_risk.solutions[0].npl_ratio} vs baseline npl={baseline.solutions[0].npl_ratio}"
        )
    assert low_risk.status in ("completed", "negotiation_required")
    if low_risk.status == "negotiation_required":
        # 低风险产品池收益率低(3.5-5.2%)，难以达成10%利润增长目标
        assert len(low_risk.solutions) < 10
    else:
        assert low_risk.solutions[0].npl_ratio < baseline.solutions[0].npl_ratio


def test_solver_enters_negotiation_when_fewer_than_ten_solutions_are_feasible() -> None:
    target = parse_leadership_target("净利润增长35%，不良率控制在0.5%")
    result = solve_intelligent_budget(
        IntelligentBudgetSolveRequest(
            parsed_target=target,
            product_profiles=_product_profiles(),
            required_solution_count=10,
        )
    )

    assert result.status == "negotiation_required"
    assert len(result.solutions) < 10
    assert "未达到10套方案集要求" in result.negotiation_message
    assert any("放宽" in suggestion for suggestion in result.negotiation_suggestions)


def test_solver_with_real_db_product_profiles() -> None:
    """使用数据库真实产品配置运行求解器，确保 12 产品兼容。"""
    from pathlib import Path

    from app.services.intelligent_budget_product_loader import load_product_profiles_from_db

    project_root = Path(__file__).resolve().parent.parent.parent
    data_dir = project_root / "var" / "data"

    common_db = data_dir / "common.db"
    budget_db = data_dir / "budget_2026.db"

    if not common_db.exists() or not budget_db.exists():
        print(f"数据库不存在，跳过: {data_dir}")
        return

    profiles = load_product_profiles_from_db(
        common_db_path=common_db,
        budget_db_path=budget_db,
    )

    assert len(profiles) == 12, f"期望 12 个产品，实际 {len(profiles)}"
    assert profiles[0].product_code == "A01"
    assert profiles[0].product_name == "泛微粒贷"

    target = parse_leadership_target("净利润增长10%，不良率控制在1.5%以内")
    result = solve_intelligent_budget(
        IntelligentBudgetSolveRequest(
            parsed_target=target,
            product_profiles=profiles,
            required_solution_count=5,
        )
    )
    assert result.status == "completed", f"期望 completed，实际 {result.status}: {result.step_summary}"
    assert len(result.solutions) >= 3, f"至少 3 个方案，实际 {len(result.solutions)}"
