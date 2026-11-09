from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from homeclaw.evolution import (
    CandidateChange,
    CanaryController,
    CanaryPolicy,
    CanaryStatus,
    EvaluationSnapshot,
    EvidencePack,
    EvidenceStore,
    EvolutionGate,
    EvolutionStatus,
    GatePolicy,
    FailureTrace,
    KeywordMissCandidateGenerator,
    OfflineEvolutionPipeline,
    ReplayResult,
)


def snapshot(success: float, safety=True, dataset_hash="same"):
    return EvaluationSnapshot(
        dataset_id="router-gold-v1",
        dataset_hash=dataset_hash,
        model_id="gpt-version-pinned",
        prompt_version="prompt-v1",
        seed=42,
        token_budget=4000,
        metrics={"task_success": success, "safety_recall": 1.0, "token_cost": 100.0},
        safety_checks={"no_raw_mqtt": safety, "no_false_done": safety},
        sample_count=100,
    )


class EvolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = EvolutionGate(
            GatePolicy(
                primary_metric="task_success",
                minimum_improvement=0.01,
                maximum_regression={"safety_recall": 0.0},
                required_safety_checks=("no_raw_mqtt", "no_false_done"),
                minimum_sample_count=50,
            )
        )

    def test_gate_accepts_comparable_improvement_with_all_safety_checks(self) -> None:
        result = self.gate.evaluate(snapshot(0.70), snapshot(0.73))
        self.assertTrue(result.passed)
        self.assertEqual(result.reasons, ())

    def test_gate_fails_closed_for_safety_or_non_comparable_data(self) -> None:
        unsafe = self.gate.evaluate(snapshot(0.70), snapshot(0.80, safety=False))
        changed_data = self.gate.evaluate(
            snapshot(0.70), snapshot(0.80, dataset_hash="different")
        )
        self.assertFalse(unsafe.passed)
        self.assertIn("safety check failed or missing: no_false_done", unsafe.reasons)
        self.assertFalse(changed_data.passed)
        self.assertIn("non-comparable dataset_hash", changed_data.reasons)

    def test_evidence_pack_is_atomic_and_contains_candidate_hash(self) -> None:
        local_tmp = Path(__file__).resolve().parents[1] / "tmp"
        local_tmp.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_tmp) as directory:
            candidate = CandidateChange(
                "skills/lighting",
                "v1",
                "v2",
                {"add_keyword": "illumination"},
                "router miss analysis",
            )
            result = self.gate.evaluate(snapshot(0.70), snapshot(0.73))
            pack = EvidencePack(
                candidate,
                snapshot(0.70),
                snapshot(0.73),
                result.passed,
                result.reasons,
                EvolutionStatus.EVALUATED,
            )

            path = EvidenceStore(directory).write(pack)
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(payload["candidate"]["hash"], candidate.hash)
            self.assertTrue(payload["gate_passed"])
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_canary_requires_human_approval_and_auto_pauses_on_safety_violation(self) -> None:
        controller = CanaryController(
            "candidate-1",
            baseline_failure_rate=0.01,
            policy=CanaryPolicy(
                traffic_fraction=0.1,
                minimum_samples=3,
                maximum_failure_rate=0.05,
                maximum_failure_rate_increase=0.02,
            ),
        )
        controller.record(success=True)
        controller.record(success=True)
        status = controller.record(success=True)
        self.assertEqual(status, CanaryStatus.READY_FOR_APPROVAL)
        controller.approve("project-owner")
        self.assertEqual(controller.status, CanaryStatus.PROMOTED)

        unsafe = CanaryController("candidate-2", 0.01)
        unsafe.record(success=True, safety_violation=True)
        self.assertEqual(unsafe.status, CanaryStatus.PAUSED)
        unsafe.rollback()
        self.assertEqual(unsafe.status, CanaryStatus.ROLLED_BACK)

    def test_offline_pipeline_replays_gates_records_ablation_and_prepares_canary(self) -> None:
        class Evaluator:
            def evaluate(self, candidate):
                return ReplayResult(
                    snapshot(0.73),
                    {"without_tool_contraction": snapshot(0.68)},
                )

        local_tmp = Path(__file__).resolve().parents[1] / "tmp"
        local_tmp.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_tmp) as directory:
            pipeline = OfflineEvolutionPipeline(
                generator=KeywordMissCandidateGenerator(),
                evaluator=Evaluator(),
                gate=self.gate,
                evidence_store=EvidenceStore(directory),
                active_versions={"skills/lighting": "v1"},
                canary_policy=CanaryPolicy(minimum_samples=2),
            )
            failures = [
                FailureTrace(
                    "trace-1",
                    "task-1",
                    "router",
                    "skill_miss",
                    "make the room luminous",
                    {
                        "target_skill": "lighting",
                        "base_version": "v1",
                        "missing_terms": ["luminous"],
                    },
                )
            ]

            runs = pipeline.run(failures, snapshot(0.70))

            self.assertEqual(len(runs), 1)
            self.assertTrue(runs[0].evidence.gate_passed)
            self.assertEqual(runs[0].evidence.status, EvolutionStatus.CANARY)
            self.assertIsNotNone(runs[0].canary)
            payload = json.loads(runs[0].evidence_path.read_text(encoding="utf-8"))
            self.assertIn("without_tool_contraction", payload["ablations"])
            self.assertEqual(payload["candidate"]["patch"]["add_keywords"], ["luminous"])

    def test_offline_pipeline_rejects_stale_base_without_replay(self) -> None:
        class MustNotRun:
            def evaluate(self, candidate):
                raise AssertionError("stale candidate must not be replayed")

        local_tmp = Path(__file__).resolve().parents[1] / "tmp"
        local_tmp.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_tmp) as directory:
            pipeline = OfflineEvolutionPipeline(
                generator=KeywordMissCandidateGenerator(),
                evaluator=MustNotRun(),
                gate=self.gate,
                evidence_store=EvidenceStore(directory),
                active_versions={"skills/lighting": "v2"},
            )
            failure = FailureTrace(
                "trace-2",
                "task-2",
                "router",
                "skill_miss",
                "luminous",
                {
                    "target_skill": "lighting",
                    "base_version": "v1",
                    "missing_terms": ["luminous"],
                },
            )

            run = pipeline.run([failure], snapshot(0.70))[0]

            self.assertFalse(run.evidence.gate_passed)
            self.assertEqual(run.evidence.status, EvolutionStatus.REJECTED)
            self.assertIn("stale base version", run.evidence.gate_reasons[0])
            self.assertIsNone(run.canary)


if __name__ == "__main__":
    unittest.main()
