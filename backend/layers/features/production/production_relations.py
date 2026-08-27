from __future__ import annotations

from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def feed_plan_relation_valid(cursor: Any, row: dict[str, Any]) -> bool:
    """Check the complete feed-plan relationship at the point of use."""
    cursor.execute(
        "SELECT b.id FROM ponds p "
        "JOIN production_batches b ON b.id=%s AND b.pond_id=p.id "
        "AND b.organization_id=p.organization_id AND b.status='verified' "
        "JOIN materials m ON m.id=%s AND m.organization_id=p.organization_id "
        "AND m.status='verified' "
        "WHERE p.id=%s AND p.organization_id=%s AND p.status='verified' "
        "AND (LOWER(COALESCE(m.category,'')) LIKE '%feed%' "
        "OR m.category LIKE '%饲料%' OR m.name LIKE '%饲料%')",
        (row.get("batch_id"), row.get("material_id"), row.get("pond_id"), row.get("organization_id")),
    )
    return cursor.fetchone() is not None


def validate_relations(cursor: Any, resource: str, row: dict[str, Any]) -> None:
    if resource == "feed-plans" and not feed_plan_relation_valid(cursor, row):
        raise DomainError("FEED_PLAN_RELATION_INVALID", "投喂计划必须关联同企业、同塘口的已核验批次和可用饲料", 409)
    if resource in {"feed-logs", "feed-tasks"} and row.get("feed_task_id"):
        cursor.execute(
            "SELECT id FROM production_documents WHERE id=%s AND document_type='feed_task' AND status='verified' AND organization_id=%s AND batch_id<=>%s AND pond_id=%s",
            (row["feed_task_id"], row["organization_id"], row.get("batch_id"), row["pond_id"]),
        )
        if cursor.fetchone() is None:
            raise DomainError("FEED_TASK_RELATION_INVALID", "投喂记录必须关联同企业、同塘口、同批次的已核验投喂任务", 409)
    if resource in {"feed-logs", "feed-tasks"} and row.get("feed_plan_id"):
        cursor.execute(
            "SELECT id FROM production_documents WHERE id=%s AND document_type='feed_plan' AND status='verified' AND organization_id=%s AND batch_id<=>%s AND pond_id=%s",
            (row["feed_plan_id"], row["organization_id"], row.get("batch_id"), row["pond_id"]),
        )
        if cursor.fetchone() is None:
            raise DomainError("FEED_PLAN_RELATION_INVALID", "投喂记录必须关联同企业、同塘口、同批次的已核验投喂计划", 409)
    if resource == "feed-logs" and row.get("material_issue_request_id"):
        cursor.execute(
            "SELECT id FROM warehouse_documents WHERE id=%s AND document_type='issue_request' AND status='verified' AND organization_id=%s AND material_id=%s AND pond_id<=>%s",
            (row["material_issue_request_id"], row["organization_id"], row.get("material_id"), row.get("pond_id")),
        )
        if cursor.fetchone() is None:
            raise DomainError("FEED_MATERIAL_REQUEST_INVALID", "投喂记录必须关联同企业、同塘口、同物料的已核验领料申请", 409)
