from __future__ import annotations

import json
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.security.data_scope import require_active_scope, unrestricted
from backend.layers.common.files.evidence import validate_bound_evidence


COST_TARGET_QUERIES = {
    "area": "SELECT organization_id,farm_id,id AS area_id FROM areas WHERE id=%s AND status<>'archived'",
    "group": "SELECT organization_id,farm_id,area_id FROM pond_groups WHERE id=%s AND status<>'archived'",
    "pond": "SELECT organization_id,farm_id,area_id FROM ponds WHERE id=%s AND status<>'archived'",
    "batch": "SELECT organization_id,farm_id,area_id FROM production_batches WHERE id=%s AND status<>'archived'",
}


def decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    result = dict(row)
    for field in ("evidence_attachment_ids_json", "participant_snapshot_json", "source_snapshot_json"):
        value = result.get(field)
        if isinstance(value, str):
            result[field] = json.loads(value)
    evidence = result.pop("evidence_attachment_ids_json", None)
    if evidence is not None:
        result["evidence_attachment_ids"] = evidence
    return result


def scope_clause(user: dict[str, Any], alias: str = "r") -> tuple[str, list[Any]]:
    scopes = require_active_scope(user)
    if unrestricted(user):
        return "", []
    areas = [int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")]
    if areas:
        return f"{alias}.area_id IN ({','.join(['%s'] * len(areas))})", areas
    if any(item.get("scope_type") == "personal" for item in scopes):
        return f"{alias}.created_by=%s", [int(user["id"])]
    return "1=0", []


def require_scope(user: dict[str, Any], row: dict[str, Any]) -> None:
    scopes = require_active_scope(user)
    if unrestricted(user):
        return
    areas = {int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")}
    if int(row.get("area_id") or 0) in areas:
        return
    if any(item.get("scope_type") == "personal" for item in scopes) and not row.get("area_id") and int(row.get("created_by") or 0) == int(user["id"]):
        return
    raise DomainError("DATA_SCOPE_FORBIDDEN", "无权访问授权范围之外的成本记录", 403)


def validate_scope(cursor: Any, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    try:
        organization_id, farm_id = int(result["organization_id"]), int(result["farm_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainError("COST_SCOPE_REQUIRED", "必须指定企业和基地", 400) from exc
    cursor.execute("SELECT organization_id FROM farms WHERE id=%s AND status<>'archived'", (farm_id,))
    farm = cursor.fetchone()
    if not farm or int(farm["organization_id"]) != organization_id:
        raise DomainError("COST_SCOPE_INVALID", "企业与基地不匹配", 400)
    if result.get("area_id") is not None:
        cursor.execute("SELECT organization_id,farm_id FROM areas WHERE id=%s AND status<>'archived'", (result["area_id"],))
        area = cursor.fetchone()
        if not area or int(area["organization_id"]) != organization_id or int(area["farm_id"]) != farm_id:
            raise DomainError("COST_SCOPE_INVALID", "区域不属于指定企业和基地", 400)
    target_type, target_id = result.get("target_type"), result.get("target_id")
    if target_type == "farm":
        cursor.execute("SELECT organization_id,id AS farm_id,NULL AS area_id FROM farms WHERE id=%s AND status<>'archived'", (target_id,))
        target = cursor.fetchone()
    elif target_type in COST_TARGET_QUERIES:
        cursor.execute(COST_TARGET_QUERIES[str(target_type)], (target_id,))
        target = cursor.fetchone()
    else:
        target = None
    if target_type and (
        target is None
        or int(target["organization_id"]) != organization_id
        or int(target["farm_id"]) != farm_id
        or (result.get("area_id") is not None and target.get("area_id") is not None and int(target["area_id"]) != int(result["area_id"]))
    ):
        raise DomainError("COST_TARGET_SCOPE_INVALID", "成本归属对象不属于所选企业、基地或区域", 400)
    if target and result.get("area_id") is None and target.get("area_id") is not None:
        result["area_id"] = int(target["area_id"])
    require_scope(user, {**result, "created_by": user["id"]})
    return result


def require_evidence(cursor: Any, row: dict[str, Any], entity_type: str, evidence: list[int]) -> None:
    if not evidence:
        raise DomainError("EVIDENCE_REQUIRED", "最终确认前必须关联至少一份凭据", 422)
    validate_bound_evidence(cursor, organization_id=int(row["organization_id"]), entity_type=entity_type, entity_id=int(row["id"]), evidence_ids=evidence, invalid_status=422, invalid_message="凭据未绑定到当前成本记录")


def require_unlocked(cursor: Any, row: dict[str, Any], occurred_field: str = "occurred_on") -> None:
    cursor.execute(
        "SELECT id FROM cost_settlements WHERE organization_id=%s AND farm_id=%s AND status='confirmed' AND (area_id IS NULL OR area_id<=>%s) AND %s BETWEEN period_start AND period_end LIMIT 1",
        (row["organization_id"], row["farm_id"], row.get("area_id"), row[occurred_field]),
    )
    if cursor.fetchone():
        raise DomainError("COST_PERIOD_LOCKED", "该期间已确认结算，请先执行反结算", 409)


def page_result(items: list[dict[str, Any]], page: int, page_size: int, total: int) -> dict[str, Any]:
    return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}
