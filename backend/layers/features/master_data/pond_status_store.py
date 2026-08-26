from __future__ import annotations

from typing import Any

from pymysql.err import IntegrityError

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.work_item_notifications import notify_work_item_created


class MySqlPondStatusStore:
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.audit = AuditLogger()

    def pending(self, pond_id: int) -> dict[str, Any] | None:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM pond_status_change_requests WHERE pond_id=%s AND status='submitted'", (pond_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def request(self, pond_id: int, *, to_status: str, reason: str, expected_pond_version: int, user_id: int) -> dict[str, Any]:
        try:
            with get_connection(self.settings) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT * FROM ponds WHERE id=%s FOR UPDATE", (pond_id,))
                pond = cursor.fetchone()
                if pond is None:
                    raise DomainError("MASTER_RECORD_NOT_FOUND", "塘口不存在", 404)
                if pond["status"] != "verified":
                    raise DomainError("POND_NOT_VERIFIED", "塘口资料核验后才能申请状态变更", 409)
                if int(pond["row_version"]) != expected_pond_version:
                    raise DomainError("VERSION_CONFLICT", "塘口已被修改，请刷新后重试", 409)
                cursor.execute("SELECT id FROM pond_status_change_requests WHERE pond_id=%s AND status='submitted' FOR UPDATE", (pond_id,))
                if cursor.fetchone():
                    raise DomainError("POND_STATUS_CHANGE_PENDING", "该塘口已有待核验状态变更", 409)
                cursor.execute(
                    "INSERT INTO pond_status_change_requests (organization_id,pond_id,from_status,to_status,reason,pond_version,requested_by) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (pond["organization_id"], pond_id, pond["pond_status"], to_status, reason, expected_pond_version, user_id),
                )
                request_id = int(cursor.lastrowid)
                source_key = f"pond_status:{request_id}:verify"
                cursor.execute(
                    "INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,object_ref,source_key,title,detail,status,target_version) VALUES (%s,'master_data','verify','master:pond_status_change',%s,%s,%s,%s,%s,'pending',1)",
                    (pond["organization_id"], pond_id, f"pond_status_change:{request_id}", source_key, f"核验塘口状态变更：{pond['name']}", reason),
                )
                cursor.execute("SELECT * FROM pond_status_change_requests WHERE id=%s", (request_id,))
                change = dict(cursor.fetchone())
                notify_work_item_created(
                    connection,
                    organization_id=pond["organization_id"],
                    area_id=pond.get("area_id"),
                    module_code="master_data",
                    action_code="verify",
                    object_type="master:pond_status_change",
                    object_id=request_id,
                    object_ref=f"pond_status_change:{request_id}",
                    source_key=source_key,
                    title=f"核验塘口状态变更：{pond['name']}",
                    permission_codes=["master_data.verify"],
                )
                self.audit.write(connection, user_id=user_id, action="request_pond_status_change", object_type="master:pond_status_change", object_id=request_id, object_ref=f"pond_status_change:{request_id}", result="success", ip_address=None, module_code="master_data", reason=reason, after=change)
                return change
        except IntegrityError as exc:
            raise DomainError("POND_STATUS_CHANGE_PENDING", "该塘口已有待核验状态变更", 409) from exc

    def verify(self, pond_id: int, request_id: int, *, expected_version: int, expected_pond_version: int, user_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM pond_status_change_requests WHERE id=%s AND pond_id=%s FOR UPDATE", (request_id, pond_id))
            change = cursor.fetchone()
            if change is None:
                raise DomainError("POND_STATUS_CHANGE_NOT_FOUND", "状态变更申请不存在", 404)
            if change["status"] != "submitted":
                raise DomainError("INVALID_STATE_TRANSITION", "该状态变更已经核验", 409)
            if int(change["requested_by"]) == user_id:
                raise DomainError("SELF_VERIFICATION_FORBIDDEN", "经办人与核验人不能是同一人", 409)
            if int(change["row_version"]) != expected_version:
                raise DomainError("VERSION_CONFLICT", "状态变更申请已更新，请刷新后重试", 409)
            cursor.execute("SELECT * FROM ponds WHERE id=%s FOR UPDATE", (pond_id,))
            pond = cursor.fetchone()
            if pond is None:
                raise DomainError("MASTER_RECORD_NOT_FOUND", "塘口不存在", 404)
            if pond["status"] != "verified" or pond["pond_status"] != change["from_status"] or int(pond["row_version"]) != expected_pond_version:
                raise DomainError("VERSION_CONFLICT", "塘口状态或版本已变化，请刷新后重试", 409)
            cursor.execute("UPDATE pond_status_change_requests SET status='verified',verified_by=%s,verified_at=CURRENT_TIMESTAMP,row_version=row_version+1 WHERE id=%s AND row_version=%s", (user_id, request_id, expected_version))
            cursor.execute("UPDATE ponds SET pond_status=%s,updated_by=%s,row_version=row_version+1 WHERE id=%s AND row_version=%s", (change["to_status"], user_id, pond_id, expected_pond_version))
            if cursor.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "塘口已被修改，请刷新后重试", 409)
            cursor.execute("UPDATE work_items SET status='completed',completed_by=%s,completed_at=CURRENT_TIMESTAMP,completion_note='塘口状态变更核验完成',row_version=row_version+1 WHERE source_key=%s AND status IN ('pending','claimed','in_progress','escalated')", (user_id, f"pond_status:{request_id}:verify"))
            cursor.execute("SELECT id FROM work_items WHERE source_key=%s", (f"pond_status:{request_id}:verify",)); work_item_id = int(cursor.fetchone()["id"])
            cursor.execute("SELECT * FROM ponds WHERE id=%s", (pond_id,)); updated_pond = dict(cursor.fetchone())
            cursor.execute("SELECT * FROM pond_status_change_requests WHERE id=%s", (request_id,)); updated_change = dict(cursor.fetchone())
            self.audit.write(connection, user_id=user_id, action="verify_pond_status_change", object_type="master:ponds", object_id=pond_id, object_ref=f"ponds:{pond_id}", result="success", ip_address=None, module_code="master_data", related_work_item_id=work_item_id, reason=change["reason"], before=pond, after=updated_pond)
            return updated_pond, updated_change
