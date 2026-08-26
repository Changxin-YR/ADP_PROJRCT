from __future__ import annotations

from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def validate_relations(cursor: Any, resource: str, row: dict[str, Any]) -> None:
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
