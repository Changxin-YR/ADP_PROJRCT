from __future__ import annotations

from typing import Any

from backend.config.settings import Settings
from backend.layers.features.account_review.review_service import ReviewService, ReviewServiceError
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError
from test_auth_api import FakeAuthStore


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


class AuditedAuthStore(FakeAuthStore):
    def __init__(self) -> None:
        super().__init__()
        self.audit_events: list[dict[str, Any]] = []

    def audit_event(self, **event: Any) -> None:
        self.audit_events.append(event)


class RetirementReviewStore:
    def __init__(self) -> None:
        self.users = {2: {"id": 2, "name": "待注销账号", "status": "active"}}
        self.retirements: list[dict[str, Any]] = []

    def is_admin(self, user_id: int) -> bool:
        return user_id == 1

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        return self.users.get(user_id)

    def retire_managed_user(self, user_id: int, *, operator_id: int, reason: str) -> dict[str, Any]:
        user = self.users[user_id]
        user["status"] = "retired"
        self.retirements.append({"user_id": user_id, "operator_id": operator_id, "reason": reason})
        return dict(user)


def test_retired_account_cannot_login_and_is_audited() -> None:
    store = AuditedAuthStore()
    store.add_user(phone="13800000901", login_name="retired", password="Correct9!", status="retired")
    service = AuthService(store, _settings())

    try:
        service.login("retired", "Correct9!", ip="127.0.0.1", user_agent="pytest", request_id="req-retired")
    except AuthServiceError as error:
        assert error.code == "ACCOUNT_RETIRED"
        assert error.status == 403
    else:
        raise AssertionError("retired account must not log in")

    assert store.audit_events[-1]["action"] == "login"
    assert store.audit_events[-1]["result"] == "failure"
    assert store.audit_events[-1]["request_id"] == "req-retired"


def test_auth_security_events_cover_login_logout_and_password_change() -> None:
    store = AuditedAuthStore()
    user = store.add_user(phone="13800000902", login_name="audited", password="Correct9!", status="active")
    service = AuthService(store, _settings())

    result = service.login("audited", "Correct9!", ip="127.0.0.1", user_agent="pytest", request_id="req-login")
    service.logout(result["session_token"], request_id="req-logout")
    service.change_password(
        user["id"],
        "Correct9!",
        "NewPass9!",
        "hashed-new-password",
        current_user=user,
        request_id="req-password",
    )

    assert [event["action"] for event in store.audit_events] == ["login", "logout", "password_change"]
    assert [event["request_id"] for event in store.audit_events] == ["req-login", "req-logout", "req-password"]
    assert all("password" not in str(event).lower() or event.get("action") == "password_change" for event in store.audit_events)


def test_retire_requires_reason_and_preserves_account_reference() -> None:
    store = RetirementReviewStore()
    service = ReviewService(store, _settings())

    try:
        service.retire_user(1, 2, reason="")
    except ReviewServiceError as error:
        assert error.code == "RETIRE_REASON_REQUIRED"
    else:
        raise AssertionError("retirement must require a reason")

    retired = service.retire_user(1, 2, reason="员工离职")
    assert retired["status"] == "retired"
    assert store.get_user_by_id(2) is not None
    assert store.retirements == [{"user_id": 2, "operator_id": 1, "reason": "员工离职"}]
