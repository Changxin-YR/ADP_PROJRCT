from __future__ import annotations

from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def require_material_issue(cursor: Any, row: dict[str, Any]) -> None:
    cursor.execute(
        """
        SELECT r.id AS request_id,COALESCE(SUM(i.quantity),0) AS issued_quantity
        FROM warehouse_documents r
        LEFT JOIN warehouse_documents i ON i.source_document_id=r.id
          AND i.document_type='issue' AND i.status='verified'
          AND i.material_id=r.material_id AND i.pond_id=r.pond_id
        WHERE r.id=%s AND r.document_type='issue_request' AND r.status='verified'
          AND r.material_id=%s AND r.pond_id=%s
        GROUP BY r.id
        HAVING issued_quantity>=%s
        """,
        (row.get("material_issue_request_id"), row.get("material_id"), row.get("pond_id"), row.get("quantity") or 0),
    )
    if cursor.fetchone() is None:
        raise DomainError(
            "FEED_MATERIAL_ISSUE_REQUIRED",
            "投喂核验必须关联已核验领料申请和足额实际出库",
            409,
        )
