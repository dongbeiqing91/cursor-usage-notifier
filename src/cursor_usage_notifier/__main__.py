"""CLI entry point for Cursor usage notifier."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .auth import AuthError, resolve_session_token
from .config import ensure_runtime_dirs, load_config
from .fetch import (
    FetchError,
    compute_milestone,
    fetch_usage_snapshot,
    format_timestamp,
)
from .notify import NotifyError, send_notification
from .state import (
    load_state,
    mark_notified,
    pending_milestones,
    reset_for_new_cycle,
    save_state,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cursor-usage-notifier",
        description="Notify on macOS when Cursor monthly usage crosses thresholds.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config TOML (default: ~/Library/Application Support/cursor-usage-notifier/config.toml)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Run one check and optionally notify")
    check.add_argument(
        "--config",
        type=Path,
        help="Path to config TOML",
    )
    check.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send notifications or write state",
    )
    check.add_argument(
        "--notify-test",
        action="store_true",
        help="Send a test notification and exit",
    )
    return parser


def _format_usd(value: float) -> str:
    return f"${value:,.2f}"


def run_check(*, config_path: Path | None, dry_run: bool) -> int:
    config = load_config(config_path)
    ensure_runtime_dirs(config)
    state = load_state(config.state_path)

    token = resolve_session_token()
    snapshot = fetch_usage_snapshot(token)

    if (
        snapshot.billing_cycle_start
        and state.billing_cycle_start
        and snapshot.billing_cycle_start != state.billing_cycle_start
    ):
        reset_for_new_cycle(state, snapshot.billing_cycle_start)
    elif snapshot.billing_cycle_start and not state.billing_cycle_start:
        state.billing_cycle_start = snapshot.billing_cycle_start

    milestone = compute_milestone(snapshot.spend_usd, config.threshold_usd)
    to_notify = pending_milestones(
        snapshot.spend_usd,
        config.threshold_usd,
        state.notified_milestones,
    )

    # First run: seed milestones already crossed this cycle without backfilling alerts.
    if not state.last_check_at and to_notify:
        for crossed in to_notify:
            mark_notified(state, crossed)
        print(
            "bootstrap: recorded existing milestones "
            f"{[ _format_usd(x) for x in to_notify ]} without notifying"
        )
        to_notify = []

    print(f"billing_cycle: {snapshot.billing_cycle_start} -> {snapshot.billing_cycle_end}")
    print(f"membership: {snapshot.membership_type}")
    print(f"spend: {_format_usd(snapshot.spend_usd)} (source: {snapshot.source})")
    print(f"threshold: {_format_usd(config.threshold_usd)}")
    print(f"current_milestone: {_format_usd(milestone) if milestone else '$0.00'}")
    print(f"pending_notifications: {[ _format_usd(x) for x in to_notify ]}")

    if dry_run:
        print("dry-run: skipping notifications and state write")
        return 0

    for crossed in to_notify:
        message = (
            f"Cursor usage: {_format_usd(snapshot.spend_usd)} this cycle "
            f"(crossed {_format_usd(crossed)})"
        )
        send_notification("Cursor Usage", message, sound=config.sound)
        mark_notified(state, crossed)
        print(f"notified: crossed {_format_usd(crossed)}")

    state.last_spend_usd = snapshot.spend_usd
    state.last_check_at = format_timestamp()
    save_state(config.state_path, state)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        if args.notify_test:
            send_notification(
                "Cursor Usage",
                "Test notification from cursor-usage-notifier",
            )
            print("sent test notification")
            return 0
        try:
            return run_check(config_path=args.config, dry_run=args.dry_run)
        except AuthError as exc:
            print(f"auth error: {exc}", file=sys.stderr)
            return 2
        except FetchError as exc:
            print(f"fetch error: {exc}", file=sys.stderr)
            return 3
        except NotifyError as exc:
            print(f"notify error: {exc}", file=sys.stderr)
            return 4

    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
