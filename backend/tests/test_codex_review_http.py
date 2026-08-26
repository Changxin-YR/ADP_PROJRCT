from __future__ import annotations

from pathlib import Path

import pymysql
import pytest

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.http.request_helpers import json_object, pagination
from backend.tests.fake_auth_store import FakeAuthStore
from test_data_exchange import client as exchange_client


def _settings(tmp_path: Path) -> Settings:
    return Settings.from_env({
        "APP_ENV": "test",
        "FLASK_SECRET_KEY": "codex-http-test",
        "CSRF_SECRET_KEY": "codex-http-csrf",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_DATABASE": "adp_test",
        "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test",
        "SESSION_COOKIE_SECURE": "false",
        "ATTACHMENT_ROOT": str(tmp_path),
    })


def test_request_body_has_a_global_upper_bound(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path), store=FakeAuthStore())
    assert app.config["MAX_CONTENT_LENGTH"] == 21 * 1024 * 1024


def test_database_outage_is_service_unavailable_not_bad_input(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path), store=FakeAuthStore())
    with app.test_request_context("/api/v1/health"):
        response, status = app.handle_user_exception(
            pymysql.err.OperationalError(2003, "connection refused password=secret")
        )
    assert status == 503
    payload = response.get_json()
    assert payload["code"] == "DB_UNAVAILABLE"
    assert "secret" not in payload["message"]


def test_attachment_query_rejects_invalid_identifier_in_chinese(tmp_path: Path) -> None:
    response = exchange_client(tmp_path).get(
        "/api/v1/data-exchange/attachments?entity_type=cost:entry&entity_id=abc"
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "REQUEST_FIELD_INVALID"
    assert response.get_json()["message"] == "请求字段格式无效"


@pytest.mark.parametrize("payload", [[], "text", 3])
def test_json_request_body_must_be_an_object(payload: object) -> None:
    app = create_app(_settings(Path("attachments")), store=FakeAuthStore())
    with app.test_request_context("/", method="POST", json=payload):
        with pytest.raises(DomainError, match="REQUEST_BODY_INVALID"):
            json_object()


def test_explicit_json_null_is_not_treated_as_an_empty_object() -> None:
    app = create_app(_settings(Path("attachments")), store=FakeAuthStore())
    with app.test_request_context("/", method="POST", data="null", content_type="application/json"):
        with pytest.raises(DomainError, match="REQUEST_BODY_INVALID"):
            json_object()


def test_empty_request_body_remains_valid_for_action_endpoints() -> None:
    app = create_app(_settings(Path("attachments")), store=FakeAuthStore())
    with app.test_request_context("/", method="POST"):
        assert json_object() == {}


@pytest.mark.parametrize("query", ["page=nope&page_size=20", "page=0&page_size=20", "page=1&page_size=-1"])
def test_invalid_pagination_is_a_domain_error(query: str) -> None:
    app = create_app(_settings(Path("attachments")), store=FakeAuthStore())
    with app.test_request_context(f"/?{query}"):
        with pytest.raises(DomainError, match="PAGINATION_INVALID"):
            pagination()
