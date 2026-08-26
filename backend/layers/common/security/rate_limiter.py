from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


class RateLimitError(ValueError):
    code = "RATE_LIMITED"

    def __init__(self, message: str = "请求过于频繁，请稍后再试") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    request_count: int
    blocked_until: datetime | None


def check_window(
    *,
    request_count: int,
    limit: int,
    window_started_at: datetime,
    now: datetime | None = None,
    window_seconds: int,
) -> RateLimitDecision:
    current = now or datetime.now(timezone.utc)
    if current - window_started_at >= timedelta(seconds=window_seconds):
        return RateLimitDecision(True, 1, None)
    next_count = request_count + 1
    if next_count > limit:
        return RateLimitDecision(False, request_count, window_started_at + timedelta(seconds=window_seconds))
    return RateLimitDecision(True, next_count, None)


def enforce(decision: RateLimitDecision) -> None:
    if not decision.allowed:
        raise RateLimitError()
