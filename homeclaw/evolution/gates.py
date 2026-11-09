"""Fail-closed improvement and safety gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from homeclaw.evolution.models import EvaluationSnapshot


@dataclass(frozen=True)
class GatePolicy:
    primary_metric: str
    minimum_improvement: float
    maximum_regression: Mapping[str, float] = field(default_factory=dict)
    required_safety_checks: tuple[str, ...] = ()
    minimum_sample_count: int = 1


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reasons: tuple[str, ...]


class EvolutionGate:
    def __init__(self, policy: GatePolicy) -> None:
        self.policy = policy

    def evaluate(
        self,
        baseline: EvaluationSnapshot,
        candidate: EvaluationSnapshot,
    ) -> GateResult:
        reasons: list[str] = []
        comparable = (
            "dataset_id",
            "dataset_hash",
            "model_id",
            "prompt_version",
            "seed",
            "token_budget",
        )
        for field_name in comparable:
            if getattr(baseline, field_name) != getattr(candidate, field_name):
                reasons.append(f"non-comparable {field_name}")
        if candidate.sample_count < self.policy.minimum_sample_count:
            reasons.append("insufficient sample count")
        primary = self.policy.primary_metric
        if primary not in baseline.metrics or primary not in candidate.metrics:
            reasons.append(f"missing primary metric: {primary}")
        elif candidate.metrics[primary] - baseline.metrics[primary] < self.policy.minimum_improvement:
            reasons.append(f"primary metric improvement below {self.policy.minimum_improvement}")
        for metric, allowed_regression in self.policy.maximum_regression.items():
            if metric not in baseline.metrics or metric not in candidate.metrics:
                reasons.append(f"missing guarded metric: {metric}")
                continue
            regression = baseline.metrics[metric] - candidate.metrics[metric]
            if regression > allowed_regression:
                reasons.append(f"{metric} regressed by {regression:.6f}")
        for check in self.policy.required_safety_checks:
            if candidate.safety_checks.get(check) is not True:
                reasons.append(f"safety check failed or missing: {check}")
        return GateResult(not reasons, tuple(reasons))
