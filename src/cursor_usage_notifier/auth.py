"""Resolve Cursor session token for dashboard API access."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
from pathlib import Path

CURSOR_STATE_DB = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Cursor"
    / "User"
    / "globalStorage"
    / "state.vscdb"
)
AUTH_KEY = "cursorAuth/accessToken"


class AuthError(Exception):
    """Raised when a Cursor session token cannot be resolved."""


def _read_token_from_db(db_path: Path) -> str | None:
    if not db_path.is_file():
        return None
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key = ?",
            (AUTH_KEY,),
        ).fetchone()
    if not row or not row[0]:
        return None
    token = row[0]
    if isinstance(token, bytes):
        token = token.decode("utf-8", errors="replace")
    token = str(token).strip()
    return token or None


def _jwt_sub(token: str) -> str:
    try:
        payload_segment = token.split(".", 2)[1]
    except IndexError as exc:
        raise AuthError("Cursor access token is not a valid JWT") from exc
    padded = payload_segment + "=" * (-len(payload_segment) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (json.JSONDecodeError, ValueError) as exc:
        raise AuthError("Could not decode Cursor access token JWT payload") from exc
    sub = payload.get("sub")
    if not sub:
        raise AuthError("Cursor access token JWT is missing sub claim")
    return str(sub)


def _session_cookie_value(raw_token: str) -> str:
    token = raw_token.strip()
    if not token:
        raise AuthError("Cursor session token is empty")
    if "::" in token or "%3A%3A" in token:
        return token.replace("%3A%3A", "::")
    return f"{_jwt_sub(token)}::{token}"


def resolve_session_token() -> str:
    """
    Resolve the Cursor WorkosCursorSessionToken cookie value.

    Priority:
    1. CURSOR_SESSION_TOKEN env var
    2. WorkosCursorSessionToken env var (cookie value)
    3. Cursor IDE local state database
    """
    for env_name in ("CURSOR_SESSION_TOKEN", "WorkosCursorSessionToken"):
        env_token = os.environ.get(env_name, "").strip()
        if env_token:
            return _session_cookie_value(env_token)

    db_token = _read_token_from_db(CURSOR_STATE_DB)
    if db_token:
        return _session_cookie_value(db_token)

    raise AuthError(
        "Could not resolve Cursor session token. "
        "Ensure Cursor is signed in, or set CURSOR_SESSION_TOKEN."
    )
