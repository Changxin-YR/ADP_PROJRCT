from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from backend.layers.features.cost.cost_service import CostService, CostServiceError


class FakeCostLifecycleStore:
    def __init__(self) -> None:
        self.items: dict[int, dict[str, Any]] = {}
        self.next_id = 1
        self.audit: list[tuple[str, int]] = []

    def create_entry(self, *, user_id: int, **payload: Any) -> dict[str, Any]:
        item = {"id": self.next_id, **payload, "status": "draft", "created_by": user_id, "amount": payload["amount"], "occurred_on": payload["occurred_on"], "period_start": payload["period_start"], "period_end": payload["period_end"]}
        self.items[self.next_id] = item
        self.next_id += 1
        self.audit.append(("create", item["id"]))
        return dict(item)

    def update_draft(self, entry_id: int, *, user_id: int, **payload: Any) -> dict[str, Any]:
        item = self.items[entry_id]
        if item["status"] != "draft":
            raise ValueError("只有草稿成本才可以编辑")
        item.update(payload)
        self.audit.append(("update", entry_id))
        return dict(item)

    def submit_entry(self, entry_id: int, **_: Any) -> dict[str, Any]:
        item = self.items[entry_id]
        if item["status"] != "draft":
            raise ValueError("只有草稿成本才可以提交核验")
        item["status"] = "pending"
        self.audit.append(("submit", entry_id))
        return dict(item)

    def confirm_entry(self, entry_id: int, **_: Any) -> dict[str, Any]:
        item = self.items[entry_id]
        user_id = int(_.get("user_id", 0))
        if item.get("created_by") == user_id:
            raise ValueError("提交人不能核验自己提交的成本")
        if item["status"] != "pending":
            raise ValueError("只有待核验成本才可以完成核验")
        item["status"] = "confirmed"
        self.audit.append(("confirm", entry_id))
        return dict(item)

    def delete_draft(self, entry_id: int, **_: Any) -> dict[str, Any]:
        item = self.items[entry_id]
        if item["status"] != "draft":
            raise ValueError("只有未正式录入的草稿成本可以删除")
        self.audit.append(("delete", entry_id))
        return self.items.pop(entry_id)

    def reverse_entry(self, entry_id: int, *, reason: str, user_id: int, **_: Any) -> dict[str, Any]:
        original = self.items[entry_id]
        if original["status"] != "confirmed":
            raise ValueError("只有已核验成本才可以冲销")
        item = {**original, "id": self.next_id, "status": "confirmed", "amount": -abs(original["amount"]), "reversal_of_id": entry_id, "reason": reason, "created_by": user_id}
        self.items[self.next_id] = item
        self.next_id += 1
        self.audit.append(("reverse", entry_id))
        return dict(item)


def _user(*permissions: str) -> dict[str, Any]:
    return {"id": 7, "permissions": list(permissions)}


def _payload() -> dict[str, Any]:
    return {
        "category_code": "feed",
        "amount": "128.50",
        "occurred_on": "2026-08-15",
        "period_start": "2026-08-01",
        "period_end": "2026-08-31",
        "source_type": "purchase_invoice",
        "source_ref": "INV-001",
        "source_detail": {"supplier": "供应商 A"},
    }


def test_cost_lifecycle_only_draft_is_editable_or_deletable() -> None:
    store = FakeCostLifecycleStore()
    service = CostService(store)
    user = _user("cost.entry.manage", "cost.entry.verify", "cost.entry.reverse")

    draft = service.create_entry(user, _payload())
    submitted = service.submit_entry(user, draft["id"])
    verifier = {"id": 8, "permissions": ["cost.entry.verify"]}
    confirmed = service.confirm_entry(verifier, submitted["id"])
    assert confirmed["status"] == "confirmed"
    with pytest.raises(CostServiceError) as edit_error:
        service.update_draft(user, confirmed["id"], _payload())
    assert edit_error.value.code == "COST_DRAFT_EDIT_FAILED"
    with pytest.raises(CostServiceError) as delete_error:
        service.delete_draft(user, confirmed["id"])
    assert delete_error.value.code == "COST_DRAFT_DELETE_FAILED"


def test_verified_cost_is_corrected_by_reversal_without_mutating_original() -> None:
    store = FakeCostLifecycleStore()
    service = CostService(store)
    user = _user("cost.entry.manage", "cost.entry.verify", "cost.entry.reverse")
    draft = service.create_entry(user, _payload())
    service.submit_entry(user, draft["id"])
    service.confirm_entry({"id": 8, "permissions": ["cost.entry.verify"]}, draft["id"])

    reversal = service.reverse_entry(user, draft["id"], "原始发票金额录入错误")

    assert reversal["status"] == "confirmed"
    assert reversal["amount"] == "-128.50"
    assert reversal["reversal_of_id"] == draft["id"]
    assert store.items[draft["id"]]["status"] == "confirmed"


def test_submitter_cannot_verify_own_cost_entry() -> None:
    store = FakeCostLifecycleStore()
    service = CostService(store)
    user = _user("cost.entry.manage", "cost.entry.verify")
    draft = service.create_entry(user, _payload())
    service.submit_entry(user, draft["id"])

    with pytest.raises(CostServiceError) as error:
        service.confirm_entry(user, draft["id"])
    assert error.value.code == "COST_CONFIRM_FAILED"


def test_reversal_requires_separate_permission_and_reason() -> None:
    store = FakeCostLifecycleStore()
    service = CostService(store)
    with pytest.raises(CostServiceError, match="成本功能权限"):
        service.create_entry(_user("cost.view"), _payload())
    with pytest.raises(CostServiceError) as error:
        service.reverse_entry(_user("cost.entry.reverse"), 1, "")
    assert error.value.code == "COST_REVERSAL_REASON_REQUIRED"
