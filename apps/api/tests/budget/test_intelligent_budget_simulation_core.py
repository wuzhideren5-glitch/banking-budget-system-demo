from __future__ import annotations

import math

from app.services.intelligent_budget_risk import RiskSubmodelInput, derive_risk_metrics
from app.services.intelligent_budget_scoring import (
    IntelligentBudgetScoringInput,
    IntelligentBudgetTargetThresholds,
    rank_intelligent_budget_solutions,
)
from app.services.intelligent_budget_steps import StepVariable, generate_step_candidates


def test_risk_submodel_derives_npl_provision_and_excess_provision() -> None:
    result = derive_risk_metrics(
        RiskSubmodelInput(
            opening_loan_scale=9000,
            ending_loan_scale=10000,
            opening_npl_balance=100,
            new_npl=40,
            recovery_collection=15,
            writeoff_disposal=5,
            opening_provision_balance=135,
            provision_charge=20,
            writeoff_provision_consumption=5,
        )
    )

    assert result.ending_npl_balance == 120
    assert math.isclose(result.npl_ratio, 0.012)
    assert result.ending_provision_balance == 150
    assert result.excess_provision == 30
    assert not result.scale_dilution_only


def test_risk_submodel_flags_scale_dilution_only_npl_improvement() -> None:
    result = derive_risk_metrics(
        RiskSubmodelInput(
            opening_loan_scale=9000,
            ending_loan_scale=12000,
            opening_npl_balance=100,
            new_npl=0,
            recovery_collection=0,
            writeoff_disposal=0,
            opening_provision_balance=130,
            provision_charge=0,
            writeoff_provision_consumption=0,
        )
    )

    assert result.ending_npl_balance == 100
    assert result.npl_ratio < result.opening_npl_ratio
    assert result.scale_dilution_only


def test_formula_aware_step_generation_uses_sensitivity_clamp_and_business_rounding() -> None:
    summary = generate_step_candidates(
        StepVariable(
            variable_code="A01_LOAN_YIELD",
            label="A01贷款收益率",
            baseline_value=0.075,
            sensitivity=100000,
            target_step=20,
            historical_min_reasonable_step=0.0001,
            historical_max_reasonable_step=0.0005,
            business_unit=0.0001,
            lower_bound=0.074,
            upper_bound=0.076,
            levels_each_side=2,
        )
    )

    assert math.isclose(summary.step_size, 0.0002)
    assert summary.method == "formula_aware_adaptive"
    assert summary.candidate_values == [0.0746, 0.0748, 0.075, 0.0752, 0.0754]
    assert "sensitivity" in summary.reason


def test_formula_aware_step_generation_coarsens_low_impact_variables() -> None:
    summary = generate_step_candidates(
        StepVariable(
            variable_code="SMALL_PRODUCT_EXPENSE",
            label="小产品费用",
            baseline_value=1000,
            sensitivity=0.5,
            target_step=20,
            historical_min_reasonable_step=10,
            historical_max_reasonable_step=100,
            business_unit=10,
            lower_bound=800,
            upper_bound=1200,
            levels_each_side=1,
        )
    )

    assert summary.step_size == 100
    assert summary.candidate_values == [900, 1000, 1100]


def test_final_scoring_filters_hard_target_failures_before_ranking() -> None:
    ranked = rank_intelligent_budget_solutions(
        [
            IntelligentBudgetScoringInput(
                solution_id="aggressive_profit",
                net_profit_growth=0.15,
                npl_ratio=0.011,
                operating_disturbance=40,
                historical_deviation=30,
                product_decomposition_penalty=12,
                risk_action_difficulty=16,
                excess_provision_buffer=20,
                difference_score=8,
            ),
            IntelligentBudgetScoringInput(
                solution_id="balanced_target",
                net_profit_growth=0.103,
                npl_ratio=0.0118,
                operating_disturbance=8,
                historical_deviation=6,
                product_decomposition_penalty=3,
                risk_action_difficulty=4,
                excess_provision_buffer=18,
                difference_score=6,
            ),
            IntelligentBudgetScoringInput(
                solution_id="misses_profit",
                net_profit_growth=0.09,
                npl_ratio=0.011,
                operating_disturbance=1,
                historical_deviation=1,
                product_decomposition_penalty=1,
                risk_action_difficulty=1,
                excess_provision_buffer=30,
                difference_score=10,
            ),
        ],
        IntelligentBudgetTargetThresholds(
            min_net_profit_growth=0.10,
            max_npl_ratio=0.012,
        ),
    )

    assert [item.solution_id for item in ranked] == ["balanced_target", "aggressive_profit"]
    assert ranked[0].rank == 1
    assert ranked[0].math_score > ranked[1].math_score
