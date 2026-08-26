from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.cost_enterprise_repository import validate_scope as validate_cost_scope
from backend.layers.features.data_exchange.data_exchange_service import DataExchangeService
from backend.layers.features.data_exchange.data_exchange_store import MySqlDataExchangeStore
from backend.layers.features.data_exchange.import_refs import _date, _decimal, _int
from backend.layers.features.data_exchange.importers import _import_master, _import_ponds
from backend.layers.features.data_exchange.importers_finance import import_customer_receipt, import_expense, import_payment
from backend.layers.features.master_data.master_data_service import MasterDataService
from backend.layers.features.master_data.master_data_store import MySqlMasterDataStore
from backend.layers.features.warehouse.warehouse_service import WarehouseService
from backend.layers.features.warehouse.warehouse_store import MySqlWarehouseStore
from backend.tests.mysql_test_database import disposable_database, settings_for
from test_data_exchange import FakeExchangeStore
from test_data_exchange import workbook


@pytest.mark.parametrize(
    ("resource", "expected_column"),
    [("inventory-ledger", "w.area_id"), ("stock-alerts", "w.area_id")],
)
def test_area_scoped_exports_never_fall_back_to_organization_wide(resource: str, expected_column: str) -> None:
    user = {"id": 7, "data_scopes": [{"scope_type": "area", "area_id": 2}]}
    sql, params = MySqlDataExchangeStore._export_scope(user, resource)
    assert expected_column in sql
    assert params == [2]


def test_area_scoped_import_audit_export_is_limited_to_own_batches() -> None:
    user = {"id": 7, "data_scopes": [{"scope_type": "area", "area_id": 2}]}
    sql, params = MySqlDataExchangeStore._export_scope(user, "imports")
    assert "imported_by" in sql
    assert params == [7]


def test_attachment_upload_checks_target_data_scope_before_writing(tmp_path: Path) -> None:
    class DenyingStore(FakeExchangeStore):
        def attachment_target_accessible(self, user: dict[str, Any], organization_id: int, entity_type: str, entity_id: int) -> bool:
            del user, organization_id, entity_type, entity_id
            return False

    service = DataExchangeService(DenyingStore(), tmp_path)
    scoped_user = {
        "id": 7,
        "permissions": ["attachment.manage"],
        "roles": [{"code": "breed_manager"}],
        "data_scopes": [{"scope_type": "area", "area_id": 2, "organization_id": 1}],
    }
    with pytest.raises(DomainError, match="无权访问"):
        service.upload_attachment(
            scoped_user,
            organization_id=1,
            entity_type="production:losses",
            entity_id=99,
            file_name="evidence.pdf",
            media_type="application/pdf",
            content=b"%PDF-1.4\n%%EOF\n",
        )
    assert not list(tmp_path.iterdir())


def test_attachment_target_scope_allows_area_or_owner_only() -> None:
    area_user = {"id": 7, "data_scopes": [{"scope_type": "area", "area_id": 2}]}
    personal_user = {"id": 7, "data_scopes": [{"scope_type": "personal"}]}
    target = {"organization_id": 1, "area_id": 2, "created_by": 9}
    assert MySqlDataExchangeStore._target_scope_allows(area_user, target) is True
    assert MySqlDataExchangeStore._target_scope_allows(area_user, {**target, "area_id": 3}) is False
    assert MySqlDataExchangeStore._target_scope_allows(personal_user, {**target, "created_by": 7}) is True
    assert MySqlDataExchangeStore._target_scope_allows(personal_user, target) is False


def test_attachment_upload_uses_atomic_scoped_insert_when_store_supports_it(tmp_path: Path) -> None:
    class AtomicStore(FakeExchangeStore):
        atomic_called = False

        def create_scoped_attachment(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
            self.atomic_called = True
            return {"id": 8, **payload}

    store = AtomicStore()
    service = DataExchangeService(store, tmp_path)
    user = {"id": 7, "permissions": ["attachment.manage"], "data_scopes": []}
    created = service.upload_attachment(
        user,
        organization_id=1,
        entity_type="cost:entry",
        entity_id=9,
        file_name="voucher.pdf",
        media_type="application/pdf",
        content=b"%PDF-1.4\n%%EOF\n",
    )

    assert created["id"] == 8
    assert store.atomic_called is True


class ImportCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = list(rows)
        self.statements: list[str] = []
        self.params: list[tuple[Any, ...]] = []
        self.lastrowid = 1

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.statements.append(" ".join(sql.split()))
        self.params.append(tuple(params))

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows.pop(0) if self.rows else None


def test_pond_import_enforces_area_scope_before_insert() -> None:
    cursor = ImportCursor([
        {"organization_id": 1},
        {"organization_id": 1, "farm_id": 4},
    ])
    with pytest.raises(DomainError, match="授权范围"):
        _import_ponds(
            cursor,
            {"farm_id": 4, "area_id": 3, "code": "P-OUT", "name": "越权塘", "capacity_mu": 1},
            organization_id=1,
            user={"id": 7, "data_scopes": [{"scope_type": "area", "area_id": 2}]},
            user_id=7,
        )
    assert not any(sql.startswith("INSERT INTO ponds") for sql in cursor.statements)


def test_area_scoped_master_import_is_bound_to_its_single_authorized_area() -> None:
    cursor = ImportCursor([{"organization_id": 1, "farm_id": 4}])
    _import_master(
        cursor,
        {"code": "MAT-AREA", "name": "区域物料"},
        organization_id=1,
        user={"id": 7, "data_scopes": [{"scope_type": "area", "area_id": 2}]},
        user_id=7,
        table="materials",
        entity_type="master:materials",
    )
    insert_index = next(index for index, sql in enumerate(cursor.statements) if sql.startswith("INSERT INTO materials"))
    assert "farm_id,area_id" in cursor.statements[insert_index]
    assert 4 in cursor.params[insert_index] and 2 in cursor.params[insert_index]


def test_area_scoped_expense_import_keeps_cost_area_traceability() -> None:
    cursor = ImportCursor([
        {"id": 9},
        {"default_nature": "direct"},
        {"organization_id": 1, "farm_id": 4},
    ])
    import_expense(
        cursor,
        {"code": "EXP-AREA", "name": "区域费用", "category_code": "FEED", "amount": 100, "happened_at": "2026-08-24"},
        organization_id=1,
        user={"id": 7, "data_scopes": [{"scope_type": "area", "area_id": 2}]},
        user_id=7,
    )
    insert_index = next(index for index, sql in enumerate(cursor.statements) if sql.startswith("INSERT INTO cost_entries"))
    assert "farm_id,area_id" in cursor.statements[insert_index]
    assert 4 in cursor.params[insert_index] and 2 in cursor.params[insert_index]


@pytest.mark.parametrize(
    ("importer", "id_field"),
    [(import_payment, "payable_id"), (import_customer_receipt, "receivable_id")],
)
def test_financial_import_enforces_source_order_area(importer: Any, id_field: str) -> None:
    cursor = ImportCursor([{"id": 5, "status": "unpaid", "area_id": 3}])
    with pytest.raises(DomainError, match="授权范围"):
        importer(
            cursor,
            {id_field: 5, "code": "FIN-OUT", "amount": 10, "happened_at": "2026-08-24"},
            organization_id=1,
            user={"id": 7, "data_scopes": [{"scope_type": "area", "area_id": 2}]},
            user_id=7,
        )
    assert not any(sql.startswith("INSERT INTO") for sql in cursor.statements[1:])


def test_import_scalar_parsers_reject_suffixes_precision_tricks_and_invalid_decimal() -> None:
    assert _date("2026-08-24-extra") is None
    assert _int("1e3") is None
    assert _int(12.0) == 12
    with pytest.raises(DomainError, match="数字"):
        _decimal("not-a-number")


def test_preview_business_validation_receives_current_user_scope(tmp_path: Path) -> None:
    class TrackingStore(FakeExchangeStore):
        checked_user: dict[str, Any] | None = None

        def validate_rows(self, user: dict[str, Any], organization_id: int, template_code: str, rows: list[dict[str, Any]], row_numbers: list[int]) -> list[dict[str, Any]]:
            del organization_id, template_code, rows
            self.checked_user = user
            return [{"row": row_numbers[0], "column": "area_id", "message": "无权预览该区域", "value": 3}]

    store = TrackingStore()
    service = DataExchangeService(store, tmp_path)
    user = {
        "id": 7,
        "permissions": ["data_exchange.import"],
        "roles": [{"code": "breed_manager"}],
        "data_scopes": [{"scope_type": "area", "area_id": 2, "organization_id": 1}],
    }
    batch = service.preview(
        user,
        organization_id=1,
        template_code="materials",
        file_name="materials.xlsx",
        content=workbook([["MAT-SCOPE", "范围物料", "饲料", "kg"]]),
    )
    assert store.checked_user is user
    assert batch["status"] == "invalid" and batch["failed_rows"] == 1


def test_master_data_rejects_cross_organization_hierarchy() -> None:
    with disposable_database("adp_master_scope", through=24) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO users (phone,name,password_hash,status) VALUES ('13981110001','范围管理员','hash','active')")
            user_id = int(cursor.lastrowid)
            cursor.execute("SELECT id,organization_id FROM farms WHERE code='default-farm'")
            default_farm = cursor.fetchone()
            cursor.execute("INSERT INTO organizations (code,name) VALUES ('other-org','其他企业')")
            other_org = int(cursor.lastrowid)
            cursor.execute("INSERT INTO farms (organization_id,code,name) VALUES (%s,'other-farm','其他基地')", (other_org,))
            other_farm = int(cursor.lastrowid)
            cursor.execute("INSERT INTO areas (organization_id,farm_id,code,name,status,row_version,created_by) VALUES (%s,%s,'OTHER-A','其他区域','verified',1,%s)", (other_org, other_farm, user_id))
            other_area = int(cursor.lastrowid)
        service = MasterDataService(MySqlMasterDataStore(settings))
        user = {"id": user_id, "permissions": ["master_data.ponds.manage"], "data_scopes": []}
        with pytest.raises(DomainError, match="MASTER_SCOPE_MISMATCH"):
            service.create(user, "ponds", {
                "organization_id": int(default_farm["organization_id"]),
                "farm_id": int(default_farm["id"]),
                "area_id": other_area,
                "code": "CROSS-ORG-POND",
                "name": "跨企业塘口",
            })


def test_personal_scope_cannot_read_or_write_another_users_warehouse_record() -> None:
    personal = {"id": 7, "data_scopes": [{"scope_type": "personal"}]}
    foreign = {"area_id": 2, "created_by": 9}
    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        WarehouseService._scope(personal, foreign)
    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        MySqlWarehouseStore._require_scope(personal, foreign)

    WarehouseService._scope(personal, {**foreign, "created_by": 7})
    MySqlWarehouseStore._require_scope(personal, {**foreign, "created_by": 7})


def test_cost_target_must_belong_to_selected_enterprise_and_farm() -> None:
    cursor = ImportCursor([
        {"organization_id": 1},
        {"organization_id": 2, "farm_id": 9, "area_id": 8},
    ])
    with pytest.raises(DomainError, match="COST_TARGET_SCOPE_INVALID"):
        validate_cost_scope(
            cursor,
            {"organization_id": 1, "farm_id": 4, "target_type": "batch", "target_id": 99},
            {"id": 7, "data_scopes": []},
        )
