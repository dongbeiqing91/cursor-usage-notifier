"""Tests for milestone and state helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cursor_usage_notifier.fetch import (
    _extract_spend_from_summary,
    compute_milestone,
)
from cursor_usage_notifier.state import (
    load_state,
    pending_milestones,
    save_state,
    NotifierState,
)


class MilestoneTests(unittest.TestCase):
    def test_compute_milestone(self) -> None:
        self.assertEqual(compute_milestone(49.99, 50), 0.0)
        self.assertEqual(compute_milestone(50.0, 50), 50.0)
        self.assertEqual(compute_milestone(102.4, 50), 100.0)

    def test_pending_milestones(self) -> None:
        pending = pending_milestones(125.0, 50.0, [50.0])
        self.assertEqual(pending, [100.0])


class SpendExtractionTests(unittest.TestCase):
    def test_prefers_personal_overall_over_team_on_demand(self) -> None:
        spend, limit, source = _extract_spend_from_summary(
            {
                "individualUsage": {
                    "overall": {
                        "enabled": True,
                        "used": 47753,
                        "limit": 80000,
                    }
                },
                "teamUsage": {"onDemand": {"enabled": True, "used": 2789}},
            }
        )
        self.assertAlmostEqual(spend, 477.53)
        self.assertAlmostEqual(limit, 800.0)
        self.assertEqual(source, "individualUsage.overall.used")


class StateTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = NotifierState(
                billing_cycle_start="2026-07-01T00:00:00.000Z",
                notified_milestones=[50.0, 100.0],
                last_spend_usd=120.5,
                last_check_at="2026-07-30T00:00:00+00:00",
            )
            save_state(path, state)
            loaded = load_state(path)
            self.assertEqual(loaded.billing_cycle_start, state.billing_cycle_start)
            self.assertEqual(loaded.notified_milestones, state.notified_milestones)
            self.assertEqual(loaded.last_spend_usd, state.last_spend_usd)


if __name__ == "__main__":
    unittest.main()
