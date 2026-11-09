from __future__ import annotations

import unittest

from homeclaw.agent import CapacityControlledProposer, ResilientProposer, StaticProposer
from homeclaw.agent.proposer import ProposalResult
from homeclaw.domain import ActionProposal, CorrelationIds, DeviceRef, DomainError
from homeclaw.grounding import CapacityControlledGrounderClient, GrounderCandidate, GrounderRequest
from homeclaw.observability import InMemoryTelemetry
from homeclaw.resilience import (
    ConcurrencyGate,
    RetryPolicy,
    TokenBudgetPool,
    TokenBucketRateLimiter,
)
from homeclaw.routing import RouteDecision, SkillMatch


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class FakeGrounder:
    def __init__(self):
        self.calls = 0

    def ground(self, request, timeout_seconds=10.0):
        self.calls += 1
        return "grounded"

    def ground_batch(self, requests, timeout_seconds=30.0):
        self.calls += 1
        return tuple("grounded" for _ in requests)

    def healthy(self, timeout_seconds=2.0):
        return True


class CapacityWrapperTests(unittest.TestCase):
    def route(self):
        return RouteDecision(
            (SkillMatch("lighting", 1.0, (), "lighting"),),
            ("turn_light_on",),
            (),
            False,
            1,
            1,
            1,
        )

    def test_planner_qps_and_in_flight_tokens_fail_closed(self):
        proposal = ActionProposal(
            "turn_light_on", DeviceRef("home-1", "light-1"), {}, "lighting", {"power": "on"}
        )
        clock = Clock()
        telemetry = InMemoryTelemetry()
        wrapper = CapacityControlledProposer(
            StaticProposer([proposal]),
            concurrency=ConcurrencyGate(1),
            rate_limiter=TokenBucketRateLimiter(1, 1, clock=clock),
            in_flight_tokens=TokenBudgetPool(100),
            reservation_tokens=80,
            telemetry=telemetry,
        )
        self.assertEqual(
            len(wrapper.propose("turn on", self.route(), CorrelationIds()).proposals), 1
        )
        with self.assertRaises(DomainError) as raised:
            wrapper.propose("turn on", self.route(), CorrelationIds())
        self.assertEqual(raised.exception.detail.code.value, "rate_limited")

        budget_limited = CapacityControlledProposer(
            StaticProposer([proposal]),
            concurrency=ConcurrencyGate(1),
            rate_limiter=TokenBucketRateLimiter(1, 2, clock=clock),
            in_flight_tokens=TokenBudgetPool(50),
            reservation_tokens=80,
        )
        with self.assertRaises(DomainError) as budget_error:
            budget_limited.propose("turn on", self.route(), CorrelationIds())
        self.assertEqual(budget_error.exception.detail.code.value, "budget_exhausted")

    def test_grounder_wrapper_limits_batch_cost_and_reports_queue_time(self):
        clock = Clock()
        telemetry = InMemoryTelemetry()
        inner = FakeGrounder()
        wrapper = CapacityControlledGrounderClient(
            inner,
            concurrency=ConcurrencyGate(1),
            rate_limiter=TokenBucketRateLimiter(1, 2, clock=clock),
            telemetry=telemetry,
        )
        candidate = GrounderCandidate(DeviceRef("home-1", "light-1"), "Lamp")
        request = GrounderRequest("data:image/png;base64,AA", "lamp", [candidate])

        self.assertEqual(wrapper.ground(request), "grounded")
        with self.assertRaises(TimeoutError):
            wrapper.ground_batch([request, request])
        self.assertEqual(inner.calls, 1)
        self.assertTrue(any(name == "grounder.queue_ms" for name, _ in telemetry.observations))

    def test_resilient_planner_retries_transport_failure_only(self):
        class Flaky:
            def __init__(self):
                self.calls = 0

            def propose(self, *args, **kwargs):
                self.calls += 1
                if self.calls < 3:
                    raise TimeoutError("provider timeout")
                return ProposalResult(())

        flaky = Flaky()
        wrapper = ResilientProposer(
            flaky,
            retry_policy=RetryPolicy(
                max_attempts=3, base_delay_seconds=0, jitter_ratio=0
            ),
        )
        result = wrapper.propose("request", self.route(), CorrelationIds())
        self.assertEqual(result.proposals, ())
        self.assertEqual(flaky.calls, 3)


if __name__ == "__main__":
    unittest.main()
