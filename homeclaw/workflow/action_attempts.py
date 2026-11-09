"""Durable PostgreSQL action-attempt audit and idempotency claims."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Optional

from homeclaw.domain import ActionProposal, ActionStatus, CorrelationIds, ExecutionEvidence
from homeclaw.domain.models import utc_now


@dataclass(frozen=True)
class ActionAttempt:
    command_id: str
    task_id: str
    action_id: str
    idempotency_key: str
    status: ActionStatus
    request: Mapping[str, Any]
    evidence: Mapping[str, Any] | None
    attempt_count: int
    created_at: datetime
    updated_at: datetime


class PostgresActionAttemptStore:
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self.connection_factory = connection_factory

    def claim(
        self,
        ids: CorrelationIds,
        proposal: ActionProposal,
        *,
        idempotency_key: str,
    ) -> bool:
        if ids.command_id is None:
            raise ValueError("command_id is required for a durable action attempt")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO action_attempt(
                  command_id, task_id, action_id, idempotency_key, status,
                  request, attempt_count
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, 1)
                ON CONFLICT DO NOTHING RETURNING command_id
                """,
                (
                    ids.command_id,
                    ids.task_id,
                    proposal.action_id,
                    idempotency_key,
                    ActionStatus.DISPATCHED.value,
                    json.dumps(proposal.to_dict(), separators=(",", ":"), sort_keys=True),
                ),
            )
            return cursor.fetchone() is not None

    def complete(self, evidence: ExecutionEvidence) -> None:
        command_id = evidence.ids.command_id
        if command_id is None:
            raise ValueError("command_id is required for action evidence")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE action_attempt SET status=%s, evidence=%s::jsonb,
                  updated_at=%s
                WHERE command_id=%s RETURNING command_id
                """,
                (
                    evidence.status.value,
                    json.dumps(evidence.to_dict(), separators=(",", ":"), sort_keys=True),
                    utc_now(),
                    command_id,
                ),
            )
            if cursor.fetchone() is None:
                raise KeyError(command_id)

    def record_retry(self, command_id: str) -> None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE action_attempt SET attempt_count=attempt_count + 1,
                  updated_at=%s WHERE command_id=%s RETURNING command_id
                """,
                (utc_now(), command_id),
            )
            if cursor.fetchone() is None:
                raise KeyError(command_id)

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[ActionAttempt]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT command_id, task_id, action_id, idempotency_key, status,
                       request, evidence, attempt_count, created_at, updated_at
                FROM action_attempt WHERE idempotency_key=%s
                """,
                (idempotency_key,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        request = json.loads(row[5]) if isinstance(row[5], str) else row[5]
        evidence = json.loads(row[6]) if isinstance(row[6], str) else row[6]
        return ActionAttempt(
            command_id=row[0],
            task_id=row[1],
            action_id=row[2],
            idempotency_key=row[3],
            status=ActionStatus(row[4]),
            request=request,
            evidence=evidence,
            attempt_count=int(row[7]),
            created_at=row[8],
            updated_at=row[9],
        )
