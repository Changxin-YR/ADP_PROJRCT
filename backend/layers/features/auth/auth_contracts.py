from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol


class AuthServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400, *, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.data = data


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "phone": user.get("phone"),
        "login_name": user.get("login_name"),
        "name": user.get("name"),
        "status": user["status"],
        "roles": user.get("roles", []),
        "data_scopes": user.get("data_scopes", []),
        "permissions": list(user.get("permissions") or []),
    }


class AuthStore(Protocol):
    def get_user_by_identifier(self, identifier: str) -> dict[str, Any] | None: ...
    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None: ...
    def record_failed_login(self, user_id: int, *, threshold: int, lock_minutes: int) -> bool: ...
    def reset_failed_login(self, user_id: int) -> None: ...
    def consume_rate_limit(self, limit_type: str, subject_key: str, *, limit: int, window_seconds: int) -> bool: ...
    def create_session(self, user_id: int, *, token_hash: str, ip: str, user_agent: str, expires_at: datetime, max_sessions: int = 2) -> int: ...
    def get_session(self, token_hash: str) -> dict[str, Any] | None: ...
    def touch_session(self, session_id: int, when: datetime) -> None: ...
    def revoke_session(self, session_id: int, reason: str) -> None: ...
    def change_password(self, user_id: int, *, password_hash: str, activate: bool) -> None: ...
    def audit_event(self, **event: Any) -> None: ...


def next_path(status: str) -> str:
    return {
        "pending": "/auth/pending", "rejected": "/auth/rejected",
        "must_change_password": "/auth/first-password", "active": "/workbench",
    }.get(status, "/auth/login")


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
