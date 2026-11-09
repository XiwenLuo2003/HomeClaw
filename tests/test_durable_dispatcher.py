from __future__ import annotations

import unittest
from types import SimpleNamespace

from homeclaw.agent import DurableActionDispatcher
from homeclaw.domain import ActionProposal, ActionStatus, CorrelationIds, DeviceRef, ExecutionEvidence


class Inner:
    def __init__(self):
        self.ids = []

    def execute(self, proposal, ids, allowed_tools):
        self.ids.append(ids)
        return ExecutionEvidence(
            ids,
            proposal.action_id,
            ActionStatus.SUCCEEDED,
            "mqtt-state",
            {"power": "on"},
            "1",
        )


class Attempts:
    def __init__(self, claimed=True, existing=None):
        self.claimed = claimed
        self.existing = existing
        self.completed = []
        self.retried = []

    def claim(self, ids, proposal, idempotency_key):
        self.key = idempotency_key
        return self.claimed

    def get_by_idempotency_key(self, key):
        return self.existing

    def complete(self, evidence):
        self.completed.append(evidence)

    def record_retry(self, command_id):
        self.retried.append(command_id)


class DurableDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.proposal = ActionProposal(
            "turn_light_on",
            DeviceRef("home-1", "light-1"),
            {},
            "lighting",
            {"power": "on"},
        )

    def test_new_attempt_is_claimed_and_completed(self):
        inner = Inner()
        attempts = Attempts(claimed=True)
        ids = CorrelationIds().for_command("cmd-new")

        evidence = DurableActionDispatcher(inner, attempts).execute(
            self.proposal, ids, ["turn_light_on"]
        )

        self.assertEqual(evidence.status, ActionStatus.SUCCEEDED)
        self.assertEqual(attempts.key, f"{ids.task_id}:{self.proposal.action_id}")
        self.assertEqual(len(attempts.completed), 1)

    def test_incomplete_replay_reuses_original_command_id(self):
        inner = Inner()
        attempts = Attempts(
            claimed=False,
            existing=SimpleNamespace(command_id="cmd-original", evidence=None),
        )
        ids = CorrelationIds().for_command("cmd-after-crash")

        DurableActionDispatcher(inner, attempts).execute(
            self.proposal, ids, ["turn_light_on"]
        )

        self.assertEqual(inner.ids[0].command_id, "cmd-original")
        self.assertEqual(attempts.retried, ["cmd-original"])

    def test_completed_replay_returns_evidence_without_dispatch(self):
        existing_ids = CorrelationIds().for_command("cmd-complete")
        existing = ExecutionEvidence(
            existing_ids,
            self.proposal.action_id,
            ActionStatus.SUCCEEDED,
            "mqtt-state",
            {"power": "on"},
            "5",
        )
        inner = Inner()
        attempts = Attempts(
            claimed=False,
            existing=SimpleNamespace(
                command_id="cmd-complete", evidence=existing.to_dict()
            ),
        )

        restored = DurableActionDispatcher(inner, attempts).execute(
            self.proposal,
            CorrelationIds().for_command("cmd-new"),
            ["turn_light_on"],
        )

        self.assertEqual(restored.ids.command_id, "cmd-complete")
        self.assertEqual(inner.ids, [])


if __name__ == "__main__":
    unittest.main()
