"""CLI entry point for Cursor usage notifier."""

from __future__ import annotations

import argparse
import math
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
from .history import record_snapshot
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

    notify_now = sub.add_parser(
        "notify-now",
        help="Fetch current spend and send one macOS notification now",
    )
    notify_now.add_argument(
        "--config",
        type=Path,
        help="Path to config TOML",
    )

    serve = sub.add_parser(
        "serve",
        help="Run the local usage history dashboard (http://127.0.0.1:8765)",
    )
    serve.add_argument(
        "--config",
        type=Path,
        help="Path to config TOML",
    )
    serve.add_argument("--host", help="Bind host (default from config / 127.0.0.1)")
    serve.add_argument(
        "--port",
        type=int,
        help="Bind port (default from config / 8765)",
    )

    open_dash = sub.add_parser(
        "open-dashboard",
        help="Open the local usage dashboard in your default browser",
    )
    open_dash.add_argument(
        "--config",
        type=Path,
        help="Path to config TOML",
    )
    return parser


def _format_usd(value: float) -> str:
    return f"${value:,.2f}"


def _format_quota(snapshot) -> str:
    if snapshot.limit_usd is not None and snapshot.limit_usd > 0:
        percent = snapshot.spend_usd / snapshot.limit_usd * 100.0
        return (
            f"{percent:.1f}% "
            f"{_format_usd(snapshot.spend_usd)}/{_format_usd(snapshot.limit_usd)}"
        )
    return _format_usd(snapshot.spend_usd)


def _next_threshold(spend_usd: float, threshold_usd: float) -> float:
    if spend_usd < threshold_usd:
        return threshold_usd
    return (math.floor(spend_usd / threshold_usd) + 1) * threshold_usd


def run_notify_now(*, config_path: Path | None) -> int:
    config = load_config(config_path)
    ensure_runtime_dirs(config)
    snapshot = fetch_usage_snapshot(resolve_session_token())
    record_snapshot(config.history_path, snapshot)
    next_at = _next_threshold(snapshot.spend_usd, config.threshold_usd)
    quota = _format_quota(snapshot)
    message = f"This cycle: {quota} (next alert at {_format_usd(next_at)})"
    send_notification(
        "Cursor Usage",
        message,
        sound=config.sound,
        group="cursor-usage-notifier-manual",
    )
    print(f"billing_cycle: {snapshot.billing_cycle_start} -> {snapshot.billing_cycle_end}")
    print(f"spend: {quota} (source: {snapshot.source})")
    print(f"notified: {message}")
    return 0


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
    print(f"spend: {_format_quota(snapshot)} (source: {snapshot.source})")
    print(f"threshold: {_format_usd(config.threshold_usd)}")
    print(f"current_milestone: {_format_usd(milestone) if milestone else '$0.00'}")
    print(f"pending_notifications: {[ _format_usd(x) for x in to_notify ]}")

    if dry_run:
        print("dry-run: skipping notifications, history, and state write")
        return 0

    record_snapshot(config.history_path, snapshot)

    for crossed in to_notify:
        message = (
            f"Cursor usage: {_format_quota(snapshot)} "
            f"(crossed {_format_usd(crossed)})"
        )
        send_notification("Cursor Usage", message, sound=config.sound)
        mark_notified(state, crossed)
        print(f"notified: crossed {_format_usd(crossed)}")

    state.last_spend_usd = snapshot.spend_usd
    state.last_check_at = format_timestamp()
    save_state(config.state_path, state)
    return 0


def run_serve(
    *,
    config_path: Path | None,
    host: str | None,
    port: int | None,
) -> int:
    from .web import run_server

    config = load_config(config_path)
    ensure_runtime_dirs(config)
    run_server(
        host=host or config.web_host,
        port=port if port is not None else config.web_port,
        history_path=config.history_path,
    )
    return 0


def dashboard_url(config_path: Path | None = None) -> str:
    config = load_config(config_path)
    host = config.web_host
    # Prefer localhost in browser URLs when bound to all interfaces.
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    return f"http://{host}:{config.web_port}"


def run_open_dashboard(*, config_path: Path | None) -> int:
    import subprocess
    import webbrowser

    url = dashboard_url(config_path)
    try:
        subprocess.run(["open", url], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        webbrowser.open(url)
    print(f"opened: {url}")
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

    if args.command == "notify-now":
        try:
            return run_notify_now(config_path=args.config)
        except AuthError as exc:
            print(f"auth error: {exc}", file=sys.stderr)
            return 2
        except FetchError as exc:
            print(f"fetch error: {exc}", file=sys.stderr)
            return 3
        except NotifyError as exc:
            print(f"notify error: {exc}", file=sys.stderr)
            return 4

    if args.command == "serve":
        return run_serve(
            config_path=args.config,
            host=args.host,
            port=args.port,
        )

    if args.command == "open-dashboard":
        return run_open_dashboard(config_path=args.config)

    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
