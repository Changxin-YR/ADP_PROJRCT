from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pymysql

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.revisions import build_revision, save_revision
from backend.layers.common.governance.work_item_notifications import notify_work_item_created
from backend.layers.common.files.evidence import validate_bound_evidence


EDITABLE_FIELDS = {"code", "name", "amount", "received_at", "receipt_method", "note", "evidence_attachment_ids"}


def decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row: return None
    result = dict(row); value = result.pop("evidence_attachment_ids_json", None)
    if isinstance(value, str): value = json.loads(value)
    if value is not None: result["evidence_attachment_ids"] = value
    return result


def receivable_snapshot(store: Any, cursor: Any, user: dict[str, Any], receivable_id: int, *, lock: bool = False) -> dict[str, Any]:
    cursor.execute(
        "SELECT r.*,o.area_id,o.created_by,c.name AS customer_name,r.amount+COALESCE((SELECT SUM(amount_delta) FROM sales_receivable_adjustments WHERE receivable_id=r.id),0) AS effective_amount "
        "FROM sales_receivables r JOIN sales_orders o ON o.id=r.sales_order_id JOIN business_partners c ON c.id=r.customer_id WHERE r.id=%s" + (" FOR UPDATE" if lock else ""),
        (receivable_id,),
    )
    row = cursor.fetchone()
    if row is None: raise DomainError("SALES_RECEIVABLE_NOT_FOUND", "应收记录不存在", 404)
    store._require_scope(user, row); row["balance"] = Decimal(str(row["effective_amount"])) - Decimal(str(row["received_amount"])); return row


def list_receivables(store: Any, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, **_: Any) -> dict[str, Any]:
    clauses, values = ["1=1"], []; scope, scoped = store._scope(user, "o")
    if scope: clauses.append(scope); values.extend(scoped)
    if status: clauses.append("r.status=%s"); values.append(status)
    if search: clauses.append("(o.code LIKE %s OR c.name LIKE %s)"); values.extend([f"%{search}%"] * 2)
    where = " AND ".join(clauses); page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
    joins = " FROM sales_receivables r JOIN sales_orders o ON o.id=r.sales_order_id JOIN business_partners c ON c.id=r.customer_id"
    effective = "r.amount+COALESCE((SELECT SUM(amount_delta) FROM sales_receivable_adjustments a WHERE a.receivable_id=r.id),0)"
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS total{joins} WHERE {where}", tuple(values)); total = int(cursor.fetchone()["total"])
        cursor.execute(f"SELECT COALESCE(SUM({effective}),0) AS total_amount,COALESCE(SUM(GREATEST({effective}-r.received_amount,0)),0) AS total_balance,COALESCE(SUM(GREATEST(r.received_amount-{effective},0)),0) AS overpaid_amount,SUM(CASE WHEN r.due_date<CURRENT_DATE AND {effective}-r.received_amount>0 THEN 1 ELSE 0 END) AS overdue_count{joins} WHERE {where}", tuple(values)); summary = dict(cursor.fetchone())
        cursor.execute(f"SELECT r.id,r.sales_order_id,r.source_delivery_id,r.customer_id,r.due_date,r.status,r.created_at,o.code AS order_code,o.area_id,c.name AS customer_name,{effective} AS amount,r.received_amount,{effective}-r.received_amount AS balance,DATEDIFF(CURRENT_DATE,r.due_date) AS overdue_days{joins} WHERE {where} ORDER BY r.due_date,r.id LIMIT %s OFFSET %s", tuple(values + [page_size, (page - 1) * page_size])); items = [dict(row) for row in cursor.fetchall()]
    summary["overdue_count"] = int(summary.get("overdue_count") or 0)
    return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total, "summary": summary}


def list_receipts(store: Any, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, **_: Any) -> dict[str, Any]:
    clauses, values = ["1=1"], []; scope, scoped = store._scope(user, "o")
    if scope: clauses.append(scope); values.extend(scoped)
    if status: clauses.append("m.status=%s"); values.append(status)
    if search: clauses.append("(m.code LIKE %s OR m.name LIKE %s OR o.code LIKE %s OR c.name LIKE %s)"); values.extend([f"%{search}%"] * 4)
    where = " AND ".join(clauses); page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
    joins = " FROM sales_receipts m JOIN sales_receivables r ON r.id=m.receivable_id JOIN sales_orders o ON o.id=r.sales_order_id JOIN business_partners c ON c.id=r.customer_id"
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS total{joins} WHERE {where}", tuple(values)); total = int(cursor.fetchone()["total"])
        cursor.execute(f"SELECT m.*,x.id AS reversal_id,o.code AS order_code,o.area_id,c.name AS customer_name{joins} LEFT JOIN sales_receipt_reversals x ON x.receipt_id=m.id WHERE {where} ORDER BY m.updated_at DESC,m.id DESC LIMIT %s OFFSET %s", tuple(values + [page_size, (page - 1) * page_size])); items = [decode(row) or {} for row in cursor.fetchall()]
    return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}


def receipt_was_handled_by(store: Any, record_id: int, user_id: int) -> bool:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT (EXISTS(SELECT 1 FROM sales_receipts WHERE id=%s AND created_by=%s) OR "
            "EXISTS(SELECT 1 FROM audit_logs WHERE object_type='sales:receipt' AND object_id=%s AND user_id=%s "
            "AND action IN ('create_sales','submitted_sales','update_sales'))) AS handled",
            (record_id, user_id, record_id, user_id),
        )
        return bool(cursor.fetchone()["handled"])


def get_receipt(store: Any, record_id: int, *, user: dict[str, Any]) -> dict[str, Any] | None:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT m.*,x.id AS reversal_id,o.area_id,o.created_by AS order_created_by FROM sales_receipts m JOIN sales_receivables r ON r.id=m.receivable_id JOIN sales_orders o ON o.id=r.sales_order_id LEFT JOIN sales_receipt_reversals x ON x.receipt_id=m.id WHERE m.id=%s", (record_id,)); row = decode(cursor.fetchone())
        if row: store._require_scope(user, row)
        return row


def create_receipt(store: Any, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        source = receivable_snapshot(store, cursor, user, int(payload["receivable_id"]), lock=True)
        if source["status"] not in {"unpaid", "partial"}: raise DomainError("RECEIVABLE_NOT_PAYABLE", "当前应收状态不能登记收款", 409)
        clean = {key: value for key, value in payload.items() if key in EDITABLE_FIELDS | {"receivable_id"} and key != "evidence_attachment_ids"}
        if payload.get("evidence_attachment_ids"): clean["evidence_attachment_ids_json"] = json.dumps(payload["evidence_attachment_ids"])
        clean.update(organization_id=source["organization_id"], status="draft", row_version=1, created_by=user_id)
        cursor.execute(f"INSERT INTO sales_receipts ({','.join(clean)}) VALUES ({','.join(['%s'] * len(clean))})", tuple(clean.values())); record_id = int(cursor.lastrowid)
        cursor.execute("SELECT * FROM sales_receipts WHERE id=%s", (record_id,)); row = decode(cursor.fetchone()) or {}; store._audit(connection, user_id, "create", "receipt", record_id, after=row); return row


def update_receipt(store: Any, record_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM sales_receipts WHERE id=%s FOR UPDATE", (record_id,)); before = decode(cursor.fetchone())
        if before is None: raise DomainError("SALES_RECEIPT_NOT_FOUND", "收款记录不存在", 404)
        receivable_snapshot(store, cursor, user, int(before["receivable_id"])); clean = {key: value for key, value in payload.items() if key in EDITABLE_FIELDS and key != "evidence_attachment_ids"}
        if "evidence_attachment_ids" in payload: clean["evidence_attachment_ids_json"] = json.dumps(payload["evidence_attachment_ids"])
        if not clean: raise DomainError("SALES_NO_CHANGES", "没有可保存的修改", 400)
        cursor.execute(f"UPDATE sales_receipts SET {','.join(f'{key}=%s' for key in clean)},updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status IN ('draft','submitted')", (*clean.values(), user_id, record_id, expected_version))
        if cursor.rowcount != 1: raise DomainError("VERSION_CONFLICT", "收款数据已变化，请刷新后重试", 409)
        cursor.execute("SELECT * FROM sales_receipts WHERE id=%s", (record_id,)); after = decode(cursor.fetchone()) or {}
        if before["status"] == "submitted":
            save_revision(connection, build_revision(entity_type="sales:receipt", entity_id=record_id, current_version=expected_version, before=before, after=after, actor_user_id=user_id)); cursor.execute("UPDATE work_items SET target_version=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (after["row_version"], f"sales:receipt:{record_id}:verify"))
        store._audit(connection, user_id, "update", "receipt", record_id, before=before, after=after); return after


def set_receipt_status(store: Any, record_id: int, status: str, *, expected_version: int, user: dict[str, Any], user_id: int, evidence_attachment_ids: list[int] | None = None) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM sales_receipts WHERE id=%s FOR UPDATE", (record_id,)); before = decode(cursor.fetchone())
        if before is None: raise DomainError("SALES_RECEIPT_NOT_FOUND", "收款记录不存在", 404)
        source = receivable_snapshot(store, cursor, user, int(before["receivable_id"]), lock=status == "verified")
        evidence = validate_bound_evidence(cursor, organization_id=int(before["organization_id"]), entity_type="sales:receipt", entity_id=record_id, evidence_ids=evidence_attachment_ids or before.get("evidence_attachment_ids"))
        if status == "verified" and (source["status"] not in {"unpaid", "partial"} or Decimal(str(before["amount"])) > Decimal(str(source["balance"]))): raise DomainError("RECEIPT_EXCEEDS_BALANCE", "收款金额不能超过应收余额", 409)
        extra, params = "", [status, user_id]
        if evidence: extra += ",evidence_attachment_ids_json=%s"; params.append(json.dumps(evidence))
        if status == "verified": extra += ",verified_by=%s,verified_at=NOW()"; params.append(user_id)
        params.extend([record_id, expected_version]); cursor.execute(f"UPDATE sales_receipts SET status=%s,updated_by=%s{extra},row_version=row_version+1 WHERE id=%s AND row_version=%s", tuple(params))
        if cursor.rowcount != 1: raise DomainError("VERSION_CONFLICT", "收款状态或版本已变化", 409)
        cursor.execute("SELECT * FROM sales_receipts WHERE id=%s", (record_id,)); after = decode(cursor.fetchone()) or {}; key = f"sales:receipt:{record_id}:verify"
        if status == "submitted":
            cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'finance','verify','sales:receipt',%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version)", (after["organization_id"], record_id, f"receipt:{record_id}", key, f"核验收款：{after['name']}", after["row_version"]))
            notify_work_item_created(
                connection,
                organization_id=after["organization_id"],
                area_id=source.get("area_id"),
                module_code="finance",
                action_code="verify",
                object_type="sales:receipt",
                object_id=record_id,
                object_ref=f"receipt:{record_id}",
                source_key=key,
                title=f"核验收款：{after['name']}",
                permission_codes=["finance.receipt.verify"],
            )
        else:
            received = Decimal(str(source["received_amount"])) + Decimal(str(after["amount"])); effective = Decimal(str(source["effective_amount"])); cursor.execute("UPDATE sales_receivables SET received_amount=%s,status=%s WHERE id=%s", (received, "settled" if received == effective else "partial", after["receivable_id"])); cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=NOW(),completion_note='收款核验完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, key))
        store._audit(connection, user_id, status, "receipt", record_id, before=before, after=after); return after


def cancel_receipt(store: Any, record_id: int, *, expected_version: int, user: dict[str, Any], user_id: int, reason: str) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM sales_receipts WHERE id=%s FOR UPDATE", (record_id,)); before = decode(cursor.fetchone())
        if before is None: raise DomainError("SALES_RECEIPT_NOT_FOUND", "收款记录不存在", 404)
        receivable_snapshot(store, cursor, user, int(before["receivable_id"])); cursor.execute("UPDATE sales_receipts SET status='cancelled',cancellation_reason=%s,cancelled_by=%s,cancelled_at=NOW(),updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status='submitted'", (reason, user_id, user_id, record_id, expected_version))
        if cursor.rowcount != 1: raise DomainError("VERSION_CONFLICT", "收款状态或版本已变化", 409)
        cursor.execute("SELECT * FROM sales_receipts WHERE id=%s", (record_id,)); after = decode(cursor.fetchone()) or {}; cursor.execute("UPDATE work_items SET status='cancelled',cancelled_by=%s,cancelled_at=NOW(),cancel_reason=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, reason, f"sales:receipt:{record_id}:verify")); store._audit(connection, user_id, "cancel", "receipt", record_id, before=before, after=after); return after


def delete_receipt_draft(store: Any, record_id: int, *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM sales_receipts WHERE id=%s FOR UPDATE", (record_id,)); before = decode(cursor.fetchone())
        if before is None: raise DomainError("SALES_RECEIPT_NOT_FOUND", "收款记录不存在", 404)
        receivable_snapshot(store, cursor, user, int(before["receivable_id"]))
        try: cursor.execute("DELETE FROM sales_receipts WHERE id=%s AND status='draft'", (record_id,))
        except pymysql.IntegrityError as exc: raise DomainError("DELETE_NOT_ALLOWED", "已有业务引用的收款草稿不能删除", 409) from exc
        if cursor.rowcount != 1: raise DomainError("DELETE_NOT_ALLOWED", "仅无引用收款草稿可以删除", 409)
        store._audit(connection, user_id, "delete_draft", "receipt", record_id, before=before); return before
