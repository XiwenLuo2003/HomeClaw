"""Component latency/error summaries derived from telemetry spans."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean
from typing import Iterable

from homeclaw.observability import SpanRecord, SpanStatus


@dataclass(frozen=True)
class ComponentPerformance:
    component: str
    count: int
    error_count: int
    error_rate: float
    average_ms: float
    p50_ms: float
    p95_ms: float


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[rank]


def summarize_spans(spans: Iterable[SpanRecord]) -> dict[str, ComponentPerformance]:
    grouped: dict[str, list[SpanRecord]] = {}
    for span in spans:
        grouped.setdefault(span.name, []).append(span)
    return {
        name: ComponentPerformance(
            component=name,
            count=len(items),
            error_count=sum(item.status is SpanStatus.ERROR for item in items),
            error_rate=sum(item.status is SpanStatus.ERROR for item in items) / len(items),
            average_ms=mean(item.duration_ms for item in items),
            p50_ms=percentile([item.duration_ms for item in items], 0.50),
            p95_ms=percentile([item.duration_ms for item in items], 0.95),
        )
        for name, items in grouped.items()
    }
