from __future__ import annotations

import unittest
from pathlib import Path

from homeclaw.eval.routing_metrics import RoutingExample, evaluate_router
from homeclaw.routing import (
    RouteRequest,
    SkillDefinition,
    SkillRegistry,
    SkillRouter,
    ToolDefinition,
)


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "homeclaw" / "skills" / "registry.json"


class SkillRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = SkillRegistry.from_json(REGISTRY_PATH)
        self.router = SkillRouter(self.registry)

    def test_routes_lighting_and_contracts_tool_schema(self) -> None:
        decision = self.router.route(RouteRequest("Turn off the living room lamp", top_k=1))

        self.assertEqual(decision.selected_skill_ids, ("lighting",))
        self.assertIn("turn_light_off", decision.exposed_tools)
        self.assertNotIn("set_temperature", decision.exposed_tools)
        self.assertGreater(decision.tool_contraction_ratio, 0.5)

    def test_multi_intent_routes_two_skills(self) -> None:
        decision = self.router.route(
            RouteRequest("Dim the lamp and set the air conditioner temperature", top_k=2)
        )

        self.assertEqual(set(decision.selected_skill_ids), {"lighting", "climate"})
        self.assertIn("set_light_brightness", decision.exposed_tools)
        self.assertIn("set_temperature", decision.exposed_tools)

    def test_visual_reference_routes_disambiguation_skill(self) -> None:
        decision = self.router.route(RouteRequest("Turn on that lamp in the image", top_k=2))
        self.assertIn("device-disambiguation", decision.selected_skill_ids)
        self.assertIn("ground_visual_device", decision.exposed_tools)

    def test_unknown_request_uses_clarification_fallback(self) -> None:
        decision = self.router.route(RouteRequest("xyzzy frobnicate", top_k=2))
        self.assertTrue(decision.fallback)
        self.assertEqual(decision.selected_skill_ids, ("clarification",))
        self.assertEqual(decision.exposed_tools, ("request_clarification",))

    def test_shared_tool_is_defined_once_and_referenced_by_many_skills(self) -> None:
        definitions = [tool for tool in self.registry.tools if tool.name == "get_device_state"]
        references = [skill for skill in self.registry.skills if "get_device_state" in skill.tool_names]
        self.assertEqual(len(definitions), 1)
        self.assertGreater(len(references), 1)

    def test_duplicate_tool_and_unknown_reference_are_rejected(self) -> None:
        registry = SkillRegistry()
        tool = ToolDefinition("read_state", "Read state", {"type": "object"})
        registry.register_tool(tool)
        with self.assertRaises(ValueError):
            registry.register_tool(tool)
        with self.assertRaises(ValueError):
            registry.register_skill(
                SkillDefinition(
                    "broken",
                    "test",
                    "Broken skill",
                    (),
                    ("missing_tool",),
                )
            )

    def test_routing_metrics_report_recall_mrr_and_contraction(self) -> None:
        examples = [
            RoutingExample("turn on the bedroom light", frozenset({"lighting"})),
            RoutingExample("set air conditioner temperature", frozenset({"climate"})),
            RoutingExample(
                "dim the lamp and cool the room",
                frozenset({"lighting", "climate"}),
            ),
        ]

        metrics = evaluate_router(self.router, examples, top_k=2)

        self.assertEqual(metrics.sample_count, 3)
        self.assertEqual(metrics.recall_at_k, 1.0)
        self.assertEqual(metrics.full_coverage_rate, 1.0)
        self.assertGreater(metrics.average_tool_contraction, 0.3)


if __name__ == "__main__":
    unittest.main()
