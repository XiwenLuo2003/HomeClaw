from __future__ import annotations

import unittest
from pathlib import Path

from homeclaw.domain import DeviceRef
from homeclaw.routing import (
    RouteRequest,
    SkillRegistry,
    SkillRouter,
    ToolSpaceContractor,
)
from homeclaw.verification import DeviceRecord, InMemoryCapabilityRegistry, ToolSpec


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "homeclaw" / "skills" / "registry.json"


class ToolContractionTests(unittest.TestCase):
    def test_device_capabilities_shrink_selected_skill_tool_space(self) -> None:
        registry = SkillRegistry.from_json(REGISTRY_PATH)
        route = SkillRouter(registry).route(RouteRequest("control the living room light", top_k=1))
        device = DeviceRef("home-1", "simple-light", "living-room", "power")
        capabilities = InMemoryCapabilityRegistry(
            [
                DeviceRecord(
                    device,
                    {
                        "turn_light_on": ToolSpec("turn_light_on", "power"),
                        "turn_light_off": ToolSpec("turn_light_off", "power"),
                    },
                )
            ]
        )

        result = ToolSpaceContractor(capabilities).contract(route, [device])

        self.assertIn("turn_light_on", result.decision.exposed_tools)
        self.assertIn("turn_light_off", result.decision.exposed_tools)
        self.assertNotIn("set_light_brightness", result.decision.exposed_tools)
        self.assertGreater(result.reduction, 0.0)
        self.assertEqual(result.candidate_device_count, 1)

    def test_no_candidates_preserves_routed_tools_for_clarification_flow(self) -> None:
        registry = SkillRegistry.from_json(REGISTRY_PATH)
        route = SkillRouter(registry).route(RouteRequest("turn on the light", top_k=1))
        result = ToolSpaceContractor(InMemoryCapabilityRegistry()).contract(route, [])
        self.assertEqual(result.decision.exposed_tools, route.exposed_tools)
        self.assertEqual(result.reduction, 0.0)


if __name__ == "__main__":
    unittest.main()
