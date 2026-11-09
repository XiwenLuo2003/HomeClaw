"""Comparable four-strategy benchmark harness for online-model experiments."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from enum import Enum
from statistics import mean
from typing import Mapping, Protocol, Sequence

from homeclaw.eval.performance import percentile


class StrategyName(str, Enum):
    FULL_REACT = "full_tool_react"
    FULL_PLAN_AND_SOLVE = "full_tool_plan_and_solve"
    PROGRESSIVE_ROUTER = "router_progressive_disclosure"
    HOMECLAW_DOUBLE_CONTRACTION = "homeclaw_double_contraction"


@dataclass(frozen=True)
class PlanningCase:
    case_id: str
    instruction: str
    expected_tools: frozenset[str]
    metadata: Mapping[str, object]


@dataclass(frozen=True)
class StrategyObservation:
    success: bool
    planning_steps: int
    prompt_tokens: int
    completion_tokens: int
    exposed_tool_count: int
    exposed_schema_bytes: int
    latency_ms: float
    error: str = ""


class StrategyRunner(Protocol):
    def run(self, case: PlanningCase) -> StrategyObservation:
        ...


@dataclass(frozen=True)
class BenchmarkConfig:
    model_id: str
    prompt_version: str
    temperature: float
    seed: int
    max_tokens: int
    max_steps: int
    dataset_id: str
    input_cost_per_million: float = 0.0
    output_cost_per_million: float = 0.0

    def __post_init__(self) -> None:
        if self.input_cost_per_million < 0 or self.output_cost_per_million < 0:
            raise ValueError("model token prices must be non-negative")

    @property
    def hash(self) -> str:
        payload = json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StrategyAggregate:
    strategy: StrategyName
    samples: int
    success_rate: float
    average_steps: float
    average_total_tokens: float
    average_prompt_tokens: float
    average_completion_tokens: float
    average_model_cost: float
    average_exposed_tools: float
    average_schema_bytes: float
    latency_p50_ms: float
    latency_p95_ms: float
    failure_count: int
    failure_distribution: Mapping[str, int]


@dataclass(frozen=True)
class BenchmarkResult:
    config: BenchmarkConfig
    aggregates: Mapping[StrategyName, StrategyAggregate]
    observations: Mapping[StrategyName, tuple[StrategyObservation, ...]]


def run_strategy_benchmark(
    cases: Sequence[PlanningCase],
    runners: Mapping[StrategyName, StrategyRunner],
    config: BenchmarkConfig,
) -> BenchmarkResult:
    missing = set(StrategyName) - set(runners)
    if missing:
        raise ValueError(f"missing benchmark runners: {sorted(item.value for item in missing)}")
    observations: dict[StrategyName, tuple[StrategyObservation, ...]] = {}
    aggregates: dict[StrategyName, StrategyAggregate] = {}
    for strategy in StrategyName:
        items = tuple(runners[strategy].run(case) for case in cases)
        observations[strategy] = items
        latencies = [item.latency_ms for item in items]
        count = len(items)
        aggregates[strategy] = StrategyAggregate(
            strategy=strategy,
            samples=count,
            success_rate=(sum(item.success for item in items) / count) if count else 0.0,
            average_steps=mean(item.planning_steps for item in items) if items else 0.0,
            average_total_tokens=(
                mean(item.prompt_tokens + item.completion_tokens for item in items) if items else 0.0
            ),
            average_prompt_tokens=mean(item.prompt_tokens for item in items) if items else 0.0,
            average_completion_tokens=(
                mean(item.completion_tokens for item in items) if items else 0.0
            ),
            average_model_cost=(
                mean(
                    item.prompt_tokens / 1_000_000 * config.input_cost_per_million
                    + item.completion_tokens / 1_000_000 * config.output_cost_per_million
                    for item in items
                )
                if items
                else 0.0
            ),
            average_exposed_tools=mean(item.exposed_tool_count for item in items) if items else 0.0,
            average_schema_bytes=mean(item.exposed_schema_bytes for item in items) if items else 0.0,
            latency_p50_ms=percentile(latencies, 0.50),
            latency_p95_ms=percentile(latencies, 0.95),
            failure_count=sum(not item.success for item in items),
            failure_distribution=dict(
                Counter(item.error or "unspecified" for item in items if not item.success)
            ),
        )
    return BenchmarkResult(config, aggregates, observations)


def benchmark_result_to_dict(result: BenchmarkResult) -> dict[str, object]:
    """Return a JSON-safe report that keeps raw observations auditable."""

    return {
        "config": {**asdict(result.config), "hash": result.config.hash},
        "aggregates": {
            strategy.value: {
                **asdict(aggregate),
                "strategy": aggregate.strategy.value,
            }
            for strategy, aggregate in result.aggregates.items()
        },
        "observations": {
            strategy.value: [asdict(item) for item in items]
            for strategy, items in result.observations.items()
        },
    }
