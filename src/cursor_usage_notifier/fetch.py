"""Fetch current billing-cycle usage from Cursor dashboard API."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

USAGE_SUMMARY_URL = "https://cursor.com/api/usage-summary"
AGGREGATED_EVENTS_URL = (
    "https://cursor.com/api/dashboard/get-aggregated-usage-events"
)


class FetchError(Exception):
    """Raised when usage data cannot be fetched or parsed."""


@dataclass(frozen=True)
class UsageSnapshot:
    spend_usd: float
    limit_usd: float | None
    billing_cycle_start: str
    billing_cycle_end: str
    membership_type: str
    source: str


def _cookie_header(token: str) -> str:
    return f"WorkosCursorSessionToken={token}"


def _request_json(
    *,
    url: str,
    token: str,
    method: str = "GET",
    body: dict | None = None,
) -> dict:
    headers = {
        "Accept": "application/json",
        "Cookie": _cookie_header(token),
        "User-Agent": "cursor-usage-notifier/0.1",
    }
    data = None
    if method == "POST":
        headers["Content-Type"] = "application/json"
        headers["Origin"] = "https://cursor.com"
        data = json.dumps(body or {}).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 401:
            raise FetchError(
                "Cursor session is not authenticated (401). "
                "Sign in to Cursor or refresh CURSOR_SESSION_TOKEN."
            ) from exc
        raise FetchError(f"HTTP {exc.code} from Cursor API: {detail}") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"Network error calling Cursor API: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FetchError("Cursor API returned non-JSON response") from exc
    if not isinstance(payload, dict):
        raise FetchError("Cursor API returned unexpected payload")
    return payload


def _cents_to_usd(value: object) -> float:
    if value is None:
        return 0.0
    return float(value) / 100.0


def _parse_iso(value: object) -> str:
    if not value:
        return ""
    return str(value)


def _extract_spend_from_summary(summary: dict) -> tuple[float, float | None, str]:
    """
    Prefer personal total usage over team on-demand overage.

    Enterprise summaries often look like:
      individualUsage.overall.used/limit -> personal cycle spend/quota (cents)
      teamUsage.onDemand.used            -> team-wide on-demand only (not personal total)

    Returns (spend_usd, limit_usd_or_none, source).
    """
    individual = summary.get("individualUsage") or {}
    on_demand = individual.get("onDemand") or {}
    plan = individual.get("plan") or {}
    overall = individual.get("overall") or {}

    overall_used = overall.get("used")
    if overall_used is not None:
        limit = overall.get("limit")
        return (
            _cents_to_usd(overall_used),
            _cents_to_usd(limit) if limit is not None else None,
            "individualUsage.overall.used",
        )

    on_demand_used = on_demand.get("used")
    if on_demand_used is not None:
        limit = on_demand.get("limit")
        return (
            _cents_to_usd(on_demand_used),
            _cents_to_usd(limit) if limit is not None else None,
            "individualUsage.onDemand.used",
        )

    # Legacy schema fallback when only plan percentages are available.
    total_percent = plan.get("totalPercentUsed")
    if total_percent is not None:
        return float(total_percent), None, "individualUsage.plan.totalPercentUsed"

    api_percent = plan.get("apiPercentUsed")
    if api_percent is not None:
        return float(api_percent), None, "individualUsage.plan.apiPercentUsed"

    # Team on-demand is a last resort (team-wide, not personal total).
    team_on_demand = (summary.get("teamUsage") or {}).get("onDemand") or {}
    team_used = team_on_demand.get("used")
    if team_used is not None:
        limit = team_on_demand.get("limit")
        return (
            _cents_to_usd(team_used),
            _cents_to_usd(limit) if limit is not None else None,
            "teamUsage.onDemand.used",
        )

    return 0.0, None, "none"


def _fetch_aggregated_total_cents(token: str) -> float:
    payload = _request_json(
        url=AGGREGATED_EVENTS_URL,
        token=token,
        method="POST",
        body={},
    )
    total = payload.get("totalCostCents")
    if total is not None:
        return float(total)

    events = payload.get("aggregatedUsageEvents") or payload.get("aggregations") or []
    total_cents = 0.0
    for event in events:
        if not isinstance(event, dict):
            continue
        cents = event.get("totalCents")
        if cents is None:
            continue
        total_cents += float(cents)
    return total_cents


def fetch_usage_snapshot(token: str) -> UsageSnapshot:
    """Fetch current billing-cycle spend for the authenticated user."""
    summary = _request_json(url=USAGE_SUMMARY_URL, token=token)
    spend_usd, limit_usd, source = _extract_spend_from_summary(summary)

    # Percent-based fallback is not dollar spend; try aggregated totals.
    if source.endswith("PercentUsed") or spend_usd <= 0:
        try:
            total_cents = _fetch_aggregated_total_cents(token)
            if total_cents > 0:
                spend_usd = total_cents / 100.0
                source = "aggregatedUsageEvents.totalCostCents"
        except FetchError:
            pass

    return UsageSnapshot(
        spend_usd=max(0.0, spend_usd),
        limit_usd=limit_usd,
        billing_cycle_start=_parse_iso(summary.get("billingCycleStart")),
        billing_cycle_end=_parse_iso(summary.get("billingCycleEnd")),
        membership_type=str(summary.get("membershipType") or "unknown"),
        source=source,
    )


def compute_milestone(spend_usd: float, threshold_usd: float) -> float:
    if threshold_usd <= 0:
        raise ValueError("threshold_usd must be > 0")
    if spend_usd < threshold_usd:
        return 0.0
    return math.floor(spend_usd / threshold_usd) * threshold_usd


def format_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
