from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def _root_and_parent(cursor: Any, correction_of_id: int) -> tuple[int, dict[str, Any]]:
    cursor.execute("SELECT id,correction_of_id,quantity FROM sales_deliveries WHERE id=%s", (correction_of_id,))
    parent = cursor.fetchone()
    if parent is None:
        raise DomainError("SALES_DELIVERY_SOURCE_MISSING", "上次交付更正不存在", 409)
    root_id, cursor_id = int(parent["id"]), parent.get("correction_of_id")
    while cursor_id:
        root_id = int(cursor_id)
        cursor.execute("SELECT correction_of_id FROM sales_deliveries WHERE id=%s", (root_id,))
        root = cursor.fetchone()
        if root is None:
            raise DomainError("SALES_DELIVERY_SOURCE_MISSING", "原始交付记录不存在", 409)
        cursor_id = root.get("correction_of_id")
    return root_id, parent


def _update_order(cursor: Any, order_id: int) -> None:
    cursor.execute(
        "SELECT o.quantity,COALESCE(SUM(CASE WHEN d.correction_of_id IS NULL THEN d.quantity ELSE d.quantity-p.quantity END),0) AS delivered "
        "FROM sales_orders o LEFT JOIN sales_deliveries d ON d.sales_order_id=o.id AND d.status='verified' "
        "LEFT JOIN sales_deliveries p ON p.id=d.correction_of_id WHERE o.id=%s GROUP BY o.id,o.quantity",
        (order_id,),
    )
    totals = cursor.fetchone()
    if totals is None:
        raise DomainError("SALES_ORDER_NOT_FOUND", "销售单不存在", 404)
    delivered, ordered = Decimal(str(totals["delivered"])), Decimal(str(totals["quantity"]))
    if delivered < 0 or delivered > ordered:
        raise DomainError("SALES_DELIVERY_EXCEEDS_ORDER", "有效交付数量超过销售数量", 409)
    status = "fully_delivered" if delivered == ordered else "partially_delivered" if delivered else "approved"
    cursor.execute("UPDATE sales_orders SET status=%s,row_version=row_version+1 WHERE id=%s", (status, order_id))


def post_delivery(cursor: Any, row: dict[str, Any], order: dict[str, Any]) -> None:
    unit_price = Decimal(str(order["unit_price"]))
    if row.get("correction_of_id"):
        root_id, parent = _root_and_parent(cursor, int(row["correction_of_id"]))
        cursor.execute("SELECT id,amount,received_amount FROM sales_receivables WHERE source_delivery_id=%s FOR UPDATE", (root_id,))
        receivable = cursor.fetchone()
        if receivable is None:
            raise DomainError("SALES_RECEIVABLE_SOURCE_MISSING", "原交付应收不存在，不能核验更正", 409)
        delta = (Decimal(str(row["quantity"])) - Decimal(str(parent["quantity"]))) * unit_price
        cursor.execute(
            "INSERT INTO sales_receivable_adjustments (organization_id,receivable_id,source_delivery_id,amount_delta,reason,created_by) VALUES (%s,%s,%s,%s,%s,%s)",
            (order["organization_id"], receivable["id"], row["id"], delta, row.get("correction_reason") or "交付更正", row.get("verified_by") or row["created_by"]),
        )
        cursor.execute("SELECT COALESCE(SUM(amount_delta),0) AS total FROM sales_receivable_adjustments WHERE receivable_id=%s", (receivable["id"],))
        effective = Decimal(str(receivable["amount"])) + Decimal(str(cursor.fetchone()["total"]))
        received = Decimal(str(receivable["received_amount"]))
        status = "overpaid" if received > effective else "settled" if received == effective else "partial" if received else "unpaid"
        cursor.execute("UPDATE sales_receivables SET status=%s WHERE id=%s", (status, receivable["id"]))
    else:
        amount = Decimal(str(row["quantity"])) * unit_price
        cursor.execute(
            "INSERT INTO sales_receivables (organization_id,sales_order_id,source_delivery_id,customer_id,idempotency_key,amount,due_date) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (order["organization_id"], order["id"], row["id"], order["customer_id"], f"sales-delivery:{row['id']}", amount, order["due_date"]),
        )
    _update_order(cursor, int(order["id"]))
