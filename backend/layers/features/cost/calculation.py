from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any, Iterable


CENT = Decimal("0.01")
PERCENT = Decimal("0.0001")


def _money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _percentage(part: Decimal, total: Decimal) -> str | None:
    if total == 0:
        return None
    return str((part * Decimal("100") / total).quantize(PERCENT, rounding=ROUND_HALF_UP))


def summarize_costs(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    normalized = [
        {
            **row,
            "amount": Decimal(str(row["amount"])),
            **({"direct_amount": Decimal(str(row["direct_amount"]))} if "direct_amount" in row else {}),
        }
        for row in rows
    ]
    total = sum((row["amount"] for row in normalized), Decimal("0"))
    direct = sum(
        (
            row["direct_amount"]
            if "direct_amount" in row
            else row["amount"] if row["nature"] == "direct" else Decimal("0")
            for row in normalized
        ),
        Decimal("0"),
    )
    public = total - direct
    has_entry_counts = any("confirmed_entry_count" in row for row in normalized)
    confirmed_entry_count = (
        sum(int(row.get("confirmed_entry_count", 0)) for row in normalized)
        if has_entry_counts
        else int(any(row["amount"] != 0 for row in normalized))
    )
    categories = [
        {
            "id": int(row["id"]),
            "code": row["code"],
            "name": row["name"],
            "nature": row["nature"],
            "amount": _money(row["amount"]),
            "share": _percentage(row["amount"], total),
            **({"allocation_driver": row["allocation_driver"]} if "allocation_driver" in row else {}),
        }
        for row in normalized
    ]
    if total != 0 and categories:
        displayed = [Decimal(item["share"]) for item in categories if item["share"] is not None]
        difference = Decimal("100.0000") - sum(displayed, Decimal("0"))
        if difference:
            categories[-1]["share"] = str(Decimal(categories[-1]["share"]) + difference)
    return {
        "total_amount": _money(total),
        "direct_amount": _money(direct),
        "public_amount": _money(public),
        "direct_share": _percentage(direct, total),
        "public_share": _percentage(public, total),
        "confirmed_entry_count": confirmed_entry_count,
        "has_data": confirmed_entry_count > 0,
        "categories": categories,
    }


def unit_production_cost(total_cost: Decimal, output_weight_jin: Decimal) -> str | None:
    if output_weight_jin <= 0:
        return None
    return str((total_cost / output_weight_jin).quantize(PERCENT, rounding=ROUND_HALF_UP))


def allocate_amount(amount: Decimal, drivers: list[tuple[int, Decimal]]) -> dict[int, Decimal]:
    if not drivers:
        return {}
    ordered = sorted((item_id, Decimal(value)) for item_id, value in drivers)
    if any(value < 0 for _, value in ordered):
        raise ValueError("ALLOCATION_DRIVER_NEGATIVE")
    denominator = sum((value for _, value in ordered), Decimal("0"))
    if denominator <= 0:
        ordered = [(item_id, Decimal("1")) for item_id, _ in ordered]
        denominator = Decimal(len(ordered))
    sign = Decimal("-1") if amount < 0 else Decimal("1")
    total_cents = int((abs(amount) / CENT).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    raw = [(item_id, Decimal(total_cents) * value / denominator) for item_id, value in ordered]
    floors = {item_id: int(value.quantize(Decimal("1"), rounding=ROUND_DOWN)) for item_id, value in raw}
    remaining = total_cents - sum(floors.values())
    ranked = sorted(raw, key=lambda item: (-(item[1] - Decimal(floors[item[0]])), item[0]))
    for item_id, _ in ranked[:remaining]:
        floors[item_id] += 1
    return {item_id: Decimal(cents) * CENT * sign for item_id, cents in sorted(floors.items())}
