from __future__ import annotations

import unittest
from types import SimpleNamespace

from homeclaw.memory import MemorySummary, MongoSummaryStore, SummaryPeriod


class FakeCollection:
    def __init__(self) -> None:
        self.items = {}

    def find_one(self, query):
        for item in self.items.values():
            if all(item.get(key) == value for key, value in query.items()):
                return dict(item)
        return None

    def insert_one(self, document):
        self.items[document["_id"]] = dict(document)

    def update_one(self, query, update):
        item = self.items.get(query["_id"])
        if item is None or item.get("version") != query["version"]:
            return SimpleNamespace(matched_count=0)
        item.update(update["$set"])
        item["version"] += update["$inc"]["version"]
        return SimpleNamespace(matched_count=1)


class MongoSummaryStoreTests(unittest.TestCase):
    def test_same_sources_are_idempotent_and_changed_sources_increment_version(self) -> None:
        collection = FakeCollection()
        store = MongoSummaryStore(collection)
        first = MemorySummary(
            "amal", SummaryPeriod.DAILY, "2026-11-09", "first", ("event-1",)
        )

        created = store.put_if_changed(first)
        duplicate = store.put_if_changed(first)
        changed = store.put_if_changed(
            MemorySummary(
                "amal",
                SummaryPeriod.DAILY,
                "2026-11-09",
                "changed",
                ("event-1", "event-2"),
            )
        )

        self.assertEqual(created.version, 1)
        self.assertEqual(duplicate.summary_id, created.summary_id)
        self.assertEqual(changed.version, 2)
        self.assertEqual(changed.source_event_ids, ("event-1", "event-2"))
        self.assertEqual(store.get("amal", SummaryPeriod.DAILY, "2026-11-09").text, "changed")


if __name__ == "__main__":
    unittest.main()
