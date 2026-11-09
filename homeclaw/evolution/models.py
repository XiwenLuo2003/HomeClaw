"""Immutable evidence models for controlled evolution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from homeclaw.domain.models import new_id, utc_now


class EvolutionStatus(str, Enum):
    PROPOSED = "proposed"
    EVALUATED = "evaluated"
    REJECTED = "rejected"
    CANARY = "canary"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"


def content_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CandidateChange:
    target: str
    base_version: str
    candidate_version: str
    patch: Mapping[str, Any]
    reason: str
    candidate_id: str = field(default_factory=lambda: new_id("candidate"))

    @property
    def hash(self) -> str:
        return content_hash(
            {
                "target": self.target,
                "base_version": self.base_version,
                "candidate_version": self.candidate_version,
                "patch": self.patch,
            }
        )


@dataclass(frozen=True)
class EvaluationSnapshot:
    dataset_id: str
    dataset_hash: str
    model_id: str
    prompt_version: str
    seed: int
    token_budget: int
    metrics: Mapping[str, float]
    safety_checks: Mapping[str, bool]
    sample_count: int


@dataclass(frozen=True)
class EvidencePack:
    candidate: CandidateChange
    baseline: EvaluationSnapshot
    evaluation: EvaluationSnapshot
    gate_passed: bool
    gate_reasons: tuple[str, ...]
    status: EvolutionStatus
    ablations: Mapping[str, EvaluationSnapshot] = field(default_factory=dict)
    evidence_id: str = field(default_factory=lambda: new_id("evidence"))
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "candidate": {
                "candidate_id": self.candidate.candidate_id,
                "target": self.candidate.target,
                "base_version": self.candidate.base_version,
                "candidate_version": self.candidate.candidate_version,
                "patch": dict(self.candidate.patch),
                "reason": self.candidate.reason,
                "hash": self.candidate.hash,
            },
            "baseline": _snapshot_dict(self.baseline),
            "evaluation": _snapshot_dict(self.evaluation),
            "gate_passed": self.gate_passed,
            "gate_reasons": list(self.gate_reasons),
            "status": self.status.value,
            "ablations": {
                name: _snapshot_dict(snapshot) for name, snapshot in self.ablations.items()
            },
        }


def _snapshot_dict(snapshot: EvaluationSnapshot) -> dict[str, Any]:
    return {
        "dataset_id": snapshot.dataset_id,
        "dataset_hash": snapshot.dataset_hash,
        "model_id": snapshot.model_id,
        "prompt_version": snapshot.prompt_version,
        "seed": snapshot.seed,
        "token_budget": snapshot.token_budget,
        "metrics": dict(snapshot.metrics),
        "safety_checks": dict(snapshot.safety_checks),
        "sample_count": snapshot.sample_count,
    }
