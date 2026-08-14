"""Persist and query historical usage snapshots."""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .fetch import UsageSnapshot, format_timestamp


@dataclass(frozen=True)
class DailyUsage:
    date: str  # YYYY-MM-DD
    end_spend: float
    day_delta: float
    limit_usd: float | None
    sample_count: int


def default_history_path() -> Path:
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "cursor-usage-notifier"
        / "history.sqlite"
    )


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL,
            spend_usd REAL NOT NULL,
            limit_usd REAL,
            billing_cycle_start TEXT,
            source TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_recorded_at "
        "ON snapshots(recorded_at)"
    )
    conn.commit()


def record_snapshot(
    db_path: Path,
    snapshot: UsageSnapshot,
    *,
    recorded_at: str | None = None,
) -> None:
    ts = recorded_at or format_timestamp()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO snapshots (
                recorded_at, spend_usd, limit_usd, billing_cycle_start, source
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                ts,
                float(snapshot.spend_usd),
                float(snapshot.limit_usd) if snapshot.limit_usd is not None else None,
                snapshot.billing_cycle_start or "",
                snapshot.source or "",
            ),
        )
        conn.commit()


def list_months(db_path: Path) -> list[str]:
    """Return YYYY-MM months that have at least one snapshot, newest first."""
    if not db_path.is_file():
        return []
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT substr(recorded_at, 1, 7) AS month
            FROM snapshots
            WHERE length(recorded_at) >= 7
            ORDER BY month DESC
            """
        ).fetchall()
    return [str(r["month"]) for r in rows if r["month"]]


def _parse_month(month: str) -> tuple[int, int]:
    year_s, month_s = month.split("-", 1)
    year = int(year_s)
    mon = int(month_s)
    if mon < 1 or mon > 12:
        raise ValueError(f"invalid month: {month}")
    return year, mon


def _local_date_from_recorded_at(recorded_at: str) -> date:
    """Map snapshot timestamp to the user's local calendar date."""
    raw = recorded_at.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date()


def daily_series(db_path: Path, year: int, month: int) -> list[DailyUsage]:
    if not db_path.is_file():
        return []

    with connect(db_path) as conn:
        start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end = date(year, month, last_day)

        rows = conn.execute(
            """
            SELECT recorded_at, spend_usd, limit_usd
            FROM snapshots
            WHERE recorded_at >= ? AND recorded_at < ?
            ORDER BY recorded_at ASC
            """,
            (
                f"{year:04d}-{month:02d}-01T00:00:00+00:00",
                f"{year + (1 if month == 12 else 0):04d}-"
                f"{(1 if month == 12 else month + 1):02d}-02T00:00:00+00:00",
            ),
        ).fetchall()

        prev_rows = conn.execute(
            """
            SELECT recorded_at, spend_usd
            FROM snapshots
            WHERE recorded_at < ?
            ORDER BY recorded_at DESC
            LIMIT 200
            """,
            (f"{year:04d}-{month:02d}-01T00:00:00+00:00",),
        ).fetchall()

    by_day: dict[date, list[tuple[float, float | None]]] = {}
    for row in rows:
        day = _local_date_from_recorded_at(str(row["recorded_at"]))
        if day < start or day > end:
            continue
        spend = float(row["spend_usd"])
        limit = float(row["limit_usd"]) if row["limit_usd"] is not None else None
        by_day.setdefault(day, []).append((spend, limit))

    prev_end: float | None = None
    for row in prev_rows:
        day = _local_date_from_recorded_at(str(row["recorded_at"]))
        if day < start:
            prev_end = float(row["spend_usd"])
            break

    days: list[DailyUsage] = []
    previous = prev_end
    for day in sorted(by_day):
        samples = by_day[day]
        end_spend = max(s for s, _ in samples)
        limit_usd = None
        for _, lim in reversed(samples):
            if lim is not None:
                limit_usd = lim
                break
        if previous is None:
            day_delta = end_spend
        else:
            day_delta = max(0.0, end_spend - previous)
        days.append(
            DailyUsage(
                date=day.isoformat(),
                end_spend=end_spend,
                day_delta=day_delta,
                limit_usd=limit_usd,
                sample_count=len(samples),
            )
        )
        previous = end_spend
    return days


def month_usage_payload(db_path: Path, month: str) -> dict:
    year, mon = _parse_month(month)
    days = daily_series(db_path, year, mon)
    total_spend = days[-1].end_spend if days else 0.0
    limit_usd = None
    for day in reversed(days):
        if day.limit_usd is not None:
            limit_usd = day.limit_usd
            break
    return {
        "month": month,
        "days": [
            {
                "date": d.date,
                "end_spend": round(d.end_spend, 4),
                "day_delta": round(d.day_delta, 4),
                "limit_usd": d.limit_usd,
                "sample_count": d.sample_count,
                "percent": (
                    round(d.end_spend / d.limit_usd * 100.0, 2)
                    if d.limit_usd and d.limit_usd > 0
                    else None
                ),
            }
            for d in days
        ],
        "total_spend": round(total_spend, 4),
        "limit_usd": limit_usd,
    }


def current_month_key(now: datetime | None = None) -> str:
    dt = now or datetime.now().astimezone()
    return f"{dt.year:04d}-{dt.month:02d}"
