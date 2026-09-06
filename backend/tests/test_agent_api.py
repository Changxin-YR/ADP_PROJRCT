from __future__ import annotations

from typing import Any

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.common.security.session import hash_session_token
from fake_auth_store import FakeAuthStore


def _settings() -> Settings:
    return Settings.from_env(
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


class FakeAgentGateway:
    def __init__(self) -> None:
        self.turn_calls: list[dict[str, Any]] = []
        self.confirm_calls: list[dict[str, Any]] = []

    def run_turn(self, user: dict[str, Any], message: str, *, conversation_id: str, request_id: str) -> dict[str, Any]:
        self.turn_calls.append(
            {
                "user": user,
                "message": message,
                "conversation_id": conversation_id,
                "request_id": request_id,
            }
        )
        return {"kind": "success", "data": {"message": message}, "request_id": request_id}

    def confirm(self, user: dict[str, Any], token: str, *, request_id: str) -> dict[str, Any]:
        self.confirm_calls.append({"user": user, "token": token, "request_id": request_id})
        return {"kind": "success", "data": {"confirmed": True}, "request_id": request_id}


def _csrf(client: Any) -> str:
    return client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]


def _logged_in_client(gateway: FakeAgentGateway) -> tuple[Any, FakeAuthStore, dict[str, Any]]:
    store = FakeAuthStore()
    user = store.add_user(phone="13800000101", login_name="agent-user", password="Correct9!", status="active")
    user["permissions"] = ["master_data.view", "master_data.manage"]
    client = create_app(_settings(), store=store, agent_gateway=gateway).test_client()
    csrf = _csrf(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "agent-user", "password": "Correct9!"},
        headers={"X-CSRF-Token": csrf},
    )
    assert login.status_code == 200
    return client, store, {"csrf": _csrf(client), "user": user}


def test_agent_turn_requires_login() -> None:
    gateway = FakeAgentGateway()
    client = create_app(_settings(), store=FakeAuthStore(), agent_gateway=gateway).test_client()

    response = client.post("/api/v1/agent/turn", json={"message": "查询塘口"})

    assert response.status_code == 401
    assert response.get_json()["code"] == "UNAUTHENTICATED"


def test_agent_turn_requires_csrf_after_login() -> None:
    gateway = FakeAgentGateway()
    client, _, _ = _logged_in_client(gateway)

    response = client.post("/api/v1/agent/turn", json={"message": "查询塘口"})

    assert response.status_code == 403
    assert response.get_json()["code"] == "CSRF_INVALID"


def test_agent_turn_forwards_current_user_and_message() -> None:
    gateway = FakeAgentGateway()
    client, _, state = _logged_in_client(gateway)

    response = client.post(
        "/api/v1/agent/turn",
        json={"message": "  查询塘口  ", "conversation_id": "conversation-1"},
        headers={"X-CSRF-Token": state["csrf"]},
    )

    assert response.status_code == 200
    assert response.get_json()["code"] == "OK"
    call = gateway.turn_calls[0]
    assert call["user"]["id"] == state["user"]["id"]
    assert call["message"] == "查询塘口"
    assert call["conversation_id"] == "conversation-1"
    assert call["request_id"] == response.get_json()["request_id"]
    assert call["user"]["_session_hash"] == hash_session_token(client.get_cookie("adp_session").value)


def test_agent_turn_rejects_blank_message() -> None:
    gateway = FakeAgentGateway()
    client, _, state = _logged_in_client(gateway)

    response = client.post(
        "/api/v1/agent/turn",
        json={"message": "   "},
        headers={"X-CSRF-Token": state["csrf"]},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "VALIDATION_ERROR"
    assert gateway.turn_calls == []


def test_agent_confirm_requires_csrf_and_forwards_token() -> None:
    gateway = FakeAgentGateway()
    client, _, state = _logged_in_client(gateway)

    missing_csrf = client.post("/api/v1/agent/confirm", json={"token": "confirmation-token"})
    assert missing_csrf.status_code == 403
    assert missing_csrf.get_json()["code"] == "CSRF_INVALID"

    response = client.post(
        "/api/v1/agent/confirm",
        json={"token": "confirmation-token"},
        headers={"X-CSRF-Token": state["csrf"]},
    )

    assert response.status_code == 200
    assert gateway.confirm_calls[0]["user"]["id"] == state["user"]["id"]
    assert gateway.confirm_calls[0]["token"] == "confirmation-token"


def test_agent_turn_is_unavailable_until_runner_is_connected() -> None:
    store = FakeAuthStore()
    user = store.add_user(phone="13800000102", login_name="agent-no-runner", password="Correct9!", status="active")
    user["permissions"] = ["master_data.view"]
    client = create_app(_settings(), store=store).test_client()
    csrf = _csrf(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "agent-no-runner", "password": "Correct9!"},
        headers={"X-CSRF-Token": csrf},
    )
    assert login.status_code == 200

    response = client.post(
        "/api/v1/agent/turn",
        json={"message": "查询塘口"},
        headers={"X-CSRF-Token": _csrf(client)},
    )

    assert response.status_code == 503
    assert response.get_json()["code"] == "AGENT_UNAVAILABLE"
