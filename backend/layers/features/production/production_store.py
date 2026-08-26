from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pymysql

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.revisions import build_revision, save_revision
from backend.layers.common.governance.work_item_notifications import notify_work_item_created
from backend.layers.common.files.evidence import validate_bound_evidence
from backend.layers.common.security.data_scope import require_active_scope, unrestricted
from backend.layers.features.production.production_service import FIELDS
from backend.layers.features.production.production_material_control import require_material_issue
from backend.layers.features.production.production_filters import apply_record_filters
from backend.layers.features.production.production_stock_locking import lock_batch_anchors
DOC_TYPES = {
    "samplings": "sampling", "transfers": "transfer", "losses": "loss", "harvests": "harvest",
    "feed-plans": "feed_plan", "feed-tasks": "feed_task", "feed-logs": "feed_log",
    "daily-operations": "daily_operation",
}
class MySqlProductionStore:
    require_material_issue = staticmethod(require_material_issue)
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.audit = AuditLogger()

    @staticmethod
    def _table(resource: str) -> tuple[str, str | None]:
        return ("production_batches", None) if resource == "batches" else ("production_documents", DOC_TYPES[resource])
    @staticmethod
    def _decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        result = dict(row)
        for source, target in (("payload_json", "payload"), ("evidence_attachment_ids_json", "evidence_attachment_ids")):
            value = result.pop(source, None)
            if isinstance(value, str):
                value = json.loads(value)
            if value is not None:
                result[target] = value
        return result
    @staticmethod
    def _scope(user: dict[str, Any]) -> tuple[str, list[Any]]:
        scopes = require_active_scope(user)
        if unrestricted(user):
            return "", []
        areas = [int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")]
        if areas:
            return f"area_id IN ({','.join(['%s'] * len(areas))})", areas
        if any(item.get("scope_type") == "personal" for item in scopes):
            return "created_by = %s", [int(user["id"])]
        return "1=0", []

    def list_records(self, resource: str, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, pond_id: Any = None, area_id: Any = None, **_: Any) -> dict[str, Any]:
        table, doc_type = self._table(resource)
        clauses, values = (["document_type = %s"], [doc_type]) if doc_type else ([], [])
        scope, scope_values = self._scope(user)
        if scope:
            clauses.append(scope); values.extend(scope_values)
        if status:
            clauses.append("status = %s"); values.append(status)
        if search:
            clauses.append("(code LIKE %s OR name LIKE %s)"); values.extend([f"%{search}%", f"%{search}%"])
        # BUG-M1-001：塘口/区域筛选真实生效，并与数据范围叠加（AND），不泄露授权外数据。
        apply_record_filters(clauses, values, pond_id=pond_id, area_id=area_id)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table} {where}", tuple(values))
            total = int((cursor.fetchone() or {}).get("total", 0))
            select = "*,(SELECT COALESCE(SUM(quantity_delta),0) FROM batch_stock_records WHERE batch_id=production_batches.id) AS current_quantity,(SELECT COALESCE(SUM(weight_delta_kg),0) FROM batch_stock_records WHERE batch_id=production_batches.id) AS current_weight_kg" if resource == "batches" else "*"
            cursor.execute(f"SELECT {select} FROM {table} {where} ORDER BY updated_at DESC,id DESC LIMIT %s OFFSET %s", tuple(values + [page_size, (page - 1) * page_size]))
            items = [self._decode(row) or {} for row in cursor.fetchall()]
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}

    @staticmethod
    def _scope_defaults(cursor: Any, payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        if result.get("pond_id"):
            cursor.execute("SELECT organization_id,farm_id,area_id FROM ponds WHERE id=%s", (result["pond_id"],))
            pond = cursor.fetchone()
            if pond is None:
                raise DomainError("POND_NOT_FOUND", "塘口不存在", 400)
            for key in ("organization_id", "farm_id", "area_id"):
                result[key] = int(pond[key])
        if result.get("target_pond_id"):
            cursor.execute("SELECT organization_id,area_id FROM ponds WHERE id=%s", (result["target_pond_id"],))
            target = cursor.fetchone()
            if target is None:
                raise DomainError("TARGET_POND_NOT_FOUND", "转入塘口不存在", 400)
            if result.get("organization_id") and int(target["organization_id"]) != int(result["organization_id"]):
                raise DomainError("PRODUCTION_SCOPE_INVALID", "来源与目标塘口必须属于同一企业", 400)
            result["_target_area_id"] = int(target["area_id"])
        if (assignee := result.get("assigned_user_id")) not in (None, ""):
            try: assignee = int(assignee)
            except (TypeError, ValueError) as exc: raise DomainError("FEED_TASK_ASSIGNEE_INVALID", "指派作业员不存在或已停用", 400) from exc
            cursor.execute("SELECT id FROM users WHERE id=%s AND status='active'", (assignee,))
            if cursor.fetchone() is None: raise DomainError("FEED_TASK_ASSIGNEE_INVALID", "指派作业员不存在或已停用", 400)
        return result
    @staticmethod
    def require_write_scope(user: dict[str, Any], row: dict[str, Any]) -> None:
        scopes = require_active_scope(user)
        if unrestricted(user):
            return
        allowed = {int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")}
        actual = {int(row[key]) for key in ("area_id", "_target_area_id") if row.get(key)}
        personal = any(item.get("scope_type") == "personal" for item in scopes)
        if actual and actual <= allowed and (not personal or int(row.get("created_by") or 0) == int(user["id"])):
            return
        raise DomainError("DATA_SCOPE_FORBIDDEN", "无权写入授权范围之外的生产记录", 403)
    @staticmethod
    def _db_payload(resource: str, payload: dict[str, Any]) -> dict[str, Any]:
        clean = {key: value for key, value in payload.items() if key in FIELDS[resource] and value != ""}
        if "payload" in clean: clean["payload_json"] = json.dumps(clean.pop("payload"), ensure_ascii=False, default=str)
        if "evidence_attachment_ids" in clean: clean["evidence_attachment_ids_json"] = json.dumps(clean.pop("evidence_attachment_ids"))
        return clean
    def create_record(self, resource: str, payload: dict[str, Any], *, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        table, doc_type = self._table(resource)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            scoped = {**self._scope_defaults(cursor, payload), "created_by": user_id}
            self.require_write_scope(user, scoped)
            clean = self._db_payload(resource, scoped)
            if not all(clean.get(key) for key in ("organization_id", "farm_id", "area_id", "pond_id")):
                raise DomainError("PRODUCTION_SCOPE_REQUIRED", "生产记录必须关联有效塘口", 400)
            if doc_type:
                clean["document_type"] = doc_type
            clean.update(status="draft", row_version=1, created_by=user_id)
            cursor.execute(f"INSERT INTO {table} ({','.join(clean)}) VALUES ({','.join(['%s'] * len(clean))})", tuple(clean.values()))
            record_id = int(cursor.lastrowid)
            row = self._get(cursor, resource, record_id)
            self._audit(connection, user_id, "create", resource, record_id, after=row)
            return row or {}
    def _get(self, cursor: Any, resource: str, record_id: int, *, lock: bool = False) -> dict[str, Any] | None:
        table, doc_type = self._table(resource)
        clause, params = (" AND document_type=%s", (doc_type,)) if doc_type else ("", ())
        cursor.execute(f"SELECT * FROM {table} WHERE id=%s{clause}" + (" FOR UPDATE" if lock else ""), (record_id, *params))
        return self._decode(cursor.fetchone())

    def get_record(self, resource: str, record_id: int) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            return self._get(cursor, resource, record_id)

    def create_correction(self, resource: str, record_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        table, doc_type = self._table(resource)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, resource, record_id, lock=True)
            if before is None:
                raise DomainError("PRODUCTION_RECORD_NOT_FOUND", "生产记录不存在", 404)
            if before["status"] != "verified" or int(before["row_version"]) != expected_version:
                raise DomainError("VERSION_CONFLICT", "数据已被修改，请刷新后重试", 409)
            copied = {key: before[key] for key in FIELDS[resource] if before.get(key) is not None and key != "evidence_attachment_ids"}
            copied.update(payload)
            scoped = self._scope_defaults(cursor, copied)
            self.require_write_scope(user, scoped)
            clean = self._db_payload(resource, scoped)
            clean["correction_of_id"] = record_id
            if doc_type:
                clean["document_type"] = doc_type
            clean.update(status="draft", row_version=1, created_by=user_id)
            try:
                cursor.execute(f"INSERT INTO {table} ({','.join(clean)}) VALUES ({','.join(['%s'] * len(clean))})", tuple(clean.values()))
            except pymysql.IntegrityError as exc:
                key = "uq_production_batches_correction" if table == "production_batches" else "uq_production_documents_correction"
                if key not in str(exc):
                    raise
                raise DomainError("CORRECTION_EXISTS", "该核验记录已有更正单", 409) from exc
            correction_id = int(cursor.lastrowid)
            row = self._get(cursor, resource, correction_id)
            self._audit(connection, user_id, "create_correction", resource, correction_id, before=before, after=row)
            return row or {}

    def update_record(self, resource: str, record_id: int, payload: dict[str, Any], *, expected_version: int, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        table, _doc_type = self._table(resource)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, resource, record_id, lock=True)
            if before is None:
                raise DomainError("PRODUCTION_RECORD_NOT_FOUND", "生产记录不存在", 404)
            scoped = self._scope_defaults(cursor, {**before, **payload})
            self.require_write_scope(user, scoped)
            effective = dict(payload)
            if "pond_id" in payload:
                effective.update({key: scoped[key] for key in ("organization_id", "farm_id", "area_id")})
            clean = self._db_payload(resource, effective)
            if not clean:
                raise DomainError("PRODUCTION_NO_CHANGES", "没有可保存的修改", 400)
            assignments = ",".join(f"{key}=%s" for key in clean)
            cursor.execute(f"UPDATE {table} SET {assignments},updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s AND status IN ('draft','submitted')", (*clean.values(), user_id, record_id, expected_version))
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "数据已被修改，请刷新后重试", 409)
            after = self._get(cursor, resource, record_id)
            if before["status"] == "submitted":
                save_revision(connection, build_revision(entity_type=f"production:{resource}", entity_id=record_id, current_version=expected_version, before=before, after=after or {}, actor_user_id=user_id))
                cursor.execute("UPDATE work_items SET target_version=%s,row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (after["row_version"], f"production:{resource}:{record_id}:verify"))
            self._audit(connection, user_id, "update", resource, record_id, before=before, after=after)
            return after or {}

    @staticmethod
    def _check_evidence(cursor: Any, row: dict[str, Any], evidence: Any, *, entity_type: str) -> list[int]:
        return validate_bound_evidence(cursor, organization_id=int(row["organization_id"]), entity_type=entity_type, entity_id=int(row["id"]), evidence_ids=evidence)

    def set_status(self, resource: str, record_id: int, status: str, *, expected_version: int, user_id: int, evidence_attachment_ids: list[int] | None = None) -> dict[str, Any]:
        table, _doc_type = self._table(resource)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, resource, record_id, lock=True)
            if before is None:
                raise DomainError("PRODUCTION_RECORD_NOT_FOUND", "生产记录不存在", 404)
            if status == "verified":
                lock_batch_anchors(cursor, resource, before)
            if status == "verified" and resource == "feed-logs":
                self.require_material_issue(cursor, before)
            evidence = self._check_evidence(cursor, before, evidence_attachment_ids, entity_type=f"production:{resource}")
            evidence_sql = ",evidence_attachment_ids_json=%s" if evidence and table == "production_documents" else ""
            params: list[Any] = [status, user_id]
            if status == "verified":
                verified_sql = ",verified_by=%s,verified_at=CURRENT_TIMESTAMP"
                params.append(user_id)
            else:
                verified_sql = ""
            if evidence_sql:
                params.append(json.dumps(evidence))
            params.extend([record_id, expected_version])
            cursor.execute(f"UPDATE {table} SET status=%s,updated_by=%s{verified_sql}{evidence_sql},row_version=row_version+1 WHERE id=%s AND row_version=%s", tuple(params))
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "数据已被修改，请刷新后重试", 409)
            after = self._get(cursor, resource, record_id)
            source_key = f"production:{resource}:{record_id}:verify"
            if status == "submitted":
                cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'production','verify',%s,%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending',target_version=VALUES(target_version),completed_by=NULL,completed_at=NULL", (after["organization_id"], f"production:{resource}", record_id, f"{resource}:{record_id}", source_key, f"核验生产记录：{after['name']}", after["row_version"]))
                notify_work_item_created(connection, organization_id=after["organization_id"], module_code="production", action_code="verify", object_type=f"production:{resource}", object_id=record_id, object_ref=f"{resource}:{record_id}", source_key=source_key, title=f"核验生产记录：{after['name']}", permission_codes=["production.verify"])
            else:
                self._post_stock(cursor, resource, after or {}, user_id)
                cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=CURRENT_TIMESTAMP,completion_note='生产记录核验完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, source_key))
            self._audit(connection, user_id, status, resource, record_id, before=before, after=after)
            return after or {}

    @staticmethod
    def _stock_lines(resource: str, row: dict[str, Any]) -> list[tuple[int, int, str, Decimal, Decimal]]:
        batch_id = int(row.get("correction_of_id") or row["id"]) if resource == "batches" else int(row["batch_id"])
        quantity = Decimal(str(row.get("initial_quantity") if resource == "batches" else row.get("quantity") or 0))
        weight = Decimal(str(row.get("initial_weight_kg") if resource == "batches" else row.get("weight_kg") or 0))
        if resource == "batches":
            return [(batch_id, int(row["pond_id"]), "stocking", quantity, weight)]
        if resource == "transfers":
            return [
                (batch_id, int(row["pond_id"]), "transfer_out", -quantity, -weight),
                (batch_id, int(row["target_pond_id"]), "transfer_in", quantity, weight),
            ]
        return [(batch_id, int(row["pond_id"]), "loss" if resource == "losses" else "harvest", -quantity, -weight)]

    def _post_stock(self, cursor: Any, resource: str, row: dict[str, Any], user_id: int) -> None:
        if resource not in {"batches", "transfers", "losses", "harvests"}:
            return
        lock_batch_anchors(cursor, resource, row)
        lines = self._stock_lines(resource, row)
        if row.get("correction_of_id"):
            original = self._get(cursor, resource, int(row["correction_of_id"]))
            if original is None:
                raise DomainError("CORRECTION_SOURCE_NOT_FOUND", "原核验记录不存在", 409)
            deltas: dict[tuple[int, int], tuple[Decimal, Decimal]] = {}
            for batch_id, pond_id, _kind, quantity, weight in self._stock_lines(resource, original):
                deltas[(batch_id, pond_id)] = (-quantity, -weight)
            for batch_id, pond_id, _kind, quantity, weight in lines:
                old_quantity, old_weight = deltas.get((batch_id, pond_id), (Decimal("0"), Decimal("0")))
                deltas[(batch_id, pond_id)] = (old_quantity + quantity, old_weight + weight)
            lines = [(batch_id, pond_id, "correction", quantity, weight) for (batch_id, pond_id), (quantity, weight) in deltas.items() if quantity or weight]
        for batch_id, pond_id, _kind, quantity, weight in lines:
            if quantity >= 0 and weight >= 0:
                continue
            cursor.execute("SELECT COALESCE(SUM(quantity_delta),0) AS quantity,COALESCE(SUM(weight_delta_kg),0) AS weight FROM batch_stock_records WHERE batch_id=%s AND pond_id=%s", (batch_id, pond_id))
            available = cursor.fetchone() or {}
            if -quantity > Decimal(str(available.get("quantity", 0))) or -weight > Decimal(str(available.get("weight", 0))):
                raise DomainError("BATCH_STOCK_INSUFFICIENT", "塘口批次存量不足，禁止核验", 409)
        cursor.executemany("INSERT INTO batch_stock_records (organization_id,batch_id,pond_id,source_type,source_id,line_no,quantity_delta,weight_delta_kg,happened_at,posted_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP),%s)", [(row["organization_id"], batch_id, pond_id, kind, row["id"], index, qty, kg, row.get("happened_at") or row.get("stocked_at"), user_id) for index, (batch_id, pond_id, kind, qty, kg) in enumerate(lines, 1)])

    def delete_draft(self, resource: str, record_id: int, *, user_id: int) -> dict[str, Any]:
        table, _doc_type = self._table(resource)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, resource, record_id, lock=True)
            if before is None:
                raise DomainError("PRODUCTION_RECORD_NOT_FOUND", "生产记录不存在", 404)
            try:
                cursor.execute(f"DELETE FROM {table} WHERE id=%s AND status='draft'", (record_id,))
            except pymysql.IntegrityError as exc:
                raise DomainError("DELETE_NOT_ALLOWED", "已有业务引用的草稿不能删除", 409) from exc
            if cursor.rowcount != 1:
                raise DomainError("DELETE_NOT_ALLOWED", "仅无引用的未提交草稿可以删除", 409)
            self._audit(connection, user_id, "delete_draft", resource, record_id, before=before)
            return before

    def reconcile_batch(self, batch_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COALESCE(SUM(quantity_delta),0) AS quantity,COALESCE(SUM(weight_delta_kg),0) AS weight_kg FROM batch_stock_records WHERE batch_id=%s", (batch_id,))
            totals = cursor.fetchone() or {}
        return {"batch_id": batch_id, "quantity": totals.get("quantity", Decimal("0")), "weight_kg": totals.get("weight_kg", Decimal("0")), "difference": Decimal("0")}
    def _audit(self, connection: Any, user_id: int, action: str, resource: str, record_id: int, *, before: Any = None, after: Any = None) -> None:
        self.audit.write(connection, user_id=user_id, action=f"{action}_production", object_type=f"production:{resource}", object_id=record_id, object_ref=f"{resource}:{record_id}", result="success", ip_address=None, module_code="production", before=before, after=after)
