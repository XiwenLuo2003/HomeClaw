from __future__ import annotations

import unittest

from homeclaw.mcp_runtime import DomainMCPServer
from homeclaw.mcp_runtime.resources import StateResourcePublisher
from homeclaw.state import (
    InMemoryStateCache,
    ReadThroughStateService,
    StateReconciler,
    VersionedStateDiff,
)


class FakeReader:
    def __init__(self, sequence, state):
        self.sequence = sequence
        self.state = state

    def read(self, home_id, device_id):
        return self.sequence, self.state


class CountingReader(FakeReader):
    def __init__(self, sequence, state, fail=False):
        super().__init__(sequence, state)
        self.calls = 0
        self.fail = fail

    def read(self, home_id, device_id):
        self.calls += 1
        if self.fail:
            raise ConnectionError("gateway offline")
        return super().read(home_id, device_id)


class StateResourceTests(unittest.TestCase):
    def test_high_frequency_updates_are_aggregated_and_only_anomalies_notify(self) -> None:
        server = DomainMCPServer()
        cache = InMemoryStateCache()
        publisher = StateResourcePublisher(
            server,
            cache,
            should_notify=lambda previous, current: current.state.get("temperature", 0) >= 30,
        )
        uri = publisher.register("home-1", "sensor-1", "Temperature sensor")
        notifications = []
        server.subscribe_resource(uri, notifications.append)

        publisher.apply(VersionedStateDiff("home-1", "sensor-1", 1, {"temperature": 20}))
        publisher.apply(VersionedStateDiff("home-1", "sensor-1", 2, {"temperature": 21}))
        publisher.apply(VersionedStateDiff("home-1", "sensor-1", 3, {"temperature": 31}))

        resource = server.read_resource(uri)
        self.assertEqual(resource["sequence"], 3)
        self.assertEqual(resource["state"]["temperature"], 31)
        self.assertEqual(notifications, [uri])

    def test_authoritative_reconcile_repairs_missed_diff(self) -> None:
        cache = InMemoryStateCache()
        cache.apply(VersionedStateDiff("home-1", "light-1", 1, {"power": "off"}))
        reconciler = StateReconciler(cache, FakeReader(4, {"power": "on", "brightness": 40}))

        result = reconciler.reconcile("home-1", "light-1")

        self.assertTrue(result.changed)
        self.assertEqual(result.difference_fields, ("brightness", "power"))
        snapshot = cache.get("home-1", "light-1")
        self.assertEqual(snapshot.sequence, 4)
        self.assertEqual(snapshot.state["power"], "on")

    def test_read_through_uses_cache_then_repairs_miss_from_truth_source(self) -> None:
        cache = InMemoryStateCache()
        reader = CountingReader(7, {"power": "on"})
        service = ReadThroughStateService(cache, reader)

        first = service.read("home-1", "light-1")
        second = service.read("home-1", "light-1")

        self.assertEqual(first.sequence, 7)
        self.assertEqual(second.state["power"], "on")
        self.assertEqual(reader.calls, 1)


if __name__ == "__main__":
    unittest.main()
