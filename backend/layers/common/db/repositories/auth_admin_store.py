from __future__ import annotations

import json
from typing import Any

from pymysql.err import IntegrityError

from backend.layers.common.db.repositories.store_errors import StoreError


class AuthAdminStoreMixin:
    def is_admin(self, user_id: int) -> bool:
        with self.transaction() as connection:
            return self.review.is_admin(connection, user_id=user_id)

    def list_applications(self, status: str | None = None, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        with self.transaction() as connection:
            return self.review.list_applications(connection, status=status, page=page, page_size=page_size)

    def approve_application(self, application_id: int, *, reviewer_id: int, role_ids: list[int], scope_ids: list[int]) -> dict[str, Any]:
        with self.transaction() as connection:
            result = self.review.approve(connection, application_id=application_id, reviewer_id=reviewer_id, role_ids=role_ids, scope_ids=scope_ids)
            self.audit.write(connection, user_id=reviewer_id, action="approve_registration", object_type="registration_application", object_id=application_id, result="success", ip_address=None, detail_json=json.dumps({"role_ids": role_ids, "scope_ids": scope_ids}))
            return result

    def reject_application(self, application_id: int, *, reviewer_id: int, reason: str) -> dict[str, Any]:
        with self.transaction() as connection:
            result = self.review.reject(connection, application_id=application_id, reviewer_id=reviewer_id, reason=reason)
            self.audit.write(connection, user_id=reviewer_id, action="reject_registration", object_type="registration_application", object_id=application_id, result="success", ip_address=None)
            return result

    def create_managed_user(self, payload: dict[str, Any], *, password_hash: str) -> dict[str, Any]:
        try:
            with self.transaction() as connection:
                result = self.review.create_user(
                    connection, phone=payload["phone"], login_name=payload.get("login_name"),
                    name=payload["name"], password_hash=password_hash,
                    role_ids=[int(item) for item in payload["role_ids"]],
                    scope_ids=[int(item) for item in payload["scope_ids"]],
                    assigned_by=int(payload["assigned_by"]),
                )
                self.audit.write(
                    connection, user_id=int(payload["assigned_by"]), action="create_managed_user",
                    object_type="user", object_id=int(result["id"]), object_ref=f"user:{result['id']}",
                    result="success", ip_address=None, module_code="account", after=result,
                )
                return result
        except IntegrityError as exc:
            if exc.args and exc.args[0] == 1062:
                raise StoreError("PHONE_EXISTS", "该手机号或登录名已注册，无法重复创建账号", 409) from exc
            raise StoreError("USER_CREATE_FAILED", "账号创建失败", 409) from exc

    def set_user_status(self, user_id: int, status: str, *, operator_id: int | None = None) -> None:
        with self.transaction() as connection:
            self.review.set_user_status(connection, user_id=user_id, status=status)
            self.audit.write(connection, user_id=operator_id, action="set_user_status", object_type="user", object_id=user_id, result="success", ip_address=None, detail_json=json.dumps({"status": status}))

    def list_users(self, status: str | None = None, keyword: str | None = None, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        with self.transaction() as connection:
            return self.review.list_users(connection, status=status, keyword=keyword, page=page, page_size=page_size)

    def reset_password(self, user_id: int, *, password_hash: str, operator_id: int | None = None) -> None:
        with self.transaction() as connection:
            self.review.reset_password(connection, user_id=user_id, password_hash=password_hash)
            self.audit.write(connection, user_id=operator_id, action="reset_password", object_type="user", object_id=user_id, result="success", ip_address=None)

    def list_registration_options(self) -> dict[str, Any]:
        with self.transaction() as connection:
            return {"roles": self.review.list_roles(connection), "areas": self.review.list_areas(connection), "data_scopes": self.review.list_data_scopes(connection)}

    def list_roles_with_permissions(self) -> dict[str, Any]:
        with self.transaction() as connection:
            return self.review.list_roles_with_permissions(connection)

    def replace_role_permissions(self, role_id: int, *, permission_codes: list[str], operator_id: int) -> dict[str, Any]:
        with self.transaction() as connection:
            before = next((item for item in self.review.list_roles_with_permissions(connection)["items"] if int(item["id"]) == role_id), None)
            result = self.roles.replace_permissions(connection, role_id=role_id, permission_codes=permission_codes)
            self.audit.write(connection, user_id=operator_id, action="replace_role_permissions", object_type="role", object_id=role_id, object_ref=f"role:{role_id}", result="success", ip_address=None, module_code="admin", before=before, after=result)
            return result

    def copy_role(self, source_role_id: int, *, code: str, name: str, description: str | None, operator_id: int) -> dict[str, Any]:
        try:
            with self.transaction() as connection:
                result = self.roles.copy(connection, source_role_id=source_role_id, code=code, name=name, description=description)
                self.audit.write(connection, user_id=operator_id, action="copy_role", object_type="role", object_id=result["id"], object_ref=f"role:{result['id']}", result="success", ip_address=None, module_code="admin", after=result)
                return result
        except IntegrityError as exc:
            raise StoreError("ROLE_CODE_EXISTS", "角色编码已存在", 409) from exc

    def retire_managed_user(self, user_id: int, *, operator_id: int, reason: str) -> dict[str, Any]:
        with self.transaction() as connection:
            before = self.users.find_by_id(connection, user_id)
            retired = self.review.retire_user(connection, user_id=user_id, operator_id=operator_id, reason=reason)
            self.audit.write(
                connection, user_id=operator_id, action="retire_user", object_type="user",
                object_id=user_id, result="success", ip_address=None, module_code="account",
                action_code="retire_user", object_ref=f"user:{user_id}", reason=reason,
                before=before, after=retired,
            )
            return retired

    def delete_managed_user(self, user_id: int, *, operator_id: int) -> dict[str, Any]:
        return self.retire_managed_user(user_id, operator_id=operator_id, reason="legacy_delete_api")

    def replace_user_grants(self, user_id: int, *, role_ids: list[int], scope_ids: list[int], operator_id: int) -> dict[str, Any]:
        with self.transaction() as connection:
            result = self.review.replace_user_grants(connection, user_id=user_id, role_ids=role_ids, scope_ids=scope_ids, operator_id=operator_id)
            self.audit.write(connection, user_id=operator_id, action="replace_user_grants", object_type="user", object_id=user_id, result="success", ip_address=None, detail_json=json.dumps({"role_ids": role_ids, "scope_ids": scope_ids}))
            return result
