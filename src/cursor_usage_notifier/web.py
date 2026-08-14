"""Localhost web dashboard for Cursor usage history."""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .history import current_month_key, list_months, month_usage_payload

STATIC_DIR = Path(__file__).resolve().parent / "static"
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class DashboardHandler(BaseHTTPRequestHandler):
    history_path: Path = Path()

    def log_message(self, fmt: str, *args) -> None:
        if args and len(args) > 1 and str(args[1]).startswith("5"):
            super().log_message(fmt, *args)

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(
        self,
        body: bytes,
        *,
        content_type: str,
        status: int = 200,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            index = STATIC_DIR / "index.html"
            if not index.is_file():
                self._send_json({"error": "index.html missing"}, status=500)
                return
            self._send_bytes(
                index.read_bytes(),
                content_type="text/html; charset=utf-8",
            )
            return

        if path == "/api/months":
            months = list_months(self.history_path)
            default = current_month_key()
            if default not in months:
                months = [default, *months]
            self._send_json({"months": months, "default": default})
            return

        if path == "/api/usage":
            qs = parse_qs(parsed.query)
            month = (qs.get("month") or [current_month_key()])[0]
            if not MONTH_RE.match(month):
                self._send_json({"error": "month must be YYYY-MM"}, status=400)
                return
            try:
                payload = month_usage_payload(self.history_path, month)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(payload)
            return

        self._send_json({"error": "not found"}, status=404)


def run_server(*, host: str, port: int, history_path: Path) -> None:
    class BoundHandler(DashboardHandler):
        pass

    BoundHandler.history_path = history_path
    server = ThreadingHTTPServer((host, port), BoundHandler)
    print(f"Cursor usage dashboard: http://{host}:{port}")
    print(f"history db: {history_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        server.server_close()
