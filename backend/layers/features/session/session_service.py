from __future__ import annotations

from typing import Any

from backend.layers.features.auth.auth_service import AuthService


class SessionService:
    def __init__(self, auth_service: AuthService) -> None:
        self.auth_service = auth_service

    def current_user(self, session_token: str | None) -> dict[str, Any]:
        return self.auth_service.current_user(session_token)

    def logout(self, session_token: str | None) -> None:
        self.auth_service.logout(session_token)
