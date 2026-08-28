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
from backend.layers.common.files.evidence import validate_bound_evidence
from backend.layers.common.db.repositories.cost_enterprise_repository import require_unlocked
from backend.layers.features.sales import sales_receipt_reversal_store as reversals
from backend.layers.features.sales import sales_receipt_store as receipts
from backend.layers.features.sales.sales_posting import post_delivery
from backend.layers.features.sales.sales_source_control import harvest_root, require_order_evidence
from backend.layers.common.security.data_scope import require_active_scope, row_in_scope, scope_predicate, unrestricted
from backend.layers.features.returns.return_store import MySqlReturnStore


ORDER_FIELDS = {"code", "name", "customer_id", "pond_id", "batch_id", "species", "quantity", "unit", "unit_price", "sold_at", "due_date", "note", "evidence_attachment_ids"}
DELIVERY_FIELDS = {"code", "name", "sales_order_id", "harvest_document_id", "quantity", "delivered_at", "transport_info", "acceptance_note", "evidence_attachment_ids", "correction_reason"}

def _sort_clause(sort_by: str | None, sort_dir: str | None, allowed: dict[str, str], default: str, tie: str) -> str:
    column = allowed.get(str(sort_by or ""), default)
    direction = "ASC" if str(sort_dir or "").lower() == "asc" else "DESC"
    return f"{column} {direction},{tie} DESC"


class MySqlSalesStore:
    def __init__(self, settings: Any) -> None:
        self.settings = settings; self.audit = AuditLogger()
        self.returns = MySqlReturnStore(settings)

    @staticmethod
    def _decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row: return None
        result = dict(row); value = result.pop("evidence_attachment_ids_json", None)
        if isinstance(value, str): value = json.loads(value)
        if value is not None: result["evidence_attachment_ids"] = value
        return result

    @staticmethod
    def _scope(user: dict[str, Any], alias: str = "o") -> tuple[str, list[Any]]:
        return scope_predicate(user, alias)

    @staticmethod
    def _require_scope(user: dict[str, Any], row: dict[str, Any]) -> None:
        if row_in_scope(user, row): return
        raise DomainError("DATA_SCOPE_FORBIDDEN", "无权写入授权范围之外的销售记录", 403)

    @staticmethod
    def _scoped(cursor: Any, payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        cursor.execute("SELECT organization_id,farm_id,area_id FROM ponds WHERE id=%s AND status='verified'", (result.get("pond_id"),)); pond = cursor.fetchone()
        if pond is None: raise DomainError("SALES_POND_INVALID", "销售塘口不存在或未核验", 400)
        result.update(pond)
        cursor.execute("SELECT organization_id,pond_id,species,status FROM production_batches WHERE id=%s", (result.get("batch_id"),)); batch = cursor.fetchone()
        cursor.execute("SELECT organization_id FROM business_partners WHERE id=%s AND partner_type='customer' AND status='verified'", (result.get("customer_id"),)); customer = cursor.fetchone()
        if batch is None or customer is None or batch["status"] != "verified" or int(batch["pond_id"]) != int(result["pond_id"]) or any(int(item["organization_id"]) != int(result["organization_id"]) for item in (batch, customer)):
            raise DomainError("SALES_MASTER_DATA_INVALID", "客户、塘口或养殖批次无效或不属于同一企业", 400)
        if str(batch["species"]) != str(result.get("species")): raise DomainError("SALES_SPECIES_MISMATCH", "销售品种与养殖批次不一致", 400)
        return result

    @staticmethod
    def _payload(payload: dict[str, Any], fields: set[str]) -> dict[str, Any]:
        clean = {key: value for key, value in payload.items() if key in fields | {"organization_id", "farm_id", "area_id"} and value != ""}
        if "evidence_attachment_ids" in clean: clean["evidence_attachment_ids_json"] = json.dumps(clean.pop("evidence_attachment_ids"))
        return clean

    def _order(self, cursor: Any, record_id: int, *, lock: bool = False) -> dict[str, Any] | None:
        cursor.execute("SELECT * FROM sales_orders WHERE id=%s" + (" FOR UPDATE" if lock else ""), (record_id,)); return self._decode(cursor.fetchone())

    def get_order(self, record_id: int, *, user: dict[str, Any]) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            row = self._order(cursor, record_id)
            if row: self._require_scope(user, row)
            return row

    def list_orders(self, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, sort_by: str | None = None, sort_dir: str | None = None, **_: Any) -> dict[str, Any]:
        clauses, values = ["1=1"], []; scope, scoped = self._scope(user)
        if scope: clauses.append(scope); values.extend(scoped)
        if status: clauses.append("o.status=%s"); values.append(status)
        if search: clauses.append("(o.code LIKE %s OR o.name LIKE %s OR c.name LIKE %s OR p.name LIKE %s)"); values.extend([f"%{search}%"] * 4)
        where = " AND ".join(clauses); page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
        joins = " FROM sales_orders o JOIN business_partners c ON c.id=o.customer_id JOIN ponds p ON p.id=o.pond_id JOIN production_batches b ON b.id=o.batch_id"
        delivered = "COALESCE((SELECT SUM(CASE WHEN d.correction_of_id IS NULL THEN d.quantity ELSE d.quantity-parent.quantity END) FROM sales_deliveries d LEFT JOIN sales_deliveries parent ON parent.id=d.correction_of_id WHERE d.sales_order_id=o.id AND d.status='verified'),0)"
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total{joins} WHERE {where}", tuple(values)); total = int(cursor.fetchone()["total"])
            cursor.execute(f"SELECT o.*,c.name AS customer_name,p.name AS pond_name,b.code AS batch_code,{delivered} AS delivered_quantity,COALESCE((SELECT SUM(r.amount+COALESCE((SELECT SUM(a.amount_delta) FROM sales_receivable_adjustments a WHERE a.receivable_id=r.id),0)) FROM sales_receivables r WHERE r.sales_order_id=o.id),0) AS receivable_amount,COALESCE((SELECT SUM(r.received_amount) FROM sales_receivables r WHERE r.sales_order_id=o.id),0) AS received_amount{joins} WHERE {where} ORDER BY {_sort_clause(sort_by, sort_dir, {'code':'o.code','name':'o.name','customer_name':'c.name','quantity':'o.quantity','total_amount':'o.total_amount','status':'o.status','updated_at':'o.updated_at'}, 'o.updated_at', 'o.id')} LIMIT %s OFFSET %s", tuple(values + [page_size, (page - 1) * page_size]))
            items = [self._decode(row) or {} for row in cursor.fetchall()]
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}

    def create_order(self, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            scoped = self._scoped(cursor, payload); self._require_scope(user, scoped); clean = self._payload(scoped, ORDER_FIELDS)
            clean["total_amount"] = Decimal(str(clean["quantity"])) * Decimal(str(clean["unit_price"])); clean.update(status="draft", row_version=1, created_by=user_id)
            cursor.execute(f"INSERT INTO sales_orders ({','.join(clean)}) VALUES ({','.join(['%s'] * len(clean))})", tuple(clean.values()))
            record_id = int(cursor.lastrowid); row = self._order(cursor, record_id) or {}; require_order_evidence(cursor, row, list(payload.get("evidence_attachment_ids") or [])); self._audit(connection, user_id, "create", "order", record_id, after=row); return row

    def update_order(self, record_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._order(cursor, record_id, lock=True)
            if before is None: raise DomainError("SALES_ORDER_NOT_FOUND", "销售单不存在", 404)
            scoped = self._scoped(cursor, {**before, **payload}); self._require_scope(user, scoped); clean = self._payload(payload, ORDER_FIELDS)
            if not clean: raise DomainError("SALES_NO_CHANGES", "没有可保存的修改", 400)
            require_order_evidence(cursor, before, list(payload.get("evidence_attachment_ids") or []))
            effective = {**before, **clean}; clean["total_amount"] = Decimal(str(effective["quantity"])) * Decimal(str(effective["unit_price"]))
            cursor.execute(f"UPDATE sales_orders SET {','.join(f'{key}=%s' for key in clean)},updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status IN ('draft','submitted')", (*clean.values(), user_id, record_id, expected_version))
            if cursor.rowcount != 1: raise DomainError("VERSION_CONFLICT", "数据已变化，请刷新后重试", 409)
            after = self._order(cursor, record_id) or {}
            if before["status"] == "submitted":
                save_revision(connection, build_revision(entity_type="sales:order", entity_id=record_id, current_version=expected_version, before=before, after=after, actor_user_id=user_id))
                cursor.execute("UPDATE work_items SET target_version=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (after["row_version"], f"sales:order:{record_id}:approve"))
            self._audit(connection, user_id, "update", "order", record_id, before=before, after=after); return after

    def set_order_status(self, record_id: int, status: str, *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._order(cursor, record_id, lock=True)
            if before is None: raise DomainError("SALES_ORDER_NOT_FOUND", "销售单不存在", 404)
            self._require_scope(user, before); extra, params = "", [status, user_id]
            if status == "approved":
                self._scoped(cursor, before)
                require_order_evidence(cursor, before, list(before.get("evidence_attachment_ids") or []))
            if status == "approved": extra = ",approved_by=%s,approved_at=CURRENT_TIMESTAMP"; params.append(user_id)
            params.extend([record_id, expected_version]); cursor.execute(f"UPDATE sales_orders SET status=%s,updated_by=%s{extra},row_version=row_version+1 WHERE id=%s AND row_version=%s", tuple(params))
            if cursor.rowcount != 1: raise DomainError("VERSION_CONFLICT", "数据已变化，请刷新后重试", 409)
            after = self._order(cursor, record_id) or {}; key = f"sales:order:{record_id}:approve"
            if status == "submitted":
                cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'sales','approve','sales:order',%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version)", (after["organization_id"], record_id, f"order:{record_id}", key, f"审批销售单：{after['name']}", after["row_version"]))
                notify_work_item_created(connection, organization_id=after["organization_id"], area_id=after.get("area_id"), module_code="sales", action_code="approve", object_type="sales:order", object_id=record_id, object_ref=f"order:{record_id}", source_key=key, title=f"审批销售单：{after['name']}", permission_codes=["sales.verify"])
            else: cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=CURRENT_TIMESTAMP,completion_note='销售审批完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, key))
            self._audit(connection, user_id, status, "order", record_id, before=before, after=after); return after

    def cancel_order(self, record_id: int, *, expected_version: int, user: dict[str, Any], user_id: int, reason: str) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._order(cursor, record_id, lock=True)
            if before is None: raise DomainError("SALES_ORDER_NOT_FOUND", "销售单不存在", 404)
            self._require_scope(user, before); cursor.execute("SELECT COUNT(*) AS total FROM sales_deliveries WHERE sales_order_id=%s AND status='verified'", (record_id,))
            if int(cursor.fetchone()["total"]): raise DomainError("SALES_ORDER_HAS_DELIVERIES", "销售单已有交付，不能取消，请办理退货或冲销", 409)
            cursor.execute("UPDATE sales_orders SET status='cancelled',cancellation_reason=%s,cancelled_by=%s,cancelled_at=NOW(),updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status IN ('submitted','approved')", (reason, user_id, user_id, record_id, expected_version))
            if cursor.rowcount != 1: raise DomainError("VERSION_CONFLICT", "销售单状态或版本已变化", 409)
            after = self._order(cursor, record_id) or {}; cursor.execute("UPDATE work_items SET status='cancelled',cancelled_by=%s,cancelled_at=NOW(),cancel_reason=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, reason, f"sales:order:{record_id}:approve"))
            self._audit(connection, user_id, "cancel", "order", record_id, before=before, after=after); return after

    def delete_order_draft(self, record_id: int, *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._order(cursor, record_id, lock=True)
            if before is None: raise DomainError("SALES_ORDER_NOT_FOUND", "销售单不存在", 404)
            self._require_scope(user, before)
            try: cursor.execute("DELETE FROM sales_orders WHERE id=%s AND status='draft'", (record_id,))
            except pymysql.IntegrityError as exc: raise DomainError("DELETE_NOT_ALLOWED", "已有业务引用的销售草稿不能删除", 409) from exc
            if cursor.rowcount != 1: raise DomainError("DELETE_NOT_ALLOWED", "仅无引用销售草稿可以删除", 409)
            self._audit(connection, user_id, "delete_draft", "order", record_id, before=before); return before

    def _delivery(self, cursor: Any, record_id: int, *, lock: bool = False) -> dict[str, Any] | None:
        cursor.execute("SELECT d.*,o.area_id FROM sales_deliveries d JOIN sales_orders o ON o.id=d.sales_order_id WHERE d.id=%s" + (" FOR UPDATE" if lock else ""), (record_id,)); return self._decode(cursor.fetchone())

    def _source(self, cursor: Any, order: dict[str, Any], row: dict[str, Any]) -> int:
        return harvest_root(cursor, order, row)

    def get_delivery(self, record_id: int, *, user: dict[str, Any]) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            row = self._delivery(cursor, record_id)
            if row: self._require_scope(user, row)
            return row

    def list_deliveries(self, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, sort_by: str | None = None, sort_dir: str | None = None, **_: Any) -> dict[str, Any]:
        clauses, values = ["1=1"], []; scope, scoped = self._scope(user, "o")
        if scope: clauses.append(scope); values.extend(scoped)
        if status: clauses.append("d.status=%s"); values.append(status)
        if search: clauses.append("(d.code LIKE %s OR d.name LIKE %s OR o.code LIKE %s OR c.name LIKE %s)"); values.extend([f"%{search}%"] * 4)
        where = " AND ".join(clauses); page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
        joins = " FROM sales_deliveries d JOIN sales_orders o ON o.id=d.sales_order_id JOIN business_partners c ON c.id=o.customer_id"
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total{joins} WHERE {where}", tuple(values)); total = int(cursor.fetchone()["total"])
            cursor.execute(f"SELECT d.*,o.code AS order_code,o.area_id,c.name AS customer_name,(SELECT id FROM sales_deliveries x WHERE x.correction_of_id=d.id LIMIT 1) AS correction_id{joins} WHERE {where} ORDER BY {_sort_clause(sort_by, sort_dir, {'code':'d.code','name':'d.name','customer_name':'c.name','quantity':'d.quantity','delivered_at':'d.delivered_at','status':'d.status','updated_at':'d.updated_at'}, 'd.updated_at', 'd.id')} LIMIT %s OFFSET %s", tuple(values + [page_size, (page - 1) * page_size])); items = [self._decode(row) or {} for row in cursor.fetchall()]
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}

    def create_delivery(self, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            order = self._order(cursor, int(payload["sales_order_id"]), lock=True)
            if order is None or order["status"] not in {"approved", "partially_delivered"}: raise DomainError("SALES_ORDER_NOT_DELIVERABLE", "销售单未审批或已完成交付", 409)
            self._require_scope(user, order); root_id = self._source(cursor, order, payload); clean = self._payload(payload, DELIVERY_FIELDS); clean.update(organization_id=order["organization_id"], harvest_root_id=root_id, status="draft", row_version=1, created_by=user_id)
            try: cursor.execute(f"INSERT INTO sales_deliveries ({','.join(clean)}) VALUES ({','.join(['%s'] * len(clean))})", tuple(clean.values()))
            except pymysql.IntegrityError as exc: raise DomainError("SALES_DELIVERY_CONFLICT", "交付单号或业务字段与现有记录冲突", 409) from exc
            record_id = int(cursor.lastrowid)
            try:
                cursor.execute("INSERT INTO sales_delivery_harvest_claims (harvest_root_id,sales_delivery_id) VALUES (%s,%s)", (root_id, record_id))
            except pymysql.IntegrityError as exc:
                raise DomainError("SALES_HARVEST_ALREADY_DELIVERED", "该出塘事实已被交付单占用", 409) from exc
            row = self._delivery(cursor, record_id) or {}; self._audit(connection, user_id, "create", "delivery", record_id, after=row); return row

    def update_delivery(self, record_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._delivery(cursor, record_id, lock=True)
            if before is None: raise DomainError("SALES_DELIVERY_NOT_FOUND", "交付单不存在", 404)
            self._require_scope(user, before); order = self._order(cursor, int(before["sales_order_id"])) or {}; root_id = self._source(cursor, order, {**before, **payload}); clean = self._payload(payload, DELIVERY_FIELDS - {"sales_order_id", "correction_reason"})
            if not clean: raise DomainError("SALES_NO_CHANGES", "没有可保存的修改", 400)
            clean["harvest_root_id"] = root_id
            if before.get("correction_of_id") and root_id != int(before["harvest_root_id"]): raise DomainError("CORRECTION_HARVEST_MISMATCH", "交付更正必须使用同一出塘更正链", 409)
            try: cursor.execute(f"UPDATE sales_deliveries SET {','.join(f'{key}=%s' for key in clean)},updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status IN ('draft','submitted')", (*clean.values(), user_id, record_id, expected_version))
            except pymysql.IntegrityError as exc: raise DomainError("SALES_DELIVERY_CONFLICT", "交付单号或业务字段与现有记录冲突", 409) from exc
            if cursor.rowcount != 1: raise DomainError("VERSION_CONFLICT", "交付数据已变化，请刷新后重试", 409)
            if not before.get("correction_of_id"):
                try:
                    cursor.execute("UPDATE sales_delivery_harvest_claims SET harvest_root_id=%s WHERE sales_delivery_id=%s", (root_id, record_id))
                except pymysql.IntegrityError as exc: raise DomainError("SALES_HARVEST_ALREADY_DELIVERED", "该出塘事实已被交付单占用", 409) from exc
                cursor.execute("SELECT harvest_root_id FROM sales_delivery_harvest_claims WHERE sales_delivery_id=%s", (record_id,)); claim = cursor.fetchone()
                if claim is None or int(claim["harvest_root_id"]) != root_id: raise DomainError("SALES_HARVEST_CLAIM_INVALID", "交付出塘占用记录异常", 409)
            after = self._delivery(cursor, record_id) or {}
            if before["status"] == "submitted":
                save_revision(connection, build_revision(entity_type="sales:delivery", entity_id=record_id, current_version=expected_version, before=before, after=after, actor_user_id=user_id))
                cursor.execute("UPDATE work_items SET target_version=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (after["row_version"], f"sales:delivery:{record_id}:verify"))
            self._audit(connection, user_id, "update", "delivery", record_id, before=before, after=after); return after

    def create_delivery_correction(self, record_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._delivery(cursor, record_id, lock=True)
            if before is None: raise DomainError("SALES_DELIVERY_NOT_FOUND", "交付单不存在", 404)
            self._require_scope(user, before)
            if before["status"] != "verified" or int(before["row_version"]) != expected_version: raise DomainError("VERSION_CONFLICT", "交付状态或版本已变化", 409)
            copied = {key: before[key] for key in DELIVERY_FIELDS if key != "evidence_attachment_ids" and before.get(key) is not None}
            clean = self._payload({**copied, **payload}, DELIVERY_FIELDS); clean.update(organization_id=before["organization_id"], sales_order_id=before["sales_order_id"], correction_of_id=record_id, status="draft", row_version=1, created_by=user_id)
            order = self._order(cursor, int(before["sales_order_id"])) or {}; root_id = self._source(cursor, order, clean)
            if root_id != int(before["harvest_root_id"]): raise DomainError("CORRECTION_HARVEST_MISMATCH", "交付更正必须使用同一出塘更正链", 409)
            clean["harvest_root_id"] = root_id
            try: cursor.execute(f"INSERT INTO sales_deliveries ({','.join(clean)}) VALUES ({','.join(['%s'] * len(clean))})", tuple(clean.values()))
            except pymysql.IntegrityError as exc: raise DomainError("CORRECTION_EXISTS", "该交付已有更正或出塘单已被引用", 409) from exc
            correction_id = int(cursor.lastrowid); row = self._delivery(cursor, correction_id) or {}; self._audit(connection, user_id, "create_correction", "delivery", correction_id, before=before, after=row); return row

    def set_delivery_status(self, record_id: int, status: str, *, expected_version: int, user: dict[str, Any], user_id: int, evidence_attachment_ids: list[int] | None = None) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._delivery(cursor, record_id, lock=True)
            if before is None: raise DomainError("SALES_DELIVERY_NOT_FOUND", "交付单不存在", 404)
            self._require_scope(user, before); order = self._order(cursor, int(before["sales_order_id"]), lock=True) or {}
            evidence = validate_bound_evidence(cursor, organization_id=int(before["organization_id"]), entity_type="sales:delivery", entity_id=record_id, evidence_ids=evidence_attachment_ids or before.get("evidence_attachment_ids"))
            if status == "verified":
                if order.get("status") not in {"approved", "partially_delivered"}:
                    raise DomainError("SALES_ORDER_NOT_DELIVERABLE", "销售单已取消或完成交付，不能核验交付", 409)
                require_unlocked(cursor, {**order, **before}, "delivered_at")
                self._source(cursor, order, before)
            extra, params = "", [status, user_id]
            if evidence: extra += ",evidence_attachment_ids_json=%s"; params.append(json.dumps(evidence))
            if status == "verified": extra += ",verified_by=%s,verified_at=NOW()"; params.append(user_id)
            params.extend([record_id, expected_version]); cursor.execute(f"UPDATE sales_deliveries SET status=%s,updated_by=%s{extra},row_version=row_version+1 WHERE id=%s AND row_version=%s", tuple(params))
            if cursor.rowcount != 1: raise DomainError("VERSION_CONFLICT", "交付状态或版本已变化", 409)
            after = self._delivery(cursor, record_id) or {}; key = f"sales:delivery:{record_id}:verify"
            if status == "submitted":
                cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'sales','verify','sales:delivery',%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version)", (after["organization_id"], record_id, f"delivery:{record_id}", key, f"核验销售交付：{after['name']}", after["row_version"]))
                notify_work_item_created(connection, organization_id=after["organization_id"], area_id=after.get("area_id"), module_code="sales", action_code="verify", object_type="sales:delivery", object_id=record_id, object_ref=f"delivery:{record_id}", source_key=key, title=f"核验销售交付：{after['name']}", permission_codes=["sales.verify"])
            else:
                post_delivery(cursor, after, order); cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=NOW(),completion_note='交付核验完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, key))
            self._audit(connection, user_id, status, "delivery", record_id, before=before, after=after); return after

    def cancel_delivery(self, record_id: int, *, expected_version: int, user: dict[str, Any], user_id: int, reason: str) -> dict[str, Any]: return self._cancel_delivery(record_id, expected_version, user, user_id, reason)

    def _cancel_delivery(self, record_id: int, expected_version: int, user: dict[str, Any], user_id: int, reason: str) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._delivery(cursor, record_id, lock=True)
            if before is None: raise DomainError("SALES_DELIVERY_NOT_FOUND", "交付单不存在", 404)
            self._require_scope(user, before); cursor.execute("UPDATE sales_deliveries SET status='cancelled',cancellation_reason=%s,cancelled_by=%s,cancelled_at=NOW(),updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status='submitted'", (reason, user_id, user_id, record_id, expected_version))
            if cursor.rowcount != 1: raise DomainError("VERSION_CONFLICT", "交付状态或版本已变化", 409)
            after = self._delivery(cursor, record_id) or {}; cursor.execute("UPDATE work_items SET status='cancelled',cancelled_by=%s,cancelled_at=NOW(),cancel_reason=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, reason, f"sales:delivery:{record_id}:verify")); self._audit(connection, user_id, "cancel", "delivery", record_id, before=before, after=after); return after

    def delete_delivery_draft(self, record_id: int, *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._delivery(cursor, record_id, lock=True)
            if before is None: raise DomainError("SALES_DELIVERY_NOT_FOUND", "交付单不存在", 404)
            self._require_scope(user, before)
            try: cursor.execute("DELETE FROM sales_deliveries WHERE id=%s AND status='draft'", (record_id,))
            except pymysql.IntegrityError as exc: raise DomainError("DELETE_NOT_ALLOWED", "已有业务引用的交付草稿不能删除", 409) from exc
            if cursor.rowcount != 1: raise DomainError("DELETE_NOT_ALLOWED", "仅无引用交付草稿可以删除", 409)
            self._audit(connection, user_id, "delete_draft", "delivery", record_id, before=before); return before

    def list_receivables(self, **query: Any) -> dict[str, Any]: return receipts.list_receivables(self, **query)
    def list_receipts(self, **query: Any) -> dict[str, Any]: return receipts.list_receipts(self, **query)
    def get_receipt(self, record_id: int, **context: Any) -> dict[str, Any] | None: return receipts.get_receipt(self, record_id, **context)
    def receipt_was_handled_by(self, record_id: int, user_id: int) -> bool: return receipts.receipt_was_handled_by(self, record_id, user_id)
    def create_receipt(self, payload: dict[str, Any], **context: Any) -> dict[str, Any]: return receipts.create_receipt(self, payload, **context)
    def update_receipt(self, record_id: int, payload: dict[str, Any], **context: Any) -> dict[str, Any]: return receipts.update_receipt(self, record_id, payload, **context)
    def set_receipt_status(self, record_id: int, status: str, **context: Any) -> dict[str, Any]: return receipts.set_receipt_status(self, record_id, status, **context)
    def cancel_receipt(self, record_id: int, **context: Any) -> dict[str, Any]: return receipts.cancel_receipt(self, record_id, **context)
    def delete_receipt_draft(self, record_id: int, **context: Any) -> dict[str, Any]: return receipts.delete_receipt_draft(self, record_id, **context)
    def reverse_receipt(self, record_id: int, **context: Any) -> dict[str, Any]: return reversals.reverse_receipt(self, record_id, **context)
    def list_returns(self, kind: str, **context: Any) -> dict[str, Any]: return self.returns.list_returns(kind, **context)
    def get_return(self, kind: str, record_id: int, **context: Any) -> dict[str, Any] | None: return self.returns.get_return(kind, record_id, **context)
    def create_return(self, kind: str, payload: dict[str, Any], **context: Any) -> dict[str, Any]: return self.returns.create_return(kind, payload, **context)
    def set_return_status(self, kind: str, record_id: int, status: str, **context: Any) -> dict[str, Any]: return self.returns.set_return_status(kind, record_id, status, **context)
    def delete_return(self, kind: str, record_id: int, **context: Any) -> dict[str, Any]: return self.returns.delete_return(kind, record_id, **context)

    def _audit(self, connection: Any, user_id: int, action: str, resource: str, record_id: int, *, before: Any = None, after: Any = None) -> None:
        self.audit.write(connection, user_id=user_id, action=f"{action}_sales", object_type=f"sales:{resource}", object_id=record_id, object_ref=f"{resource}:{record_id}", result="success", ip_address=None, module_code="sales", before=before, after=after)
