from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError


class MySqlReturnStore:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    @staticmethod
    def _table(kind: str) -> str:
        if kind not in {"purchase", "sales"}:
            raise DomainError("RETURN_KIND_INVALID", "退货类型无效", 400)
        return f"{kind}_returns"

    def list_returns(self, kind: str, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, **_: Any) -> dict[str, Any]:
        table = self._table(kind); page = max(1, int(page)); page_size = min(100, max(1, int(page_size)))
        clauses, values = [], []
        if user.get("organization_id"):
            clauses.append("r.organization_id=%s"); values.append(int(user["organization_id"]))
        if status: clauses.append("r.status=%s"); values.append(status)
        if search: clauses.append("(r.code LIKE %s OR r.name LIKE %s)"); values.extend([f"%{search}%", f"%{search}%"])
        where = " AND ".join(clauses) or "1=1"
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table} r WHERE {where}", tuple(values)); total = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(f"SELECT r.* FROM {table} r WHERE {where} ORDER BY r.updated_at DESC,r.id DESC LIMIT %s OFFSET %s", tuple(values + [page_size, (page - 1) * page_size]))
            items = list(cursor.fetchall())
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}

    def get_return(self, kind: str, record_id: int, *, user: dict[str, Any]) -> dict[str, Any] | None:
        table = self._table(kind)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            clause = " AND organization_id=%s" if user.get("organization_id") else ""
            params = (record_id, int(user["organization_id"])) if user.get("organization_id") else (record_id,)
            cursor.execute(f"SELECT * FROM {table} WHERE id=%s{clause}", params); return cursor.fetchone()

    def create_return(self, kind: str, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        table = self._table(kind)
        try: quantity = Decimal(str(payload.get("quantity"))); refund = Decimal(str(payload.get("refund_amount", 0)))
        except (InvalidOperation, TypeError) as exc: raise DomainError("RETURN_QUANTITY_INVALID", "退货数量或退款金额格式无效", 400) from exc
        if quantity <= 0 or refund < 0: raise DomainError("RETURN_QUANTITY_INVALID", "退货数量必须大于零，退款金额不能为负", 400)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            if kind == "purchase":
                cursor.execute("SELECT d.*,p.id AS payable_id,p.amount AS payable_amount FROM warehouse_documents d JOIN purchase_payables p ON p.source_receipt_id=d.id WHERE d.id=%s AND d.document_type='receipt' AND d.status='verified' FOR UPDATE", (payload.get("source_receipt_id"),))
                source = cursor.fetchone()
                required = ("source_receipt_id", "warehouse_id", "material_id", "inventory_lot_id")
                if source is None or any(int(source.get(k) or 0) != int(payload.get(k) or 0) for k in required[1:]): raise DomainError("RETURN_SOURCE_INVALID", "采购退货必须关联已核验入库单及其物料批次", 409)
                if user.get("organization_id") and int(source["organization_id"]) != int(user["organization_id"]): raise DomainError("DATA_SCOPE_FORBIDDEN", "无权操作其他企业退货", 403)
                cursor.execute("SELECT COALESCE(SUM(quantity),0) AS returned FROM purchase_returns WHERE source_receipt_id=%s AND status='verified'", (source["id"],))
                returned = Decimal(str((cursor.fetchone() or {}).get("returned", 0)))
                if quantity + returned > Decimal(str(source["quantity"])): raise DomainError("RETURN_EXCEEDS_SOURCE", "累计退货数量不能超过入库数量", 409)
                amount = quantity * Decimal(str(source["unit_cost"] or 0)); columns = ("organization_id,source_receipt_id,payable_id,warehouse_id,material_id,inventory_lot_id,code,name,quantity,amount,reason,created_by")
                values = (source["organization_id"], source["id"], source["payable_id"], source["warehouse_id"], source["material_id"], source["inventory_lot_id"], payload["code"], payload["name"], quantity, amount, payload["reason"], user_id)
            else:
                cursor.execute("SELECT d.*,r.id AS receivable_id,o.unit_price,o.organization_id FROM sales_deliveries d JOIN sales_receivables r ON r.source_delivery_id=d.id JOIN sales_orders o ON o.id=d.sales_order_id WHERE d.id=%s AND d.status='verified' FOR UPDATE", (payload.get("source_delivery_id"),)); source = cursor.fetchone()
                if source is None: raise DomainError("RETURN_SOURCE_INVALID", "销售退货必须关联已核验交付单", 409)
                if user.get("organization_id") and int(source["organization_id"]) != int(user["organization_id"]): raise DomainError("DATA_SCOPE_FORBIDDEN", "无权操作其他企业退货", 403)
                cursor.execute("SELECT COALESCE(SUM(quantity),0) AS returned FROM sales_returns WHERE source_delivery_id=%s AND status='verified'", (source["id"],))
                returned = Decimal(str((cursor.fetchone() or {}).get("returned", 0)))
                if quantity + returned > Decimal(str(source["quantity"])): raise DomainError("RETURN_EXCEEDS_SOURCE", "累计退货数量不能超过交付数量", 409)
                amount = quantity * Decimal(str(source["unit_price"] or 0))
                if refund > amount: raise DomainError("RETURN_REFUND_INVALID", "退款金额不能超过退货金额", 400)
                columns = "organization_id,source_delivery_id,receivable_id,code,name,quantity,amount,refund_amount,reason,created_by"
                values = (source["organization_id"], source["id"], source["receivable_id"], payload["code"], payload["name"], quantity, amount, refund, payload["reason"], user_id)
            cursor.execute(f"INSERT INTO {table} ({columns}) VALUES ({','.join(['%s'] * len(values))})", values)
            record_id = int(cursor.lastrowid); cursor.execute(f"SELECT * FROM {table} WHERE id=%s", (record_id,)); return cursor.fetchone() or {}

    def set_return_status(self, kind: str, record_id: int, status: str, *, expected_version: int, user: dict[str, Any], user_id: int, reason: str | None = None) -> dict[str, Any]:
        table = self._table(kind)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table} WHERE id=%s FOR UPDATE", (record_id,)); row = cursor.fetchone()
            if row is None: raise DomainError("RETURN_NOT_FOUND", "退货单不存在", 404)
            if int(row["row_version"]) != expected_version or row["status"] not in {"draft" if status == "submitted" else "submitted"}: raise DomainError("VERSION_CONFLICT", "退货状态或版本已变化", 409)
            if status == "verified":
                if kind == "purchase":
                    cursor.execute("SELECT COALESCE(SUM(quantity_delta),0) AS qty FROM inventory_ledger WHERE warehouse_id=%s AND material_id=%s AND inventory_lot_id=%s FOR UPDATE", (row["warehouse_id"], row["material_id"], row["inventory_lot_id"]))
                    if Decimal(str((cursor.fetchone() or {}).get("qty", 0))) < Decimal(str(row["quantity"])): raise DomainError("WAREHOUSE_STOCK_INSUFFICIENT", "库存不足，不能核验采购退货", 409)
                    cursor.execute("INSERT INTO inventory_ledger (organization_id,warehouse_id,material_id,inventory_lot_id,source_type,source_id,line_no,quantity_delta,unit_cost,posted_by) VALUES (%s,%s,%s,%s,'purchase_return',%s,1,%s,0,%s)", (row["organization_id"], row["warehouse_id"], row["material_id"], row["inventory_lot_id"], record_id, -Decimal(str(row["quantity"])), user_id))
                    cursor.execute("INSERT INTO purchase_payable_adjustments (organization_id,payable_id,purchase_return_id,amount_delta,reason,created_by) VALUES (%s,%s,%s,%s,%s,%s)", (row["organization_id"], row["payable_id"], record_id, -Decimal(str(row["amount"])), row["reason"], user_id))
                    cursor.execute("UPDATE purchase_payables SET status=CASE WHEN paid_amount >= amount + COALESCE((SELECT SUM(amount_delta) FROM purchase_payable_adjustments WHERE payable_id=%s),0) THEN 'settled' WHEN paid_amount > 0 THEN 'partial' ELSE 'unpaid' END WHERE id=%s", (row["payable_id"], row["payable_id"]))
                else:
                    cursor.execute("INSERT INTO sales_receivable_adjustments (organization_id,receivable_id,sales_return_id,amount_delta,reason,created_by) VALUES (%s,%s,%s,%s,%s,%s)", (row["organization_id"], row["receivable_id"], record_id, -Decimal(str(row["amount"])), row["reason"], user_id))
                    cursor.execute("UPDATE sales_receivables SET status=CASE WHEN received_amount > amount + COALESCE((SELECT SUM(amount_delta) FROM sales_receivable_adjustments WHERE receivable_id=%s),0) THEN 'overpaid' WHEN received_amount = amount + COALESCE((SELECT SUM(amount_delta) FROM sales_receivable_adjustments WHERE receivable_id=%s),0) THEN 'settled' ELSE 'partial' END WHERE id=%s", (row["receivable_id"], row["receivable_id"], row["receivable_id"]))
                cursor.execute(f"UPDATE {table} SET status='verified',verified_by=%s,verified_at=NOW(),row_version=row_version+1 WHERE id=%s AND row_version=%s", (user_id, record_id, expected_version))
            elif status == "submitted":
                cursor.execute(f"UPDATE {table} SET status='submitted',row_version=row_version+1 WHERE id=%s AND row_version=%s", (record_id, expected_version))
            else:
                cursor.execute(f"UPDATE {table} SET status='cancelled',row_version=row_version+1 WHERE id=%s AND row_version=%s", (record_id, expected_version))
            cursor.execute(f"SELECT * FROM {table} WHERE id=%s", (record_id,)); return cursor.fetchone() or {}

    def delete_return(self, kind: str, record_id: int, *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        table = self._table(kind)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table} WHERE id=%s AND status='draft' FOR UPDATE", (record_id,)); row = cursor.fetchone()
            if row is None: raise DomainError("DELETE_NOT_ALLOWED", "仅未提交的退货草稿可以删除", 409)
            cursor.execute(f"DELETE FROM {table} WHERE id=%s AND status='draft'", (record_id,))
            return row
