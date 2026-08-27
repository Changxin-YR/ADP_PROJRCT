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


EDITABLE_PAYMENT_FIELDS = {"code", "name", "amount", "paid_at", "payment_method", "note", "evidence_attachment_ids"}


def decode_payment(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    result = dict(row)
    value = result.pop("evidence_attachment_ids_json", None)
    if isinstance(value, str):
        value = json.loads(value)
    if value is not None:
        result["evidence_attachment_ids"] = value
    return result


def list_payables(store: Any, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, **_: Any) -> dict[str, Any]:
    page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
    clauses, values = ["1=1"], []
    if status:
        clauses.append("p.status=%s"); values.append(status)
    if search:
        clauses.append("(o.code LIKE %s OR s.name LIKE %s)"); values.extend([f"%{search}%"] * 2)
    scope, scoped = store._scope(user, "o")
    if scope:
        clauses.append(scope); values.extend(scoped)
    where = " AND ".join(clauses)
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS total FROM purchase_payables p JOIN purchase_orders o ON o.id=p.purchase_order_id JOIN business_partners s ON s.id=p.supplier_id WHERE {where}", tuple(values))
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            f"SELECT p.*,p.amount+COALESCE((SELECT SUM(a.amount_delta) FROM purchase_payable_adjustments a WHERE a.payable_id=p.id),0) AS effective_amount,"
            f"p.amount+COALESCE((SELECT SUM(a.amount_delta) FROM purchase_payable_adjustments a WHERE a.payable_id=p.id),0)-p.paid_amount AS balance,DATEDIFF(CURRENT_DATE,p.due_date) AS overdue_days,o.code AS order_code,s.name AS supplier_name "
            f"FROM purchase_payables p JOIN purchase_orders o ON o.id=p.purchase_order_id JOIN business_partners s ON s.id=p.supplier_id WHERE {where} "
            "ORDER BY p.due_date,p.id LIMIT %s OFFSET %s",
            tuple(values + [page_size, (page - 1) * page_size]),
        )
        items = list(cursor.fetchall())
        for item in items:
            item["source_amount"] = item["amount"]
            item["amount"] = item.pop("effective_amount")
    return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}


def list_payments(store: Any, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, **_: Any) -> dict[str, Any]:
    page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
    clauses, values = ["1=1"], []
    if status:
        clauses.append("m.status=%s"); values.append(status)
    if search:
        clauses.append("(m.code LIKE %s OR m.name LIKE %s OR o.code LIKE %s OR s.name LIKE %s)"); values.extend([f"%{search}%"] * 4)
    scope, scoped = store._scope(user, "o")
    if scope:
        clauses.append(scope); values.extend(scoped)
    where = " AND ".join(clauses)
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS total FROM purchase_payments m JOIN purchase_payables p ON p.id=m.payable_id JOIN purchase_orders o ON o.id=p.purchase_order_id JOIN business_partners s ON s.id=p.supplier_id WHERE {where}", tuple(values))
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            f"SELECT m.*,r.id AS reversal_id,o.code AS order_code,s.name AS supplier_name FROM purchase_payments m LEFT JOIN purchase_payment_reversals r ON r.payment_id=m.id JOIN purchase_payables p ON p.id=m.payable_id JOIN purchase_orders o ON o.id=p.purchase_order_id JOIN business_partners s ON s.id=p.supplier_id WHERE {where} ORDER BY m.updated_at DESC,m.id DESC LIMIT %s OFFSET %s",
            tuple(values + [page_size, (page - 1) * page_size]),
        )
        items = [decode_payment(row) or {} for row in cursor.fetchall()]
    return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}


def payable_snapshot(store: Any, cursor: Any, user: dict[str, Any], payable_id: int, *, lock: bool = False) -> dict[str, Any]:
    cursor.execute(
        "SELECT p.*,o.area_id,o.created_by,COALESCE((SELECT SUM(a.amount_delta) FROM purchase_payable_adjustments a WHERE a.payable_id=p.id),0) AS adjustment_total "
        "FROM purchase_payables p JOIN purchase_orders o ON o.id=p.purchase_order_id WHERE p.id=%s" + (" FOR UPDATE" if lock else ""),
        (payable_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise DomainError("PAYABLE_NOT_FOUND", "应付账款不存在", 404)
    store._require_scope(user, row)
    row["effective_amount"] = Decimal(str(row["amount"])) + Decimal(str(row["adjustment_total"]))
    row["balance"] = row["effective_amount"] - Decimal(str(row["paid_amount"]))
    return row


def get_payment(store: Any, payment_id: int, *, user: dict[str, Any]) -> dict[str, Any] | None:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT m.*,r.id AS reversal_id FROM purchase_payments m LEFT JOIN purchase_payment_reversals r ON r.payment_id=m.id WHERE m.id=%s", (payment_id,))
        row = decode_payment(cursor.fetchone())
        if row is not None:
            payable_snapshot(store, cursor, user, int(row["payable_id"]))
        return row


def create_payment(store: Any, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        payable = payable_snapshot(store, cursor, user, int(payload["payable_id"]), lock=True)
        if payable is None or payable["status"] not in {"unpaid", "partial"}:
            raise DomainError("PAYABLE_NOT_OPEN", "应付账款不存在或已经结清", 409)
        if Decimal(str(payload["amount"])) > Decimal(str(payable["balance"])):
            raise DomainError("PAYMENT_EXCEEDS_BALANCE", "付款金额不能超过应付余额", 409)
        clean = {key: value for key, value in payload.items() if key != "evidence_attachment_ids"}
        if payload.get("evidence_attachment_ids"):
            clean["evidence_attachment_ids_json"] = json.dumps(payload["evidence_attachment_ids"])
        clean.update(organization_id=payable["organization_id"], status="draft", row_version=1, created_by=user_id)
        cursor.execute(f"INSERT INTO purchase_payments ({','.join(clean)}) VALUES ({','.join(['%s'] * len(clean))})", tuple(clean.values()))
        payment_id = int(cursor.lastrowid); cursor.execute("SELECT * FROM purchase_payments WHERE id=%s", (payment_id,))
        row = decode_payment(cursor.fetchone()) or {}; store._audit(connection, user_id, "create", "payment", payment_id, after=row)
        return row


def update_payment(store: Any, payment_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM purchase_payments WHERE id=%s FOR UPDATE", (payment_id,)); before = decode_payment(cursor.fetchone())
        if before is None:
            raise DomainError("PAYMENT_NOT_FOUND", "付款记录不存在", 404)
        payable_snapshot(store, cursor, user, int(before["payable_id"]))
        clean = {key: value for key, value in payload.items() if key in EDITABLE_PAYMENT_FIELDS and key != "evidence_attachment_ids"}
        if "evidence_attachment_ids" in payload:
            clean["evidence_attachment_ids_json"] = json.dumps(payload["evidence_attachment_ids"])
        if not clean:
            raise DomainError("PAYMENT_NO_CHANGES", "没有可保存的修改", 400)
        cursor.execute(f"UPDATE purchase_payments SET {','.join(f'{key}=%s' for key in clean)},updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status IN ('draft','submitted')", (*clean.values(), user_id, payment_id, expected_version))
        if cursor.rowcount != 1:
            raise DomainError("VERSION_CONFLICT", "数据已变化，请刷新后重试", 409)
        cursor.execute("SELECT * FROM purchase_payments WHERE id=%s", (payment_id,)); after = decode_payment(cursor.fetchone()) or {}
        if before["status"] == "submitted":
            save_revision(connection, build_revision(entity_type="purchase:payment", entity_id=payment_id, current_version=expected_version, before=before, after=after, actor_user_id=user_id))
            cursor.execute("UPDATE work_items SET target_version=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (after["row_version"], f"purchase:payment:{payment_id}:verify"))
        store._audit(connection, user_id, "update", "payment", payment_id, before=before, after=after); return after


def set_payment_status(store: Any, payment_id: int, status: str, *, expected_version: int, user: dict[str, Any], user_id: int, evidence_attachment_ids: list[int] | None = None) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM purchase_payments WHERE id=%s FOR UPDATE", (payment_id,)); before = decode_payment(cursor.fetchone())
        if before is None:
            raise DomainError("PAYMENT_NOT_FOUND", "付款记录不存在", 404)
        payable = payable_snapshot(store, cursor, user, int(before["payable_id"]), lock=status == "verified")
        evidence = validate_bound_evidence(cursor, organization_id=int(before["organization_id"]), entity_type="purchase:payment", entity_id=payment_id, evidence_ids=evidence_attachment_ids or before.get("evidence_attachment_ids"))
        if status == "verified":
            remaining = Decimal(str(payable["balance"]))
            if payable["status"] not in {"unpaid", "partial"} or Decimal(str(before["amount"])) > remaining:
                raise DomainError("PAYMENT_EXCEEDS_BALANCE", "付款金额不能超过应付余额", 409)
        extra, params = "", [status, user_id]
        if evidence:
            extra += ",evidence_attachment_ids_json=%s"; params.append(json.dumps(evidence))
        if status == "verified":
            extra += ",verified_by=%s,verified_at=CURRENT_TIMESTAMP"; params.append(user_id)
        params.extend([payment_id, expected_version])
        cursor.execute(f"UPDATE purchase_payments SET status=%s,updated_by=%s{extra},row_version=row_version+1 WHERE id=%s AND row_version=%s", tuple(params))
        if cursor.rowcount != 1:
            raise DomainError("VERSION_CONFLICT", "数据已变化，请刷新后重试", 409)
        cursor.execute("SELECT * FROM purchase_payments WHERE id=%s", (payment_id,)); after = decode_payment(cursor.fetchone()) or {}
        source_key = f"purchase:payment:{payment_id}:verify"
        if status == "submitted":
            cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'finance','verify','purchase:payment',%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version)", (after["organization_id"], payment_id, f"payment:{payment_id}", source_key, f"核验付款：{after['name']}", after["row_version"]))
            notify_work_item_created(
                connection,
                organization_id=after["organization_id"],
                area_id=payable.get("area_id"),
                module_code="finance",
                action_code="verify",
                object_type="purchase:payment",
                object_id=payment_id,
                object_ref=f"payment:{payment_id}",
                source_key=source_key,
                title=f"核验付款：{after['name']}",
                permission_codes=["finance.payment.verify"],
            )
        else:
            paid = Decimal(str(payable["paid_amount"])) + Decimal(str(after["amount"]))
            cursor.execute("UPDATE purchase_payables SET paid_amount=%s,status=%s WHERE id=%s", (paid, "settled" if paid == Decimal(str(payable["effective_amount"])) else "partial", after["payable_id"]))
            cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=CURRENT_TIMESTAMP,completion_note='付款核验完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, source_key))
        store._audit(connection, user_id, status, "payment", payment_id, before=before, after=after); return after


def cancel_payment(store: Any, payment_id: int, *, expected_version: int, user: dict[str, Any], user_id: int, reason: str) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM purchase_payments WHERE id=%s FOR UPDATE", (payment_id,)); before = decode_payment(cursor.fetchone())
        if before is None:
            raise DomainError("PAYMENT_NOT_FOUND", "付款记录不存在", 404)
        payable_snapshot(store, cursor, user, int(before["payable_id"]))
        cursor.execute("UPDATE purchase_payments SET status='cancelled',cancellation_reason=%s,cancelled_by=%s,cancelled_at=CURRENT_TIMESTAMP,updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status='submitted'", (reason, user_id, user_id, payment_id, expected_version))
        if cursor.rowcount != 1:
            raise DomainError("VERSION_CONFLICT", "付款状态或版本已变化", 409)
        cursor.execute("SELECT * FROM purchase_payments WHERE id=%s", (payment_id,)); after = decode_payment(cursor.fetchone()) or {}
        cursor.execute("UPDATE work_items SET status='cancelled',cancelled_by=%s,cancelled_at=CURRENT_TIMESTAMP,cancel_reason=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, reason, f"purchase:payment:{payment_id}:verify"))
        store._audit(connection, user_id, "cancel", "payment", payment_id, before=before, after=after); return after


def delete_payment_draft(store: Any, payment_id: int, *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM purchase_payments WHERE id=%s FOR UPDATE", (payment_id,)); before = decode_payment(cursor.fetchone())
        if before is None:
            raise DomainError("PAYMENT_NOT_FOUND", "付款记录不存在", 404)
        payable_snapshot(store, cursor, user, int(before["payable_id"]))
        try:
            cursor.execute("DELETE FROM purchase_payments WHERE id=%s AND status='draft'", (payment_id,))
        except pymysql.IntegrityError as exc:
            raise DomainError("DELETE_NOT_ALLOWED", "已有业务引用的付款草稿不能删除", 409) from exc
        if cursor.rowcount != 1:
            raise DomainError("DELETE_NOT_ALLOWED", "仅未提交付款草稿可以删除", 409)
        store._audit(connection, user_id, "delete_draft", "payment", payment_id, before=before); return before or {}
