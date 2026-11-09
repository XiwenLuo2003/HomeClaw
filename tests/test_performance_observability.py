from __future__ import annotations

import unittest

from homeclaw.domain import ActionProposal, CorrelationIds, DeviceRef
from homeclaw.eval.performance import summarize_spans
from homeclaw.mqtt import CommandMapping, InMemoryMqttTransport, MqttCommandBridge
from homeclaw.observability import InMemoryTelemetry, SpanRecord, SpanStatus
from homeclaw.routing import RouteRequest, SkillRegistry, SkillRouter
from pathlib import Path


class PerformanceTests(unittest.TestCase):
    def test_summary_reports_component_p50_p95_and_errors(self) -> None:
        ids = CorrelationIds()
        spans = [
            SpanRecord("router.retrieve", ids, duration_ms=1.0),
            SpanRecord("router.retrieve", ids, duration_ms=2.0),
            SpanRecord("router.retrieve", ids, duration_ms=10.0, status=SpanStatus.ERROR),
        ]

        result = summarize_spans(spans)["router.retrieve"]

        self.assertEqual(result.count, 3)
        self.assertEqual(result.error_count, 1)
        self.assertEqual(result.p50_ms, 2.0)
        self.assertEqual(result.p95_ms, 10.0)

    def test_router_and_mqtt_propagate_same_trace_and_command_ids(self) -> None:
        telemetry = InMemoryTelemetry()
        registry_path = Path(__file__).resolve().parents[1] / "homeclaw" / "skills" / "registry.json"
        router = SkillRouter(SkillRegistry.from_json(registry_path), telemetry=telemetry)
        ids = CorrelationIds().for_command("cmd-observed")
        router.route(RouteRequest("turn on the light", ids=ids))

        transport = InMemoryMqttTransport()

        def respond(topic, payload, broker):
            broker.inject(
                "home/home-1/light-1/state",
                {"command_id": payload["command_id"], "sequence": 1, "state": {"power": "on"}},
            )

        transport.on_publish = respond
        bridge = MqttCommandBridge(
            transport,
            [CommandMapping("turn_light_on", "home/home-1/light-1/command", "home/home-1/light-1/state")],
            telemetry=telemetry,
        )
        proposal = ActionProposal(
            "turn_light_on",
            DeviceRef("home-1", "light-1"),
            {},
            "lighting",
            {"power": "on"},
        )
        bridge.execute(proposal, ids)

        by_name = {span.name: span for span in telemetry.spans}
        self.assertEqual(
            set(by_name), {"router.retrieve", "mqtt.publish", "mqtt.wait_state"}
        )
        self.assertTrue(all(span.ids.trace_id == ids.trace_id for span in telemetry.spans))
        self.assertTrue(all(span.ids.command_id == "cmd-observed" for span in telemetry.spans))


if __name__ == "__main__":
    unittest.main()
