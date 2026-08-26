from __future__ import annotations

import json

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.common.audit.audit_logger import AuditLogger
from test_auth_api import FakeAuthStore


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.connection.query = query
        self.connection.params = params


class FakeConnection:
    query: str = ""
    params: tuple[object, ...] = ()

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def test_audit_writer_records_context_and_redacts_sensitive_values() -> None:
    connection = FakeConnection()

    AuditLogger().write(
        connection,
        user_id=7,
        action="update_draft",
        object_type="cost_entry",
        object_id=11,
        result="success",
        ip_address="127.0.0.1",
        request_id="r1",
        module_code="cost",
        action_code="draft.update",
        before={"amount": "10.00", "password": "secret", "current_password": "old-secret"},
        after={"amount": "12.00", "token": "secret-token", "refresh_token": "refresh-secret", "api_key": "key-secret"},
    )

    assert "request_id" in connection.query
    assert len(connection.params) >= 7
    detail = " ".join(str(value) for value in connection.params)
    assert "secret" not in detail
    assert "secret-token" not in detail
    assert "old-secret" not in detail
    assert "refresh-secret" not in detail
    assert "key-secret" not in detail
    assert "r1" in connection.params
    assert '"amount": "12.00"' in detail


def test_audit_writer_preserves_legacy_detail_json_calls() -> None:
    connection = FakeConnection()

    AuditLogger().write(
        connection,
        user_id=3,
        action="legacy_action",
        object_type="legacy_object",
        object_id=9,
        result="success",
        ip_address=None,
        detail_json=json.dumps({"reason": "legacy"}),
    )

    assert connection.params[1] == "legacy_action"
    assert connection.params[5] == '{"reason": "legacy"}'


def test_request_id_is_reused_in_response_and_header() -> None:
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
    app = create_app(settings, store=FakeAuthStore())

    @app.get("/_test/request-id")
    def request_id() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    response = app.test_client().get("/_test/request-id", headers={"X-Request-ID": "request-123"})

    assert response.headers["X-Request-ID"] == "request-123"
