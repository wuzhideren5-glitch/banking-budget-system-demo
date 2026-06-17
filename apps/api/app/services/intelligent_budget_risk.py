"""Risk submodel for intelligent budget simulation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskSubmodelInput:
    opening_loan_scale: float
    ending_loan_scale: float
    opening_npl_balance: float
    new_npl: float
    recovery_collection: float
    writeoff_disposal: float
    opening_provision_balance: float
    provision_charge: float
    writeoff_provision_consumption: float


@dataclass(frozen=True)
class RiskSubmodelResult:
    opening_loan_scale: float
    ending_loan_scale: float
    opening_npl_balance: float
    ending_npl_balance: float
    opening_npl_ratio: float
    npl_ratio: float
    ending_provision_balance: float
    excess_provision: float
    scale_dilution_only: bool


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if abs(float(denominator)) > 1e-12 else 0.0


def derive_risk_metrics(input: RiskSubmodelInput) -> RiskSubmodelResult:
    ending_npl_balance = (
        float(input.opening_npl_balance)
        + float(input.new_npl)
        - float(input.recovery_collection)
        - float(input.writeoff_disposal)
    )
    ending_provision_balance = (
        float(input.opening_provision_balance)
        + float(input.provision_charge)
        - float(input.writeoff_provision_consumption)
    )
    opening_npl_ratio = _safe_ratio(input.opening_npl_balance, input.opening_loan_scale)
    npl_ratio = _safe_ratio(ending_npl_balance, input.ending_loan_scale)
    scale_dilution_only = (
        npl_ratio < opening_npl_ratio
        and ending_npl_balance >= float(input.opening_npl_balance) - 1e-9
        and float(input.ending_loan_scale) > float(input.opening_loan_scale)
    )
    return RiskSubmodelResult(
        opening_loan_scale=float(input.opening_loan_scale),
        ending_loan_scale=float(input.ending_loan_scale),
        opening_npl_balance=float(input.opening_npl_balance),
        ending_npl_balance=ending_npl_balance,
        opening_npl_ratio=opening_npl_ratio,
        npl_ratio=npl_ratio,
        ending_provision_balance=ending_provision_balance,
        excess_provision=ending_provision_balance - ending_npl_balance,
        scale_dilution_only=scale_dilution_only,
    )
