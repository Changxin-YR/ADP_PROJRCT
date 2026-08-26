from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from flask import request

from backend.config.settings import ConfigError, Settings
from backend.layers.common.http.response import fail, ok
from backend.layers.common.security.csrf import CsrfError, validate_csrf_token
from backend.layers.common.security.password import hash_password, verify_password
from backend.layers.common.security.session import SessionExpiredError, validate_session_activity
from backend.layers.common.validation.auth_validation import ValidationError, validate_name, validate_password, validate_phone
from backend.app import create_app
from test_auth_api import FakeAuthStore


def test_validate_phone_returns_mainland_phone_without_separators() -> None:
    assert validate_phone("+86 138-0000-0000") == "13800000000"


def test_weak_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_password("12345678", "12345678")


def test_one_character_name_is_rejected_by_design_contract() -> None:
    with pytest.raises(ValidationError, match="姓名长度必须为 2-40 个字符"):
        validate_name("李")


def test_password_hash_uses_one_way_scrypt_verification() -> None:
    password = "FarmPass9!"
    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password_hash, password) is True
    assert verify_password(password_hash, "WrongPass9!") is False
    assert password_hash.startswith("scrypt:")


def test_breed_worker_uses_field_worker_session_limit() -> None:
    settings = Settings.from_env({"SESSION_DEFAULT_LIMIT": "2", "SESSION_FIELD_WORKER_LIMIT": "3"})
    assert settings.session_limit_for_user({"status": "active", "roles": [{"code": "breed_worker"}]}) == 3


def test_unified_response_contains_contract_fields() -> None:
    success = ok(data={"status": "pending"}, message="已提交")
    error = fail(code="VALIDATION_ERROR", message="字段有误", status=400)

    assert set(("code", "message", "data", "request_id")).issubset(success)
    assert set(("code", "message", "data", "request_id")).issubset(error)
    assert success["code"] == "OK"
    assert error["code"] == "VALIDATION_ERROR"
    assert success["request_id"]
    assert error["request_id"]


@pytest.mark.parametrize("provided", [None, "wrong-token"])
def test_missing_or_wrong_csrf_token_is_rejected(provided: str | None) -> None:
    with pytest.raises(CsrfError) as error:
        validate_csrf_token(provided, "expected-token")

    assert error.value.code == "CSRF_INVALID"


def test_expired_session_is_rejected() -> None:
    last_active_at = datetime.now(timezone.utc) - timedelta(minutes=31)

    with pytest.raises(SessionExpiredError) as error:
        validate_session_activity(last_active_at, now=datetime.now(timezone.utc))

    assert error.value.code == "SESSION_EXPIRED"


def test_production_configuration_rejects_empty_secrets() -> None:
    env = {
        "APP_ENV": "production",
        "FLASK_SECRET_KEY": "",
        "CSRF_SECRET_KEY": "",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "adp_auth",
        "MYSQL_USER": "adp_app",
        "MYSQL_PASSWORD": "db-password-from-secret-store",
    }

    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_production_configuration_rejects_insecure_session_cookie() -> None:
    env = {
        "APP_ENV": "production",
        "FLASK_SECRET_KEY": "production-flask-secret",
        "CSRF_SECRET_KEY": "production-csrf-secret",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "adp_auth",
        "MYSQL_USER": "adp_app",
        "MYSQL_PASSWORD": "db-password-from-secret-store",
        "SESSION_COOKIE_SECURE": "false",
    }

    with pytest.raises(ConfigError, match="SESSION_COOKIE_SECURE"):
        Settings.from_env(env)


def test_security_headers_include_cross_origin_isolation_headers() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "test",
            "FLASK_SECRET_KEY": "test-flask-secret",
            "CSRF_SECRET_KEY": "test-csrf-secret",
            "MYSQL_HOST": "127.0.0.1",
            "MYSQL_DATABASE": "adp_test",
            "MYSQL_USER": "adp_test",
            "MYSQL_PASSWORD": "test-password",
            "SESSION_COOKIE_SECURE": "false",
        }
    )
    response = create_app(settings, store=FakeAuthStore()).test_client().get("/api/v1/auth/csrf")

    expected = {
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "Cross-Origin-Opener-Policy",
        "Cross-Origin-Resource-Policy",
    }
    assert expected.issubset(set(response.headers.keys()))


def _proxy_settings(hops: str | None = None) -> Settings:
    env = {
        "APP_ENV": "test",
        "FLASK_SECRET_KEY": "test-flask-secret",
        "CSRF_SECRET_KEY": "test-csrf-secret",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_DATABASE": "adp_test",
        "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test-password",
        "SESSION_COOKIE_SECURE": "false",
    }
    if hops is not None:
        env["TRUSTED_PROXY_HOPS"] = hops
    return Settings.from_env(env)


def test_forwarded_headers_are_ignored_without_a_trusted_proxy() -> None:
    settings = _proxy_settings()
    app = create_app(settings, store=FakeAuthStore())

    @app.get("/_test/client-ip")
    def client_ip() -> str:
        return request.remote_addr or ""

    response = app.test_client().get(
        "/_test/client-ip",
        headers={"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https"},
    )

    assert settings.trusted_proxy_hops == 0
    assert response.get_data(as_text=True) == "127.0.0.1"


def test_forwarded_headers_are_used_for_one_configured_proxy_hop() -> None:
    app = create_app(_proxy_settings("1"), store=FakeAuthStore())

    @app.get("/_test/client-ip")
    def client_ip() -> str:
        return f"{request.remote_addr}|{request.scheme}"

    response = app.test_client().get(
        "/_test/client-ip",
        headers={"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https"},
    )

    assert response.get_data(as_text=True) == "203.0.113.7|https"


def test_trusted_proxy_hops_rejects_negative_values() -> None:
    with pytest.raises(ConfigError, match="TRUSTED_PROXY_HOPS"):
        _proxy_settings("-1")


def test_unexpected_errors_are_logged_with_the_response_request_id(caplog) -> None:
    app = create_app(_proxy_settings(), store=FakeAuthStore())

    @app.get("/_test/unexpected")
    def unexpected() -> str:
        raise RuntimeError("database detail that must not leak")

    with caplog.at_level("ERROR"):
        response = app.test_client().get("/_test/unexpected")

    payload = response.get_json()
    assert response.status_code == 500
    assert payload["request_id"] in caplog.text
    assert "database detail that must not leak" not in response.get_data(as_text=True)
