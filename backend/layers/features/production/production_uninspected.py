from __future__ import annotations

from datetime import date
from typing import Any

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.security.data_scope import scope_predicate


def list_uninspected_records(
    settings: Any,
    *,
    user: dict[str, Any],
    page: int,
    page_size: int,
    search: str | None,
    pond_id: Any,
    area_id: Any,
    uninspected_on: Any,
) -> dict[str, Any]:
    try:
        inspection_date = date.today() if str(uninspected_on).lower() == "today" else date.fromisoformat(str(uninspected_on))
    except (TypeError, ValueError) as exc:
        raise DomainError("PRODUCTION_DATE_INVALID", "巡检日期格式无效", 400) from exc
    scope, scope_values = scope_predicate(user)
    clauses = ["p.status = 'verified'"]
    values: list[Any] = [inspection_date]
    if scope:
        scoped = scope.replace("area_id", "p.area_id").replace("farm_id", "p.farm_id").replace("organization_id", "p.organization_id").replace("created_by", "p.created_by")
        clauses.append(scoped)
        values.extend(scope_values)
    if pond_id:
        clauses.append("p.id = %s"); values.append(pond_id)
    if area_id:
        clauses.append("p.area_id = %s"); values.append(area_id)
    if search:
        clauses.append("(p.code LIKE %s OR p.name LIKE %s)"); values.extend([f"%{search}%", f"%{search}%"])
    page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
    query = (
        "SELECT p.id,p.organization_id,p.farm_id,p.area_id,p.code,p.name,p.status,p.row_version,p.created_by,p.updated_by,p.created_at,p.updated_at "
        "FROM ponds p LEFT JOIN production_documents d ON d.pond_id=p.id AND d.document_type='daily_operation' AND d.status='verified' "
        "AND DATE(COALESCE(d.happened_at,d.created_at))=%s "
        f"WHERE {' AND '.join(clauses)} GROUP BY p.id,p.organization_id,p.farm_id,p.area_id,p.code,p.name,p.status,p.row_version,p.created_by,p.updated_by,p.created_at,p.updated_at "
        "HAVING COUNT(d.id)=0 ORDER BY p.updated_at DESC,p.id DESC LIMIT %s OFFSET %s"
    )
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(query, tuple(values + [page_size, (page - 1) * page_size]))
        items = [dict(row) for row in cursor.fetchall()]
    return {"items": items, "page": page, "page_size": page_size, "total": len(items), "has_next": False}
