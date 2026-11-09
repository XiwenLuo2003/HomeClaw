from __future__ import annotations

import unittest

from homeclaw.domain import ActionProposal, DeviceRef
from homeclaw.verification import ActionConflictDetector
from homeclaw.eval.conflict_metrics import ConflictExample, evaluate_conflict_detector


def proposal(
    device_id: str,
    tool: str,
    expected: dict,
    *,
    arguments: dict | None = None,
    verification: dict | None = None,
    preconditions: tuple[dict, ...] = (),
) -> ActionProposal:
    return ActionProposal(
        tool_name=tool,
        target=DeviceRef("home-1", device_id),
        arguments=arguments or {},
        source_skill="test",
        expected_state=expected,
        verification=verification or {"path": next(iter(expected)), "equals": next(iter(expected.values()))},
        preconditions=preconditions,
    )


class ConflictDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = ActionConflictDetector()

    def test_detects_redundant_and_device_conflicting_actions(self) -> None:
        first = proposal("light-1", "set_power", {"power": "on"}, arguments={"power": "on"})
        duplicate = proposal("light-1", "set_power", {"power": "on"}, arguments={"power": "on"})
        opposite = proposal("light-1", "set_power", {"power": "off"}, arguments={"power": "off"})

        issues = self.detector.detect([first, duplicate, opposite])
        codes = {issue.code for issue in issues}

        self.assertIn("redundant_action", codes)
        self.assertIn("device_conflict", codes)

    def test_detects_environment_and_exclusive_resource_conflicts(self) -> None:
        heater = proposal(
            "heater",
            "set_heat",
            {"power": "on"},
            verification={
                "environment_effects": {"room_temperature_direction": "up"},
                "exclusive_resources": ["power-circuit-a"],
            },
        )
        cooler = proposal(
            "ac",
            "set_cool",
            {"power": "on"},
            verification={
                "environment_effects": {"room_temperature_direction": "down"},
                "exclusive_resources": ["power-circuit-a"],
            },
        )

        codes = {issue.code for issue in self.detector.detect([heater, cooler])}

        self.assertIn("environment_conflict", codes)
        self.assertIn("resource_conflict", codes)

    def test_dependency_order_resolves_exclusive_resource_but_cycle_is_rejected(self) -> None:
        first = proposal(
            "dishwasher",
            "run",
            {"state": "running"},
            verification={"exclusive_resources": ["water-line"]},
        )
        second = proposal(
            "washer",
            "run",
            {"state": "running"},
            verification={"exclusive_resources": ["water-line"]},
        )
        ordered = self.detector.detect([first, second], {second.action_id: [first.action_id]})
        cyclic = self.detector.detect(
            [first, second],
            {first.action_id: [second.action_id], second.action_id: [first.action_id]},
        )

        self.assertNotIn("resource_conflict", {issue.code for issue in ordered})
        self.assertIn("dependency_cycle", {issue.code for issue in cyclic})

    def test_detects_action_blocked_by_another_final_state(self) -> None:
        close_window = proposal("window", "set_window", {"open": False})
        run_ac = proposal(
            "ac",
            "set_mode",
            {"mode": "cool"},
            preconditions=({"device_id": "window", "state": {"open": True}},),
        )

        issues = self.detector.detect([close_window, run_ac])
        self.assertIn("blocked_action", {issue.code for issue in issues})

    def test_metric_uses_homeclaw_labels_instead_of_external_paper_numbers(self) -> None:
        on = proposal("light-1", "set_power", {"power": "on"}, arguments={"power": "on"})
        off = proposal("light-1", "set_power", {"power": "off"}, arguments={"power": "off"})
        safe = proposal("light-2", "set_power", {"power": "on"}, arguments={"power": "on"})
        metrics = evaluate_conflict_detector(
            self.detector,
            [
                ConflictExample([on, off], frozenset({"device_conflict"})),
                ConflictExample([on, safe], frozenset()),
            ],
        )
        self.assertEqual(metrics.sample_count, 2)
        self.assertEqual(metrics.precision, 1.0)
        self.assertEqual(metrics.recall, 1.0)
        self.assertEqual(metrics.f1, 1.0)


if __name__ == "__main__":
    unittest.main()
