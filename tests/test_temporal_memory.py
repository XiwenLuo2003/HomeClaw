from __future__ import annotations

import unittest
from datetime import timedelta

from homeclaw.domain.models import utc_now
from homeclaw.memory import (
    InMemoryPreferenceStore,
    InMemorySummaryStore,
    MemoryEvent,
    PreferenceFact,
    PreferenceQuery,
    PreferenceScope,
    PreferenceSource,
    SummaryPeriod,
    SummaryService,
)


class TemporalPreferenceTests(unittest.TestCase):
    def test_latest_explicit_fact_invalidates_previous_fact_without_deleting_history(self) -> None:
        store = InMemoryPreferenceStore()
        start = utc_now()
        warm = PreferenceFact(
            "amal", "light_color", "warm", PreferenceSource.EXPLICIT, valid_at=start
        )
        cool = PreferenceFact(
            "amal",
            "light_color",
            "cool",
            PreferenceSource.EXPLICIT,
            valid_at=start + timedelta(seconds=1),
        )

        first = store.add(warm)
        second = store.add(cool)
        resolved = store.resolve(
            PreferenceQuery("amal", "light_color", at=start + timedelta(seconds=2))
        )

        self.assertTrue(first.active)
        self.assertEqual(second.invalidated_fact_ids, (warm.fact_id,))
        self.assertEqual(resolved.value, "cool")
        history = store.history("amal", "light_color")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].invalid_at, cool.valid_at)

    def test_inferred_fact_cannot_override_explicit_fact_in_same_scope(self) -> None:
        store = InMemoryPreferenceStore()
        start = utc_now()
        explicit = PreferenceFact(
            "amal", "temperature", 24, PreferenceSource.EXPLICIT, valid_at=start
        )
        inferred = PreferenceFact(
            "amal",
            "temperature",
            22,
            PreferenceSource.INFERRED,
            confidence=0.99,
            valid_at=start + timedelta(minutes=1),
        )
        store.add(explicit)

        result = store.add(inferred)
        resolved = store.resolve(
            PreferenceQuery("amal", "temperature", at=start + timedelta(minutes=2))
        )

        self.assertFalse(result.active)
        self.assertIn("cannot override explicit", result.reason)
        self.assertEqual(resolved.value, 24)

    def test_specific_scope_overrides_global_only_when_query_matches(self) -> None:
        store = InMemoryPreferenceStore()
        now = utc_now()
        store.add(PreferenceFact("amal", "brightness", 40, PreferenceSource.EXPLICIT, valid_at=now))
        store.add(
            PreferenceFact(
                "amal",
                "brightness",
                20,
                PreferenceSource.EXPLICIT,
                scope=PreferenceScope.ROOM,
                scope_id="bedroom",
                valid_at=now,
            )
        )

        bedroom = store.resolve(PreferenceQuery("amal", "brightness", room_id="bedroom"))
        kitchen = store.resolve(PreferenceQuery("amal", "brightness", room_id="kitchen"))

        self.assertEqual(bedroom.value, 20)
        self.assertEqual(kitchen.value, 40)

    def test_expired_temporary_preference_is_not_resolved(self) -> None:
        store = InMemoryPreferenceStore()
        start = utc_now()
        store.add(
            PreferenceFact(
                "amal",
                "temperature",
                20,
                PreferenceSource.EXPLICIT,
                valid_at=start,
                expires_at=start + timedelta(minutes=10),
            )
        )
        self.assertIsNone(
            store.resolve(
                PreferenceQuery("amal", "temperature", at=start + timedelta(minutes=11))
            )
        )

    def test_users_are_isolated_and_owner_can_revoke_without_deleting_history(self) -> None:
        store = InMemoryPreferenceStore()
        start = utc_now()
        amal = PreferenceFact(
            "amal", "temperature", 24, PreferenceSource.EXPLICIT, valid_at=start
        )
        bob = PreferenceFact(
            "bob", "temperature", 20, PreferenceSource.EXPLICIT, valid_at=start
        )
        store.add(amal)
        store.add(bob)

        with self.assertRaises(KeyError):
            store.revoke("bob", amal.fact_id, start + timedelta(minutes=1))
        revoked = store.revoke("amal", amal.fact_id, start + timedelta(minutes=1))

        self.assertIsNotNone(revoked.invalid_at)
        self.assertIsNone(
            store.resolve(
                PreferenceQuery("amal", "temperature", at=start + timedelta(minutes=2))
            )
        )
        self.assertEqual(
            store.resolve(
                PreferenceQuery("bob", "temperature", at=start + timedelta(minutes=2))
            ).value,
            20,
        )
        self.assertEqual(len(store.history("amal", "temperature")), 1)


class SummaryTests(unittest.TestCase):
    def test_summary_materialization_is_idempotent_and_versioned(self) -> None:
        store = InMemorySummaryStore()
        service = SummaryService(
            store,
            lambda events: " | ".join(event.content for event in events),
        )
        now = utc_now()
        first_event = MemoryEvent("amal", "preferred warm light", now)

        first = service.materialize("amal", SummaryPeriod.DAILY, "2026-11-09", [first_event])
        duplicate = service.materialize("amal", SummaryPeriod.DAILY, "2026-11-09", [first_event])
        changed = service.materialize(
            "amal",
            SummaryPeriod.DAILY,
            "2026-11-09",
            [first_event, MemoryEvent("amal", "slept early", now + timedelta(minutes=1))],
        )

        self.assertEqual(first.summary_id, duplicate.summary_id)
        self.assertEqual(first.version, 1)
        self.assertEqual(changed.version, 2)
        self.assertEqual(len(changed.source_event_ids), 2)


if __name__ == "__main__":
    unittest.main()
