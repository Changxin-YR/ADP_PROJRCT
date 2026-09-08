from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.data_exchange.import_refs import (
    _batch,
    _date,
    _decimal,
    _int,
    _pond,
    _warehouse,
    enforce_area_scope,
    scoped_area_defaults,
)
from backend.layers.features.data_exchange.import_scope_validation import validate_import_scope
from backend.layers.features.data_exchange import import_validation
from backend.layers.features.data_exchange.importers_finance import (
    import_asset,
    import_cost_adjustment,
    import_customer_receipt,
    import_expense,
    import_payment,
    import_purchase_order,
    import_sales_order,
)
from backend.layers.features.production.production_store import MySqlProductionStore
from backend.layers.features.production.production_service import ProductionService
from backend.layers.features.purchase.purchase_service import PurchaseService
from backend.layers.features.sales.sales_service import SalesService
from backend.layers.features.warehouse.warehouse_service import WarehouseService
from backend.scripts.readiness.database_drill import DatabaseSnapshot, compare_snapshots, dump_arguments, run_drill


class Cursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = list(rows or [])
        self.lastrowid = 41
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows.pop(0) if self.rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        rows, self.rows = self.rows, []
        return rows


def actor(*, area_id: int | None = None, personal: bool = False) -> dict[str, Any]:
    scopes = []
    if area_id is not None:
        scopes.append({"scope_type": "area", "area_id": area_id})
    if personal:
        scopes.append({"scope_type": "personal"})
    return {"id": 7, "data_scopes": scopes, "_scope_enforced": bool(scopes)}


def test_import_reference_parsers_and_scope_fail_closed() -> None:
    assert _int("12.0") == 12
    assert _int("0") is None
    assert _int("1.2") is None
    assert _date(datetime(2026, 9, 8, 1, 2)) == date(2026, 9, 8)
    assert _date("bad") is None
    assert _decimal("12.50") == Decimal("12.50")
    with pytest.raises(DomainError, match="FIELD_INVALID"):
        _decimal("NaN")

    with pytest.raises(DomainError, match="POND_NOT_VERIFIED"):
        _pond(Cursor([{"organization_id": 1, "farm_id": 2, "area_id": 3, "status": "draft"}]), 1, 8)
    with pytest.raises(DomainError, match="BATCH_NOT_FOUND"):
        _batch(Cursor(), 1, 8)
    with pytest.raises(DomainError, match="WAREHOUSE_NOT_FOUND"):
        _warehouse(Cursor(), 1, 8)

    scoped = actor(area_id=3)
    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        enforce_area_scope(scoped, 4)
    assert scoped_area_defaults(Cursor([{"organization_id": 1, "farm_id": 2}]), scoped, 1) == {"farm_id": 2, "area_id": 3}


def test_import_scope_matrix_rejects_personal_and_foreign_rows() -> None:
    assert validate_import_scope(Cursor(), actor(), 1, "materials", [{"code": "M"}], [2]) == []
    assert validate_import_scope(Cursor(), actor(personal=True), 1, "ponds", [{}], [2])[0]["column"] == "data_scope"
    assert validate_import_scope(Cursor(), actor(area_id=3), 1, "materials", [{}], [2]) == []
    errors = validate_import_scope(Cursor([{"area_id": 4}]), actor(area_id=3), 1, "batches", [{"pond_id": 8}], [9])
    assert errors == [{"row": 9, "column": "pond_id", "message": "关联业务对象不在当前账号授权区域内", "value": 4}]


def test_finance_importers_validate_and_build_insert_rows() -> None:
    user = actor()
    purchase_cursor = Cursor([
        {"organization_id": 1, "farm_id": 2, "area_id": 3},
        {"id": 5},
        {"id": 6},
    ])
    assert import_purchase_order(purchase_cursor, {"code": "PO", "warehouse_id": 8, "supplier_id": 5, "material_id": 6, "quantity": "2", "unit_price": "3", "due_date": "2026-09-30"}, organization_id=1, user=user, user_id=7) == ("purchase:orders", 41)

    payment_cursor = Cursor([{"id": 9, "status": "unpaid", "area_id": 3}])
    assert import_payment(payment_cursor, {"code": "PAY", "payable_id": 9, "amount": "3", "happened_at": "2026-09-08", "payment_method": "cash"}, organization_id=1, user=user, user_id=7) == ("purchase:payments", 41)
    receipt_cursor = Cursor([{"id": 10, "status": "partial", "area_id": 3}])
    assert import_customer_receipt(receipt_cursor, {"code": "REC", "receivable_id": 10, "amount": "3", "happened_at": "2026-09-08"}, organization_id=1, user=user, user_id=7) == ("sales:receipts", 41)

    sales_cursor = Cursor([
        {"id": 11, "organization_id": 1, "farm_id": 2, "area_id": 3, "pond_id": 4, "species": "鲈鱼", "status": "verified"},
        {"id": 12},
    ])
    assert import_sales_order(sales_cursor, {"code": "SO", "batch_id": 11, "customer_id": 12, "quantity": "2", "unit_price": "5", "sold_at": "2026-09-08", "due_date": "2026-09-30"}, organization_id=1, user=user, user_id=7) == ("sales:orders", 41)

    expense_cursor = Cursor([{"id": 13}, {"default_nature": "public"}, {"id": 2, "organization_id": 1}])
    assert import_expense(expense_cursor, {"code": "COST", "category_code": "electricity", "amount": "4", "farm_id": 2, "happened_at": "2026-09-08"}, organization_id=1, user=user, user_id=7) == ("cost:entries", 41)
    asset_cursor = Cursor([{"id": 14}, {"id": 2, "organization_id": 1}])
    assert import_asset(asset_cursor, {"code": "ASSET", "name": "设备", "category_code": "equipment", "amount": "20", "farm_id": 2, "purchase_date": "2026-09-01", "depreciation_start_date": "2026-09-01", "salvage_value": "1", "useful_life_months": "12"}, organization_id=1, user=user, user_id=7, asset_type="equipment", entity_type="cost:assets") == ("cost:assets", 41)
    adjustment_cursor = Cursor([{"organization_id": 1, "farm_id": 2, "area_id": 3, "category_id": 13, "cost_nature": "public", "period_start": date(2026, 9, 1), "period_end": date(2026, 9, 30)}])
    assert import_cost_adjustment(adjustment_cursor, {"code": "ADJ", "source_id": 13, "amount": "2", "reason": "修正"}, organization_id=1, user=user, user_id=7) == ("cost:adjustments", 41)

    with pytest.raises(DomainError, match="PAYMENT_METHOD_REQUIRED"):
        import_payment(Cursor(), {"code": "BAD", "payment_method": "wire"}, organization_id=1, user=user, user_id=7)
    with pytest.raises(DomainError, match="SALES_DATE_INVALID"):
        import_sales_order(Cursor([{"id": 11, "organization_id": 1, "farm_id": 2, "area_id": 3, "pond_id": 4, "species": "鲈鱼", "status": "verified"}, {"id": 12}]), {"code": "BAD", "batch_id": 11, "customer_id": 12, "quantity": "2", "unit_price": "5", "sold_at": "2026-09-08", "due_date": "2026-09-01"}, organization_id=1, user=user, user_id=7)


def test_business_validation_branches_and_snapshot_diff() -> None:
    assert MySqlProductionStore._db_payload("daily-operations", {"pond_id": 1, "payload": {"ok": True}, "name": "巡塘", "empty": ""})["payload_json"] == '{"ok": true}'
    assert MySqlProductionStore._stock_lines("transfers", {"batch_id": 2, "pond_id": 3, "target_pond_id": 4, "quantity": 5, "weight_kg": 2})[1][2] == "transfer_in"
    with pytest.raises(DomainError, match="WAREHOUSE_TRANSFER_TARGET_INVALID"):
        WarehouseService._validate("transfers", {"warehouse_id": 1, "target_warehouse_id": 1, "quantity": 1})
    with pytest.raises(DomainError, match="PURCHASE_AMOUNT_INVALID"):
        PurchaseService._positive({"quantity": 0}, "quantity")
    PurchaseService._validate_dates({"expected_delivery_date": "2026-09-08", "due_date": "2026-09-09"})
    with pytest.raises(DomainError, match="SALES_DATE_INVALID"):
        SalesService.validate_dates({"sold_at": "2026-09-09", "due_date": "2026-09-08"})
    assert dump_arguments("adp_db")[-1] == "adp_db"
    source = DatabaseSnapshot({"001": "a"}, {"ponds": 1}, {"stock": "2"})
    restored = DatabaseSnapshot({"001": "b"}, {"ponds": 1}, {"stock": "2"})
    assert compare_snapshots(source, restored) == ["migrations.001: source=a restore=b"]


def test_import_preview_special_checks_report_business_errors() -> None:
    errors: list[dict[str, Any]] = []
    import_validation._check_warehouse_transfer(Cursor(), 1, [{"warehouse_id": 2, "target_warehouse_id": 2}, {"warehouse_id": 2}], [1, 2], errors)
    import_validation._check_sales_order(Cursor(), 1, [{"unit": "box", "sold_at": "bad", "due_date": "bad"}], [3], errors)
    import_validation._check_receipt_method(Cursor(), 1, [{"receipt_method": "wire"}], [4], errors)
    import_validation._check_assets(Cursor(), 1, [{"asset_type": "other", "amount": "10", "salvage_value": "10"}], [5], errors)
    import_validation._check_feed_task_pond(Cursor(), 1, [{}], [6], errors)
    assert {item["row"] for item in errors} == {1, 2, 3, 4, 5, 6}

    payment_errors: list[dict[str, Any]] = []
    import_validation._check_payments(Cursor([{"id": 8, "amount": "10", "paid_amount": "2", "status": "unpaid", "adjustment_total": "0"}]), 1, [{"payable_id": 8, "amount": "20"}], [7], payment_errors)
    receipt_errors: list[dict[str, Any]] = []
    import_validation._check_receipts(Cursor([{"id": 9, "status": "settled"}]), 1, [{"receivable_id": 9}], [8], receipt_errors)
    assert payment_errors[0]["column"] == "amount" and receipt_errors[0]["column"] == "receivable_id"


def test_production_and_result_formatting_boundaries() -> None:
    with pytest.raises(DomainError, match="PRODUCTION_FIELD_INVALID"):
        ProductionService._clean("daily-operations", {"status": "verified"})
    with pytest.raises(DomainError, match="PRODUCTION_VALUE_INVALID"):
        ProductionService._positive({"quantity": "NaN"}, "quantity")
    with pytest.raises(DomainError, match="PRODUCTION_DATE_INVALID"):
        ProductionService._validate_batch_dates({"stocked_at": "2026-09-08", "expected_harvest_date": "2026-09-01"})
    with pytest.raises(DomainError, match="FEED_PLAN_REQUIRED_FIELDS"):
        ProductionService._validate_feed_plan({}, submitting=True)
    assert ProductionService.result({"status": "draft", "row_version": 1, "name": "草稿"}, {"permissions": ["production.manage"]}, "daily-operations")["version"] == 1
    assert PurchaseService.order_result({"status": "submitted", "row_version": 2}, {"permissions": ["purchase.verify"]})["allowed_actions"] == ["view", "approve", "cancel"]
    assert SalesService.order_result({"status": "approved", "row_version": 1}, {"permissions": ["sales.manage"]})["allowed_actions"] == ["view", "deliver"]


def test_real_mysql_backup_restore_drill_is_clean(tmp_path: Any) -> None:
    result = run_drill(tmp_path / "database-drill.json")
    assert result["status"] == "PASS"
    assert result["metrics"]["snapshot_differences"] == []
    assert result["metrics"]["idempotency_differences"] == []
    assert result["metrics"]["source_reconciliation"]["ok"]
    assert result["metrics"]["restored_reconciliation"]["ok"]
    assert result["metrics"]["cleanup"] is True
