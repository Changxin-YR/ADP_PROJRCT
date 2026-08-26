from __future__ import annotations

from typing import Any

import pymysql

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.query_guard import sql_identifier
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.revisions import build_revision, save_revision
from backend.layers.common.governance.work_item_notifications import notify_work_item_created
from backend.layers.features.master_data.master_data_service import MASTER_FIELDS
from backend.layers.features.master_data.master_data_scope import validate_master_hierarchy
from backend.layers.features.master_data.pond_status_store import MySqlPondStatusStore
from backend.layers.common.security.data_scope import require_active_scope, unrestricted


SPECS = {
    "farms": ("farms", None), "areas": ("areas", None),
    "pond-groups": ("pond_groups", None), "ponds": ("ponds", None),
    "materials": ("materials", None), "suppliers": ("business_partners", "supplier"),
    "customers": ("business_partners", "customer"), "settings": ("business_settings", None),
}


class MySqlMasterDataStore:
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.audit = AuditLogger()
        self.pond_status = MySqlPondStatusStore(settings)

    def get_pending_pond_status_change(self, pond_id: int) -> dict[str, Any] | None:
        return self.pond_status.pending(pond_id)

    def request_pond_status_change(self, pond_id: int, **context: Any) -> dict[str, Any]:
        return self.pond_status.request(pond_id, **context)

    def verify_pond_status_change(self, pond_id: int, request_id: int, **context: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.pond_status.verify(pond_id, request_id, **context)

    @staticmethod
    def _spec(resource: str) -> tuple[str, str | None, set[str]]:
        try:
            table, partner_type = SPECS[resource]
            return table, partner_type, MASTER_FIELDS[resource]
        except KeyError as exc:
            raise DomainError("MASTER_RESOURCE_NOT_FOUND", "主数据类型不存在", 404) from exc

    @staticmethod
    def _where(partner_type: str | None) -> tuple[str, tuple[Any, ...]]:
        return ("partner_type = %s", (partner_type,)) if partner_type else ("1 = 1", ())

    def list_records(self, resource: str, *, user: dict[str, Any], page: int = 1, page_size: int = 20, status: str | None = None, search: str | None = None, **_: Any) -> dict[str, Any]:
        table, partner_type, _fields = self._spec(resource)
        page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
        where, params = self._where(partner_type)
        clauses, values = [where], list(params)
        if status:
            clauses.append("status = %s")
            values.append(status)
        if search:
            clauses.append("(code LIKE %s OR name LIKE %s)")
            values.extend([f"%{search}%", f"%{search}%"])
        scope_sql, scope_values = self._scope_filter(user, resource)
        if scope_sql:
            clauses.append(scope_sql)
            values.extend(scope_values)
        sql_where = " AND ".join(clauses)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {sql_identifier(table)} WHERE {sql_where}", tuple(values))
            total = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(f"SELECT * FROM {sql_identifier(table)} WHERE {sql_where} ORDER BY updated_at DESC, id DESC LIMIT %s OFFSET %s", tuple(values + [page_size, (page - 1) * page_size]))
            items = list(cursor.fetchall())
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}

    @staticmethod
    def _scope_filter(user: dict[str, Any], resource: str) -> tuple[str, list[Any]]:
        scopes = require_active_scope(user)
        if unrestricted(user):
            return "", []
        areas = [int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")]
        if areas:
            placeholders = ",".join(["%s"] * len(areas))
            if resource == "farms":
                return f"id IN (SELECT farm_id FROM areas WHERE id IN ({placeholders}))", areas
            if resource == "areas":
                return f"id IN ({placeholders})", areas
            return f"area_id IN ({placeholders})", areas
        if any(item.get("scope_type") == "personal" for item in scopes):
            return "created_by = %s", [int(user["id"])]
        return "1=0", []

    def _defaults(self, cursor: Any, payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        if not result.get("organization_id"):
            cursor.execute("SELECT id FROM organizations WHERE status='active' ORDER BY id LIMIT 2")
            organizations = list(cursor.fetchall())
            if len(organizations) != 1:
                raise DomainError("MASTER_ORGANIZATION_REQUIRED", "多企业环境必须明确指定企业", 400)
            result["organization_id"] = int(organizations[0]["id"])
        if not result.get("farm_id"):
            cursor.execute("SELECT id FROM farms WHERE organization_id = %s ORDER BY id LIMIT 1", (result["organization_id"],))
            farm = cursor.fetchone()
            if farm:
                result["farm_id"] = int(farm["id"])
        if not result.get("area_id") and result.get("farm_id"):
            cursor.execute("SELECT id FROM areas WHERE farm_id = %s ORDER BY id LIMIT 1", (result["farm_id"],))
            area = cursor.fetchone()
            if area:
                result["area_id"] = int(area["id"])
        return result

    def create_record(self, resource: str, payload: dict[str, Any], *, user_id: int) -> dict[str, Any]:
        table, partner_type, fields = self._spec(resource)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            clean = self._defaults(cursor, {key: value for key, value in payload.items() if key in fields})
            clean = {key: value for key, value in clean.items() if key in fields and value != ""}
            validate_master_hierarchy(cursor, resource, clean)
            if table == "areas" and not clean.get("farm_id"):
                raise DomainError("MASTER_SCOPE_REQUIRED", "区域必须归属基地", 400)
            if table in {"pond_groups", "ponds"} and not clean.get("area_id"):
                raise DomainError("MASTER_SCOPE_REQUIRED", "塘组和塘口必须归属区域", 400)
            if table == "business_settings":
                clean.setdefault("group_code", "general")
                clean.setdefault("value_text", str(clean.get("name", "")))
            columns = list(clean) + (["partner_type"] if partner_type else []) + ["status", "row_version", "created_by"]
            values = list(clean.values()) + ([partner_type] if partner_type else []) + ["draft", 1, user_id]
            cursor.execute(f"INSERT INTO {sql_identifier(table)} ({','.join(columns)}) VALUES ({','.join(['%s'] * len(values))})", tuple(values))
            record_id = int(cursor.lastrowid)
            row = self._get(cursor, resource, record_id)
            self._audit(connection, user_id, "create", resource, record_id, after=row)
            return row

    def get_record(self, resource: str, record_id: int) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            return self._get(cursor, resource, record_id)

    def get_detail(self, resource: str, record_id: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            if resource == "ponds":
                cursor.execute(
                    """SELECT p.*,a.name AS area_name,pg.name AS group_name
                       FROM ponds p INNER JOIN areas a ON a.id=p.area_id
                       LEFT JOIN pond_groups pg ON pg.id=p.pond_group_id WHERE p.id=%s""",
                    (record_id,),
                )
                record = cursor.fetchone()
            else:
                record = self._get(cursor, resource, record_id)
            cursor.execute(
                """SELECT al.id,al.action AS event_type,al.action AS title,COALESCE(al.reason,'') AS description,
                          al.created_at AS happened_at,COALESCE(al.actor_name_snapshot,u.name,'系统') AS operator_name
                   FROM audit_logs al LEFT JOIN users u ON u.id=al.user_id
                   WHERE al.object_type=%s AND al.object_id=%s ORDER BY al.created_at DESC,al.id DESC LIMIT 20""",
                (f"master:{resource}", record_id),
            )
            return (dict(record) if record else None), list(cursor.fetchall())

    def _get(self, cursor: Any, resource: str, record_id: int, *, lock: bool = False) -> dict[str, Any] | None:
        table, partner_type, _fields = self._spec(resource)
        where, params = self._where(partner_type)
        cursor.execute(f"SELECT * FROM {sql_identifier(table)} WHERE id = %s AND {where}" + (" FOR UPDATE" if lock else ""), (record_id, *params))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_record(self, resource: str, record_id: int, payload: dict[str, Any], *, expected_version: int, user_id: int) -> dict[str, Any]:
        table, _partner_type, fields = self._spec(resource)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, resource, record_id, lock=True)
            if before is None:
                raise DomainError("MASTER_RECORD_NOT_FOUND", "主数据记录不存在", 404)
            clean = {key: value for key, value in payload.items() if key in fields}
            if not clean:
                raise DomainError("MASTER_NO_CHANGES", "没有可保存的修改", 400)
            validate_master_hierarchy(cursor, resource, {**before, **clean}, record_id=record_id)
            assignments = ",".join(f"{key} = %s" for key in clean)
            cursor.execute(f"UPDATE {sql_identifier(table)} SET {assignments}, updated_by = %s, row_version = row_version + 1 WHERE id = %s AND row_version = %s AND status IN ('draft','submitted')", (*clean.values(), user_id, record_id, expected_version))
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "数据已被修改，请刷新后重试", 409)
            after = self._get(cursor, resource, record_id)
            if before["status"] == "submitted":
                save_revision(connection, build_revision(entity_type=f"master:{resource}", entity_id=record_id, current_version=expected_version, before=before, after=after or {}, actor_user_id=user_id))
                cursor.execute("UPDATE work_items SET target_version = %s, row_version = row_version + 1 WHERE source_key = %s AND status IN ('pending','claimed','in_progress','escalated')", (after["row_version"], f"master:{resource}:{record_id}:verify"))
            self._audit(connection, user_id, "update", resource, record_id, before=before, after=after)
            return dict(after or {})

    def set_status(self, resource: str, record_id: int, status: str, *, expected_version: int, user_id: int) -> dict[str, Any]:
        table, _partner_type, _fields = self._spec(resource)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, resource, record_id, lock=True)
            if before is None:
                raise DomainError("MASTER_RECORD_NOT_FOUND", "主数据记录不存在", 404)
            cursor.execute(f"UPDATE {sql_identifier(table)} SET status = %s, updated_by = %s, row_version = row_version + 1 WHERE id = %s AND row_version = %s", (status, user_id, record_id, expected_version))
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "数据已被修改，请刷新后重试", 409)
            after = dict(self._get(cursor, resource, record_id) or {})
            source_key = f"master:{resource}:{record_id}:verify"
            if status == "submitted":
                cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,status,target_version) VALUES (%s,'master_data','verify',%s,%s,%s,%s,%s,'pending',%s) ON DUPLICATE KEY UPDATE status='pending', target_version=VALUES(target_version), completed_by=NULL, completed_at=NULL", (after.get("organization_id"), f"master:{resource}", record_id, f"{resource}:{record_id}", source_key, f"核验主数据：{after.get('name')}", after["row_version"]))
                notify_work_item_created(
                    connection,
                    organization_id=after.get("organization_id"),
                    module_code="master_data",
                    action_code="verify",
                    object_type=f"master:{resource}",
                    object_id=record_id,
                    object_ref=f"{resource}:{record_id}",
                    source_key=source_key,
                    title=f"核验主数据：{after.get('name')}",
                    permission_codes=["master_data.verify"],
                )
            else:
                cursor.execute("UPDATE work_items SET status='completed', completed_by=%s, completed_at=CURRENT_TIMESTAMP, completion_note='主数据核验完成', row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, source_key))
            self._audit(connection, user_id, status, resource, record_id, before=before, after=after)
            return after

    def delete_draft(self, resource: str, record_id: int, *, user_id: int) -> dict[str, Any]:
        table, _partner_type, _fields = self._spec(resource)
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            before = self._get(cursor, resource, record_id, lock=True)
            if before is None:
                raise DomainError("MASTER_RECORD_NOT_FOUND", "主数据记录不存在", 404)
            try:
                cursor.execute(f"DELETE FROM {sql_identifier(table)} WHERE id = %s AND status = 'draft'", (record_id,))
            except pymysql.IntegrityError as exc:
                raise DomainError("DELETE_NOT_ALLOWED", "已有业务引用的草稿不能删除", 409) from exc
            if cursor.rowcount != 1:
                raise DomainError("DELETE_NOT_ALLOWED", "仅无引用的未提交草稿可以删除", 409)
            self._audit(connection, user_id, "delete_draft", resource, record_id, before=before)
            return before

    def _audit(self, connection: Any, user_id: int, action: str, resource: str, record_id: int, *, before: Any = None, after: Any = None) -> None:
        self.audit.write(connection, user_id=user_id, action=f"{action}_master_data", object_type=f"master:{resource}", object_id=record_id, object_ref=f"{resource}:{record_id}", result="success", ip_address=None, module_code="master_data", before=before, after=after)
