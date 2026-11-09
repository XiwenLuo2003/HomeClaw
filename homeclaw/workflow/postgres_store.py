"""DB-API PostgreSQL checkpoint store using deploy/postgres migrations."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Optional

from homeclaw.domain.models import utc_now
from homeclaw.workflow.state import WorkflowState
from homeclaw.workflow.store import CheckpointConflict, OutboxMessage


class PostgresCheckpointStore:
    """Accepts a connection factory, avoiding a mandatory psycopg dependency."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self.connection_factory = connection_factory

    def create(self, state: WorkflowState) -> WorkflowState:
        stored = WorkflowState.from_dict(state.to_dict())
        stored.revision = 0
        raw = json.dumps(stored.to_dict(), separators=(",", ":"), sort_keys=True)
        try:
            with self.connection_factory() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO workflow_task(
                      task_id, request_id, trace_id, status, current_node, revision,
                      deadline_at, state, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 0, %s, %s::jsonb, %s, %s)
                    """,
                    (
                        stored.ids.task_id,
                        stored.ids.request_id,
                        stored.ids.trace_id,
                        stored.status.value,
                        stored.current_node.value,
                        stored.deadline_at,
                        raw,
                        stored.created_at,
                        stored.updated_at,
                    ),
                )
                cursor.execute(
                    "INSERT INTO workflow_checkpoint(task_id, revision, node, state) VALUES (%s, 0, %s, %s::jsonb)",
                    (stored.ids.task_id, stored.current_node.value, raw),
                )
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505":
                raise CheckpointConflict(f"task already exists: {stored.ids.task_id}") from exc
            raise
        return stored

    def load(self, task_id: str) -> Optional[WorkflowState]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT state::text FROM workflow_task WHERE task_id = %s", (task_id,))
            row = cursor.fetchone()
        return WorkflowState.from_dict(json.loads(row[0])) if row else None

    def save(self, state: WorkflowState, expected_revision: int) -> WorkflowState:
        return self.save_with_outbox(state, expected_revision, [])

    def save_with_outbox(
        self,
        state: WorkflowState,
        expected_revision: int,
        messages: list[OutboxMessage],
    ) -> WorkflowState:
        stored = WorkflowState.from_dict(state.to_dict())
        stored.revision = expected_revision + 1
        stored.updated_at = utc_now()
        raw = json.dumps(stored.to_dict(), separators=(",", ":"), sort_keys=True)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE workflow_task SET status=%s, current_node=%s, revision=%s,
                    state=%s::jsonb, updated_at=%s
                WHERE task_id=%s AND revision=%s RETURNING revision
                """,
                (
                    stored.status.value,
                    stored.current_node.value,
                    stored.revision,
                    raw,
                    stored.updated_at,
                    stored.ids.task_id,
                    expected_revision,
                ),
            )
            if cursor.fetchone() is None:
                raise CheckpointConflict(
                    f"stale checkpoint for {stored.ids.task_id}: expected {expected_revision}"
                )
            cursor.execute(
                "INSERT INTO workflow_checkpoint(task_id, revision, node, state) VALUES (%s, %s, %s, %s::jsonb)",
                (stored.ids.task_id, stored.revision, stored.current_node.value, raw),
            )
            for message in messages:
                cursor.execute(
                    """
                    INSERT INTO workflow_outbox(message_id, task_id, topic, payload, created_at, published_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                    ON CONFLICT (message_id) DO NOTHING
                    """,
                    (
                        message.message_id,
                        message.task_id,
                        message.topic,
                        json.dumps(dict(message.payload), separators=(",", ":")),
                        message.created_at,
                        message.published_at,
                    ),
                )
        return stored

    def enqueue(self, message: OutboxMessage) -> None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO workflow_outbox(message_id, task_id, topic, payload, created_at, published_at)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s) ON CONFLICT (message_id) DO NOTHING
                """,
                (
                    message.message_id,
                    message.task_id,
                    message.topic,
                    json.dumps(dict(message.payload), separators=(",", ":")),
                    message.created_at,
                    message.published_at,
                ),
            )

    def pending(self, limit: int = 100) -> list[OutboxMessage]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT message_id, task_id, topic, payload::text, created_at
                FROM workflow_outbox WHERE published_at IS NULL
                ORDER BY created_at LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return [
            OutboxMessage(row[1], row[2], json.loads(row[3]), row[0], row[4]) for row in rows
        ]

    def mark_published(self, message_id: str, published_at: Optional[datetime] = None) -> None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE workflow_outbox SET published_at=%s
                WHERE message_id=%s AND published_at IS NULL RETURNING message_id
                """,
                (published_at or utc_now(), message_id),
            )
            if cursor.fetchone() is None:
                raise KeyError(message_id)
