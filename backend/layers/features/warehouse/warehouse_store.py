from __future__ import annotations

import json
from typing import Any

import pymysql

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.revisions import build_revision, save_revision
from backend.layers.common.governance.work_item_notifications import notify_work_item_created
from backend.layers.common.files.evidence import validate_bound_evidence
from backend.layers.features.warehouse.warehouse_ledger_store import WarehouseLedgerPoster
from backend.layers.features.warehouse.warehouse_alert_store import handle_alert, list_alerts
from backend.layers.features.warehouse.warehouse_service import FIELDS
from backend.layers.features.warehouse.warehouse_transfer_store import cancel_transfer, dispatch_transfer, receive_transfer


DOC_TYPES = {
    "receipts": "receipt", "issue-requests": "issue_request", "issues": "issue",
    "returns": "return", "transfers": "transfer", "stocktakes": "stocktake", "scraps": "scrap",
}


class MySqlWarehouseStore:
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.audit = AuditLogger()
        self.poster = WarehouseLedgerPoster()

    @staticmethod
    def _decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        result = dict(row)
        value = result.pop("evidence_attachment_ids_json", None)
        if isinstance(value, str):
            value = json.loads(value)
        if value is not None:
            result["evidence_attachment_ids"] = value
        return result

    @staticmethod
    def _scope(user: dict[str, Any]) -> tuple[str, list[Any]]:
        scopes = user.get("data_scopes") or []
        if not scopes or any(item.get("scope_type") == "farm" for item in scopes):
            return "", []
        areas = [int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")]
        return (f"d.area_id IN ({','.join(['%s'] * len(areas))})", areas) if areas else ("d.created_by=%s", [int(user["id"])])

    def list_records(self, resource: str, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, **_: Any) -> dict[str, Any]:
        clauses, values = ["d.document_type=%s"], [DOC_TYPES[resource]]
        scope, scoped = self._scope(user)
        if scope:
            clauses.append(scope); values.extend(scoped)
        if status:
            clauses.append("d.status=%s"); values.append(status)
        if search:
            clauses.append("(d.code LIKE %s OR d.name LIKE %s OR m.name LIKE %s)"); values.extend([f"%{search}%"] * 3)
        where = " AND ".join(clauses); page = max(1, int(page)); page_size = min(100, max(1, int(page_size)))
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM warehouse_documents d JOIN materials m ON m.id=d.material_id WHERE {where}", tuple(values))
            total = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(
                f"SELECT d.*,m.name AS material_name,w.name AS warehouse_name,tw.name AS target_warehouse_name,l.lot_no AS inventory_lot_no FROM warehouse_documents d JOIN materials m ON m.id=d.material_id JOIN warehouses w ON w.id=d.warehouse_id LEFT JOIN warehouses tw ON tw.id=d.target_warehouse_id LEFT JOIN inventory_lots l ON l.id=d.inventory_lot_id WHERE {where} ORDER BY d.updated_at DESC,d.id DESC LIMIT %s OFFSET %s",
                tuple(values + [page_size, (page - 1) * page_size]),
            )
            items = [self._decode(row) or {} for row in cursor.fetchall()]
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}

    @staticmethod
    def _scoped(cursor: Any, payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        cursor.execute("SELECT organization_id,farm_id,area_id FROM warehouses WHERE id=%s AND status='active'", (result.get("warehouse_id"),))
        warehouse = cursor.fetchone()
        if warehouse is None:
            raise DomainError("WAREHOUSE_NOT_FOUND", "仓库不存在或已停用", 400)
        for key in ("organization_id", "farm_id", "area_id"):
            result[key] = warehouse[key]
        if result.get("target_warehouse_id"):
            cursor.execute("SELECT organization_id,area_id FROM warehouses WHERE id=%s AND status='active'", (result["target_warehouse_id"],))
            target = cursor.fetchone()
            if target is None or int(target["organization_id"]) != int(result["organization_id"]):
                raise DomainError("WAREHOUSE_TARGET_INVALID", "调入仓不存在或不属于同一企业", 400)
            result["_target_area_id"] = target["area_id"]
        cursor.execute("SELECT organization_id FROM materials WHERE id=%s AND status='verified'", (result.get("material_id"),))
        material = cursor.fetchone()
        if material is None or int(material["organization_id"]) != int(result["organization_id"]):
            raise DomainError("WAREHOUSE_MATERIAL_INVALID", "物料不存在、未核验或不属于当前企业", 400)
        return result

    @staticmethod
    def _require_scope(user: dict[str, Any], row: dict[str, Any]) -> None:
        scopes = user.get("data_scopes") or []
        if not scopes or any(item.get("scope_type") == "farm" for item in scopes):
            return
        allowed = {int(item["area_id"]) for item in scopes if item.get("area_id")}
        actual = {int(row[key]) for key in ("area_id", "_target_area_id") if row.get(key)}
        if actual and actual <= allowed:
            return
        if any(item.get("scope_type") == "personal" for item in scopes) and int(row.get("created_by") or 0) == int(user["id"]):
            return
        raise DomainError("DATA_SCOPE_FORBIDDEN", "无权写入授权范围之外的仓储记录", 403)

    @staticmethod
    def _payload(payload: dict[str, Any]) -> dict[str, Any]:
        clean = {key: value for key, value in payload.items() if key in FIELDS and value != ""}
        if "evidence_attachment_ids" in clean:
            clean["evidence_attachment_ids_json"] = json.dumps(clean.pop("evidence_attachment_ids"))
        return clean

    def _get(self, cursor: Any, resource: str, record_id: int, *, lock: bool = False) -> dict[str, Any] | None:
        cursor.execute("SELECT * FROM warehouse_documents WHERE id=%s AND document_type=%s" + (" FOR UPDATE" if lock else ""), (record_id, DOC_TYPES[resource]))
        return self._decode(cursor.fetchone())

    def get_record(self, resource: str, record_id: int) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            return self._get(cursor, resource, record_id)

    def create_record(self, resource: str, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            scoped = {**self._scoped(cursor, payload), "created_by": user_id}; self._require_scope(user, scoped); clean = self._payload(scoped)
            clean.update(document_type=DOC_TYPES[resource], status="draft", row_version=1, created_by=user_id)
            try:
                cursor.execute(f"INSERT INTO warehouse_documents ({','.join(clean)}) VALUES ({','.join(['%s'] * len(clean))})", tuple(clean.values()))
            except pymysql.IntegrityError as exc:
                if "uq_warehouse_documents_org_type_code" not in str(exc):
                    raise
                raise DomainError("WAREHOUSE_CODE_EXISTS", "当前企业该仓储业务类型的单号已存在", 409) from exc
            record_id = int(cursor.lastrowid); row = self._get(cursor, resource, record_id)
            self._audit(connection, user_id, "create", resource, record_id, after=row)
            return row or {}

    def create_correction(self, resource: str, record_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, resource, record_id, lock=True)
            if before is None or before["status"] != "verified" or int(before["row_version"]) != expected_version:
                raise DomainError("VERSION_CONFLICT", "数据已被修改，请刷新后重试", 409)
            copied = {key: before[key] for key in FIELDS if before.get(key) is not None and key != "evidence_attachment_ids"}
            copied.update(payload); scoped = {**self._scoped(cursor, copied), "created_by": user_id}; self._require_scope(user, scoped); clean = self._payload(scoped)
            clean.update(document_type=DOC_TYPES[resource], correction_of_id=record_id, status="draft", row_version=1, created_by=user_id)
            try:
                cursor.execute(f"INSERT INTO warehouse_documents ({','.join(clean)}) VALUES ({','.join(['%s'] * len(clean))})", tuple(clean.values()))
            except pymysql.IntegrityError as exc:
                if "uq_warehouse_documents_correction" not in str(exc):
                    raise
                raise DomainError("CORRECTION_EXISTS", "该核验记录已有更正单", 409) from exc
            correction_id = int(cursor.lastrowid); row = self._get(cursor, resource, correction_id)
            self._audit(connection, user_id, "create_correction", resource, correction_id, before=before, after=row)
            return row or {}

    def update_record(self, resource: str, record_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, resource, record_id, lock=True)
            if before is None:
                raise DomainError("WAREHOUSE_RECORD_NOT_FOUND", "仓储记录不存在", 404)
            scoped = self._scoped(cursor, {**before, **payload}); self._require_scope(user, scoped)
            clean = self._payload({**payload, **({key: scoped[key] for key in ("organization_id", "farm_id", "area_id")} if "warehouse_id" in payload else {})})
            assignments = ",".join(f"{key}=%s" for key in clean)
            cursor.execute(f"UPDATE warehouse_documents SET {assignments},updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status IN ('draft','submitted')", (*clean.values(), user_id, record_id, expected_version))
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "数据已被修改，请刷新后重试", 409)
            after = self._get(cursor, resource, record_id)
            if before["status"] == "submitted":
                save_revision(connection, build_revision(entity_type=f"warehouse:{resource}", entity_id=record_id, current_version=expected_version, before=before, after=after or {}, actor_user_id=user_id))
                cursor.execute("UPDATE work_items SET target_version=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (after["row_version"], f"warehouse:{resource}:{record_id}:verify"))
            self._audit(connection, user_id, "update", resource, record_id, before=before, after=after)
            return after or {}

    def set_status(self, resource: str, record_id: int, status: str, *, expected_version: int, user: dict[str, Any], user_id: int, evidence_attachment_ids: list[int] | None = None) -> dict[str, Any]:
        del user
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, resource, record_id, lock=True)
            if before is None:
                raise DomainError("WAREHOUSE_RECORD_NOT_FOUND", "仓储记录不存在", 404)
            if status == "verified":
                self.poster.lock_business_anchors(cursor, resource, before)
            evidence = validate_bound_evidence(cursor, organization_id=int(before["organization_id"]), entity_type=f"warehouse:{resource}", entity_id=record_id, evidence_ids=evidence_attachment_ids)
            lot_id = self.poster.ensure_receipt_lot(cursor, before) if status == "verified" and resource == "receipts" else before.get("inventory_lot_id")
            params: list[Any] = [status, user_id]
            extra = ",inventory_lot_id=%s" if lot_id and lot_id != before.get("inventory_lot_id") else ""
            if extra:
                params.append(lot_id)
            if evidence:
                extra += ",evidence_attachment_ids_json=%s"; params.append(json.dumps(evidence))
            verified = ",verified_by=%s,verified_at=CURRENT_TIMESTAMP" if status == "verified" else ""
            if verified:
                params.append(user_id)
            params.extend([record_id, expected_version])
            cursor.execute(f"UPDATE warehouse_documents SET status=%s,updated_by=%s{extra}{verified},row_version=row_version+1 WHERE id=%s AND row_version=%s", tuple(params))
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "数据已被修改，请刷新后重试", 409)
            after = self._get(cursor, resource, record_id); source_key = f"warehouse:{resource}:{record_id}:verify"
            if status == "submitted":
                cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'warehouse','verify',%s,%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version),completed_by=NULL,completed_at=NULL", (after["organization_id"], f"warehouse:{resource}", record_id, f"{resource}:{record_id}", source_key, f"核验仓储单据：{after['name']}", after["row_version"]))
                notify_work_item_created(
                    connection,
                    organization_id=after["organization_id"],
                    module_code="warehouse",
                    action_code="verify",
                    object_type=f"warehouse:{resource}",
                    object_id=record_id,
                    object_ref=f"{resource}:{record_id}",
                    source_key=source_key,
                    title=f"核验仓储单据：{after['name']}",
                    permission_codes=["warehouse.verify"],
                )
            else:
                self.poster.post(cursor, resource, after or {}, user_id)
                cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=CURRENT_TIMESTAMP,completion_note='仓储单据核验完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, source_key))
            self._audit(connection, user_id, status, resource, record_id, before=before, after=after)
            return after or {}

    def dispatch_transfer(self, record_id: int, *, expected_version: int, user_id: int) -> dict[str, Any]:
        return dispatch_transfer(self, record_id, expected_version=expected_version, user_id=user_id)

    def receive_transfer(self, record_id: int, **context: Any) -> dict[str, Any]:
        return receive_transfer(self, record_id, **context)

    def cancel_transfer(self, record_id: int, **context: Any) -> dict[str, Any]:
        return cancel_transfer(self, record_id, **context)

    def delete_draft(self, resource: str, record_id: int, *, user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, resource, record_id, lock=True)
            if before is None:
                raise DomainError("WAREHOUSE_RECORD_NOT_FOUND", "仓储记录不存在", 404)
            try:
                cursor.execute("DELETE FROM warehouse_documents WHERE id=%s AND status='draft'", (record_id,))
            except pymysql.IntegrityError as exc:
                raise DomainError("DELETE_NOT_ALLOWED", "已有业务引用的仓储草稿不能删除", 409) from exc
            if cursor.rowcount != 1:
                raise DomainError("DELETE_NOT_ALLOWED", "仅无引用的未提交草稿可以删除", 409)
            self._audit(connection, user_id, "delete_draft", resource, record_id, before=before)
            return before

    @staticmethod
    def _area_where(user: dict[str, Any], alias: str) -> tuple[str, list[Any]]:
        scopes = user.get("data_scopes") or []
        if not scopes or any(item.get("scope_type") == "farm" for item in scopes):
            return "", []
        areas = [int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")]
        return (f"WHERE {alias}.area_id IN ({','.join(['%s'] * len(areas))})", areas) if areas else ("WHERE 1=0", [])

    def list_warehouses(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        where, values = self._area_where(user, "w")
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT w.id,w.code,w.name,w.farm_id,w.area_id,w.location FROM warehouses w {where} AND w.status='active'" if where else "SELECT w.id,w.code,w.name,w.farm_id,w.area_id,w.location FROM warehouses w WHERE w.status='active'", tuple(values))
            return list(cursor.fetchall())

    def list_ledger(self, user: dict[str, Any], *, page: int = 1, page_size: int = 50, **_: Any) -> dict[str, Any]:
        where, values = self._area_where(user, "w"); page = max(1, int(page)); page_size = min(100, max(1, int(page_size)))
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM inventory_ledger g JOIN warehouses w ON w.id=g.warehouse_id {where}", tuple(values))
            total = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(
                f"SELECT g.id,g.source_type,g.source_id,g.quantity_delta,g.unit_cost,g.pond_id,g.batch_id,g.happened_at,m.name AS material_name,l.lot_no,w.name AS warehouse_name FROM inventory_ledger g JOIN warehouses w ON w.id=g.warehouse_id JOIN materials m ON m.id=g.material_id JOIN inventory_lots l ON l.id=g.inventory_lot_id {where} ORDER BY g.happened_at DESC,g.id DESC LIMIT %s OFFSET %s",
                tuple(values + [page_size, (page - 1) * page_size]),
            )
            items = list(cursor.fetchall())
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}

    def list_alerts(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        return list_alerts(self, user)

    def handle_alert(self, user: dict[str, Any], alert_key: str, **context: Any) -> dict[str, Any]:
        return handle_alert(self, user, alert_key, **context)

    def _audit(self, connection: Any, user_id: int, action: str, resource: str, record_id: int, *, before: Any = None, after: Any = None) -> None:
        self.audit.write(connection, user_id=user_id, action=f"{action}_warehouse", object_type=f"warehouse:{resource}", object_id=record_id, object_ref=f"{resource}:{record_id}", result="success", ip_address=None, module_code="warehouse", before=before, after=after)
