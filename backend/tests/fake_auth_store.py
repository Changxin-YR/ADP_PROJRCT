from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from werkzeug.security import generate_password_hash


class FakeAuthStore:
    def __init__(self) -> None:
        self.users: list[dict[str, Any]] = []
        self.sessions: dict[str, dict[str, Any]] = {}
        self.applications: list[dict[str, Any]] = []
        self.rate_limits: dict[tuple[str, str], int] = {}
        self.next_user_id = 1
        self.next_session_id = 1
        self.next_application_id = 1

    def add_user(self, *, phone: str, login_name: str | None, password: str, status: str) -> dict[str, Any]:
        user = {
            "id": self.next_user_id, "phone": phone, "login_name": login_name,
            "name": "测试用户", "password_hash": generate_password_hash(password, method="scrypt"),
            "status": status, "failed_login_count": 0, "locked_until": None, "permissions": [],
        }
        self.next_user_id += 1
        self.users.append(user)
        return user

    def get_user_by_identifier(self, identifier: str) -> dict[str, Any] | None:
        return next((user for user in self.users if identifier in {user["phone"], user["login_name"]}), None)

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        return next((user for user in self.users if user["id"] == user_id), None)

    def record_failed_login(self, user_id: int, *, threshold: int, lock_minutes: int) -> bool:
        user = self.get_user_by_id(user_id)
        assert user is not None
        user["failed_login_count"] += 1
        if user["failed_login_count"] >= threshold:
            user["locked_until"] = datetime.now(timezone.utc) + timedelta(minutes=lock_minutes)
            return True
        return False

    def reset_failed_login(self, user_id: int) -> None:
        user = self.get_user_by_id(user_id)
        assert user is not None
        user["failed_login_count"] = 0
        user["locked_until"] = None

    def create_session(self, user_id: int, *, token_hash: str, ip: str, user_agent: str, expires_at: datetime, max_sessions: int = 2) -> int:
        active = sorted((item for item in self.sessions.values() if item["user_id"] == user_id and item["status"] == "active"), key=lambda item: item["id"])
        for item in active[:max(0, len(active) - max(1, max_sessions) + 1)]:
            item["status"] = "revoked"
            item["revoke_reason"] = "session_replaced"
        session_id = self.next_session_id
        self.next_session_id += 1
        self.sessions[token_hash] = {
            "id": session_id, "user_id": user_id, "status": "active",
            "last_active_at": datetime.now(timezone.utc), "expires_at": expires_at,
            "ip_address": ip, "user_agent": user_agent,
        }
        return session_id

    def get_session(self, token_hash: str) -> dict[str, Any] | None:
        session = self.sessions.get(token_hash)
        return {**session, "user": self.get_user_by_id(session["user_id"])} if session else None

    def touch_session(self, session_id: int, when: datetime) -> None:
        for session in self.sessions.values():
            if session["id"] == session_id:
                session["last_active_at"] = when

    def revoke_session(self, session_id: int, reason: str) -> None:
        for session in self.sessions.values():
            if session["id"] == session_id:
                session["status"] = "revoked"
                session["revoke_reason"] = reason

    def consume_rate_limit(self, limit_type: str, subject_key: str, *, limit: int, window_seconds: int) -> bool:
        del window_seconds
        key = (limit_type, subject_key)
        self.rate_limits[key] = self.rate_limits.get(key, 0) + 1
        return self.rate_limits[key] <= limit

    def register_pending(self, payload: dict[str, Any], *, password_hash: str) -> dict[str, Any]:
        user = self.add_user(phone=payload["phone"], login_name=None, password="ignored", status="pending")
        user["password_hash"] = password_hash
        application = {
            "id": self.next_application_id, "user_id": user["id"], "version_no": 1,
            "status": "pending", "name": payload["name"],
            "application_note": payload.get("application_note", ""),
        }
        self.next_application_id += 1
        self.applications.append(application)
        return {"user": user, "application": application}

    def get_application(self, user_id: int) -> dict[str, Any] | None:
        return next((item for item in reversed(self.applications) if item["user_id"] == user_id), None)

    def change_password(self, user_id: int, *, password_hash: str, activate: bool) -> None:
        user = self.get_user_by_id(user_id)
        assert user is not None
        user["password_hash"] = password_hash
        if activate and user["status"] == "must_change_password":
            user["status"] = "active"

