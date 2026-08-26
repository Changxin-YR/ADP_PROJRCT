from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.production.production_service import ProductionService
from backend.layers.features.production.production_store import MySqlProductionStore
from fake_auth_store import FakeAuthStore


ROOT = Path(__file__).parents[2]


class FakeProductionStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict[int, dict[str, Any]]] = {}
        self.ledger: list[dict[str, Any]] = []
        self.next_id = 1

    def list_records(self, resource: str, **_query: Any) -> dict[str, Any]:
        items = [deepcopy(row) for row in self.rows.get(resource, {}).values()]
        return {"items": items, "page": 1, "page_size": 20, "total": len(items), "has_next": False}

    def create_record(self, resource: str, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        del user
        row = {"id": self.next_id, **payload, "status": "draft", "row_version": 1, "created_by": user_id}
        self.rows.setdefault(resource, {})[self.next_id] = row
        self.next_id += 1
        return deepcopy(row)

    def get_record(self, resource: str, record_id: int) -> dict[str, Any] | None:
        row = self.rows.get(resource, {}).get(record_id)
        return deepcopy(row) if row else None

    def create_correction(self, resource: str, record_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        del user
        original = self.rows[resource][record_id]
        assert original["status"] == "verified"
        assert original["row_version"] == expected_version
        row = {
            **original, **payload, "id": self.next_id, "correction_of_id": record_id,
            "status": "draft", "row_version": 1, "created_by": user_id,
        }
        self.rows[resource][self.next_id] = row
        self.next_id += 1
        return deepcopy(row)

    def update_record(self, resource: str, record_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        del user
        row = self.rows[resource][record_id]
        if row["row_version"] != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        row.update(payload)
        row.update(row_version=expected_version + 1, updated_by=user_id)
        return deepcopy(row)

    def set_status(self, resource: str, record_id: int, status: str, *, expected_version: int, user_id: int, evidence_attachment_ids: list[int] | None = None) -> dict[str, Any]:
        row = self.rows[resource][record_id]
        if row["row_version"] != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        row.update(status=status, row_version=expected_version + 1, updated_by=user_id)
        if evidence_attachment_ids:
            row["evidence_attachment_ids"] = evidence_attachment_ids
        if status == "verified":
            self._post(resource, row)
        return deepcopy(row)

    def _post(self, resource: str, row: dict[str, Any]) -> None:
        if resource not in {"batches", "transfers", "losses", "harvests"}:
            return
        quantity = Decimal(str(row.get("quantity", row.get("initial_quantity", 0))))
        weight = Decimal(str(row.get("weight_kg", row.get("initial_weight_kg", 0))))
        batch_id = int(row["id"] if resource == "batches" else row["batch_id"])
        if resource == "batches":
            self.ledger.append({"batch_id": batch_id, "pond_id": row["pond_id"], "quantity_delta": quantity, "weight_delta": weight})
        elif resource == "transfers":
            self.ledger.extend([
                {"batch_id": batch_id, "pond_id": row["pond_id"], "quantity_delta": -quantity, "weight_delta": -weight},
                {"batch_id": batch_id, "pond_id": row["target_pond_id"], "quantity_delta": quantity, "weight_delta": weight},
            ])
        elif resource in {"losses", "harvests"}:
            self.ledger.append({"batch_id": batch_id, "pond_id": row["pond_id"], "quantity_delta": -quantity, "weight_delta": -weight})

    def delete_draft(self, resource: str, record_id: int, *, user_id: int) -> dict[str, Any]:
        del user_id
        return deepcopy(self.rows[resource].pop(record_id))

    def reconcile_batch(self, batch_id: int) -> dict[str, Any]:
        rows = [item for item in self.ledger if item["batch_id"] == batch_id]
        return {
            "batch_id": batch_id,
            "quantity": sum((item["quantity_delta"] for item in rows), Decimal("0")),
            "weight_kg": sum((item["weight_delta"] for item in rows), Decimal("0")),
            "difference": Decimal("0"),
        }


def user(user_id: int, *permissions: str) -> dict[str, Any]:
    return {"id": user_id, "permissions": list(permissions), "data_scopes": []}


def create_verified(service: ProductionService, resource: str, payload: dict[str, Any], creator_id: int = 1) -> dict[str, Any]:
    creator = user(creator_id, "production.view", "production.manage")
    verifier = user(2, "production.view", "production.verify")
    row = service.create(creator, resource, payload)
    row = service.submit(creator, resource, row["id"], {"expected_version": row["version"]})
    return service.verify(verifier, resource, row["id"], {"expected_version": row["version"]})


def test_batch_stock_is_reconciled_from_append_only_facts() -> None:
    service = ProductionService(FakeProductionStore())
    batch = create_verified(service, "batches", {"code": "B-001", "name": "春季虾批次", "pond_id": 10, "species": "南美白对虾", "initial_quantity": 1000, "initial_weight_kg": 20})
    evidence = {"evidence_attachment_ids": [91]}
    create_verified(service, "transfers", {"code": "TR-001", "name": "转塘", "batch_id": batch["id"], "pond_id": 10, "target_pond_id": 11, "quantity": 200, "weight_kg": 4, **evidence})
    create_verified(service, "losses", {"code": "LS-001", "name": "死亡损耗", "batch_id": batch["id"], "pond_id": 11, "quantity": 10, "weight_kg": 0.2, **evidence})
    create_verified(service, "harvests", {"code": "HV-001", "name": "首批起捕", "batch_id": batch["id"], "pond_id": 10, "quantity": 300, "weight_kg": 6, **evidence})

    result = service.reconcile(user(1, "production.view"), batch["id"])

    assert result["quantity"] == Decimal("690")
    assert result["weight_kg"] == Decimal("13.8")
    assert result["difference"] == Decimal("0")


def test_verified_stock_correction_appends_only_the_difference() -> None:
    original = {
        "id": 1, "organization_id": 1, "batch_id": 4, "pond_id": 10,
        "quantity": Decimal("10"), "weight_kg": Decimal("2"), "status": "verified",
    }

    class Cursor:
        inserted: list[tuple[Any, ...]] = []
        result: dict[str, Any] = {}

        def execute(self, sql: str, _params: tuple[Any, ...]) -> None:
            self.result = original if sql.startswith("SELECT * FROM production_documents") else {"quantity": Decimal("90"), "weight": Decimal("18")}

        def fetchone(self) -> dict[str, Any]:
            return self.result

        def executemany(self, _sql: str, rows: list[tuple[Any, ...]]) -> None:
            self.inserted = rows

    cursor = Cursor()
    store = object.__new__(MySqlProductionStore)
    store._post_stock(cursor, "losses", {
        **original, "id": 2, "correction_of_id": 1,
        "quantity": Decimal("8"), "weight_kg": Decimal("1.6"),
    }, user_id=7)

    assert len(cursor.inserted) == 1
    assert cursor.inserted[0][3] == "correction"
    assert cursor.inserted[0][6:8] == (Decimal("2"), Decimal("0.4"))


def test_submitted_production_record_edit_invalidates_stale_verification() -> None:
    store = FakeProductionStore()
    service = ProductionService(store)
    manager = user(1, "production.view", "production.manage")
    verifier = user(2, "production.view", "production.verify")
    row = service.create(manager, "samplings", {"code": "SP-001", "name": "规格抽样", "batch_id": 1, "pond_id": 10, "quantity": 30})
    row = service.submit(manager, "samplings", row["id"], {"expected_version": 1})
    changed = service.update(manager, "samplings", row["id"], {"expected_version": 2, "quantity": 32})

    assert changed["version"] == 3
    with pytest.raises(DomainError, match="VERSION_CONFLICT"):
        service.verify(verifier, "samplings", row["id"], {"expected_version": 2})


def test_last_editor_cannot_verify_any_submitted_production_record() -> None:
    service = ProductionService(FakeProductionStore())
    creator = user(1, "production.view", "production.manage")
    editor = user(2, "production.view", "production.manage", "production.verify")
    row = service.create(creator, "samplings", {"code": "SP-SELF", "name": "自审抽样", "batch_id": 1, "pond_id": 10, "quantity": 30})
    row = service.submit(creator, "samplings", row["id"], {"expected_version": row["version"]})
    row = service.update(editor, "samplings", row["id"], {"expected_version": row["version"], "quantity": 31})

    with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
        service.verify(editor, "samplings", row["id"], {"expected_version": row["version"]})


def test_verified_production_record_is_read_only() -> None:
    service = ProductionService(FakeProductionStore())
    row = create_verified(service, "daily-operations", {"code": "OP-001", "name": "巡塘", "pond_id": 10})
    manager = user(1, "production.manage")

    with pytest.raises(DomainError, match="RECORD_READ_ONLY"):
        service.update(manager, "daily-operations", row["id"], {"expected_version": row["version"], "name": "篡改"})


def test_record_operations_enforce_authorized_area_scope() -> None:
    store = FakeProductionStore()
    row = store.create_record("samplings", {"code": "SP-SCOPE", "name": "越权抽样", "area_id": 12, "pond_id": 10}, user=user(2), user_id=2)
    scoped_user = {
        "id": 1, "permissions": ["production.view", "production.manage"],
        "data_scopes": [{"scope_type": "area", "area_id": 11}],
    }
    service = ProductionService(store)

    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        service.get(scoped_user, "samplings", row["id"])
    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        service.update(scoped_user, "samplings", row["id"], {"expected_version": 1, "name": "越权修改"})


def test_verified_record_creates_linked_correction_without_mutating_original() -> None:
    store = FakeProductionStore()
    service = ProductionService(store)
    original = create_verified(service, "samplings", {"code": "SP-002", "name": "规格抽样", "batch_id": 1, "pond_id": 10, "quantity": 30})

    assert callable(getattr(service, "correct", None)), "ProductionService.correct is required"
    correction = service.correct(
        user(1, "production.manage"), "samplings", original["id"],
        {"expected_version": original["version"], "code": "SP-002-C1", "name": "规格抽样更正", "quantity": 32, "note": "复核抽样记录"},
    )

    assert correction["correction_of_id"] == original["id"]
    assert correction["status"] == "draft"
    assert correction["allowed_actions"] == ["view", "edit", "delete", "submit"]
    assert store.rows["samplings"][original["id"]]["status"] == "verified"
    assert store.rows["samplings"][original["id"]]["quantity"] == 30


def test_high_risk_production_verification_requires_evidence_and_separate_actor() -> None:
    service = ProductionService(FakeProductionStore())
    manager = user(1, "production.view", "production.manage", "production.verify")
    row = service.create(manager, "losses", {"code": "LS-002", "name": "损耗", "batch_id": 1, "pond_id": 10, "quantity": 5})
    row = service.submit(manager, "losses", row["id"], {"expected_version": 1})

    with pytest.raises(DomainError, match="EVIDENCE_REQUIRED"):
        service.verify(user(2, "production.verify"), "losses", row["id"], {"expected_version": 2})
    with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
        service.verify(manager, "losses", row["id"], {"expected_version": 2, "evidence_attachment_ids": [9]})

    second = service.create(user(3, "production.manage"), "losses", {"code": "LS-003", "name": "损耗", "batch_id": 1, "pond_id": 10, "quantity": 5})
    submitter = user(4, "production.manage", "production.verify")
    second = service.submit(submitter, "losses", second["id"], {"expected_version": 1})
    with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
        service.verify(submitter, "losses", second["id"], {"expected_version": second["version"], "evidence_attachment_ids": [9]})


def test_feed_log_requires_task_and_material_issue_before_verification() -> None:
    service = ProductionService(FakeProductionStore())
    manager = user(1, "production.manage")
    row = service.create(manager, "feed-logs", {"code": "FL-001", "name": "晨间投喂", "batch_id": 1, "pond_id": 10, "material_id": 7, "quantity": 20})
    row = service.submit(manager, "feed-logs", row["id"], {"expected_version": row["version"]})

    with pytest.raises(DomainError, match="FEED_LOG_LINKS_REQUIRED"):
        service.verify(user(2, "production.verify"), "feed-logs", row["id"], {"expected_version": row["version"]})


def test_production_migration_declares_relations_and_immutable_stock_ledger() -> None:
    sql = (ROOT / "database/migrations/009_production.sql").read_text(encoding="utf-8")
    for marker in (
        "CREATE TABLE production_batches", "CREATE TABLE production_documents",
        "CREATE TABLE batch_stock_records", "uq_batch_stock_source_line",
        "CREATE TRIGGER batch_stock_records_no_update", "CREATE TRIGGER batch_stock_records_no_delete",
        "CREATE TRIGGER production_documents_no_formal_delete", "ON DELETE RESTRICT",
        "feed_task_id BIGINT UNSIGNED", "material_issue_request_id BIGINT UNSIGNED",
    ):
        assert marker in sql


def test_production_record_get_and_correction_routes() -> None:
    store = FakeProductionStore()
    store.rows["samplings"] = {1: {
        "id": 1, "code": "SP-API", "name": "接口抽样", "batch_id": 1, "pond_id": 10,
        "quantity": 20, "status": "verified", "row_version": 4, "created_by": 9,
    }}
    store.next_id = 2
    auth = FakeAuthStore()
    account = auth.add_user(phone="13800000606", login_name="production-admin", password="Correct9!", status="active")
    account["permissions"] = ["production.view", "production.manage", "production.verify"]
    settings = Settings.from_env({
        "APP_ENV": "test", "FLASK_SECRET_KEY": "production-test", "CSRF_SECRET_KEY": "production-csrf",
        "MYSQL_HOST": "127.0.0.1", "MYSQL_DATABASE": "adp_test", "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test", "SESSION_COOKIE_SECURE": "false",
    })
    client = create_app(settings, store=auth, production_store=store).test_client()
    token = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    assert client.post("/api/v1/auth/login", json={"identifier": "production-admin", "password": "Correct9!"}, headers={"X-CSRF-Token": token}).status_code == 200

    fetched = client.get("/api/v1/production/samplings/1")
    token = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    corrected = client.post(
        "/api/v1/production/samplings/1/corrections",
        json={"expected_version": 4, "code": "SP-API-C1", "name": "接口抽样更正", "quantity": 22, "note": "复核原始记录"},
        headers={"X-CSRF-Token": token},
    )

    assert fetched.status_code == 200
    assert fetched.get_json()["data"]["record"]["allowed_actions"] == ["view", "correct"]
    assert corrected.status_code == 201
    assert corrected.get_json()["data"]["record"]["correction_of_id"] == 1
