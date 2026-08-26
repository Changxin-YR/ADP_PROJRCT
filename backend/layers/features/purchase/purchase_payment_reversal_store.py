from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pymysql

from backend.layers.common.db.connection import get_connection
from backend.layers.common.files.evidence import validate_bound_evidence
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.purchase.purchase_payment_store import payable_snapshot


def reverse_payment(
    store: Any,
    payment_id: int,
    *,
    expected_version: int,
    user: dict[str, Any],
    user_id: int,
    reason: str,
    evidence_attachment_ids: list[int],
) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM purchase_payments WHERE id=%s FOR UPDATE", (payment_id,))
        payment = cursor.fetchone()
        if payment is None:
            raise DomainError("PAYMENT_NOT_FOUND", "付款记录不存在", 404)
        if payment["status"] != "verified" or int(payment["row_version"]) != expected_version:
            raise DomainError("PAYMENT_NOT_REVERSIBLE", "付款状态或版本已变化", 409)
        payable = payable_snapshot(store, cursor, user, int(payment["payable_id"]), lock=True)
        evidence = validate_bound_evidence(
            cursor,
            organization_id=int(payment["organization_id"]),
            entity_type=("purchase:payment", "purchase:payment_reversal"),
            entity_id=payment_id,
            evidence_ids=evidence_attachment_ids,
        )
        try:
            cursor.execute(
                "INSERT INTO purchase_payment_reversals (organization_id,payment_id,amount,reversal_reason,evidence_attachment_ids_json,created_by) VALUES (%s,%s,%s,%s,%s,%s)",
                (payment["organization_id"], payment_id, payment["amount"], reason, json.dumps(evidence), user_id),
            )
        except pymysql.IntegrityError as exc:
            raise DomainError("PAYMENT_ALREADY_REVERSED", "该付款已经冲销", 409) from exc
        reversal_id = int(cursor.lastrowid)
        paid = Decimal(str(payable["paid_amount"])) - Decimal(str(payment["amount"]))
        if paid < 0:
            raise DomainError("PAYABLE_BALANCE_INVALID", "应付已付金额异常，拒绝冲销", 409)
        status = "settled" if paid == payable["effective_amount"] else "partial" if paid else "unpaid"
        cursor.execute("UPDATE purchase_payables SET paid_amount=%s,status=%s WHERE id=%s", (paid, status, payment["payable_id"]))
        cursor.execute("SELECT * FROM purchase_payment_reversals WHERE id=%s", (reversal_id,))
        row = dict(cursor.fetchone())
        store._audit(connection, user_id, "reverse", "payment", payment_id, before=payment, after=row)
        return row
