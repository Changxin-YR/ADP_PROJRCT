from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.db.repositories.cost_allocation_store import MySqlCostAllocationStore
from backend.layers.common.db.repositories.cost_store import MySqlCostStore
from backend.layers.features.cost.cost_enterprise_service import CostEnterpriseService


MANAGER = {"id": 7, "permissions": ["cost.view", "cost.entry.manage", "cost.entry.verify", "cost.asset.manage", "cost.settlement.manage", "cost.allocation.manage"]}
REVIEWER = {"id": 8, "permissions": ["cost.entry.verify", "cost.asset.verify", "cost.settlement.verify"]}
APPROVER = {"id": 9, "permissions": ["cost.entry.confirm", "cost.asset.confirm", "cost.settlement.confirm", "cost.entry.reverse", "cost.settlement.reverse"]}


class FakeEnterpriseStore:
    def __init__(self) -> None:
        self.expense = {"id": 1, "status": "draft", "row_version": 1, "created_by": 7, "updated_by": None}
        self.asset = {"id": 2, "status": "draft", "row_version": 1, "created_by": 7, "updated_by": None}
        self.depreciated: set[str] = set()
        self.work_target_version = 0
        self.settlement = {"id": 3, "status": "draft", "row_version": 1, "created_by": 7, "updated_by": None}
        self.locked = False

    def list_expenses(self, **_: Any) -> dict[str, Any]:
        return {"items": [deepcopy(self.expense)], "page": 1, "page_size": 20, "total": 1, "has_next": False}

    def create_expense(self, payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        self.expense.update(payload)
        return deepcopy(self.expense)

    def get_expense(self, _record_id: int, **_: Any) -> dict[str, Any]:
        return deepcopy(self.expense)

    def update_expense(self, _record_id: int, payload: dict[str, Any], *, expected_version: int, user_id: int, **_: Any) -> dict[str, Any]:
        if expected_version != self.expense["row_version"]:
            raise DomainError("VERSION_CONFLICT", "数据已被修改", 409)
        self.expense.update(payload)
        self.expense.update(row_version=expected_version + 1, updated_by=user_id)
        if self.expense["status"] == "submitted":
            self.work_target_version = self.expense["row_version"]
        return deepcopy(self.expense)

    def transition_expense(self, _record_id: int, status: str, *, expected_version: int, **kwargs: Any) -> dict[str, Any]:
        if expected_version != self.expense["row_version"]:
            raise DomainError("VERSION_CONFLICT", "数据已被修改", 409)
        if status == "verified" and kwargs.get("user_id") in {self.expense["created_by"], self.expense["updated_by"]}:
            raise DomainError("SELF_APPROVAL_FORBIDDEN", "经办人与核验人必须分离", 403)
        if status in {"verified", "confirmed"} and kwargs.get("evidence_attachment_ids") != [11]:
            raise DomainError("EVIDENCE_INVALID", "凭据未绑定到当前费用", 422)
        self.expense.update(status=status, row_version=expected_version + 1)
        self.work_target_version = self.expense["row_version"]
        return deepcopy(self.expense)

    def delete_expense(self, _record_id: int, **_: Any) -> dict[str, Any]:
        if self.expense["status"] != "draft":
            raise DomainError("DELETE_NOT_ALLOWED", "仅草稿可删除", 409)
        return deepcopy(self.expense)

    def reverse_expense(self, _record_id: int, **_: Any) -> dict[str, Any]:
        if self.locked:
            raise DomainError("COST_PERIOD_LOCKED", "期间已结算", 409)
        return {**self.expense, "id": 4, "amount": Decimal("-120.00"), "reversal_of_id": 1, "status": "confirmed"}

    def list_assets(self, **_: Any) -> dict[str, Any]:
        return {"items": [deepcopy(self.asset)], "page": 1, "page_size": 20, "total": 1, "has_next": False}

    def create_asset(self, payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        self.asset.update(payload)
        return deepcopy(self.asset)

    def get_asset(self, _record_id: int, **_: Any) -> dict[str, Any]:
        return deepcopy(self.asset)

    def update_asset(self, _record_id: int, payload: dict[str, Any], *, expected_version: int, user_id: int, **_: Any) -> dict[str, Any]:
        self.asset.update(payload)
        self.asset.update(row_version=expected_version + 1, updated_by=user_id)
        return deepcopy(self.asset)

    def transition_asset(self, _record_id: int, status: str, *, expected_version: int, **_: Any) -> dict[str, Any]:
        self.asset.update(status=status, row_version=expected_version + 1)
        return deepcopy(self.asset)

    def delete_asset(self, _record_id: int, **_: Any) -> dict[str, Any]:
        return deepcopy(self.asset)

    def depreciate_asset(self, _record_id: int, *, period: str, **_: Any) -> dict[str, Any]:
        if period in self.depreciated:
            raise DomainError("DEPRECIATION_PERIOD_EXISTS", "该期间已计提折旧", 409)
        self.depreciated.add(period)
        return {"id": 5, "asset_id": 2, "period": period, "amount": Decimal("10.00"), "cost_entry_id": 6}

    def run_allocation(self, **_: Any) -> dict[str, Any]:
        return {
            "id": 6,
            "source_total": Decimal("100.00"),
            "allocated_total": Decimal("100.00"),
            "fallback_count": 3,
            "details": [
                {"pond_id": 1, "amount": Decimal("33.34"), "fallback_used": True},
                {"pond_id": 2, "amount": Decimal("33.33"), "fallback_used": True},
                {"pond_id": 3, "amount": Decimal("33.33"), "fallback_used": True},
            ],
        }

    def list_settlements(self, **_: Any) -> dict[str, Any]:
        return {"items": [deepcopy(self.settlement)], "page": 1, "page_size": 20, "total": 1, "has_next": False}

    def create_settlement(self, payload: dict[str, Any], **_: Any) -> dict[str, Any]:
        self.settlement.update(payload, income_amount=Decimal("260.00"), cost_amount=Decimal("100.00"), profit_amount=Decimal("160.00"))
        return deepcopy(self.settlement)

    def get_settlement(self, _record_id: int, **_: Any) -> dict[str, Any]:
        return deepcopy(self.settlement)

    def update_settlement(self, _record_id: int, name: str, *, expected_version: int, user_id: int, **_: Any) -> dict[str, Any]:
        if expected_version != self.settlement["row_version"]:
            raise DomainError("VERSION_CONFLICT", "数据已被修改", 409)
        self.settlement.update(name=name, row_version=expected_version + 1, updated_by=user_id)
        self.work_target_version = self.settlement["row_version"]
        return deepcopy(self.settlement)

    def delete_settlement(self, _record_id: int, **_: Any) -> dict[str, Any]:
        if self.settlement["status"] != "draft":
            raise DomainError("DELETE_NOT_ALLOWED", "仅草稿可删除", 409)
        return deepcopy(self.settlement)

    def transition_settlement(self, _record_id: int, status: str, *, expected_version: int, **_: Any) -> dict[str, Any]:
        self.settlement.update(status=status, row_version=expected_version + 1)
        if status == "confirmed":
            self.locked = True
        return deepcopy(self.settlement)

    def reverse_settlement(self, _record_id: int, **_: Any) -> dict[str, Any]:
        self.settlement.update(status="reversed", row_version=self.settlement["row_version"] + 1)
        self.locked = False
        return deepcopy(self.settlement)

    def net_report(self, **_: Any) -> dict[str, Any]:
        active = self.settlement["status"] == "confirmed"
        return {"income_amount": Decimal("260.00") if active else Decimal("0"), "cost_amount": Decimal("100.00") if active else Decimal("0"), "profit_amount": Decimal("160.00") if active else Decimal("0")}


def expense_payload() -> dict[str, Any]:
    return {"category_code": "electricity", "amount": "120.00", "occurred_on": "2026-08-10", "period_start": "2026-08-01", "period_end": "2026-08-31", "source_type": "expense", "source_ref": "EXP-001"}


def test_cost_enterprise_migration_owns_assets_allocations_and_settlements() -> None:
    migration = Path("database/migrations/015_cost_assets_settlement.sql")
    warehouse_migration = Path("database/migrations/016_cost_warehouse_facts.sql")
    assert migration.exists()
    sql = migration.read_text(encoding="utf-8").lower()
    for table in ("cost_assets", "cost_depreciation_entries", "cost_allocation_runs", "cost_allocation_details", "cost_settlements", "cost_settlement_sources"):
        assert f"create table {table}" in sql
    for field in ("organization_id", "row_version", "updated_by", "verified_by", "evidence_attachment_ids_json"):
        assert f"add column {field}" in sql
    assert "unique key uq_cost_depreciation_asset_period" in sql
    assert "create trigger cost_entries_no_formal_update" in sql
    assert "create trigger cost_assets_no_formal_update" in sql
    assert "create trigger cost_allocation_details_no_update" in sql
    assert "create trigger cost_settlement_sources_no_delete" in sql
    assert "create trigger cost_settlements_no_formal_delete" in sql
    warehouse_sql = warehouse_migration.read_text(encoding="utf-8").lower()
    assert "create trigger inventory_ledger_post_cost" in warehouse_sql
    assert "'warehouse_ledger'" in warehouse_sql
    assert "'$.inventory_ledger_id'" in warehouse_sql
    assert "'warehouse_ledger',d.code" in warehouse_sql
    schema = Path("database/schema.sql").read_text(encoding="utf-8")
    assert "SOURCE database/migrations/015_cost_assets_settlement.sql;" in schema
    assert "SOURCE database/migrations/016_cost_warehouse_facts.sql;" in schema


def test_cost_store_proxy_rejects_duplicate_enterprise_methods() -> None:
    class First:
        def collide(self) -> str: return "first"

    class Second:
        def collide(self) -> str: return "second"

    with pytest.raises(RuntimeError, match="collide"):
        MySqlCostStore._build_enterprise_methods((First(), Second()))


def test_submitted_expense_edit_updates_target_version_and_enforces_separation() -> None:
    store = FakeEnterpriseStore()
    service = CostEnterpriseService(store)
    created = service.create_expense(MANAGER, expense_payload())
    submitted = service.submit_expense(MANAGER, created["id"], {"expected_version": created["version"]})
    edited = service.update_expense(MANAGER, created["id"], {**expense_payload(), "amount": "150.00", "expected_version": submitted["version"]})
    assert edited["version"] == 3
    assert store.work_target_version == 3
    with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
        service.verify_expense(MANAGER, created["id"], {"expected_version": 3, "evidence_attachment_ids": [11]})
    verified = service.verify_expense(REVIEWER, created["id"], {"expected_version": 3, "evidence_attachment_ids": [11]})
    confirmed = service.confirm_expense(APPROVER, created["id"], {"expected_version": verified["version"], "evidence_attachment_ids": [11]})
    assert confirmed["status"] == "confirmed"
    assert confirmed["allowed_actions"] == ["view", "reverse"]


def test_expense_version_conflict_and_bound_evidence_are_required() -> None:
    service = CostEnterpriseService(FakeEnterpriseStore())
    with pytest.raises(DomainError, match="VERSION_CONFLICT"):
        service.update_expense(MANAGER, 1, {**expense_payload(), "expected_version": 9})
    submitted = service.submit_expense(MANAGER, 1, {"expected_version": 1})
    with pytest.raises(DomainError, match="EVIDENCE_INVALID"):
        service.verify_expense(REVIEWER, 1, {"expected_version": submitted["version"], "evidence_attachment_ids": [99]})


def test_asset_depreciation_rejects_duplicate_periods() -> None:
    store = FakeEnterpriseStore(); store.asset["status"] = "confirmed"
    service = CostEnterpriseService(store)
    assert service.get_asset(MANAGER, 2)["allowed_actions"] == ["view", "depreciate"]
    first = service.depreciate_asset(MANAGER, 2, {"period": "2026-08"})
    assert first == {"id": 5, "asset_id": 2, "period": "2026-08", "amount": "10.00", "cost_entry_id": 6}
    with pytest.raises(DomainError, match="DEPRECIATION_PERIOD_EXISTS"):
        service.depreciate_asset(MANAGER, 2, {"period": "2026-08"})


def test_allocation_snapshot_preserves_total_and_marks_equal_fallback() -> None:
    result = CostEnterpriseService(FakeEnterpriseStore()).run_allocation(MANAGER, {
        "period_start": "2026-08-01", "period_end": "2026-08-31", "farm_id": 1, "area_id": 2,
    })
    assert result["source_total"] == result["allocated_total"] == "100.00"
    assert sum(Decimal(row["amount"]) for row in result["details"]) == Decimal("100.00")
    assert result["fallback_count"] == 3


def test_allocation_requires_an_explicit_farm_scope() -> None:
    with pytest.raises(DomainError, match="COST_ALLOCATION_SCOPE_REQUIRED"):
        CostEnterpriseService(FakeEnterpriseStore()).run_allocation(
            MANAGER, {"period_start": "2026-08-01", "period_end": "2026-08-31"},
        )


@pytest.mark.parametrize(
    ("driver", "field"),
    [
        ("equipment_count", "equipment_count"),
        ("runtime_hours", "runtime_hours"),
        ("direct_input", "direct_input"),
        ("direct_consumption", "direct_consumption"),
        ("work_scope", "work_scope"),
    ],
)
def test_configured_allocation_drivers_use_participant_metrics(driver: str, field: str) -> None:
    participants = [
        {"pond_id": 1, "batch_id": 10, field: Decimal("3")},
        {"pond_id": 2, "batch_id": 20, field: Decimal("1")},
    ]

    weights, fallback = MySqlCostAllocationStore._weights({}, {"driver": driver}, participants)

    assert weights == [(1, Decimal("3")), (2, Decimal("1"))]
    assert fallback is False


def test_asset_depreciation_cost_facts_cannot_be_reversed_as_expenses() -> None:
    store = FakeEnterpriseStore()
    store.expense.update(status="confirmed", source_type="asset_depreciation")
    service = CostEnterpriseService(store)
    finance = {**APPROVER, "permissions": [*APPROVER["permissions"], "cost.view"]}

    assert service.get_expense(finance, 1)["allowed_actions"] == ["view"]
    with pytest.raises(DomainError, match="COST_REVERSAL_NOT_ALLOWED"):
        service.reverse_expense(finance, 1, {"reason": "不应通过费用冲销折旧"})


def test_confirmed_settlement_locks_writes_and_reversal_zeroes_net_report() -> None:
    store = FakeEnterpriseStore()
    service = CostEnterpriseService(store)
    created = service.create_settlement(MANAGER, {"period_start": "2026-08-01", "period_end": "2026-08-31", "allocation_run_id": 6})
    submitted = service.submit_settlement(MANAGER, 3, {"expected_version": created["version"]})
    verified = service.verify_settlement(REVIEWER, 3, {"expected_version": submitted["version"]})
    confirmed = service.confirm_settlement(APPROVER, 3, {"expected_version": verified["version"]})
    assert confirmed["profit_amount"] == "160.00"
    with pytest.raises(DomainError, match="COST_PERIOD_LOCKED"):
        service.reverse_expense(APPROVER, 1, {"reason": "结算期内禁止直接冲销"})
    service.reverse_settlement(APPROVER, 3, {"expected_version": confirmed["version"], "reason": "发现期末漏单，重新结算"})
    assert service.net_report(MANAGER, {"period_start": "2026-08-01", "period_end": "2026-08-31"})["profit_amount"] == "0.00"


def test_settlement_draft_delete_and_submitted_edit_match_advertised_actions() -> None:
    store = FakeEnterpriseStore(); service = CostEnterpriseService(store)
    draft = service.get_settlement(MANAGER, 3)
    assert draft["allowed_actions"] == ["view", "edit", "delete", "submit"]
    assert service.delete_settlement(MANAGER, 3)["status"] == "draft"
    submitted = service.submit_settlement(MANAGER, 3, {"expected_version": 1})
    edited = service.update_settlement(MANAGER, 3, {"name": "八月正式结算", "expected_version": submitted["version"]})
    assert (edited["name"], edited["version"], store.work_target_version) == ("八月正式结算", 3, 3)
    assert edited["allowed_actions"] == ["view", "edit"]
    with pytest.raises(DomainError, match="DELETE_NOT_ALLOWED"):
        service.delete_settlement(MANAGER, 3)
