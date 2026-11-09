"""Workflow state and execution budgets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping, Optional

from homeclaw.domain import CorrelationIds, ErrorDetail, TaskStatus
from homeclaw.domain.models import utc_now


class WorkflowNode(str, Enum):
    RECEIVE = "receive"
    GROUND = "ground"
    ROUTE = "route"
    PLAN = "plan"
    VERIFY = "verify"
    EXECUTE = "execute"
    CONFIRM = "confirm"
    REPLAN = "replan"
    COMPLETE = "complete"
    REJECT = "reject"
    FAIL = "fail"

    @property
    def terminal(self) -> bool:
        return self in (WorkflowNode.COMPLETE, WorkflowNode.REJECT, WorkflowNode.FAIL)


@dataclass(frozen=True)
class ExecutionBudget:
    max_steps: int = 24
    max_replans: int = 2
    max_tokens: int = 16_000
    timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if self.max_steps <= 0 or self.max_tokens <= 0 or self.timeout_seconds <= 0:
            raise ValueError("workflow budget values must be positive")
        if self.max_replans < 0:
            raise ValueError("max_replans must be non-negative")


@dataclass
class WorkflowState:
    ids: CorrelationIds
    user_input: str
    status: TaskStatus = TaskStatus.RECEIVED
    current_node: WorkflowNode = WorkflowNode.RECEIVE
    revision: int = 0
    step_count: int = 0
    replan_count: int = 0
    tokens_used: int = 0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    deadline_at: Optional[datetime] = None
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[ErrorDetail] = field(default_factory=list)
    completed_nodes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.user_input.strip():
            raise ValueError("workflow user_input must not be empty")
        if self.deadline_at is not None and self.deadline_at.tzinfo is None:
            raise ValueError("deadline_at must be timezone-aware")

    @classmethod
    def create(
        cls,
        user_input: str,
        budget: ExecutionBudget,
        ids: Optional[CorrelationIds] = None,
        initial_data: Optional[Mapping[str, Any]] = None,
    ) -> "WorkflowState":
        now = utc_now()
        return cls(
            ids=ids or CorrelationIds(),
            user_input=user_input,
            deadline_at=now + timedelta(seconds=budget.timeout_seconds),
            created_at=now,
            updated_at=now,
            data=dict(initial_data or {}),
        )

    @property
    def expired(self) -> bool:
        return self.deadline_at is not None and utc_now() >= self.deadline_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "ids": self.ids.to_dict(),
            "user_input": self.user_input,
            "status": self.status.value,
            "current_node": self.current_node.value,
            "revision": self.revision,
            "step_count": self.step_count,
            "replan_count": self.replan_count,
            "tokens_used": self.tokens_used,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
            "deadline_at": (
                self.deadline_at.astimezone(timezone.utc).isoformat()
                if self.deadline_at is not None
                else None
            ),
            "data": self.data,
            "errors": [error.to_dict() for error in self.errors],
            "completed_nodes": list(self.completed_nodes),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "WorkflowState":
        from homeclaw.domain import ErrorCode

        ids_raw = raw["ids"]
        errors = [
            ErrorDetail(
                code=ErrorCode(item["code"]),
                message=item["message"],
                retryable=bool(item.get("retryable", False)),
                component=str(item.get("component", "")),
                metadata=dict(item.get("metadata", {})),
            )
            for item in raw.get("errors", [])
        ]
        return cls(
            ids=CorrelationIds(
                trace_id=ids_raw["trace_id"],
                request_id=ids_raw["request_id"],
                task_id=ids_raw["task_id"],
                command_id=ids_raw.get("command_id"),
            ),
            user_input=str(raw["user_input"]),
            status=TaskStatus(raw["status"]),
            current_node=WorkflowNode(raw["current_node"]),
            revision=int(raw.get("revision", 0)),
            step_count=int(raw.get("step_count", 0)),
            replan_count=int(raw.get("replan_count", 0)),
            tokens_used=int(raw.get("tokens_used", 0)),
            created_at=datetime.fromisoformat(raw["created_at"]),
            updated_at=datetime.fromisoformat(raw["updated_at"]),
            deadline_at=(
                datetime.fromisoformat(raw["deadline_at"])
                if raw.get("deadline_at")
                else None
            ),
            data=dict(raw.get("data", {})),
            errors=errors,
            completed_nodes=list(raw.get("completed_nodes", [])),
        )
