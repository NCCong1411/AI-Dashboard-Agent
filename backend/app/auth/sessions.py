"""Opaque server-side session token primitives."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(ttl_seconds: int, *, now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + timedelta(seconds=ttl_seconds)
