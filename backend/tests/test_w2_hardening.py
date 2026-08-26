from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backend.app import create_app
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.mysql_store import MySqlAuthStore
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.security.password import weak_password_reason
from backend.layers.common.security.session import hash_session_token, new_session_token
from backend.layers.common.validation.auth_validation import ValidationError, validate_password
from backend.layers.features.master_data.master_data_service import MasterDataService
from backend.layers.features.master_data.master_data_store import MySqlMasterDataStore
from backend.layers.features.production.daily_operation_rules import normalize_daily_operation_payload
from backend.layers.features.production.production_filters import apply_record_filters
from backend.layers.features.production.production_service import ProductionService
from backend.layers.features.warehouse.warehouse_service import WarehouseService
from backend.tests.mysql_test_database import disposable_database, settings_for
from test_master_data_api import FakeMasterStore
from test_production_flow import FakeProductionStore, user

# ---------- 1. 密码策略（BUG-M4-08） ----------

@pytest.mark.parametrize(
    "password",
    ["abc12345", "1111aaaa", "aaaa1111", "qwerty123", "admin8888", "1qaz2wsx9", "qwer1234", "asdf1234"],
)
def test_w2_weak_passwords_are_rejected_with_code(password: str) -> None:
    with pytest.raises(ValidationError) as caught:
        validate_password(password, password)
    assert caught.value.code == "WEAK_PASSWORD"


@pytest.mark.parametrize("password", ["FarmPass9!", "Xy7!Kp9#Lm2Q", "Blue3#Sky4$Wave"])
def test_w2_strong_passwords_pass_policy(password: str) -> None:
    assert validate_password(password, password) == password


@pytest.mark.parametrize("password", [12345678, ["FarmPass9!"], {"value": "FarmPass9!"}])
def test_password_validation_rejects_non_string_input_as_business_error(password: Any) -> None:
    with pytest.raises(ValidationError, match="字符串"):
        validate_password(password, password)  # type: ignore[arg-type]


def test_password_validation_rejects_excessive_length() -> None:
    password = "A1!" * 100
    with pytest.raises(ValidationError, match="128"):
        validate_password(password, password)


def test_w2_weak_password_reason_detects_sequences() -> None:
    assert weak_password_reason("xq1234zx9a") == "包含连续递增数字"
    assert weak_password_reason("ab9876cd1x") == "包含连续递减数字"
    assert weak_password_reason("az1111qk89") == "包含连续重复字符"
    assert weak_password_reason("qzqazwsx12") == "包含键盘顺序字符"
    assert weak_password_reason("FarmPass9!") is None


# ---------- 2. 塘口字段预校验（BUG-M4-01/02/04、BUG-007） ----------

def _pond_manager() -> dict[str, Any]:
    return {"id": 1, "permissions": ["master_data.ponds.manage"], "data_scopes": []}


def test_w2_pond_invalid_capacity_name_status_are_400() -> None:
    service = MasterDataService(FakeMasterStore())
    with pytest.raises(DomainError, match="capacity_mu"):
        service.create(_pond_manager(), "ponds", {"code": "P1", "name": "塘1", "capacity_mu": "abc"})
    with pytest.raises(DomainError, match="capacity_mu"):
        service.create(_pond_manager(), "ponds", {"code": "P1", "name": "塘1", "capacity_mu": -3})
    with pytest.raises(DomainError, match="120"):
        service.create(_pond_manager(), "ponds", {"code": "P1", "name": "塘" * 121})
    with pytest.raises(DomainError, match="筹建"):
        service.create(_pond_manager(), "ponds", {"code": "P1", "name": "塘1", "pond_status": "farming"})
    with pytest.raises(DomainError, match="aerator_count"):
        service.create(_pond_manager(), "ponds", {"code": "P1", "name": "塘1", "aerator_count": -1})
    with pytest.raises(DomainError, match="stock_quantity_source"):
        service.create(_pond_manager(), "ponds", {"code": "P1", "name": "塘1", "stock_quantity_source": "guessed"})


def test_w2_pond_extended_fields_accepted_and_roundtrip() -> None:
    service = MasterDataService(FakeMasterStore())
    created = service.create(_pond_manager(), "ponds", {
        "code": "P-EXT", "name": "扩展塘", "capacity_mu": 12.5, "pond_status": "build",
        "aerator_count": 4, "stocking_spec": "3cm", "current_spec": "12cm",
        "stock_quantity": 5000, "stock_quantity_source": "measured",
    })
    assert created["aerator_count"] == 4
    assert created["stocking_spec"] == "3cm"
    assert created["current_spec"] == "12cm"
    assert created["stock_quantity"] == 5000
    assert created["stock_quantity_source"] == "measured"


# ---------- 3. 批次字段预校验（BUG-M4-06/07、1e18、2026-02-30） ----------

def _production_service() -> ProductionService:
    return ProductionService(FakeProductionStore())


def test_w2_batch_quantity_and_date_violations_are_400() -> None:
    service = _production_service()
    creator = user(1, "production.view", "production.manage")
    with pytest.raises(DomainError, match="大于 0"):
        service.create(creator, "batches", {"code": "B1", "name": "批", "pond_id": 10, "species": "虾", "initial_quantity": 0})
    with pytest.raises(DomainError, match="超出允许范围"):
        service.create(creator, "batches", {"code": "B1", "name": "批", "pond_id": 10, "species": "虾", "initial_quantity": 1e18})
    with pytest.raises(DomainError, match="不能早于"):
        service.create(creator, "batches", {
            "code": "B1", "name": "批", "pond_id": 10, "species": "虾", "initial_quantity": 1000,
            "stocked_at": "2026-01-10T08:00:00", "expected_harvest_date": "2026-01-09",
        })
    with pytest.raises(DomainError, match="日期格式无效"):
        service.create(creator, "batches", {
            "code": "B1", "name": "批", "pond_id": 10, "species": "虾", "initial_quantity": 1000,
            "expected_harvest_date": "2026-02-30",
        })
    with pytest.raises(DomainError, match="日期格式无效"):
        service.create(creator, "batches", {
            "code": "B2", "name": "批", "pond_id": 10, "species": "虾", "initial_quantity": 1000,
            "expected_harvest_date": "2026-02-20-not-a-date",
        })


def test_w2_batch_update_and_stock_movements_reject_zero_quantity() -> None:
    service = _production_service()
    manager = user(1, "production.view", "production.manage")
    batch = service.create(manager, "batches", {
        "code": "B-ZERO", "name": "批", "pond_id": 10, "species": "虾", "initial_quantity": 1000,
    })
    with pytest.raises(DomainError, match="大于 0"):
        service.update(manager, "batches", batch["id"], {
            "expected_version": batch["version"], "initial_quantity": 0,
        })
    with pytest.raises(DomainError, match="大于 0"):
        service.create(manager, "losses", {
            "code": "L-ZERO", "name": "损耗", "pond_id": 10, "batch_id": batch["id"], "quantity": 0,
        })


# ---------- 4. 日常作业类型化（BUG-012） ----------

def test_w2_daily_operation_typed_payload_is_normalized() -> None:
    service = _production_service()
    creator = user(1, "production.view", "production.manage")
    row = service.create(creator, "daily-operations", {
        "code": "D1", "name": "换水", "pond_id": 10, "operation_type": "water_change",
        "payload": {"volume_m3": 50, "water_source": "外河"},
    })
    assert row["payload"] == {"operation_type": "water_change", "source_detail": {"volume_m3": 50, "water_source": "外河"}}


def test_w2_daily_operation_missing_key_params_are_400() -> None:
    service = _production_service()
    creator = user(1, "production.view", "production.manage")
    with pytest.raises(DomainError, match="关键参数"):
        service.create(creator, "daily-operations", {
            "code": "D2", "name": "换水", "pond_id": 10, "operation_type": "water_change", "payload": {"volume_m3": 50},
        })
    with pytest.raises(DomainError, match="作业类型必须"):
        service.create(creator, "daily-operations", {
            "code": "D3", "name": "x", "pond_id": 10, "operation_type": "sweeping", "payload": {},
        })


def test_w2_daily_operation_water_quality_and_numeric_boundaries() -> None:
    service = _production_service()
    creator = user(1, "production.view", "production.manage")
    row = service.create(creator, "daily-operations", {
        "code": "D-WQ", "name": "水质检测", "pond_id": 10, "operation_type": "water_quality",
        "payload": {"temperature_c": 26.5, "ph": 7.4, "dissolved_oxygen_mg_l": 6.2},
    })
    assert row["payload"]["operation_type"] == "water_quality"
    with pytest.raises(DomainError, match="必须大于 0"):
        service.create(creator, "daily-operations", {
            "code": "D-NEG", "name": "换水", "pond_id": 10, "operation_type": "water_change",
            "payload": {"volume_m3": -1, "water_source": "外河"},
        })
    with pytest.raises(DomainError, match="安全间隔"):
        service.create(creator, "daily-operations", {
            "code": "D-MED", "name": "用药", "pond_id": 10, "operation_type": "medicine",
            "payload": {"medicine_name": "测试药", "dosage": 1, "usage_method": "泼洒"},
        })
    for invalid in ("nan", "inf"):
        with pytest.raises(DomainError, match="有效数字"):
            service.create(creator, "daily-operations", {
                "code": f"D-{invalid}", "name": "换水", "pond_id": 10, "operation_type": "water_change",
                "payload": {"volume_m3": invalid, "water_source": "外河"},
            })
    with pytest.raises(DomainError, match="非负整数"):
        service.create(creator, "daily-operations", {
            "code": "D-MED-FLOAT", "name": "用药", "pond_id": 10, "operation_type": "medicine",
            "payload": {"medicine_name": "测试药", "dosage": 1, "usage_method": "泼洒", "safety_interval_days": 1.5},
        })


def test_master_scope_rejects_non_numeric_area_as_business_error() -> None:
    scoped = {
        "id": 1,
        "permissions": ["master_data.ponds.manage"],
        "data_scopes": [{"scope_type": "area", "area_id": 2}],
    }
    with pytest.raises(DomainError, match="区域编号"):
        MasterDataService(FakeMasterStore()).create(
            scoped,
            "ponds",
            {"code": "P-BAD", "name": "塘口", "area_id": "abc", "capacity_mu": 1},
        )


def test_w2_daily_operation_generic_form_stays_compatible() -> None:
    service = _production_service()
    creator = user(1, "production.view", "production.manage")
    row = service.create(creator, "daily-operations", {"code": "D4", "name": "巡塘", "pond_id": 10})
    assert row.get("payload") is None


def test_w2_normalize_daily_operation_flat_detail_keys() -> None:
    clean: dict[str, Any] = {"operation_type": "patrol", "payload": {"water_quality": "正常", "fish_activity": "活跃"}}
    normalize_daily_operation_payload(clean, None)
    assert clean["payload"] == {
        "operation_type": "patrol",
        "source_detail": {"water_quality": "正常", "fish_activity": "活跃"},
    }


# ---------- 5. feed-logs 筛选（BUG-M1-001） ----------

def test_w2_feed_log_filters_build_clauses_and_reject_garbage() -> None:
    clauses: list[str] = ["document_type = %s"]
    values: list[Any] = ["feed_log"]
    apply_record_filters(clauses, values, pond_id="3", area_id="")
    assert clauses == ["document_type = %s", "pond_id = %s"]
    assert values == ["feed_log", 3]
    with pytest.raises(DomainError, match="筛选参数"):
        apply_record_filters([], [], pond_id="abc")


# ---------- 6. 报损/盘点字段校验（BUG-002） ----------

def test_w2_scraps_stocktakes_field_validation_is_400() -> None:
    with pytest.raises(DomainError, match="大于 0"):
        WarehouseService._validate("scraps", {"quantity": 0, "inventory_lot_id": 1})
    with pytest.raises(DomainError, match="格式无效"):
        WarehouseService._validate("scraps", {"quantity": "abc", "inventory_lot_id": 1})
    with pytest.raises(DomainError, match="日期格式无效"):
        WarehouseService._validate("stocktakes", {"quantity": 5, "inventory_lot_id": 1, "happened_at": "2026-02-30"})
    with pytest.raises(DomainError, match="单价格式无效"):
        WarehouseService._validate("scraps", {"quantity": 5, "inventory_lot_id": 1, "unit_cost": "abc"})
    with pytest.raises(DomainError, match="大于 0"):
        WarehouseService._validate("receipts", {"quantity": 0})
    with pytest.raises(DomainError, match="格式无效"):
        WarehouseService._validate("issues", {"quantity": "nan", "source_document_id": 1})
    with pytest.raises(DomainError, match="日期格式无效"):
        WarehouseService._validate("receipts", {"quantity": 1, "happened_at": "2026-08-24-garbage"})
    with pytest.raises(DomainError, match="单价格式无效"):
        WarehouseService._validate("receipts", {"quantity": 1, "unit_cost": "inf"})
