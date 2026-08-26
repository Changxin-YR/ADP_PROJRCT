from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import pymysql

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.master_data.master_data_service import MasterDataService
from backend.layers.features.master_data.master_data_store import MySqlMasterDataStore
from backend.tests.mysql_test_database import disposable_database, settings_for
from fake_auth_store import FakeAuthStore


ROOT = Path(__file__).parents[2]


class FakeMasterStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict[int, dict[str, Any]]] = {}
        self.next_id = 1

    def list_records(self, resource: str, **_query: Any) -> dict[str, Any]:
        items = [deepcopy(item) for item in self.rows.get(resource, {}).values()]
        return {"items": items, "page": 1, "page_size": 20, "total": len(items), "has_next": False}

    def create_record(self, resource: str, payload: dict[str, Any], *, user_id: int) -> dict[str, Any]:
        row = {"id": self.next_id, **payload, "status": "draft", "row_version": 1, "created_by": user_id, "has_references": False}
        self.rows.setdefault(resource, {})[self.next_id] = row
        self.next_id += 1
        return deepcopy(row)

    def get_record(self, resource: str, record_id: int) -> dict[str, Any] | None:
        row = self.rows.get(resource, {}).get(record_id)
        return deepcopy(row) if row else None

    def update_record(self, resource: str, record_id: int, payload: dict[str, Any], *, expected_version: int, user_id: int) -> dict[str, Any]:
        row = self.rows[resource][record_id]
        assert row["row_version"] == expected_version
        row.update(payload)
        row["row_version"] += 1
        row["updated_by"] = user_id
        return deepcopy(row)

    def set_status(self, resource: str, record_id: int, status: str, *, expected_version: int, user_id: int) -> dict[str, Any]:
        row = self.rows[resource][record_id]
        assert row["row_version"] == expected_version
        row["status"] = status
        row["row_version"] += 1
        row["updated_by"] = user_id
        return deepcopy(row)

    def delete_draft(self, resource: str, record_id: int, *, user_id: int) -> dict[str, Any]:
        del user_id
        return deepcopy(self.rows[resource].pop(record_id))

    def get_pending_pond_status_change(self, pond_id: int) -> dict[str, Any] | None:
        return deepcopy(self.rows["ponds"][pond_id].get("pending_status_change"))

    def request_pond_status_change(self, pond_id: int, *, to_status: str, reason: str, expected_pond_version: int, user_id: int) -> dict[str, Any]:
        pond = self.rows["ponds"][pond_id]
        assert pond["row_version"] == expected_pond_version
        request = {"id": 1, "pond_id": pond_id, "from_status": pond["pond_status"], "to_status": to_status, "reason": reason, "status": "submitted", "requested_by": user_id, "row_version": 1}
        pond["pending_status_change"] = request
        return deepcopy(request)

    def verify_pond_status_change(self, pond_id: int, request_id: int, *, expected_version: int, expected_pond_version: int, user_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
        pond = self.rows["ponds"][pond_id]
        change = pond["pending_status_change"]
        assert request_id == change["id"] and expected_version == change["row_version"]
        assert expected_pond_version == pond["row_version"]
        if change["requested_by"] == user_id:
            raise DomainError("SELF_VERIFICATION_FORBIDDEN", "经办人与核验人不能是同一人", 409)
        change.update(status="verified", verified_by=user_id, row_version=2)
        pond.update(pond_status=change["to_status"], row_version=pond["row_version"] + 1, pending_status_change=None)
        return deepcopy(pond), deepcopy(change)


def settings() -> Settings:
    return Settings.from_env({
        "APP_ENV": "test", "FLASK_SECRET_KEY": "master-test", "CSRF_SECRET_KEY": "master-csrf",
        "MYSQL_HOST": "127.0.0.1", "MYSQL_DATABASE": "adp_test", "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test", "SESSION_COOKIE_SECURE": "false",
    })


def logged_in_client(master_store: Any | None = None):
    auth = FakeAuthStore()
    user = auth.add_user(phone="13800000601", login_name="master-admin", password="Correct9!", status="active")
    user["permissions"] = ["master_data.view", "master_data.manage", "master_data.verify"]
    app = create_app(settings(), store=auth, master_store=master_store or FakeMasterStore())
    client = app.test_client()
    csrf = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    login = client.post("/api/v1/auth/login", json={"identifier": "master-admin", "password": "Correct9!"}, headers={"X-CSRF-Token": csrf})
    assert login.status_code == 200
    return client


def csrf(client) -> dict[str, str]:
    token = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    return {"X-CSRF-Token": token}


def test_submitted_master_record_can_change_version_then_becomes_read_only() -> None:
    client = logged_in_client()
    created = client.post("/api/v1/master-data/materials", json={"code": "MAT-001", "name": "膨化饲料"}, headers=csrf(client))
    assert created.status_code == 201
    row = created.get_json()["data"]["record"]
    assert set(row["allowed_actions"]) == {"view", "edit", "delete", "submit"}

    submitted = client.post(f"/api/v1/master-data/materials/{row['id']}/submit", json={"expected_version": 1}, headers=csrf(client))
    assert submitted.status_code == 200
    assert submitted.get_json()["data"]["record"]["allowed_actions"] == ["view", "edit", "verify"]

    changed = client.patch(f"/api/v1/master-data/materials/{row['id']}", json={"expected_version": 2, "name": "高蛋白膨化饲料"}, headers=csrf(client))
    assert changed.status_code == 200
    assert changed.get_json()["data"]["record"]["row_version"] == 3

    stale = client.post(f"/api/v1/master-data/materials/{row['id']}/verify", json={"expected_version": 2}, headers=csrf(client))
    assert stale.status_code == 409
    assert stale.get_json()["code"] == "VERSION_CONFLICT"
    verified = client.post(f"/api/v1/master-data/materials/{row['id']}/verify", json={"expected_version": 3}, headers=csrf(client))
    assert verified.status_code == 200
    assert verified.get_json()["data"]["record"]["allowed_actions"] == ["view"]
    assert client.patch(f"/api/v1/master-data/materials/{row['id']}", json={"expected_version": 4, "name": "非法修改"}, headers=csrf(client)).status_code == 409
    assert client.delete(f"/api/v1/master-data/materials/{row['id']}", headers=csrf(client)).status_code == 409


def test_unsubmitted_unreferenced_draft_can_be_deleted() -> None:
    client = logged_in_client()
    row = client.post("/api/v1/master-data/suppliers", json={"code": "SUP-001", "name": "测试供应商"}, headers=csrf(client)).get_json()["data"]["record"]

    response = client.delete(f"/api/v1/master-data/suppliers/{row['id']}", headers=csrf(client))

    assert response.status_code == 200


def test_unknown_or_server_owned_master_fields_are_rejected() -> None:
    client = logged_in_client()

    unknown = client.post(
        "/api/v1/master-data/materials",
        json={"code": "MAT-002", "name": "非法字段测试", "table_name": "users"},
        headers=csrf(client),
    )
    owned = client.post(
        "/api/v1/master-data/materials",
        json={"code": "MAT-003", "name": "状态篡改测试", "status": "verified"},
        headers=csrf(client),
    )

    assert unknown.status_code == 400
    assert unknown.get_json()["code"] == "MASTER_FIELD_INVALID"
    assert owned.status_code == 400


def test_invalid_master_relation_returns_business_error_instead_of_500() -> None:
    class InvalidRelationStore(FakeMasterStore):
        def create_record(self, resource: str, payload: dict[str, Any], *, user_id: int) -> dict[str, Any]:
            raise pymysql.IntegrityError(1452, "foreign key constraint fails")

    client = logged_in_client(InvalidRelationStore())
    response = client.post(
        "/api/v1/master-data/ponds",
        json={"code": "P-BAD-GROUP", "name": "无效分组塘口", "area_id": 2, "pond_group_id": 999},
        headers=csrf(client),
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "MASTER_RELATION_NOT_FOUND"


def test_pond_status_cannot_be_changed_through_general_master_edit() -> None:
    client = logged_in_client()
    pond = client.post("/api/v1/master-data/ponds", json={"code": "P-001", "name": "测试塘口", "pond_status": "build"}, headers=csrf(client)).get_json()["data"]["record"]

    response = client.patch(f"/api/v1/master-data/ponds/{pond['id']}", json={"pond_status": "stocked", "expected_version": pond["version"]}, headers=csrf(client))

    assert response.status_code == 409
    assert response.get_json()["code"] == "POND_STATUS_CHANGE_REQUIRES_REVIEW"


def test_verified_pond_status_change_requires_another_verifier() -> None:
    store = FakeMasterStore()
    store.rows["ponds"] = {1: {"id": 1, "code": "P-002", "name": "生产塘", "pond_status": "farming", "status": "verified", "row_version": 4, "created_by": 2, "has_references": True}}
    service = MasterDataService(store)
    maker = {"id": 7, "permissions": ["master_data.ponds.manage"], "data_scopes": []}
    checker = {"id": 8, "permissions": ["master_data.verify"], "data_scopes": []}

    requested = service.request_pond_status_change(maker, 1, {"to_status": "clean", "reason": "批次结束清塘", "expected_version": 4})
    with pytest.raises(DomainError) as caught:
        service.verify_pond_status_change(maker | {"permissions": ["master_data.verify"]}, 1, requested["id"], {"expected_version": 1, "expected_pond_version": 4})
    assert caught.value.code == "SELF_VERIFICATION_FORBIDDEN"

    verified = service.verify_pond_status_change(checker, 1, requested["id"], {"expected_version": 1, "expected_pond_version": 4})

    assert verified["record"]["pond_status"] == "clean"
    assert verified["status_change"]["status"] == "verified"


def test_real_mysql_pond_status_change_is_verified_and_audited() -> None:
    with disposable_database("adp_pond_status", through=19) as database:
        mysql_settings = settings_for(database)
        with get_connection(mysql_settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO users (phone,login_name,name,password_hash,status) VALUES ('13990000041','pond-maker','塘口经办','hash','active'),('13990000042','pond-checker','塘口核验','hash','active')")
            maker_id = int(cursor.lastrowid)
            checker_id = maker_id + 1
            cursor.execute("SELECT id,organization_id FROM farms WHERE code='default-farm'"); farm = cursor.fetchone()
            cursor.execute("INSERT INTO areas (organization_id,farm_id,code,name,status,row_version,created_by) VALUES (%s,%s,'P-AREA','状态测试区','verified',1,%s)", (farm["organization_id"], farm["id"], maker_id))
            area_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO ponds (organization_id,farm_id,area_id,code,name,capacity_mu,pond_status,status,row_version,created_by) VALUES (%s,%s,%s,'P-STATUS','状态流程塘',10,'farming','verified',4,%s)", (farm["organization_id"], farm["id"], area_id, maker_id))
            pond_id = int(cursor.lastrowid)

        service = MasterDataService(MySqlMasterDataStore(mysql_settings))
        maker = {"id": maker_id, "permissions": ["master_data.ponds.manage"], "data_scopes": []}
        checker = {"id": checker_id, "permissions": ["master_data.verify"], "data_scopes": []}
        requested = service.request_pond_status_change(maker, pond_id, {"to_status": "clean", "reason": "批次结束清塘", "expected_version": 4})
        with pytest.raises(DomainError) as caught:
            service.verify_pond_status_change(maker | {"permissions": ["master_data.verify"]}, pond_id, requested["id"], {"expected_version": 1, "expected_pond_version": 4})
        assert caught.value.code == "SELF_VERIFICATION_FORBIDDEN"

        verified = service.verify_pond_status_change(checker, pond_id, requested["id"], {"expected_version": 1, "expected_pond_version": 4})

        assert verified["record"]["pond_status"] == "clean"
        with get_connection(mysql_settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status,verified_by FROM pond_status_change_requests WHERE id=%s", (requested["id"],)); change = cursor.fetchone()
            cursor.execute("SELECT id,status FROM work_items WHERE source_key=%s", (f"pond_status:{requested['id']}:verify",)); task = cursor.fetchone()
            cursor.execute("SELECT related_work_item_id FROM audit_logs WHERE object_type='master:ponds' AND object_id=%s AND action='verify_pond_status_change'", (pond_id,)); audit = cursor.fetchone()
        assert change == {"status": "verified", "verified_by": checker_id}
        assert task["status"] == "completed"
        assert audit["related_work_item_id"] == task["id"]


def test_area_scope_cannot_create_master_data_in_another_area() -> None:
    service = MasterDataService(FakeMasterStore())
    user = {
        "id": 7,
        "permissions": ["master_data.materials.manage"],
        "data_scopes": [{"scope_type": "area", "area_id": 11}],
    }

    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        service.create(user, "materials", {"code": "MAT-AREA", "name": "越权物料", "area_id": 12})


def test_view_only_user_receives_view_only_actions() -> None:
    store = FakeMasterStore()
    store.create_record("materials", {"code": "MAT-VIEW", "name": "只读物料"}, user_id=2)
    service = MasterDataService(store)
    user = {"id": 8, "permissions": ["master_data.view"], "data_scopes": []}

    result = service.list_records(user, "materials")

    assert result["items"][0]["allowed_actions"] == ["view"]


def test_master_data_migration_has_relational_scope_and_delete_guards() -> None:
    sql = (ROOT / "database/migrations/008_master_data.sql").read_text(encoding="utf-8")
    for marker in (
        "CREATE TABLE materials", "CREATE TABLE business_partners", "CREATE TABLE business_settings",
        "organization_id BIGINT UNSIGNED NOT NULL", "row_version INT UNSIGNED NOT NULL",
        "CREATE TRIGGER materials_no_formal_delete", "OLD.status <> 'draft'", "ON DELETE RESTRICT",
    ):
        assert marker in sql
