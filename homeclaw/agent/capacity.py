"""QPS, concurrency, and in-flight token controls for online proposers."""

from __future__ import annotations

import time
from typing import Any, Mapping, Sequence

from homeclaw.agent.proposer import ProposalResult, Proposer
from homeclaw.domain import CorrelationIds, DomainError, ErrorCode, ErrorDetail
from homeclaw.observability import NoopTelemetry, Telemetry
from homeclaw.resilience import ConcurrencyGate, TokenBudgetPool, TokenBucketRateLimiter
from homeclaw.resilience import CircuitBreaker, CircuitOpen, RetryPolicy, retry_call
from homeclaw.domain import IdempotencyClass
from homeclaw.routing import RouteDecision


class CapacityControlledProposer:
    def __init__(
        self,
        inner: Proposer,
        *,
        concurrency: ConcurrencyGate,
        rate_limiter: TokenBucketRateLimiter,
        in_flight_tokens: TokenBudgetPool,
        reservation_tokens: int,
        queue_timeout_seconds: float = 5.0,
        telemetry: Telemetry | None = None,
    ) -> None:
        if reservation_tokens <= 0 or queue_timeout_seconds <= 0:
            raise ValueError("capacity reservation and queue timeout must be positive")
        self.inner = inner
        self.concurrency = concurrency
        self.rate_limiter = rate_limiter
        self.in_flight_tokens = in_flight_tokens
        self.reservation_tokens = reservation_tokens
        self.queue_timeout_seconds = queue_timeout_seconds
        self.telemetry = telemetry or NoopTelemetry()

    def propose(
        self,
        user_input: str,
        route: RouteDecision,
        ids: CorrelationIds,
        *,
        context: Mapping[str, Any] | None = None,
        feedback: Sequence[Mapping[str, Any]] = (),
    ) -> ProposalResult:
        if not self.rate_limiter.allow():
            self.telemetry.increment("planner.rate_limited")
            raise DomainError(
                ErrorDetail(
                    ErrorCode.RATE_LIMITED,
                    "online planner QPS limit exceeded",
                    retryable=True,
                    component="planner.capacity",
                )
            )
        if not self.in_flight_tokens.reserve(self.reservation_tokens):
            self.telemetry.increment("planner.token_capacity_rejected")
            raise DomainError(
                ErrorDetail(
                    ErrorCode.BUDGET_EXHAUSTED,
                    "online planner in-flight token capacity exhausted",
                    retryable=True,
                    component="planner.capacity",
                )
            )
        queued_at = time.perf_counter()
        try:
            try:
                with self.concurrency.acquire(self.queue_timeout_seconds):
                    queue_ms = (time.perf_counter() - queued_at) * 1000.0
                    self.telemetry.observe("planner.queue_ms", queue_ms)
                    return self.inner.propose(
                        user_input,
                        route,
                        ids,
                        context=context,
                        feedback=feedback,
                    )
            except TimeoutError as exc:
                raise DomainError(
                    ErrorDetail(
                        ErrorCode.TIMEOUT,
                        "online planner concurrency queue timed out",
                        retryable=True,
                        component="planner.capacity",
                    )
                ) from exc
        finally:
            self.in_flight_tokens.release(self.reservation_tokens)


class ResilientProposer:
    """Retries only transport failures; invalid model output is never blindly retried."""

    def __init__(
        self,
        inner: Proposer,
        *,
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.inner = inner
        self.retry_policy = retry_policy or RetryPolicy()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    def propose(
        self,
        user_input: str,
        route: RouteDecision,
        ids: CorrelationIds,
        *,
        context: Mapping[str, Any] | None = None,
        feedback: Sequence[Mapping[str, Any]] = (),
    ) -> ProposalResult:
        def call() -> ProposalResult:
            with self.circuit_breaker.call():
                return self.inner.propose(
                    user_input, route, ids, context=context, feedback=feedback
                )

        try:
            return retry_call(
                call,
                policy=self.retry_policy,
                idempotency=IdempotencyClass.IDEMPOTENT,
            )
        except CircuitOpen as exc:
            raise DomainError(
                ErrorDetail(
                    ErrorCode.CIRCUIT_OPEN,
                    str(exc),
                    retryable=True,
                    component="planner",
                )
            ) from exc
        except (TimeoutError, ConnectionError) as exc:
            raise DomainError(
                ErrorDetail(
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    str(exc) or type(exc).__name__,
                    retryable=True,
                    component="planner",
                )
            ) from exc
