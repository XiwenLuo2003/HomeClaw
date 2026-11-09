from __future__ import annotations

import json
import unittest

from homeclaw.domain import (
    ActionProposal,
    ActionStatus,
    BBox,
    CorrelationIds,
    DeviceRef,
    ExecutionEvidence,
    GroundingCandidate,
    GroundingResult,
    IdempotencyClass,
    MessageEnvelope,
    VerificationDecision,
)


class DomainContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.device = DeviceRef(
            home_id="home-1",
            room_id="living-room",
            device_id="light-1",
            capability="brightness",
        )

    def test_action_proposal_is_json_serializable(self) -> None:
        proposal = ActionProposal(
            tool_name="set_light_brightness",
            target=self.device,
            arguments={"brightness": 40},
            expected_state={"brightness": 40},
            verification={"path": "brightness", "equals": 40},
            source_skill="lighting",
        )

        encoded = json.dumps(proposal.to_dict())

        self.assertIn("set_light_brightness", encoded)
        self.assertIn('"idempotency": "idempotent_with_key"', encoded)

    def test_non_idempotent_action_requires_verification(self) -> None:
        with self.assertRaises(ValueError):
            ActionProposal(
                tool_name="toggle_light",
                target=self.device,
                arguments={},
                expected_state={"power": "on"},
                verification={},
                source_skill="lighting",
                idempotency=IdempotencyClass.NON_IDEMPOTENT,
            )

    def test_ambiguous_grounding_cannot_select_device(self) -> None:
        candidate = GroundingCandidate(
            device=self.device,
            score=0.8,
            bbox=BBox(0.1, 0.1, 0.4, 0.4),
        )
        with self.assertRaises(ValueError):
            GroundingResult(
                query="the lamp next to the television",
                candidates=[candidate],
                selected_device_id="light-1",
                ambiguous=True,
                model_version="qwen3-vl-4b-homeclaw",
            )

    def test_success_evidence_requires_observed_state(self) -> None:
        ids = CorrelationIds().for_command()
        with self.assertRaises(ValueError):
            ExecutionEvidence(
                ids=ids,
                action_id="action-1",
                status=ActionStatus.SUCCEEDED,
                source="mqtt-state",
            )

    def test_envelope_preserves_correlation_ids(self) -> None:
        ids = CorrelationIds().for_command()
        envelope = MessageEnvelope(
            message_type="action.requested",
            ids=ids,
            payload={"action_id": "action-1"},
            producer="workflow-host",
        )

        raw = envelope.to_dict()

        self.assertEqual(raw["ids"]["trace_id"], ids.trace_id)
        self.assertEqual(raw["ids"]["command_id"], ids.command_id)
        json.dumps(raw)

    def test_accepted_verification_has_no_issues(self) -> None:
        decision = VerificationDecision(accepted=True)
        self.assertTrue(decision.accepted)


if __name__ == "__main__":
    unittest.main()
