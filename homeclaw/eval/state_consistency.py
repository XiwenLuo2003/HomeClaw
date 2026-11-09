"""State-cache and command-confirmation acceptance metrics."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Sequence

from homeclaw.eval.performance import percentile


@dataclass(frozen=True)
class StateConsistencyObservation:
    cache_hit: bool
    stale_read: bool
    command_expected: bool
    read_your_write: bool
    confirmation_ms: float | None = None
    reconciliation_ms: float | None = None
    reconciliation_difference: bool = False


@dataclass(frozen=True)
class StateConsistencySummary:
    samples: int
    cache_hit_rate: float
    stale_read_rate: float
    read_your_write_rate: float
    reconciliation_difference_rate: float
    confirmation_p50_ms: float
    confirmation_p95_ms: float
    reconciliation_p50_ms: float
    reconciliation_p95_ms: float


def summarize_state_consistency(
    observations: Sequence[StateConsistencyObservation],
) -> StateConsistencySummary:
    count = len(observations)
    command_items = [item for item in observations if item.command_expected]
    confirmation = [
        item.confirmation_ms for item in command_items if item.confirmation_ms is not None
    ]
    reconciliation = [
        item.reconciliation_ms
        for item in observations
        if item.reconciliation_ms is not None
    ]
    return StateConsistencySummary(
        samples=count,
        cache_hit_rate=mean(item.cache_hit for item in observations) if count else 0.0,
        stale_read_rate=mean(item.stale_read for item in observations) if count else 0.0,
        read_your_write_rate=(
            mean(item.read_your_write for item in command_items) if command_items else 0.0
        ),
        reconciliation_difference_rate=(
            mean(item.reconciliation_difference for item in observations) if count else 0.0
        ),
        confirmation_p50_ms=percentile(confirmation, 0.50),
        confirmation_p95_ms=percentile(confirmation, 0.95),
        reconciliation_p50_ms=percentile(reconciliation, 0.50),
        reconciliation_p95_ms=percentile(reconciliation, 0.95),
    )
