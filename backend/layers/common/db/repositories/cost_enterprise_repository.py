from __future__ import annotations

import json
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.security.data_scope import require_active_scope, row_in_scope, scope_predicate, unrestricted
from backend.layers.common.files.evidence import validate_bound_evidence


COST_TARGET_QUERIES = {
    "area": "SELECT organization_id,farm_id,id AS area_id FROM areas WHERE id=%s AND status='verified'",
    "group": "SELECT organization_id,farm_id,area_id FROM pond_groups WHERE id=%s AND status='verified'",
    "pond": "SELECT organization_id,farm_id,area_id FROM ponds WHERE id=%s AND status='verified'",
    "batch": "SELECT organization_id,farm_id,area_id FROM production_batches WHERE id=%s AND status='verified'",
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
    return scope_predicate(user, alias)


def require_scope(user: dict[str, Any], row: dict[str, Any]) -> None:
    if row_in_scope(user, row):
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


DIRECT_STOCK_CATEGORY_CODES = {"feed", "seed", "health"}
STOCK_OVERRIDE_SOURCE_TYPES = {"manual_feed_offset", "manual_feed_direct"}


def resolve_entry_scope(cursor: Any, row: dict[str, Any]) -> dict[str, Any]:
    """补全 organization_id/farm_id/area_id：旧成本入口不携带企业与基地，按归属对象回查。"""
    result = {"organization_id": None, "farm_id": None, "area_id": None, **row}
    if result.get("organization_id") is not None and result.get("farm_id") is not None:
        return result
    query = COST_TARGET_QUERIES.get(str(result.get("target_type") or ""))
    if not query or result.get("target_id") in (None, ""):
        return result
    cursor.execute(query, (result["target_id"],))
    target = cursor.fetchone()
    if not target:
        return result
    for field in ("organization_id", "farm_id", "area_id"):
        if result.get(field) is None and target.get(field) is not None:
            result[field] = int(target[field])
    return result


def require_source_not_duplicated(cursor: Any, row: dict[str, Any], *, category_code: str | None = None) -> None:
    """库存自动成本防重复归集：同一塘口或批次、期间重叠且已由库存自动归集时，拒绝手工费用再次归集。"""
    source_type = str(row.get("source_type") or "").strip()
    if source_type in STOCK_OVERRIDE_SOURCE_TYPES:
        # 财务明确选择“库存已自动归集但仍需登记”的口径时放行，由人工对账负责不重复计入。
        return
    if source_type != "manual_expense":
        return
    code = str(category_code or row.get("category_code") or "").strip()
    target_type, target_id = row.get("target_type"), row.get("target_id")
    period_start, period_end = row.get("period_start"), row.get("period_end")
    if code not in DIRECT_STOCK_CATEGORY_CODES or target_type not in {"pond", "batch"} or not target_id:
        return
    if not period_start or not period_end:
        return
    resolved = resolve_entry_scope(cursor, row)
    cursor.execute(
        """
        SELECT ce.id
        FROM cost_entries AS ce
        WHERE ce.source_type='warehouse_ledger' AND ce.status='confirmed'
          AND ce.target_type=%s AND ce.target_id=%s
          AND ce.organization_id<=>%s AND ce.farm_id<=>%s
          AND ce.period_start<=%s AND ce.period_end>=%s
        LIMIT 1
        """,
        (target_type, int(target_id), resolved.get("organization_id"), resolved.get("farm_id"), period_end, period_start),
    )
    if cursor.fetchone():
        raise DomainError(
            "COST_SOURCE_DUPLICATED",
            "该塘口/批次在此期间已有库存自动归集的同类成本，请改用直接采购/其他费用类别，或先冲销自动成本",
            409,
        )


def require_entry_open(connection: Any, row: dict[str, Any], *, category_code: str | None = None, occurred_field: str = "occurred_on") -> dict[str, Any]:
    """旧成本入口复用的公共前置校验：期间已确认结算即锁定，且不得与库存自动成本重复归集。"""
    with connection.cursor() as cursor:
        resolved = resolve_entry_scope(cursor, row)
        if resolved.get(occurred_field) is not None:
            require_unlocked(cursor, resolved, occurred_field)
        require_source_not_duplicated(cursor, resolved, category_code=category_code or resolved.get("category_code"))
    return resolved


def page_result(items: list[dict[str, Any]], page: int, page_size: int, total: int) -> dict[str, Any]:
    return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}
