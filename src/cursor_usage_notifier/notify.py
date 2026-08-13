"""Send sticky macOS alerts that stay until the user dismisses them."""

from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
from pathlib import Path


class NotifyError(Exception):
    """Raised when a macOS notification cannot be delivered."""


def _project_alerter() -> Path:
    # src/cursor_usage_notifier/notify.py -> repo root/bin/alerter
    return Path(__file__).resolve().parents[2] / "bin" / "alerter"


def _is_executable(path: Path) -> bool:
    return path.is_file() and (path.stat().st_mode & 0o111) != 0


def _resolve_alerter() -> str | None:
    bundled = _project_alerter()
    if _is_executable(bundled):
        return str(bundled)
    return shutil.which("alerter")


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _send_via_alerter(
    alerter: str,
    title: str,
    message: str,
    sound: str,
    *,
    group: str | None,
) -> None:
    """
    Fire a sticky alert and return immediately.

    alerter blocks until the user dismisses when timeout=0, so launch it
    detached so polling / Alfred stay responsive.
    """
    cmd = [
        alerter,
        "--title",
        title,
        "--message",
        message,
        "--timeout",
        "0",
        "--close-label",
        "Close",
        "--ignore-dnd",
        "--group",
        group or f"cursor-usage-notifier-{uuid.uuid4().hex[:8]}",
    ]
    if sound:
        cmd.extend(["--sound", sound])

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise NotifyError(f"alerter failed to start: {exc}") from exc


def _send_via_osascript(title: str, message: str, sound: str) -> None:
    """Fallback banner notification (auto-hides per Notification Center settings)."""
    title_esc = _escape_applescript(title)
    message_esc = _escape_applescript(message)
    sound_esc = _escape_applescript(sound)
    script = (
        f'display notification "{message_esc}" '
        f'with title "{title_esc}" sound name "{sound_esc}"'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise NotifyError(f"osascript failed: {stderr or exc}") from exc


def send_notification(
    title: str,
    message: str,
    sound: str = "Glass",
    *,
    group: str | None = None,
) -> None:
    """
    Display a sticky alert in the top-right that stays until Close is clicked.

    Prefers bundled/PATH `alerter` (timeout 0). Falls back to osascript banners
    if alerter is unavailable.
    """
    alerter = _resolve_alerter()
    if alerter:
        _send_via_alerter(alerter, title, message, sound, group=group)
        return
    _send_via_osascript(title, message, sound)
    print(
        "warning: alerter not found; used auto-hiding banner. "
        "Install bin/alerter for sticky alerts.",
        file=sys.stderr,
    )
