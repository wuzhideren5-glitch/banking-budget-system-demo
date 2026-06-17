"""Formula-aware adaptive step generation for intelligent budget simulation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StepVariable:
    variable_code: str
    label: str
    baseline_value: float
    sensitivity: float
    target_step: float
    historical_min_reasonable_step: float
    historical_max_reasonable_step: float
    business_unit: float
    lower_bound: float
    upper_bound: float
    levels_each_side: int = 3


@dataclass(frozen=True)
class StepCandidateSummary:
    variable_code: str
    label: str
    method: str
    sensitivity: float
    raw_step: float
    step_size: float
    candidate_values: list[float]
    reason: str


def _round_to_business_unit(value: float, business_unit: float) -> float:
    unit = abs(float(business_unit)) or 1.0
    rounded = round(float(value) / unit) * unit
    return max(unit, rounded)


def _normalize_number(value: float) -> float:
    normalized = round(float(value), 10)
    return 0.0 if normalized == -0.0 else normalized


def generate_step_candidates(variable: StepVariable) -> StepCandidateSummary:
    sensitivity = abs(float(variable.sensitivity))
    epsilon = 1e-9
    raw_step = abs(float(variable.target_step)) / max(sensitivity, epsilon)
    if sensitivity < 1:
        clamped = float(variable.historical_max_reasonable_step)
    else:
        clamped = min(
            max(raw_step, float(variable.historical_min_reasonable_step)),
            float(variable.historical_max_reasonable_step),
        )
    step_size = _round_to_business_unit(clamped, variable.business_unit)
    lower = float(variable.lower_bound)
    upper = float(variable.upper_bound)
    baseline = float(variable.baseline_value)
    candidates: list[float] = []
    for idx in range(-int(variable.levels_each_side), int(variable.levels_each_side) + 1):
        value = baseline + idx * step_size
        if value < lower - 1e-12 or value > upper + 1e-12:
            continue
        normalized = _normalize_number(value)
        if normalized not in candidates:
            candidates.append(normalized)
    return StepCandidateSummary(
        variable_code=variable.variable_code,
        label=variable.label,
        method="formula_aware_adaptive",
        sensitivity=sensitivity,
        raw_step=raw_step,
        step_size=_normalize_number(step_size),
        candidate_values=candidates,
        reason=(
            f"Generated from sensitivity={sensitivity:.6g}, target_step={float(variable.target_step):.6g}, "
            "historical clamp, and business-unit rounding."
        ),
    )
