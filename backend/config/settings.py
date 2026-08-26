from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import Mapping


class ConfigError(ValueError):
    """配置不满足当前运行环境时抛出。"""


def _as_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError("SESSION_COOKIE_SECURE 必须是 true/false")


def _as_positive_int(name: str, value: str | None, *, default: int) -> int:
    try:
        parsed = int(value or default)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是正整数") from exc
    if parsed < 1:
        raise ConfigError(f"{name} 必须是正整数")
    return parsed


def _as_non_negative_int(name: str, value: str | None, *, default: int) -> int:
    try:
        parsed = int(value if value is not None else default)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是非负整数") from exc
    if parsed < 0:
        raise ConfigError(f"{name} 必须是非负整数")
    return parsed


def _as_scanner_argv(value: str | None) -> tuple[str, ...]:
    if not value or not value.strip():
        return ()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ConfigError("ATTACHMENT_SCANNER_ARGV_JSON 必须是 JSON 参数数组") from exc
    if not isinstance(parsed, list) or not parsed or any(not isinstance(item, str) or not item for item in parsed):
        raise ConfigError("ATTACHMENT_SCANNER_ARGV_JSON 必须是 JSON 参数数组")
    if sum(item.count("{path}") for item in parsed) != 1:
        raise ConfigError("ATTACHMENT_SCANNER_ARGV_JSON 必须且只能包含一个 {path} 占位符")
    return tuple(parsed)


def _as_exit_codes(value: str | None) -> tuple[int, ...]:
    raw_items = (value or "2").split(",")
    try:
        codes = tuple(dict.fromkeys(int(item.strip()) for item in raw_items))
    except ValueError as exc:
        raise ConfigError("ATTACHMENT_SCANNER_THREAT_EXIT_CODES 必须是非零正整数列表") from exc
    if not codes or any(code <= 0 for code in codes):
        raise ConfigError("ATTACHMENT_SCANNER_THREAT_EXIT_CODES 必须是非零正整数列表")
    return codes


@dataclass(frozen=True)
class Settings:
    app_env: str
    flask_secret_key: str
    csrf_secret_key: str
    mysql_host: str
    mysql_port: int
    mysql_database: str
    mysql_user: str
    mysql_password: str
    session_cookie_secure: bool
    attachment_root: str = "backend/private/attachments"
    trusted_proxy_hops: int = 0
    session_idle_timeout_minutes: int = 30
    login_lock_threshold: int = 5
    login_lock_minutes: int = 15
    login_ip_limit: int = 30
    login_ip_window_seconds: int = 600
    session_default_limit: int = 2
    session_super_admin_limit: int = 1
    session_field_worker_limit: int = 3
    session_pending_limit: int = 1
    attachment_scanner_argv: tuple[str, ...] = ()
    attachment_scanner_timeout_seconds: int = 30
    attachment_scanner_threat_exit_codes: tuple[int, ...] = (2,)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if env is None else env
        app_env = values.get("APP_ENV", "development").strip().lower()
        if app_env not in {"development", "test", "production"}:
            raise ConfigError("APP_ENV 只能是 development、test 或 production")

        flask_secret_key = values.get("FLASK_SECRET_KEY", "").strip()
        csrf_secret_key = values.get("CSRF_SECRET_KEY", "").strip()
        if app_env == "production" and (not flask_secret_key or not csrf_secret_key):
            raise ConfigError("生产环境必须配置 FLASK_SECRET_KEY 和 CSRF_SECRET_KEY")
        if not flask_secret_key:
            flask_secret_key = "development-only-flask-secret"
        if not csrf_secret_key:
            csrf_secret_key = "development-only-csrf-secret"

        try:
            mysql_port = int(values.get("MYSQL_PORT", "3306"))
        except ValueError as exc:
            raise ConfigError("MYSQL_PORT 必须是数字") from exc
        if not 1 <= mysql_port <= 65535:
            raise ConfigError("MYSQL_PORT 超出范围")

        required = {
            "MYSQL_HOST": values.get("MYSQL_HOST", "127.0.0.1"),
            "MYSQL_DATABASE": values.get("MYSQL_DATABASE", "adp_auth"),
            "MYSQL_USER": values.get("MYSQL_USER", "adp_dev"),
            "MYSQL_PASSWORD": values.get("MYSQL_PASSWORD", ""),
        }
        if app_env == "production" and any(not item.strip() for item in required.values()):
            raise ConfigError("生产环境必须配置完整的 MySQL 连接信息")

        session_idle_timeout_minutes = _as_positive_int("SESSION_IDLE_TIMEOUT_MINUTES", values.get("SESSION_IDLE_TIMEOUT_MINUTES"), default=30)
        login_lock_threshold = _as_positive_int("LOGIN_LOCK_THRESHOLD", values.get("LOGIN_LOCK_THRESHOLD"), default=5)
        login_lock_minutes = _as_positive_int("LOGIN_LOCK_MINUTES", values.get("LOGIN_LOCK_MINUTES"), default=15)
        login_ip_limit = _as_positive_int("LOGIN_IP_LIMIT", values.get("LOGIN_IP_LIMIT"), default=30)
        login_ip_window_seconds = _as_positive_int("LOGIN_IP_WINDOW_SECONDS", values.get("LOGIN_IP_WINDOW_SECONDS"), default=600)
        session_default_limit = _as_positive_int("SESSION_DEFAULT_LIMIT", values.get("SESSION_DEFAULT_LIMIT"), default=2)
        session_super_admin_limit = _as_positive_int("SESSION_SUPER_ADMIN_LIMIT", values.get("SESSION_SUPER_ADMIN_LIMIT"), default=1)
        session_field_worker_limit = _as_positive_int("SESSION_FIELD_WORKER_LIMIT", values.get("SESSION_FIELD_WORKER_LIMIT"), default=3)
        session_pending_limit = _as_positive_int("SESSION_PENDING_LIMIT", values.get("SESSION_PENDING_LIMIT"), default=1)
        session_cookie_secure = _as_bool(
            values.get("SESSION_COOKIE_SECURE"),
            default=app_env == "production",
        )
        if app_env == "production" and not session_cookie_secure:
            raise ConfigError("生产环境 SESSION_COOKIE_SECURE 必须为 true")

        return cls(
            app_env=app_env,
            flask_secret_key=flask_secret_key,
            csrf_secret_key=csrf_secret_key,
            mysql_host=required["MYSQL_HOST"].strip(),
            mysql_port=mysql_port,
            mysql_database=required["MYSQL_DATABASE"].strip(),
            mysql_user=required["MYSQL_USER"].strip(),
            mysql_password=required["MYSQL_PASSWORD"],
            session_cookie_secure=session_cookie_secure,
            attachment_root=values.get("ATTACHMENT_ROOT", "backend/private/attachments").strip() or "backend/private/attachments",
            trusted_proxy_hops=_as_non_negative_int(
                "TRUSTED_PROXY_HOPS",
                values.get("TRUSTED_PROXY_HOPS"),
                default=0,
            ),
            session_idle_timeout_minutes=session_idle_timeout_minutes,
            login_lock_threshold=login_lock_threshold,
            login_lock_minutes=login_lock_minutes,
            login_ip_limit=login_ip_limit,
            login_ip_window_seconds=login_ip_window_seconds,
            session_default_limit=session_default_limit,
            session_super_admin_limit=session_super_admin_limit,
            session_field_worker_limit=session_field_worker_limit,
            session_pending_limit=session_pending_limit,
            attachment_scanner_argv=_as_scanner_argv(values.get("ATTACHMENT_SCANNER_ARGV_JSON")),
            attachment_scanner_timeout_seconds=_as_positive_int(
                "ATTACHMENT_SCANNER_TIMEOUT_SECONDS",
                values.get("ATTACHMENT_SCANNER_TIMEOUT_SECONDS"),
                default=30,
            ),
            attachment_scanner_threat_exit_codes=_as_exit_codes(
                values.get("ATTACHMENT_SCANNER_THREAT_EXIT_CODES")
            ),
        )

    def session_limit_for_user(self, user: Mapping[str, object]) -> int:
        if user.get("status") == "pending":
            return self.session_pending_limit
        roles = user.get("roles") or []
        role_codes = {
            str(role.get("code")) if isinstance(role, Mapping) else str(role)
            for role in roles
        }
        if "super_admin" in role_codes:
            return self.session_super_admin_limit
        if role_codes.intersection({"field_worker", "farmer", "operator"}):
            return self.session_field_worker_limit
        return self.session_default_limit
