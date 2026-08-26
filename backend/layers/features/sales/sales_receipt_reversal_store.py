from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pymysql

from backend.layers.common.db.connection import get_connection
from backend.layers.common.files.evidence import validate_bound_evidence
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.sales.sales_receipt_store import receivable_snapshot


def reverse_receipt(store: Any, record_id: int, *, expected_version: int, user: dict[str, Any], user_id: int, reason: str, evidence_attachment_ids: list[int]) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM sales_receipts WHERE id=%s FOR UPDATE", (record_id,)); receipt = cursor.fetchone()
        if receipt is None: raise DomainError("SALES_RECEIPT_NOT_FOUND", "收款记录不存在", 404)
        if receipt["status"] != "verified" or int(receipt["row_version"]) != expected_version: raise DomainError("RECEIPT_NOT_REVERSIBLE", "收款状态或版本已变化", 409)
        source = receivable_snapshot(store, cursor, user, int(receipt["receivable_id"]), lock=True)
        evidence = validate_bound_evidence(cursor, organization_id=int(receipt["organization_id"]), entity_type=("sales:receipt", "sales:receipt_reversal"), entity_id=record_id, evidence_ids=evidence_attachment_ids)
        try:
            cursor.execute("INSERT INTO sales_receipt_reversals (organization_id,receipt_id,amount,reversal_reason,evidence_attachment_ids_json,created_by) VALUES (%s,%s,%s,%s,%s,%s)", (receipt["organization_id"], record_id, receipt["amount"], reason, json.dumps(evidence), user_id))
        except pymysql.IntegrityError as exc: raise DomainError("RECEIPT_ALREADY_REVERSED", "该收款已经冲销", 409) from exc
        reversal_id = int(cursor.lastrowid); received = Decimal(str(source["received_amount"])) - Decimal(str(receipt["amount"]))
        if received < 0: raise DomainError("RECEIVABLE_BALANCE_INVALID", "应收已收金额异常，拒绝冲销", 409)
        effective = Decimal(str(source["effective_amount"])); status = "settled" if received == effective else "partial" if received else "unpaid"
        cursor.execute("UPDATE sales_receivables SET received_amount=%s,status=%s WHERE id=%s", (received, status, receipt["receivable_id"])); cursor.execute("SELECT * FROM sales_receipt_reversals WHERE id=%s", (reversal_id,)); row = dict(cursor.fetchone()); store._audit(connection, user_id, "reverse", "receipt", record_id, before=receipt, after=row); return row
