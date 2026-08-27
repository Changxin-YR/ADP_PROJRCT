from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from backend.app import create_app
from backend.config.settings import Settings
from backend.tests.fake_auth_store import FakeAuthStore
from backend.layers.features.data_exchange.data_exchange_service import DataExchangeService
from backend.layers.common.db.repositories.user_repository import UserRepository
from backend.layers.features.data_exchange.data_exchange_store import MySqlDataExchangeStore
from backend.layers.features.data_exchange.template_catalog import get_template
from backend.layers.features.data_exchange.workbooks import preview_workbook
from backend.layers.features.data_exchange.import_validation import validate_rows
from backend.layers.common.governance.lifecycle import DomainError


ROOT = Path(__file__).parents[2]
def test_farm_scope_without_organization_id_allows_organization_access() -> None:
    DataExchangeService.scope({"roles": [{"code": "super_admin"}], "data_scopes": [{"scope_type": "farm"}]}, 1)


def test_export_requires_module_permission_in_addition_to_exchange_permission(tmp_path: Path) -> None:
    service = DataExchangeService(FakeExchangeStore(), tmp_path)
    user = {"id": 1, "permissions": ["data_exchange.export"], "roles": [{"code": "breed_worker"}], "data_scopes": [{"scope_type": "farm", "organization_id": 1}]}
    with pytest.raises(DomainError, match="FORBIDDEN"):
        service.export(user, organization_id=1, resource="payments", file_format="xlsx", filters={}, request_id="r")


def test_export_rejects_filters_not_supported_by_resource(tmp_path: Path) -> None:
    service = DataExchangeService(FakeExchangeStore(), tmp_path)
    user = {"id": 1, "permissions": ["data_exchange.export"], "roles": [{"code": "super_admin"}], "data_scopes": [{"scope_type": "farm", "organization_id": 1}]}

    with pytest.raises(DomainError, match="EXPORT_FILTER_INVALID"):
        service.export(user, organization_id=1, resource="materials", file_format="xlsx", filters={"pond_id": 1}, request_id="r")


def test_attachment_requires_the_target_business_module_permission(tmp_path: Path) -> None:
    service = DataExchangeService(FakeExchangeStore(), tmp_path)
    user = {
        "id": 7,
        "permissions": ["attachment.manage", "production.view"],
        "roles": [{"code": "breed_worker"}],
        "data_scopes": [{"scope_type": "farm", "organization_id": 1}],
    }

    with pytest.raises(DomainError, match="FORBIDDEN"):
        service.upload_attachment(
            user, organization_id=1, entity_type="cost:expense", entity_id=9,
            file_name="invoice.pdf", media_type="application/pdf", content=b"%PDF-1.4\n%%EOF\n",
        )


def test_super_admin_farm_scope_is_unrestricted_for_exchange_store() -> None:
    assert MySqlDataExchangeStore._organizations({"roles": [{"code": "super_admin"}], "data_scopes": [{"scope_type": "farm"}]}) is None


def test_auth_me_preserves_organization_id_for_area_scope(tmp_path: Path) -> None:
    auth = FakeAuthStore()
    user = auth.add_user(phone="13800000802", login_name="scoped-user", password="Correct9!", status="active")
    user.update(
        roles=[{"code": "breed_manager"}],
        data_scopes=[{"id": 7, "scope_type": "area", "area_id": 2, "organization_id": 42}],
        permissions=["data_exchange.export"],
    )
    browser = create_app(settings(tmp_path), store=auth, data_exchange_store=FakeExchangeStore()).test_client()
    csrf = browser.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    login = browser.post(
        "/api/v1/auth/login",
        json={"identifier": "scoped-user", "password": "Correct9!"},
        headers={"X-CSRF-Token": csrf},
    )
    assert login.status_code == 200

    me = browser.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.get_json()["data"]["user"]["data_scopes"] == [
        {"id": 7, "scope_type": "area", "area_id": 2, "organization_id": 42}
    ]


def test_data_exchange_scope_requires_resolved_organization_for_scoped_users() -> None:
    scoped = {"roles": [{"code": "breed_manager"}], "data_scopes": [{"scope_type": "area", "area_id": 2}]}
    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        DataExchangeService.scope(scoped, 42)

    allowed = {"roles": [{"code": "breed_manager"}], "data_scopes": [{"scope_type": "area", "area_id": 2, "organization_id": 42}]}
    DataExchangeService.scope(allowed, 42)
    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        DataExchangeService.scope(allowed, 43)
def test_user_scope_query_includes_organization_id() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.sql: list[str] = []
            self.fetch_count = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, statement, params=()):
            del params
            self.sql.append(statement)

        def fetchall(self):
            self.fetch_count += 1
            if self.fetch_count == 2:
                return [{"id": 1, "code": "north-farm-all", "name": "北区", "scope_type": "area", "area_id": 2, "organization_id": 1}]
            return []

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

    connection = Connection()
    roles, scopes, permissions = UserRepository().permissions(connection, user_id=7)
    assert roles == [] and permissions == []
    assert scopes[0]["organization_id"] == 1
    assert "organization_id" in connection.cursor_instance.sql[1]


class FakeExchangeStore:
    def __init__(self) -> None:
        self.batches: dict[int, dict[str, Any]] = {}
        self.attachments: dict[int, dict[str, Any]] = {}
        self.materials: list[dict[str, Any]] = []
        self.exports: list[dict[str, Any]] = []
        self.items: dict[int, list[tuple[str, int]]] = {}
        self.next_id = 1

    def attachment_target_exists(self, organization_id: int, entity_type: str, entity_id: int) -> bool:
        del organization_id, entity_type, entity_id
        return True

    def attachment_target_accessible(self, user: dict[str, Any], organization_id: int, entity_type: str, entity_id: int) -> bool:
        del user, organization_id, entity_type, entity_id
        return True

    def find_import_hash(self, organization_id: int, template_code: str, sha256: str):
        return next((row for row in self.batches.values() if row["organization_id"] == organization_id and row["template_code"] == template_code and row["file_sha256"] == sha256), None)

    def create_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**deepcopy(payload), "id": len(self.batches) + 1}
        self.batches[row["id"]] = row
        return deepcopy(row)

    def list_imports(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        del user
        return [deepcopy(row) for row in reversed(self.batches.values())]

    def get_import(self, batch_id: int, user: dict[str, Any]) -> dict[str, Any] | None:
        del user
        row = self.batches.get(batch_id)
        return deepcopy(row) if row else None

    def validate_rows(self, user: dict[str, Any], organization_id: int, template_code: str, rows: list[dict[str, Any]], row_numbers: list[int]) -> list[dict[str, Any]]:
        del user, organization_id, template_code, rows, row_numbers
        return []

    def confirm_import(self, batch_id: int, user: dict[str, Any]) -> dict[str, Any]:
        row = self.batches[batch_id]
        before = deepcopy(self.materials)
        inserted: list[tuple[str, int]] = []
        try:
            for item in row["preview_rows"]:
                if item.get("name") == "ROLLBACK":
                    raise ValueError("forced transaction failure")
                record_id = self.next_id
                self.next_id += 1
                self.materials.append({**item, "id": record_id, "status": "draft", "created_by": user["id"]})
                inserted.append(("master:materials", record_id))
        except Exception:
            self.materials = before
            raise
        self.items[batch_id] = inserted
        row.update(status="imported", imported_count=len(row["preview_rows"]))
        return deepcopy(row)

    def revoke_import(self, batch_id: int, user: dict[str, Any]) -> dict[str, Any]:
        del user
        row = self.batches[batch_id]
        if row.get("status") != "imported":
            raise DomainError("IMPORT_NOT_IMPORTED", "仅已导入的批次可以撤销", 409)
        revoked = {entity_id for _entity_type, entity_id in self.items.get(batch_id, [])}
        self.materials = [item for item in self.materials if item.get("id") not in revoked]
        row.update(status="undone", imported_count=0)
        return deepcopy(row)

    def export_rows(self, user: dict[str, Any], resource: str, filters: dict[str, Any]):
        del user, filters
        if resource not in {"materials", "imports"}:
            raise DomainError("EXPORT_RESOURCE_INVALID", "不支持导出该业务类型", 400)
        return deepcopy(self.materials if resource == "materials" else list(self.batches.values()))

    def record_export(self, payload: dict[str, Any]) -> int:
        self.exports.append(deepcopy(payload))
        return len(self.exports)

    def find_attachment_hash(self, organization_id: int, entity_type: str, entity_id: int, sha256: str):
        return next((row for row in self.attachments.values() if (row["organization_id"], row["entity_type"], row["entity_id"], row["sha256"]) == (organization_id, entity_type, entity_id, sha256)), None)

    def create_attachment(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**deepcopy(payload), "id": len(self.attachments) + 1}
        self.attachments[row["id"]] = row
        return deepcopy(row)

    def list_attachments(self, user: dict[str, Any], entity_type: str, entity_id: int):
        del user
        return [deepcopy(row) for row in self.attachments.values() if row["entity_type"] == entity_type and row["entity_id"] == entity_id]

    def get_attachment(self, user: dict[str, Any], attachment_id: int):
        del user
        row = self.attachments.get(attachment_id)
        return deepcopy(row) if row else None


def settings(tmp_path: Path) -> Settings:
    return Settings.from_env({
        "APP_ENV": "test", "FLASK_SECRET_KEY": "exchange-test", "CSRF_SECRET_KEY": "exchange-csrf",
        "MYSQL_HOST": "127.0.0.1", "MYSQL_DATABASE": "adp_test", "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test", "SESSION_COOKIE_SECURE": "false", "ATTACHMENT_ROOT": str(tmp_path),
    })


def client(tmp_path: Path, store: FakeExchangeStore | None = None):
    auth = FakeAuthStore()
    user = auth.add_user(phone="13800000801", login_name="exchange-admin", password="Correct9!", status="active")
    user.update(permissions=["data_exchange.view", "data_exchange.import", "data_exchange.export", "attachment.manage", "cost.view"])
    app = create_app(settings(tmp_path), store=auth, data_exchange_store=store or FakeExchangeStore())
    browser = app.test_client()
    csrf = browser.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    assert browser.post("/api/v1/auth/login", json={"identifier": "exchange-admin", "password": "Correct9!"}, headers={"X-CSRF-Token": csrf}).status_code == 200
    return browser


def token(browser) -> dict[str, str]:
    value = browser.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    return {"X-CSRF-Token": value}


def workbook(rows: list[list[Any]]) -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(["code", "name", "category", "unit"])
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def upload(browser, content: bytes, name: str = "materials.xlsx"):
    return browser.post(
        "/api/v1/data-exchange/imports/preview",
        data={"organization_id": "1", "template_code": "materials", "file": (BytesIO(content), name)},
        headers=token(browser), content_type="multipart/form-data",
    )


def test_templates_are_versioned_and_downloadable(tmp_path: Path) -> None:
    browser = client(tmp_path)
    response = browser.get("/api/v1/data-exchange/templates")

    assert response.status_code == 200
    templates = response.get_json()["data"]["items"]
    assert len(templates) >= 30
    assert all(item["version"] and item["fields"] for item in templates)
    downloaded = browser.get("/api/v1/data-exchange/templates/materials/download")
    assert downloaded.status_code == 200
    assert downloaded.data.startswith(b"PK")
    assert downloaded.headers["X-Template-Version"]


def test_preview_rejects_invalid_datetime_values() -> None:
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    template = get_template("feed-plans")
    sheet.append([field.key for field in template.fields])
    sheet.append(["FEED-1", "计划", 1, 1, 1, 2, 10, "2026-99-99 25:61"])
    output = BytesIO()
    book.save(output)

    result = preview_workbook(template, output.getvalue())

    assert any(item["column"] == "planned_at" and "日期时间" in item["message"] for item in result["errors"])


def test_import_validation_rejects_inventory_lot_for_another_material() -> None:
    class Cursor:
        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            self.last_sql = sql
            self.last_params = params

        def fetchall(self) -> list[dict[str, object]]:
            if "SELECT id FROM materials" in self.last_sql:
                return [{"id": 7}]
            if "SELECT id FROM warehouses" in self.last_sql:
                return [{"id": 2}]
            return []

        def fetchone(self) -> dict[str, object] | None:
            if "FROM inventory_lots" in self.last_sql:
                return {"organization_id": 1, "material_id": 99, "status": "available"}
            return None

    errors = validate_rows(
        Cursor(), 1, "scraps",
        [{"code": "SCRAP-1", "name": "报损", "warehouse_id": 2, "material_id": 7, "inventory_lot_id": 8, "quantity": 1, "happened_at": "2026-08-26", "reason": "破损"}],
        [2],
    )

    assert any(item["column"] == "inventory_lot_id" and "物料" in item["message"] for item in errors)


def test_import_validation_rejects_asset_salvage_not_below_original_value() -> None:
    class Cursor:
        def execute(self, _sql: str, _params: tuple[object, ...] = ()) -> None:
            pass

        def fetchall(self) -> list[dict[str, object]]:
            return []

    errors = validate_rows(
        Cursor(), 1, "assets",
        [{"code": "ASSET-1", "name": "设备", "farm_id": 1, "asset_type": "equipment", "category_code": "equipment", "amount": "100.00", "salvage_value": "100.00", "useful_life_months": 12, "purchase_date": "2026-08-01", "depreciation_start_date": "2026-08-01"}],
        [2],
    )

    assert any(item["column"] == "salvage_value" and "小于资产原值" in item["message"] for item in errors)


def test_import_validation_returns_empty_errors_for_valid_template_without_special_checks() -> None:
    class Cursor:
        def execute(self, _sql: str, _params: tuple[object, ...] = ()) -> None:
            pass

        def fetchall(self) -> list[dict[str, object]]:
            return [{"id": 1, "code": "MAT-1"}]

    errors = validate_rows(Cursor(), 1, "materials", [{"code": "MAT-2", "name": "饲料"}], [2])

    assert errors == []


def test_preview_rejects_bad_rows_deduplicates_hash_and_blocks_confirmation(tmp_path: Path) -> None:
    browser = client(tmp_path)
    content = workbook([["MAT-001", "", "饲料", "kg"]])

    preview = upload(browser, content)
    assert preview.status_code == 201
    batch = preview.get_json()["data"]["batch"]
    assert batch["status"] == "invalid"
    assert batch["errors"][0]["column"] == "name"
    assert upload(browser, content).status_code == 409
    confirmed = browser.post(f"/api/v1/data-exchange/imports/{batch['id']}/confirm", json={}, headers=token(browser))
    assert confirmed.status_code == 409
    errors = browser.get(f"/api/v1/data-exchange/imports/{batch['id']}/errors")
    assert errors.status_code == 200
    assert errors.data.startswith(b"PK")


def test_valid_import_and_exports_are_audited_with_request_scope(tmp_path: Path) -> None:
    store = FakeExchangeStore()
    browser = client(tmp_path, store)
    preview = upload(browser, workbook([["MAT-002", "膨化饲料", "饲料", "kg"]])).get_json()["data"]["batch"]

    confirmed = browser.post(f"/api/v1/data-exchange/imports/{preview['id']}/confirm", json={}, headers=token(browser))
    assert confirmed.status_code == 200
    assert store.materials[0]["status"] == "draft"
    for file_format, prefix in (("xlsx", b"PK"), ("pdf", b"%PDF")):
        response = browser.post(
            "/api/v1/data-exchange/exports", json={"organization_id": 1, "resource": "materials", "format": file_format, "filters": {"status": "draft"}},
            headers={**token(browser), "X-Request-ID": f"export-{file_format}"},
        )
        assert response.status_code == 200
        assert response.data.startswith(prefix)
    assert [(item["format"], item["request_id"], item["row_count"]) for item in store.exports] == [("xlsx", "export-xlsx", 1), ("pdf", "export-pdf", 1)]


def test_private_attachments_require_auth_and_deduplicate_content(tmp_path: Path) -> None:
    browser = client(tmp_path)
    payload = {"organization_id": "1", "entity_type": "cost:entry", "entity_id": "9", "file": (BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"), "客户凭证.pdf", "application/pdf")}
    created = browser.post("/api/v1/data-exchange/attachments", data=payload, headers=token(browser), content_type="multipart/form-data")
    assert created.status_code == 201
    attachment = created.get_json()["data"]["attachment"]
    assert "客户凭证" not in attachment["storage_name"]
    duplicate = browser.post("/api/v1/data-exchange/attachments", data={**payload, "file": (BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"), "copy.pdf", "application/pdf")}, headers=token(browser), content_type="multipart/form-data")
    assert duplicate.status_code == 409
    anonymous = browser.application.test_client().get(f"/api/v1/data-exchange/attachments/{attachment['id']}/download")
    assert anonymous.status_code == 401
    downloaded = browser.get(f"/api/v1/data-exchange/attachments/{attachment['id']}/download")
    assert downloaded.data == b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
