from __future__ import annotations

from typing import Any


class ApplicationRepository:
    def create(
        self,
        connection: Any,
        *,
        user_id: int,
        name: str,
        desired_role_id: int,
        area_id: int,
        application_note: str,
        desired_scope_type: str | None = None,
    ) -> dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO registration_applications
                    (user_id, version_no, name, desired_role_id, area_id, desired_scope_type, application_note, status)
                SELECT %s, COALESCE(MAX(version_no), 0) + 1, %s, %s, %s, %s, %s, 'pending'
                FROM registration_applications
                WHERE user_id = %s
                """,
                (user_id, name, desired_role_id, area_id, desired_scope_type, application_note, user_id),
            )
            application_id = int(cursor.lastrowid)
            return {"id": application_id, "user_id": user_id, "status": "pending"}

    def latest_for_user(self, connection: Any, *, user_id: int) -> dict[str, Any] | None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ra.id, ra.user_id, ra.version_no, ra.name, ra.desired_role_id, ra.area_id,
                       ra.desired_scope_type,
                       ra.application_note, ra.status, ra.rejection_reason, ra.reviewed_by,
                       ra.reviewed_at, ra.created_at, ra.created_at AS submitted_at, ra.updated_at,
                       CASE WHEN ra.status = 'rejected' THEN ra.rejection_reason ELSE '申请正在等待管理员审核。' END AS admin_message,
                       COALESCE(r.name, CONCAT('岗位 #', ra.desired_role_id)) AS desired_role_name,
                       COALESCE(a.name, CONCAT('区域 #', ra.area_id)) AS area_name
                FROM registration_applications AS ra
                LEFT JOIN roles AS r ON r.id = ra.desired_role_id
                LEFT JOIN areas AS a ON a.id = ra.area_id
                WHERE user_id = %s
                ORDER BY version_no DESC
                LIMIT 1
                """,
                (user_id,),
            )
            return cursor.fetchone()

    def by_id(self, connection: Any, *, application_id: int) -> dict[str, Any] | None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM registration_applications WHERE id = %s", (application_id,))
            return cursor.fetchone()
