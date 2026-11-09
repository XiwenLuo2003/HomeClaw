"""Versioned, JSON-safe contracts for the HomeClaw execution path."""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from homeclaw.domain.errors import ErrorDetail


CONTRACT_VERSION = "1.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    if not prefix or not prefix.replace("_", "").isalnum():
        raise ValueError("id prefix must be alphanumeric with optional underscores")
    return f"{prefix}_{uuid.uuid4().hex}"


def _require_identifier(name: str, value: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must not be empty")
    if len(value) > 160:
        raise ValueError(f"{name} is too long")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if dataclasses.is_dataclass(value):
        return {
            item.name: _json_ready(getattr(value, item.name))
            for item in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


class TaskStatus(str, Enum):
    RECEIVED = "received"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    VERIFIED = "verified"
    DISPATCHED = "dispatched"
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"
    UNKNOWN = "unknown"


class IdempotencyClass(str, Enum):
    IDEMPOTENT = "idempotent"
    IDEMPOTENT_WITH_KEY = "idempotent_with_key"
    NON_IDEMPOTENT = "non_idempotent"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class CorrelationIds:
    trace_id: str = field(default_factory=lambda: new_id("trace"))
    request_id: str = field(default_factory=lambda: new_id("req"))
    task_id: str = field(default_factory=lambda: new_id("task"))
    command_id: Optional[str] = None

    def __post_init__(self) -> None:
        _require_identifier("trace_id", self.trace_id)
        _require_identifier("request_id", self.request_id)
        _require_identifier("task_id", self.task_id)
        if self.command_id is not None:
            _require_identifier("command_id", self.command_id)

    def for_command(self, command_id: Optional[str] = None) -> "CorrelationIds":
        return dataclasses.replace(self, command_id=command_id or new_id("cmd"))

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(self)


@dataclass(frozen=True)
class DeviceRef:
    home_id: str
    device_id: str
    room_id: Optional[str] = None
    capability: Optional[str] = None

    def __post_init__(self) -> None:
        _require_identifier("home_id", self.home_id)
        _require_identifier("device_id", self.device_id)

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(self)


@dataclass(frozen=True)
class BBox:
    """Normalized XYXY bounding box."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        values = (self.x1, self.y1, self.x2, self.y2)
        if any(value < 0.0 or value > 1.0 for value in values):
            raise ValueError("bbox coordinates must be normalized to [0, 1]")
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("bbox must have positive width and height")


@dataclass(frozen=True)
class GroundingCandidate:
    device: DeviceRef
    score: float
    bbox: Optional[BBox] = None
    evidence: str = ""

    def __post_init__(self) -> None:
        if self.score < 0.0 or self.score > 1.0:
            raise ValueError("grounding score must be in [0, 1]")


@dataclass(frozen=True)
class GroundingResult:
    query: str
    candidates: Sequence[GroundingCandidate]
    selected_device_id: Optional[str]
    ambiguous: bool
    model_version: str
    latency_ms: float = 0.0
    schema_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("grounding query must not be empty")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        candidate_ids = {candidate.device.device_id for candidate in self.candidates}
        if self.selected_device_id is not None and self.selected_device_id not in candidate_ids:
            raise ValueError("selected device must be present in candidates")
        if self.ambiguous and self.selected_device_id is not None:
            raise ValueError("ambiguous grounding cannot select a device")

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(self)


@dataclass(frozen=True)
class ActionProposal:
    tool_name: str
    target: DeviceRef
    arguments: Mapping[str, Any]
    source_skill: str
    expected_state: Mapping[str, Any]
    preconditions: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    verification: Mapping[str, Any] = field(default_factory=dict)
    idempotency: IdempotencyClass = IdempotencyClass.IDEMPOTENT_WITH_KEY
    risk: RiskLevel = RiskLevel.LOW
    action_id: str = field(default_factory=lambda: new_id("action"))
    created_at: datetime = field(default_factory=utc_now)
    schema_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_identifier("action_id", self.action_id)
        _require_identifier("tool_name", self.tool_name)
        _require_identifier("source_skill", self.source_skill)
        if not self.expected_state:
            raise ValueError("expected_state is required for execution confirmation")
        if self.idempotency is IdempotencyClass.NON_IDEMPOTENT and not self.verification:
            raise ValueError("non-idempotent action requires an explicit verification rule")

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(self)


@dataclass(frozen=True)
class VerificationIssue:
    code: str
    message: str
    rule: str
    retryable: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_identifier("issue code", self.code)
        if not self.message.strip() or not self.rule.strip():
            raise ValueError("verification issue requires message and rule")


@dataclass(frozen=True)
class VerificationDecision:
    accepted: bool
    issues: Sequence[VerificationIssue] = field(default_factory=tuple)
    registry_version: Optional[str] = None
    topology_version: Optional[str] = None
    checked_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.accepted and self.issues:
            raise ValueError("accepted verification cannot contain issues")
        if not self.accepted and not self.issues:
            raise ValueError("rejected verification must contain at least one issue")

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(self)


@dataclass(frozen=True)
class ExecutionEvidence:
    ids: CorrelationIds
    action_id: str
    status: ActionStatus
    source: str
    observed_state: Mapping[str, Any] = field(default_factory=dict)
    state_version: Optional[str] = None
    observed_at: datetime = field(default_factory=utc_now)
    error: Optional[ErrorDetail] = None

    def __post_init__(self) -> None:
        if self.ids.command_id is None:
            raise ValueError("execution evidence requires command_id")
        _require_identifier("action_id", self.action_id)
        if self.status is ActionStatus.SUCCEEDED and not self.observed_state:
            raise ValueError("successful action requires observed state evidence")
        if self.status in (ActionStatus.FAILED, ActionStatus.REJECTED) and self.error is None:
            raise ValueError("failed or rejected action requires error detail")

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(self)


@dataclass(frozen=True)
class MessageEnvelope:
    message_type: str
    ids: CorrelationIds
    payload: Mapping[str, Any]
    producer: str
    message_id: str = field(default_factory=lambda: new_id("msg"))
    created_at: datetime = field(default_factory=utc_now)
    schema_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_identifier("message_id", self.message_id)
        _require_identifier("message_type", self.message_type)
        _require_identifier("producer", self.producer)

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(self)
