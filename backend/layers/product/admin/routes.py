from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, jsonify, request

from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.http.request_helpers import json_object as request_json_object, pagination, require_csrf
from backend.layers.common.http.response import fail, ok
from backend.layers.common.security.csrf import CsrfError
from backend.layers.features.account_review.review_service import ReviewService, ReviewServiceError
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError


def create_admin_blueprint(settings: Settings, store: Any) -> Blueprint:
    blueprint = Blueprint("admin", __name__, url_prefix="/api/v1/admin")
    auth_service = AuthService(store, settings)
    review_service = ReviewService(store, settings)

    def json_object() -> dict[str, Any]:
        try:
            return request_json_object()
        except DomainError as error:
            raise ReviewServiceError(error.code, error.message, error.status) from error

    def response_error(error: Exception, fallback: str, status: int) -> tuple[Response, int]:
        return jsonify(fail(getattr(error, "code", fallback), getattr(error, "message", str(error)), getattr(error, "status", status))), getattr(error, "status", status)

    def authorized_user(*required: str) -> dict[str, Any]:
        user = auth_service.current_user(request.cookies.get("adp_session"))
        if not set(required).intersection(user.get("permissions") or []):
            raise ReviewServiceError("FORBIDDEN", "当前账号没有所需管理权限", 403)
        return user

    def super_admin(*permissions: str) -> dict[str, Any]:
        user = authorized_user(*permissions)
        if "super_admin" not in {role.get("code") for role in user.get("roles") or []}:
            raise ReviewServiceError("FORBIDDEN", "该操作仅限超级管理员", 403)
        return user

    def csrf() -> None:
        require_csrf()

    @blueprint.get("/applications")
    def applications() -> tuple[Response, int] | Response:
        try:
            user = super_admin("auth.review")
            page, page_size = pagination()
            result = review_service.list_applications(user["id"], request.args.get("status"), page=page, page_size=page_size)
            return jsonify(ok(result))
        except (AuthServiceError, ReviewServiceError, DomainError) as error:
            return response_error(error, "APPLICATION_LIST_FAILED", 403)
        except (TypeError, ValueError):
            return response_error(ReviewServiceError("VALIDATION_ERROR", "分页参数无效", 400), "APPLICATION_LIST_FAILED", 400)

    @blueprint.get("/audit-logs")
    def audit_logs() -> tuple[Response, int] | Response:
        try:
            user = super_admin("audit.view")
            page, page_size = pagination(default_page_size=50)
            result = store.list_audit_logs(
                user_id=int(request.args["user_id"]) if request.args.get("user_id") else None,
                module_code=request.args.get("module_code") or None,
                action_code=request.args.get("action_code") or None,
                object_type=request.args.get("object_type") or None,
                result=request.args.get("result") or None,
                request_id=request.args.get("request_id") or None,
                page=page,
                page_size=page_size,
            )
            return jsonify(ok(result))
        except (AuthServiceError, ReviewServiceError, DomainError) as error:
            return response_error(error, "AUDIT_LOG_LIST_FAILED", 403)
        except (TypeError, ValueError):
            return response_error(ReviewServiceError("VALIDATION_ERROR", "日志查询参数无效", 400), "AUDIT_LOG_LIST_FAILED", 400)

    @blueprint.patch("/applications/<int:application_id>/review")
    def review(application_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            user = super_admin("auth.review")
            payload = json_object()
            result = review_service.review(user["id"], application_id, payload)
            message = "申请已通过" if payload.get("decision") == "approve" else "申请已驳回"
            return jsonify(ok({"application": result}, message=message))
        except (CsrfError, AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "APPLICATION_REVIEW_FAILED", 400)

    @blueprint.post("/applications/<int:application_id>/approve")
    def approve(application_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            user = super_admin("auth.review")
            result = review_service.approve(user["id"], application_id, json_object())
            return jsonify(ok({"application": result}, message="申请已通过"))
        except (CsrfError, AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "APPLICATION_APPROVE_FAILED", 400)

    @blueprint.post("/applications/<int:application_id>/reject")
    def reject(application_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            user = super_admin("auth.review")
            result = review_service.reject(user["id"], application_id, json_object())
            return jsonify(ok({"application": result}, message="申请已驳回"))
        except (CsrfError, AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "APPLICATION_REJECT_FAILED", 400)

    @blueprint.post("/users")
    def create_user() -> tuple[Response, int] | Response:
        try:
            csrf()
            user = super_admin("auth.user.manage")
            result = review_service.create_user(user["id"], json_object())
            return jsonify(ok({"user": result}, message="账号已创建"))
        except (CsrfError, AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "USER_CREATE_FAILED", 400)

    @blueprint.get("/users")
    def users() -> tuple[Response, int] | Response:
        try:
            user = super_admin("auth.user.manage")
            page, page_size = pagination()
            result = review_service.list_users(user["id"], request.args.get("status"), request.args.get("keyword"), page=page, page_size=page_size)
            return jsonify(ok(result))
        except (AuthServiceError, ReviewServiceError, DomainError) as error:
            return response_error(error, "USER_LIST_FAILED", 403)
        except (TypeError, ValueError):
            return response_error(ReviewServiceError("VALIDATION_ERROR", "分页参数无效", 400), "USER_LIST_FAILED", 400)

    @blueprint.patch("/users/<int:user_id>/status")
    def set_status(user_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            user = super_admin("auth.user.manage")
            review_service.set_status(user["id"], user_id, str(json_object().get("status", "")))
            return jsonify(ok(message="账号状态已更新"))
        except (CsrfError, AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "USER_STATUS_FAILED", 400)

    @blueprint.post("/users/<int:user_id>/reset-password")
    @blueprint.post("/users/<int:user_id>/password-reset")
    def reset_password(user_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            user = super_admin("auth.user.manage")
            payload = json_object()
            review_service.reset_password(user["id"], user_id, str(payload.get("temporary_password", "")))
            return jsonify(ok(message="密码已重置，用户下次登录必须修改"))
        except (CsrfError, AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "PASSWORD_RESET_FAILED", 400)

    @blueprint.get("/options")
    def options() -> tuple[Response, int] | Response:
        try:
            user = super_admin("auth.review", "auth.user.manage")
            return jsonify(ok(review_service.options(user["id"])))
        except (AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "OPTIONS_FAILED", 403)

    @blueprint.get("/roles")
    def roles() -> tuple[Response, int] | Response:
        try:
            user = super_admin("auth.role.manage")
            return jsonify(ok(review_service.roles(user["id"])))
        except (AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "ROLE_LIST_FAILED", 403)

    @blueprint.put("/roles/<int:role_id>/permissions")
    def update_role_permissions(role_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            user = super_admin("auth.role.manage")
            role = review_service.update_role_permissions(user["id"], role_id, json_object())
            return jsonify(ok({"role": role}, message="角色权限已更新并记录差异"))
        except (CsrfError, AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "ROLE_PERMISSION_UPDATE_FAILED", 400)

    @blueprint.post("/roles/<int:role_id>/copies")
    def copy_role(role_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            user = super_admin("auth.role.manage")
            role = review_service.copy_role(user["id"], role_id, json_object())
            return jsonify(ok({"role": role}, message="角色已复制")), 201
        except (CsrfError, AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "ROLE_COPY_FAILED", 400)

    @blueprint.post("/users/<int:user_id>/retire")
    def retire_user(user_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            user = super_admin("auth.user.manage")
            payload = json_object()
            retired = review_service.retire_user(user["id"], user_id, reason=str(payload.get("reason", "")))
            return jsonify(ok({"user": retired}, message="账号已注销，历史记录已保留"))
        except (CsrfError, AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "USER_RETIRE_FAILED", 400)

    @blueprint.delete("/users/<int:user_id>")
    def delete_user_compatibility(user_id: int) -> tuple[Response, int] | Response:
        """兼容旧客户端路径：永远执行注销，不物理删除；新客户端请使用 POST /retire。"""
        try:
            csrf()
            user = super_admin("auth.user.manage")
            payload = json_object()
            reason = str(payload.get("reason", "")).strip()
            if not reason and payload.get("confirm_phrase") == "DELETE":
                reason = "旧版删除接口迁移为账号注销"
            retired = review_service.retire_user(user["id"], user_id, reason=reason)
            return jsonify(ok({"user": retired}, message="账号已注销，历史记录已保留"))
        except (CsrfError, AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "USER_RETIRE_FAILED", 400)

    @blueprint.put("/users/<int:user_id>/grants")
    def update_grants(user_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            user = super_admin("auth.user.manage")
            result = review_service.update_grants(user["id"], user_id, json_object())
            return jsonify(ok({"grants": result}, message="权限已更新（角色/数据范围按最终集合同步）"))
        except (CsrfError, AuthServiceError, ReviewServiceError) as error:
            return response_error(error, "GRANT_UPDATE_FAILED", 400)

    return blueprint
