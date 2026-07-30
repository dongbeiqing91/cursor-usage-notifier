"""Send macOS Notification Center alerts."""

from __future__ import annotations

import subprocess


class NotifyError(Exception):
    """Raised when a macOS notification cannot be delivered."""


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def send_notification(title: str, message: str, sound: str = "Glass") -> None:
    """Display a macOS notification via osascript."""
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
