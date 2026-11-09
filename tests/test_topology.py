from __future__ import annotations

import unittest

from homeclaw.topology import (
    InMemoryTopologyStore,
    TopologyCandidateFilter,
    TopologyConflict,
    TopologyEdge,
    TopologyNode,
)


class TopologyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryTopologyStore()
        self.store.apply(
            nodes=(
                TopologyNode("living-room", "room", "Living room"),
                TopologyNode(
                    "floor-lamp",
                    "device",
                    "Floor lamp",
                    {
                        "room_id": "living-room",
                        "capabilities": ["power", "brightness"],
                        "aliases": ["lamp beside sofa"],
                    },
                ),
                TopologyNode(
                    "ceiling-light",
                    "device",
                    "Ceiling light",
                    {
                        "room_id": "living-room",
                        "capabilities": ["power", "brightness"],
                        "aliases": ["main light"],
                    },
                ),
            ),
            edges=(
                TopologyEdge("living-room", "contains", "floor-lamp"),
                TopologyEdge("living-room", "contains", "ceiling-light"),
            ),
            expected_version=0,
        )

    def test_optimistic_version_prevents_lost_update(self) -> None:
        with self.assertRaises(TopologyConflict):
            self.store.apply(
                nodes=(TopologyNode("bedroom", "room", "Bedroom"),),
                expected_version=0,
            )
        self.assertEqual(self.store.version, 1)

    def test_edges_require_existing_endpoints(self) -> None:
        with self.assertRaises(ValueError):
            self.store.apply(
                edges=(TopologyEdge("living-room", "contains", "missing"),),
                expected_version=1,
            )

    def test_knowledge_anchor_reduces_visual_candidates(self) -> None:
        candidate_filter = TopologyCandidateFilter(self.store)

        all_lights = candidate_filter.candidates(
            room_id="living-room", capability="brightness"
        )
        anchored = candidate_filter.candidates(
            room_id="living-room",
            capability="brightness",
            text_hint="the lamp beside sofa",
        )

        self.assertEqual(len(all_lights), 2)
        self.assertEqual([candidate.device_id for candidate in anchored], ["floor-lamp"])


if __name__ == "__main__":
    unittest.main()
