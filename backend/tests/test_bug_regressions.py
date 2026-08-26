from __future__ import annotations

import pytest

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.master_data.master_data_service import MasterDataService
from backend.layers.features.master_data.master_data_store import MySqlMasterDataStore
from backend.layers.features.production.production_service import ProductionService
from backend.layers.features.production.production_store import MySqlProductionStore
from backend.layers.features.warehouse.warehouse_posting import allocate_fefo
from backend.layers.features.warehouse.warehouse_ledger_store import WarehouseLedgerPoster
from backend.layers.features.warehouse.warehouse_service import WarehouseService
from backend.layers.features.warehouse.warehouse_store import MySqlWarehouseStore
from backend.layers.features.warehouse.warehouse_master_store import WarehouseMasterStoreMixin
from test_master_data_api import FakeMasterStore
from test_production_flow import FakeProductionStore, user


def test_feed_plan_rejects_zero_quantity() -> None:
    service = ProductionService(FakeProductionStore())
    with pytest.raises(DomainError, match="PRODUCTION_QUANTITY_INVALID"):
        service.create(user(1, "production.manage"), "feed-plans", {"code": "FP-001", "name": "晨投", "pond_id": 10, "quantity": 0})


def test_feed_plan_submit_rechecks_business_integrity() -> None:
    store = FakeProductionStore()
    store.rows["feed-plans"] = {1: {"id": 1, "code": "FP-002", "name": "缺字段计划", "pond_id": 10, "quantity": 20, "status": "draft", "row_version": 1, "created_by": 1}}
    with pytest.raises(DomainError, match="FEED_PLAN_REQUIRED_FIELDS"):
        ProductionService(store).submit(user(1, "production.manage"), "feed-plans", 1, {"expected_version": 1})


def test_batch_rejects_future_stocked_at() -> None:
    with pytest.raises(DomainError, match="PRODUCTION_DATE_INVALID"):
        ProductionService(FakeProductionStore()).create(user(1, "production.manage"), "batches", {
            "code": "B-FUTURE", "name": "未来批次", "pond_id": 10, "species": "草鱼", "initial_quantity": 10,
            "stocked_at": "2999-01-01T00:00:00",
        })


def test_master_data_validates_material_and_partner_business_fields() -> None:
    service = MasterDataService(FakeMasterStore())
    manager = {"id": 1, "permissions": ["master_data.manage"], "data_scopes": []}
    with pytest.raises(DomainError, match="SAFETY_STOCK_INVALID"):
        service.create(manager, "materials", {"code": "MAT-NEG", "name": "负库存", "safety_stock": -1})
    with pytest.raises(DomainError, match="CREDIT_LIMIT_INVALID"):
        service.create(manager, "customers", {"code": "CUS-NEG", "name": "负授信", "credit_limit": -1})
    with pytest.raises(DomainError, match="PHONE_INVALID"):
        service.create(manager, "suppliers", {"code": "SUP-BAD", "name": "错误电话", "phone": "abc"})


def test_master_data_verification_requires_a_different_actor() -> None:
    service = MasterDataService(FakeMasterStore())
    maker = {"id": 1, "permissions": ["master_data.manage", "master_data.verify"], "data_scopes": []}
    row = service.create(maker, "materials", {"code": "MAT-SELF", "name": "自审物料"})
    submitted = service.submit(maker, "materials", row["id"], {"expected_version": row["version"]})
    with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
        service.verify(maker, "materials", row["id"], {"expected_version": submitted["version"]})


def test_master_defaults_fail_closed_when_multiple_organizations_exist() -> None:
    class Cursor:
        def execute(self, _sql: str, _params: tuple[object, ...] = ()) -> None: return None
        @staticmethod
        def fetchall() -> list[dict[str, int]]: return [{"id": 1}, {"id": 2}]

    with pytest.raises(DomainError, match="MASTER_ORGANIZATION_REQUIRED"):
        object.__new__(MySqlMasterDataStore)._defaults(Cursor(), {"code": "MAT-MULTI", "name": "多企业物料"})


def test_transfer_scope_requires_access_to_source_and_target_areas() -> None:
    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        WarehouseService._scope({"id": 7, "data_scopes": [{"scope_type": "area", "area_id": 2}]}, {"area_id": 2, "_target_area_id": 3, "created_by": 7})


def test_transfer_list_scope_requires_target_area_access() -> None:
    clause, values = MySqlWarehouseStore._transfer_target_scope({"id": 7, "data_scopes": [{"scope_type": "area", "area_id": 2}]})
    assert "target_scope.area_id IN (%s)" in clause
    assert values == [2]


def test_inventory_lot_must_match_document_material_and_organization() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.rows = [{"organization_id": 1, "farm_id": 1, "area_id": 2}, {"organization_id": 1}, {"organization_id": 1, "material_id": 99}]
        def execute(self, _sql: str, _params: tuple[object, ...]) -> None: return None
        def fetchone(self) -> dict[str, object] | None: return self.rows.pop(0) if self.rows else None

    with pytest.raises(DomainError, match="WAREHOUSE_LOT_INVALID"):
        MySqlWarehouseStore._scoped(Cursor(), {"warehouse_id": 1, "material_id": 7, "inventory_lot_id": 8})


def test_return_must_match_source_issue_warehouse_and_material() -> None:
    class Cursor:
        def execute(self, _sql: str, _params: tuple[object, ...]) -> None: return None
        @staticmethod
        def fetchone() -> dict[str, object]: return {"organization_id": 1, "warehouse_id": 9, "material_id": 7, "document_type": "issue", "status": "verified"}

    with pytest.raises(DomainError, match="WAREHOUSE_RETURN_SOURCE_INVALID"):
        WarehouseLedgerPoster._validate_return(Cursor(), {"source_document_id": 5, "organization_id": 1, "warehouse_id": 2, "material_id": 7, "inventory_lot_id": 8, "quantity": 1})


def test_empty_active_scope_fails_closed_for_real_accounts() -> None:
    account = {"id": 7, "roles": [{"code": "breed_manager"}], "permissions": ["production.manage"], "data_scopes": []}
    with pytest.raises(DomainError, match="DATA_SCOPE_REQUIRED"):
        ProductionService._require_record_scope(account, {"area_id": 2, "created_by": 7})
    with pytest.raises(DomainError, match="DATA_SCOPE_REQUIRED"):
        WarehouseService._scope(account, {"area_id": 2, "created_by": 7})


def test_non_super_admin_farm_scope_does_not_become_cross_tenant_global_access() -> None:
    account = {"id": 7, "roles": [{"code": "breed_manager"}], "data_scopes": [{"scope_type": "farm"}]}
    assert MySqlProductionStore._scope(account) == ("1=0", [])
    assert MySqlWarehouseStore._scope(account) == ("1=0", [])
    admin = {"id": 1, "roles": [{"code": "super_admin"}], "data_scopes": [{"scope_type": "farm"}]}
    assert MySqlProductionStore._scope(admin) == ("", [])


def test_personal_scope_cannot_write_a_record_outside_its_area() -> None:
    account = {"id": 7, "roles": [{"code": "breed_worker"}], "data_scopes": [{"scope_type": "personal"}]}
    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        MySqlProductionStore.require_write_scope(account, {"area_id": 2, "_target_area_id": None, "created_by": 7})


def test_stocktake_allows_zero_but_other_documents_still_require_positive_quantity() -> None:
    WarehouseService._validate("stocktakes", {"inventory_lot_id": 1, "quantity": 0})
    with pytest.raises(DomainError, match="WAREHOUSE_QUANTITY_INVALID"):
        WarehouseService._validate("scraps", {"inventory_lot_id": 1, "quantity": 0})


def test_inventory_dates_require_production_before_expiry() -> None:
    with pytest.raises(DomainError, match="WAREHOUSE_DATE_INVALID"):
        WarehouseService._validate("receipts", {"quantity": 1, "production_date": "2026-12-01", "expiry_date": "2026-09-01"})


def test_scrap_can_allocate_an_expired_lot() -> None:
    lots = [{"id": 3, "available": 5, "expiry_date": "2026-08-01", "expired": True}]
    assert WarehouseLedgerPoster._allocations
    assert allocate_fefo(lots, 2, include_expired=True) == [(3, 2)]


def test_scrap_correction_allows_expired_lot_allocation(monkeypatch: pytest.MonkeyPatch) -> None:
    poster = WarehouseLedgerPoster()
    poster._lots = lambda _cursor, _row: [{"id": 3, "available": 5, "expired": True}]  # type: ignore[method-assign]
    captured: dict[str, object] = {}

    def fake_allocate(_lots: object, _quantity: object, **kwargs: object) -> list[tuple[int, int]]:
        captured.update(kwargs)
        return [(3, 1)]

    monkeypatch.setattr("backend.layers.features.warehouse.warehouse_ledger_store.allocate_fefo", fake_allocate)
    assert poster._correction_allocations(object(), {"warehouse_id": 1, "quantity": 1}, [], include_expired=True) == [(3, 1)]
    assert captured["include_expired"] is True


def test_warehouse_master_data_requires_code_name_and_farm() -> None:
    service = WarehouseService(type("Store", (), {})())
    with pytest.raises(DomainError, match="WAREHOUSE_REQUIRED_FIELDS"):
        service.create_warehouse({"id": 1, "permissions": ["warehouse.manage"], "data_scopes": []}, {"code": "", "name": ""})
    with pytest.raises(DomainError, match="WAREHOUSE_REQUIRED_FIELDS"):
        service.update_warehouse({"id": 1, "permissions": ["warehouse.manage"], "data_scopes": []}, 1, {"name": "   "})


def test_warehouse_master_area_must_belong_to_selected_farm() -> None:
    class Cursor:
        def execute(self, _sql: str, _params: tuple[object, ...]) -> None: return None
        @staticmethod
        def fetchone() -> dict[str, int]: return {"organization_id": 1, "farm_id": 9}

    with pytest.raises(DomainError, match="WAREHOUSE_SCOPE_INVALID"):
        WarehouseMasterStoreMixin._validate_area(Cursor(), 3, 1, 2)


def test_warehouse_master_listing_can_include_disabled_rows() -> None:
    class Store:
        def __init__(self) -> None:
            self.include_disabled = False

        def list_warehouses(self, _user: dict[str, object], *, include_disabled: bool = False) -> list[dict[str, object]]:
            self.include_disabled = include_disabled
            return []

    store = Store()
    WarehouseService(store).warehouses({"id": 1, "permissions": ["warehouse.view"], "data_scopes": []}, include_disabled=True)
    assert store.include_disabled is True
