"""Persist notifier state across billing cycles."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NotifierState:
    billing_cycle_start: str = ""
    notified_milestones: list[float] = field(default_factory=list)
    last_spend_usd: float = 0.0
    last_check_at: str = ""


def load_state(path: Path) -> NotifierState:
    if not path.is_file():
        return NotifierState()
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        return NotifierState()
    milestones = raw.get("notified_milestones", [])
    if not isinstance(milestones, list):
        milestones = []
    return NotifierState(
        billing_cycle_start=str(raw.get("billing_cycle_start") or ""),
        notified_milestones=[float(x) for x in milestones],
        last_spend_usd=float(raw.get("last_spend_usd") or 0.0),
        last_check_at=str(raw.get("last_check_at") or ""),
    )


def save_state(path: Path, state: NotifierState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "billing_cycle_start": state.billing_cycle_start,
        "notified_milestones": state.notified_milestones,
        "last_spend_usd": state.last_spend_usd,
        "last_check_at": state.last_check_at,
    }
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    tmp.replace(path)


def reset_for_new_cycle(state: NotifierState, billing_cycle_start: str) -> None:
    state.billing_cycle_start = billing_cycle_start
    state.notified_milestones = []


def mark_notified(state: NotifierState, milestone: float) -> None:
    if milestone not in state.notified_milestones:
        state.notified_milestones.append(milestone)
        state.notified_milestones.sort()


def pending_milestones(
    spend_usd: float,
    threshold_usd: float,
    notified: list[float],
) -> list[float]:
    if spend_usd < threshold_usd:
        return []
    max_milestone = int(spend_usd // threshold_usd) * threshold_usd
    milestones: list[float] = []
    current = threshold_usd
    while current <= max_milestone:
        if current not in notified:
            milestones.append(current)
        current += threshold_usd
    return milestones
