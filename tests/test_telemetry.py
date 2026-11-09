from __future__ import annotations

import unittest

from homeclaw.domain import CorrelationIds
from homeclaw.observability import InMemoryTelemetry, SpanStatus, redact_attributes


class TelemetryTests(unittest.TestCase):
    def test_span_preserves_correlation_and_duration(self) -> None:
        telemetry = InMemoryTelemetry()
        ids = CorrelationIds()

        with telemetry.span("router.retrieve", ids, {"skill_count": 3}):
            pass

        self.assertEqual(len(telemetry.spans), 1)
        self.assertEqual(telemetry.spans[0].ids.trace_id, ids.trace_id)
        self.assertEqual(telemetry.spans[0].status, SpanStatus.OK)
        self.assertGreaterEqual(telemetry.spans[0].duration_ms, 0.0)

    def test_span_records_and_reraises_error(self) -> None:
        telemetry = InMemoryTelemetry()
        with self.assertRaisesRegex(RuntimeError, "broken"):
            with telemetry.span("mcp.call", CorrelationIds()):
                raise RuntimeError("broken")

        self.assertEqual(telemetry.spans[0].status, SpanStatus.ERROR)
        self.assertEqual(telemetry.spans[0].error_type, "RuntimeError")

    def test_sensitive_attributes_are_redacted(self) -> None:
        safe = redact_attributes(
            {"api_key": "secret-value", "authorization_header": "bearer", "model": "gpt"}
        )
        self.assertEqual(safe["api_key"], "[REDACTED]")
        self.assertEqual(safe["authorization_header"], "[REDACTED]")
        self.assertEqual(safe["model"], "gpt")

    def test_metrics_are_grouped_by_attributes(self) -> None:
        telemetry = InMemoryTelemetry()
        telemetry.increment("workflow.requests", attributes={"status": "ok"})
        telemetry.increment("workflow.requests", attributes={"status": "ok"})
        telemetry.observe("router.latency_ms", 4.0, {"route": "lighting"})

        self.assertEqual(next(iter(telemetry.counters.values())), 2)
        self.assertEqual(next(iter(telemetry.observations.values())), [4.0])


if __name__ == "__main__":
    unittest.main()
