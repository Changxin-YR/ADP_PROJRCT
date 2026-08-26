from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.work_item_notifications import notify_work_item_created
from backend.layers.common.files.evidence import evidence_from_payload
from backend.layers.features.cost.cost_enterprise_validation import asset_payload
from backend.layers.features.data_exchange.importers_finance import import_purchase_order, import_sales_order
from backend.layers.features.production.production_store import MySqlProductionStore
from backend.layers.features.warehouse.warehouse_ledger_store import WarehouseLedgerPoster
from backend.layers.features.warehouse.warehouse_service import WarehouseService


class RecordingCursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.rows = list(rows or [])
        self.lastrowid = 77

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.statements.append((" ".join(sql.split()), tuple(params)))

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> None:
        self.statements.append((" ".join(sql.split()), tuple(params)))

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows.pop(0) if self.rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


def test_production_evidence_must_be_bound_to_current_record() -> None:
    cursor = RecordingCursor([{"total": 1}])
    MySqlProductionStore._check_evidence(
        cursor,
        {"id": 8, "organization_id": 1},
        [91],
        entity_type="production:losses",
    )
    sql, params = cursor.statements[0]
    assert "entity_type=%s" in sql and "entity_id=%s" in sql
    assert params[:3] == (1, "production:losses", 8)


def test_production_stock_check_locks_batch_anchor_before_balance_read() -> None:
    cursor = RecordingCursor([
        {"id": 4},
        {"quantity": Decimal("10"), "weight": Decimal("2")},
    ])
    store = object.__new__(MySqlProductionStore)
    store._post_stock(cursor, "losses", {
        "id": 9, "organization_id": 1, "batch_id": 4, "pond_id": 2,
        "quantity": 3, "weight_kg": 0.5, "happened_at": "2026-08-24",
    }, 7)
    assert "FROM production_batches" in cursor.statements[0][0]
    assert "FOR UPDATE" in cursor.statements[0][0]


def test_warehouse_negative_check_locks_lot_anchor_before_balance_read() -> None:
    cursor = RecordingCursor([{"id": 5}, {"quantity": Decimal("10")}])
    WarehouseLedgerPoster._validate_negative(cursor, {"material_id": 3}, [{
        "warehouse_id": 2, "inventory_lot_id": 5, "quantity_delta": Decimal("-4"),
    }])
    assert "FROM inventory_lots" in cursor.statements[0][0]
    assert "FOR UPDATE" in cursor.statements[0][0]


class NotificationConnection:
    def __init__(self) -> None:
        self.cursor_instance = RecordingCursor([])

    def cursor(self) -> RecordingCursor:
        cursor = self.cursor_instance

        class Context:
            def __enter__(self_nonlocal) -> RecordingCursor:
                return cursor

            def __exit__(self_nonlocal, *_: Any) -> bool:
                return False

        return Context()  # type: ignore[return-value]


def test_notification_recipient_query_includes_farm_scope_users() -> None:
    connection = NotificationConnection()
    notify_work_item_created(
        connection,
        organization_id=1,
        module_code="production",
        action_code="verify",
        object_type="production:losses",
        object_id=9,
        object_ref="losses:9",
        source_key="production:losses:9:verify",
        title="核验损耗",
        permission_codes=["production.verify"],
    )
    sql = connection.cursor_instance.statements[0][0]
    assert "ds.scope_type = 'farm'" in sql


@pytest.mark.parametrize("invalid_id", [0, True, 1.5, "1.5"])
def test_invalid_evidence_id_is_rejected_before_sql_construction(invalid_id: Any) -> None:
    cursor = RecordingCursor()
    with pytest.raises(DomainError, match="凭据编号"):
        MySqlProductionStore._check_evidence(
            cursor,
            {"id": 8, "organization_id": 1},
            [invalid_id],
            entity_type="production:losses",
        )


def test_evidence_payload_must_be_an_object_not_a_list() -> None:
    with pytest.raises(DomainError, match="请求内容必须是对象"):
        evidence_from_payload([{"evidence_attachment_ids": [1]}])


def test_explicit_empty_evidence_does_not_restore_fallback_ids() -> None:
    assert evidence_from_payload({"evidence_attachment_ids": []}, [9]) == []


@pytest.mark.parametrize(
    ("path", "wrong_type", "expected_type"),
    [
        ("backend/layers/features/purchase/purchase_payment_reversal_store.py", "purchase:payment_reversal", "purchase:payment"),
        ("backend/layers/features/sales/sales_receipt_reversal_store.py", "sales:receipt_reversal", "sales:receipt"),
    ],
)
def test_reversal_evidence_supports_current_source_and_legacy_reversal_targets(path: str, wrong_type: str, expected_type: str) -> None:
    source = Path(path).read_text(encoding="utf-8")
    assert wrong_type in source
    assert expected_type in source


@pytest.mark.parametrize("invalid_life", [1.5, True, "1.5"])
def test_cost_asset_useful_life_requires_a_positive_whole_month(invalid_life: Any) -> None:
    with pytest.raises(DomainError, match="COST_ASSET_LIFE_INVALID"):
        asset_payload({
            "code": "ASSET-LIFE", "name": "增氧机", "asset_type": "equipment",
            "category_code": "equipment", "purchase_date": "2026-08-01",
            "original_value": "100.00", "useful_life_months": invalid_life,
            "depreciation_start_date": "2026-09-01",
        })


def test_purchase_order_import_calculates_total_without_runtime_name_error() -> None:
    cursor = RecordingCursor([
        {"organization_id": 1, "farm_id": 2, "area_id": 3},
        {"id": 4},
        {"id": 5},
    ])
    entity_type, entity_id = import_purchase_order(cursor, {
        "warehouse_id": 1, "supplier_id": 4, "material_id": 5,
        "quantity": "2", "unit_price": "3.00", "due_date": "2026-09-16", "code": "PO-IMPORT", "name": "测试采购",
    }, organization_id=1, user={"id": 9, "data_scopes": []}, user_id=9)
    assert (entity_type, entity_id) == ("purchase:orders", 77)
    assert Decimal("6.00") in cursor.statements[-1][1]


def test_sales_order_import_calculates_total_without_runtime_name_error() -> None:
    cursor = RecordingCursor([
        {"id": 1, "organization_id": 1, "farm_id": 2, "area_id": 3, "pond_id": 4, "species": "鲈鱼"},
        {"id": 5},
    ])
    entity_type, entity_id = import_sales_order(cursor, {
        "batch_id": 1, "customer_id": 5, "quantity": "2", "unit_price": "3.00",
        "sold_at": "2026-08-24", "due_date": "2026-09-16", "code": "SO-IMPORT", "name": "测试销售",
    }, organization_id=1, user={"id": 9, "data_scopes": []}, user_id=9)
    assert (entity_type, entity_id) == ("sales:orders", 77)
    assert Decimal("6.00") in cursor.statements[-1][1]
    assert "SELECT id," in cursor.statements[0][0]


@pytest.mark.parametrize("invalid_version", [True, 1.5, "1.5", 0, -1, None])
def test_expected_version_requires_a_positive_integer(invalid_version: Any) -> None:
    with pytest.raises(DomainError, match="EXPECTED_VERSION_REQUIRED"):
        WarehouseService.expected({"expected_version": invalid_version})
