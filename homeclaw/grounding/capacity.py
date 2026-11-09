"""Capacity wrapper for the independently deployed GPU Grounder."""

from __future__ import annotations

import time
from typing import Sequence

from homeclaw.domain import GroundingResult
from homeclaw.grounding.client import GrounderClient, GrounderRequest
from homeclaw.observability import NoopTelemetry, Telemetry
from homeclaw.resilience import ConcurrencyGate, TokenBucketRateLimiter


class CapacityControlledGrounderClient:
    def __init__(
        self,
        inner: GrounderClient,
        *,
        concurrency: ConcurrencyGate,
        rate_limiter: TokenBucketRateLimiter,
        queue_timeout_seconds: float = 5.0,
        telemetry: Telemetry | None = None,
    ) -> None:
        self.inner = inner
        self.concurrency = concurrency
        self.rate_limiter = rate_limiter
        self.queue_timeout_seconds = queue_timeout_seconds
        self.telemetry = telemetry or NoopTelemetry()

    def _enter(self, cost: float = 1.0):
        if not self.rate_limiter.allow(cost):
            self.telemetry.increment("grounder.rate_limited")
            raise TimeoutError("grounder QPS capacity exceeded")
        return self.concurrency.acquire(self.queue_timeout_seconds)

    def ground(self, request: GrounderRequest, timeout_seconds: float = 10.0) -> GroundingResult:
        queued_at = time.perf_counter()
        with self._enter():
            self.telemetry.observe(
                "grounder.queue_ms", (time.perf_counter() - queued_at) * 1000.0
            )
            return self.inner.ground(request, timeout_seconds)

    def ground_batch(
        self,
        requests: Sequence[GrounderRequest],
        timeout_seconds: float = 30.0,
    ) -> tuple[GroundingResult, ...]:
        queued_at = time.perf_counter()
        with self._enter(max(1.0, float(len(requests)))):
            self.telemetry.observe(
                "grounder.queue_ms", (time.perf_counter() - queued_at) * 1000.0
            )
            return self.inner.ground_batch(requests, timeout_seconds)

    def healthy(self, timeout_seconds: float = 2.0) -> bool:
        return self.inner.healthy(timeout_seconds)
