from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, g, jsonify, request

from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.http.response import fail, ok
from backend.layers.common.http.request_helpers import json_object, pagination, require_csrf
from backend.layers.common.security.session import request_session_token
from backend.layers.common.security.csrf import CsrfError
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError
from backend.layers.features.workbench.workbench_service import WorkbenchService, WorkbenchServiceError


def create_workbench_blueprint(settings: Settings, store: Any) -> Blueprint:
    blueprint = Blueprint("workbench_api", __name__, url_prefix="/api/v1")
    auth_service = AuthService(store, settings)
    workbench_service = WorkbenchService(store)

    def error_response(error: Exception, fallback: str, status: int) -> tuple[Response, int]:
        actual_status = int(getattr(error, "status", status))
        return jsonify(fail(getattr(error, "code", fallback), str(error), actual_status)), actual_status

    def csrf() -> None:
        require_csrf()

    def current_user() -> dict[str, Any]:
        return auth_service.current_user(request_session_token(request), request_id=getattr(g, "request_id", None))

    @blueprint.get("/workbench/summary")
    def summary() -> tuple[Response, int] | Response:
        try:
            return jsonify(ok(workbench_service.summary(current_user())))
        except (AuthServiceError, WorkbenchServiceError) as error:
            return error_response(error, "WORKBENCH_SUMMARY_FAILED", 403)

    @blueprint.get("/work-items")
    def work_items() -> tuple[Response, int] | Response:
        try:
            user = current_user()
            include_history = request.args.get("include_history", "true").lower() != "false"
            page, page_size = pagination()
            result = workbench_service.list_work_items(user, status=request.args.get("status") or None, include_history=include_history, page=page, page_size=page_size)
            return jsonify(ok(result))
        except (AuthServiceError, WorkbenchServiceError, DomainError) as error:
            return error_response(error, "WORK_ITEM_LIST_FAILED", 403)
        except (TypeError, ValueError):
            return error_response(WorkbenchServiceError("VALIDATION_ERROR", "分页参数无效", 400), "WORK_ITEM_LIST_FAILED", 400)

    @blueprint.patch("/work-items/<int:item_id>")
    def transition_work_item(item_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            user = current_user()
            payload = json_object()
            expected_version = payload.get("expected_version")
            result = workbench_service.transition_work_item(
                user,
                item_id,
                action=str(payload.get("action", "")),
                expected_version=expected_version,
                note=str(payload.get("note", "")) or None,
            )
            return jsonify(ok({"work_item": result}, message="待办状态已更新"))
        except (CsrfError, AuthServiceError, WorkbenchServiceError, DomainError) as error:
            return error_response(error, "WORK_ITEM_UPDATE_FAILED", 400)
        except (TypeError, ValueError):
            return error_response(WorkbenchServiceError("VALIDATION_ERROR", "待办参数无效", 400), "WORK_ITEM_UPDATE_FAILED", 400)

    @blueprint.get("/notifications")
    def notifications() -> tuple[Response, int] | Response:
        try:
            user = current_user()
            include_history = request.args.get("include_history", "true").lower() != "false"
            page, page_size = pagination()
            result = workbench_service.list_notifications(user, status=request.args.get("status") or None, include_history=include_history, page=page, page_size=page_size)
            return jsonify(ok(result))
        except (AuthServiceError, WorkbenchServiceError, DomainError) as error:
            return error_response(error, "NOTIFICATION_LIST_FAILED", 403)
        except (TypeError, ValueError):
            return error_response(WorkbenchServiceError("VALIDATION_ERROR", "分页参数无效", 400), "NOTIFICATION_LIST_FAILED", 400)

    @blueprint.patch("/notifications/<int:notification_id>")
    def update_notification(notification_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            user = current_user()
            payload = json_object()
            status = str(payload.get("status", ""))
            if status == "read":
                result = workbench_service.mark_notification_read(user, notification_id)
            elif status == "closed":
                result = workbench_service.close_notification(user, notification_id, str(payload.get("conclusion", "")))
            else:
                raise WorkbenchServiceError("VALIDATION_ERROR", "消息状态只能更新为 read 或 closed", 400)
            return jsonify(ok({"notification": result}, message="消息状态已更新"))
        except (CsrfError, AuthServiceError, WorkbenchServiceError, DomainError) as error:
            return error_response(error, "NOTIFICATION_UPDATE_FAILED", 400)

    return blueprint
