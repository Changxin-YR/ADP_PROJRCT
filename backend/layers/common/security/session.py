from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone


class SessionExpiredError(ValueError):
    code = "SESSION_EXPIRED"

    def __init__(self, message: str = "会话已过期，请重新登录") -> None:
        super().__init__(message)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def validate_session_activity(
    last_active_at: datetime,
    *,
    now: datetime | None = None,
    timeout_minutes: int = 30,
) -> None:
    current = _as_utc(now or datetime.now(timezone.utc))
    if current - _as_utc(last_active_at) > timedelta(minutes=timeout_minutes):
        raise SessionExpiredError()
