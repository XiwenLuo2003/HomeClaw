from __future__ import annotations

import unittest

from homeclaw.domain import ActionProposal, ActionStatus, CorrelationIds, DeviceRef
from homeclaw.mqtt import CommandMapping, InMemoryMqttTransport, MqttCommandBridge
from homeclaw.mqtt.transport import PublishReceipt
from homeclaw.resilience import RetryPolicy


class MqttBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = InMemoryMqttTransport()
        self.bridge = MqttCommandBridge(
            self.transport,
            [
                CommandMapping(
                    "set_light_brightness",
                    "home/home-1/light-1/command",
                    "home/home-1/light-1/state",
                )
            ],
        )
        self.proposal = ActionProposal(
            tool_name="set_light_brightness",
            target=DeviceRef("home-1", "light-1", "living-room", "brightness"),
            arguments={"brightness": 40},
            source_skill="lighting",
            expected_state={"brightness": 40},
            verification={"path": "brightness", "equals": 40},
        )

    def test_puback_is_not_treated_as_device_success(self) -> None:
        evidence = self.bridge.execute(self.proposal, CorrelationIds(), timeout_seconds=0.001)

        self.assertEqual(evidence.status, ActionStatus.UNKNOWN)
        self.assertEqual(evidence.error.code.value, "execution_unconfirmed")
        self.assertEqual(len(self.transport.published), 1)

    def test_matching_state_confirms_action_and_updates_cache(self) -> None:
        def respond(topic, payload, transport):
            transport.inject(
                "home/home-1/light-1/state",
                {
                    "command_id": payload["command_id"],
                    "sequence": 12,
                    "state": {"power": "on", "brightness": 40},
                },
            )

        self.transport.on_publish = respond
        ids = CorrelationIds().for_command("cmd-fixed")

        first = self.bridge.execute(self.proposal, ids)
        duplicate = self.bridge.execute(self.proposal, ids)

        self.assertEqual(first.status, ActionStatus.SUCCEEDED)
        self.assertEqual(first.observed_state["brightness"], 40)
        self.assertIs(duplicate, first)
        self.assertEqual(len(self.transport.published), 1)
        cached = self.bridge.state_cache.get("home-1", "light-1")
        self.assertEqual(cached.sequence, 12)

    def test_wrong_command_state_does_not_confirm(self) -> None:
        def respond(topic, payload, transport):
            transport.inject(
                "home/home-1/light-1/state",
                {
                    "command_id": "another-command",
                    "sequence": 2,
                    "state": {"brightness": 40},
                },
            )

        self.transport.on_publish = respond
        evidence = self.bridge.execute(self.proposal, CorrelationIds(), timeout_seconds=0.001)
        self.assertEqual(evidence.status, ActionStatus.UNKNOWN)

    def test_missing_mapping_is_rejected_without_publish(self) -> None:
        proposal = ActionProposal(
            tool_name="raw_topic_publish",
            target=self.proposal.target,
            arguments={},
            source_skill="lighting",
            expected_state={"power": "on"},
        )
        evidence = self.bridge.execute(proposal, CorrelationIds())
        self.assertEqual(evidence.status, ActionStatus.REJECTED)
        self.assertEqual(self.transport.published, [])

    def test_device_business_rejection_is_not_reported_as_timeout(self) -> None:
        def respond(topic, payload, transport):
            transport.inject(
                "home/home-1/light-1/state",
                {
                    "command_id": payload["command_id"],
                    "status": "rejected",
                    "reason": "physical child lock is active",
                },
            )

        self.transport.on_publish = respond
        evidence = self.bridge.execute(self.proposal, CorrelationIds())

        self.assertEqual(evidence.status, ActionStatus.REJECTED)
        self.assertEqual(evidence.error.code.value, "execution_rejected")
        self.assertIn("child lock", evidence.error.message)

    def test_broker_unavailable_is_a_retryable_dependency_failure(self) -> None:
        self.transport.accept_publish = False
        bridge = MqttCommandBridge(
            self.transport,
            list(self.bridge.mappings.values()),
            publish_retry_policy=RetryPolicy(
                max_attempts=2, base_delay_seconds=0, jitter_ratio=0
            ),
        )

        evidence = bridge.execute(self.proposal, CorrelationIds())

        self.assertEqual(evidence.status, ActionStatus.FAILED)
        self.assertEqual(evidence.error.code.value, "dependency_unavailable")
        self.assertTrue(evidence.error.retryable)
        self.assertEqual(len(self.transport.published), 2)

    def test_known_offline_device_fails_before_command_publish(self) -> None:
        transport = InMemoryMqttTransport()
        transport.inject("availability", {"status": "offline"})
        bridge = MqttCommandBridge(
            transport,
            [
                CommandMapping(
                    "set_light_brightness",
                    "command",
                    "state",
                    availability_topic="availability",
                )
            ],
        )

        evidence = bridge.execute(self.proposal, CorrelationIds())

        self.assertEqual(evidence.status, ActionStatus.FAILED)
        self.assertEqual(evidence.error.code.value, "dependency_unavailable")
        self.assertIn("offline", evidence.error.message)
        self.assertEqual(transport.published, [])

    def test_stale_retained_state_cannot_confirm_new_command(self) -> None:
        def respond(topic, payload, transport):
            transport.inject(
                "home/home-1/light-1/state",
                {
                    "sequence": 99,
                    "observed_at": "2020-01-01T00:00:00+00:00",
                    "state": {"brightness": 40},
                },
                retained=True,
            )

        self.transport.on_publish = respond
        evidence = self.bridge.execute(self.proposal, CorrelationIds(), timeout_seconds=0.001)
        self.assertEqual(evidence.status, ActionStatus.UNKNOWN)

    def test_late_ack_can_upgrade_unknown_without_republishing(self) -> None:
        ids = CorrelationIds().for_command("cmd-late")
        first = self.bridge.execute(self.proposal, ids, timeout_seconds=0.001)
        self.transport.inject(
            "home/home-1/light-1/state",
            {
                "command_id": "cmd-late",
                "sequence": 5,
                "state": {"brightness": 40},
            },
        )
        second = self.bridge.execute(self.proposal, ids, timeout_seconds=0.001)

        self.assertEqual(first.status, ActionStatus.UNKNOWN)
        self.assertEqual(second.status, ActionStatus.SUCCEEDED)
        self.assertEqual(len(self.transport.published), 1)

    def test_idempotent_publish_retry_reuses_same_command_id(self) -> None:
        class FlakyTransport(InMemoryMqttTransport):
            def __init__(self):
                super().__init__()
                self.attempts = 0

            def publish(self, topic, payload, qos=1):
                self.attempts += 1
                if self.attempts == 1:
                    self.published.append(type("Published", (), {"payload": dict(payload)})())
                    return PublishReceipt(False, reason="temporary broker failure")
                result = super().publish(topic, payload, qos)
                self.inject(
                    "state",
                    {
                        "command_id": payload["command_id"],
                        "sequence": 8,
                        "state": {"brightness": 40},
                    },
                )
                return result

        transport = FlakyTransport()
        bridge = MqttCommandBridge(
            transport,
            [CommandMapping("set_light_brightness", "command", "state")],
            publish_retry_policy=RetryPolicy(
                max_attempts=2, base_delay_seconds=0, jitter_ratio=0
            ),
        )
        ids = CorrelationIds().for_command("cmd-retry")

        evidence = bridge.execute(self.proposal, ids, timeout_seconds=0.01)

        self.assertEqual(evidence.status, ActionStatus.SUCCEEDED)
        self.assertEqual(transport.attempts, 2)
        command_ids = [message.payload["command_id"] for message in transport.published]
        self.assertEqual(command_ids, ["cmd-retry", "cmd-retry"])


if __name__ == "__main__":
    unittest.main()
