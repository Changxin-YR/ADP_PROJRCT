from __future__ import annotations

from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def lock_batch_anchors(cursor: Any, resource: str, row: dict[str, Any]) -> None:
    """Acquire stock anchors before any consistent read creates an old snapshot."""
    if resource not in {"batches", "transfers", "losses", "harvests"}:
        return
    batch_ids = {
        int(row.get("correction_of_id") or row["id"])
        if resource == "batches"
        else int(row["batch_id"])
    }
    if row.get("correction_of_id") and resource != "batches":
        cursor.execute(
            "SELECT * FROM production_documents WHERE id=%s FOR UPDATE",
            (row["correction_of_id"],),
        )
        original = cursor.fetchone()
        if original is None:
            raise DomainError("CORRECTION_SOURCE_NOT_FOUND", "原核验记录不存在", 409)
        batch_ids.add(int(original["batch_id"]))
    for batch_id in sorted(batch_ids):
        cursor.execute("SELECT id FROM production_batches WHERE id=%s FOR UPDATE", (batch_id,))
        if cursor.fetchone() is None:
            raise DomainError("BATCH_NOT_FOUND", "生产批次不存在", 409)
