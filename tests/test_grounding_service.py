from __future__ import annotations

import json
import unittest

from homeclaw.domain import BBox, GroundingCandidate, GroundingResult
from homeclaw.grounding import (
    DeviceDisambiguationService,
    GrounderCandidate,
    GrounderRequest,
    HttpGrounderClient,
)
from homeclaw.topology import InMemoryTopologyStore, TopologyCandidateFilter, TopologyNode


class FakeGrounderClient:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def ground(self, request, timeout_seconds=10.0):
        self.calls += 1
        if self.fail:
            raise TimeoutError("model timed out")
        selected = request.candidates[0]
        return GroundingResult(
            query=request.query,
            candidates=(
                GroundingCandidate(
                    selected.device,
                    0.92,
                    BBox(0.1, 0.2, 0.4, 0.8),
                    "matches the lamp beside the sofa",
                ),
            ),
            selected_device_id=selected.device.device_id,
            ambiguous=False,
            model_version="test-grounder",
        )

    def healthy(self, timeout_seconds=2.0):
        return not self.fail


class FakeHttpResponse:
    def __init__(self, payload, status=200):
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class GroundingServiceTests(unittest.TestCase):
    def topology(self, device_count=2):
        store = InMemoryTopologyStore()
        nodes = [
            TopologyNode(
                f"light-{index}",
                "device",
                f"Lamp {index}",
                {"room_id": "living-room", "capabilities": ["brightness"]},
            )
            for index in range(device_count)
        ]
        store.apply(nodes=tuple(nodes), expected_version=0)
        return store

    def test_single_topology_candidate_skips_model(self) -> None:
        client = FakeGrounderClient()
        service = DeviceDisambiguationService(
            TopologyCandidateFilter(self.topology(1)), client
        )

        result = service.resolve(
            home_id="home-1",
            image_uri="data:image/png;base64,AAAA",
            query="that lamp",
            room_id="living-room",
            capability="brightness",
        )

        self.assertEqual(client.calls, 0)
        self.assertFalse(result.ambiguous)
        self.assertEqual(result.model_version, "knowledge-anchor/deterministic")

    def test_multiple_candidates_call_grounder(self) -> None:
        client = FakeGrounderClient()
        service = DeviceDisambiguationService(
            TopologyCandidateFilter(self.topology(2)), client
        )

        result = service.resolve(
            home_id="home-1",
            image_uri="data:image/png;base64,AAAA",
            query="that lamp",
            room_id="living-room",
            capability="brightness",
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(result.selected_device_id, "light-0")

    def test_grounder_failure_remains_ambiguous_instead_of_guessing(self) -> None:
        client = FakeGrounderClient(fail=True)
        service = DeviceDisambiguationService(
            TopologyCandidateFilter(self.topology(2)), client
        )

        result = service.resolve(
            home_id="home-1",
            image_uri="data:image/png;base64,AAAA",
            query="that lamp",
            room_id="living-room",
            capability="brightness",
            timeout_seconds=0.01,
        )

        self.assertTrue(result.ambiguous)
        self.assertIsNone(result.selected_device_id)
        self.assertEqual(result.model_version, "grounder/unavailable")

    def test_http_client_rejects_device_outside_anchored_candidates(self) -> None:
        payload = {
            "selected_device_id": "invented-device",
            "ambiguous": False,
            "model_version": "test",
            "candidates": [
                {"device_id": "invented-device", "score": 0.9, "bbox": [0, 0, 1, 1]}
            ],
        }
        client = HttpGrounderClient(
            "http://grounder",
            opener=lambda request, timeout: FakeHttpResponse(payload),
        )
        candidate = GrounderCandidate(
            device=self._device("light-1"), name="Lamp"
        )

        with self.assertRaises(ValueError):
            client.ground(GrounderRequest("data:image/png;base64,AAAA", "lamp", [candidate]))

    def test_http_client_batch_preserves_each_anchored_candidate_set(self) -> None:
        requests_seen = []

        def opener(request, timeout):
            requests_seen.append(json.loads(request.data.decode("utf-8")))
            return FakeHttpResponse(
                {
                    "results": [
                        {
                            "selected_device_id": "light-1",
                            "ambiguous": False,
                            "model_version": "batch-test",
                            "candidates": [{"device_id": "light-1", "score": 0.9}],
                        },
                        {
                            "selected_device_id": "light-2",
                            "ambiguous": False,
                            "model_version": "batch-test",
                            "candidates": [{"device_id": "light-2", "score": 0.8}],
                        },
                    ],
                    "batch_size": 2,
                    "latency_ms": 12.0,
                }
            )

        client = HttpGrounderClient("http://grounder", opener=opener)
        batch = tuple(
            GrounderRequest(
                "data:image/png;base64,AAAA",
                "lamp",
                [GrounderCandidate(self._device(device_id), "Lamp")],
            )
            for device_id in ("light-1", "light-2")
        )

        results = client.ground_batch(batch)

        self.assertEqual([item.selected_device_id for item in results], ["light-1", "light-2"])
        self.assertEqual(results[0].latency_ms, 6.0)
        self.assertEqual(len(requests_seen[0]["requests"]), 2)

        with self.assertRaises(ValueError):
            client.ground_batch(())

    @staticmethod
    def _device(device_id):
        from homeclaw.domain import DeviceRef

        return DeviceRef("home-1", device_id, "living-room", "brightness")


if __name__ == "__main__":
    unittest.main()
