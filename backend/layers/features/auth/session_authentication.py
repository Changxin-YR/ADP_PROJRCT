from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from backend.layers.common.security.session import SessionExpiredError, hash_session_token, validate_session_activity
from backend.layers.features.auth.auth_contracts import AuthServiceError, public_user


class AuthSessionServiceMixin:
    def current_user(
        self,
        session_token: str | None,
        *,
        request_id: str | None = None,
        allow_password_change: bool = False,
    ) -> dict[str, Any]:
        user, _ = self.current_session(session_token, request_id=request_id)
        if user.get("status") == "must_change_password" and not allow_password_change:
            raise AuthServiceError("PASSWORD_CHANGE_REQUIRED", "首次登录必须修改密码后才能访问业务功能", 403)
        return user

    def current_session(
        self, session_token: str | None, *, request_id: str | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not session_token:
            raise AuthServiceError("UNAUTHENTICATED", "请先登录", 401)
        token_hash = hash_session_token(session_token)
        session_transaction = getattr(self.store, "session_transaction", None)
        if callable(session_transaction):
            with session_transaction(token_hash) as (session, touch):
                return self._validate_current_session(session, request_id=request_id, touch=touch)
        session = self.store.get_session(token_hash)
        return self._validate_current_session(
            session,
            request_id=request_id,
            touch=lambda when: self.store.touch_session(int(session["id"]), when) if session else None,
        )

    def _validate_current_session(
        self,
        session: dict[str, Any] | None,
        *,
        request_id: str | None,
        touch: Callable[[datetime], None],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if session is None:
            raise AuthServiceError("UNAUTHENTICATED", "请先登录", 401)
        if session.get("status") != "active":
            reason = session.get("revoke_reason")
            if reason == "session_replaced":
                raise AuthServiceError("SESSION_REPLACED", "当前会话已在其他设备登录", 401)
            if reason in {"idle_timeout", "expired"}:
                raise AuthServiceError("SESSION_EXPIRED", "会话已过期，请重新登录", 401)
            raise AuthServiceError("UNAUTHENTICATED", "请先登录", 401)
        try:
            validate_session_activity(
                session["last_active_at"], timeout_minutes=self.settings.session_idle_timeout_minutes
            )
        except SessionExpiredError as exc:
            self._revoke_current_session(session, "idle_timeout", request_id)
            raise AuthServiceError(exc.code, str(exc), 401) from exc
        if self._utc(session["expires_at"]) <= datetime.now(timezone.utc):
            self._revoke_current_session(session, "expired", request_id)
            raise AuthServiceError("SESSION_EXPIRED", "会话已过期，请重新登录", 401)
        user = session.get("user") or self.store.get_user_by_id(session["user_id"])
        if not user:
            raise AuthServiceError("UNAUTHENTICATED", "请先登录", 401)
        if user.get("status") == "retired":
            self._revoke_current_session(session, "account_retired", request_id, user_id=int(user["id"]))
            raise AuthServiceError("ACCOUNT_RETIRED", "账号已注销，当前会话已失效", 401)
        touch(datetime.now(timezone.utc))
        return public_user(user), session

    def _revoke_current_session(
        self,
        session: dict[str, Any],
        reason: str,
        request_id: str | None,
        *,
        user_id: int | None = None,
    ) -> None:
        self.store.revoke_session(session["id"], reason)
        self._audit(
            action="session_revoke",
            result="success",
            user_id=user_id or session.get("user_id"),
            object_type="session",
            object_id=session.get("id"),
            object_ref=f"session:{session.get('id')}",
            request_id=request_id,
            reason=reason,
        )
