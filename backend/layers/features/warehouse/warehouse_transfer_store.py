from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError


def dispatch_transfer(store: Any, record_id: int, *, expected_version: int, user_id: int) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        before = store._get(cursor, "transfers", record_id, lock=True)
        if before is None or before["status"] != "submitted" or int(before["row_version"]) != expected_version:
            raise DomainError("VERSION_CONFLICT", "调拨单状态或版本已变化，请刷新后重试", 409)
        store.poster.lock_business_anchors(cursor, "transfers", before)
        cursor.execute(
            "UPDATE warehouse_documents SET status='in_transit',dispatched_by=%s,dispatched_at=CURRENT_TIMESTAMP,updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s",
            (user_id, user_id, record_id, expected_version),
        )
        after = store._get(cursor, "transfers", record_id)
        store.poster.post_transfer_dispatch(cursor, after or {}, user_id)
        cursor.execute(
            "UPDATE work_items SET action_code='receive',title=%s,target_version=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')",
            (f"接收调拨单：{after['name']}", after["row_version"], f"warehouse:transfers:{record_id}:verify"),
        )
        store._audit(connection, user_id, "dispatch", "transfers", record_id, before=before, after=after)
        return after or {}


def receive_transfer(
    store: Any,
    record_id: int,
    *,
    expected_version: int,
    user_id: int,
    received_quantity: Decimal,
    difference_reason: str | None,
) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        before = store._get(cursor, "transfers", record_id, lock=True)
        if before is None or before["status"] != "in_transit" or int(before["row_version"]) != expected_version:
            raise DomainError("VERSION_CONFLICT", "调拨单状态或版本已变化，请刷新后重试", 409)
        cursor.execute(
            "UPDATE warehouse_documents SET status='verified',received_quantity=%s,receipt_difference_reason=%s,received_by=%s,received_at=CURRENT_TIMESTAMP,verified_by=%s,verified_at=CURRENT_TIMESTAMP,updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s",
            (received_quantity, difference_reason, user_id, user_id, user_id, record_id, expected_version),
        )
        after = store._get(cursor, "transfers", record_id)
        store.poster.post_transfer_receive(cursor, after or {}, user_id)
        cursor.execute(
            "UPDATE work_items SET status='completed',completed_by=%s,completed_at=CURRENT_TIMESTAMP,completion_note='调拨接收完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')",
            (user_id, f"warehouse:transfers:{record_id}:verify"),
        )
        store._audit(connection, user_id, "receive", "transfers", record_id, before=before, after=after)
        return after or {}


def cancel_transfer(store: Any, record_id: int, *, expected_version: int, user_id: int, reason: str) -> dict[str, Any]:
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        before = store._get(cursor, "transfers", record_id, lock=True)
        if before is None or before["status"] not in {"submitted", "in_transit"} or int(before["row_version"]) != expected_version:
            raise DomainError("VERSION_CONFLICT", "调拨单状态或版本已变化，请刷新后重试", 409)
        if before["status"] == "in_transit":
            store.poster.post_transfer_cancel(cursor, before, user_id)
        cursor.execute(
            "UPDATE warehouse_documents SET status='cancelled',cancellation_reason=%s,cancelled_by=%s,cancelled_at=CURRENT_TIMESTAMP,updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s",
            (reason, user_id, user_id, record_id, expected_version),
        )
        after = store._get(cursor, "transfers", record_id)
        cursor.execute(
            "UPDATE work_items SET status='cancelled',cancelled_by=%s,cancelled_at=CURRENT_TIMESTAMP,cancel_reason=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')",
            (user_id, reason, f"warehouse:transfers:{record_id}:verify"),
        )
        store._audit(connection, user_id, "cancel", "transfers", record_id, before=before, after=after)
        return after or {}
