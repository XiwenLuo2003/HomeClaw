from __future__ import annotations

import unittest

from homeclaw.workflow import (
    ExecutionBudget,
    OutboxMessage,
    PostgresCheckpointStore,
    WorkflowState,
)


class Cursor:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, parameters=()):
        self.statements.append((" ".join(sql.split()), parameters))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class Connection:
    def __init__(self, cursor):
        self.value = cursor
        self.enter_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.value


class PostgresCheckpointTests(unittest.TestCase):
    def test_checkpoint_and_outbox_are_written_in_same_connection_context(self):
        cursor = Cursor(rows=[(1,)])
        connection = Connection(cursor)
        store = PostgresCheckpointStore(lambda: connection)
        state = WorkflowState.create("turn on light", ExecutionBudget())
        message = OutboxMessage(
            task_id=state.ids.task_id,
            topic="workflow.changed",
            payload={"node": "route"},
            message_id="message-1",
        )

        stored = store.save_with_outbox(state, 0, [message])

        self.assertEqual(stored.revision, 1)
        self.assertEqual(connection.enter_count, 1)
        rendered = "\n".join(sql for sql, _ in cursor.statements)
        self.assertIn("UPDATE workflow_task", rendered)
        self.assertIn("INSERT INTO workflow_checkpoint", rendered)
        self.assertIn("INSERT INTO workflow_outbox", rendered)


if __name__ == "__main__":
    unittest.main()
