#!/usr/bin/env python3
"""Serve the portfolio and store contact submissions locally in SQLite."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
EMAIL_RE = __import__("re").compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_LENGTH = {"name": 200, "email": 320, "subject": 300, "message": 5000}


def validate_contact(value: Any) -> tuple[dict[str, str], dict[str, str]]:
    errors: dict[str, str] = {}
    data: dict[str, str] = {}
    if not isinstance(value, dict):
        return {"body": "JSON object required"}, data
    for field, maximum in MAX_LENGTH.items():
        raw = value.get(field)
        text = raw.strip() if isinstance(raw, str) else ""
        if not text:
            errors[field] = f"{field} is required"
        elif len(text) > maximum:
            errors[field] = f"{field} exceeds {maximum} characters"
        else:
            data[field] = text
    if data.get("email") and not EMAIL_RE.fullmatch(data["email"]):
        errors["email"] = "email is not a valid address"
    return errors, data


class ContactStore:
    def __init__(self, path: Path, retention_days: int = 90) -> None:
        self.path = path
        self.retention_days = max(1, retention_days)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY,
                received_at TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL
            )
            """
        )
        return conn

    def add(self, data: dict[str, str]) -> str:
        submission_id = str(uuid.uuid4())
        now = int(time.time())
        received_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        expires_at = now + self.retention_days * 86400
        with self._connect() as conn:
            conn.execute("DELETE FROM submissions WHERE expires_at < ?", (now,))
            conn.execute(
                """
                INSERT INTO submissions
                    (id, received_at, expires_at, name, email, subject, message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission_id,
                    received_at,
                    expires_at,
                    data["name"],
                    data["email"],
                    data["subject"],
                    data["message"],
                ),
            )
        return submission_id


class RateLimiter:
    def __init__(self, limit: int = 5, window_seconds: int = 600) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        cutoff = time.monotonic() - self.window_seconds
        with self.lock:
            events = self.events[key]
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(time.monotonic())
            return True


class PortfolioHandler(SimpleHTTPRequestHandler):
    store: ContactStore
    limiter = RateLimiter()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        super().end_headers()

    def _json(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        try:
            return urlsplit(origin).netloc.casefold() == self.headers.get("Host", "").casefold()
        except ValueError:
            return False

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/contact-config.js":
            payload = b'window.PORTFOLIO_CONTACT_ENDPOINT = "/api/contact";\n'
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/contact":
            self._json(HTTPStatus.NOT_FOUND, {"success": False, "error": "not found"})
            return
        if not self._same_origin():
            self._json(HTTPStatus.FORBIDDEN, {"success": False, "error": "origin rejected"})
            return
        client = self.client_address[0]
        if not self.limiter.allow(client):
            self._json(
                HTTPStatus.TOO_MANY_REQUESTS,
                {"success": False, "error": "too many submissions"},
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 16 * 1024:
            self._json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"success": False, "error": "invalid request size"},
            )
            return
        try:
            body = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"success": False, "error": "invalid JSON"},
            )
            return
        errors, data = validate_contact(body)
        if errors:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"success": False, "error": "validation failed", "fields": errors},
            )
            return
        submission_id = self.store.add(data)
        self._json(
            HTTPStatus.OK,
            {
                "success": True,
                "message": "Thanks - your message has been received.",
                "submissionId": submission_id,
            },
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("PORTFOLIO_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PORTFOLIO_PORT", "8080"))
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.environ.get("CONTACT_DB_PATH", "runtime/contacts.db")),
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=int(os.environ.get("CONTACT_RETENTION_DAYS", "90")),
    )
    args = parser.parse_args()

    PortfolioHandler.store = ContactStore(args.database, args.retention_days)
    server = ThreadingHTTPServer((args.host, args.port), PortfolioHandler)
    print(f"Portfolio: http://{args.host}:{args.port}")
    print(f"Contact database: {args.database}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
