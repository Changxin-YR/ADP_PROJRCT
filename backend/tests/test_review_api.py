from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.features.account_review.review_service import ReviewService, ReviewServiceError
from test_auth_api import FakeAuthStore


class FakeReviewStore(FakeAuthStore):
    def __init__(self) -> None:
        super().__init__()
        self.admin_ids: set[int] = set()
        self.user_roles: dict[int, list[int]] = {}
        self.user_scopes: dict[int, list[int]] = {}

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def list_applications(self, status: str | None = None, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        items = [a for a in self.applications if status is None or a["status"] == status]
        return {"items": items[(page - 1) * page_size: page * page_size], "page": page, "page_size": page_size, "total": len(items), "has_next": page * page_size < len(items)}

    def approve_application(self, application_id: int, *, reviewer_id: int, role_ids: list[int], scope_ids: list[int]) -> dict[str, Any]:
        application = next(a for a in self.applications if a["id"] == application_id)
        application["status"] = "approved"
        application["reviewed_by"] = reviewer_id
        user = self.get_user_by_id(application["user_id"])
        assert user is not None
        user["status"] = "active"
        self.user_roles[user["id"]] = role_ids
        self.user_scopes[user["id"]] = scope_ids
        return application

    def reject_application(self, application_id: int, *, reviewer_id: int, reason: str) -> dict[str, Any]:
        application = next(a for a in self.applications if a["id"] == application_id)
        application["status"] = "rejected"
        application["rejection_reason"] = reason
        application["reviewed_by"] = reviewer_id
        user = self.get_user_by_id(application["user_id"])
        assert user is not None
        user["status"] = "rejected"
        return application

    def create_managed_user(self, payload: dict[str, Any], *, password_hash: str) -> dict[str, Any]:
        user = self.add_user(
            phone=payload["phone"],
            login_name=payload.get("login_name"),
            password="ignored",
            status="must_change_password",
        )
        user["name"] = payload["name"]
        user["password_hash"] = password_hash
        self.user_roles[user["id"]] = [int(item) for item in payload["role_ids"]]
        self.user_scopes[user["id"]] = [int(item) for item in payload["scope_ids"]]
        return user

    def list_users(self, status: str | None = None, keyword: str | None = None, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        items = [u for u in self.users if (status is None or u["status"] == status) and (not keyword or keyword in u["name"] or keyword in u["phone"])]
        return {"items": items[(page - 1) * page_size: page * page_size], "page": page, "page_size": page_size, "total": len(items), "has_next": page * page_size < len(items)}

    def set_user_status(self, user_id: int, status: str, *, operator_id: int | None = None) -> None:
        del operator_id
        user = self.get_user_by_id(user_id)
        assert user is not None
        user["status"] = status

    def reset_password(self, user_id: int, *, password_hash: str, operator_id: int | None = None) -> None:
        del operator_id
        user = self.get_user_by_id(user_id)
        assert user is not None
        user["password_hash"] = password_hash
        if user["status"] in {"active", "must_change_password"}:
            user["status"] = "must_change_password"
        for session in self.sessions.values():
            if session["user_id"] == user_id:
                session["status"] = "revoked"


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


def _login(client, identifier: str, password: str) -> None:
    csrf = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200


def _grant_super_admin(store: FakeReviewStore, user: dict[str, Any], *permissions: str) -> None:
    user["permissions"] = list(permissions)
    user["roles"] = [{"id": 1, "code": "super_admin", "name": "超级管理员"}]
    store.admin_ids.add(user["id"])


def _seed_application(store: FakeReviewStore) -> tuple[int, int, int]:
    applicant = store.add_user(phone="13800000020", login_name=None, password="Applicant9!", status="pending")
    store.applications.append(
        {
            "id": 1,
            "user_id": applicant["id"],
            "version_no": 1,
            "status": "pending",
            "name": applicant["name"],
            "application_note": "申请审核",
        }
    )
    store.next_application_id = 2
    return applicant["id"], 7, 9


def test_non_admin_cannot_read_application_list() -> None:
    store = FakeReviewStore()
    applicant_id, _, _ = _seed_application(store)
    client = create_app(_settings(), store=store).test_client()
    _login(client, "13800000020", "Applicant9!")

    response = client.get("/api/v1/admin/applications")

    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"


def test_non_admin_cannot_access_any_admin_endpoint() -> None:
    store = FakeReviewStore()
    applicant_id, _, _ = _seed_application(store)
    client = create_app(_settings(), store=store).test_client()
    _login(client, "13800000020", "Applicant9!")

    endpoints = [
        ("GET", "/api/v1/admin/applications", None),
        ("GET", "/api/v1/admin/users", None),
        ("POST", "/api/v1/admin/applications/1/approve", {"role_ids": [3], "data_scopes": [{"type": "area", "id": 1}]}),
        ("POST", "/api/v1/admin/applications/1/reject", {"reason": "无权限测试"}),
        ("PATCH", "/api/v1/admin/applications/1/review", {"decision": "reject", "reject_reason": "无权限测试"}),
        ("POST", "/api/v1/admin/users", {"phone": "13800000099", "name": "越权测试", "temporary_password": "TempPass9!", "role_ids": [3], "data_scopes": [{"type": "area", "id": 1}]}),
        ("PATCH", f"/api/v1/admin/users/{applicant_id}/status", {"status": "disabled"}),
        ("POST", f"/api/v1/admin/users/{applicant_id}/reset-password", {"temporary_password": "TempPass9!"}),
        ("POST", f"/api/v1/admin/users/{applicant_id}/password-reset", {"temporary_password": "TempPass9!"}),
    ]

    for method, path, payload in endpoints:
        headers = {}
        if method != "GET":
            headers["X-CSRF-Token"] = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
        response = client.open(path, method=method, json=payload, headers=headers)
        assert response.status_code == 403, (method, path, response.get_data(as_text=True))
        assert response.get_json()["code"] == "FORBIDDEN"


def test_review_permission_does_not_grant_user_management_api() -> None:
    store = FakeReviewStore()
    _seed_application(store)
    reviewer = store.add_user(phone="13800000029", login_name="reviewer", password="AdminPass9!", status="active")
    _grant_super_admin(store, reviewer, "auth.review")
    client = create_app(_settings(), store=store).test_client()
    _login(client, "reviewer", "AdminPass9!")

    assert client.get("/api/v1/admin/applications").status_code == 200
    forbidden = client.get("/api/v1/admin/users")
    assert forbidden.status_code == 403
    assert forbidden.get_json()["code"] == "FORBIDDEN"


def test_approve_writes_active_role_scope_and_application_status() -> None:
    store = FakeReviewStore()
    applicant_id, role_id, scope_id = _seed_application(store)
    admin = store.add_user(phone="13800000021", login_name="admin", password="AdminPass9!", status="active")
    _grant_super_admin(store, admin, "auth.review")
    client = create_app(_settings(), store=store).test_client()
    _login(client, "admin", "AdminPass9!")
    csrf = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]

    response = client.patch(
        "/api/v1/admin/applications/1/review",
        json={"role_ids": [role_id], "data_scopes": [{"type": "area", "id": scope_id}], "decision": "approve"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert store.get_user_by_id(applicant_id)["status"] == "active"
    assert store.user_roles[applicant_id] == [role_id]
    assert store.user_scopes[applicant_id] == [scope_id]
    assert store.applications[0]["status"] == "approved"


def test_admin_application_list_has_items_and_pagination() -> None:
    store = FakeReviewStore()
    _seed_application(store)
    admin = store.add_user(phone="13800000025", login_name="admin4", password="AdminPass9!", status="active")
    _grant_super_admin(store, admin, "auth.review")
    client = create_app(_settings(), store=store).test_client()
    _login(client, "admin4", "AdminPass9!")
    response = client.get("/api/v1/admin/applications?status=pending&page=1&page_size=10")
    data = response.get_json()["data"]
    assert response.status_code == 200
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert "applications" not in data


def test_admin_user_list_and_canonical_create_payload() -> None:
    store = FakeReviewStore()
    admin = store.add_user(phone="13800000026", login_name="admin5", password="AdminPass9!", status="active")
    _grant_super_admin(store, admin, "auth.user.manage")
    client = create_app(_settings(), store=store).test_client()
    _login(client, "admin5", "AdminPass9!")
    csrf = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    created = client.post("/api/v1/admin/users", json={"phone": "13800000027", "name": "新建用户", "temporary_password": "TempPass9!", "role_ids": [3], "data_scopes": [{"type": "area", "id": 1}]}, headers={"X-CSRF-Token": csrf})
    assert created.status_code == 200
    listed = client.get("/api/v1/admin/users")
    assert listed.status_code == 200
    assert any(item["phone"] == "13800000027" for item in listed.get_json()["data"]["items"])


def test_reject_requires_reason() -> None:
    store = FakeReviewStore()
    _seed_application(store)
    admin = store.add_user(phone="13800000022", login_name="admin2", password="AdminPass9!", status="active")
    _grant_super_admin(store, admin, "auth.review")
    client = create_app(_settings(), store=store).test_client()
    _login(client, "admin2", "AdminPass9!")
    csrf = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]

    response = client.post(
        "/api/v1/admin/applications/1/reject",
        json={"reason": ""},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "REJECTION_REASON_REQUIRED"


def test_reset_password_revokes_sessions_and_requires_first_change() -> None:
    store = FakeReviewStore()
    user = store.add_user(phone="13800000023", login_name="worker", password="WorkerPass9!", status="active")
    admin = store.add_user(phone="13800000024", login_name="admin3", password="AdminPass9!", status="active")
    _grant_super_admin(store, admin, "auth.user.manage")
    client = create_app(_settings(), store=store).test_client()
    _login(client, "admin3", "AdminPass9!")
    csrf = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]

    response = client.post(
        f"/api/v1/admin/users/{user['id']}/reset-password",
        json={"temporary_password": "TempPass9!"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert store.get_user_by_id(user["id"])["status"] == "must_change_password"
    assert all(item["status"] == "revoked" for item in store.sessions.values() if item["user_id"] == user["id"])
    assert "TempPass9!" not in response.get_data(as_text=True)


def test_admin_cannot_disable_or_enable_own_account() -> None:
    store = FakeReviewStore()
    admin = store.add_user(phone="13800000030", login_name="self-admin", password="AdminPass9!", status="active")
    _grant_super_admin(store, admin, "auth.user.manage")
    service = ReviewService(store, _settings())

    with pytest.raises(ReviewServiceError, match="当前登录账号") as caught:
        service.set_status(admin["id"], admin["id"], "disabled")
    assert caught.value.code == "SELF_STATUS_FORBIDDEN"


def test_admin_status_and_password_audit_keep_operator_identity() -> None:
    from backend.layers.common.db.repositories.auth_admin_store import AuthAdminStoreMixin

    class Audit:
        def __init__(self) -> None:
            self.events: list[dict[str, Any]] = []

        def write(self, _connection: object, **event: Any) -> None:
            self.events.append(event)

    class Review:
        @staticmethod
        def set_user_status(_connection: object, **_kwargs: Any) -> None:
            return None

        @staticmethod
        def reset_password(_connection: object, **_kwargs: Any) -> None:
            return None

        @staticmethod
        def create_user(_connection: object, **_kwargs: Any) -> dict[str, Any]:
            return {"id": 9, "status": "must_change_password"}

    class Store(AuthAdminStoreMixin):
        def __init__(self) -> None:
            self.audit = Audit()
            self.review = Review()

        def transaction(self):
            from contextlib import contextmanager

            @contextmanager
            def context():
                yield object()

            return context()

    store = Store()
    store.set_user_status(3, "disabled", operator_id=7)
    store.reset_password(3, password_hash="hash", operator_id=7)
    store.create_managed_user(
        {"phone": "13800000099", "name": "审计用户", "role_ids": [3], "scope_ids": [1], "assigned_by": 7},
        password_hash="hash",
    )
    assert [event["user_id"] for event in store.audit.events] == [7, 7, 7]
    assert store.audit.events[-1]["action"] == "create_managed_user"


def test_disabled_data_scope_cannot_be_granted() -> None:
    from backend.layers.common.db.repositories.review_repository import ReviewRepository

    class Cursor:
        def execute(self, _sql: str, _params: tuple[int, ...]) -> None:
            return None

        @staticmethod
        def fetchone() -> dict[str, int]:
            return {"total": 0}

    with pytest.raises(ValueError, match="数据范围不存在或已停用"):
        ReviewRepository._validate_grant_ids(Cursor(), role_ids=[], scope_ids=[99])
