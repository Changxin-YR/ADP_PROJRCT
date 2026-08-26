from __future__ import annotations

import re
from typing import Any, Protocol

from backend.config.settings import Settings
from backend.layers.common.security.password import hash_password
from backend.layers.common.validation.auth_validation import validate_name, validate_password, validate_phone


class ReviewServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class ReviewStore(Protocol):
    def is_admin(self, user_id: int) -> bool: ...
    def list_applications(self, status: str | None = None, *, page: int = 1, page_size: int = 20) -> dict[str, Any]: ...
    def approve_application(self, application_id: int, *, reviewer_id: int, role_ids: list[int], scope_ids: list[int]) -> dict[str, Any]: ...
    def reject_application(self, application_id: int, *, reviewer_id: int, reason: str) -> dict[str, Any]: ...
    def create_managed_user(self, payload: dict[str, Any], *, password_hash: str) -> dict[str, Any]: ...
    def list_users(self, status: str | None = None, keyword: str | None = None, *, page: int = 1, page_size: int = 20) -> dict[str, Any]: ...
    def set_user_status(self, user_id: int, status: str) -> None: ...
    def reset_password(self, user_id: int, *, password_hash: str) -> None: ...
    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None: ...
    def list_registration_options(self) -> dict[str, Any]: ...
    def list_roles_with_permissions(self) -> dict[str, Any]: ...
    def replace_role_permissions(self, role_id: int, *, permission_codes: list[str], operator_id: int) -> dict[str, Any]: ...
    def copy_role(self, source_role_id: int, *, code: str, name: str, description: str | None, operator_id: int) -> dict[str, Any]: ...
    def retire_managed_user(self, user_id: int, *, operator_id: int, reason: str) -> dict[str, Any]: ...
    def replace_user_grants(self, user_id: int, *, role_ids: list[int], scope_ids: list[int], operator_id: int) -> dict[str, Any]: ...


class ReviewService:
    def __init__(self, store: ReviewStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    def require_admin(self, user_id: int) -> None:
        if not self.store.is_admin(user_id):
            raise ReviewServiceError("FORBIDDEN", "需要管理员权限", 403)

    def list_applications(self, reviewer_id: int, status: str | None = None, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        self.require_admin(reviewer_id)
        page = max(1, page)
        page_size = min(100, max(1, page_size))
        return self.store.list_applications(status, page=page, page_size=page_size)

    @staticmethod
    def _ids(payload: dict[str, Any]) -> tuple[list[int], list[int]]:
        raw_roles = payload.get("role_ids")
        if raw_roles is None:
            raw_roles = [payload.get("final_role_id", payload.get("role_id"))]
        raw_scopes = payload.get("data_scopes")
        if raw_scopes is None:
            raw_scopes = [payload.get("data_scope_id")]
        role_ids: list[int] = []
        scope_ids: list[int] = []
        try:
            for item in raw_roles:
                if item is not None:
                    role_ids.append(int(item))
            for item in raw_scopes:
                if isinstance(item, dict) and item.get("type", "area") not in {"farm", "area", "personal"}:
                    raise ReviewServiceError("VALIDATION_ERROR", "数据范围类型无效", 400)
                value = item.get("id") if isinstance(item, dict) else item
                if value is not None:
                    scope_ids.append(int(value))
        except (TypeError, ValueError) as exc:
            raise ReviewServiceError("VALIDATION_ERROR", "必须选择有效的角色和数据范围", 400) from exc
        role_ids = list(dict.fromkeys(role_ids))
        scope_ids = list(dict.fromkeys(scope_ids))
        if not role_ids or not scope_ids:
            raise ReviewServiceError("VALIDATION_ERROR", "必须选择至少一个角色和数据范围", 400)
        return role_ids, scope_ids

    def review(self, reviewer_id: int, application_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.require_admin(reviewer_id)
        decision = str(payload.get("decision", "")).strip().lower()
        if decision not in {"approve", "reject"}:
            raise ReviewServiceError("VALIDATION_ERROR", "审核决定只能是 approve 或 reject", 400)
        if decision == "reject":
            reason = str(payload.get("reject_reason", payload.get("reason", ""))).strip()
            if not reason:
                raise ReviewServiceError("REJECTION_REASON_REQUIRED", "驳回时必须填写原因", 400)
            if len(reason) > 500:
                raise ReviewServiceError("VALIDATION_ERROR", "驳回原因不能超过 500 个字符", 400)
            try:
                return self.store.reject_application(application_id, reviewer_id=reviewer_id, reason=reason)
            except ValueError as exc:
                raise ReviewServiceError("APPLICATION_REVIEW_FAILED", str(exc), 409) from exc
        role_ids, scope_ids = self._ids(payload)
        try:
            return self.store.approve_application(application_id, reviewer_id=reviewer_id, role_ids=role_ids, scope_ids=scope_ids)
        except ValueError as exc:
            raise ReviewServiceError("APPLICATION_REVIEW_FAILED", str(exc), 409) from exc

    def approve(self, reviewer_id: int, application_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.review(reviewer_id, application_id, {**payload, "decision": "approve"})

    def reject(self, reviewer_id: int, application_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.review(reviewer_id, application_id, {**payload, "decision": "reject"})

    def create_user(self, reviewer_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.require_admin(reviewer_id)
        try:
            role_ids, scope_ids = self._ids(payload)
            normalized = {
                "phone": validate_phone(payload.get("phone", "")),
                "name": validate_name(payload.get("name", "")),
                "login_name": str(payload.get("login_name", "")).strip() or None,
                "role_ids": role_ids,
                "scope_ids": scope_ids,
                "assigned_by": reviewer_id,
            }
            temporary_password = str(payload.get("temporary_password", ""))
            validate_password(temporary_password)
        except ReviewServiceError:
            raise
        except (TypeError, ValueError) as exc:
            raise ReviewServiceError("VALIDATION_ERROR", str(exc), 400) from exc
        try:
            result = self.store.create_managed_user(normalized, password_hash=hash_password(temporary_password))
            return {key: value for key, value in result.items() if key not in {"password_hash", "failed_login_count", "locked_until"}}
        except ValueError as exc:
            raise ReviewServiceError(
                getattr(exc, "code", "USER_CREATE_FAILED"),
                str(exc),
                int(getattr(exc, "status", 409)),
            ) from exc

    def list_users(self, reviewer_id: int, status: str | None = None, keyword: str | None = None, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        self.require_admin(reviewer_id)
        page = max(1, page)
        page_size = min(100, max(1, page_size))
        return self.store.list_users(status, keyword, page=page, page_size=page_size)

    def set_status(self, reviewer_id: int, user_id: int, status: str) -> None:
        self.require_admin(reviewer_id)
        if status not in {"active", "disabled"}:
            raise ReviewServiceError("VALIDATION_ERROR", "状态只能是 active 或 disabled", 400)
        user = self.store.get_user_by_id(user_id)
        if user is None:
            raise ReviewServiceError("USER_NOT_FOUND", "账号不存在", 404)
        if user.get("status") == "retired":
            raise ReviewServiceError("USER_RETIRED_IMMUTABLE", "已注销账号仅可查看，不能恢复或停用", 409)
        self.store.set_user_status(user_id, status)

    def reset_password(self, reviewer_id: int, user_id: int, temporary_password: str) -> None:
        self.require_admin(reviewer_id)
        user = self.store.get_user_by_id(user_id)
        if user is None:
            raise ReviewServiceError("USER_NOT_FOUND", "账号不存在", 404)
        if user.get("status") == "retired":
            raise ReviewServiceError("USER_RETIRED_IMMUTABLE", "已注销账号仅可查看，不能重置密码", 409)
        if user["status"] not in {"active", "must_change_password"}:
            raise ReviewServiceError("USER_STATE_NOT_RESETTABLE", "当前账号状态不允许重置密码", 409)
        try:
            validate_password(temporary_password)
            self.store.reset_password(user_id, password_hash=hash_password(temporary_password))
        except ValueError as exc:
            raise ReviewServiceError("PASSWORD_RESET_FAILED", str(exc), 409) from exc

    # ===== 字典 / 删除账号 / 权限回收 =====
    def options(self, reviewer_id: int) -> dict[str, Any]:
        self.require_admin(reviewer_id)
        return self.store.list_registration_options()

    def roles(self, reviewer_id: int) -> dict[str, Any]:
        self.require_admin(reviewer_id)
        return self.store.list_roles_with_permissions()

    def update_role_permissions(self, reviewer_id: int, role_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.require_admin(reviewer_id)
        if payload.get("confirm_phrase") != "CONFIRM":
            raise ReviewServiceError("CONFIRM_REQUIRED", "角色权限变更需要二次确认", 400)
        raw_codes = payload.get("permission_codes")
        if not isinstance(raw_codes, list) or not raw_codes:
            raise ReviewServiceError("VALIDATION_ERROR", "至少保留一项角色权限", 400)
        codes = list(dict.fromkeys(str(code).strip() for code in raw_codes if str(code).strip()))
        if not codes or len(codes) > 100 or any(len(code) > 64 for code in codes):
            raise ReviewServiceError("VALIDATION_ERROR", "角色权限集合无效", 400)
        role = next((item for item in self.store.list_roles_with_permissions()["items"] if int(item["id"]) == int(role_id)), None)
        if role is None:
            raise ReviewServiceError("ROLE_NOT_FOUND", "角色不存在", 404)
        if role["code"] == "super_admin" and not {"auth.user.manage", "workbench.enter"}.issubset(codes):
            raise ReviewServiceError("SUPER_ADMIN_PERMISSION_REQUIRED", "超级管理员必须保留账号管理和工作台权限", 409)
        try:
            return self.store.replace_role_permissions(int(role_id), permission_codes=codes, operator_id=reviewer_id)
        except ValueError as exc:
            raise ReviewServiceError(getattr(exc, "code", "ROLE_PERMISSION_UPDATE_FAILED"), str(exc), getattr(exc, "status", 409)) from exc

    def copy_role(self, reviewer_id: int, source_role_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.require_admin(reviewer_id)
        if payload.get("confirm_phrase") != "CONFIRM":
            raise ReviewServiceError("CONFIRM_REQUIRED", "复制角色需要二次确认", 400)
        code = str(payload.get("code", "")).strip()
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip() or None
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", code) or not 2 <= len(name) <= 100 or (description and len(description) > 255):
            raise ReviewServiceError("VALIDATION_ERROR", "角色编码、名称或说明不符合要求", 400)
        try:
            return self.store.copy_role(int(source_role_id), code=code, name=name, description=description, operator_id=reviewer_id)
        except ValueError as exc:
            raise ReviewServiceError(getattr(exc, "code", "ROLE_COPY_FAILED"), str(exc), getattr(exc, "status", 409)) from exc

    def retire_user(self, reviewer_id: int, user_id: int, *, reason: str = "") -> dict[str, Any]:
        """注销账号但保留所有业务引用；账号状态变为 retired，历史数据只读。"""
        self.require_admin(reviewer_id)
        if int(user_id) == int(reviewer_id):
            raise ReviewServiceError("SELF_RETIRE_FORBIDDEN", "不能注销当前登录账号", 400)
        reason = str(reason).strip()
        if not reason:
            raise ReviewServiceError("RETIRE_REASON_REQUIRED", "注销账号必须填写原因", 400)
        if len(reason) > 500:
            raise ReviewServiceError("VALIDATION_ERROR", "注销原因不能超过 500 个字符", 400)
        user = self.store.get_user_by_id(user_id)
        if user is None:
            raise ReviewServiceError("USER_NOT_FOUND", "账号不存在", 404)
        if user.get("status") == "retired":
            raise ReviewServiceError("USER_ALREADY_RETIRED", "账号已经注销", 409)
        try:
            return self.store.retire_managed_user(user_id, operator_id=reviewer_id, reason=reason)
        except ValueError as exc:
            raise ReviewServiceError("USER_RETIRE_FAILED", str(exc), 409) from exc

    def delete_user(self, reviewer_id: int, user_id: int, *, confirm_phrase: str = "") -> dict[str, Any]:
        """兼容旧客户端：旧版删除接口现在只执行可追溯的账号注销，不会物理删除。"""
        if confirm_phrase != "DELETE":
            raise ReviewServiceError("CONFIRM_REQUIRED", "账号注销需要完成两轮确认", 400)
        return self.retire_user(reviewer_id, user_id, reason="旧版删除接口迁移为账号注销")

    def update_grants(self, reviewer_id: int, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """按最终集合同步角色与数据范围：既支持追加权限，也支持移除（删除）权限。"""
        self.require_admin(reviewer_id)
        if int(user_id) == int(reviewer_id):
            raise ReviewServiceError("SELF_GRANT_FORBIDDEN", "不能修改当前登录账号自身的权限", 400)
        user = self.store.get_user_by_id(user_id)
        if user is None:
            raise ReviewServiceError("USER_NOT_FOUND", "账号不存在", 404)
        if user.get("status") == "retired":
            raise ReviewServiceError("USER_RETIRED_IMMUTABLE", "已注销账号仅可查看，不能修改权限", 409)
        role_ids, scope_ids = self._ids({**payload, "data_scopes": payload.get("scope_ids", payload.get("data_scopes"))})
        try:
            return self.store.replace_user_grants(user_id, role_ids=role_ids, scope_ids=scope_ids, operator_id=reviewer_id)
        except ValueError as exc:
            raise ReviewServiceError("GRANT_UPDATE_FAILED", str(exc), 409) from exc
