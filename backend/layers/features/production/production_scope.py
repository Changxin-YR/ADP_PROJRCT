from __future__ import annotations

from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def scope_defaults(cursor: Any, payload: dict[str, Any], resource: str | None = None) -> dict[str, Any]:
    result = dict(payload)
    if result.get("pond_id"):
        cursor.execute("SELECT organization_id,farm_id,area_id,pond_status,status FROM ponds WHERE id=%s", (result["pond_id"],))
        pond = cursor.fetchone()
        if pond is None:
            raise DomainError("POND_NOT_FOUND", "塘口不存在", 400)
        if pond.get("status") is not None and pond.get("status") != "verified":
            raise DomainError("POND_NOT_VERIFIED", "生产业务只能引用已核验塘口", 409)
        if resource in {"feed-plans", "feed-tasks", "feed-logs", "daily-operations"} and pond.get("pond_status") not in (None, "farming"):
            raise DomainError("POND_NOT_READY", "当前塘口状态不允许正常养殖作业", 409)
        for key in ("organization_id", "farm_id", "area_id"):
            result[key] = int(pond[key])
    if result.get("target_pond_id"):
        cursor.execute("SELECT organization_id,area_id,status FROM ponds WHERE id=%s", (result["target_pond_id"],))
        target = cursor.fetchone()
        if target is None:
            raise DomainError("TARGET_POND_NOT_FOUND", "转入塘口不存在", 400)
        if target.get("status") is not None and target.get("status") != "verified":
            raise DomainError("POND_NOT_VERIFIED", "生产业务只能引用已核验目标塘口", 409)
        if result.get("organization_id") and int(target["organization_id"]) != int(result["organization_id"]):
            raise DomainError("PRODUCTION_SCOPE_INVALID", "来源与目标塘口必须属于同一企业", 400)
        result["_target_area_id"] = int(target["area_id"])
    if result.get("batch_id"):
        cursor.execute("SELECT organization_id,farm_id,area_id,pond_id,status FROM production_batches WHERE id=%s", (result["batch_id"],))
        batch = cursor.fetchone()
        if batch is None or batch.get("status") != "verified":
            raise DomainError("BATCH_NOT_VERIFIED", "生产业务只能关联已核验批次", 409)
        if result.get("organization_id") and int(batch["organization_id"]) != int(result["organization_id"]):
            raise DomainError("PRODUCTION_RELATION_INVALID", "批次与塘口必须属于同一企业", 409)
        if result.get("pond_id") and int(batch["pond_id"]) != int(result["pond_id"]):
            raise DomainError("PRODUCTION_RELATION_INVALID", "批次与生产塘口不一致", 409)
    if result.get("material_id") and result.get("organization_id"):
        cursor.execute("SELECT id FROM materials WHERE id=%s AND organization_id=%s AND status='verified'", (result["material_id"], result["organization_id"]))
        if cursor.fetchone() is None:
            raise DomainError("MATERIAL_NOT_VERIFIED", "生产业务只能关联当前企业已核验物料", 409)
    if (assignee := result.get("assigned_user_id")) not in (None, ""):
        try:
            assignee = int(assignee)
        except (TypeError, ValueError) as exc:
            raise DomainError("FEED_TASK_ASSIGNEE_INVALID", "指派作业员不存在或已停用", 400) from exc
        cursor.execute("SELECT id FROM users WHERE id=%s AND status='active'", (assignee,))
        if cursor.fetchone() is None:
            raise DomainError("FEED_TASK_ASSIGNEE_INVALID", "指派作业员不存在或已停用", 400)
        cursor.execute(
            "SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id AND r.status='active' "
            "JOIN user_data_scopes uds ON uds.user_id=ur.user_id "
            "JOIN data_scopes ds ON ds.id=uds.data_scope_id AND ds.status='active' "
            "WHERE ur.user_id=%s AND r.code IN ('breed_worker','breed_manager') "
            "AND ((ds.scope_type='area' AND ds.area_id=%s AND ds.organization_id=%s) "
            "OR (ds.scope_type='farm' AND ds.organization_id=%s AND (ds.farm_id=%s OR ds.farm_id IS NULL))) LIMIT 1",
            (assignee, result.get("area_id"), result.get("organization_id"), result.get("organization_id"), result.get("farm_id")),
        )
        if cursor.fetchone() is None:
            raise DomainError("FEED_TASK_ASSIGNEE_INVALID", "投喂任务只能指派养殖岗位人员", 400)
    return result
