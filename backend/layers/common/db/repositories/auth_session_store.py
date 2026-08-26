from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator


class AuthSessionStoreMixin:
    def create_session(
        self,
        user_id: int,
        *,
        token_hash: str,
        ip: str,
        user_agent: str,
        expires_at: datetime,
        max_sessions: int = 2,
    ) -> int:
        with self.transaction() as connection:
            self.sessions.revoke_oldest_excess(connection, user_id=user_id, max_sessions=max_sessions)
            return self.sessions.create(
                connection,
                user_id=user_id,
                session_token_hash=token_hash,
                ip_address=ip,
                user_agent=user_agent,
                last_active_at=datetime.now(timezone.utc),
                expires_at=expires_at,
            )

    def get_session(self, token_hash: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            return self._session_with_user(connection, token_hash)

    def _session_with_user(self, connection: Any, token_hash: str) -> dict[str, Any] | None:
        session = self.sessions.find_by_token(connection, session_token_hash=token_hash)
        if session is None:
            return None
        user = {
            "id": int(session["user_id"]),
            "phone": session.get("phone"),
            "login_name": session.get("login_name"),
            "name": session.get("name"),
            "status": session.get("user_status"),
        }
        roles, data_scopes, permissions = self.users.permissions(connection, user_id=user["id"])
        return {
            **session,
            "user": {
                **user,
                "roles": roles,
                "data_scopes": data_scopes,
                "permissions": permissions,
            },
        }

    @contextmanager
    def session_transaction(self, token_hash: str) -> Iterator[tuple[dict[str, Any] | None, Any]]:
        with self.transaction() as connection:
            session = self._session_with_user(connection, token_hash)

            def touch(when: datetime) -> None:
                if session is not None:
                    self.sessions.touch(connection, session_id=int(session["id"]), last_active_at=when)

            yield session, touch

    def touch_session(self, session_id: int, when: datetime) -> None:
        with self.transaction() as connection:
            self.sessions.touch(connection, session_id=session_id, last_active_at=when)

    def revoke_session(self, session_id: int, reason: str) -> None:
        with self.transaction() as connection:
            self.sessions.revoke(connection, session_id=session_id, reason=reason)
