from __future__ import annotations

import pytest

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.master_data.master_data_service import MasterDataService
from backend.layers.features.master_data.master_data_store import MySqlMasterDataStore
from backend.layers.features.production.production_service import ProductionService
from backend.layers.features.warehouse.warehouse_ledger_store import WarehouseLedgerPoster
from backend.layers.features.warehouse.warehouse_service import WarehouseService
from backend.layers.features.warehouse.warehouse_store import MySqlWarehouseStore
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
