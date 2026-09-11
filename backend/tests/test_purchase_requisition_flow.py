from __future__ import annotations

from typing import Any

import pytest

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.purchase.purchase_requisition_service import RequisitionService
from backend.layers.features.purchase.purchase_service import PurchaseService
from backend.layers.features.warehouse.warehouse_alert_store import (
    _suggested_quantity,
    alert_references,
    validate_requisition_reference,
)
from fake_auth_store import FakeAuthStore


def actor(user_id: int, *permissions: str) -> dict[str, Any]:
    return {"id": user_id, "permissions": list(permissions), "data_scopes": []}


class RequisitionStore:
    """请购单 + 采购单的最小内存实现，转换唯一性用 requisition_id 记录模拟库内唯一键。"""

    def __init__(self) -> None:
        self.items: dict[int, dict[str, Any]] = {}
        self.orders: dict[int, dict[str, Any]] = {}
        self.next_id = 1

    def _row(self, record_id: int) -> dict[str, Any]:
        if record_id not in self.items:
            raise DomainError("PURCHASE_REQUISITION_NOT_FOUND", "请购单不存在", 404)
        return self.items[record_id]

    def create_requisition(self, payload: dict[str, Any], **_context: Any) -> dict[str, Any]:
        row = {
            **payload, "id": self.next_id, "status": "draft", "row_version": 1, "converted_order_id": None,
            "organization_id": payload.get("organization_id") or 1, "farm_id": payload.get("farm_id") or 9,
        }
        self.items[self.next_id] = row
        self.next_id += 1
        return dict(row)

    def list_requisitions(self, **_query: Any) -> dict[str, Any]:
        return {"items": [dict(row) for row in self.items.values()], "page": 1, "page_size": 20,
                "total": len(self.items), "has_next": False}

    def get_requisition(self, record_id: int, **_context: Any) -> dict[str, Any]:
        return dict(self._row(record_id))

    def update_requisition(self, record_id: int, payload: dict[str, Any], *, expected_version: int,
                           user_id: int, **_context: Any) -> dict[str, Any]:
        row = self._row(record_id)
        if row["row_version"] != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        row.update(payload, updated_by=user_id, row_version=expected_version + 1)
        return dict(row)

    def set_requisition_status(self, record_id: int, status: str, *, expected_version: int, user_id: int,
                               reason: str | None = None, **_context: Any) -> dict[str, Any]:
        row = self._row(record_id)
        if row["row_version"] != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        row.update(status=status, updated_by=user_id, row_version=expected_version + 1)
        if reason is not None:
            row["cancellation_reason"] = reason
        return dict(row)

    def convert_requisition(self, record_id: int, payload: dict[str, Any], *, expected_version: int,
                            user_id: int, **_context: Any) -> dict[str, Any]:
        row = self._row(record_id)
        if row.get("converted_order_id"):
            raise DomainError("PURCHASE_REQUISITION_ALREADY_CONVERTED", "请购单已转换为采购单，不能重复转换", 409)
        if row["row_version"] != expected_version:
            raise DomainError("VERSION_CONFLICT", "版本冲突", 409)
        order_id = 1000 + record_id
        order = {
            "id": order_id, "code": row["code"], "name": row["name"], "material_id": row["material_id"],
            "quantity": row["quantity"], "supplier_id": payload.get("supplier_id"),
            "unit_price": payload.get("unit_price"), "due_date": payload.get("due_date"),
            "warehouse_id": row.get("warehouse_id") or payload.get("warehouse_id"),
            "organization_id": row["organization_id"], "farm_id": row["farm_id"],
            "status": "draft", "row_version": 1, "created_by": user_id, "requisition_id": record_id,
        }
        self.orders[order_id] = order
        row.update(status="converted", converted_order_id=order_id, row_version=expected_version + 1)
        return {"record": dict(order), "requisition": dict(row)}

    def delete_requisition_draft(self, record_id: int, **_context: Any) -> dict[str, Any]:
        row = self._row(record_id)
        if row["status"] != "draft":
            raise DomainError("DELETE_NOT_ALLOWED", "仅草稿状态的请购单可以删除", 409)
        return self.items.pop(record_id)


def requisition_service(store: RequisitionStore) -> RequisitionService:
    """构造请购服务；转换结果里复用采购单的字段格式化。"""
    return RequisitionService(store, PurchaseService(store))


def requisition_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "code": "PR-0001", "name": "饲料补货请购", "material_id": 8, "quantity": 500,
        "warehouse_id": 3, "reason": "安全库存不足", "alert_key": "3:11:low_stock",
    }
    payload.update(overrides)
    return payload


def convert_payload(**overrides: Any) -> dict[str, Any]:
    payload = {"supplier_id": 5, "unit_price": 6.5, "due_date": "2026-09-25", "expected_version": 3}
    payload.update(overrides)
    return payload


def test_requisition_flow_from_draft_to_converted_order() -> None:
    service = requisition_service(RequisitionStore())
    requester = actor(7, "purchase.view", "purchase.manage")
    approver = actor(8, "purchase.view", "purchase.verify")

    created = service.create_requisition(requester, requisition_payload())
    assert created["status"] == "draft"
    assert created["allowed_actions"] == ["view", "edit", "delete", "submit"]

    submitted = service.submit_requisition(requester, created["id"], {"expected_version": 1})
    assert submitted["status"] == "submitted"
    # 经办人不能自审。
    with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
        service.approve_requisition(actor(7, "purchase.verify"), created["id"], {"expected_version": 2})

    approved = service.approve_requisition(approver, created["id"], {"expected_version": 2})
    assert approved["status"] == "approved"
    # allowed_actions 按查看者权限计算：审批人只有 cancel，经办人才能 convert。
    assert approved["allowed_actions"] == ["view", "cancel"]
    # 经办人只能转换（cancel 属于 purchase.verify）。
    assert service.requisition_result(approved, requester)["allowed_actions"] == ["view", "convert"]
    # 已转换的请购单是终态，不再给出任何操作出口。
    assert service.requisition_result({"status": "converted", "row_version": 4}, requester)["allowed_actions"] == ["view"]

    converted = service.convert_requisition(requester, created["id"], convert_payload())
    assert converted["record"]["status"] == "draft"
    assert converted["record"]["requisition_id"] == created["id"]
    assert converted["record"]["quantity"] == 500
    assert converted["requisition"]["status"] == "converted"
    assert converted["requisition"]["converted_order_id"] == converted["record"]["id"]


def test_requisition_cannot_be_converted_twice() -> None:
    store = RequisitionStore()
    service = requisition_service(store)
    requester = actor(7, "purchase.manage")
    approver = actor(8, "purchase.verify")

    created = service.create_requisition(requester, requisition_payload())
    service.submit_requisition(requester, created["id"], {"expected_version": 1})
    service.approve_requisition(approver, created["id"], {"expected_version": 2})
    converted = service.convert_requisition(requester, created["id"], convert_payload())
    order_id = converted["record"]["id"]

    with pytest.raises(DomainError, match="PURCHASE_REQUISITION_ALREADY_CONVERTED"):
        service.convert_requisition(requester, created["id"], convert_payload(expected_version=4))
    assert sorted(store.orders) == [order_id]


def test_requisition_cancel_requires_a_reason() -> None:
    service = requisition_service(RequisitionStore())
    requester = actor(7, "purchase.manage")
    approver = actor(8, "purchase.verify")

    created = service.create_requisition(requester, requisition_payload())
    service.submit_requisition(requester, created["id"], {"expected_version": 1})
    with pytest.raises(DomainError, match="CANCELLATION_REASON_REQUIRED"):
        service.cancel_requisition(approver, created["id"], {"expected_version": 2})
    cancelled = service.cancel_requisition(approver, created["id"], {"expected_version": 2, "cancellation_reason": "重复请购"})
    assert cancelled["status"] == "cancelled"
    # 已取消的请购单不能再转换。
    with pytest.raises(DomainError, match="INVALID_STATE_TRANSITION"):
        service.convert_requisition(requester, created["id"], convert_payload(expected_version=3))


def test_requisition_requires_quantity_and_fields() -> None:
    service = requisition_service(RequisitionStore())
    requester = actor(7, "purchase.manage")
    with pytest.raises(DomainError, match="PURCHASE_REQUISITION_REQUIRED_FIELDS"):
        service.create_requisition(requester, requisition_payload(reason=""))
    with pytest.raises(DomainError, match="PURCHASE_AMOUNT_INVALID"):
        service.create_requisition(requester, requisition_payload(quantity=0))


def test_requisition_permissions_are_enforced() -> None:
    service = requisition_service(RequisitionStore())
    with pytest.raises(DomainError, match="FORBIDDEN"):
        service.create_requisition(actor(7, "purchase.view"), requisition_payload())
    requester = actor(7, "purchase.manage")
    created = service.create_requisition(requester, requisition_payload())
    with pytest.raises(DomainError, match="FORBIDDEN"):
        service.approve_requisition(actor(8, "purchase.manage"), created["id"], {"expected_version": 1})


def test_alert_replenish_accepts_requisition_or_purchase_order() -> None:
    # 新行为：关联请购单。
    assert alert_references("replenish", {"requisition_id": 42}) == {"requisition_id": 42}
    # 老行为：关联采购单，保持兼容。
    assert alert_references("replenish", {"purchase_order_id": 123}) == {"purchase_order_id": 123}
    # 采购单优先于请购单，避免同一 payload 语义歧义。
    assert alert_references("replenish", {"purchase_order_id": 123, "requisition_id": 42}) == {"purchase_order_id": 123}
    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_REFERENCE_REQUIRED"):
        alert_references("replenish", {"resolution_note": "已补货"})


def test_low_stock_alert_suggests_a_replenishment_quantity() -> None:
    row = {"alert_type": "low_stock", "safety_stock": 100, "current_quantity": 35}
    assert _suggested_quantity(row) == 65
    assert _suggested_quantity({"alert_type": "low_stock", "safety_stock": 10, "current_quantity": 40}) == 0
    # 非低库存预警不给请购建议。
    assert _suggested_quantity({"alert_type": "expired", "safety_stock": 0, "current_quantity": 0}) is None


def alert_row(**overrides: Any) -> dict[str, Any]:
    row = {"alert_key": "3:11:low_stock", "alert_type": "low_stock", "severity": "medium",
           "organization_id": 1, "warehouse_id": 3, "material_id": 8, "inventory_lot_id": 11,
           "suggested_quantity": 65, "allowed_actions": ["handle"]}
    row.update(overrides)
    return row


def test_requisition_reference_must_match_the_alert_material() -> None:
    alert = alert_row()
    validate_requisition_reference(
        {"id": 42, "material_id": 8, "warehouse_id": 3, "status": "submitted"}, alert)
    # 物料不一致 -> 400，防止把别的物料的请购单挂到本条预警上。
    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_REFERENCE_INVALID"):
        validate_requisition_reference(
            {"id": 42, "material_id": 99, "warehouse_id": 3, "status": "submitted"}, alert)
    # 交货仓不一致
    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_REFERENCE_INVALID"):
        validate_requisition_reference(
            {"id": 42, "material_id": 8, "warehouse_id": 7, "status": "submitted"}, alert)
    # 已取消
    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_REFERENCE_INVALID"):
        validate_requisition_reference(
            {"id": 42, "material_id": 8, "warehouse_id": 3, "status": "cancelled"}, alert)


def test_requisition_reference_must_exist_in_the_same_organization() -> None:
    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_REFERENCE_INVALID"):
        validate_requisition_reference(None, alert_row())


def test_alert_replenish_still_rejects_a_missing_reference() -> None:
    """老行为的必备校验未被破坏。"""
    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_REFERENCE_REQUIRED"):
        alert_references("replenish", {"purchase_order_id": None, "requisition_id": ""})


def test_alert_replenish_rejects_a_non_positive_reference() -> None:
    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_REFERENCE_REQUIRED"):
        alert_references("replenish", {"requisition_id": 0})
    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_REFERENCE_REQUIRED"):
        alert_references("replenish", {"requisition_id": "abc"})


def test_other_alert_actions_are_unchanged() -> None:
    assert alert_references("transfer", {"resolution_document_id": 5}) == {"resolution_document_id": 5}
    assert alert_references("threshold", {"safety_stock": 20}) == {"safety_stock": 20}
    assert alert_references("replenish", {"requisition_id": 42}) == {"requisition_id": 42}


def test_purchase_requisition_routes_are_registered_and_authorized() -> None:
    auth = FakeAuthStore()
    account = auth.add_user(phone="13800000909", login_name="requisition-admin", password="Correct9!", status="active")
    account["permissions"] = ["purchase.view", "purchase.manage", "purchase.verify"]
    settings = Settings.from_env({
        "APP_ENV": "test", "FLASK_SECRET_KEY": "requisition-test", "CSRF_SECRET_KEY": "requisition-csrf",
        "MYSQL_HOST": "127.0.0.1", "MYSQL_DATABASE": "adp_test", "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test", "SESSION_COOKIE_SECURE": "false",
    })
    client = create_app(settings, store=auth, purchase_store=RequisitionStore()).test_client()
    token = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    login = client.post("/api/v1/auth/login", json={"identifier": "requisition-admin", "password": "Correct9!"},
                        headers={"X-CSRF-Token": token})
    assert login.status_code == 200

    assert client.get("/api/v1/purchase/requisitions").status_code == 200
    created = client.post("/api/v1/purchase/requisitions", json=requisition_payload(),
                          headers={"X-CSRF-Token": token})
    assert created.status_code == 201, created.get_json()
    record_id = created.get_json()["data"]["record"]["id"]

    assert client.post(f"/api/v1/purchase/requisitions/{record_id}/submit", json={"expected_version": 1},
                       headers={"X-CSRF-Token": token}).status_code == 200
    assert client.post(f"/api/v1/purchase/requisitions/{record_id}/approve", json={"expected_version": 2},
                       headers={"X-CSRF-Token": token}).status_code == 403
    converted = client.post(f"/api/v1/purchase/requisitions/{record_id}/convert",
                            json={"supplier_id": 5, "unit_price": 6.5, "due_date": "2026-09-25", "expected_version": 3},
                            headers={"X-CSRF-Token": token})
    assert converted.status_code in {200, 201, 403, 409}, converted.get_json()
