"""Stable domain contracts shared by the production-ready runtime.

The package intentionally depends only on the Python standard library.  Cloud,
database, MCP, MQTT, and model adapters translate their native payloads at the
boundary instead of leaking vendor-specific objects into the workflow.
"""

from homeclaw.domain.errors import DomainError, ErrorCode, ErrorDetail
from homeclaw.domain.models import (
    CONTRACT_VERSION,
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
    RiskLevel,
    TaskStatus,
    VerificationDecision,
    VerificationIssue,
)

__all__ = [
    "ActionProposal",
    "ActionStatus",
    "BBox",
    "CorrelationIds",
    "CONTRACT_VERSION",
    "DeviceRef",
    "DomainError",
    "ErrorCode",
    "ErrorDetail",
    "ExecutionEvidence",
    "GroundingCandidate",
    "GroundingResult",
    "IdempotencyClass",
    "MessageEnvelope",
    "RiskLevel",
    "TaskStatus",
    "VerificationDecision",
    "VerificationIssue",
]
