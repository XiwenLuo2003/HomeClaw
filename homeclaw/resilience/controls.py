"""Dependency-free reliability and capacity controls."""

from __future__ import annotations

import random
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterator, Optional, TypeVar

from homeclaw.domain import IdempotencyClass


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.1
    max_delay_seconds: float = 2.0
    jitter_ratio: float = 0.1

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays must be non-negative")
        if self.jitter_ratio < 0 or self.jitter_ratio > 1:
            raise ValueError("jitter_ratio must be in [0, 1]")

    def delay(self, attempt: int, random_value: float) -> float:
        base = min(self.base_delay_seconds * (2 ** max(attempt - 1, 0)), self.max_delay_seconds)
        jitter = base * self.jitter_ratio * ((random_value * 2.0) - 1.0)
        return max(0.0, base + jitter)


def retry_call(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    idempotency: IdempotencyClass,
    retryable: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError),
    sleep: Callable[[float], None] = time.sleep,
    random_source: Callable[[], float] = random.random,
) -> T:
    attempts = 1 if idempotency is IdempotencyClass.NON_IDEMPOTENT else policy.max_attempts
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except retryable:
            if attempt >= attempts:
                raise
            sleep(policy.delay(attempt, random_source()))
    raise AssertionError("unreachable")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpen(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold <= 0 or recovery_timeout_seconds <= 0:
            raise ValueError("circuit breaker thresholds must be positive")
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.clock = clock
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at: Optional[float] = None
        self._lock = threading.RLock()

    @contextmanager
    def call(self) -> Iterator[None]:
        with self._lock:
            self._allow()
        try:
            yield
        except Exception:
            self.record_failure()
            raise
        else:
            self.record_success()

    def _allow(self) -> None:
        if self.state is CircuitState.OPEN:
            assert self.opened_at is not None
            if self.clock() - self.opened_at < self.recovery_timeout_seconds:
                raise CircuitOpen("circuit is open")
            self.state = CircuitState.HALF_OPEN

    def record_failure(self) -> None:
        with self._lock:
            self.failure_count += 1
            if self.state is CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = self.clock()

    def record_success(self) -> None:
        with self._lock:
            self.failure_count = 0
            self.state = CircuitState.CLOSED
            self.opened_at = None


class ConcurrencyGate:
    def __init__(self, limit: int) -> None:
        if limit <= 0:
            raise ValueError("concurrency limit must be positive")
        self.limit = limit
        self._semaphore = threading.BoundedSemaphore(limit)

    @contextmanager
    def acquire(self, timeout_seconds: Optional[float] = None) -> Iterator[None]:
        acquired = self._semaphore.acquire(timeout=timeout_seconds)
        if not acquired:
            raise TimeoutError("concurrency queue timeout")
        try:
            yield
        finally:
            self._semaphore.release()


class TokenBudgetPool:
    def __init__(self, total_tokens: int) -> None:
        if total_tokens <= 0:
            raise ValueError("token budget must be positive")
        self.total_tokens = total_tokens
        self.remaining_tokens = total_tokens
        self._lock = threading.Lock()

    def reserve(self, tokens: int) -> bool:
        if tokens <= 0:
            raise ValueError("reserved tokens must be positive")
        with self._lock:
            if tokens > self.remaining_tokens:
                return False
            self.remaining_tokens -= tokens
            return True

    def release(self, tokens: int) -> None:
        if tokens <= 0:
            raise ValueError("released tokens must be positive")
        with self._lock:
            self.remaining_tokens = min(self.total_tokens, self.remaining_tokens + tokens)


class TokenBucketRateLimiter:
    def __init__(
        self,
        rate_per_second: float,
        capacity: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate_per_second <= 0 or capacity <= 0:
            raise ValueError("rate and capacity must be positive")
        self.rate_per_second = rate_per_second
        self.capacity = capacity
        self.tokens = capacity
        self.clock = clock
        self.updated_at = clock()
        self._lock = threading.Lock()

    def allow(self, cost: float = 1.0) -> bool:
        if cost <= 0:
            raise ValueError("rate-limit cost must be positive")
        with self._lock:
            now = self.clock()
            elapsed = max(0.0, now - self.updated_at)
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_second)
            self.updated_at = now
            if self.tokens < cost:
                return False
            self.tokens -= cost
            return True


@dataclass(frozen=True)
class AdaptiveTopKPolicy:
    simple_top_k: int = 1
    complex_top_k: int = 2
    max_top_k: int = 3

    def choose(self, text: str, *, available_experts: int, token_budget: int) -> int:
        if available_experts <= 0:
            return 0
        lowered = text.lower()
        complex_markers = (
            " and ", " then ", " after ", "同时", "然后", "之后",
            "in the image", "that lamp", "this device", "图里", "那盏灯", "这个设备",
        )
        requested = self.complex_top_k if any(marker in lowered for marker in complex_markers) else self.simple_top_k
        if token_budget < 1_000:
            requested = 1
        return min(max(requested, 1), self.max_top_k, available_experts)
