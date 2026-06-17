"""Mathematical scoring for intelligent budget simulation solutions."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntelligentBudgetTargetThresholds:
    min_net_profit_growth: float
    max_npl_ratio: float


@dataclass(frozen=True)
class IntelligentBudgetScoringInput:
    solution_id: str
    net_profit_growth: float
    npl_ratio: float
    operating_disturbance: float
    historical_deviation: float
    product_decomposition_penalty: float
    risk_action_difficulty: float
    excess_provision_buffer: float
    difference_score: float


@dataclass(frozen=True)
class IntelligentBudgetScoredSolution:
    solution_id: str
    rank: int
    math_score: float
    net_profit_growth: float
    npl_ratio: float


def _is_hard_target_met(
    solution: IntelligentBudgetScoringInput,
    thresholds: IntelligentBudgetTargetThresholds,
) -> bool:
    return (
        float(solution.net_profit_growth) >= float(thresholds.min_net_profit_growth)
        and float(solution.npl_ratio) <= float(thresholds.max_npl_ratio)
    )


def _score(
    solution: IntelligentBudgetScoringInput,
    thresholds: IntelligentBudgetTargetThresholds,
) -> float:
    target_distance = abs(float(solution.net_profit_growth) - float(thresholds.min_net_profit_growth)) * 1000
    npl_margin = max(0.0, float(thresholds.max_npl_ratio) - float(solution.npl_ratio)) * 500
    buffer_bonus = min(max(float(solution.excess_provision_buffer), 0.0), 30.0) * 0.2
    difference_bonus = min(max(float(solution.difference_score), 0.0), 10.0) * 0.4
    penalty = (
        target_distance
        + float(solution.operating_disturbance)
        + float(solution.historical_deviation)
        + float(solution.product_decomposition_penalty)
        + float(solution.risk_action_difficulty)
    )
    return round(1000.0 - penalty + npl_margin + buffer_bonus + difference_bonus, 6)


def rank_intelligent_budget_solutions(
    solutions: list[IntelligentBudgetScoringInput],
    thresholds: IntelligentBudgetTargetThresholds,
) -> list[IntelligentBudgetScoredSolution]:
    feasible = [solution for solution in solutions if _is_hard_target_met(solution, thresholds)]
    scored = [
        IntelligentBudgetScoredSolution(
            solution_id=solution.solution_id,
            rank=0,
            math_score=_score(solution, thresholds),
            net_profit_growth=float(solution.net_profit_growth),
            npl_ratio=float(solution.npl_ratio),
        )
        for solution in feasible
    ]
    scored.sort(key=lambda item: (-item.math_score, item.solution_id))
    return [
        IntelligentBudgetScoredSolution(
            solution_id=item.solution_id,
            rank=idx,
            math_score=item.math_score,
            net_profit_growth=item.net_profit_growth,
            npl_ratio=item.npl_ratio,
        )
        for idx, item in enumerate(scored, start=1)
    ]
