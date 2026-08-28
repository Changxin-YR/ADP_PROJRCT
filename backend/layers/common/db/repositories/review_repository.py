from __future__ import annotations

from typing import Any


class ReviewRepository:
    @staticmethod
    def _validate_grant_ids(cursor: Any, *, role_ids: list[int], scope_ids: list[int]) -> None:
        """Only active roles and data scopes may be assigned to an account."""
        if role_ids:
            placeholders = ",".join(["%s"] * len(role_ids))
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM roles WHERE id IN ({placeholders}) AND status='active'",
                tuple(role_ids),
            )
            if int((cursor.fetchone() or {}).get("total", 0)) != len(set(role_ids)):
                raise ValueError("角色不存在或已停用")
        if scope_ids:
            placeholders = ",".join(["%s"] * len(scope_ids))
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM data_scopes WHERE id IN ({placeholders}) AND status='active'",
                tuple(scope_ids),
            )
            if int((cursor.fetchone() or {}).get("total", 0)) != len(set(scope_ids)):
                raise ValueError("数据范围不存在或已停用")

    def is_admin(self, connection: Any, *, user_id: int) -> bool:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 FROM user_roles AS ur
                INNER JOIN roles AS r ON r.id = ur.role_id
                INNER JOIN role_permissions AS rp ON rp.role_id = r.id
                INNER JOIN permissions AS p ON p.id = rp.permission_id
                WHERE ur.user_id = %s AND p.code IN ('auth.review', 'auth.user.manage') AND r.status = 'active'
                LIMIT 1
                """,
                (user_id,),
            )
            return cursor.fetchone() is not None

    def list_applications(self, connection: Any, *, status: str | None, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        where = ""
        params: list[Any] = []
        if status:
            where = "WHERE ra.status = %s"
            params.append(status)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM registration_applications AS ra {where}", tuple(params))
            total = int((cursor.fetchone() or {}).get("total", 0))
            offset = (page - 1) * page_size
            cursor.execute(
                f"""
                SELECT ra.id, ra.user_id, ra.version_no, ra.name, ra.desired_role_id,
                       ra.area_id, ra.desired_scope_type, ra.application_note, ra.status, ra.rejection_reason,
                       ra.reviewed_by, ra.reviewed_at, ra.created_at,
                       ra.created_at AS submitted_at, ra.updated_at,
                       u.phone, COALESCE(r.name, CONCAT('岗位 #', ra.desired_role_id)) AS desired_role_name,
                       COALESCE(a.name, CONCAT('区域 #', ra.area_id)) AS area_name,
                       reviewer.name AS reviewer_name
                FROM registration_applications AS ra
                INNER JOIN users AS u ON u.id = ra.user_id
                LEFT JOIN roles AS r ON r.id = ra.desired_role_id
                LEFT JOIN areas AS a ON a.id = ra.area_id
                LEFT JOIN users AS reviewer ON reviewer.id = ra.reviewed_by
                {where}
                ORDER BY ra.created_at DESC, ra.id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params + [page_size, offset]),
            )
            items = list(cursor.fetchall())
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": offset + len(items) < total}

    def approve(self, connection: Any, *, application_id: int, reviewer_id: int, role_ids: list[int], scope_ids: list[int]) -> dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM registration_applications WHERE id = %s FOR UPDATE", (application_id,))
            application = cursor.fetchone()
            if application is None:
                raise ValueError("申请不存在")
            if application["status"] != "pending":
                raise ValueError("当前申请状态不允许通过")
            # 审核人提交的 scope_ids 是最终授权集合；申请人的 desired_scope 仅作参考。
            resolved_scope_ids = list(scope_ids)
            self._validate_grant_ids(cursor, role_ids=role_ids, scope_ids=resolved_scope_ids)
            cursor.execute("UPDATE users SET status = 'active' WHERE id = %s", (application["user_id"],))
            cursor.executemany("INSERT IGNORE INTO user_roles (user_id, role_id, granted_by) VALUES (%s, %s, %s)", [(application["user_id"], role_id, reviewer_id) for role_id in role_ids])
            cursor.executemany("INSERT IGNORE INTO user_data_scopes (user_id, data_scope_id, granted_by) VALUES (%s, %s, %s)", [(application["user_id"], scope_id, reviewer_id) for scope_id in resolved_scope_ids])
            cursor.execute("UPDATE registration_applications SET status = 'approved', reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP WHERE id = %s", (reviewer_id, application_id))
            return {**application, "status": "approved", "reviewed_by": reviewer_id}

    def _resolve_scope_id(self, cursor: Any, scope_type: str, area_id: Any) -> int | None:
        """按申请的数据范围类型解析对应 data_scope id：farm→全场，personal→本人，area→所属区域。"""
        if scope_type == "farm":
            cursor.execute(
                "SELECT ds.id FROM data_scopes ds LEFT JOIN areas a ON a.id=ds.area_id "
                "WHERE ds.scope_type='farm' AND ds.status='active' "
                "AND (ds.farm_id=(SELECT farm_id FROM areas WHERE id=%s) OR ds.organization_id=(SELECT organization_id FROM areas WHERE id=%s) OR (ds.farm_id IS NULL AND ds.organization_id IS NULL)) "
                "ORDER BY (ds.farm_id IS NOT NULL) DESC, ds.id LIMIT 1",
                (area_id, area_id),
            )
        elif scope_type == "personal":
            cursor.execute("SELECT id FROM data_scopes WHERE scope_type = 'personal' AND status = 'active' ORDER BY id LIMIT 1", ())
        else:
            if area_id is None:
                return None
            cursor.execute(
                """
                SELECT ds.id
                FROM data_scopes AS ds
                WHERE ds.scope_type = 'area' AND ds.area_id = %s AND ds.status = 'active'
                ORDER BY ds.id LIMIT 1
                """,
                (area_id,),
            )
        row = cursor.fetchone()
        return int(row["id"]) if row else None

    def reject(self, connection: Any, *, application_id: int, reviewer_id: int, reason: str) -> dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM registration_applications WHERE id = %s FOR UPDATE", (application_id,))
            application = cursor.fetchone()
            if application is None:
                raise ValueError("申请不存在")
            if application["status"] != "pending":
                raise ValueError("当前申请状态不允许驳回")
            cursor.execute("UPDATE users SET status = 'rejected' WHERE id = %s", (application["user_id"],))
            cursor.execute("UPDATE registration_applications SET status = 'rejected', rejection_reason = %s, reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP WHERE id = %s", (reason, reviewer_id, application_id))
            return {**application, "status": "rejected", "rejection_reason": reason, "reviewed_by": reviewer_id}

    def create_user(self, connection: Any, *, phone: str, login_name: str | None, name: str, password_hash: str, role_ids: list[int], scope_ids: list[int], assigned_by: int) -> dict[str, Any]:
        with connection.cursor() as cursor:
            self._validate_grant_ids(cursor, role_ids=role_ids, scope_ids=scope_ids)
            cursor.execute("INSERT INTO users (phone, login_name, name, password_hash, status) VALUES (%s, %s, %s, %s, 'must_change_password')", (phone, login_name, name, password_hash))
            user_id = int(cursor.lastrowid)
            cursor.executemany("INSERT INTO user_roles (user_id, role_id, granted_by) VALUES (%s, %s, %s)", [(user_id, role_id, assigned_by) for role_id in role_ids])
            cursor.executemany("INSERT INTO user_data_scopes (user_id, data_scope_id, granted_by) VALUES (%s, %s, %s)", [(user_id, scope_id, assigned_by) for scope_id in scope_ids])
            return {"id": user_id, "phone": phone, "login_name": login_name, "name": name, "status": "must_change_password"}

    def list_users(self, connection: Any, *, status: str | None, keyword: str | None, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("u.status = %s")
            params.append(status)
        if keyword:
            conditions.append("(u.phone LIKE %s OR u.name LIKE %s OR u.login_name LIKE %s)")
            term = f"%{keyword}%"
            params.extend([term, term, term])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM users AS u {where}", tuple(params))
            total = int((cursor.fetchone() or {}).get("total", 0))
            offset = (page - 1) * page_size
            cursor.execute(f"SELECT u.id, u.phone, u.login_name, u.name, u.status, u.created_at, u.updated_at FROM users AS u {where} ORDER BY u.created_at DESC, u.id DESC LIMIT %s OFFSET %s", tuple(params + [page_size, offset]))
            users = list(cursor.fetchall())
            for user in users:
                cursor.execute("SELECT r.id, r.code, r.name FROM user_roles AS ur INNER JOIN roles AS r ON r.id = ur.role_id WHERE ur.user_id = %s AND r.status = 'active' ORDER BY r.id", (user["id"],))
                user["roles"] = list(cursor.fetchall())
                cursor.execute("SELECT ds.id, ds.code, ds.name FROM user_data_scopes AS uds INNER JOIN data_scopes AS ds ON ds.id = uds.data_scope_id WHERE uds.user_id = %s AND ds.status = 'active' ORDER BY ds.id", (user["id"],))
                user["data_scopes"] = list(cursor.fetchall())
        return {"items": users, "page": page, "page_size": page_size, "total": total, "has_next": offset + len(users) < total}

    def set_user_status(self, connection: Any, *, user_id: int, status: str) -> None:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE users SET status = %s WHERE id = %s", (status, user_id))
            if cursor.rowcount != 1:
                raise ValueError("账号不存在")
            if status == "disabled":
                cursor.execute("UPDATE sessions SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP, revoke_reason = 'account_disabled' WHERE user_id = %s AND status = 'active'", (user_id,))

    def reset_password(self, connection: Any, *, user_id: int, password_hash: str) -> None:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE users SET password_hash = %s, status = 'must_change_password' WHERE id = %s AND status IN ('active', 'must_change_password')", (password_hash, user_id))
            if cursor.rowcount != 1:
                raise ValueError("当前账号状态不允许重置密码")
            cursor.execute("UPDATE sessions SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP, revoke_reason = 'password_reset' WHERE user_id = %s AND status = 'active'", (user_id,))

    # ===== 注册/账号字典（对齐功能文档 7 角色 + 三级数据范围） =====
    def list_roles(self, connection: Any, *, include_disabled: bool = False) -> list[dict[str, Any]]:
        with connection.cursor() as cursor:
            where = "WHERE status = %s AND code <> 'super_admin'" if not include_disabled else ""
            cursor.execute(
                f"SELECT id, code, name, description FROM roles {where} ORDER BY id",
                (("active",) if not include_disabled else ()),
            )
            return list(cursor.fetchall())

    def list_roles_with_permissions(self, connection: Any) -> dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT r.id,r.code,r.name,r.description,r.status,COUNT(DISTINCT ur.user_id) AS user_count
                   FROM roles r LEFT JOIN user_roles ur ON ur.role_id=r.id
                   WHERE r.code NOT IN ('area_manager','farmer')
                   GROUP BY r.id,r.code,r.name,r.description,r.status ORDER BY r.id"""
            )
            roles = list(cursor.fetchall())
            for role in roles:
                cursor.execute(
                    """SELECT p.code,p.name,p.module_code,p.description FROM role_permissions rp
                       INNER JOIN permissions p ON p.id=rp.permission_id
                       WHERE rp.role_id=%s ORDER BY p.module_code,p.code""",
                    (role["id"],),
                )
                role["permissions"] = list(cursor.fetchall())
            cursor.execute("SELECT code,name,module_code,description FROM permissions ORDER BY module_code,code")
            permissions = list(cursor.fetchall())
        return {"items": roles, "available_permissions": permissions, "total": len(roles)}

    def list_areas(self, connection: Any) -> list[dict[str, Any]]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, code, name FROM areas WHERE status IN ('active', 'verified') ORDER BY sort_order, id")
            return list(cursor.fetchall())

    def list_data_scopes(self, connection: Any) -> list[dict[str, Any]]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ds.id, ds.code, ds.name, ds.scope_type, ds.organization_id, ds.farm_id, ds.area_id, a.name AS area_name
                FROM data_scopes AS ds
                LEFT JOIN areas AS a ON a.id = ds.area_id
                WHERE ds.status = 'active'
                ORDER BY FIELD(ds.scope_type, 'farm', 'area', 'personal'), ds.id
                """
            )
            return list(cursor.fetchall())

    # ===== 账号注销：只变更生命周期状态，保留业务引用与历史台账 =====
    def retire_user(self, connection: Any, *, user_id: int, operator_id: int, reason: str) -> dict[str, Any]:
        with connection.cursor() as cursor:
            if int(user_id) == int(operator_id):
                raise ValueError("不能注销当前登录账号")
            cursor.execute("SELECT id, phone, login_name, name, status, retired_at, retired_by FROM users WHERE id = %s FOR UPDATE", (user_id,))
            user = cursor.fetchone()
            if user is None:
                raise ValueError("账号不存在")
            if user.get("status") == "retired":
                raise ValueError("账号已经注销")
            cursor.execute(
                "UPDATE users SET status = 'retired', retired_at = CURRENT_TIMESTAMP, retired_by = %s WHERE id = %s AND status <> 'retired'",
                (operator_id, user_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("账号状态更新失败")
            cursor.execute("UPDATE sessions SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP, revoke_reason = 'account_retired' WHERE user_id = %s AND status = 'active'", (user_id,))
            cursor.execute("SELECT id, phone, login_name, name, status, retired_at, retired_by FROM users WHERE id = %s", (user_id,))
            updated = cursor.fetchone() or {**user, "status": "retired", "retired_by": operator_id}
            return {**dict(updated), "retirement_reason": reason}

    def delete_user(self, connection: Any, *, user_id: int, operator_id: int) -> dict[str, Any]:
        """兼容旧仓储调用：旧删除动作降级为可追溯注销。"""
        return self.retire_user(connection, user_id=user_id, operator_id=operator_id, reason="legacy_delete_api")

    # ===== 权限（角色/数据范围）回收：按提交的最终集合同步 =====
    def replace_user_grants(self, connection: Any, *, user_id: int, role_ids: list[int], scope_ids: list[int], operator_id: int) -> dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if cursor.fetchone() is None:
                raise ValueError("账号不存在")
            if int(user_id) == int(operator_id):
                raise ValueError("不能修改当前登录账号自身的权限")
            self._validate_grant_ids(cursor, role_ids=role_ids, scope_ids=scope_ids)
            cursor.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM user_data_scopes WHERE user_id = %s", (user_id,))
            cursor.executemany(
                "INSERT IGNORE INTO user_roles (user_id, role_id, granted_by) VALUES (%s, %s, %s)",
                [(user_id, role_id, operator_id) for role_id in role_ids],
            )
            cursor.executemany(
                "INSERT IGNORE INTO user_data_scopes (user_id, data_scope_id, granted_by) VALUES (%s, %s, %s)",
                [(user_id, scope_id, operator_id) for scope_id in scope_ids],
            )
            cursor.execute(
                "SELECT r.id, r.code, r.name FROM user_roles AS ur INNER JOIN roles AS r ON r.id = ur.role_id WHERE ur.user_id = %s",
                (user_id,),
            )
            roles = list(cursor.fetchall())
            cursor.execute(
                "SELECT ds.id, ds.code, ds.name, ds.scope_type FROM user_data_scopes AS uds INNER JOIN data_scopes AS ds ON ds.id = uds.data_scope_id WHERE uds.user_id = %s",
                (user_id,),
            )
            return {"user_id": user_id, "roles": roles, "data_scopes": list(cursor.fetchall())}
