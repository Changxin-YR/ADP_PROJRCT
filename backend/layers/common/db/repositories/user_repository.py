from __future__ import annotations

from datetime import datetime
from typing import Any


class UserRepository:
    def find_by_identifier(self, connection: Any, identifier: str) -> dict[str, Any] | None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, phone, login_name, name, password_hash, status,
                       failed_login_count, locked_until, last_login_at
                FROM users
                WHERE phone = %s OR login_name = %s
                LIMIT 1
                """,
                (identifier, identifier),
            )
            return cursor.fetchone()

    def find_by_id(self, connection: Any, user_id: int) -> dict[str, Any] | None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, phone, login_name, name, password_hash, status, failed_login_count, locked_until FROM users WHERE id = %s",
                (user_id,),
            )
            return cursor.fetchone()

    def permissions(self, connection: Any, *, user_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.id, r.code, r.name
                FROM user_roles AS ur
                INNER JOIN roles AS r ON r.id = ur.role_id
                WHERE ur.user_id = %s AND r.status = 'active'
                ORDER BY r.id
                """,
                (user_id,),
            )
            roles = list(cursor.fetchall())
            # Older migration chains do not have organization_id/farm_id on data_scopes.
            # Keep the returned shape stable while resolving those values through area/farm.
            has_scope_org = has_scope_farm = True
            if hasattr(cursor, "fetchone"):
                cursor.execute(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='data_scopes' "
                    "AND COLUMN_NAME IN ('organization_id','farm_id')"
                )
                columns = {str(row["COLUMN_NAME"]) for row in cursor.fetchall()}
                has_scope_org = "organization_id" in columns
                has_scope_farm = "farm_id" in columns
            scope_farm_value = "COALESCE(ds.farm_id, area.farm_id)" if has_scope_farm else "area.farm_id"
            scope_org_value = "COALESCE(ds.organization_id, area.organization_id, farm.organization_id)" if has_scope_org else "COALESCE(area.organization_id, farm.organization_id)"
            cursor.execute(
                f"""
                SELECT ds.id, ds.code, ds.name, ds.scope_type, {scope_farm_value} AS farm_id, ds.area_id,
                       {scope_org_value} AS organization_id
                FROM user_data_scopes AS uds
                INNER JOIN data_scopes AS ds ON ds.id = uds.data_scope_id
                LEFT JOIN areas AS area ON area.id = ds.area_id
                LEFT JOIN farms AS farm ON farm.id = {scope_farm_value}
                WHERE uds.user_id = %s AND ds.status = 'active'
                ORDER BY ds.id
                """,
                (user_id,),
            )
            data_scopes = list(cursor.fetchall())
            cursor.execute(
                """
                SELECT DISTINCT p.code
                FROM user_roles ur
                INNER JOIN roles r ON r.id = ur.role_id AND r.status = 'active'
                INNER JOIN role_permissions rp ON rp.role_id = r.id
                INNER JOIN permissions p ON p.id = rp.permission_id
                WHERE ur.user_id = %s
                ORDER BY p.code
                """,
                (user_id,),
            )
            permission_codes = [str(item["code"]) for item in cursor.fetchall()]
            return roles, data_scopes, permission_codes

    def create_pending(self, connection: Any, *, phone: str, name: str, password_hash: str) -> int:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (phone, name, password_hash, status) VALUES (%s, %s, %s, 'pending')",
                (phone, name, password_hash),
            )
            return int(cursor.lastrowid)

    def record_failed_login(self, connection: Any, *, user_id: int, locked_until: datetime | None) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET failed_login_count = failed_login_count + 1, locked_until = %s WHERE id = %s",
                (locked_until, user_id),
            )

    def reset_failed_login(self, connection: Any, *, user_id: int, logged_in_at: datetime) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET failed_login_count = 0, locked_until = NULL, last_login_at = %s WHERE id = %s",
                (logged_in_at, user_id),
            )

    def update_password(self, connection: Any, *, user_id: int, password_hash: str, status: str | None = None) -> None:
        with connection.cursor() as cursor:
            if status is None:
                cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
            else:
                cursor.execute(
                    "UPDATE users SET password_hash = %s, status = %s WHERE id = %s",
                    (password_hash, status, user_id),
                )

    def set_status(self, connection: Any, *, user_id: int, status: str) -> None:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE users SET status = %s WHERE id = %s", (status, user_id))
