from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError
from fake_auth_store import FakeAuthStore


def _settings(**overrides: str) -> Settings:
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
    env.update(overrides)
    return Settings.from_env(env)


def _csrf(client) -> str:
    response = client.get("/api/v1/auth/csrf")
    return response.get_json()["data"]["csrf_token"]


def test_wrong_password_has_unified_error_without_account_disclosure() -> None:
    store = FakeAuthStore()
    store.add_user(phone="13800000000", login_name="operator", password="Correct9!", status="active")
    client = create_app(_settings(), store=store).test_client()
    token = _csrf(client)

    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "13800000000", "password": "Wrong9!"},
        headers={"X-CSRF-Token": token},
    )

    body = response.get_json()
    assert response.status_code == 401
    assert body["code"] == "AUTH_INVALID_CREDENTIALS"
    assert "手机号" not in body["message"]
    assert body["request_id"]


def test_login_ip_rate_limit_returns_retry_after() -> None:
    store = FakeAuthStore()
    client = create_app(_settings(), store=store).test_client()
    token = _csrf(client)

    for _ in range(30):
        response = client.post(
            "/api/v1/auth/login",
            json={"identifier": "unknown", "password": "Wrong9!"},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 401

    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "unknown", "password": "Wrong9!"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 429
    assert response.get_json()["code"] == "RATE_LIMITED"
    assert response.headers["Retry-After"] == "600"


def test_fifth_wrong_password_locks_account_for_fifteen_minutes() -> None:
    store = FakeAuthStore()
    store.add_user(phone="13800000001", login_name=None, password="Correct9!", status="active")
    client = create_app(_settings(), store=store).test_client()

    for _ in range(5):
        token = _csrf(client)
        response = client.post(
            "/api/v1/auth/login",
            json={"identifier": "13800000001", "password": "Wrong9!"},
            headers={"X-CSRF-Token": token},
        )
    assert response.status_code == 423
    assert response.get_json()["code"] == "AUTH_LOCKED"
    assert store.users[0]["locked_until"] > datetime.now(timezone.utc) + timedelta(minutes=14)

    token = _csrf(client)
    locked = client.post(
        "/api/v1/auth/login",
        json={"identifier": "13800000001", "password": "Correct9!"},
        headers={"X-CSRF-Token": token},
    )
    assert locked.get_json()["code"] == "AUTH_LOCKED"


def test_lock_expiry_starts_a_new_failed_password_window() -> None:
    store = FakeAuthStore()
    user = store.add_user(phone="13800000011", login_name="expired-lock", password="Correct9!", status="active")
    user["failed_login_count"] = 5
    user["locked_until"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    client = create_app(_settings(), store=store).test_client()

    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "expired-lock", "password": "Wrong9!"},
        headers={"X-CSRF-Token": _csrf(client)},
    )

    assert response.status_code == 401
    assert response.get_json()["code"] == "AUTH_INVALID_CREDENTIALS"
    assert store.get_user_by_id(user["id"])["failed_login_count"] == 1
    assert store.get_user_by_id(user["id"])["locked_until"] is None


def test_must_change_password_session_cannot_use_current_user_without_override() -> None:
    store = FakeAuthStore()
    user = store.add_user(phone="13800000012", login_name="must-change-service", password="TempPass9!", status="must_change_password")
    service = AuthService(store, _settings())
    login = service.login("must-change-service", "TempPass9!", ip="127.0.0.1", user_agent="pytest")

    with pytest.raises(AuthServiceError, match="首次登录必须修改密码") as caught:
        service.current_user(login["session_token"])
    assert caught.value.code == "PASSWORD_CHANGE_REQUIRED"
    assert service.current_user(login["session_token"], allow_password_change=True)["id"] == user["id"]


def test_disabled_account_cannot_login() -> None:
    store = FakeAuthStore()
    store.add_user(phone="13800000002", login_name=None, password="Correct9!", status="disabled")
    client = create_app(_settings(), store=store).test_client()
    token = _csrf(client)

    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "13800000002", "password": "Correct9!"},
        headers={"X-CSRF-Token": token},
    )

    assert response.get_json()["code"] == "ACCOUNT_DISABLED"


def test_register_creates_pending_user_and_restricted_session() -> None:
    store = FakeAuthStore()
    client = create_app(_settings(), store=store).test_client()
    token = _csrf(client)

    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "新申请人",
            "phone": "138-0000-0003",
            "password": "FarmPass9!",
            "confirm_password": "FarmPass9!",
            "desired_role_id": 1,
            "area_id": 1,
            "application_note": "申请加入 A 区",
        },
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 201
    assert response.get_json()["data"]["status"] == "pending"
    assert store.users[0]["status"] == "pending"
    assert len(store.applications) == 1


def test_missing_csrf_token_is_rejected_before_login() -> None:
    store = FakeAuthStore()
    store.add_user(phone="13800000004", login_name=None, password="Correct9!", status="active")
    client = create_app(_settings(), store=store).test_client()

    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "13800000004", "password": "Correct9!"},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "CSRF_INVALID"


def test_login_and_me_expose_session_expiry() -> None:
    store = FakeAuthStore()
    store.add_user(phone="13800000005", login_name=None, password="Correct9!", status="active")
    client = create_app(_settings(), store=store).test_client()
    token = _csrf(client)
    login_response = client.post("/api/v1/auth/login", json={"identifier": "13800000005", "password": "Correct9!"}, headers={"X-CSRF-Token": token})
    assert login_response.status_code == 200
    assert login_response.get_json()["data"]["session"]["expires_at"]
    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.get_json()["data"]["session"]["expires_at"]


def test_mobile_login_returns_bearer_token_only_for_mobile_client() -> None:
    store = FakeAuthStore()
    store.add_user(phone="13800000010", login_name=None, password="Correct9!", status="active")
    client = create_app(_settings(), store=store).test_client()

    web_csrf = _csrf(client)
    web_login = client.post("/api/v1/auth/login", json={"identifier": "13800000010", "password": "Correct9!"}, headers={"X-CSRF-Token": web_csrf})
    assert web_login.status_code == 200
    assert "token" not in web_login.get_json()["data"]["session"]

    mobile_csrf = _csrf(client)
    mobile_login = client.post("/api/v1/auth/login", json={"identifier": "13800000010", "password": "Correct9!"}, headers={"X-CSRF-Token": mobile_csrf, "X-ADP-Client": "mobile"})
    assert mobile_login.status_code == 200
    assert mobile_login.get_json()["data"]["session"]["token"]


def test_me_exposes_permission_codes() -> None:
    store = FakeAuthStore()
    user = store.add_user(phone="13800000109", login_name="permission-user", password="Permission9!", status="active")
    user["permissions"] = ["workbench.enter", "cost.view"]
    client = create_app(_settings(), store=store).test_client()
    token = _csrf(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "permission-user", "password": "Permission9!"},
        headers={"X-CSRF-Token": token},
    )
    assert login.status_code == 200

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["permissions"] == ["workbench.enter", "cost.view"]


def test_registration_rate_limit_returns_retry_after() -> None:
    store = FakeAuthStore()
    client = create_app(_settings(), store=store).test_client()
    payload = {"name": "限流测试", "password": "FarmPass9!", "confirm_password": "FarmPass9!", "desired_role_id": 3, "area_id": 1, "application_note": ""}
    for index in range(5):
        token = _csrf(client)
        response = client.post("/api/v1/auth/register", json={**payload, "phone": f"1390000000{index}"}, headers={"X-CSRF-Token": token})
        assert response.status_code == 201
    token = _csrf(client)
    response = client.post("/api/v1/auth/register", json={**payload, "phone": "13900000009"}, headers={"X-CSRF-Token": token})
    assert response.status_code == 429
    assert response.get_json()["code"] == "RATE_LIMITED"
    assert response.headers["Retry-After"] == "3600"


def test_four_logins_keep_only_configured_number_of_sessions_and_replace_oldest() -> None:
    store = FakeAuthStore()
    store.add_user(phone="13800000006", login_name="multi-device", password="Correct9!", status="active")
    clients = [create_app(_settings(), store=store).test_client() for _ in range(4)]

    for client in clients:
        token = _csrf(client)
        response = client.post(
            "/api/v1/auth/login",
            json={"identifier": "multi-device", "password": "Correct9!"},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 200

    sessions = sorted(store.sessions.values(), key=lambda item: item["id"])
    active = [item for item in sessions if item["status"] == "active"]
    assert len(active) == 2
    assert sessions[0]["status"] == "revoked"
    assert sessions[0]["revoke_reason"] == "session_replaced"
    replaced = clients[0].get("/api/v1/auth/me")
    assert replaced.status_code == 401
    assert replaced.get_json()["code"] == "SESSION_REPLACED"


def test_password_change_rejects_reusing_current_password() -> None:
    store = FakeAuthStore()
    store.add_user(phone="13800000007", login_name="must-change", password="TempPass9!", status="must_change_password")
    client = create_app(_settings(), store=store).test_client()
    csrf = _csrf(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "must-change", "password": "TempPass9!"},
        headers={"X-CSRF-Token": csrf},
    )
    assert login.status_code == 200

    csrf = _csrf(client)
    response = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "TempPass9!", "new_password": "TempPass9!", "confirm_password": "TempPass9!"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "PASSWORD_REUSE"
    assert store.get_user_by_id(1)["status"] == "must_change_password"


def test_lock_response_includes_remaining_seconds_and_retry_after_header() -> None:
    store = FakeAuthStore()
    store.add_user(phone="13800000008", login_name=None, password="Correct9!", status="active")
    client = create_app(_settings(), store=store).test_client()

    for _ in range(5):
        token = _csrf(client)
        response = client.post(
            "/api/v1/auth/login",
            json={"identifier": "13800000008", "password": "Wrong9!"},
            headers={"X-CSRF-Token": token},
        )

    assert response.status_code == 423
    body = response.get_json()
    assert body["data"]["retry_after"] > 0
    assert int(response.headers["Retry-After"]) == body["data"]["retry_after"]


def test_session_timeout_uses_configured_idle_timeout() -> None:
    store = FakeAuthStore()
    store.add_user(phone="13800000009", login_name=None, password="Correct9!", status="active")
    client = create_app(_settings(SESSION_IDLE_TIMEOUT_MINUTES="1"), store=store).test_client()
    token = _csrf(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "13800000009", "password": "Correct9!"},
        headers={"X-CSRF-Token": token},
    )
    assert login.status_code == 200
    session = next(iter(store.sessions.values()))
    session["last_active_at"] = datetime.now(timezone.utc) - timedelta(minutes=2)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.get_json()["code"] == "SESSION_EXPIRED"
