"""Machine-readable error taxonomy for workflow and adapter boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    INVALID_SCHEMA = "invalid_schema"
    INVALID_ACTION = "invalid_action"
    DEVICE_NOT_FOUND = "device_not_found"
    CAPABILITY_NOT_FOUND = "capability_not_found"
    AMBIGUOUS_DEVICE = "ambiguous_device"
    STALE_STATE = "stale_state"
    CONFLICT = "conflict"
    POLICY_DENIED = "policy_denied"
    TIMEOUT = "timeout"
    BUDGET_EXHAUSTED = "budget_exhausted"
    RATE_LIMITED = "rate_limited"
    CIRCUIT_OPEN = "circuit_open"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    EXECUTION_REJECTED = "execution_rejected"
    EXECUTION_UNCONFIRMED = "execution_unconfirmed"
    INTERNAL = "internal"


@dataclass(frozen=True)
class ErrorDetail:
    """Serializable failure information safe to pass between services."""

    code: ErrorCode
    message: str
    retryable: bool = False
    component: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("error message must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "component": self.component,
            "metadata": dict(self.metadata),
        }


class DomainError(RuntimeError):
    """Exception wrapper used inside a process.

    External boundaries should serialize :attr:`detail` instead of serializing
    the Python exception itself.
    """

    def __init__(self, detail: ErrorDetail):
        self.detail = detail
        super().__init__(f"{detail.code.value}: {detail.message}")
