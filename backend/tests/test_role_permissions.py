from __future__ import annotations

from typing import Any

import pytest

from backend.layers.features.account_review.review_service import ReviewService, ReviewServiceError
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.mysql_store import MySqlAuthStore
from backend.tests.mysql_test_database import disposable_database, settings_for
from test_auth_api import _settings


class RoleStore:
    def __init__(self) -> None:
        self.roles = {
            1: {"id": 1, "code": "super_admin", "name": "超级管理员", "permission_codes": ["auth.user.manage", "workbench.enter"]},
            2: {"id": 2, "code": "breed_manager", "name": "养殖管理员", "permission_codes": ["production.view"]},
        }

    def is_admin(self, user_id: int) -> bool:
        return user_id == 7

    def list_roles_with_permissions(self) -> dict[str, Any]:
        return {"items": list(self.roles.values()), "available_permissions": [], "total": len(self.roles)}

    def replace_role_permissions(self, role_id: int, *, permission_codes: list[str], operator_id: int) -> dict[str, Any]:
        assert operator_id == 7
        role = self.roles[role_id]
        role["permission_codes"] = permission_codes
        return dict(role)

    def copy_role(self, source_role_id: int, *, code: str, name: str, description: str | None, operator_id: int) -> dict[str, Any]:
        assert operator_id == 7
        source = self.roles[source_role_id]
        copied = {"id": 3, "code": code, "name": name, "description": description, "permission_codes": list(source["permission_codes"])}
        self.roles[3] = copied
        return copied


def service() -> ReviewService:
    return ReviewService(RoleStore(), _settings())


def test_role_permission_change_requires_second_confirmation() -> None:
    with pytest.raises(ReviewServiceError, match="二次确认") as caught:
        service().update_role_permissions(7, 2, {"permission_codes": ["production.view"]})
    assert caught.value.code == "CONFIRM_REQUIRED"


def test_super_admin_must_keep_management_and_workbench_permissions() -> None:
    with pytest.raises(ReviewServiceError, match="超级管理员") as caught:
        service().update_role_permissions(7, 1, {"permission_codes": ["workbench.enter"], "confirm_phrase": "CONFIRM"})
    assert caught.value.code == "SUPER_ADMIN_PERMISSION_REQUIRED"


def test_role_permissions_are_replaced_as_a_final_set() -> None:
    result = service().update_role_permissions(
        7, 2, {"permission_codes": ["production.view", "work_item.view", "production.view"], "confirm_phrase": "CONFIRM"}
    )
    assert result["permission_codes"] == ["production.view", "work_item.view"]


def test_copy_role_reuses_source_permissions() -> None:
    result = service().copy_role(
        7, 2, {"code": "breed_reviewer", "name": "养殖复核员", "description": "负责养殖复核", "confirm_phrase": "CONFIRM"}
    )
    assert result["permission_codes"] == ["production.view"]


def test_role_definition_api_rejects_non_super_admin() -> None:
    from backend.app import create_app
    from backend.tests.test_review_api import FakeReviewStore, _login

    store = FakeReviewStore()
    manager = store.add_user(phone="13800000031", login_name="breed-manager", password="AdminPass9!", status="active")
    manager["permissions"] = ["auth.user.manage"]
    manager["roles"] = [{"id": 2, "code": "breed_manager", "name": "养殖管理员"}]
    store.admin_ids.add(manager["id"])
    client = create_app(_settings(), store=store).test_client()
    _login(client, "breed-manager", "AdminPass9!")

    response = client.get("/api/v1/admin/roles")

    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"


def test_user_management_api_rejects_non_super_admin_with_legacy_permission() -> None:
    from backend.app import create_app
    from backend.tests.test_review_api import FakeReviewStore, _login

    store = FakeReviewStore()
    manager = store.add_user(phone="13800000032", login_name="legacy-manager", password="AdminPass9!", status="active")
    manager["permissions"] = ["auth.user.manage"]
    manager["roles"] = [{"id": 2, "code": "breed_manager", "name": "养殖管理员"}]
    store.admin_ids.add(manager["id"])
    client = create_app(_settings(), store=store).test_client()
    _login(client, "legacy-manager", "AdminPass9!")

    response = client.get("/api/v1/admin/users")

    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"


def test_real_mysql_role_changes_are_persisted_and_audited() -> None:
    with disposable_database("adp_role_permissions", through=19) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO users (phone,login_name,name,password_hash,status) VALUES ('13990000019','role-admin','角色管理员','hash','active')")
            operator_id = int(cursor.lastrowid)
            cursor.execute("SELECT id FROM roles WHERE code='breed_manager'")
            role_id = int(cursor.fetchone()["id"])
            cursor.execute("SELECT COUNT(*) AS total FROM role_permissions rp INNER JOIN roles r ON r.id=rp.role_id INNER JOIN permissions p ON p.id=rp.permission_id WHERE r.code='super_admin' AND p.code='auth.role.manage'")
            assert int(cursor.fetchone()["total"]) == 1
            cursor.execute("SELECT COUNT(*) AS total FROM role_permissions rp INNER JOIN roles r ON r.id=rp.role_id INNER JOIN permissions p ON p.id=rp.permission_id WHERE r.code<>'super_admin' AND p.code IN ('auth.review','auth.user.manage','audit.view')")
            assert int(cursor.fetchone()["total"]) == 0
            cursor.execute("SELECT COUNT(*) AS total FROM role_permissions rp INNER JOIN roles r ON r.id=rp.role_id INNER JOIN permissions p ON p.id=rp.permission_id WHERE (r.code='purchaser' AND p.code='finance.payable.view') OR (r.code='sales_staff' AND p.code='finance.receivable.view')")
            assert int(cursor.fetchone()["total"]) == 2

        store = MySqlAuthStore(settings)
        changed = store.replace_role_permissions(role_id, permission_codes=["workbench.enter", "production.view"], operator_id=operator_id)
        copied = store.copy_role(role_id, code="breed_reviewer", name="养殖复核员", description="负责养殖复核", operator_id=operator_id)

        assert changed["permission_codes"] == ["workbench.enter", "production.view"]
        assert copied["permission_codes"] == ["production.view", "workbench.enter"]
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM audit_logs WHERE user_id=%s AND action IN ('replace_role_permissions','copy_role')", (operator_id,))
            assert int(cursor.fetchone()["total"]) == 2
