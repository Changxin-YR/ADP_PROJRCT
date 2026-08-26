from decimal import Decimal

import pytest

from backend.layers.features.cost.calculation import allocate_amount, summarize_costs, unit_production_cost


ROWS = [
    {"id": 1, "code": "pond_rent", "name": "塘租", "nature": "public", "amount": Decimal("120000.00")},
    {"id": 2, "code": "equipment", "name": "设备", "nature": "public", "amount": Decimal("38000.00")},
    {"id": 3, "code": "infrastructure", "name": "基础建设", "nature": "public", "amount": Decimal("46000.00")},
    {"id": 4, "code": "labor", "name": "人工", "nature": "public", "amount": Decimal("144000.00")},
    {"id": 5, "code": "electricity", "name": "电费", "nature": "public", "amount": Decimal("42000.00")},
    {"id": 6, "code": "seed", "name": "苗种", "nature": "direct", "amount": Decimal("96000.00")},
    {"id": 7, "code": "feed", "name": "饲料", "nature": "direct", "amount": Decimal("128000.00")},
    {"id": 8, "code": "health", "name": "动保", "nature": "direct", "amount": Decimal("26000.00")},
    {"id": 9, "code": "other", "name": "其他费用", "nature": "public", "amount": Decimal("32000.00")},
]


def test_structure_uses_one_total_for_all_shares() -> None:
    result = summarize_costs(ROWS)

    assert result["total_amount"] == "672000.00"
    assert result["direct_amount"] == "250000.00"
    assert result["public_amount"] == "422000.00"
    assert result["direct_share"] == "37.2024"
    assert result["public_share"] == "62.7976"
    assert result["categories"][0]["id"] == 1
    assert sum(Decimal(item["share"]) for item in result["categories"]) == Decimal("100.0000")


def test_zero_total_returns_unavailable_shares() -> None:
    result = summarize_costs([{**ROWS[0], "amount": Decimal("0.00")}])

    assert result["total_amount"] == "0.00"
    assert result["direct_share"] is None
    assert result["categories"][0]["share"] is None


def test_structure_uses_entry_level_nature_totals_when_present() -> None:
    result = summarize_costs([
        {"id": 9, "code": "other", "name": "其他费用", "nature": "public", "amount": Decimal("100.00"), "direct_amount": Decimal("40.00")},
    ])

    assert result["direct_amount"] == "40.00"
    assert result["public_amount"] == "60.00"
    assert result["direct_share"] == "40.0000"


def test_structure_reports_no_data_when_left_join_categories_have_no_entries() -> None:
    result = summarize_costs([
        {
            "id": 7,
            "code": "feed",
            "name": "饲料",
            "nature": "direct",
            "amount": Decimal("0.00"),
            "direct_amount": Decimal("0.00"),
            "confirmed_entry_count": 0,
        }
    ])

    assert result["has_data"] is False
    assert result["confirmed_entry_count"] == 0


def test_unit_cost_requires_confirmed_output_weight() -> None:
    assert unit_production_cost(Decimal("672000"), Decimal("0")) is None
    assert unit_production_cost(Decimal("672000"), Decimal("98000")) == "6.8571"


def test_allocation_preserves_cents_and_is_deterministic() -> None:
    result = allocate_amount(Decimal("100.00"), [(3, Decimal("3")), (1, Decimal("1")), (2, Decimal("2"))])

    assert result == {1: Decimal("16.67"), 2: Decimal("33.33"), 3: Decimal("50.00")}
    assert sum(result.values()) == Decimal("100.00")


def test_all_zero_drivers_fall_back_to_equal() -> None:
    result = allocate_amount(Decimal("100.00"), [(3, Decimal("0")), (1, Decimal("0")), (2, Decimal("0"))])

    assert result == {1: Decimal("33.34"), 2: Decimal("33.33"), 3: Decimal("33.33")}


def test_negative_reversal_allocation_preserves_sign_and_cents() -> None:
    result = allocate_amount(Decimal("-10.00"), [(2, Decimal("1")), (1, Decimal("1")), (3, Decimal("1"))])

    assert result == {1: Decimal("-3.34"), 2: Decimal("-3.33"), 3: Decimal("-3.33")}
    assert sum(result.values()) == Decimal("-10.00")


def test_negative_driver_is_rejected() -> None:
    with pytest.raises(ValueError, match="ALLOCATION_DRIVER_NEGATIVE"):
        allocate_amount(Decimal("10.00"), [(1, Decimal("-1")), (2, Decimal("2"))])
