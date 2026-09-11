from __future__ import annotations

from decimal import Decimal

import pytest

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.production.production_service import ProductionService
from backend.layers.features.production.production_store import MySqlProductionStore
from pond_stock_fixtures import FakePondStockStore, pond, seeded_store, user


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
