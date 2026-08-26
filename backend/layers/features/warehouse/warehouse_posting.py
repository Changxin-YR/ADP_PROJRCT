from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def amount(value: Any) -> Decimal:
    try:
        result = Decimal(str(value or 0))
    except InvalidOperation as exc:
        raise DomainError("WAREHOUSE_QUANTITY_INVALID", "库存数量格式无效", 400) from exc
    if result < 0:
        raise DomainError("WAREHOUSE_QUANTITY_INVALID", "库存数量不能为负数", 400)
    return result


def allocate_fefo(
    lots: list[dict[str, Any]],
    quantity: Decimal,
    *,
    specified_lot_id: int | None = None,
    override_reason: str | None = None,
) -> list[tuple[int, Decimal]]:
    valid = sorted(
        (lot for lot in lots if not lot.get("expired") and amount(lot.get("available")) > 0),
        key=lambda lot: (lot.get("expiry_date") or "9999-12-31", int(lot["id"])),
    )
    if specified_lot_id is not None:
        selected = next((lot for lot in valid if int(lot["id"]) == int(specified_lot_id)), None)
        if selected is None or amount(selected["available"]) < quantity:
            raise DomainError("WAREHOUSE_STOCK_INSUFFICIENT", "指定批次可用库存不足或已过期", 409)
        if valid and int(valid[0]["id"]) != int(specified_lot_id) and not str(override_reason or "").strip():
            raise DomainError("FEFO_OVERRIDE_REASON_REQUIRED", "未按近效期优先出库必须填写覆盖原因", 400)
        return [(int(selected["id"]), quantity)]
    remaining = quantity
    allocations: list[tuple[int, Decimal]] = []
    for lot in valid:
        used = min(remaining, amount(lot["available"]))
        if used:
            allocations.append((int(lot["id"]), used))
            remaining -= used
        if remaining == 0:
            return allocations
    raise DomainError("WAREHOUSE_STOCK_INSUFFICIENT", "可用库存不足，禁止形成负库存", 409)


def build_movements(
    resource: str,
    row: dict[str, Any],
    *,
    allocations: list[tuple[int, Decimal]] | None = None,
    book_quantity: Decimal | None = None,
) -> list[dict[str, Any]]:
    warehouse_id = int(row["warehouse_id"])
    quantity = amount(row.get("quantity"))
    lot_id = int(row.get("inventory_lot_id") or 0)
    if resource in {"receipts", "returns"}:
        return [{"warehouse_id": warehouse_id, "inventory_lot_id": lot_id, "quantity_delta": quantity}]
    if resource in {"issues", "scraps"}:
        return [{"warehouse_id": warehouse_id, "inventory_lot_id": item, "quantity_delta": -used} for item, used in allocations or []]
    if resource == "transfers":
        target = int(row["target_warehouse_id"])
        return [movement for item, used in allocations or [] for movement in (
            {"warehouse_id": warehouse_id, "inventory_lot_id": item, "quantity_delta": -used},
            {"warehouse_id": target, "inventory_lot_id": item, "quantity_delta": used},
        )]
    if resource == "stocktakes":
        return [{"warehouse_id": warehouse_id, "inventory_lot_id": lot_id, "quantity_delta": quantity - (book_quantity or Decimal("0"))}]
    return []


def movement_difference(
    desired: list[dict[str, Any]],
    original: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    totals: dict[tuple[int, int], Decimal] = {}
    for sign, movements in ((Decimal("1"), desired), (Decimal("-1"), original)):
        for movement in movements:
            key = (int(movement["warehouse_id"]), int(movement["inventory_lot_id"]))
            totals[key] = totals.get(key, Decimal("0")) + sign * Decimal(str(movement["quantity_delta"]))
    return [
        {"warehouse_id": warehouse_id, "inventory_lot_id": lot_id, "quantity_delta": quantity}
        for (warehouse_id, lot_id), quantity in totals.items() if quantity
    ]
