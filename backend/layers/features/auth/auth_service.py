from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any

from backend.config.settings import Settings
from backend.layers.common.security.password import verify_password
from backend.layers.common.security.session import hash_session_token, new_session_token
from backend.layers.features.auth.auth_contracts import AuthServiceError, AuthStore, next_path, public_user, utc
from backend.layers.features.auth.session_authentication import AuthSessionServiceMixin


class AuthService(AuthSessionServiceMixin):
    next_path = staticmethod(next_path)
    _utc = staticmethod(utc)
    def __init__(self, store: AuthStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    def login(self, identifier: str, password: str, *, ip: str, user_agent: str, request_id: str | None = None) -> dict[str, Any]:
        """登录主流程：限流 -> 定位账号 -> 状态检查 -> 密码校验 -> 建立会话。"""
        self._enforce_login_rate_limit(ip, request_id)
        user = self.store.get_user_by_identifier(identifier.strip())
        if user is None:
            self._audit_login_denied(ip=ip, request_id=request_id, reason="invalid_credentials")
            raise AuthServiceError("AUTH_INVALID_CREDENTIALS", "登录标识或密码错误", 401)
        self._reject_inactive_account(user, ip, request_id)
        self._verify_password_or_lock(user, password, ip, request_id)
        return self._open_login_session(user, ip, user_agent, request_id)

    def _enforce_login_rate_limit(self, ip: str, request_id: str | None) -> None:
        if self.store.consume_rate_limit(
            "login_ip",
            ip,
            limit=self.settings.login_ip_limit,
            window_seconds=self.settings.login_ip_window_seconds,
        ):
            return
        self._audit_login_denied(ip=ip, request_id=request_id, reason="rate_limited")
        raise AuthServiceError(
            "RATE_LIMITED",
            "登录请求过于频繁，请稍后再试",
            429,
            data={"retry_after": self.settings.login_ip_window_seconds},
        )

    def _reject_inactive_account(self, user: dict[str, Any], ip: str, request_id: str | None) -> None:
        """拒绝锁定、停用和已注销账号；通过时不做任何事。"""
        locked_until = user.get("locked_until")
        if locked_until:
            now = datetime.now(timezone.utc)
            if self._utc(locked_until) > now:
                self._audit_login_denied(user=user, ip=ip, request_id=request_id, reason="account_locked")
                raise self._locked_error(locked_until)
            # Expired locks start a fresh failure window instead of inheriting the threshold count.
            self.store.reset_failed_login(user["id"])
        if user["status"] == "disabled":
            self._audit_login_denied(user=user, ip=ip, request_id=request_id, reason="account_disabled")
            raise AuthServiceError("ACCOUNT_DISABLED", "账号当前不可登录", 403)
        if user["status"] == "retired":
            self._audit_login_denied(user=user, ip=ip, request_id=request_id, reason="account_retired")
            raise AuthServiceError("ACCOUNT_RETIRED", "账号已注销，禁止登录", 403)

    def _verify_password_or_lock(self, user: dict[str, Any], password: str, ip: str, request_id: str | None) -> None:
        """校验密码；失败时累加失败次数并在达到阈值后锁定。"""
        if verify_password(user.get("password_hash", ""), password):
            return
        locked = self.store.record_failed_login(
            user["id"],
            threshold=self.settings.login_lock_threshold,
            lock_minutes=self.settings.login_lock_minutes,
        )
        if locked:
            updated_user = self.store.get_user_by_id(user["id"]) or user
            self._audit_login_denied(user=updated_user, ip=ip, request_id=request_id, reason="invalid_credentials_account_locked")
            raise self._locked_error(updated_user.get("locked_until"))
        self._audit_login_denied(user=user, ip=ip, request_id=request_id, reason="invalid_credentials")
        raise AuthServiceError("AUTH_INVALID_CREDENTIALS", "登录标识或密码错误", 401)

    def _open_login_session(self, user: dict[str, Any], ip: str, user_agent: str, request_id: str | None) -> dict[str, Any]:
        """创建会话并返回公开用户信息与会话凭证。"""
        self.store.reset_failed_login(user["id"])
        token = new_session_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
        session_id = self.store.create_session(
            user["id"],
            token_hash=hash_session_token(token),
            ip=ip,
            user_agent=user_agent[:255],
            expires_at=expires_at,
            max_sessions=self.settings.session_limit_for_user(user),
        )
        self._audit(
            action="login",
            result="success",
            user_id=user["id"],
            object_type="session",
            object_id=session_id,
            object_ref=f"session:{session_id}",
            ip_address=ip,
            request_id=request_id,
            after={"user_id": user["id"], "session_id": session_id, "expires_at": expires_at},
        )
        return {
            "user": public_user(user),
            "session_token": token,
            "expires_at": expires_at,
            "next_path": self.next_path(user["status"]),
        }

    def _audit_login_denied(self, *, ip: str, request_id: str | None, reason: str, user: dict[str, Any] | None = None) -> None:
        """统一登录失败审计：未定位账号记 auth 域，已定位账号记 user 域。"""
        if user is None:
            self._audit(action="login", result="failure", object_type="auth", object_ref="login", ip_address=ip, request_id=request_id, reason=reason)
            return
        self._audit(
            action="login",
            result="failure",
            user_id=user["id"],
            object_type="user",
            object_id=user["id"],
            object_ref=f"user:{user['id']}",
            ip_address=ip,
            request_id=request_id,
            reason=reason,
        )

    def logout(self, session_token: str | None, *, request_id: str | None = None, ip: str | None = None) -> None:
        if session_token:
            session = self.store.get_session(hash_session_token(session_token))
            if session:
                self.store.revoke_session(session["id"], "logout")
                self._audit(
                    action="logout",
                    result="success",
                    user_id=session.get("user_id"),
                    object_type="session",
                    object_id=session.get("id"),
                    object_ref=f"session:{session.get('id')}",
                    ip_address=ip,
                    request_id=request_id,
                    reason="user_logout",
                )
                return
        self._audit(action="logout", result="failure", object_type="auth", object_ref="logout", ip_address=ip, request_id=request_id, reason="session_not_found")

    def change_password(
        self,
        user_id: int,
        current_password: str | None,
        new_password: str,
        new_password_hash: str,
        *,
        current_user: dict[str, Any],
        request_id: str | None = None,
        ip: str | None = None,
    ) -> None:
        stored = self.store.get_user_by_id(user_id)
        if not stored:
            self._audit(action="password_change", result="failure", user_id=user_id, object_type="user", object_id=user_id, object_ref=f"user:{user_id}", ip_address=ip, request_id=request_id, reason="user_not_found")
            raise AuthServiceError("UNAUTHENTICATED", "请先登录", 401)
        if not verify_password(stored.get("password_hash", ""), current_password or ""):
            self._audit(action="password_change", result="failure", user_id=user_id, object_type="user", object_id=user_id, object_ref=f"user:{user_id}", ip_address=ip, request_id=request_id, reason="current_password_invalid")
            raise AuthServiceError("AUTH_INVALID_CREDENTIALS", "当前密码错误", 401)
        if verify_password(stored.get("password_hash", ""), new_password):
            self._audit(action="password_change", result="failure", user_id=user_id, object_type="user", object_id=user_id, object_ref=f"user:{user_id}", ip_address=ip, request_id=request_id, reason="password_reuse")
            raise AuthServiceError("PASSWORD_REUSE", "新密码不能与当前密码相同", 400)
        self.store.change_password(user_id, password_hash=new_password_hash, activate=True)
        self._audit(
            action="password_change",
            result="success",
            user_id=user_id,
            object_type="user",
            object_id=user_id,
            object_ref=f"user:{user_id}",
            ip_address=ip,
            request_id=request_id,
            reason="user_change_password",
            before={"status": stored.get("status")},
            after={"status": "active" if stored.get("status") == "must_change_password" else stored.get("status")},
        )

    def _audit(self, **event: Any) -> None:
        writer = getattr(self.store, "audit_event", None)
        if callable(writer):
            writer(**event)

    def _locked_error(self, locked_until: datetime | None) -> AuthServiceError:
        remaining = 1
        if locked_until:
            remaining = max(1, ceil((self._utc(locked_until) - datetime.now(timezone.utc)).total_seconds()))
        return AuthServiceError(
            "AUTH_LOCKED",
            f"账号暂时锁定，还需约 {remaining} 秒后重试",
            423,
            data={"retry_after": remaining},
        )
