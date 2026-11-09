"""Deterministic canary routing with automatic fail-closed pause."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum


class CanaryStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    READY_FOR_APPROVAL = "ready_for_approval"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class CanaryPolicy:
    traffic_fraction: float = 0.05
    minimum_samples: int = 100
    maximum_failure_rate: float = 0.05
    maximum_failure_rate_increase: float = 0.01

    def __post_init__(self) -> None:
        if self.traffic_fraction <= 0 or self.traffic_fraction > 1:
            raise ValueError("canary traffic_fraction must be in (0, 1]")
        if self.minimum_samples <= 0:
            raise ValueError("canary minimum_samples must be positive")


class CanaryController:
    def __init__(
        self,
        candidate_id: str,
        baseline_failure_rate: float,
        policy: CanaryPolicy | None = None,
    ) -> None:
        self.candidate_id = candidate_id
        self.baseline_failure_rate = baseline_failure_rate
        self.policy = policy or CanaryPolicy()
        self.status = CanaryStatus.RUNNING
        self.samples = 0
        self.failures = 0
        self.safety_violations = 0
        self.approved_by: str | None = None

    def selected(self, stable_key: str) -> bool:
        digest = hashlib.sha256(
            f"{self.candidate_id}:{stable_key}".encode("utf-8")
        ).digest()
        bucket = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
        return self.status is CanaryStatus.RUNNING and bucket < self.policy.traffic_fraction

    def record(self, *, success: bool, safety_violation: bool = False) -> CanaryStatus:
        if self.status is not CanaryStatus.RUNNING:
            raise RuntimeError(f"cannot record outcome while canary is {self.status.value}")
        self.samples += 1
        self.failures += int(not success)
        self.safety_violations += int(safety_violation)
        if safety_violation:
            self.status = CanaryStatus.PAUSED
            return self.status
        failure_rate = self.failures / self.samples
        allowed = min(
            self.policy.maximum_failure_rate,
            self.baseline_failure_rate + self.policy.maximum_failure_rate_increase,
        )
        if self.samples >= self.policy.minimum_samples:
            self.status = (
                CanaryStatus.READY_FOR_APPROVAL
                if failure_rate <= allowed
                else CanaryStatus.PAUSED
            )
        return self.status

    def approve(self, approved_by: str) -> None:
        if self.status is not CanaryStatus.READY_FOR_APPROVAL:
            raise RuntimeError("canary is not ready for approval")
        if not approved_by.strip():
            raise ValueError("approved_by is required")
        self.approved_by = approved_by
        self.status = CanaryStatus.PROMOTED

    def rollback(self) -> None:
        self.status = CanaryStatus.ROLLED_BACK
