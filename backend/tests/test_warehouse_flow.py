from decimal import Decimal
from inspect import getsource
from pathlib import Path

import pytest

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.warehouse.warehouse_posting import allocate_fefo, build_movements, movement_difference
from backend.layers.features.warehouse.warehouse_ledger_store import WarehouseLedgerPoster
from backend.layers.features.warehouse.warehouse_service import WarehouseService
from backend.layers.features.warehouse.warehouse_transfer_store import cancel_transfer
from fake_auth_store import FakeAuthStore


ROOT = Path(__file__).parents[2]


def test_fefo_uses_nearest_valid_expiry_and_prevents_negative_stock() -> None:
    lots = [
        {"id": 2, "available": Decimal("5"), "expiry_date": "2026-10-01", "expired": False},
        {"id": 1, "available": Decimal("8"), "expiry_date": "2026-09-01", "expired": False},
        {"id": 3, "available": Decimal("50"), "expiry_date": "2026-08-01", "expired": True},
    ]

    assert allocate_fefo(lots, Decimal("10")) == [(1, Decimal("8")), (2, Decimal("2"))]
    with pytest.raises(DomainError, match="WAREHOUSE_STOCK_INSUFFICIENT"):
        allocate_fefo(lots, Decimal("14"))


def test_manual_lot_override_requires_reason() -> None:
    lots = [
        {"id": 1, "available": Decimal("8"), "expiry_date": "2026-09-01", "expired": False},
        {"id": 2, "available": Decimal("8"), "expiry_date": "2026-10-01", "expired": False},
    ]

    with pytest.raises(DomainError, match="FEFO_OVERRIDE_REASON_REQUIRED"):
        allocate_fefo(lots, Decimal("2"), specified_lot_id=2)
    assert allocate_fefo(lots, Decimal("2"), specified_lot_id=2, override_reason="质量抽检") == [(2, Decimal("2"))]


def test_verified_documents_create_balanced_append_only_movements() -> None:
    receipt = build_movements("receipts", {"warehouse_id": 1, "inventory_lot_id": 8, "quantity": 100})
    issue = build_movements("issues", {"warehouse_id": 1}, allocations=[(8, Decimal("30"))])
    returned = build_movements("returns", {"warehouse_id": 1, "inventory_lot_id": 8, "quantity": 5})
    transfer = build_movements("transfers", {"warehouse_id": 1, "target_warehouse_id": 2}, allocations=[(8, Decimal("20"))])
    stocktake = build_movements("stocktakes", {"warehouse_id": 1, "inventory_lot_id": 8, "quantity": 45}, book_quantity=Decimal("55"))
    scrap = build_movements("scraps", {"warehouse_id": 1}, allocations=[(8, Decimal("5"))])

    movements = receipt + issue + returned + transfer + stocktake + scrap
    source = sum((item["quantity_delta"] for item in movements if item["warehouse_id"] == 1), Decimal("0"))
    target = sum((item["quantity_delta"] for item in movements if item["warehouse_id"] == 2), Decimal("0"))
    assert (source, target) == (Decimal("40"), Decimal("20"))


def test_correction_posts_only_the_difference_from_the_original_document() -> None:
    original = [
        {"warehouse_id": 1, "inventory_lot_id": 8, "quantity_delta": Decimal("-30")},
        {"warehouse_id": 2, "inventory_lot_id": 8, "quantity_delta": Decimal("30")},
    ]
    corrected = [
        {"warehouse_id": 1, "inventory_lot_id": 8, "quantity_delta": Decimal("-24")},
        {"warehouse_id": 2, "inventory_lot_id": 8, "quantity_delta": Decimal("24")},
    ]

    assert movement_difference(corrected, original) == [
        {"warehouse_id": 1, "inventory_lot_id": 8, "quantity_delta": Decimal("6")},
        {"warehouse_id": 2, "inventory_lot_id": 8, "quantity_delta": Decimal("-6")},
    ]


class Store:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row

    def get_record(self, _resource: str, _record_id: int) -> dict[str, object]:
        return dict(self.row)

    def list_records(self, _resource: str, **_query: object) -> dict[str, object]:
        return {"items": [dict(self.row)], "page": 1, "page_size": 20, "total": 1, "has_next": False}

    def update_record(self, _resource: str, _record_id: int, payload: dict[str, object], *, expected_version: int, **_context: object) -> dict[str, object]:
        if int(self.row["row_version"]) != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        self.row.update(payload)
        self.row["row_version"] = expected_version + 1
        return dict(self.row)

    def set_status(self, _resource: str, _record_id: int, status: str, *, expected_version: int, user_id: int, evidence_attachment_ids: list[int] | None = None, **_context: object) -> dict[str, object]:
        if int(self.row["row_version"]) != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        self.row.update(status=status, row_version=expected_version + 1, updated_by=user_id)
        if evidence_attachment_ids:
            self.row["evidence_attachment_ids"] = evidence_attachment_ids
        return dict(self.row)

    def create_correction(self, _resource: str, record_id: int, payload: dict[str, object], *, user_id: int, **_context: object) -> dict[str, object]:
        return {**self.row, **payload, "id": 2, "correction_of_id": record_id, "status": "draft", "row_version": 1, "created_by": user_id}


def actor(user_id: int, *permissions: str) -> dict[str, object]:
    return {"id": user_id, "permissions": list(permissions), "data_scopes": []}


def test_verified_warehouse_record_is_read_only() -> None:
    service = WarehouseService(Store({"id": 1, "status": "verified", "row_version": 3, "created_by": 1}))
    with pytest.raises(DomainError, match="RECORD_READ_ONLY"):
        service.update(actor(2, "warehouse.manage"), "receipts", 1, {"expected_version": 3, "quantity": 12})


def test_verification_requires_evidence_and_separate_actor() -> None:
    row = {"id": 1, "status": "submitted", "row_version": 2, "created_by": 7, "updated_by": 7, "evidence_attachment_ids": []}
    service = WarehouseService(Store(row))

    with pytest.raises(DomainError, match="EVIDENCE_REQUIRED"):
        service.verify(actor(8, "warehouse.verify"), "scraps", 1, {"expected_version": 2})
    with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
        service.verify(actor(7, "warehouse.verify"), "scraps", 1, {"expected_version": 2, "evidence_attachment_ids": [9]})


def test_submitted_edit_invalidates_stale_warehouse_verification() -> None:
    store = Store({"id": 1, "status": "submitted", "row_version": 2, "created_by": 7, "updated_by": 7, "quantity": 10})
    service = WarehouseService(store)

    changed = service.update(actor(7, "warehouse.manage"), "receipts", 1, {"expected_version": 2, "quantity": 12})
    assert changed["version"] == 3
    with pytest.raises(DomainError, match="VERSION_CONFLICT"):
        service.verify(actor(8, "warehouse.verify"), "receipts", 1, {"expected_version": 2, "evidence_attachment_ids": [9]})
    verified = service.verify(actor(8, "warehouse.verify"), "receipts", 1, {"expected_version": 3, "evidence_attachment_ids": [9]})
    assert verified["status"] == "verified"
    assert verified["allowed_actions"] == ["view"]


def test_verified_warehouse_record_creates_a_linked_correction() -> None:
    original = {"id": 1, "code": "IN-1", "name": "入库", "status": "verified", "row_version": 3, "created_by": 7, "quantity": 10}
    service = WarehouseService(Store(original))

    correction = service.correct(actor(8, "warehouse.manage"), "receipts", 1, {
        "expected_version": 3, "code": "IN-1-C1", "name": "入库更正", "quantity": 12, "correction_reason": "复核送货单",
    })

    assert correction["correction_of_id"] == 1
    assert correction["status"] == "draft"
    assert correction["allowed_actions"] == ["view", "edit", "delete", "submit"]


@pytest.mark.parametrize("resource", ["stocktakes", "scraps"])
def test_stocktake_and_scrap_require_a_specific_inventory_lot(resource: str) -> None:
    with pytest.raises(DomainError, match="WAREHOUSE_LOT_REQUIRED"):
        WarehouseService._validate(resource, {"warehouse_id": 1, "material_id": 2, "quantity": 1})


def test_actual_issue_requires_a_verified_request_with_remaining_quantity() -> None:
    class Cursor:
        def execute(self, sql: str, _params: tuple[object, ...]) -> None:
            self.sql = sql

        @staticmethod
        def fetchone() -> None:
            return None

    row = {"id": 9, "source_document_id": 5, "material_id": 7, "pond_id": 3, "quantity": 20}
    with pytest.raises(DomainError, match="WAREHOUSE_ISSUE_REQUEST_INVALID"):
        WarehouseLedgerPoster._validate_issue_request(Cursor(), row)

    with pytest.raises(DomainError, match="WAREHOUSE_ISSUE_REQUEST_REQUIRED"):
        WarehouseService._validate("issues", {"warehouse_id": 1, "material_id": 7, "quantity": 20})


class TransferStore(Store):
    def dispatch_transfer(self, _record_id: int, *, expected_version: int, user_id: int) -> dict[str, object]:
        if int(self.row["row_version"]) != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        self.row.update(status="in_transit", row_version=expected_version + 1, dispatched_by=user_id)
        return dict(self.row)

    def receive_transfer(self, _record_id: int, *, expected_version: int, user_id: int, received_quantity: Decimal, difference_reason: str | None) -> dict[str, object]:
        if int(self.row["row_version"]) != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        self.row.update(status="verified", row_version=expected_version + 1, received_by=user_id,
                        received_quantity=received_quantity, receipt_difference_reason=difference_reason)
        return dict(self.row)

    def cancel_transfer(self, _record_id: int, *, expected_version: int, user_id: int, reason: str) -> dict[str, object]:
        if int(self.row["row_version"]) != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        self.row.update(status="cancelled", row_version=expected_version + 1, cancelled_by=user_id, cancellation_reason=reason)
        return dict(self.row)


def test_transfer_is_dispatched_to_in_transit_before_another_user_receives_it() -> None:
    store = TransferStore({"id": 4, "status": "submitted", "row_version": 2, "created_by": 7, "updated_by": 7, "quantity": 10})
    service = WarehouseService(store)

    dispatched = service.dispatch(actor(8, "warehouse.verify"), "transfers", 4, {"expected_version": 2})
    assert dispatched["status"] == "in_transit"
    assert dispatched["allowed_actions"] == ["view", "receive", "cancel"]
    received = service.receive(actor(9, "warehouse.verify", "warehouse.manage"), "transfers", 4, {
        "expected_version": 3, "received_quantity": 10,
    })
    assert received["status"] == "verified"
    assert received["allowed_actions"] == ["view", "correct"]


def test_transfer_receipt_difference_requires_a_reason() -> None:
    store = TransferStore({"id": 4, "status": "in_transit", "row_version": 3, "created_by": 7, "dispatched_by": 8, "quantity": 10})
    service = WarehouseService(store)

    with pytest.raises(DomainError, match="TRANSFER_DIFFERENCE_REASON_REQUIRED"):
        service.receive(actor(9, "warehouse.verify"), "transfers", 4, {
            "expected_version": 3, "received_quantity": 9,
        })


def test_in_transit_transfer_can_only_be_cancelled_with_a_reason() -> None:
    store = TransferStore({"id": 4, "status": "in_transit", "row_version": 3, "created_by": 7, "dispatched_by": 8, "quantity": 10})
    service = WarehouseService(store)

    with pytest.raises(DomainError, match="TRANSFER_CANCELLATION_REASON_REQUIRED"):
        service.cancel_transfer(actor(9, "warehouse.verify"), "transfers", 4, {"expected_version": 3})
    cancelled = service.cancel_transfer(actor(9, "warehouse.verify"), "transfers", 4, {
        "expected_version": 3, "cancellation_reason": "目标仓临时关闭",
    })
    assert cancelled["status"] == "cancelled"
    assert cancelled["allowed_actions"] == ["view"]


def test_transfer_cancel_uses_the_governance_work_item_column() -> None:
    source = getsource(cancel_transfer)

    assert "work_items SET status='cancelled'" in source
    assert "cancel_reason=%s" in source


def test_alert_handling_persists_an_action_and_resolution_note() -> None:
    class AlertStore:
        @staticmethod
        def handle_alert(_user: dict[str, object], alert_key: str, *, action_code: str, resolution_note: str, user_id: int) -> dict[str, object]:
            return {"alert_key": alert_key, "status": "handled", "action_code": action_code,
                    "resolution_note": resolution_note, "handled_by": user_id}

    service = WarehouseService(AlertStore())
    handled = service.handle_alert(actor(9, "warehouse.manage"), "3:8:low_stock", {
        "action_code": "replenish", "resolution_note": "采购申请 PR-009 已提交",
    })

    assert handled["status"] == "handled"
    assert handled["handled_by"] == 9


def test_alert_handling_requires_a_supported_action_and_note() -> None:
    service = WarehouseService(object())
    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_ACTION_INVALID"):
        service.handle_alert(actor(9, "warehouse.manage"), "3:8:low_stock", {
            "action_code": "ignore", "resolution_note": "忽略",
        })
    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_NOTE_REQUIRED"):
        service.handle_alert(actor(9, "warehouse.manage"), "3:8:low_stock", {
            "action_code": "replenish",
        })


def test_warehouse_routes_are_registered_and_authorized() -> None:
    auth = FakeAuthStore()
    account = auth.add_user(phone="13800000707", login_name="warehouse-admin", password="Correct9!", status="active")
    account["permissions"] = ["warehouse.view", "warehouse.manage", "warehouse.verify"]
    settings = Settings.from_env({
        "APP_ENV": "test", "FLASK_SECRET_KEY": "warehouse-test", "CSRF_SECRET_KEY": "warehouse-csrf",
        "MYSQL_HOST": "127.0.0.1", "MYSQL_DATABASE": "adp_test", "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test", "SESSION_COOKIE_SECURE": "false",
    })
    row = {"id": 1, "code": "IN-1", "name": "采购入库", "status": "submitted", "row_version": 2, "created_by": 8}
    client = create_app(settings, store=auth, warehouse_store=Store(row)).test_client()
    token = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    assert client.post("/api/v1/auth/login", json={"identifier": "warehouse-admin", "password": "Correct9!"}, headers={"X-CSRF-Token": token}).status_code == 200

    response = client.get("/api/v1/warehouse/receipts")
    assert response.status_code == 200
    assert response.get_json()["data"]["items"][0]["allowed_actions"] == ["view", "edit", "verify"]

    invalid_page = client.get("/api/v1/warehouse/ledger?page=not-a-number")
    assert invalid_page.status_code == 400
    assert invalid_page.get_json()["code"] == "WAREHOUSE_PAGE_INVALID"


def test_warehouse_migration_declares_traceable_immutable_ledger() -> None:
    sql = (ROOT / "database/migrations/010_warehouse.sql").read_text(encoding="utf-8")
    for marker in (
        "CREATE TABLE warehouses", "CREATE TABLE inventory_lots", "CREATE TABLE warehouse_documents",
        "CREATE TABLE inventory_ledger", "material_issue_request_id", "FOREIGN KEY",
        "inventory_ledger_no_update", "inventory_ledger_no_delete", "warehouse_documents_no_formal_delete",
        "in_transit", "received_quantity", "dispatched_by", "received_by", "cancellation_reason", "cancelled_by",
        "CREATE TABLE warehouse_alert_actions", "condition_fingerprint", "resolution_note",
    ):
        assert marker in sql
