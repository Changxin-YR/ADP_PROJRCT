from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError


def alert_references(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action == "threshold":
        try:
            threshold = Decimal(str(payload.get("safety_stock")))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise DomainError("WAREHOUSE_ALERT_THRESHOLD_REQUIRED", "调整阈值必须填写非负安全库存值", 400) from exc
        if not threshold.is_finite() or threshold < 0:
            raise DomainError("WAREHOUSE_ALERT_THRESHOLD_REQUIRED", "调整阈值必须填写非负安全库存值", 400)
        return {"safety_stock": threshold}
    if action == "replenish":
        # 兼容老行为（关联已存在的采购单）；新增缺口来源：直接关联请购单。
        message = "补货处理必须关联采购单或请购单"
        for candidate in ("purchase_order_id", "requisition_id"):
            raw = payload.get(candidate)
            if raw is None or str(raw).strip() == "":
                continue
            try:
                reference_id = int(raw)
            except (TypeError, ValueError) as exc:
                raise DomainError("WAREHOUSE_ALERT_REFERENCE_REQUIRED", message, 400) from exc
            if reference_id <= 0:
                raise DomainError("WAREHOUSE_ALERT_REFERENCE_REQUIRED", message, 400)
            return {candidate: reference_id}
        raise DomainError("WAREHOUSE_ALERT_REFERENCE_REQUIRED", message, 400)
    if action in {"transfer", "scrap", "recheck"}:
        field, message = "resolution_document_id", "该处理动作必须关联仓储单据"
    else:
        return {}
    field, message = "resolution_document_id", "该处理动作必须关联仓储单据"
    try:
        reference_id = int(payload.get(field))
    except (TypeError, ValueError) as exc:
        raise DomainError("WAREHOUSE_ALERT_REFERENCE_REQUIRED", message, 400) from exc
    if reference_id <= 0:
        raise DomainError("WAREHOUSE_ALERT_REFERENCE_REQUIRED", message, 400)
    return {field: reference_id}


def _fingerprint(row: dict[str, Any]) -> str:
    value = f"{row['alert_type']}|{row.get('current_quantity')}|{row.get('expiry_date')}|{row.get('safety_stock')}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _collapse_low_stock_alerts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare safety stock with warehouse/material totals, not individual lots."""
    totals: dict[tuple[int, int], Any] = {}
    thresholds: dict[tuple[int, int], Any] = {}
    for row in rows:
        if row.get("alert_type") != "low_stock":
            continue
        key = (int(row["warehouse_id"]), int(row["material_id"]))
        totals[key] = totals.get(key, 0) + row.get("current_quantity", 0)
        thresholds[key] = row.get("safety_stock", 0)
    emitted: set[tuple[int, int]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        if row.get("alert_type") != "low_stock":
            result.append(row)
            continue
        key = (int(row["warehouse_id"]), int(row["material_id"]))
        if totals[key] >= thresholds[key] or key in emitted:
            continue
        emitted.add(key)
        result.append({**row, "current_quantity": totals[key]})
    return result


def validate_requisition_reference(requisition: dict[str, Any] | None, alert: dict[str, Any]) -> None:
    """请购单必须存在、属于同企业、与预警物料一致且未取消。

    抽成纯函数以便脱离 MySQL 直接测试；handle_alert 负责取行并调用本函数。
    """
    if requisition is None:
        raise DomainError("WAREHOUSE_ALERT_REFERENCE_INVALID", "请购单不存在或不属于当前企业", 400)
    if int(requisition.get("material_id") or 0) != int(alert["material_id"]):
        raise DomainError("WAREHOUSE_ALERT_REFERENCE_INVALID", "请购单物料与预警物料不一致", 400)
    if requisition.get("warehouse_id") and int(requisition["warehouse_id"]) != int(alert["warehouse_id"]):
        raise DomainError("WAREHOUSE_ALERT_REFERENCE_INVALID", "请购单交货仓与预警仓库不一致", 400)
    if requisition.get("status") not in {"draft", "submitted", "approved", "converted"}:
        raise DomainError("WAREHOUSE_ALERT_REFERENCE_INVALID", "请购单已取消，不能关联该预警", 400)


def _suggested_quantity(row: dict[str, Any]) -> Any:
    """低库存预警的建议请购量 = 安全库存 - 当前可用量（不足则 0）。"""
    if row.get("alert_type") != "low_stock":
        return None
    try:
        gap = Decimal(str(row.get("safety_stock") or 0)) - Decimal(str(row.get("current_quantity") or 0))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return gap if gap > 0 else Decimal(0)


def list_alerts(store: Any, user: dict[str, Any]) -> list[dict[str, Any]]:
    where, values = store._area_where(user, "w"); scope = f"{where} AND" if where else "WHERE"
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT l.organization_id,w.id AS warehouse_id,l.id AS inventory_lot_id,m.id AS material_id,
                       m.name AS material_name,l.lot_no,w.name AS warehouse_name,m.safety_stock,l.expiry_date,
                       COALESCE(SUM(g.quantity_delta),0)-COALESCE((
                         SELECT SUM(CASE WHEN d.correction_of_id IS NULL THEN d.quantity ELSE d.quantity-COALESCE(parent.quantity,0) END) FROM warehouse_documents d
                         LEFT JOIN warehouse_documents parent ON parent.id=d.correction_of_id
                         WHERE d.document_type='scrap' AND d.status='submitted'
                           AND d.warehouse_id=w.id AND d.inventory_lot_id=l.id
                       ),0) AS current_quantity,
                       CASE WHEN l.expiry_date<CURRENT_DATE THEN 'expired'
                            WHEN l.expiry_date<=DATE_ADD(CURRENT_DATE,INTERVAL 30 DAY) THEN 'expiring'
                            ELSE 'low_stock' END AS alert_type,
                       CASE WHEN l.expiry_date<CURRENT_DATE OR COALESCE(SUM(g.quantity_delta),0)<=0 THEN 'high' ELSE 'medium' END AS severity
                FROM inventory_lots l JOIN materials m ON m.id=l.material_id
                JOIN inventory_ledger g ON g.inventory_lot_id=l.id JOIN warehouses w ON w.id=g.warehouse_id
                {scope} l.status IN ('available','expired')
                GROUP BY l.organization_id,w.id,l.id,m.id,m.name,m.safety_stock,l.lot_no,l.expiry_date,w.name
                HAVING current_quantity<m.safety_stock OR expiry_date<=DATE_ADD(CURRENT_DATE,INTERVAL 30 DAY)
                ORDER BY FIELD(severity,'high','medium'),l.expiry_date""",
            tuple(values),
        )
        rows = _collapse_low_stock_alerts(list(cursor.fetchall()))
        scope_sql, scope_values = store._area_where(user, "w")
        scope_predicate = f" AND {scope_sql[6:]}" if scope_sql else ""
        cursor.execute(
            f"""SELECT d.organization_id,d.warehouse_id,d.inventory_lot_id,d.material_id,m.name AS material_name,
                       l.lot_no,w.name AS warehouse_name,m.safety_stock,
                       COALESCE((SELECT SUM(g.quantity_delta) FROM inventory_ledger g
                                 WHERE g.warehouse_id=d.warehouse_id AND g.material_id=d.material_id
                                   AND g.inventory_lot_id=d.inventory_lot_id
                                   AND NOT (g.source_type='stocktake' AND g.source_id=d.id)),0) AS book_quantity,
                       d.quantity AS actual_quantity,d.quantity-COALESCE((SELECT SUM(g.quantity_delta) FROM inventory_ledger g
                                 WHERE g.warehouse_id=d.warehouse_id AND g.material_id=d.material_id
                                   AND g.inventory_lot_id=d.inventory_lot_id
                                   AND NOT (g.source_type='stocktake' AND g.source_id=d.id)),0) AS difference_quantity,
                       'stocktake_difference' AS alert_type,'medium' AS severity
                FROM warehouse_documents d JOIN warehouses w ON w.id=d.warehouse_id
                JOIN materials m ON m.id=d.material_id JOIN inventory_lots l ON l.id=d.inventory_lot_id
                WHERE d.document_type='stocktake' AND d.status='verified'{scope_predicate}
                  AND d.quantity<>COALESCE((SELECT SUM(g.quantity_delta) FROM inventory_ledger g
                                 WHERE g.warehouse_id=d.warehouse_id AND g.material_id=d.material_id
                                   AND g.inventory_lot_id=d.inventory_lot_id
                                   AND NOT (g.source_type='stocktake' AND g.source_id=d.id)),0)
                ORDER BY d.id DESC""",
            tuple(scope_values),
        )
        rows.extend(list(cursor.fetchall()))
        cursor.execute(
            f"""SELECT l.organization_id,w.id AS warehouse_id,l.id AS inventory_lot_id,m.id AS material_id,
                       m.name AS material_name,l.lot_no,w.name AS warehouse_name,m.safety_stock,
                       COALESCE(SUM(g.quantity_delta),0) AS current_quantity,
                       MAX(g.happened_at) AS last_activity,'inactive' AS alert_type,'low' AS severity
                FROM inventory_lots l JOIN materials m ON m.id=l.material_id
                JOIN inventory_ledger g ON g.inventory_lot_id=l.id JOIN warehouses w ON w.id=g.warehouse_id
                {scope_sql if scope_sql else ''}{' AND' if scope_sql else 'WHERE'} l.status='available'
                GROUP BY l.organization_id,w.id,l.id,m.id,m.name,m.safety_stock,l.lot_no,w.name
                HAVING current_quantity>0 AND (last_activity IS NULL OR last_activity<DATE_SUB(CURRENT_DATE,INTERVAL 90 DAY))""",
            tuple(scope_values),
        )
        rows.extend(list(cursor.fetchall()))
        for row in rows:
            row["alert_key"] = f"{row['warehouse_id']}:{row['inventory_lot_id']}:{row['alert_type']}"
            row["condition_fingerprint"] = _fingerprint(row)
            suggestion = _suggested_quantity(row)
            if suggestion is not None:
                row["suggested_quantity"] = suggestion
        keys = [row["alert_key"] for row in rows]
        actions: dict[str, dict[str, Any]] = {}
        if keys:
            cursor.execute(
                f"SELECT * FROM warehouse_alert_actions WHERE alert_key IN ({','.join(['%s'] * len(keys))})",
                tuple(keys),
            )
            actions = {item["alert_key"]: item for item in cursor.fetchall()}
    for row in rows:
        action = actions.get(row["alert_key"])
        same = action and action["condition_fingerprint"] == row["condition_fingerprint"]
        row.update({
            "status": action["status"] if same else "pending",
            "action_code": action.get("action_code") if same else None,
            "resolution_note": action.get("resolution_note") if same else None,
            "handled_by": action.get("handled_by") if same else None,
            "handled_at": action.get("handled_at") if same else None,
            "allowed_actions": [] if same else ["handle"],
        })
    return rows


def handle_alert(
    store: Any,
    user: dict[str, Any],
    alert_key: str,
    *,
    action_code: str,
    resolution_note: str,
    user_id: int,
    purchase_order_id: int | None = None,
    resolution_document_id: int | None = None,
    safety_stock: Any = None,
    requisition_id: int | None = None,
) -> dict[str, Any]:
    alert = next((item for item in list_alerts(store, user) if item["alert_key"] == alert_key), None)
    if alert is None:
        raise DomainError("WAREHOUSE_ALERT_NOT_FOUND", "预警不存在、已解除或不在授权范围", 404)
    if action_code == "threshold" and alert.get("alert_type") != "low_stock":
        raise DomainError("WAREHOUSE_ALERT_ACTION_INVALID", "只有低库存预警可以调整安全库存阈值", 409)
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        reference_id = None
        reference_type = None
        if action_code == "replenish":
            if requisition_id is not None:
                # 库存预警 -> 请购单：把缺料信号和请购发起连起来。
                cursor.execute(
                    "SELECT id,status,material_id,warehouse_id FROM purchase_requisitions "
                    "WHERE id=%s AND organization_id=%s",
                    (requisition_id, alert["organization_id"]),
                )
                reference = cursor.fetchone()
                validate_requisition_reference(reference, alert)
                reference_id = int(reference["id"])
                reference_type = "requisition"
            else:
                cursor.execute(
                    "SELECT id,status FROM purchase_orders WHERE id=%s AND organization_id=%s AND material_id=%s AND warehouse_id=%s",
                    (purchase_order_id, alert["organization_id"], alert["material_id"], alert["warehouse_id"]),
                )
                reference = cursor.fetchone()
                if reference is None or reference["status"] not in {"submitted", "approved", "partially_received"}:
                    raise DomainError("WAREHOUSE_ALERT_REFERENCE_INVALID", "采购单不存在、未提交或与当前预警不匹配", 409)
                reference_id = int(reference["id"])
                reference_type = "purchase_order"
        elif action_code in {"transfer", "scrap", "recheck"}:
            document_type = {"transfer": "transfer", "scrap": "scrap", "recheck": "stocktake"}[action_code]
            if action_code == "transfer":
                cursor.execute(
                    "SELECT id,status FROM warehouse_documents "
                    "WHERE id=%s AND organization_id=%s AND document_type='transfer' "
                    "AND target_warehouse_id=%s AND warehouse_id<>target_warehouse_id AND material_id=%s",
                    (resolution_document_id, alert["organization_id"], alert["warehouse_id"], alert["material_id"]),
                )
            elif action_code == "scrap":
                cursor.execute(
                    "SELECT id,status FROM warehouse_documents WHERE id=%s AND organization_id=%s "
                    "AND document_type='scrap' AND warehouse_id=%s AND material_id=%s AND inventory_lot_id=%s",
                    (resolution_document_id, alert["organization_id"], alert["warehouse_id"], alert["material_id"], alert["inventory_lot_id"]),
                )
            else:
                cursor.execute(
                    "SELECT id,status FROM warehouse_documents WHERE id=%s AND organization_id=%s "
                    "AND document_type='stocktake' AND warehouse_id=%s AND material_id=%s AND inventory_lot_id=%s",
                    (resolution_document_id, alert["organization_id"], alert["warehouse_id"], alert["material_id"], alert["inventory_lot_id"]),
                )
            reference = cursor.fetchone()
            if reference is None or reference["status"] not in {"submitted", "in_transit", "verified"}:
                raise DomainError("WAREHOUSE_ALERT_REFERENCE_INVALID", "仓储单据不存在、未提交或与当前预警不匹配", 409)
            reference_id = int(reference["id"])
        elif action_code == "threshold":
            cursor.execute("UPDATE materials SET safety_stock=%s WHERE id=%s AND organization_id=%s AND status='verified'", (safety_stock, alert["material_id"], alert["organization_id"]))
            if cursor.rowcount != 1:
                raise DomainError("WAREHOUSE_ALERT_REFERENCE_INVALID", "物料不存在或不属于当前企业", 409)
        cursor.execute(
            """INSERT INTO warehouse_alert_actions
               (organization_id,alert_key,warehouse_id,material_id,inventory_lot_id,alert_type,condition_fingerprint,status,action_code,resolution_note,resolution_reference_type,resolution_reference_id,handled_by,handled_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'handled',%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
               ON DUPLICATE KEY UPDATE condition_fingerprint=VALUES(condition_fingerprint),status='handled',action_code=VALUES(action_code),resolution_note=VALUES(resolution_note),resolution_reference_type=VALUES(resolution_reference_type),resolution_reference_id=VALUES(resolution_reference_id),handled_by=VALUES(handled_by),handled_at=CURRENT_TIMESTAMP""",
            (alert["organization_id"], alert_key, alert["warehouse_id"], alert["material_id"], alert["inventory_lot_id"],
             alert["alert_type"], alert["condition_fingerprint"], action_code, resolution_note,
             reference_type or ("warehouse_document" if action_code in {"transfer", "scrap", "recheck"} else None),
             reference_id, user_id),
        )
        result = {**alert, "status": "handled", "action_code": action_code, "resolution_note": resolution_note, "handled_by": user_id, "allowed_actions": []}
        if reference_id is not None:
            result["resolution_reference_id"] = reference_id
        if action_code == "threshold":
            result["safety_stock"] = safety_stock
        store._audit(connection, user_id, "handle", "alerts", int(alert["inventory_lot_id"]), before=alert, after=result)
        return result
