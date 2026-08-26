from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pymysql

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.revisions import build_revision, save_revision
from backend.layers.common.governance.work_item_notifications import notify_work_item_created
from backend.layers.features.purchase import purchase_payment_store as payments
from backend.layers.features.purchase import purchase_payment_reversal_store as reversals
from backend.layers.common.security.data_scope import require_active_scope, unrestricted


ORDER_FIELDS = {
    "code", "name", "supplier_id", "material_id", "warehouse_id", "quantity", "unit_price",
    "expected_delivery_date", "due_date", "note", "evidence_attachment_ids",
}


class MySqlPurchaseStore:
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.audit = AuditLogger()

    @staticmethod
    def _decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        result = dict(row); value = result.pop("evidence_attachment_ids_json", None)
        if isinstance(value, str):
            value = json.loads(value)
        if value is not None:
            result["evidence_attachment_ids"] = value
        return result

    @staticmethod
    def _scope(user: dict[str, Any], alias: str = "o") -> tuple[str, list[Any]]:
        scopes = require_active_scope(user)
        if unrestricted(user):
            return "", []
        areas = [int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")]
        if areas:
            return f"{alias}.area_id IN ({','.join(['%s'] * len(areas))})", areas
        if any(item.get("scope_type") == "personal" for item in scopes):
            return f"{alias}.created_by=%s", [int(user["id"])]
        return "1=0", []

    @staticmethod
    def _scoped(cursor: Any, payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        cursor.execute("SELECT organization_id,farm_id,area_id FROM warehouses WHERE id=%s AND status='active'", (result.get("warehouse_id"),)); warehouse = cursor.fetchone()
        if warehouse is None:
            raise DomainError("PURCHASE_WAREHOUSE_INVALID", "收货仓不存在或已停用", 400)
        result.update(warehouse)
        cursor.execute("SELECT organization_id FROM materials WHERE id=%s AND status='verified'", (result.get("material_id"),)); material = cursor.fetchone()
        cursor.execute("SELECT organization_id FROM business_partners WHERE id=%s AND partner_type='supplier' AND status='verified'", (result.get("supplier_id"),)); supplier = cursor.fetchone()
        if material is None or supplier is None or any(int(item["organization_id"]) != int(result["organization_id"]) for item in (material, supplier)):
            raise DomainError("PURCHASE_MASTER_DATA_INVALID", "供应商或物料不存在、未核验或不属于当前企业", 400)
        return result

    @staticmethod
    def _require_scope(user: dict[str, Any], row: dict[str, Any]) -> None:
        scopes = require_active_scope(user)
        if unrestricted(user):
            return
        areas = {int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")}
        if int(row.get("area_id") or 0) in areas:
            return
        if any(item.get("scope_type") == "personal" for item in scopes) and not row.get("area_id") and int(row.get("created_by") or 0) == int(user["id"]):
            return
        raise DomainError("DATA_SCOPE_FORBIDDEN", "无权写入授权范围之外的采购记录", 403)

    @staticmethod
    def _payload(payload: dict[str, Any]) -> dict[str, Any]:
        clean = {
            key: value for key, value in payload.items()
            if key in ORDER_FIELDS | {"organization_id", "farm_id", "area_id"} and value != ""
        }
        if "evidence_attachment_ids" in clean:
            clean["evidence_attachment_ids_json"] = json.dumps(clean.pop("evidence_attachment_ids"))
        if "quantity" in clean or "unit_price" in clean:
            clean["total_amount"] = Decimal(str(payload.get("quantity", 0))) * Decimal(str(payload.get("unit_price", 0)))
        return clean

    def _get(self, cursor: Any, order_id: int, *, lock: bool = False) -> dict[str, Any] | None:
        cursor.execute("SELECT * FROM purchase_orders WHERE id=%s" + (" FOR UPDATE" if lock else ""), (order_id,))
        return self._decode(cursor.fetchone())

    def get_order(self, order_id: int, *, user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            row = self._get(cursor, order_id)
            if row is not None and user is not None:
                self._require_scope(user, row)
            return row

    def list_orders(self, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, **_: Any) -> dict[str, Any]:
        clauses, values = ["1=1"], []
        scope, scoped = self._scope(user)
        if scope:
            clauses.append(scope); values.extend(scoped)
        if status:
            clauses.append("o.status=%s"); values.append(status)
        if search:
            clauses.append("(o.code LIKE %s OR o.name LIKE %s OR s.name LIKE %s OR m.name LIKE %s)"); values.extend([f"%{search}%"] * 4)
        where = " AND ".join(clauses); page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
        joins = " FROM purchase_orders o JOIN business_partners s ON s.id=o.supplier_id JOIN materials m ON m.id=o.material_id JOIN warehouses w ON w.id=o.warehouse_id"
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total{joins} WHERE {where}", tuple(values)); total = int(cursor.fetchone()["total"])
            cursor.execute(
                f"SELECT o.*,s.name AS supplier_name,m.name AS material_name,w.name AS warehouse_name,COALESCE((SELECT SUM(CASE WHEN d.correction_of_id IS NULL THEN d.quantity ELSE d.quantity-parent.quantity END) FROM warehouse_documents d LEFT JOIN warehouse_documents parent ON parent.id=d.correction_of_id WHERE d.purchase_order_id=o.id AND d.document_type='receipt' AND d.status='verified'),0) AS received_quantity,COALESCE((SELECT SUM(p.paid_amount) FROM purchase_payables p WHERE p.purchase_order_id=o.id),0) AS paid_amount{joins} WHERE {where} ORDER BY o.updated_at DESC,o.id DESC LIMIT %s OFFSET %s",
                tuple(values + [page_size, (page - 1) * page_size]),
            )
            items = [self._decode(row) or {} for row in cursor.fetchall()]
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}

    def create_order(self, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            scoped = self._scoped(cursor, payload); self._require_scope(user, scoped); clean = self._payload(scoped)
            clean.update(status="draft", row_version=1, created_by=user_id)
            cursor.execute(f"INSERT INTO purchase_orders ({','.join(clean)}) VALUES ({','.join(['%s'] * len(clean))})", tuple(clean.values()))
            order_id = int(cursor.lastrowid); row = self._get(cursor, order_id) or {}; self._audit(connection, user_id, "create", "order", order_id, after=row); return row

    def update_order(self, order_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, order_id, lock=True)
            if before is None:
                raise DomainError("PURCHASE_ORDER_NOT_FOUND", "采购单不存在", 404)
            scoped = self._scoped(cursor, {**before, **payload}); self._require_scope(user, scoped)
            effective = {**before, **payload}; clean = self._payload(payload)
            if "quantity" in payload or "unit_price" in payload:
                clean["total_amount"] = Decimal(str(effective["quantity"])) * Decimal(str(effective["unit_price"]))
            cursor.execute(f"UPDATE purchase_orders SET {','.join(f'{key}=%s' for key in clean)},updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status IN ('draft','submitted')", (*clean.values(), user_id, order_id, expected_version))
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "数据已变化，请刷新后重试", 409)
            after = self._get(cursor, order_id) or {}
            if before["status"] == "submitted":
                save_revision(connection, build_revision(entity_type="purchase:order", entity_id=order_id, current_version=expected_version, before=before, after=after, actor_user_id=user_id))
                cursor.execute("UPDATE work_items SET target_version=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (after["row_version"], f"purchase:order:{order_id}:approve"))
            self._audit(connection, user_id, "update", "order", order_id, before=before, after=after); return after

    def set_order_status(self, order_id: int, status: str, *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, order_id, lock=True)
            if before is None:
                raise DomainError("PURCHASE_ORDER_NOT_FOUND", "采购单不存在", 404)
            self._require_scope(user, before)
            extra, params = "", [status, user_id]
            if status == "approved":
                extra = ",approved_by=%s,approved_at=CURRENT_TIMESTAMP"; params.append(user_id)
            params.extend([order_id, expected_version])
            cursor.execute(f"UPDATE purchase_orders SET status=%s,updated_by=%s{extra},row_version=row_version+1 WHERE id=%s AND row_version=%s", tuple(params))
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "数据已变化，请刷新后重试", 409)
            after = self._get(cursor, order_id) or {}; source_key = f"purchase:order:{order_id}:approve"
            if status == "submitted":
                cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'purchase','approve','purchase:order',%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version)", (after["organization_id"], order_id, f"order:{order_id}", source_key, f"审批采购单：{after['name']}", after["row_version"]))
                notify_work_item_created(
                    connection,
                    organization_id=after["organization_id"],
                    area_id=after.get("area_id"),
                    module_code="purchase",
                    action_code="approve",
                    object_type="purchase:order",
                    object_id=order_id,
                    object_ref=f"order:{order_id}",
                    source_key=source_key,
                    title=f"审批采购单：{after['name']}",
                    permission_codes=["purchase.verify"],
                )
            else:
                cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=CURRENT_TIMESTAMP,completion_note='采购审批完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, source_key))
            self._audit(connection, user_id, status, "order", order_id, before=before, after=after); return after

    def cancel_order(self, order_id: int, *, expected_version: int, user: dict[str, Any], user_id: int, reason: str) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, order_id, lock=True)
            if before is None:
                raise DomainError("PURCHASE_ORDER_NOT_FOUND", "采购单不存在", 404)
            self._require_scope(user, before)
            cursor.execute("SELECT COUNT(*) AS total FROM warehouse_documents WHERE purchase_order_id=%s AND status='verified'", (order_id,))
            if int(cursor.fetchone()["total"]):
                raise DomainError("PURCHASE_ORDER_HAS_RECEIPTS", "采购单已经到货，不能取消，请办理退货或冲销", 409)
            cursor.execute("UPDATE purchase_orders SET status='cancelled',cancellation_reason=%s,cancelled_by=%s,cancelled_at=CURRENT_TIMESTAMP,updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status IN ('submitted','approved')", (reason, user_id, user_id, order_id, expected_version))
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "采购单状态或版本已变化", 409)
            after = self._get(cursor, order_id) or {}; cursor.execute("UPDATE work_items SET status='cancelled',cancelled_by=%s,cancelled_at=CURRENT_TIMESTAMP,cancel_reason=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, reason, f"purchase:order:{order_id}:approve"))
            self._audit(connection, user_id, "cancel", "order", order_id, before=before, after=after); return after

    def delete_order_draft(self, order_id: int, *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, order_id, lock=True)
            if before is None:
                raise DomainError("PURCHASE_ORDER_NOT_FOUND", "采购单不存在", 404)
            self._require_scope(user, before)
            try:
                cursor.execute("DELETE FROM purchase_orders WHERE id=%s AND status='draft'", (order_id,))
            except pymysql.IntegrityError as exc:
                raise DomainError("DELETE_NOT_ALLOWED", "已有业务引用的采购草稿不能删除", 409) from exc
            if cursor.rowcount != 1:
                raise DomainError("DELETE_NOT_ALLOWED", "仅无引用的采购草稿可以删除", 409)
            self._audit(connection, user_id, "delete_draft", "order", order_id, before=before); return before or {}

    def list_payables(self, **query: Any) -> dict[str, Any]: return payments.list_payables(self, **query)
    def list_payments(self, **query: Any) -> dict[str, Any]: return payments.list_payments(self, **query)
    def get_payment(self, payment_id: int, **context: Any) -> dict[str, Any] | None: return payments.get_payment(self, payment_id, **context)
    def create_payment(self, payload: dict[str, Any], **context: Any) -> dict[str, Any]: return payments.create_payment(self, payload, **context)
    def update_payment(self, payment_id: int, payload: dict[str, Any], **context: Any) -> dict[str, Any]: return payments.update_payment(self, payment_id, payload, **context)
    def set_payment_status(self, payment_id: int, status: str, **context: Any) -> dict[str, Any]: return payments.set_payment_status(self, payment_id, status, **context)
    def cancel_payment(self, payment_id: int, **context: Any) -> dict[str, Any]: return payments.cancel_payment(self, payment_id, **context)
    def delete_payment_draft(self, payment_id: int, **context: Any) -> dict[str, Any]: return payments.delete_payment_draft(self, payment_id, **context)
    def reverse_payment(self, payment_id: int, **context: Any) -> dict[str, Any]: return reversals.reverse_payment(self, payment_id, **context)

    def _audit(self, connection: Any, user_id: int, action: str, resource: str, record_id: int, *, before: Any = None, after: Any = None) -> None:
        self.audit.write(connection, user_id=user_id, action=f"{action}_purchase", object_type=f"purchase:{resource}", object_id=record_id, object_ref=f"{resource}:{record_id}", result="success", ip_address=None, module_code="purchase", before=before, after=after)
