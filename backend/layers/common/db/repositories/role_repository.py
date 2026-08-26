from __future__ import annotations

from typing import Any


class RoleRepository:
    @staticmethod
    def replace_permissions(connection: Any, *, role_id: int, permission_codes: list[str]) -> dict[str, Any]:
        placeholders = ",".join(["%s"] * len(permission_codes))
        with connection.cursor() as cursor:
            cursor.execute("SELECT id,code,name,description,status FROM roles WHERE id=%s FOR UPDATE", (role_id,))
            role = cursor.fetchone()
            if role is None:
                raise ValueError("角色不存在")
            cursor.execute(f"SELECT code FROM permissions WHERE code IN ({placeholders})", tuple(permission_codes))
            found = {str(row["code"]) for row in cursor.fetchall()}
            unknown = sorted(set(permission_codes) - found)
            if unknown:
                raise ValueError(f"权限编码不存在：{', '.join(unknown)}")
            cursor.execute("DELETE FROM role_permissions WHERE role_id=%s", (role_id,))
            cursor.execute(
                f"INSERT INTO role_permissions (role_id,permission_id) SELECT %s,id FROM permissions WHERE code IN ({placeholders})",
                (role_id, *permission_codes),
            )
        return {**dict(role), "permission_codes": permission_codes}

    @staticmethod
    def copy(connection: Any, *, source_role_id: int, code: str, name: str, description: str | None) -> dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM roles WHERE id=%s AND status='active' FOR UPDATE", (source_role_id,))
            if cursor.fetchone() is None:
                raise ValueError("来源角色不存在或已停用")
            cursor.execute("INSERT INTO roles (code,name,status,description) VALUES (%s,%s,'active',%s)", (code, name, description))
            role_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO role_permissions (role_id,permission_id) SELECT %s,permission_id FROM role_permissions WHERE role_id=%s",
                (role_id, source_role_id),
            )
            cursor.execute(
                "SELECT p.code FROM role_permissions rp INNER JOIN permissions p ON p.id=rp.permission_id WHERE rp.role_id=%s ORDER BY p.module_code,p.code",
                (role_id,),
            )
            permission_codes = [str(row["code"]) for row in cursor.fetchall()]
        return {"id": role_id, "code": code, "name": name, "status": "active", "description": description, "permission_codes": permission_codes}
