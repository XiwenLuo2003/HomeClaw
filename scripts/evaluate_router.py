"""Offline deterministic Router evaluation and scale benchmark."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeclaw.eval.performance import percentile  # noqa: E402
from homeclaw.eval.routing_metrics import RoutingExample, evaluate_router  # noqa: E402
from homeclaw.eval.baseline_router import TfidfVectorRouter  # noqa: E402
from homeclaw.routing import (  # noqa: E402
    RouteRequest,
    SkillDefinition,
    SkillRegistry,
    SkillRouter,
    ToolDefinition,
    ToolSpaceContractor,
)
from homeclaw.domain import DeviceRef  # noqa: E402
from homeclaw.verification import (  # noqa: E402
    DeviceRecord,
    InMemoryCapabilityRegistry,
    ToolSpec,
)


def load_examples(path: Path) -> list[RoutingExample]:
    examples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            examples.append(RoutingExample(item["text"], frozenset(item["expected_skills"])))
    return examples


def schema_bytes(registry: SkillRegistry, tool_names: tuple[str, ...]) -> int:
    payload = [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for name in tool_names
        for tool in [registry.get_tool(name)]
        if tool is not None
    ]
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def evaluate(registry: SkillRegistry, examples: list[RoutingExample], top_k: int, router=None) -> dict:
    router = router or SkillRouter(registry)
    metrics = evaluate_router(router, examples, top_k=top_k)
    latencies = []
    selected_schema = []
    decisions = []
    for example in examples:
        started = time.perf_counter()
        decision = router.route(RouteRequest(example.text, top_k=top_k))
        latencies.append((time.perf_counter() - started) * 1000.0)
        selected_schema.append(schema_bytes(registry, decision.exposed_tools))
        decisions.append(
            {
                "text": example.text,
                "expected": sorted(example.expected_skills),
                "selected": list(decision.selected_skill_ids),
                "fallback": decision.fallback,
            }
        )
    full_bytes = schema_bytes(registry, tuple(tool.name for tool in registry.tools))
    return {
        "top_k": top_k,
        "sample_count": metrics.sample_count,
        "recall_at_k": metrics.recall_at_k,
        "mrr": metrics.mean_reciprocal_rank,
        "full_coverage_rate": metrics.full_coverage_rate,
        "fallback_rate": metrics.fallback_rate,
        "average_tool_contraction": metrics.average_tool_contraction,
        "full_schema_bytes": full_bytes,
        "average_selected_schema_bytes": statistics.mean(selected_schema),
        "schema_byte_reduction": 1.0 - statistics.mean(selected_schema) / full_bytes,
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "average": statistics.mean(latencies),
        },
        "decisions": decisions,
    }


def scale_benchmark(base: SkillRegistry, sizes: tuple[int, ...] = (100, 1000, 5000)) -> list[dict]:
    rows = []
    for size in sizes:
        registry = SkillRegistry()
        for tool in base.tools:
            registry.register_tool(tool)
        tracemalloc.start()
        for index in range(size):
            tool_name = f"synthetic_tool_{index}"
            registry.register_tool(
                ToolDefinition(
                    tool_name,
                    f"Synthetic domain action {index}",
                    {"type": "object", "properties": {}},
                )
            )
            registry.register_skill(
                SkillDefinition(
                    skill_id=f"synthetic-{index}",
                    domain=f"domain-{index % 20}",
                    description=f"Synthetic capability number {index}",
                    keywords=(f"unique_keyword_{index}",),
                    tool_names=(tool_name,),
                    competence=0.5,
                )
            )
        started = time.perf_counter()
        router = SkillRouter(registry, fallback_skill_id="")
        build_ms = (time.perf_counter() - started) * 1000.0
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        latencies = []
        for index in range(min(size, 100)):
            started = time.perf_counter()
            router.route(RouteRequest(f"unique_keyword_{index}", top_k=1))
            latencies.append((time.perf_counter() - started) * 1000.0)
        rows.append(
            {
                "skill_count": size,
                "tool_count": len(registry.tools),
                "index_build_ms": build_ms,
                "route_p50_ms": percentile(latencies, 0.50),
                "route_p95_ms": percentile(latencies, 0.95),
                "route_throughput_qps": 1000.0 / statistics.mean(latencies),
                "index_peak_bytes": peak_bytes,
            }
        )
    return rows


def device_scale_benchmark(base: SkillRegistry, sizes: tuple[int, ...] = (100, 1000, 5000)) -> list[dict]:
    route = SkillRouter(base).route(RouteRequest("turn on the light", top_k=1))
    supported_tool = "turn_light_on"
    rows = []
    for size in sizes:
        devices = []
        candidates = []
        for index in range(size):
            reference = DeviceRef("scale-home", f"device-{index}", "scale-room", "power")
            candidates.append(reference)
            devices.append(
                DeviceRecord(
                    reference,
                    {supported_tool: ToolSpec(supported_tool, "power")},
                )
            )
        contractor = ToolSpaceContractor(InMemoryCapabilityRegistry(devices))
        latencies = []
        for _ in range(20):
            started = time.perf_counter()
            result = contractor.contract(route, candidates)
            latencies.append((time.perf_counter() - started) * 1000.0)
        rows.append(
            {
                "candidate_device_count": size,
                "resolved_device_count": result.candidate_device_count,
                "contracted_tool_count": result.after_count,
                "contraction_p50_ms": percentile(latencies, 0.50),
                "contraction_p95_ms": percentile(latencies, 0.95),
                "contraction_throughput_qps": 1000.0 / statistics.mean(latencies),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "data" / "eval" / "router_gold.jsonl"
    )
    parser.add_argument(
        "--registry", type=Path, default=ROOT / "homeclaw" / "skills" / "registry.json"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    registry = SkillRegistry.from_json(args.registry)
    examples = load_examples(args.dataset)
    report = {
        "provenance": {
            "kind": "offline_deterministic_router_evaluation",
            "dataset": str(args.dataset.relative_to(ROOT)),
            "registry": str(args.registry.relative_to(ROOT)),
            "python": sys.version,
            "platform": platform.platform(),
            "warning": "These metrics validate routing code only and are not online-LLM task-success results."
        },
        "top_k_1": evaluate(registry, examples, 1),
        "top_k_2": evaluate(registry, examples, 2),
        "baseline_tfidf_top_k_1": evaluate(
            registry, examples, 1, TfidfVectorRouter(registry)
        ),
        "baseline_tfidf_top_k_2": evaluate(
            registry, examples, 2, TfidfVectorRouter(registry)
        ),
        "scale": scale_benchmark(registry),
        "device_scale": device_scale_benchmark(registry),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output = output.resolve()
        if ROOT not in output.parents:
            raise SystemExit("output must remain inside the HomeClaw repository")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(output)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
