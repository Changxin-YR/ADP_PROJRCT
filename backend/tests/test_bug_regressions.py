from __future__ import annotations

import pytest
from decimal import Decimal

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
from backend.layers.features.data_exchange.template_catalog import get_template
from backend.layers.features.data_exchange.importers_finance import import_payment, import_purchase_order, import_sales_order
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


def test_import_templates_match_required_business_fields() -> None:
    feed_plan = {field.key for field in get_template("feed-plans").fields}
    assert {"batch_id", "material_id", "planned_at", "quantity"}.issubset(feed_plan)
    payment = {field.key for field in get_template("payments").fields}
    assert "payment_method" in payment
    assert get_template("payments").fields[[field.key for field in get_template("payments").fields].index("payment_method")].required is True


def test_production_scope_defaults_require_verified_pond() -> None:
    class Cursor:
        def execute(self, sql: str, _params: tuple[object, ...]) -> None:
            self.sql = sql

        @staticmethod
        def fetchone() -> dict[str, object]:
            return {"organization_id": 1, "farm_id": 1, "area_id": 2, "status": "draft"}

    with pytest.raises(DomainError, match="POND_NOT_VERIFIED"):
        from backend.layers.features.production.production_store import MySqlProductionStore
        MySqlProductionStore._scope_defaults(Cursor(), {"pond_id": 3})


def test_warehouse_update_rejects_blank_code_and_name() -> None:
    service = WarehouseService(type("Store", (), {})())
    user = {"id": 1, "permissions": ["warehouse.manage"], "data_scopes": []}
    with pytest.raises(DomainError, match="WAREHOUSE_REQUIRED_FIELDS"):
        service.update_warehouse(user, 1, {"code": ""})
    with pytest.raises(DomainError, match="WAREHOUSE_REQUIRED_FIELDS"):
        service.update_warehouse(user, 1, {"name": "   "})


def test_finance_notifications_use_parent_document_area_scope() -> None:
    import inspect
    from backend.layers.features.purchase import purchase_payment_store
    from backend.layers.features.sales import sales_receipt_store

    payment_source = inspect.getsource(purchase_payment_store.set_payment_status)
    receipt_source = inspect.getsource(sales_receipt_store.set_receipt_status)
    assert "area_id=payable.get(\"area_id\")" in payment_source
    assert "area_id=source.get(\"area_id\")" in receipt_source
def test_feed_log_requires_positive_quantity_or_weight() -> None:
    service = ProductionService(FakeProductionStore())
    with pytest.raises(DomainError, match="PRODUCTION_QUANTITY_REQUIRED"):
        service.create(user(1, "production.manage"), "feed-logs", {
            "code": "FL-ZERO", "name": "空投喂", "pond_id": 10, "batch_id": 1, "material_id": 7,
        })
def test_loss_requires_positive_quantity_or_weight_and_reason() -> None:
    service = ProductionService(FakeProductionStore())
    with pytest.raises(DomainError, match="PRODUCTION_QUANTITY_REQUIRED"):
        service.create(user(1, "production.manage"), "losses", {
            "code": "LS-ZERO", "name": "空损耗", "pond_id": 10, "batch_id": 1,
        })
    with pytest.raises(DomainError, match="PRODUCTION_LOSS_REASON_REQUIRED"):
        service.create(user(1, "production.manage"), "losses", {
            "code": "LS-NO-REASON", "name": "无原因损耗", "pond_id": 10, "batch_id": 1, "quantity": 1,
        })
def test_batch_requires_initial_quantity_or_weight() -> None:
    with pytest.raises(DomainError, match="PRODUCTION_QUANTITY_REQUIRED"):
        ProductionService(FakeProductionStore()).create(user(1, "production.manage"), "batches", {
            "code": "B-NO-STOCK", "name": "空批次", "pond_id": 10, "species": "草鱼",
        })
def test_batch_status_cannot_start_in_closed_state() -> None:
    with pytest.raises(DomainError, match="PRODUCTION_BATCH_STATUS_INVALID"):
        ProductionService(FakeProductionStore()).create(user(1, "production.manage"), "batches", {
            "code": "B-CLOSED", "name": "关闭批次", "pond_id": 10, "species": "草鱼",
            "initial_quantity": 10, "batch_status": "closed",
        })
def test_transfer_receive_scope_includes_target_area() -> None:
    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        WarehouseService._scope(
            {"id": 7, "data_scopes": [{"scope_type": "area", "area_id": 2}]},
            {"area_id": 2, "_target_area_id": 3, "created_by": 7},
        )
def test_production_scope_defaults_rejects_mismatched_batch_pond() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.rows = [
                {"organization_id": 1, "farm_id": 1, "area_id": 2, "pond_status": "farming", "status": "verified"},
                {"organization_id": 1, "farm_id": 1, "area_id": 2, "pond_id": 99, "status": "verified"},
            ]
        def execute(self, _sql: str, _params: tuple[object, ...]) -> None: return None
        def fetchone(self) -> dict[str, object] | None: return self.rows.pop(0)
    with pytest.raises(DomainError, match="PRODUCTION_RELATION_INVALID"):
        MySqlProductionStore._scope_defaults(Cursor(), {"pond_id": 10, "batch_id": 8})
def test_feed_issue_capacity_excludes_already_verified_feed_logs() -> None:
    from backend.layers.features.production.production_material_control import require_material_issue
    class Cursor:
        sql = ""
        def execute(self, sql: str, _params: tuple[object, ...]) -> None: self.sql = sql
        @staticmethod
        def fetchone() -> dict[str, object]: return {"request_id": 5, "issued_quantity": 50, "consumed_quantity": 40}
    cursor = Cursor()
    require_material_issue(cursor, {"id": 9, "material_issue_request_id": 5, "material_id": 7, "pond_id": 3, "quantity": 20})
    assert "consumed_quantity" in cursor.sql
    assert "production_documents f" in cursor.sql
def test_feed_log_relation_validation_rejects_a_non_task_reference() -> None:
    class Cursor:
        def execute(self, _sql: str, _params: tuple[object, ...]) -> None: return None
        @staticmethod
        def fetchone() -> None: return None
    with pytest.raises(DomainError, match="FEED_TASK_RELATION_INVALID"):
        MySqlProductionStore._validate_relations(Cursor(), "feed-logs", {
            "id": 9, "organization_id": 1, "batch_id": 3, "pond_id": 10, "feed_task_id": 4,
        })


def test_feed_importers_preserve_schedule_and_business_links(monkeypatch) -> None:
    import backend.layers.features.data_exchange.importers as importers

    class Cursor:
        lastrowid = 41

        def __init__(self):
            self.statement = ""
            self.params = ()

        def execute(self, statement, params=()):
            self.statement, self.params = statement, params

    monkeypatch.setattr(importers, "_pond", lambda *_args: {"farm_id": 1, "area_id": 2, "organization_id": 9})
    cursor = Cursor()
    importers._import_production_document(
        cursor,
        {"code": "FP-1", "name": "计划", "pond_id": 3, "batch_id": 4, "material_id": 5, "quantity": 10, "planned_at": "2026-08-27 08:00", "happened_at": "2026-08-27", "reason": ""},
        organization_id=9, user={"id": 7, "data_scopes": [{"scope_type": "farm"}]}, user_id=7, doc_type="feed_plan", entity_type="production:feed-plans",
    )
    assert "planned_at" in cursor.statement
    assert cursor.params[14] == "2026-08-27 08:00"

    cursor = Cursor()
    importers._import_production_document(
        cursor,
        {"code": "FL-1", "name": "记录", "pond_id": 3, "batch_id": 4, "material_id": 5, "feed_task_id": 6, "material_issue_request_id": 8, "quantity": 2, "happened_at": "2026-08-27", "reason": ""},
        organization_id=9, user={"id": 7, "data_scopes": [{"scope_type": "farm"}]}, user_id=7, doc_type="feed_log", entity_type="production:feed-logs",
    )
    assert "feed_task_id" in cursor.statement and "material_issue_request_id" in cursor.statement
    assert 6 in cursor.params and 8 in cursor.params


def test_feed_task_import_rejects_non_breeding_assignee(monkeypatch) -> None:
    import backend.layers.features.data_exchange.importers as importers

    class Cursor:
        lastrowid = 42

        def __init__(self):
            self.fetches = iter([{"id": 10}, None])

        def execute(self, *_args):
            return None

        def fetchone(self):
            return next(self.fetches)

    monkeypatch.setattr(importers, "_pond", lambda *_args: {"farm_id": 1, "area_id": 2, "organization_id": 9})
    with pytest.raises(DomainError, match="FEED_TASK_ASSIGNEE_INVALID"):
        importers._import_production_document(
            Cursor(),
            {"code": "FT-1", "name": "派工", "pond_id": 3, "assignee_id": 10, "happened_at": "2026-08-27"},
            organization_id=9, user={"id": 7, "data_scopes": [{"scope_type": "farm"}]}, user_id=7, doc_type="feed_task", entity_type="production:feed-tasks",
        )


def test_feed_task_import_requires_explicit_pond(monkeypatch) -> None:
    import backend.layers.features.data_exchange.importers as importers

    class Cursor:
        lastrowid = 42
        def execute(self, *_args):
            raise AssertionError("must reject before selecting a fallback pond")

    with pytest.raises(DomainError, match="POND_REQUIRED"):
        importers._import_production_document(
            Cursor(),
            {"code": "FT-2", "name": "派工", "assignee_id": 10, "happened_at": "2026-08-27"},
            organization_id=9, user={"id": 7, "data_scopes": [{"scope_type": "farm"}]}, user_id=7,
            doc_type="feed_task", entity_type="production:feed-tasks",
        )


def test_warehouse_import_requires_explicit_warehouse() -> None:
    import backend.layers.features.data_exchange.importers as importers

    class Cursor:
        lastrowid = 42

        def __init__(self) -> None:
            self.rows = iter([
                {"id": 7},
                {"id": 1},
                {"organization_id": 1, "farm_id": 2, "area_id": 3},
            ])

        def execute(self, *_args: object, **_kwargs: object) -> None:
            return None

        def fetchone(self) -> dict[str, object]:
            return next(self.rows)

    with pytest.raises(DomainError, match="WAREHOUSE_REQUIRED"):
        importers._import_warehouse_document(
            Cursor(),
            {"code": "IN-MISSING-WH", "name": "入库", "material_id": 7, "quantity": 1, "happened_at": "2026-08-27"},
            organization_id=1, user={"id": 1}, user_id=1, doc_type="receipt", entity_type="warehouse:receipts",
        )


def test_cost_import_requires_explicit_farm_for_unrestricted_user(monkeypatch) -> None:
    from backend.layers.features.data_exchange.importers_finance import import_expense

    class Cursor:
        def execute(self, statement, params=()):
            if "SELECT id FROM cost_categories" in statement:
                self.rows = [{"id": 9}]
            elif "SELECT default_nature" in statement:
                self.rows = [{"default_nature": "direct"}]
            elif "FROM farms" in statement:
                self.rows = [{"id": 1, "organization_id": 1}]
            else:
                raise AssertionError("must reject before selecting a fallback farm")
        def fetchone(self):
            return self.rows.pop(0)

    with pytest.raises(DomainError, match="COST_SCOPE_REQUIRED"):
        import_expense(
            Cursor(), {"code": "EXP-UNSCOPED", "name": "费用", "category_code": "FEED", "amount": 100, "happened_at": "2026-08-24"},
            organization_id=1, user={"id": 7, "roles": [{"code": "super_admin"}], "data_scopes": [{"scope_type": "farm"}]}, user_id=7,
        )


def test_second_warehouse_correction_uses_effective_parent_movements(monkeypatch) -> None:
    poster = WarehouseLedgerPoster()
    monkeypatch.setattr(poster, "_ledger_movements", lambda _cursor, source_id, _source_type=None: {
        1: [{"warehouse_id": 1, "inventory_lot_id": 8, "quantity_delta": Decimal("-100")}],
        2: [{"warehouse_id": 1, "inventory_lot_id": 8, "quantity_delta": Decimal("20")}],
    }.get(source_id, []))

    class Cursor:
        def __init__(self):
            self.params = ()

        def execute(self, _statement, params=()):
            self.params = params

        def fetchone(self):
            return {"correction_of_id": 1} if self.params == (2,) else {}

        def fetchall(self):
            return []

    assert poster._effective_movements(Cursor(), 2) == [
        {"warehouse_id": 1, "inventory_lot_id": 8, "quantity_delta": Decimal("-80")}
    ]
def test_low_stock_alerts_aggregate_all_lots_of_one_material() -> None:
    from backend.layers.features.warehouse.warehouse_alert_store import _collapse_low_stock_alerts

    rows = [
        {"warehouse_id": 1, "material_id": 7, "inventory_lot_id": 11, "alert_type": "low_stock", "current_quantity": 30, "safety_stock": 50},
        {"warehouse_id": 1, "material_id": 7, "inventory_lot_id": 12, "alert_type": "low_stock", "current_quantity": 40, "safety_stock": 50},
    ]
    assert _collapse_low_stock_alerts(rows) == []


def test_submitted_scrap_reservation_uses_latest_correction_only() -> None:
    from backend.layers.features.warehouse.warehouse_ledger_store import WarehouseLedgerPoster

    class Cursor:
        sql = ""
        def execute(self, sql: str, _params: tuple[object, ...]) -> None:
            self.sql = sql
        @staticmethod
        def fetchall() -> list[dict[str, object]]: return []

    cursor = Cursor()
    WarehouseLedgerPoster()._lots(cursor, {
        "id": 9, "warehouse_id": 1, "organization_id": 1, "material_id": 7,
    })
    assert "NOT EXISTS" in cursor.sql


def test_breed_worker_permission_covers_issue_request_creation() -> None:
    WarehouseService.require({"permissions": ["production.manage"]}, "manage", "issue-requests")
def test_feed_records_require_a_farming_pond() -> None:
    class Cursor:
        def execute(self, _sql: str, _params: tuple[object, ...]) -> None: return None
        @staticmethod
        def fetchone() -> dict[str, object]:
            return {"organization_id": 1, "farm_id": 1, "area_id": 2, "pond_status": "build", "status": "verified"}
    with pytest.raises(DomainError, match="POND_NOT_READY"):
        from backend.layers.features.production.production_store import MySqlProductionStore
        MySqlProductionStore._scope_defaults(Cursor(), {"pond_id": 3}, "feed-logs")
