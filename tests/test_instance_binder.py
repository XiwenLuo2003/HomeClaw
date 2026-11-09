from __future__ import annotations

import unittest

from homeclaw.agent import InstanceBinder
from homeclaw.domain import ActionProposal, DeviceRef
from homeclaw.topology import InMemoryTopologyStore, TopologyCandidateFilter, TopologyNode
from homeclaw.verification import DeviceRecord, InMemoryCapabilityRegistry, ToolSpec


class InstanceBinderTests(unittest.TestCase):
    def proposal(self, target_name="lamp beside sofa"):
        return ActionProposal(
            "turn_light_on",
            DeviceRef("home-1", target_name, "living-room", "power"),
            {},
            "lighting",
            {"power": "on"},
            verification={"path": "power", "equals": "on"},
        )

    def test_alias_is_bound_to_unique_registered_instance(self) -> None:
        topology = InMemoryTopologyStore()
        topology.apply(
            nodes=(
                TopologyNode(
                    "light-1",
                    "device",
                    "Floor lamp",
                    {
                        "room_id": "living-room",
                        "capabilities": ["power"],
                        "aliases": ["lamp beside sofa"],
                    },
                ),
            ),
            expected_version=0,
        )
        registry = InMemoryCapabilityRegistry(
            [
                DeviceRecord(
                    DeviceRef("home-1", "light-1", "living-room", "power"),
                    {"turn_light_on": ToolSpec("turn_light_on", "power")},
                )
            ]
        )

        result = InstanceBinder(TopologyCandidateFilter(topology), registry).bind(self.proposal())

        self.assertTrue(result.bound)
        self.assertEqual(result.proposal.target.device_id, "light-1")

    def test_unregistered_alias_does_not_reach_verifier_as_a_guess(self) -> None:
        topology = InMemoryTopologyStore()
        topology.apply(
            nodes=(
                TopologyNode(
                    "light-1",
                    "device",
                    "Floor lamp",
                    {"room_id": "living-room", "capabilities": ["power"]},
                ),
            ),
            expected_version=0,
        )
        result = InstanceBinder(
            TopologyCandidateFilter(topology), InMemoryCapabilityRegistry()
        ).bind(self.proposal("unknown lamp"))
        self.assertFalse(result.bound)
        self.assertEqual(result.issue_code, "binding_not_found")


if __name__ == "__main__":
    unittest.main()
