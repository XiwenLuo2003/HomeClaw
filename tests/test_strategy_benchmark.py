from __future__ import annotations

import unittest

from homeclaw.eval.strategy_benchmark import (
    BenchmarkConfig,
    PlanningCase,
    StrategyName,
    StrategyObservation,
    benchmark_result_to_dict,
    run_strategy_benchmark,
)


class FixedRunner:
    def __init__(self, observation):
        self.observation = observation

    def run(self, case):
        return self.observation


class StrategyBenchmarkTests(unittest.TestCase):
    def test_requires_all_four_comparable_strategies(self) -> None:
        case = PlanningCase("1", "turn on light", frozenset({"turn_light_on"}), {})
        config = BenchmarkConfig(
            "gpt-pinned", "v1", 0.0, 42, 4000, 8, "dataset-v1", 1.0, 2.0
        )
        with self.assertRaises(ValueError):
            run_strategy_benchmark([case], {}, config)

    def test_aggregates_steps_tokens_schema_and_p95(self) -> None:
        cases = [
            PlanningCase("1", "turn on light", frozenset({"turn_light_on"}), {}),
            PlanningCase("2", "turn off light", frozenset({"turn_light_off"}), {}),
        ]
        observation = StrategyObservation(True, 2, 100, 20, 3, 600, 5.0)
        runners = {strategy: FixedRunner(observation) for strategy in StrategyName}
        config = BenchmarkConfig(
            "gpt-pinned", "v1", 0.0, 42, 4000, 8, "dataset-v1", 1.0, 2.0
        )

        result = run_strategy_benchmark(cases, runners, config)

        for aggregate in result.aggregates.values():
            self.assertEqual(aggregate.success_rate, 1.0)
            self.assertEqual(aggregate.average_steps, 2.0)
            self.assertEqual(aggregate.average_total_tokens, 120.0)
            self.assertEqual(aggregate.average_prompt_tokens, 100.0)
            self.assertEqual(aggregate.average_completion_tokens, 20.0)
            self.assertAlmostEqual(aggregate.average_model_cost, 0.00014)
            self.assertEqual(aggregate.average_schema_bytes, 600.0)
            self.assertEqual(aggregate.latency_p95_ms, 5.0)
            self.assertEqual(aggregate.failure_distribution, {})
        self.assertEqual(len(config.hash), 64)
        report = benchmark_result_to_dict(result)
        self.assertEqual(report["config"]["hash"], config.hash)
        self.assertIn("full_tool_react", report["aggregates"])


if __name__ == "__main__":
    unittest.main()
