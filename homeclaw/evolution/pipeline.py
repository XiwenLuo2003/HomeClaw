"""Offline candidate generation, replay, evidence, and canary preparation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from homeclaw.evolution.canary import CanaryController, CanaryPolicy
from homeclaw.evolution.gates import EvolutionGate
from homeclaw.evolution.models import (
    CandidateChange,
    EvaluationSnapshot,
    EvidencePack,
    EvolutionStatus,
)
from homeclaw.evolution.store import EvidenceStore


@dataclass(frozen=True)
class FailureTrace:
    trace_id: str
    task_id: str
    component: str
    error_code: str
    input_text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


class CandidateGenerator(Protocol):
    def generate(self, failures: Sequence[FailureTrace]) -> Sequence[CandidateChange]:
        ...


@dataclass(frozen=True)
class ReplayResult:
    evaluation: EvaluationSnapshot
    ablations: Mapping[str, EvaluationSnapshot] = field(default_factory=dict)


class ReplayEvaluator(Protocol):
    def evaluate(self, candidate: CandidateChange) -> ReplayResult:
        ...


@dataclass(frozen=True)
class EvolutionRun:
    evidence: EvidencePack
    evidence_path: Path
    canary: CanaryController | None


class KeywordMissCandidateGenerator:
    """Produces reviewable Router keyword patches from structured miss traces."""

    def generate(self, failures: Sequence[FailureTrace]) -> Sequence[CandidateChange]:
        candidates = []
        seen = set()
        for failure in failures:
            if failure.component != "router" or failure.error_code != "skill_miss":
                continue
            target = str(failure.metadata.get("target_skill", "")).strip()
            base_version = str(failure.metadata.get("base_version", "")).strip()
            terms = tuple(
                sorted({str(term).strip().lower() for term in failure.metadata.get("missing_terms", ()) if str(term).strip()})
            )
            if not target or not base_version or not terms:
                continue
            key = (target, base_version, terms)
            if key in seen:
                continue
            seen.add(key)
            digest = hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:12]
            candidates.append(
                CandidateChange(
                    target=f"skills/{target}",
                    base_version=base_version,
                    candidate_version=f"{base_version}+candidate.{digest}",
                    patch={"add_keywords": list(terms)},
                    reason=f"router miss evidence from trace {failure.trace_id}",
                )
            )
        return tuple(candidates)


class OfflineEvolutionPipeline:
    """Never mutates a live registry; it only writes immutable evidence packs."""

    def __init__(
        self,
        *,
        generator: CandidateGenerator,
        evaluator: ReplayEvaluator,
        gate: EvolutionGate,
        evidence_store: EvidenceStore,
        active_versions: Mapping[str, str],
        canary_policy: CanaryPolicy | None = None,
    ) -> None:
        self.generator = generator
        self.evaluator = evaluator
        self.gate = gate
        self.evidence_store = evidence_store
        self.active_versions = dict(active_versions)
        self.canary_policy = canary_policy or CanaryPolicy()

    def run(
        self,
        failures: Sequence[FailureTrace],
        baseline: EvaluationSnapshot,
    ) -> tuple[EvolutionRun, ...]:
        runs = []
        for candidate in self.generator.generate(failures):
            active = self.active_versions.get(candidate.target)
            if active != candidate.base_version:
                pack = EvidencePack(
                    candidate,
                    baseline,
                    baseline,
                    False,
                    (f"stale base version: active={active}, candidate={candidate.base_version}",),
                    EvolutionStatus.REJECTED,
                )
                runs.append(EvolutionRun(pack, self.evidence_store.write(pack), None))
                continue
            replay = self.evaluator.evaluate(candidate)
            gate_result = self.gate.evaluate(baseline, replay.evaluation)
            status = EvolutionStatus.CANARY if gate_result.passed else EvolutionStatus.REJECTED
            pack = EvidencePack(
                candidate,
                baseline,
                replay.evaluation,
                gate_result.passed,
                gate_result.reasons,
                status,
                replay.ablations,
            )
            path = self.evidence_store.write(pack)
            canary = None
            if gate_result.passed:
                primary = self.gate.policy.primary_metric
                baseline_failure_rate = max(0.0, 1.0 - baseline.metrics.get(primary, 0.0))
                canary = CanaryController(
                    candidate.candidate_id,
                    baseline_failure_rate,
                    self.canary_policy,
                )
            runs.append(EvolutionRun(pack, path, canary))
        return tuple(runs)
