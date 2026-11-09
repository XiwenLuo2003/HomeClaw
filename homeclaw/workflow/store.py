"""Checkpoint and transactional-outbox storage interfaces."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Optional, Protocol

from homeclaw.domain.models import new_id, utc_now
from homeclaw.workflow.state import WorkflowState


class CheckpointConflict(RuntimeError):
    """Raised when a stale workflow writer attempts to overwrite a checkpoint."""


@dataclass(frozen=True)
class OutboxMessage:
    task_id: str
    topic: str
    payload: Mapping[str, Any]
    message_id: str = field(default_factory=lambda: new_id("outbox"))
    created_at: datetime = field(default_factory=utc_now)
    published_at: Optional[datetime] = None


class CheckpointStore(Protocol):
    def create(self, state: WorkflowState) -> WorkflowState:
        ...

    def load(self, task_id: str) -> Optional[WorkflowState]:
        ...

    def save(self, state: WorkflowState, expected_revision: int) -> WorkflowState:
        ...

    def save_with_outbox(
        self,
        state: WorkflowState,
        expected_revision: int,
        messages: list["OutboxMessage"],
    ) -> WorkflowState:
        ...

    def enqueue(self, message: OutboxMessage) -> None:
        ...

    def pending(self, limit: int = 100) -> list[OutboxMessage]:
        ...

    def mark_published(self, message_id: str, published_at: Optional[datetime] = None) -> None:
        ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}
        self._outbox: dict[str, OutboxMessage] = {}
        self._lock = RLock()

    @staticmethod
    def _copy(state: WorkflowState) -> WorkflowState:
        return WorkflowState.from_dict(json.loads(json.dumps(state.to_dict())))

    def create(self, state: WorkflowState) -> WorkflowState:
        with self._lock:
            if state.ids.task_id in self._states:
                raise CheckpointConflict(f"task already exists: {state.ids.task_id}")
            stored = self._copy(state)
            stored.revision = 0
            self._states[state.ids.task_id] = stored.to_dict()
            return self._copy(stored)

    def load(self, task_id: str) -> Optional[WorkflowState]:
        with self._lock:
            raw = self._states.get(task_id)
            return WorkflowState.from_dict(json.loads(json.dumps(raw))) if raw else None

    def save(self, state: WorkflowState, expected_revision: int) -> WorkflowState:
        return self.save_with_outbox(state, expected_revision, [])

    def save_with_outbox(
        self,
        state: WorkflowState,
        expected_revision: int,
        messages: list[OutboxMessage],
    ) -> WorkflowState:
        with self._lock:
            current = self._states.get(state.ids.task_id)
            if current is None:
                raise KeyError(state.ids.task_id)
            actual_revision = int(current["revision"])
            if actual_revision != expected_revision:
                raise CheckpointConflict(
                    f"stale checkpoint for {state.ids.task_id}: expected {expected_revision}, actual {actual_revision}"
                )
            stored = self._copy(state)
            stored.revision = expected_revision + 1
            stored.updated_at = utc_now()
            self._states[state.ids.task_id] = stored.to_dict()
            for message in messages:
                self._outbox.setdefault(message.message_id, message)
            return self._copy(stored)

    def enqueue(self, message: OutboxMessage) -> None:
        with self._lock:
            self._outbox.setdefault(message.message_id, message)

    def pending(self, limit: int = 100) -> list[OutboxMessage]:
        with self._lock:
            items = [message for message in self._outbox.values() if message.published_at is None]
            return sorted(items, key=lambda item: item.created_at)[:limit]

    def mark_published(self, message_id: str, published_at: Optional[datetime] = None) -> None:
        with self._lock:
            message = self._outbox[message_id]
            self._outbox[message_id] = OutboxMessage(
                task_id=message.task_id,
                topic=message.topic,
                payload=message.payload,
                message_id=message.message_id,
                created_at=message.created_at,
                published_at=published_at or utc_now(),
            )


class SqliteCheckpointStore:
    """Dependency-free local implementation with PostgreSQL-equivalent semantics.

    It is intended for tests and single-node development.  Production uses the
    PostgreSQL schema under ``deploy/postgres`` and an adapter with the same
    CheckpointStore contract.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._setup()

    def _setup(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_checkpoint (
                    task_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_outbox (
                    message_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    published_at TEXT NULL
                );
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SqliteCheckpointStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def create(self, state: WorkflowState) -> WorkflowState:
        stored = WorkflowState.from_dict(state.to_dict())
        stored.revision = 0
        raw = json.dumps(stored.to_dict(), separators=(",", ":"), sort_keys=True)
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    "INSERT INTO workflow_checkpoint(task_id, revision, state_json, updated_at) VALUES (?, 0, ?, ?)",
                    (state.ids.task_id, raw, utc_now().isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise CheckpointConflict(f"task already exists: {state.ids.task_id}") from exc
        return WorkflowState.from_dict(json.loads(raw))

    def load(self, task_id: str) -> Optional[WorkflowState]:
        with self._lock:
            row = self._connection.execute(
                "SELECT state_json FROM workflow_checkpoint WHERE task_id = ?", (task_id,)
            ).fetchone()
        return WorkflowState.from_dict(json.loads(row["state_json"])) if row else None

    def save(self, state: WorkflowState, expected_revision: int) -> WorkflowState:
        return self.save_with_outbox(state, expected_revision, [])

    def save_with_outbox(
        self,
        state: WorkflowState,
        expected_revision: int,
        messages: list[OutboxMessage],
    ) -> WorkflowState:
        next_revision = expected_revision + 1
        stored = WorkflowState.from_dict(state.to_dict())
        stored.revision = next_revision
        stored.updated_at = utc_now()
        raw = json.dumps(stored.to_dict(), separators=(",", ":"), sort_keys=True)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE workflow_checkpoint
                SET revision = ?, state_json = ?, updated_at = ?
                WHERE task_id = ? AND revision = ?
                """,
                (next_revision, raw, stored.updated_at.isoformat(), stored.ids.task_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise CheckpointConflict(
                    f"stale checkpoint for {stored.ids.task_id}: expected {expected_revision}"
                )
            for message in messages:
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO workflow_outbox(
                        message_id, task_id, topic, payload_json, created_at, published_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.message_id,
                        message.task_id,
                        message.topic,
                        json.dumps(dict(message.payload), separators=(",", ":"), sort_keys=True),
                        message.created_at.isoformat(),
                        message.published_at.isoformat() if message.published_at else None,
                    ),
                )
        return WorkflowState.from_dict(json.loads(raw))

    def enqueue(self, message: OutboxMessage) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO workflow_outbox(
                    message_id, task_id, topic, payload_json, created_at, published_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.task_id,
                    message.topic,
                    json.dumps(dict(message.payload), separators=(",", ":"), sort_keys=True),
                    message.created_at.isoformat(),
                    message.published_at.isoformat() if message.published_at else None,
                ),
            )

    def pending(self, limit: int = 100) -> list[OutboxMessage]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM workflow_outbox
                WHERE published_at IS NULL ORDER BY created_at ASC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            OutboxMessage(
                task_id=row["task_id"],
                topic=row["topic"],
                payload=json.loads(row["payload_json"]),
                message_id=row["message_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                published_at=None,
            )
            for row in rows
        ]

    def mark_published(self, message_id: str, published_at: Optional[datetime] = None) -> None:
        timestamp = (published_at or utc_now()).astimezone(timezone.utc).isoformat()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE workflow_outbox SET published_at = ? WHERE message_id = ? AND published_at IS NULL",
                (timestamp, message_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(message_id)
