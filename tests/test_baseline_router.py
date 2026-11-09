from __future__ import annotations

import unittest
from pathlib import Path

from homeclaw.eval import TfidfVectorRouter
from homeclaw.routing import RouteRequest, SkillRegistry


ROOT = Path(__file__).resolve().parents[1]


class TfidfBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        registry_path = ROOT / "homeclaw" / "skills" / "registry.json"
        self.registry = SkillRegistry.from_json(registry_path)
        self.router = TfidfVectorRouter(self.registry)

    def test_vector_baseline_routes_known_text_without_homeclaw_gates(self) -> None:
        decision = self.router.route(RouteRequest("turn on the bedroom light", top_k=1))
        self.assertEqual(decision.selected_skill_ids, ("lighting",))
        self.assertFalse(decision.fallback)

    def test_vector_baseline_has_explicit_unknown_fallback(self) -> None:
        decision = self.router.route(RouteRequest("xyzzy plugh", top_k=2))
        self.assertEqual(decision.selected_skill_ids, ("clarification",))
        self.assertTrue(decision.fallback)


if __name__ == "__main__":
    unittest.main()
