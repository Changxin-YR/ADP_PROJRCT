from __future__ import annotations

from typing import Any

from backend.layers.features.data_exchange.import_refs import _fetch, _int


def _error(row_number: int, field: str, area_id: int | None) -> dict[str, Any]:
    return {
        "row": row_number,
        "column": field,
        "message": "关联业务对象不在当前账号授权区域内",
        "value": area_id,
    }


def _source_area(cursor: Any, organization_id: int, template_code: str, row: dict[str, Any]) -> tuple[str, int | None]:
    if template_code == "ponds":
        return "area_id", _int(row.get("area_id"))
    if template_code in {"batches", "feed-plans", "feed-tasks", "feed-logs", "daily-operations"} and _int(row.get("pond_id")):
        source = _fetch(cursor, "SELECT area_id FROM ponds WHERE id=%s AND organization_id=%s", (_int(row.get("pond_id")), organization_id))
        return "pond_id", int(source["area_id"]) if source else None
    if template_code in {"stocking", "samplings", "transfers", "losses", "harvests", "sales-orders"}:
        source = _fetch(cursor, "SELECT area_id FROM production_batches WHERE id=%s AND organization_id=%s", (_int(row.get("batch_id")), organization_id))
        return "batch_id", int(source["area_id"]) if source else None
    if template_code in {"receipts", "issues", "warehouse-transfers", "returns", "stocktakes", "scraps", "purchase-orders"}:
        source = _fetch(cursor, "SELECT area_id FROM warehouses WHERE id=%s AND organization_id=%s", (_int(row.get("warehouse_id")), organization_id))
        return "warehouse_id", int(source["area_id"]) if source and source.get("area_id") else None
    if template_code == "payments":
        source = _fetch(cursor, "SELECT o.area_id FROM purchase_payables p JOIN purchase_orders o ON o.id=p.purchase_order_id WHERE p.id=%s AND p.organization_id=%s", (_int(row.get("payable_id")), organization_id))
        return "payable_id", int(source["area_id"]) if source and source.get("area_id") else None
    if template_code == "customer-receipts":
        source = _fetch(cursor, "SELECT o.area_id FROM sales_receivables r JOIN sales_orders o ON o.id=r.sales_order_id WHERE r.id=%s AND r.organization_id=%s", (_int(row.get("receivable_id")), organization_id))
        return "receivable_id", int(source["area_id"]) if source and source.get("area_id") else None
    if template_code == "cost-adjustments":
        source = _fetch(cursor, "SELECT area_id FROM cost_entries WHERE id=%s AND organization_id=%s", (_int(row.get("source_id")), organization_id))
        return "source_id", int(source["area_id"]) if source and source.get("area_id") else None
    return "area_id", None


def validate_import_scope(
    cursor: Any,
    user: dict[str, Any],
    organization_id: int,
    template_code: str,
    rows: list[dict[str, Any]],
    row_numbers: list[int],
) -> list[dict[str, Any]]:
    scopes = user.get("data_scopes") or []
    if not scopes or any(item.get("scope_type") in {"farm", "personal"} for item in scopes):
        return []
    allowed = {
        int(item["area_id"])
        for item in scopes
        if item.get("scope_type") == "area" and item.get("area_id")
    }
    errors: list[dict[str, Any]] = []
    implicit_area_templates = {"materials", "suppliers", "customers", "business-settings", "expenses", "assets", "leases"}
    if template_code in implicit_area_templates and len(allowed) != 1:
        return [
            {
                "row": number,
                "column": "area_id",
                "message": "当前账号有多个授权区域，该模板必须明确提供区域",
                "value": None,
            }
            for number in row_numbers
        ]
    for row, number in zip(rows, row_numbers):
        field, area_id = _source_area(cursor, organization_id, template_code, row)
        if area_id is not None and area_id not in allowed:
            errors.append(_error(number, field, area_id))
    return errors
