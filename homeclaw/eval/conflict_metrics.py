"""Precision/recall/F1 for conflict-rule evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from homeclaw.domain import ActionProposal
from homeclaw.verification import ActionConflictDetector


@dataclass(frozen=True)
class ConflictExample:
    actions: Sequence[ActionProposal]
    expected_codes: frozenset[str]
    dependencies: Mapping[str, Sequence[str]] | None = None


@dataclass(frozen=True)
class ConflictMetricResult:
    sample_count: int
    precision: float
    recall: float
    f1: float
    exact_match: float


def evaluate_conflict_detector(
    detector: ActionConflictDetector,
    examples: Sequence[ConflictExample],
) -> ConflictMetricResult:
    true_positive = false_positive = false_negative = exact = 0
    for example in examples:
        predicted = {
            issue.code for issue in detector.detect(example.actions, example.dependencies)
        }
        true_positive += len(predicted & example.expected_codes)
        false_positive += len(predicted - example.expected_codes)
        false_negative += len(example.expected_codes - predicted)
        exact += int(predicted == example.expected_codes)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return ConflictMetricResult(
        len(examples),
        precision,
        recall,
        f1,
        exact / len(examples) if examples else 0.0,
    )
