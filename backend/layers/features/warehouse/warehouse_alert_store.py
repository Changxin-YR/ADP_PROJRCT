from __future__ import annotations

import hashlib
from typing import Any

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError


def _fingerprint(row: dict[str, Any]) -> str:
    value = f"{row['alert_type']}|{row.get('current_quantity')}|{row.get('expiry_date')}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def list_alerts(store: Any, user: dict[str, Any]) -> list[dict[str, Any]]:
    where, values = store._area_where(user, "w"); scope = f"{where} AND" if where else "WHERE"
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT l.organization_id,w.id AS warehouse_id,l.id AS inventory_lot_id,m.id AS material_id,
                       m.name AS material_name,l.lot_no,w.name AS warehouse_name,m.safety_stock,l.expiry_date,
                       COALESCE(SUM(g.quantity_delta),0)-COALESCE((
                         SELECT SUM(d.quantity) FROM warehouse_documents d
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
        rows = list(cursor.fetchall())
        for row in rows:
            row["alert_key"] = f"{row['warehouse_id']}:{row['inventory_lot_id']}:{row['alert_type']}"
            row["condition_fingerprint"] = _fingerprint(row)
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


def handle_alert(store: Any, user: dict[str, Any], alert_key: str, *, action_code: str, resolution_note: str, user_id: int) -> dict[str, Any]:
    alert = next((item for item in list_alerts(store, user) if item["alert_key"] == alert_key), None)
    if alert is None:
        raise DomainError("WAREHOUSE_ALERT_NOT_FOUND", "预警不存在、已解除或不在授权范围", 404)
    with get_connection(store.settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO warehouse_alert_actions
               (organization_id,alert_key,warehouse_id,material_id,inventory_lot_id,alert_type,condition_fingerprint,status,action_code,resolution_note,handled_by,handled_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'handled',%s,%s,%s,CURRENT_TIMESTAMP)
               ON DUPLICATE KEY UPDATE condition_fingerprint=VALUES(condition_fingerprint),status='handled',action_code=VALUES(action_code),resolution_note=VALUES(resolution_note),handled_by=VALUES(handled_by),handled_at=CURRENT_TIMESTAMP""",
            (alert["organization_id"], alert_key, alert["warehouse_id"], alert["material_id"], alert["inventory_lot_id"],
             alert["alert_type"], alert["condition_fingerprint"], action_code, resolution_note, user_id),
        )
        result = {**alert, "status": "handled", "action_code": action_code, "resolution_note": resolution_note, "handled_by": user_id, "allowed_actions": []}
        store._audit(connection, user_id, "handle", "alerts", int(alert["inventory_lot_id"]), before=alert, after=result)
        return result
