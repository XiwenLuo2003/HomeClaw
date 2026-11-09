from __future__ import annotations

import unittest

from homeclaw.eval import StateConsistencyObservation, summarize_state_consistency


class StateConsistencyMetricTests(unittest.TestCase):
    def test_reports_cache_staleness_read_your_write_and_latency_percentiles(self) -> None:
        summary = summarize_state_consistency(
            [
                StateConsistencyObservation(True, False, True, True, 10, 8, False),
                StateConsistencyObservation(True, True, True, False, 50, 20, True),
                StateConsistencyObservation(False, False, False, False, None, 30, False),
            ]
        )

        self.assertEqual(summary.samples, 3)
        self.assertAlmostEqual(summary.cache_hit_rate, 2 / 3)
        self.assertAlmostEqual(summary.stale_read_rate, 1 / 3)
        self.assertEqual(summary.read_your_write_rate, 0.5)
        self.assertAlmostEqual(summary.reconciliation_difference_rate, 1 / 3)
        self.assertEqual(summary.confirmation_p95_ms, 50)
        self.assertEqual(summary.reconciliation_p50_ms, 20)


if __name__ == "__main__":
    unittest.main()
