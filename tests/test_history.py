"""Tests for history snapshot aggregation."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from cursor_usage_notifier.fetch import UsageSnapshot
from cursor_usage_notifier.history import (
    daily_series,
    list_months,
    month_usage_payload,
    record_snapshot,
)


def _snap(spend: float, limit: float | None = 800.0) -> UsageSnapshot:
    return UsageSnapshot(
        spend_usd=spend,
        limit_usd=limit,
        billing_cycle_start="2026-08-01T00:00:00.000Z",
        billing_cycle_end="2026-09-01T00:00:00.000Z",
        membership_type="enterprise",
        source="test",
    )


def _local_day(iso_utc: str) -> str:
    dt = datetime.fromisoformat(iso_utc)
    return dt.astimezone().date().isoformat()


class HistoryTests(unittest.TestCase):
    def test_daily_delta_and_months(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "history.sqlite"
            t_prev = "2026-07-31T04:00:00+00:00"  # Jul 31 12:00 CST
            t_d1a = "2026-08-01T02:00:00+00:00"  # Aug 1 10:00 CST
            t_d1b = "2026-08-01T08:00:00+00:00"  # Aug 1 16:00 CST
            t_d2 = "2026-08-02T04:00:00+00:00"  # Aug 2 12:00 CST

            record_snapshot(db, _snap(40.0), recorded_at=t_prev)
            record_snapshot(db, _snap(100.0), recorded_at=t_d1a)
            record_snapshot(db, _snap(120.0), recorded_at=t_d1b)
            record_snapshot(db, _snap(150.0), recorded_at=t_d2)

            months = list_months(db)
            self.assertIn("2026-08", months)
            self.assertIn("2026-07", months)

            day1 = _local_day(t_d1a)
            day2 = _local_day(t_d2)
            # Skip if timezone collapses the two August UTC days onto one local date.
            if day1 == day2:
                self.skipTest("local timezone collapses sample days")

            year, month = 2026, 8
            days = daily_series(db, year, month)
            by_date = {d.date: d for d in days}
            self.assertIn(day1, by_date)
            self.assertIn(day2, by_date)
            self.assertAlmostEqual(by_date[day1].end_spend, 120.0)
            self.assertAlmostEqual(by_date[day2].end_spend, 150.0)
            self.assertAlmostEqual(by_date[day2].day_delta, 30.0)

            # First August local day's delta uses previous snapshot (40).
            prev_local = _local_day(t_prev)
            if prev_local != day1:
                self.assertAlmostEqual(by_date[day1].day_delta, 80.0)

            payload = month_usage_payload(db, "2026-08")
            self.assertEqual(payload["month"], "2026-08")
            self.assertAlmostEqual(payload["total_spend"], 150.0)
            self.assertAlmostEqual(payload["limit_usd"], 800.0)


if __name__ == "__main__":
    unittest.main()
