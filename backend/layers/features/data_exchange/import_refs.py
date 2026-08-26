"""导入器共享的引用解析与范围辅助（被 importers / import_validation 复用）。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def _int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        text = str(value).strip()
        parts = text.split(".")
        if not parts[0].isdigit() or len(parts) > 2 or (len(parts) == 2 and (not parts[1] or set(parts[1]) != {"0"})):
            return None
        number = int(parts[0])
        return number if number > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal:
    from backend.layers.common.governance.lifecycle import DomainError

    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DomainError("FIELD_INVALID", "金额或数量必须是有效数字", 400) from exc
    if not result.is_finite():
        raise DomainError("FIELD_INVALID", "金额或数量必须是有效数字", 400)
    return result


def _fetch(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cursor.execute(sql, params)
    return cursor.fetchone()


def _pond(cursor: Any, organization_id: int, pond_id: int | None) -> dict[str, Any]:
    row = _fetch(cursor, "SELECT organization_id,farm_id,area_id FROM ponds WHERE id=%s", (pond_id,)) if pond_id else None
    if row is None or int(row["organization_id"]) != organization_id:
        from backend.layers.common.governance.lifecycle import DomainError

        raise DomainError("POND_NOT_FOUND", "塘口不存在或不属于当前企业", 400)
    return row


def _batch(cursor: Any, organization_id: int, batch_id: int | None) -> dict[str, Any]:
    row = _fetch(cursor, "SELECT id,organization_id,farm_id,area_id,pond_id,species FROM production_batches WHERE id=%s", (batch_id,)) if batch_id else None
    if row is None or int(row["organization_id"]) != organization_id:
        from backend.layers.common.governance.lifecycle import DomainError

        raise DomainError("BATCH_NOT_FOUND", "批次不存在或不属于当前企业", 400)
    return row


def _warehouse(cursor: Any, organization_id: int, warehouse_id: int | None) -> dict[str, Any]:
    row = _fetch(cursor, "SELECT organization_id,farm_id,area_id FROM warehouses WHERE id=%s AND status='active'", (warehouse_id,)) if warehouse_id else None
    if row is None or int(row["organization_id"]) != organization_id:
        from backend.layers.common.governance.lifecycle import DomainError

        raise DomainError("WAREHOUSE_NOT_FOUND", "仓库不存在、已停用或不属于当前企业", 400)
    return row


def _first_pond(cursor: Any, organization_id: int) -> int | None:
    row = _fetch(cursor, "SELECT id FROM ponds WHERE organization_id=%s ORDER BY id LIMIT 1", (organization_id,))
    return int(row["id"]) if row else None


def _first_warehouse(cursor: Any, organization_id: int) -> int | None:
    row = _fetch(cursor, "SELECT id FROM warehouses WHERE organization_id=%s AND status='active' ORDER BY id LIMIT 1", (organization_id,))
    return int(row["id"]) if row else None


def _first_farm(cursor: Any, organization_id: int) -> int | None:
    row = _fetch(cursor, "SELECT id FROM farms WHERE organization_id=%s ORDER BY id LIMIT 1", (organization_id,))
    return int(row["id"]) if row else None


def _category(cursor: Any, code: str) -> int | None:
    row = _fetch(cursor, "SELECT id FROM cost_categories WHERE code=%s AND status='active'", (code,)) if code else None
    return int(row["id"]) if row else None


def _first_category(cursor: Any) -> int | None:
    row = _fetch(cursor, "SELECT id FROM cost_categories WHERE status='active' ORDER BY sort_order,id LIMIT 1", ())
    return int(row["id"]) if row else None


def enforce_area_scope(user: dict[str, Any], area_id: int | None) -> None:
    """导入确认写入时，区域范围用户只能写入授权区域内的记录。"""
    from backend.layers.common.governance.lifecycle import DomainError

    if area_id is None:
        return  # 组织级记录（如整场费用）不受区域写入范围约束
    from backend.layers.common.security.data_scope import require_active_scope, unrestricted
    scopes = require_active_scope(user)
    if unrestricted(user):
        return
    if any(item.get("scope_type") == "personal" for item in scopes):
        raise DomainError("DATA_SCOPE_FORBIDDEN", "仅本人数据范围不能通过批量导入写入区域业务", 403)
    allowed = {int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")}
    if int(area_id) not in allowed:
        raise DomainError("DATA_SCOPE_FORBIDDEN", "无权写入授权范围之外的数据", 403)


def scoped_area_defaults(cursor: Any, user: dict[str, Any], organization_id: int) -> dict[str, int]:
    """无区域列模板在单一区域账号下自动落入授权区域，避免生成不可见的组织级草稿。"""
    from backend.layers.common.governance.lifecycle import DomainError

    from backend.layers.common.security.data_scope import require_active_scope, unrestricted
    scopes = require_active_scope(user)
    if unrestricted(user):
        return {}
    if any(item.get("scope_type") == "personal" for item in scopes):
        raise DomainError("DATA_SCOPE_FORBIDDEN", "仅本人数据范围不能通过批量导入推断区域", 403)
    areas = {
        int(item["area_id"])
        for item in scopes
        if item.get("scope_type") == "area" and item.get("area_id")
    }
    if len(areas) != 1:
        raise DomainError("IMPORT_AREA_REQUIRED", "当前账号有多个授权区域，模板必须明确提供区域", 400)
    area_id = next(iter(areas))
    area = _fetch(cursor, "SELECT organization_id,farm_id FROM areas WHERE id=%s", (area_id,))
    if area is None or int(area["organization_id"]) != organization_id:
        raise DomainError("DATA_SCOPE_FORBIDDEN", "授权区域不存在或不属于当前企业", 403)
    return {"farm_id": int(area["farm_id"]), "area_id": area_id}
