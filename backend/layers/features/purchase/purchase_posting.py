from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def post_purchase_receipt(cursor: Any, row: dict[str, Any]) -> None:
    order_id = row.get("purchase_order_id")
    if not order_id:
        return
    cursor.execute(
        "SELECT id,organization_id,supplier_id,material_id,warehouse_id,quantity,unit_price,due_date,status "
        "FROM purchase_orders WHERE id=%s FOR UPDATE",
        (order_id,),
    )
    order = cursor.fetchone()
    if order is None or order["status"] not in {"approved", "partially_received", "fully_received"}:
        raise DomainError("PURCHASE_ORDER_NOT_RECEIVABLE", "采购单不存在或当前状态不能办理到货", 409)
    if int(order["material_id"]) != int(row["material_id"]) or int(order["warehouse_id"]) != int(row["warehouse_id"]):
        raise DomainError("PURCHASE_RECEIPT_SCOPE_MISMATCH", "到货物料或收货仓与采购单不一致", 409)
    if Decimal(str(order["unit_price"])) != Decimal(str(row.get("unit_cost") or 0)):
        raise DomainError("PURCHASE_RECEIPT_PRICE_MISMATCH", "到货单价与已审批采购价不一致，请先走价格调整", 409)
    cursor.execute(
        "SELECT COALESCE(SUM(CASE WHEN d.correction_of_id IS NULL THEN d.quantity ELSE d.quantity-o.quantity END),0) AS received "
        "FROM warehouse_documents d LEFT JOIN warehouse_documents o ON o.id=d.correction_of_id "
        "WHERE d.purchase_order_id=%s AND d.document_type='receipt' AND d.status='verified'",
        (order_id,),
    )
    received = Decimal(str(cursor.fetchone()["received"]))
    ordered = Decimal(str(order["quantity"]))
    if received > ordered:
        raise DomainError("PURCHASE_RECEIPT_EXCEEDS_ORDER", "累计到货数量不能超过采购数量", 409)
    cursor.execute(
        "UPDATE purchase_orders SET status=%s,row_version=row_version+1 WHERE id=%s",
        ("fully_received" if received == ordered else "partially_received", order_id),
    )
    if row.get("correction_of_id"):
        parent_id = int(row["correction_of_id"])
        cursor.execute("SELECT id,correction_of_id,quantity FROM warehouse_documents WHERE id=%s", (parent_id,))
        parent = cursor.fetchone()
        if parent is None:
            raise DomainError("PURCHASE_RECEIPT_SOURCE_MISSING", "上次到货更正不存在", 409)
        root_id = parent_id
        while parent.get("correction_of_id"):
            root_id = int(parent["correction_of_id"])
            cursor.execute("SELECT id,correction_of_id,quantity FROM warehouse_documents WHERE id=%s", (root_id,))
            parent_root = cursor.fetchone()
            if parent_root is None:
                raise DomainError("PURCHASE_RECEIPT_SOURCE_MISSING", "原始到货记录不存在", 409)
            parent = {**parent, "correction_of_id": parent_root.get("correction_of_id")}
        cursor.execute(
            "SELECT p.id,p.amount,p.paid_amount FROM purchase_payables p WHERE p.source_receipt_id=%s FOR UPDATE",
            (root_id,),
        )
        payable = cursor.fetchone()
        if payable is None:
            raise DomainError("PURCHASE_PAYABLE_SOURCE_MISSING", "原到货应付不存在，不能核验更正", 409)
        amount_delta = (Decimal(str(row["quantity"])) - Decimal(str(parent["quantity"]))) * Decimal(str(order["unit_price"]))
        cursor.execute(
            "INSERT INTO purchase_payable_adjustments (organization_id,payable_id,source_receipt_id,amount_delta,reason,created_by) VALUES (%s,%s,%s,%s,%s,%s)",
            (order["organization_id"], payable["id"], row["id"], amount_delta, row.get("correction_reason") or "到货更正", row.get("verified_by") or row["created_by"]),
        )
        cursor.execute("SELECT COALESCE(SUM(amount_delta),0) AS adjustment_total FROM purchase_payable_adjustments WHERE payable_id=%s", (payable["id"],))
        effective = Decimal(str(payable["amount"])) + Decimal(str(cursor.fetchone()["adjustment_total"]))
        paid = Decimal(str(payable["paid_amount"]))
        status = "overpaid" if paid > effective else "settled" if paid == effective else "partial" if paid else "unpaid"
        cursor.execute("UPDATE purchase_payables SET status=%s WHERE id=%s", (status, payable["id"]))
    else:
        cursor.execute(
            "INSERT INTO purchase_payables (organization_id,purchase_order_id,source_receipt_id,supplier_id,idempotency_key,amount,due_date) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)",
            (
                order["organization_id"], order_id, row["id"], order["supplier_id"],
                f"purchase-receipt:{row['id']}", Decimal(str(row["quantity"])) * Decimal(str(row.get("unit_cost") or 0)),
                order["due_date"],
            ),
        )
    if row.get("inventory_lot_id"):
        cursor.execute(
            "UPDATE inventory_lots SET supplier_id=COALESCE(supplier_id,%s) WHERE id=%s",
            (order["supplier_id"], row["inventory_lot_id"]),
        )
