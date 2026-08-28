from __future__ import annotations

from decimal import Decimal
import json
from typing import Any
from backend.layers.common.security.data_scope import require_active_scope, unrestricted


def _scope(user: dict[str, Any], area_sql: str, creator_sql: str, farm_sql: str | None = None, organization_sql: str | None = None) -> tuple[str, list[int]]:
    scopes = require_active_scope(user)
    if unrestricted(user):
        return "", []
    terms: list[str] = []
    values: list[int] = []
    areas = sorted({int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")})
    farms = sorted({int(item["farm_id"]) for item in scopes if item.get("scope_type") == "farm" and item.get("farm_id")})
    organizations = sorted({int(item["organization_id"]) for item in scopes if item.get("scope_type") == "farm" and item.get("organization_id") and not item.get("farm_id")})
    if areas:
        terms.append(f"{area_sql} IN ({','.join(['%s'] * len(areas))})")
        values.extend(areas)
    if farms and farm_sql:
        terms.append(f"{farm_sql} IN ({','.join(['%s'] * len(farms))})")
        values.extend(farms)
    if organizations and organization_sql:
        terms.append(f"{organization_sql} IN ({','.join(['%s'] * len(organizations))})")
        values.extend(organizations)
    if terms:
        predicate = " AND (" + " OR ".join(terms) + ")"
        if any(item.get("scope_type") == "personal" for item in scopes):
            return predicate + f" AND {creator_sql}=%s", [*values, int(user["id"])]
        return predicate, values
    if any(item.get("scope_type") == "personal" for item in scopes):
        return f" AND {creator_sql}=%s", [int(user["id"])]
    return " AND 1=0", []


class CostDashboardRepository:
    @staticmethod
    def _warehouse_category() -> str:
        return """CASE
          WHEN LOWER(COALESCE(m.category,'')) LIKE '%%feed%%' OR m.category LIKE '%%饲料%%' OR m.name LIKE '%%饲料%%' THEN 'feed'
          WHEN LOWER(COALESCE(m.category,'')) REGEXP 'health|medicine|drug|disinfect' OR m.category REGEXP '动保|药|消毒' OR m.name REGEXP '动保|药|消毒' THEN 'health'
          ELSE 'other' END"""

    def warehouse_costs(self, connection: Any, *, period_start: Any, period_end: Any, user: dict[str, Any]) -> list[dict[str, Any]]:
        area = "COALESCE(p.area_id,d.area_id,w.area_id)"
        scope, values = _scope(user, area, "d.created_by", "COALESCE(p.farm_id,d.farm_id,w.farm_id)", "COALESCE(p.organization_id,d.organization_id,w.organization_id)")
        category = self._warehouse_category()
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {category} AS category_code,
                       -SUM(g.quantity_delta*COALESCE(NULLIF(g.unit_cost,0),l.unit_cost,0)) AS amount,
                       COUNT(g.id) AS confirmed_entry_count
                FROM inventory_ledger g
                JOIN warehouse_documents d ON d.id=g.source_id
                JOIN warehouses w ON w.id=g.warehouse_id
                JOIN materials m ON m.id=g.material_id
                JOIN inventory_lots l ON l.id=g.inventory_lot_id
                LEFT JOIN ponds p ON p.id=g.pond_id
                WHERE d.status='verified' AND d.document_type IN ('issue','return')
                  AND g.source_type IN ('issue','return','correction')
                  AND DATE(g.happened_at) BETWEEN %s AND %s{scope}
                  AND NOT EXISTS (SELECT 1 FROM cost_entries ce WHERE ce.source_type='warehouse_ledger'
                    AND CAST(JSON_UNQUOTE(JSON_EXTRACT(ce.source_detail_json,'$.inventory_ledger_id')) AS UNSIGNED)=g.id)
                GROUP BY category_code
                """,
                (period_start, period_end, *values),
            )
            return list(cursor.fetchall())

    def confirmed_entries(self, connection: Any, *, category_code: str, period_start: Any, period_end: Any, page: int, page_size: int, user: dict[str, Any], **_: Any) -> dict[str, Any]:
        cost_scope, cost_values = _scope(user, "ce.area_id", "ce.created_by", "ce.farm_id", "ce.organization_id")
        warehouse_scope, warehouse_values = _scope(user, "COALESCE(p.area_id,d.area_id,w.area_id)", "d.created_by", "COALESCE(p.farm_id,d.farm_id,w.farm_id)", "COALESCE(p.organization_id,d.organization_id,w.organization_id)")
        category = self._warehouse_category()
        cte = f"""
          WITH facts AS (
            SELECT ce.id,c.code AS category_code,c.name AS category_name,ce.amount,ce.occurred_on,
                   ce.period_start,ce.period_end,ce.status,ce.source_type,ce.source_ref,ce.source_detail_json
            FROM cost_entries ce JOIN cost_categories c ON c.id=ce.category_id
            WHERE c.code=%s AND ce.status='confirmed' AND ce.occurred_on BETWEEN %s AND %s{cost_scope}
            UNION ALL
            SELECT -CAST(g.id AS SIGNED),c.code,c.name,-g.quantity_delta*COALESCE(NULLIF(g.unit_cost,0),l.unit_cost,0),DATE(g.happened_at),
                   %s,%s,'confirmed',CONCAT('warehouse_',d.document_type),d.code,
                   JSON_OBJECT('inventory_ledger_id',g.id,'material_id',g.material_id,'inventory_lot_id',g.inventory_lot_id,
                     'purchase_order_id',(SELECT receipt.purchase_order_id FROM warehouse_documents receipt
                       WHERE receipt.inventory_lot_id=g.inventory_lot_id AND receipt.document_type='receipt'
                         AND receipt.status='verified' AND receipt.purchase_order_id IS NOT NULL ORDER BY receipt.id LIMIT 1))
            FROM inventory_ledger g
            JOIN warehouse_documents d ON d.id=g.source_id
            JOIN warehouses w ON w.id=g.warehouse_id
            JOIN materials m ON m.id=g.material_id
            JOIN inventory_lots l ON l.id=g.inventory_lot_id
            JOIN cost_categories c ON c.code={category}
            LEFT JOIN ponds p ON p.id=g.pond_id
            WHERE c.code=%s AND d.status='verified' AND d.document_type IN ('issue','return')
              AND g.source_type IN ('issue','return','correction')
              AND DATE(g.happened_at) BETWEEN %s AND %s{warehouse_scope}
              AND NOT EXISTS (SELECT 1 FROM cost_entries ce WHERE ce.source_type='warehouse_ledger'
                AND CAST(JSON_UNQUOTE(JSON_EXTRACT(ce.source_detail_json,'$.inventory_ledger_id')) AS UNSIGNED)=g.id)
          )
        """
        params = (
            category_code, period_start, period_end, *cost_values,
            period_start, period_end, category_code, period_start, period_end, *warehouse_values,
        )
        page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
        with connection.cursor() as cursor:
            cursor.execute(f"{cte} SELECT COUNT(*) AS total FROM facts", params)
            total = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(f"{cte} SELECT * FROM facts ORDER BY occurred_on DESC,id DESC LIMIT %s OFFSET %s", (*params, page_size, (page - 1) * page_size))
            items = list(cursor.fetchall())
        for item in items:
            if isinstance(item.get("source_detail_json"), str):
                item["source_detail_json"] = json.loads(item["source_detail_json"])
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}

    def facts(self, connection: Any, *, period_start: Any, period_end: Any, user: dict[str, Any]) -> dict[str, Any]:
        cost_scope, cost_values = _scope(user, "ce.area_id", "ce.created_by", "ce.farm_id", "ce.organization_id")
        purchase_scope, purchase_values = _scope(user, "COALESCE(o.area_id,d.area_id,w.area_id)", "d.created_by", "COALESCE(o.farm_id,d.farm_id,w.farm_id)", "COALESCE(o.organization_id,d.organization_id,w.organization_id)")
        production_scope, production_values = _scope(user, "pd.area_id", "pd.created_by", "pd.farm_id", "pd.organization_id")
        sales_scope, sales_values = _scope(user, "o.area_id", "d.created_by", "o.farm_id", "o.organization_id")
        warehouse_scope, warehouse_values = _scope(user, "COALESCE(p.area_id,d.area_id,w.area_id)", "d.created_by", "COALESCE(p.farm_id,d.farm_id,w.farm_id)", "COALESCE(p.organization_id,d.organization_id,w.organization_id)")
        with connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT
                  SUM(CASE WHEN ce.source_type IN ('asset_depreciation','warehouse_ledger') THEN 0 ELSE 1 END) AS expense,
                  SUM(CASE WHEN ce.source_type='asset_depreciation' THEN 1 ELSE 0 END) AS asset
                FROM cost_entries ce
                WHERE ce.status='confirmed' AND ce.occurred_on BETWEEN %s AND %s{cost_scope}""",
                (period_start, period_end, *cost_values),
            )
            cost_counts = cursor.fetchone() or {}
            cursor.execute(
                f"""SELECT COUNT(DISTINCT payable.id) AS purchase
                FROM purchase_payables payable
                JOIN warehouse_documents d ON d.id=payable.source_receipt_id
                JOIN purchase_orders o ON o.id=payable.purchase_order_id
                JOIN warehouses w ON w.id=d.warehouse_id
                WHERE d.status='verified' AND DATE(d.happened_at) BETWEEN %s AND %s{purchase_scope}""",
                (period_start, period_end, *purchase_values),
            )
            purchase = cursor.fetchone() or {}
            cursor.execute(
                f"""SELECT COALESCE(-SUM(stock.weight_delta_kg)*2,0) AS output_weight_jin,
                       COUNT(DISTINCT pd.id) AS production
                FROM batch_stock_records stock
                JOIN production_documents pd ON pd.id=stock.source_id
                WHERE pd.document_type='harvest' AND pd.status='verified'
                  AND stock.source_type IN ('harvest','correction')
                  AND DATE(stock.happened_at) BETWEEN %s AND %s{production_scope}""",
                (period_start, period_end, *production_values),
            )
            production = cursor.fetchone() or {}
            cursor.execute(
                f"""SELECT COALESCE(SUM((CASE WHEN d.correction_of_id IS NULL THEN d.quantity ELSE d.quantity-parent.quantity END)*o.unit_price),0) AS income_amount,
                       COUNT(d.id) AS sales
                FROM sales_deliveries d
                LEFT JOIN sales_deliveries parent ON parent.id=d.correction_of_id
                JOIN sales_orders o ON o.id=d.sales_order_id
                WHERE d.status='verified' AND DATE(d.delivered_at) BETWEEN %s AND %s{sales_scope}""",
                (period_start, period_end, *sales_values),
            )
            sales = cursor.fetchone() or {}
            cursor.execute(
                f"""SELECT COUNT(g.id) AS warehouse
                FROM inventory_ledger g
                JOIN warehouse_documents d ON d.id=g.source_id
                JOIN warehouses w ON w.id=g.warehouse_id
                LEFT JOIN ponds p ON p.id=g.pond_id
                WHERE d.status='verified' AND d.document_type IN ('issue','return')
                  AND g.source_type IN ('issue','return','correction')
                  AND DATE(g.happened_at) BETWEEN %s AND %s{warehouse_scope}""",
                (period_start, period_end, *warehouse_values),
            )
            warehouse = cursor.fetchone() or {}
        return {
            "output_weight_jin": Decimal(str(production.get("output_weight_jin") or 0)),
            "income_amount": Decimal(str(sales.get("income_amount") or 0)),
            "source_fact_counts": {
                "warehouse": int(warehouse.get("warehouse") or 0),
                "purchase": int(purchase.get("purchase") or 0),
                "production": int(production.get("production") or 0),
                "expense": int(cost_counts.get("expense") or 0),
                "asset": int(cost_counts.get("asset") or 0),
                "sales": int(sales.get("sales") or 0),
            },
        }
