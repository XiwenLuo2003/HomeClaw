from __future__ import annotations

import unittest

from homeclaw.memory import MongoPreferenceStore, PreferenceFact, PreferenceSource


class DuplicateKey(Exception):
    code = 11000


class RetryingMongoPreferenceStore(MongoPreferenceStore):
    def __init__(self):
        super().__init__(collection=None, maximum_attempts=3)
        self.calls = 0

    def _add_once(self, fact):
        self.calls += 1
        if self.calls == 1:
            raise DuplicateKey("concurrent active preference")
        return "stored"


class FatalMongoPreferenceStore(MongoPreferenceStore):
    def __init__(self):
        super().__init__(collection=None, maximum_attempts=3)
        self.calls = 0

    def _add_once(self, fact):
        self.calls += 1
        raise ValueError("schema error")


class MongoPreferenceRetryTests(unittest.TestCase):
    def test_duplicate_key_race_retries_but_schema_error_does_not(self):
        fact = PreferenceFact("amal", "temperature", 24, PreferenceSource.EXPLICIT)
        retrying = RetryingMongoPreferenceStore()
        self.assertEqual(retrying.add(fact), "stored")
        self.assertEqual(retrying.calls, 2)

        fatal = FatalMongoPreferenceStore()
        with self.assertRaises(ValueError):
            fatal.add(fact)
        self.assertEqual(fatal.calls, 1)


if __name__ == "__main__":
    unittest.main()
