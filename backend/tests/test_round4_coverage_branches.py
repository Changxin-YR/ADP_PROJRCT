from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.cost.cost_enterprise_service import CostEnterpriseService
from backend.layers.features.production.production_service import ProductionService
from backend.layers.features.purchase.purchase_service import PurchaseService
from backend.layers.features.sales.sales_service import SalesService
from backend.layers.features.warehouse.warehouse_service import WarehouseService


def actor(*permissions: str) -> dict[str, Any]:
    return {"id": 7, "permissions": list(permissions), "data_scopes": []}


class ProductionStore:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row
        self.calls: list[tuple[str, Any]] = []

    def list_records(self, resource: str, **_: Any) -> dict[str, Any]:
        return {"items": [self.row], "page": 1, "page_size": 20, "total": 1, "has_next": False}

    def get_record(self, resource: str, record_id: int) -> dict[str, Any]:
        return self.row

    def update_record(self, resource: str, record_id: int, payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        self.calls.append(("update", payload))
        return {**self.row, **payload, "row_version": 2}

    def set_status(self, resource: str, record_id: int, status: str, **_: Any) -> dict[str, Any]:
        self.calls.append(("status", status))
        return {**self.row, "status": status, "row_version": 2}

    def delete_draft(self, resource: str, record_id: int, **_: Any) -> dict[str, Any]:
        self.calls.append(("delete", record_id))
        return self.row


def test_production_service_validation_and_transitions_have_business_assertions() -> None:
    user = actor("production.view", "production.manage", "production.verify")
    row = {
        "id": 1,
        "code": "P-1",
        "name": "生产记录",
        "status": "submitted",
        "row_version": 1,
        "organization_id": 1,
        "farm_id": 1,
        "area_id": 1,
        "pond_id": 1,
        "created_by": 2,
    }
    store = ProductionStore(row)
    service = ProductionService(store)

    with pytest.raises(DomainError, match="PRODUCTION_RESOURCE_NOT_FOUND"):
        service.resource("unknown")
    with pytest.raises(DomainError, match="PRODUCTION_REQUIRED_FIELDS"):
        service.create(user, "samplings", {"code": "", "name": ""})
    with pytest.raises(DomainError, match="TRANSFER_TARGET_INVALID"):
        service.create(user, "transfers", {"code": "T", "name": "调拨", "pond_id": 1, "target_pond_id": 1, "quantity": 1, "weight_kg": 1})
    with pytest.raises(DomainError, match="FEED_PLAN_REQUIRED_FIELDS"):
        service.submit(user, "feed-plans", 1, {"expected_version": 1})

    listed = service.list_records(user, "samplings")
    assert listed["total"] == 1 and listed["items"][0]["code"] == "P-1"
    updated = service.update(user, "samplings", 1, {"expected_version": 1, "name": "已更新"})
    assert updated["name"] == "已更新" and store.calls[-1][0] == "update"
    with pytest.raises(DomainError, match="INVALID_STATE_TRANSITION"):
        service.submit(user, "samplings", 1, {"expected_version": 1})
    draft_service = ProductionService(ProductionStore({**row, "status": "draft", "row_version": 1}))
    submitted = draft_service.submit(user, "samplings", 1, {"expected_version": 1})
    assert submitted["status"] == "submitted"
    with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
        service.verify({**user, "id": 2}, "samplings", 1, {"expected_version": 1})

    draft_store = ProductionStore({**row, "status": "draft", "row_version": 1})
    assert ProductionService(draft_store).delete(user, "samplings", 1)["status"] == "draft"


class WarehouseStore:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row
        self.calls: list[str] = []

    def get_record(self, resource: str, record_id: int) -> dict[str, Any]:
        return self.row

    def create_record(self, resource: str, payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        self.calls.append("create")
        return {**payload, "id": 2, "status": "draft", "row_version": 1}

    def set_status(self, resource: str, record_id: int, status: str, **_: Any) -> dict[str, Any]:
        self.calls.append(status)
        return {**self.row, "status": status, "row_version": 2}

    def delete_draft(self, resource: str, record_id: int, **_: Any) -> dict[str, Any]:
        self.calls.append("delete")
        return self.row

    def list_ledger(self, user: dict[str, Any], **query: Any) -> dict[str, Any]:
        return {"items": [], "total": 0, **query}

    def list_alerts(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def list_warehouses(self, user: dict[str, Any], **_: Any) -> list[dict[str, Any]]:
        return [{"id": 1, "status": "active"}]


def test_warehouse_service_rejects_invalid_business_operations() -> None:
    user = actor("warehouse.view", "warehouse.manage", "warehouse.verify")
    row = {"id": 1, "code": "W-1", "name": "入库", "status": "submitted", "row_version": 1, "warehouse_id": 1, "material_id": 1, "created_by": 2}
    service = WarehouseService(WarehouseStore(row))
    with pytest.raises(DomainError, match="WAREHOUSE_RESOURCE_NOT_FOUND"):
        service.resource("bad")
    with pytest.raises(DomainError, match="WAREHOUSE_REQUIRED_FIELDS"):
        service.create(user, "receipts", {"code": "W"})
    with pytest.raises(DomainError, match="WAREHOUSE_TRANSFER_TARGET_INVALID"):
        service.create(user, "transfers", {"code": "T", "name": "调拨", "warehouse_id": 1, "target_warehouse_id": 1, "material_id": 1, "quantity": 1})
    with pytest.raises(DomainError, match="WAREHOUSE_TRANSFER_TARGET_INVALID"):
        WarehouseService._validate("transfers", {"warehouse_id": 1, "target_warehouse_id": 1, "quantity": 1})
    with pytest.raises(DomainError, match="WAREHOUSE_DATE_INVALID"):
        WarehouseService._validate("receipts", {"quantity": 1, "happened_at": "not-a-date"})
    with pytest.raises(DomainError, match="TRANSFER_RESOURCE_REQUIRED"):
        service.dispatch(user, "receipts", 1, {"expected_version": 1})
    with pytest.raises(DomainError, match="TRANSFER_CANCELLATION_REASON_REQUIRED"):
        service.cancel_transfer(user, "transfers", 1, {"expected_version": 1})
    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_PAYLOAD_INVALID"):
        service.handle_alert(user, "alert", None)
    assert service.ledger(user, page=1)["total"] == 0
    assert service.warehouses(user)[0]["status"] == "active"


class CostStore:
    def __init__(self) -> None:
        self.rows = {
            "expense": {"id": 1, "status": "draft", "row_version": 1, "amount": Decimal("12.345"), "created_by": 2},
            "asset": {"id": 2, "status": "submitted", "row_version": 1, "created_by": 2},
            "settlement": {"id": 3, "status": "draft", "row_version": 1, "created_by": 2},
        }
        self.calls: list[str] = []

    def get_expense(self, record_id: int, **_: Any) -> dict[str, Any]:
        return self.rows["expense"]

    def get_asset(self, record_id: int, **_: Any) -> dict[str, Any]:
        return self.rows["asset"]

    def get_settlement(self, record_id: int, **_: Any) -> dict[str, Any]:
        return self.rows["settlement"]

    def create_expense(self, payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        self.calls.append("create_expense")
        return {**self.rows["expense"], **payload}

    def update_expense(self, record_id: int, payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        self.calls.append("update_expense")
        return {**self.rows["expense"], **payload, "row_version": 2}

    def transition_expense(self, record_id: int, status: str, **_: Any) -> dict[str, Any]:
        self.calls.append(f"expense:{status}")
        return {**self.rows["expense"], "status": status, "row_version": 2}

    def delete_expense(self, record_id: int, **_: Any) -> dict[str, Any]:
        self.calls.append("delete_expense")
        return self.rows["expense"]

    def transition_asset(self, record_id: int, status: str, **_: Any) -> dict[str, Any]:
        self.calls.append(f"asset:{status}")
        return {**self.rows["asset"], "status": status}

    def depreciate_asset(self, record_id: int, **_: Any) -> dict[str, Any]:
        self.calls.append("depreciate")
        return {"status": "confirmed", "amount": Decimal("1.00")}

    def run_allocation(self, **_: Any) -> dict[str, Any]:
        self.calls.append("allocation")
        return {"id": 4, "amount": Decimal("2.00")}

    def create_settlement(self, payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        self.calls.append("settlement")
        return {**self.rows["settlement"], **payload}

    def update_settlement(self, record_id: int, name: str, **_: Any) -> dict[str, Any]:
        self.calls.append("settlement_update")
        return {**self.rows["settlement"], "name": name, "row_version": 2}

    def update_asset(self, record_id: int, payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        self.calls.append("asset_update")
        return {**self.rows["asset"], **payload, "row_version": 2}

    def delete_asset(self, record_id: int, **_: Any) -> dict[str, Any]:
        self.calls.append("asset_delete")
        return self.rows["asset"]

    def reverse_expense(self, record_id: int, **_: Any) -> dict[str, Any]:
        self.calls.append("expense_reverse")
        return {**self.rows["expense"], "status": "reversed"}

    def reverse_settlement(self, record_id: int, **_: Any) -> dict[str, Any]:
        self.calls.append("settlement_reverse")
        return {**self.rows["settlement"], "status": "reversed"}


def test_cost_enterprise_state_machine_serializes_and_checks_scope() -> None:
    store = CostStore()
    service = CostEnterpriseService(store)
    manage = actor("cost.entry.manage", "cost.entry.verify", "cost.entry.confirm", "cost.asset.manage", "cost.asset.verify", "cost.asset.confirm", "cost.allocation.manage", "cost.settlement.manage")
    with pytest.raises(DomainError, match="COST_DATE_INVALID"):
        service.dates({"period_start": "bad", "period_end": "2026-09-01"})
    with pytest.raises(DomainError, match="COST_PERIOD_INVALID"):
        service.dates({"period_start": "2026-09-02", "period_end": "2026-09-01"})
    with pytest.raises(DomainError, match="EVIDENCE_INVALID"):
        service.evidence_ids("invalid")
    assert service.serialize({"amount": Decimal("1.235"), "at": date(2026, 9, 8)}) == {"amount": "1.24", "at": "2026-09-08"}
    expense = {"period_start": "2026-09-01", "period_end": "2026-09-30", "amount": "3.00", "category_code": "feed", "occurred_on": "2026-09-08", "source_type": "manual", "source_ref": "ROUND4"}
    assert service.create_expense(manage, expense)["status"] == "draft"
    updated_expense = {**expense, "expected_version": 1, "amount": "4.00"}
    assert service.update_expense(manage, 1, updated_expense)["row_version"] == 2
    assert service.submit_expense(manage, 1, {"expected_version": 1})["allowed_actions"] == ["view", "edit", "verify"]
    assert service.depreciate_asset(manage, 2, {"period": "2026-09"})["amount"] == "1.00"
    assert service.run_allocation(manage, {"period_start": "2026-09-01", "period_end": "2026-09-30", "farm_id": 1})["amount"] == "2.00"
    assert service.create_settlement(manage, {"period_start": "2026-09-01", "period_end": "2026-09-30", "allocation_run_id": 4})["status"] == "draft"
    assert "allocation" in store.calls and "settlement" in store.calls
    assert service.result({"status": "submitted", "row_version": 1}, manage, "entry")["allowed_actions"] == ["view", "edit", "verify"]
    assert service.result({"status": "verified", "row_version": 1}, manage, "entry")["allowed_actions"] == ["view", "confirm"]
    assert service.result({"status": "confirmed", "row_version": 1, "source_type": "manual"}, manage, "entry")["allowed_actions"] == ["view"]
    assert service.result({"status": "confirmed", "row_version": 1}, manage, "asset")["allowed_actions"] == ["view", "depreciate"]
    with pytest.raises(DomainError, match="DEPRECIATION_PERIOD_INVALID"):
        service.depreciate_asset(manage, 2, {"period": "2026"})
    with pytest.raises(DomainError, match="COST_ALLOCATION_SCOPE_REQUIRED"):
        service.run_allocation(manage, {"period_start": "2026-09-01", "period_end": "2026-09-30", "farm_id": 0})
    with pytest.raises(DomainError, match="COST_ALLOCATION_RUN_INVALID"):
        service.create_settlement(manage, {"period_start": "2026-09-01", "period_end": "2026-09-30", "allocation_run_id": 0})


def test_cost_enterprise_failure_paths_and_asset_lifecycle_are_explicit() -> None:
    manage = actor("cost.view", "cost.entry.manage", "cost.entry.reverse", "cost.asset.manage", "cost.settlement.manage", "cost.settlement.reverse")
    store = CostStore()
    service = CostEnterpriseService(store)

    class Missing(CostStore):
        def get_expense(self, *_: Any, **__: Any) -> None: return None
    with pytest.raises(DomainError, match="COST_ENTRY_NOT_FOUND"):
        CostEnterpriseService(Missing()).get_expense(manage, 1)
    store.rows["expense"]["status"] = "confirmed"
    with pytest.raises(DomainError, match="RECORD_READ_ONLY"):
        service.update_expense(manage, 1, {"expected_version": 1})
    assert service.delete_expense(manage, 1)["status"] == "confirmed"
    with pytest.raises(DomainError, match="COST_REVERSAL_REASON_REQUIRED"):
        service.reverse_expense(manage, 1, {})
    store.rows["expense"].update(status="confirmed", source_type="manual")
    assert service.reverse_expense(manage, 1, {"reason": "更正"})["status"] == "reversed"
    asset_payload = {"code": "A", "name": "设备", "asset_type": "equipment", "category_code": "machine", "purchase_date": "2026-09-01", "original_value": "10.00", "salvage_value": "1.00", "useful_life_months": 12, "depreciation_start_date": "2026-09-01"}
    store.rows["asset"]["status"] = "draft"
    assert service.update_asset(manage, 2, {**asset_payload, "expected_version": 1})["row_version"] == 2
    assert service.delete_asset(manage, 2)["status"] == "draft"
    with pytest.raises(DomainError, match="COST_SETTLEMENT_FIELD_INVALID"):
        service.update_settlement(manage, 3, {"expected_version": 1, "amount": 1})
    with pytest.raises(DomainError, match="COST_SETTLEMENT_REVERSAL_REASON_REQUIRED"):
        service.reverse_settlement(manage, 3, {"expected_version": 1})


def test_remaining_business_guard_branches() -> None:
    checks = [
        (lambda: PurchaseService._clean({"forged": 1}, {"code"}), "PURCHASE_FIELD_INVALID"),
        (lambda: SalesService.clean({"forged": 1}, {"code"}), "SALES_FIELD_INVALID"),
        (lambda: WarehouseService.clean({"forged": 1}), "WAREHOUSE_FIELD_INVALID"),
        (lambda: ProductionService._clean("samplings", {"forged": 1}), "PRODUCTION_FIELD_INVALID"),
        (lambda: PurchaseService._validate_dates({"expected_delivery_date": "2026-09-10", "due_date": "2026-09-09"}), "PURCHASE_DATE_INVALID"),
        (lambda: SalesService.positive({"amount": -1}, "amount"), "SALES_AMOUNT_INVALID"),
        (lambda: WarehouseService._validate("receipts", {"quantity": -1}), "WAREHOUSE_QUANTITY_INVALID"),
        (lambda: ProductionService._positive({"quantity": -1}, "quantity"), "PRODUCTION_VALUE_INVALID"),
    ]
    for operation, error_code in checks:
        with pytest.raises(DomainError, match=error_code):
            operation()


class TransactionStore:
    def __init__(self) -> None:
        self.order = {"id": 1, "code": "O-1", "name": "订单", "status": "draft", "row_version": 1}
        self.payment = {"id": 2, "code": "PAY-1", "name": "付款", "status": "draft", "row_version": 1}
        self.sale = {"id": 3, "code": "S-1", "name": "销售", "status": "draft", "row_version": 1}
        self.receipt = {"id": 4, "code": "R-1", "name": "收款", "status": "draft", "row_version": 1}
        self.delivery_status = "draft"

    def get_order(self, *_: Any, **__: Any) -> dict[str, Any]: return self.order
    def create_order(self, payload: dict[str, Any], **_: Any) -> dict[str, Any]: return {**self.order, **payload}
    def set_order_status(self, _id: int, status: str, **_: Any) -> dict[str, Any]: return {**self.order, "status": status}
    def get_payment(self, *_: Any, **__: Any) -> dict[str, Any]: return self.payment
    def create_payment(self, payload: dict[str, Any], **_: Any) -> dict[str, Any]: return {**self.payment, **payload}
    def set_payment_status(self, _id: int, status: str, **_: Any) -> dict[str, Any]: return {**self.payment, "status": status}
    def list_orders(self, **_: Any) -> dict[str, Any]: return {"items": [self.order], "total": 1}
    def update_order(self, _id: int, payload: dict[str, Any], **_: Any) -> dict[str, Any]: return {**self.order, **payload, "row_version": 2}
    def cancel_order(self, _id: int, **_: Any) -> dict[str, Any]: return {**self.order, "status": "cancelled"}
    def delete_order_draft(self, _id: int, **_: Any) -> dict[str, Any]: return self.order
    def list_payables(self, **_: Any) -> dict[str, Any]: return {"items": [], "total": 0}
    def list_payments(self, **_: Any) -> dict[str, Any]: return {"items": [self.payment], "total": 1}
    def update_payment(self, _id: int, payload: dict[str, Any], **_: Any) -> dict[str, Any]: return {**self.payment, **payload, "row_version": 2}
    def cancel_payment(self, _id: int, **_: Any) -> dict[str, Any]: return {**self.payment, "status": "cancelled"}
    def delete_payment_draft(self, _id: int, **_: Any) -> dict[str, Any]: return self.payment
    def get_order_for_sales(self, *_: Any, **__: Any) -> dict[str, Any]: return self.sale
    def get_receipt(self, *_: Any, **__: Any) -> dict[str, Any]: return self.receipt
    def create_receipt(self, payload: dict[str, Any], **_: Any) -> dict[str, Any]: return {**self.receipt, **payload}

    def get_delivery(self, *_: Any, **__: Any) -> dict[str, Any]: return {"id": 5, "code": "D-1", "name": "交付", "status": self.delivery_status, "row_version": 1, "sales_order_id": 3, "harvest_document_id": 9, "quantity": 1, "created_by": 2}
    def create_delivery(self, payload: dict[str, Any], **_: Any) -> dict[str, Any]: return {**self.get_delivery(), **payload}
    def update_delivery(self, _id: int, payload: dict[str, Any], **_: Any) -> dict[str, Any]: return {**self.get_delivery(), **payload, "row_version": 2}
    def set_delivery_status(self, _id: int, status: str, **_: Any) -> dict[str, Any]: return {**self.get_delivery(), "status": status}
    def create_delivery_correction(self, _id: int, payload: dict[str, Any], **_: Any) -> dict[str, Any]: return {**self.get_delivery(), **payload, "status": "draft"}
    def delete_delivery_draft(self, _id: int, **_: Any) -> dict[str, Any]: return self.get_delivery()
    def cancel_delivery(self, _id: int, **_: Any) -> dict[str, Any]: return {**self.get_delivery(), "status": "cancelled"}
    def list_deliveries(self, **_: Any) -> dict[str, Any]: return {"items": [self.get_delivery()], "total": 1}
    def list_receivables(self, **_: Any) -> dict[str, Any]: return {"items": [], "total": 0}
    def list_receipts(self, **_: Any) -> dict[str, Any]: return {"items": [self.receipt], "total": 1}
    def update_receipt(self, _id: int, payload: dict[str, Any], **_: Any) -> dict[str, Any]: return {**self.receipt, **payload, "row_version": 2}
    def set_receipt_status(self, _id: int, status: str, **_: Any) -> dict[str, Any]: return {**self.receipt, "status": status}


def test_purchase_and_sales_boundaries_cover_financial_state_rules() -> None:
    purchase_user = actor("purchase.manage", "purchase.view", "purchase.verify", "finance.payment.manage", "finance.payment.verify", "finance.payable.view", "warehouse.manage")
    purchase = PurchaseService(TransactionStore())
    with pytest.raises(DomainError, match="PURCHASE_AMOUNT_INVALID"):
        purchase._positive({"quantity": 0}, "quantity")
    with pytest.raises(DomainError, match="PURCHASE_DATE_INVALID"):
        purchase._validate_dates({"expected_delivery_date": "bad"})
    with pytest.raises(DomainError, match="PURCHASE_REQUIRED_FIELDS"):
        purchase.create_order(purchase_user, {})
    order_payload = {"code": "PO", "name": "采购", "supplier_id": 1, "material_id": 1, "warehouse_id": 1, "quantity": 2, "unit_price": 3, "due_date": "2026-09-30"}
    assert purchase.create_order(purchase_user, order_payload)["code"] == "PO"
    assert purchase.submit_order(purchase_user, 1, {"expected_version": 1})["status"] == "submitted"
    cancel_store = TransactionStore()
    cancel_store.order["status"] = "submitted"
    with pytest.raises(DomainError, match="CANCELLATION_REASON_REQUIRED"):
        PurchaseService(cancel_store).cancel_order(purchase_user, 1, {"expected_version": 1})
    payment_payload = {"code": "PAY", "name": "付款", "payable_id": 1, "amount": 3, "paid_at": "2026-09-08", "payment_method": "cash"}
    assert purchase.create_payment(purchase_user, payment_payload)["code"] == "PAY"
    with pytest.raises(DomainError, match="PAYMENT_METHOD_INVALID"):
        purchase.create_payment(purchase_user, {**payment_payload, "payment_method": "wire"})
    assert purchase.payment_result({"status": "verified", "row_version": 1}, purchase_user)["allowed_actions"] == ["view", "reverse"]

    sales_user = actor("sales.manage", "sales.view", "sales.verify", "finance.receipt.manage", "finance.receipt.verify", "finance.receivable.view")
    class SalesStore(TransactionStore):
        def get_order(self, *_: Any, **__: Any) -> dict[str, Any]: return self.sale
        def create_order(self, payload: dict[str, Any], **_: Any) -> dict[str, Any]: return {**self.sale, **payload}
    sales = SalesService(SalesStore())
    with pytest.raises(DomainError, match="SALES_UNIT_INVALID"):
        sales.create_order(sales_user, {"code": "S", "name": "销售", "customer_id": 1, "pond_id": 1, "batch_id": 1, "species": "鱼", "quantity": 1, "unit": "box", "unit_price": 3, "sold_at": "2026-09-08", "due_date": "2026-09-30"})
    with pytest.raises(DomainError, match="SALES_DATE_INVALID"):
        sales.validate_dates({"sold_at": "2026-09-09", "due_date": "2026-09-08"})
    sale_payload = {"code": "SO", "name": "销售", "customer_id": 1, "pond_id": 1, "batch_id": 1, "species": "鱼", "quantity": 1, "unit": "kg", "unit_price": 3, "sold_at": "2026-09-08", "due_date": "2026-09-30"}
    assert sales.create_order(sales_user, sale_payload)["code"] == "SO"
    receipt_payload = {"code": "REC", "name": "收款", "receivable_id": 1, "amount": 3, "received_at": "2026-09-08", "receipt_method": "cash"}
    assert sales.create_receipt(sales_user, receipt_payload)["code"] == "REC"
    with pytest.raises(DomainError, match="RECEIPT_METHOD_INVALID"):
        sales.create_receipt(sales_user, {**receipt_payload, "receipt_method": "wire"})
    assert sales.order_result({"status": "approved", "row_version": 1}, sales_user)["allowed_actions"] == ["view", "deliver"]
    assert purchase.order_result({"status": "draft", "row_version": 1}, purchase_user)["allowed_actions"] == ["view", "edit", "delete", "submit"]
    assert purchase.order_result({"status": "submitted", "row_version": 1}, purchase_user)["allowed_actions"] == ["view", "edit", "approve", "cancel"]
    assert purchase.order_result({"status": "approved", "row_version": 1}, purchase_user)["allowed_actions"] == ["view", "receive", "cancel"]
    assert sales.delivery_result({"status": "draft", "row_version": 1}, sales_user)["allowed_actions"] == ["view", "edit", "delete", "submit"]
    assert sales.delivery_result({"status": "submitted", "row_version": 1}, sales_user)["allowed_actions"] == ["view", "edit", "verify", "cancel"]
    assert sales.delivery_result({"status": "verified", "row_version": 1}, sales_user)["allowed_actions"] == ["view", "correct"]
    assert sales.receipt_result({"status": "submitted", "row_version": 1}, sales_user)["allowed_actions"] == ["view", "edit", "verify", "cancel"]


def test_purchase_and_sales_transition_failures_are_explicit() -> None:
    purchase_user = actor("purchase.manage", "purchase.view", "purchase.verify", "finance.payment.manage", "finance.payment.verify", "finance.payable.view")
    purchase_store = TransactionStore()
    purchase_store.order.update(status="draft", created_by=2)
    purchase = PurchaseService(purchase_store)
    assert purchase.list_orders(purchase_user)["total"] == 1
    assert purchase.update_order(purchase_user, 1, {"expected_version": 1, "name": "改名", "quantity": 2, "unit_price": 3, "due_date": "2026-09-30"})["row_version"] == 2
    assert purchase.delete_order(purchase_user, 1)["status"] == "draft"
    purchase_store.order["status"] = "submitted"
    with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
        purchase.approve_order({**purchase_user, "id": 2}, 1, {"expected_version": 1})
    assert purchase.cancel_order(purchase_user, 1, {"expected_version": 1, "cancellation_reason": "供应商取消"})["status"] == "cancelled"
    assert purchase.list_payables(purchase_user)["total"] == 0
    assert purchase.list_payments(purchase_user)["total"] == 1
    payment_store = TransactionStore()
    payment_store.payment.update(status="draft", created_by=2)
    payment = PurchaseService(payment_store)
    payment_payload = {"expected_version": 1, "amount": 3, "payment_method": "cash"}
    assert payment.update_payment(purchase_user, 2, payment_payload)["row_version"] == 2
    assert payment.delete_payment(purchase_user, 2)["status"] == "draft"
    payment_store.payment["status"] = "submitted"
    with pytest.raises(DomainError, match="EVIDENCE_REQUIRED"):
        payment.verify_payment(purchase_user, 2, {"expected_version": 1})
    with pytest.raises(DomainError, match="CANCELLATION_REASON_REQUIRED"):
        payment.cancel_payment(purchase_user, 2, {"expected_version": 1})

    sales_user = actor("sales.manage", "sales.view", "sales.verify", "finance.receipt.manage", "finance.receipt.verify", "finance.receivable.view")
    sales_store = TransactionStore()
    sales = SalesService(sales_store)
    assert sales.list_orders(sales_user)["total"] == 1
    assert sales.list_deliveries(sales_user)["total"] == 1
    delivery_payload = {"code": "D", "name": "交付", "sales_order_id": 3, "harvest_document_id": 9, "quantity": 1, "delivered_at": "2026-09-08"}
    assert sales.create_delivery(sales_user, delivery_payload)["code"] == "D"
    assert sales.update_delivery(sales_user, 5, {"expected_version": 1, "quantity": 2})["row_version"] == 2
    assert sales.submit_delivery(sales_user, 5, {"expected_version": 1})["status"] == "submitted"
    with pytest.raises(DomainError, match="EVIDENCE_REQUIRED"):
        sales.verify_delivery(sales_user, 5, {"expected_version": 1})
    with pytest.raises(DomainError, match="INVALID_STATE_TRANSITION"):
        sales.cancel_delivery(sales_user, 5, {"expected_version": 1})
    cancel_sales_store = TransactionStore()
    cancel_sales_store.delivery_status = "submitted"
    with pytest.raises(DomainError, match="CANCELLATION_REASON_REQUIRED"):
        SalesService(cancel_sales_store).cancel_delivery(sales_user, 5, {"expected_version": 1})
    assert sales.list_receivables(sales_user)["total"] == 0
    assert sales.list_receipts(sales_user)["total"] == 1
    assert sales.update_receipt(sales_user, 4, {"expected_version": 1, "amount": 4})["row_version"] == 2
    assert sales.submit_receipt(sales_user, 4, {"expected_version": 1})["status"] == "submitted"
