from __future__ import annotations

import unittest

from homeclaw.domain import ActionProposal, ActionStatus, CorrelationIds, DeviceRef, ExecutionEvidence
from homeclaw.workflow import PostgresActionAttemptStore


class Cursor:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, parameters=()):
        self.statements.append((" ".join(sql.split()), parameters))

    def fetchone(self):
        return self.results.pop(0) if self.results else None


class Connection:
    def __init__(self, cursor):
        self.value = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.value


class ActionAttemptStoreTests(unittest.TestCase):
    def test_claim_is_unique_and_completion_requires_existing_attempt(self) -> None:
        ids = CorrelationIds().for_command("cmd-1")
        proposal = ActionProposal(
            "turn_light_on",
            DeviceRef("home-1", "light-1"),
            {},
            "lighting",
            {"power": "on"},
        )
        claim_cursor = Cursor([("cmd-1",)])
        store = PostgresActionAttemptStore(lambda: Connection(claim_cursor))
        self.assertTrue(store.claim(ids, proposal, idempotency_key="task-1:action-1"))
        self.assertIn("ON CONFLICT DO NOTHING", claim_cursor.statements[0][0])

        duplicate_cursor = Cursor([None])
        duplicate = PostgresActionAttemptStore(lambda: Connection(duplicate_cursor))
        self.assertFalse(
            duplicate.claim(ids, proposal, idempotency_key="task-1:action-1")
        )

        evidence = ExecutionEvidence(
            ids,
            proposal.action_id,
            ActionStatus.SUCCEEDED,
            "mqtt-state",
            {"power": "on"},
            "3",
        )
        complete_cursor = Cursor([("cmd-1",)])
        PostgresActionAttemptStore(lambda: Connection(complete_cursor)).complete(evidence)
        self.assertIn("UPDATE action_attempt", complete_cursor.statements[0][0])


if __name__ == "__main__":
    unittest.main()
