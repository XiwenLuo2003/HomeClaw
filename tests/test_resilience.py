from __future__ import annotations

import threading
import unittest

from homeclaw.domain import IdempotencyClass
from homeclaw.resilience import (
    AdaptiveTopKPolicy,
    CircuitBreaker,
    CircuitOpen,
    ConcurrencyGate,
    RetryPolicy,
    TokenBudgetPool,
    TokenBucketRateLimiter,
    retry_call,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class ResilienceTests(unittest.TestCase):
    def test_retry_uses_backoff_for_idempotent_operation(self) -> None:
        attempts = []
        delays = []

        def operation():
            attempts.append(1)
            if len(attempts) < 3:
                raise TimeoutError("retry")
            return "ok"

        result = retry_call(
            operation,
            policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.5, jitter_ratio=0),
            idempotency=IdempotencyClass.IDEMPOTENT_WITH_KEY,
            sleep=delays.append,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(delays, [0.5, 1.0])

    def test_non_idempotent_operation_is_never_blindly_retried(self) -> None:
        attempts = []

        def operation():
            attempts.append(1)
            raise ConnectionError("failed")

        with self.assertRaises(ConnectionError):
            retry_call(
                operation,
                policy=RetryPolicy(max_attempts=5),
                idempotency=IdempotencyClass.NON_IDEMPOTENT,
                sleep=lambda _: None,
            )
        self.assertEqual(len(attempts), 1)

    def test_circuit_opens_and_half_open_probe_recovers(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(2, 10, clock=clock)
        for _ in range(2):
            with self.assertRaises(TimeoutError):
                with breaker.call():
                    raise TimeoutError()
        with self.assertRaises(CircuitOpen):
            with breaker.call():
                pass
        clock.advance(10)
        with breaker.call():
            pass
        self.assertEqual(breaker.state.value, "closed")

    def test_rate_token_and_adaptive_top_k_controls(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(1, 2, clock=clock)
        self.assertTrue(limiter.allow())
        self.assertTrue(limiter.allow())
        self.assertFalse(limiter.allow())
        clock.advance(1)
        self.assertTrue(limiter.allow())

        budget = TokenBudgetPool(100)
        self.assertTrue(budget.reserve(80))
        self.assertFalse(budget.reserve(30))
        budget.release(20)
        self.assertTrue(budget.reserve(30))

        policy = AdaptiveTopKPolicy()
        self.assertEqual(policy.choose("turn on the light", available_experts=5, token_budget=4000), 1)
        self.assertEqual(
            policy.choose("turn on the light and cool the room", available_experts=5, token_budget=4000),
            2,
        )
        self.assertEqual(
            policy.choose("turn on the light and cool the room", available_experts=5, token_budget=500),
            1,
        )
        self.assertEqual(
            policy.choose("turn on that lamp in the image", available_experts=5, token_budget=4000),
            2,
        )

    def test_concurrency_gate_times_out_when_capacity_is_held(self) -> None:
        gate = ConcurrencyGate(1)
        with gate.acquire():
            with self.assertRaises(TimeoutError):
                with gate.acquire(timeout_seconds=0.001):
                    pass


if __name__ == "__main__":
    unittest.main()
