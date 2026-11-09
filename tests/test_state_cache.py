from __future__ import annotations

import unittest
from datetime import timedelta

from homeclaw.domain.models import utc_now
from homeclaw.state import (
    ApplyResult,
    InMemoryStateCache,
    VersionedStateDiff,
    matches_expected_state,
)


class StateCacheTests(unittest.TestCase):
    def test_incremental_diff_merges_and_rejects_old_versions(self) -> None:
        cache = InMemoryStateCache(ttl_seconds=60)
        first = VersionedStateDiff("home-1", "light-1", 10, {"power": "on", "brightness": 20})
        next_diff = VersionedStateDiff("home-1", "light-1", 11, {"brightness": 40})
        old = VersionedStateDiff("home-1", "light-1", 9, {"power": "off"})

        self.assertEqual(cache.apply(first), ApplyResult.APPLIED)
        self.assertEqual(cache.apply(next_diff), ApplyResult.APPLIED)
        self.assertEqual(cache.apply(next_diff), ApplyResult.DUPLICATE)
        self.assertEqual(cache.apply(old), ApplyResult.OUT_OF_ORDER)
        snapshot = cache.get("home-1", "light-1")

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.state, {"power": "on", "brightness": 40})

    def test_stale_state_is_hidden_unless_explicitly_requested(self) -> None:
        cache = InMemoryStateCache(ttl_seconds=1)
        cache.apply(
            VersionedStateDiff(
                "home-1",
                "sensor-1",
                1,
                {"temperature": 20},
                observed_at=utc_now() - timedelta(seconds=5),
            )
        )

        self.assertIsNone(cache.get("home-1", "sensor-1"))
        stale = cache.get("home-1", "sensor-1", allow_stale=True)
        self.assertIsNotNone(stale)
        self.assertTrue(stale.stale)

    def test_expected_state_is_recursive_and_ignores_extra_fields(self) -> None:
        observed = {"power": "on", "color": {"r": 255, "g": 0}, "sequence": 8}
        self.assertTrue(matches_expected_state(observed, {"color": {"r": 255}}))
        self.assertFalse(matches_expected_state(observed, {"color": {"r": 0}}))

    def test_incremental_gap_is_rejected_until_full_snapshot_reconciles(self) -> None:
        cache = InMemoryStateCache()
        cache.apply(VersionedStateDiff("home-1", "light-1", 1, {"power": "off"}))

        gap = cache.apply(
            VersionedStateDiff("home-1", "light-1", 3, {"brightness": 40})
        )
        repaired = cache.apply(
            VersionedStateDiff(
                "home-1",
                "light-1",
                3,
                {"power": "on", "brightness": 40},
                source="authoritative",
                full_snapshot=True,
            )
        )

        self.assertEqual(gap, ApplyResult.GAP)
        self.assertEqual(repaired, ApplyResult.APPLIED)
        self.assertEqual(
            cache.get("home-1", "light-1").state,
            {"power": "on", "brightness": 40},
        )


if __name__ == "__main__":
    unittest.main()
