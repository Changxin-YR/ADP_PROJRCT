from __future__ import annotations

from typing import Any

from backend.app import create_app
from test_auth_api import FakeAuthStore, _csrf, _settings


class FakeAuditStore(FakeAuthStore):
    def __init__(self) -> None:
        super().__init__()
        self.admin_ids: set[int] = set()
        self.last_audit_query: dict[str, Any] = {}

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def list_audit_logs(self, **kwargs: Any) -> dict[str, Any]:
        self.last_audit_query = kwargs
        return {
            "items": [{"id": 1, "user_id": kwargs.get("user_id"), "actor_name": "管理员", "action": "login", "action_code": "login", "module_code": "auth", "object_type": "session", "object_id": 1, "object_ref": "session:1", "result": "success", "request_id": "req-1", "created_at": "2026-08-16 10:00:00"}],
            "page": kwargs["page"],
            "page_size": kwargs["page_size"],
            "total": 1,
            "has_next": False,
        }


def test_audit_log_endpoint_requires_permission_and_returns_server_rows() -> None:
    store = FakeAuditStore()
    admin = store.add_user(phone="13800000951", login_name="audit-admin", password="AdminPass9!", status="active")
    admin["permissions"] = ["audit.view"]
    admin["roles"] = [{"id": 1, "code": "super_admin", "name": "超级管理员"}]
    store.admin_ids.add(admin["id"])
    client = create_app(_settings(), store=store).test_client()
    login = client.post("/api/v1/auth/login", json={"identifier": "audit-admin", "password": "AdminPass9!"}, headers={"X-CSRF-Token": _csrf(client)})
    assert login.status_code == 200

    response = client.get("/api/v1/admin/audit-logs?page=1&page_size=10&action_code=login")

    assert response.status_code == 200
    assert response.get_json()["data"]["items"][0]["request_id"] == "req-1"
    assert response.get_json()["data"]["page_size"] == 10

    filtered = client.get("/api/v1/admin/audit-logs?page=2&page_size=25&created_from=2026-08-01&created_to=2026-08-20")
    assert filtered.status_code == 200
    assert store.last_audit_query["created_from"].isoformat() == "2026-08-01"
    assert store.last_audit_query["created_to"].isoformat() == "2026-08-21"
    assert store.last_audit_query["page"] == 2


def test_audit_log_endpoint_rejects_non_super_admin_even_with_permission() -> None:
    store = FakeAuditStore()
    manager = store.add_user(phone="13800000952", login_name="area-manager", password="AdminPass9!", status="active")
    manager["permissions"] = ["audit.view"]
    manager["roles"] = [{"id": 2, "code": "breed_manager", "name": "养殖管理员"}]
    store.admin_ids.add(manager["id"])
    client = create_app(_settings(), store=store).test_client()
    login = client.post("/api/v1/auth/login", json={"identifier": "area-manager", "password": "AdminPass9!"}, headers={"X-CSRF-Token": _csrf(client)})
    assert login.status_code == 200

    response = client.get("/api/v1/admin/audit-logs")

    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"
