from __future__ import annotations

import unittest
from datetime import timedelta

from homeclaw.domain import ActionProposal, DeviceRef, IdempotencyClass, RiskLevel
from homeclaw.domain.models import utc_now
from homeclaw.verification import (
    ActionVerifier,
    DeviceRecord,
    InMemoryCapabilityRegistry,
    ParameterSpec,
    ToolSpec,
    VerificationContext,
)


class VerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.device = DeviceRef("home-1", "light-1", "living-room", "brightness")
        self.tool = ToolSpec(
            name="set_light_brightness",
            capability="brightness",
            parameters={
                "brightness": ParameterSpec("brightness", "integer", minimum=0, maximum=100)
            },
        )
        self.registry = InMemoryCapabilityRegistry(
            [DeviceRecord(self.device, {self.tool.name: self.tool})], version="registry-7"
        )
        self.verifier = ActionVerifier(self.registry)

    def proposal(self, **overrides):
        values = {
            "tool_name": self.tool.name,
            "target": self.device,
            "arguments": {"brightness": 40},
            "source_skill": "lighting",
            "expected_state": {"brightness": 40},
            "verification": {"path": "brightness", "equals": 40},
        }
        values.update(overrides)
        return ActionProposal(**values)

    def test_valid_action_is_accepted_from_registry_evidence(self) -> None:
        decision = self.verifier.verify(self.proposal())
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.registry_version, "registry-7")

    def test_invalid_parameter_and_unknown_device_are_rejected(self) -> None:
        invalid = self.verifier.verify(self.proposal(arguments={"brightness": 101}))
        self.assertFalse(invalid.accepted)
        self.assertIn("invalid_parameter", {issue.code for issue in invalid.issues})

        missing_device = DeviceRef("home-1", "missing", "living-room")
        missing = self.verifier.verify(self.proposal(target=missing_device))
        self.assertEqual(missing.issues[0].code, "device_not_found")

    def test_stale_state_and_offline_device_are_retryable(self) -> None:
        stale_registry = InMemoryCapabilityRegistry(
            [
                DeviceRecord(
                    self.device,
                    {self.tool.name: self.tool},
                    online=False,
                    state_observed_at=utc_now() - timedelta(minutes=5),
                )
            ]
        )
        decision = ActionVerifier(stale_registry).verify(self.proposal())
        codes = {issue.code for issue in decision.issues}
        self.assertEqual(codes, {"device_offline", "stale_state"})
        self.assertTrue(all(issue.retryable for issue in decision.issues))

    def test_risk_and_idempotency_must_match_registry_policy(self) -> None:
        dangerous_tool = ToolSpec(
            name="unlock_door",
            capability="lock",
            idempotency=IdempotencyClass.IDEMPOTENT_WITH_KEY,
            risk=RiskLevel.HIGH,
        )
        lock = DeviceRef("home-1", "front-lock", "entrance", "lock")
        registry = InMemoryCapabilityRegistry(
            [DeviceRecord(lock, {dangerous_tool.name: dangerous_tool})]
        )
        proposal = ActionProposal(
            tool_name="unlock_door",
            target=lock,
            arguments={},
            source_skill="security",
            expected_state={"locked": False},
            verification={"path": "locked", "equals": False},
            risk=RiskLevel.HIGH,
        )

        denied = ActionVerifier(registry).verify(proposal)
        allowed = ActionVerifier(registry).verify(
            proposal, VerificationContext(authorized_risk=RiskLevel.HIGH)
        )

        self.assertIn("risk_not_authorized", {issue.code for issue in denied.issues})
        self.assertTrue(allowed.accepted)


if __name__ == "__main__":
    unittest.main()
