from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.purchase.purchase_service import PurchaseService
from fake_auth_store import FakeAuthStore


ROOT = Path(__file__).parents[2]


class PurchaseStore:
    def __init__(self) -> None:
        self.orders: dict[int, dict[str, Any]] = {}
        self.payments: dict[int, dict[str, Any]] = {}
        self.next_id = 1

    def create_order(self, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        del user
        row = {**payload, "id": self.next_id, "status": "draft", "row_version": 1, "created_by": user_id}
        row["total_amount"] = float(row["quantity"]) * float(row["unit_price"])
        self.orders[self.next_id] = row
        self.next_id += 1
        return dict(row)

    def get_order(self, order_id: int, **_context: Any) -> dict[str, Any] | None:
        return dict(self.orders[order_id]) if order_id in self.orders else None

    def update_order(self, order_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        del user
        row = self.orders[order_id]
        if row["row_version"] != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        row.update(payload, updated_by=user_id, row_version=expected_version + 1)
        row["total_amount"] = float(row["quantity"]) * float(row["unit_price"])
        return dict(row)

    def set_order_status(self, order_id: int, status: str, *, expected_version: int, user_id: int, **_context: Any) -> dict[str, Any]:
        row = self.orders[order_id]
        if row["row_version"] != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        row.update(status=status, updated_by=user_id, row_version=expected_version + 1)
        return dict(row)

    def cancel_order(self, order_id: int, *, expected_version: int, user_id: int, reason: str, **_context: Any) -> dict[str, Any]:
        row = self.set_order_status(order_id, "cancelled", expected_version=expected_version, user_id=user_id)
        self.orders[order_id]["cancellation_reason"] = reason
        return {**row, "cancellation_reason": reason}

    def delete_order_draft(self, order_id: int, *, user_id: int, **_context: Any) -> dict[str, Any]:
        del user_id
        return self.orders.pop(order_id)

    def list_orders(self, **_query: Any) -> dict[str, Any]:
        return {"items": list(self.orders.values()), "page": 1, "page_size": 20, "total": len(self.orders), "has_next": False}

    def create_payment(self, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        del user
        row = {**payload, "id": self.next_id, "status": "draft", "row_version": 1, "created_by": user_id}
        self.payments[self.next_id] = row
        self.next_id += 1
        return dict(row)

    def get_payment(self, payment_id: int, **_context: Any) -> dict[str, Any] | None:
        return dict(self.payments[payment_id]) if payment_id in self.payments else None

    def update_payment(self, payment_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        del user
        row = self.payments[payment_id]
        row.update(payload, updated_by=user_id, row_version=expected_version + 1)
        return dict(row)

    def set_payment_status(self, payment_id: int, status: str, *, expected_version: int, user_id: int, evidence_attachment_ids: list[int] | None = None, **_context: Any) -> dict[str, Any]:
        row = self.payments[payment_id]
        row.update(status=status, updated_by=user_id, row_version=expected_version + 1)
        if evidence_attachment_ids:
            row["evidence_attachment_ids"] = evidence_attachment_ids
        return dict(row)

    def cancel_payment(self, payment_id: int, *, expected_version: int, user_id: int, reason: str, **_context: Any) -> dict[str, Any]:
        row = self.set_payment_status(payment_id, "cancelled", expected_version=expected_version, user_id=user_id)
        self.payments[payment_id]["cancellation_reason"] = reason
        return {**row, "cancellation_reason": reason}

    def delete_payment_draft(self, payment_id: int, *, user_id: int, **_context: Any) -> dict[str, Any]:
        del user_id
        return self.payments.pop(payment_id)

    def list_payables(self, **_query: Any) -> dict[str, Any]:
        return {"items": [], "page": 1, "page_size": 20, "total": 0, "has_next": False}

    def list_payments(self, **_query: Any) -> dict[str, Any]:
        return {"items": list(self.payments.values()), "page": 1, "page_size": 20, "total": len(self.payments), "has_next": False}


def actor(user_id: int, *permissions: str) -> dict[str, Any]:
    return {"id": user_id, "permissions": list(permissions), "data_scopes": []}


def order_payload() -> dict[str, Any]:
    return {
        "code": "PO-1", "name": "饲料采购", "supplier_id": 5, "material_id": 8,
        "warehouse_id": 3, "quantity": 100, "unit_price": 6.5,
        "expected_delivery_date": "2026-08-25", "due_date": "2026-09-25",
    }


def test_submitted_purchase_order_stays_editable_until_separate_approval() -> None:
    service = PurchaseService(PurchaseStore())
    purchaser = actor(7, "purchase.view", "purchase.manage")
    approver = actor(8, "purchase.view", "purchase.verify")

    order = service.create_order(purchaser, order_payload())
    order = service.submit_order(purchaser, order["id"], {"expected_version": 1})
    assert order["allowed_actions"] == ["view", "edit"]
    order = service.update_order(purchaser, order["id"], {"expected_version": 2, "quantity": 120})
    assert order["version"] == 3
    with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
        service.approve_order(actor(7, "purchase.verify"), order["id"], {"expected_version": 3})
    order = service.approve_order(approver, order["id"], {"expected_version": 3})
    assert order["status"] == "approved"
    assert order["allowed_actions"] == ["view", "cancel"]
    with pytest.raises(DomainError, match="RECORD_READ_ONLY"):
        service.update_order(purchaser, order["id"], {"expected_version": 4, "quantity": 130})


def test_purchase_due_date_cannot_precede_expected_delivery() -> None:
    service = PurchaseService(PurchaseStore())
    with pytest.raises(DomainError, match="PURCHASE_DATE_INVALID"):
        service.create_order(actor(7, "purchase.manage"), {**order_payload(), "expected_delivery_date": "2026-09-25", "due_date": "2026-09-01"})


def test_partially_received_order_still_allows_remaining_receipt() -> None:
    store = PurchaseStore()
    store.orders[1] = {**order_payload(), "id": 1, "status": "partially_received", "row_version": 4, "created_by": 7}
    page = PurchaseService(store).list_orders(actor(3, "purchase.view", "warehouse.manage"))

    assert page["items"][0]["allowed_actions"] == ["view", "receive"]


def test_payment_requires_voucher_and_separate_verifier() -> None:
    service = PurchaseService(PurchaseStore())
    maker = actor(11, "finance.payable.view", "finance.payment.manage")
    checker = actor(12, "finance.payable.view", "finance.payment.verify")
    payment = service.create_payment(maker, {
        "code": "PAY-1", "name": "饲料款", "payable_id": 4, "amount": 1000, "paid_at": "2026-08-17", "payment_method": "bank_transfer",
    })
    payment = service.submit_payment(maker, payment["id"], {"expected_version": 1})

    with pytest.raises(DomainError, match="EVIDENCE_REQUIRED"):
        service.verify_payment(checker, payment["id"], {"expected_version": 2})
    with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
        service.verify_payment(actor(11, "finance.payment.verify"), payment["id"], {
            "expected_version": 2, "evidence_attachment_ids": [9],
        })
    payment = service.verify_payment(checker, payment["id"], {
        "expected_version": 2, "evidence_attachment_ids": [9],
    })
    assert payment["status"] == "verified"
    assert payment["allowed_actions"] == ["view", "reverse"]


def test_payment_cannot_be_reassigned_to_another_payable() -> None:
    service = PurchaseService(PurchaseStore())
    maker = actor(11, "finance.payable.view", "finance.payment.manage")
    payment = service.create_payment(maker, {
        "code": "PAY-LOCKED-SOURCE", "name": "锁定应付来源", "payable_id": 4,
        "amount": 100, "paid_at": "2026-08-17", "payment_method": "bank_transfer",
    })

    with pytest.raises(DomainError, match="PURCHASE_FIELD_INVALID"):
        service.update_payment(maker, payment["id"], {"expected_version": 1, "payable_id": 5})


def test_payment_method_is_a_bounded_business_enum() -> None:
    service = PurchaseService(PurchaseStore())
    with pytest.raises(DomainError, match="PAYMENT_METHOD_INVALID"):
        service.create_payment(actor(11, "finance.payment.manage"), {
            "code": "PAY-METHOD", "name": "非法方式", "payable_id": 4, "amount": 100,
            "paid_at": "2026-08-17", "payment_method": "x" * 40,
        })


@pytest.mark.parametrize("invalid", ["nan", "inf", "-inf"])
def test_purchase_amounts_reject_non_finite_numbers(invalid: str) -> None:
    with pytest.raises(DomainError, match="PURCHASE_AMOUNT_INVALID"):
        PurchaseService._positive({"quantity": invalid}, "quantity")


def test_drafts_delete_but_submitted_records_only_cancel_with_history() -> None:
    store = PurchaseStore()
    service = PurchaseService(store)
    maker = actor(7, "purchase.manage", "finance.payment.manage")
    checker = actor(8, "purchase.verify", "finance.payment.verify")

    draft = service.create_order(maker, order_payload())
    service.delete_order(maker, draft["id"])
    assert store.get_order(draft["id"]) is None
    order = service.create_order(maker, {**order_payload(), "code": "PO-2"})
    order = service.submit_order(maker, order["id"], {"expected_version": order["version"]})
    with pytest.raises(DomainError, match="DELETE_NOT_ALLOWED"):
        service.delete_order(maker, order["id"])
    order = service.cancel_order(checker, order["id"], {
        "expected_version": order["version"], "cancellation_reason": "供应商无法履约",
    })
    assert order["status"] == "cancelled" and store.get_order(order["id"])["cancellation_reason"] == "供应商无法履约"

    draft_payment = service.create_payment(maker, {
        "code": "PAY-DRAFT", "name": "付款草稿", "payable_id": 4, "amount": 100, "paid_at": "2026-08-17", "payment_method": "bank_transfer",
    })
    service.delete_payment(maker, draft_payment["id"])
    assert store.get_payment(draft_payment["id"]) is None
    payment = service.create_payment(maker, {
        "code": "PAY-2", "name": "已提交付款", "payable_id": 4, "amount": 100, "paid_at": "2026-08-17", "payment_method": "bank_transfer",
    })
    payment = service.submit_payment(maker, payment["id"], {"expected_version": payment["version"]})
    payment = service.cancel_payment(checker, payment["id"], {
        "expected_version": payment["version"], "cancellation_reason": "付款账户错误",
    })
    assert payment["status"] == "cancelled" and store.get_payment(payment["id"])["cancellation_reason"] == "付款账户错误"


def test_purchase_migration_declares_traceable_payables_and_no_formal_delete() -> None:
    original = (ROOT / "database/migrations/011_purchase_payables.sql").read_text(encoding="utf-8")
    sql = (ROOT / "database/migrations/012_purchase_hardening.sql").read_text(encoding="utf-8")
    schema = (ROOT / "database/schema.sql").read_text(encoding="utf-8")
    for marker in (
        "CREATE TABLE purchase_payable_adjustments", "CREATE TABLE purchase_payment_reversals",
        "ADD COLUMN payment_method", "purchase_payable_adjustments_no_update",
        "purchase_payment_reversals_no_update", "ON DELETE RESTRICT",
    ):
        assert marker in sql
    assert "payment_method" not in original and "purchase_payment_reversals" not in original
    assert "SOURCE database/migrations/011_purchase_payables.sql;" in schema
    assert "SOURCE database/migrations/012_purchase_hardening.sql;" in schema


def test_purchase_routes_are_registered_and_authorized() -> None:
    auth = FakeAuthStore()
    account = auth.add_user(phone="13800000808", login_name="purchase-admin", password="Correct9!", status="active")
    account["permissions"] = [
        "purchase.view", "purchase.manage", "purchase.verify", "finance.payable.view",
        "finance.payment.manage", "finance.payment.verify",
    ]
    settings = Settings.from_env({
        "APP_ENV": "test", "FLASK_SECRET_KEY": "purchase-test", "CSRF_SECRET_KEY": "purchase-csrf",
        "MYSQL_HOST": "127.0.0.1", "MYSQL_DATABASE": "adp_test", "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test", "SESSION_COOKIE_SECURE": "false",
    })
    client = create_app(settings, store=auth, purchase_store=PurchaseStore()).test_client()
    token = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    assert client.post("/api/v1/auth/login", json={"identifier": "purchase-admin", "password": "Correct9!"}, headers={"X-CSRF-Token": token}).status_code == 200

    assert client.get("/api/v1/purchase/orders").status_code == 200
    assert client.get("/api/v1/purchase/payables").status_code == 200
    assert client.get("/api/v1/purchase/payments").status_code == 200
