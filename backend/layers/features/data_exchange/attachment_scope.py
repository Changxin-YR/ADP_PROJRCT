from __future__ import annotations

from typing import Any

import pymysql

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.security.data_scope import require_active_scope, unrestricted


ATTACHMENT_TARGETS = {
    "warehouse:receipts": ("warehouse_documents", "document_type='receipt'", None),
    "warehouse:issue-requests": ("warehouse_documents", "document_type='issue_request'", None),
    "warehouse:issues": ("warehouse_documents", "document_type='issue'", None),
    "warehouse:returns": ("warehouse_documents", "document_type='return'", None),
    "warehouse:transfers": ("warehouse_documents", "document_type='transfer'", None),
    "warehouse:stocktakes": ("warehouse_documents", "document_type='stocktake'", None),
    "warehouse:scraps": ("warehouse_documents", "document_type='scrap'", None),
    "production:batches": ("production_batches", None, None),
    "production:samplings": ("production_documents", "document_type='sampling'", None),
    "production:losses": ("production_documents", "document_type='loss'", None),
    "production:transfers": ("production_documents", "document_type='transfer'", None),
    "production:harvests": ("production_documents", "document_type='harvest'", None),
    "production:feed-plans": ("production_documents", "document_type='feed_plan'", None),
    "production:feed-tasks": ("production_documents", "document_type='feed_task'", None),
    "production:feed-logs": ("production_documents", "document_type='feed_log'", None),
    "production:daily-operations": ("production_documents", "document_type='daily_operation'", None),
    "purchase:payment": (
        "purchase_payments p",
        None,
        "JOIN purchase_payables b ON b.id=p.payable_id JOIN purchase_orders o ON o.id=b.purchase_order_id",
    ),
    "sales:receipt": (
        "sales_receipts p",
        None,
        "JOIN sales_receivables r ON r.id=p.receivable_id JOIN sales_orders o ON o.id=r.sales_order_id",
    ),
    "sales:delivery": ("sales_deliveries p", None, "JOIN sales_orders o ON o.id=p.sales_order_id"),
    "cost:expense": ("cost_entries", None, None),
    "cost:entry": ("cost_entries", None, None),
    "cost:asset": ("cost_assets", None, None),
}


def target_scope_allows(user: dict[str, Any], target: dict[str, Any]) -> bool:
    scopes = require_active_scope(user)
    if unrestricted(user):
        return True
    allowed_areas = {
        int(item["area_id"])
        for item in scopes
        if item.get("scope_type") == "area" and item.get("area_id")
    }
    if allowed_areas and int(target.get("area_id") or 0) in allowed_areas:
        return True
    personal = any(item.get("scope_type") == "personal" for item in scopes)
    return personal and int(target.get("created_by") or 0) == int(user["id"])


def attachment_target(
    cursor: Any,
    organization_id: int,
    entity_type: str,
    entity_id: int,
    *,
    lock: bool = False,
) -> dict[str, Any] | None:
    target = ATTACHMENT_TARGETS.get(entity_type)
    if not target:
        return None
    table, condition, joins = target
    alias = "p" if " " in table else table
    area_column = "o.area_id" if joins else f"{alias}.area_id"
    where = f"{alias}.id=%s AND {alias}.organization_id=%s" + (f" AND {condition}" if condition else "")
    cursor.execute(
        f"SELECT {alias}.organization_id,{area_column} AS area_id,{alias}.created_by AS created_by "
        f"FROM {table} {joins or ''} WHERE {where} LIMIT 1" + (" FOR UPDATE" if lock else ""),
        (entity_id, organization_id),
    )
    return cursor.fetchone()


def create_scoped_attachment(settings: Any, audit: Any, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Recheck target, scope and duplicate inside the attachment insert transaction."""
    with get_connection(settings) as connection, connection.cursor() as cursor:
        target = attachment_target(
            cursor, int(payload["organization_id"]), str(payload["entity_type"]),
            int(payload["entity_id"]), lock=True,
        )
        if target is None:
            raise DomainError("ATTACHMENT_TARGET_NOT_FOUND", "附件关联的业务记录不存在或无权访问", 404)
        if not target_scope_allows(user, target):
            raise DomainError("DATA_SCOPE_FORBIDDEN", "无权访问附件关联的业务记录", 403)
        try:
            cursor.execute(
                "INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                tuple(payload[key] for key in ("organization_id", "entity_type", "entity_id", "sha256", "storage_name", "original_name", "media_type", "size_bytes", "uploaded_by")),
            )
        except pymysql.IntegrityError as exc:
            if int(exc.args[0]) == 1062:
                raise DomainError("ATTACHMENT_DUPLICATE", "该业务记录已上传相同内容的附件", 409) from exc
            raise
        attachment_id = int(cursor.lastrowid)
        cursor.execute("SELECT * FROM attachments WHERE id=%s", (attachment_id,))
        row = dict(cursor.fetchone() or {})
        audit.write(connection, user_id=int(payload["uploaded_by"]), action="upload_attachment", object_type="data_exchange", object_id=attachment_id, object_ref=f"data_exchange:{attachment_id}", result="success", ip_address=None, module_code="data_exchange", after=row)
        return row
