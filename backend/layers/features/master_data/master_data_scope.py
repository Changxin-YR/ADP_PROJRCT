from __future__ import annotations

from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def _exists(cursor: Any, sql: str, params: tuple[Any, ...]) -> bool:
    cursor.execute(sql, params)
    return cursor.fetchone() is not None


def _assert_no_area_cycle(cursor: Any, parent_id: int, record_id: int | None) -> None:
    seen: set[int] = set()
    current = parent_id
    while current:
        if current in seen or current == int(record_id or 0):
            raise DomainError("MASTER_SCOPE_MISMATCH", "上级区域不能形成层级循环", 400)
        seen.add(current)
        cursor.execute("SELECT parent_id FROM areas WHERE id=%s", (current,))
        row = cursor.fetchone()
        current = int(row.get("parent_id") or 0) if row else 0


def validate_master_hierarchy(
    cursor: Any,
    resource: str,
    payload: dict[str, Any],
    *,
    record_id: int | None = None,
) -> None:
    """Prevent independently valid foreign keys from forming cross-scope records."""
    try:
        organization_id = int(payload["organization_id"])
        farm_id = int(payload["farm_id"]) if payload.get("farm_id") else None
        area_id = int(payload["area_id"]) if payload.get("area_id") else None
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainError("MASTER_SCOPE_MISMATCH", "企业、基地或区域归属无效", 400) from exc
    if not _exists(cursor, "SELECT id FROM organizations WHERE id=%s AND status='active'", (organization_id,)):
        raise DomainError("MASTER_SCOPE_MISMATCH", "企业不存在", 400)
    if farm_id and not _exists(cursor, "SELECT id FROM farms WHERE id=%s AND organization_id=%s AND status='verified'", (farm_id, organization_id)):
        raise DomainError("MASTER_SCOPE_MISMATCH", "基地不属于所选企业", 400)
    if area_id and not _exists(
        cursor,
        "SELECT id FROM areas WHERE id=%s AND organization_id=%s AND farm_id=%s AND status='verified'",
        (area_id, organization_id, farm_id),
    ):
        raise DomainError("MASTER_SCOPE_MISMATCH", "区域不属于所选企业和基地", 400)
    parent_id = payload.get("parent_id") if resource == "areas" else None
    if parent_id and (int(parent_id) == int(record_id or 0) or not _exists(
        cursor,
        "SELECT id FROM areas WHERE id=%s AND organization_id=%s AND farm_id=%s AND status='verified'",
        (int(parent_id), organization_id, farm_id),
    )):
        raise DomainError("MASTER_SCOPE_MISMATCH", "上级区域必须属于同一企业和基地且不能选择自身", 400)
    if parent_id:
        _assert_no_area_cycle(cursor, int(parent_id), record_id)
    group_id = payload.get("pond_group_id") if resource == "ponds" else None
    if group_id and not _exists(
        cursor,
        "SELECT id FROM pond_groups WHERE id=%s AND organization_id=%s AND farm_id=%s AND area_id=%s AND status='verified'",
        (int(group_id), organization_id, farm_id, area_id),
    ):
        raise DomainError("MASTER_SCOPE_MISMATCH", "塘组不属于所选企业、基地和区域", 400)
    supplier_id = payload.get("default_supplier_id") if resource == "materials" else None
    if supplier_id and not _exists(
        cursor,
        "SELECT id FROM business_partners WHERE id=%s AND organization_id=%s AND partner_type='supplier' AND status='verified'",
        (int(supplier_id), organization_id),
    ):
        raise DomainError("MASTER_SCOPE_MISMATCH", "默认供应商不属于所选企业", 400)
