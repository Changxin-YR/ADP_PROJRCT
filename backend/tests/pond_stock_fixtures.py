"""塘口存塘量只读汇总的共享测试装置：fake store + 断言口径。

fake store 存放口径与真实库一致：
- stock_records: [{pond_id, batch_id, quantity_delta, weight_delta_kg}]
- batches:       [{batch_id, pond_id, code, name, batch_status}]
- samplings:     [{document_id, pond_id, happened_at, quantity, weight_kg, status}]
聚合逻辑直接复用 MySqlProductionStore 的 _aggregate_pond_stock（不复制第二套口径）。
"""
from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.production.production_service import ProductionService
from backend.layers.features.production.production_store import MySqlProductionStore
from fake_auth_store import FakeAuthStore


SUMMARIZABLE = MySqlProductionStore.SUMMARIZABLE_POND_STATUS


def user(*permissions: str, scopes: list[dict[str, Any]] | None = None, user_id: int = 1) -> dict[str, Any]:
    return {"id": user_id, "permissions": list(permissions), "data_scopes": list(scopes or [])}


def in_scope(actor: dict[str, Any], pond: dict[str, Any]) -> bool:
    """与 data_scope.row_in_scope 相同口径的最小实现，供 fake store 使用。"""
    scopes = actor.get("data_scopes") or []
    if not scopes:
        return True
    areas = {int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")}
    return int(pond.get("area_id") or 0) in areas


class FakePondStockStore:
    """只读汇总用 fake store：事实来源 = batch_stock_records 等价流水 + 已核验抽样。

    存放口径与真实库一致：
    - stock_records: [{pond_id, batch_id, quantity_delta, weight_delta_kg}]
    - batches:       [{batch_id, pond_id, code, name, batch_status}]
    - samplings:     [{document_id, pond_id, happened_at, quantity, weight_kg, status}]
    """

    def __init__(self, ponds: list[dict[str, Any]]) -> None:
        self.ponds = {int(pond["id"]): dict(pond) for pond in ponds}
        self.stock_records: list[dict[str, Any]] = []
        self.batches: list[dict[str, Any]] = []
        self.samplings: list[dict[str, Any]] = []

    # --- 与 MySqlProductionStore 一致的聚合与查询入口 ---
    _aggregate_pond_stock = staticmethod(MySqlProductionStore._aggregate_pond_stock)
    _pond_ids = staticmethod(MySqlProductionStore._pond_ids)
    parse_pond_ids = staticmethod(MySqlProductionStore.parse_pond_ids)

    def _visible(self, actor: dict[str, Any], pond: dict[str, Any]) -> bool:
        return pond.get("status") in SUMMARIZABLE and in_scope(actor, pond)

    def _row(self, pond: dict[str, Any]) -> dict[str, Any]:
        return {
            "pond_id": int(pond["id"]), "pond_code": pond.get("code"), "pond_name": pond.get("name"),
            "pond_status": pond.get("status"), "manual_stock_quantity": pond.get("stock_quantity"),
            "manual_current_spec": pond.get("current_spec"),
        }

    def list_pond_stock_summary_rows(self, pond_ids: list[int], *, user: dict[str, Any]) -> list[dict[str, Any]]:
        targets = {int(pond_id) for pond_id in pond_ids}
        rows: list[dict[str, Any]] = []
        for pond_id in sorted(targets):
            pond_records = [record for record in self.stock_records if int(record["pond_id"]) == pond_id]
            for record in pond_records:
                rows.append({
                    "pond_id": pond_id, "row_kind": "stock",
                    "quantity_delta": Decimal(str(record["quantity_delta"])),
                    "weight_delta_kg": Decimal(str(record["weight_delta_kg"])),
                })
            for batch_id in dict.fromkeys(int(record["batch_id"]) for record in pond_records):
                rows.append({"pond_id": pond_id, "row_kind": "batch", "batch_id": batch_id})
            for sampling in self.samplings:
                if int(sampling["pond_id"]) == pond_id and sampling.get("status") == "verified":
                    rows.append({
                        "pond_id": pond_id, "row_kind": "sampling", "document_id": int(sampling["document_id"]),
                        "happened_at": sampling.get("happened_at"), "created_at": sampling.get("happened_at"),
                    })
        return rows

    def list_pond_stock_summary(self, *, user: dict[str, Any], page: int = 1, page_size: int = 50,
                                pond_ids: list[int] | None = None) -> dict[str, Any]:
        targets = set(self._pond_ids(pond_ids or []))
        ponds = [self._row(pond) for pond in self.ponds.values() if self._visible(user, pond) and (not targets or int(pond["id"]) in targets)]
        ponds.sort(key=lambda item: item["pond_id"])
        if targets:
            window = ponds
        else:
            start = (max(1, int(page)) - 1) * max(1, int(page_size))
            window = ponds[start:start + max(1, int(page_size))]
        sliced = window is not ponds
        return {
            "ponds": window, "page": max(1, int(page)), "page_size": max(1, int(page_size)), "total": len(ponds),
            "has_next": sliced and (max(1, int(page)) * max(1, int(page_size))) < len(ponds),
            "rows": self.list_pond_stock_summary_rows([item["pond_id"] for item in window], user=user),
        }

    def get_pond_stock_summary(self, pond_id: int, *, user: dict[str, Any]) -> dict[str, Any] | None:
        pond = self.ponds.get(int(pond_id))
        if pond is None or pond.get("status") not in SUMMARIZABLE:
            return None
        if not in_scope(user, pond):
            raise DomainError("DATA_SCOPE_FORBIDDEN", "无权访问授权范围之外的塘口存塘量", 403)
        result = self.list_pond_stock_summary(user=user, pond_ids=[int(pond_id)])
        result.update(page=1, page_size=1, total=1, has_next=False)
        return result

    def list_pond_batches(self, pond_id: int) -> list[dict[str, Any]]:
        rows = []
        for batch in self.batches:
            if int(batch["pond_id"]) != int(pond_id):
                continue
            records = [item for item in self.stock_records if int(item["batch_id"]) == int(batch["batch_id"])]
            rows.append({
                "batch_id": int(batch["batch_id"]), "code": batch.get("code"), "name": batch.get("name"),
                "batch_status": batch.get("batch_status"), "species": batch.get("species"),
                "quantity": sum((Decimal(str(item["quantity_delta"])) for item in records), Decimal("0")),
                "weight_kg": sum((Decimal(str(item["weight_delta_kg"])) for item in records), Decimal("0")),
                "stock_record_count": len(records),
            })
        return sorted(rows, key=lambda item: item["batch_id"])

    def get_latest_verified_sampling(self, pond_id: int) -> dict[str, Any] | None:
        candidates = [item for item in self.samplings if int(item["pond_id"]) == int(pond_id) and item.get("status") == "verified"]
        if not candidates:
            return None
        latest = max(candidates, key=lambda item: (str(item.get("happened_at")), int(item["document_id"])))
        return {
            "document_id": int(latest["document_id"]), "occurred_at": latest.get("happened_at"),
            "quantity": latest.get("quantity"), "weight_kg": latest.get("weight_kg"),
            "batch_id": latest.get("batch_id"), "code": latest.get("code"),
        }


def pond(pond_id: int = 10, **overrides: Any) -> dict[str, Any]:
    return {
        "id": pond_id, "code": f"P-{pond_id:03d}", "name": f"{pond_id} 号塘", "area_id": 1,
        "farm_id": 1, "organization_id": 1, "status": "verified",
        "stock_quantity": None, "current_spec": None, **overrides,
    }


def seeded_store() -> FakePondStockStore:
    store = FakePondStockStore([pond(10), pond(11, stock_quantity=Decimal("9000"), current_spec="400g/尾"), pond(12)])
    store.batches = [
        {"batch_id": 1, "pond_id": 10, "code": "B-001", "name": "春季虾一批", "batch_status": "farming", "species": "南美白对虾"},
        {"batch_id": 2, "pond_id": 10, "code": "B-002", "name": "春季虾二批", "batch_status": "stocked", "species": "南美白对虾"},
    ]
    store.stock_records = [
        {"batch_id": 1, "pond_id": 10, "quantity_delta": Decimal("1000"), "weight_delta_kg": Decimal("20")},
        {"batch_id": 1, "pond_id": 10, "quantity_delta": Decimal("-300"), "weight_delta_kg": Decimal("-6")},
        {"batch_id": 2, "pond_id": 10, "quantity_delta": Decimal("500"), "weight_delta_kg": Decimal("11.5")},
    ]
    store.samplings = [
        {"document_id": 7, "pond_id": 10, "happened_at": datetime(2026, 5, 1, 8, 0), "quantity": Decimal("30"), "weight_kg": Decimal("6.75"), "status": "verified"},
        {"document_id": 9, "pond_id": 10, "happened_at": datetime(2026, 6, 2, 8, 0), "quantity": Decimal("40"), "weight_kg": Decimal("11"), "status": "verified"},
        {"document_id": 11, "pond_id": 10, "happened_at": datetime(2026, 7, 2, 8, 0), "quantity": Decimal("50"), "weight_kg": Decimal("15"), "status": "submitted"},
    ]
    return store


def test_pond_stock_summary_sums_every_batch_of_the_pond() -> None:
    service = ProductionService(seeded_store())

    summary = service.pond_stock_summary(user("production.view"), 10)

    # 1000-300+500 = 1200 尾；20-6+11.5 = 25.5 kg
    assert summary["batch_stock"] == {"quantity": "1200.000", "weight_kg": "25.500"}
    assert summary["data_source"] == "batch_ledger"
    assert [item["batch_id"] for item in summary["batches"]] == [1, 2]
    assert summary["batches"][0]["quantity"] == "700.000"
    assert summary["batches"][0]["weight_kg"] == "14.000"
    assert summary["batches"][1]["quantity"] == "500.000"
    assert summary["batches"][1]["batch_status"] == "stocked"


def test_pond_stock_summary_returns_latest_verified_sampling_only() -> None:
    service = ProductionService(seeded_store())

    summary = service.pond_stock_summary(user("production.view"), 10)

    # 2026-07-02 的抽样仍是 submitted，不能作为事实；取 2026-06-02 已核验那条
    assert summary["latest_sampling"]["document_id"] == 9
    assert summary["latest_sampling"]["quantity"] == "40.000"
    assert summary["latest_sampling"]["weight_kg"] == "11.000"
    assert summary["latest_sampling"]["avg_weight_kg"] == "0.275"


def test_pond_stock_summary_falls_back_to_manual_archive_value_without_ledger() -> None:
    service = ProductionService(seeded_store())

    summary = service.pond_stock_summary(user("production.view"), 11)

    assert summary["batch_stock"] == {"quantity": "0.000", "weight_kg": "0.000"}
    assert summary["manual_stock"] == {"quantity": "9000.000", "current_spec": "400g/尾"}
    assert summary["data_source"] == "manual"
    assert summary["batches"] == []
    assert summary["latest_sampling"] is None


def test_pond_stock_summary_reports_none_source_without_ledger_or_manual_value() -> None:
    service = ProductionService(seeded_store())

    summary = service.pond_stock_summary(user("production.view"), 12)

    assert summary["data_source"] == "none"
    assert summary["manual_stock"] == {"quantity": None, "current_spec": None}
    assert summary["latest_sampling"] is None


def test_pond_stock_summary_requires_production_view_permission() -> None:
    service = ProductionService(seeded_store())

    with pytest.raises(DomainError, match="FORBIDDEN"):
        service.pond_stock_summary(user("master_data.view"), 10)


def test_pond_stock_summary_rejects_pond_outside_data_scope() -> None:
    store = FakePondStockStore([pond(21, area_id=99)])
    service = ProductionService(store)

    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN") as excinfo:
        service.pond_stock_summary(user("production.view", scopes=[{"scope_type": "area", "area_id": 1}]), 21)

    assert excinfo.value.status == 403


def test_pond_stock_summary_returns_not_found_for_unknown_pond() -> None:
    service = ProductionService(seeded_store())

    with pytest.raises(DomainError, match="POND_NOT_FOUND"):
        service.pond_stock_summary(user("production.view"), 999)


def test_list_pond_stock_summaries_covers_many_ponds_without_n_plus_one() -> None:
    store = seeded_store()
    service = ProductionService(store)

    result = service.list_pond_stock_summaries(user("production.view"), page=1, page_size=50)

    assert result["total"] == 3
    assert [item["pond_id"] for item in result["items"]] == [10, 11, 12]
    assert {item["data_source"] for item in result["items"]} == {"batch_ledger", "manual", "none"}
    assert result["items"][0]["batch_count"] == 2
    assert result["items"][0]["latest_sampling"]["document_id"] == 9
    assert result["source"] == "production_facts"


def test_list_pond_stock_summaries_honours_pond_ids_and_page_size() -> None:
    store = seeded_store()
    service = ProductionService(store)

    targeted = service.list_pond_stock_summaries(user("production.view"), pond_ids=[11, 12], page_size=1)

    # pond_ids 显式指定时不裁剪（列表页一次拉多口塘，避免 N+1）
    assert [item["pond_id"] for item in targeted["items"]] == [11, 12]
    assert targeted["total"] == 2
    assert [item["data_source"] for item in targeted["items"]] == ["manual", "none"]


def test_list_pond_stock_summaries_paginates_plain_requests() -> None:
    service = ProductionService(seeded_store())

    result = service.list_pond_stock_summaries(user("production.view"), page=2, page_size=2)

    assert [item["pond_id"] for item in result["items"]] == [12]
    assert result["total"] == 3
    assert result["has_next"] is False
    assert result["page"] == 2


def test_pond_ids_reject_non_positive_values() -> None:
    with pytest.raises(DomainError, match="POND_IDS_INVALID"):
        MySqlProductionStore._pond_ids(["abc"])

    with pytest.raises(DomainError, match="POND_IDS_INVALID"):
        MySqlProductionStore._pond_ids([0])
