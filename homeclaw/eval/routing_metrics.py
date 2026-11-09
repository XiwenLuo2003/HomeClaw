"""Reproducible Router recall and tool-contraction metrics."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Sequence

from homeclaw.routing import RouteRequest, SkillRouter


@dataclass(frozen=True)
class RoutingExample:
    text: str
    expected_skills: frozenset[str]


@dataclass(frozen=True)
class RoutingMetricResult:
    sample_count: int
    recall_at_k: float
    mean_reciprocal_rank: float
    full_coverage_rate: float
    fallback_rate: float
    average_tool_contraction: float
    average_candidate_count: float


def evaluate_router(
    router: SkillRouter,
    examples: Sequence[RoutingExample],
    *,
    top_k: int,
) -> RoutingMetricResult:
    if not examples:
        return RoutingMetricResult(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    coverages: list[float] = []
    fallbacks: list[float] = []
    contractions: list[float] = []
    candidates: list[float] = []

    for example in examples:
        decision = router.route(RouteRequest(example.text, top_k=top_k))
        ranked = list(decision.selected_skill_ids)
        hits = example.expected_skills.intersection(ranked)
        recalls.append(len(hits) / len(example.expected_skills) if example.expected_skills else 1.0)
        rank = next(
            (index for index, skill_id in enumerate(ranked, 1) if skill_id in example.expected_skills),
            None,
        )
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        coverages.append(float(example.expected_skills.issubset(set(ranked))))
        fallbacks.append(float(decision.fallback))
        contractions.append(decision.tool_contraction_ratio)
        candidates.append(float(decision.candidate_count))

    return RoutingMetricResult(
        sample_count=len(examples),
        recall_at_k=mean(recalls),
        mean_reciprocal_rank=mean(reciprocal_ranks),
        full_coverage_rate=mean(coverages),
        fallback_rate=mean(fallbacks),
        average_tool_contraction=mean(contractions),
        average_candidate_count=mean(candidates),
    )
