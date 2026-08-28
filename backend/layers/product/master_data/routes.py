from __future__ import annotations

from typing import Any, Callable

import pymysql
from flask import Blueprint, Response, g, jsonify, request

from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.idempotency import execute_idempotent
from backend.layers.common.http.response import fail, ok
from backend.layers.common.http.request_helpers import json_object, pagination, require_csrf
from backend.layers.common.security.csrf import CsrfError
from backend.layers.common.security.session import request_session_token
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError
from backend.layers.features.master_data.master_data_service import MasterDataService


def create_master_data_blueprint(settings: Settings, auth_store: Any, master_store: Any) -> Blueprint:
    blueprint = Blueprint("master_data", __name__, url_prefix="/api/v1/master-data")
    auth = AuthService(auth_store, settings)
    service = MasterDataService(master_store)

    def user() -> dict[str, Any]:
        return auth.current_user(request_session_token(request), request_id=getattr(g, "request_id", None))

    def csrf() -> None:
        require_csrf()

    def error_response(error: Exception) -> tuple[Response, int]:
        status = 403 if isinstance(error, CsrfError) else int(getattr(error, "status", 400))
        message = getattr(error, "message", str(error))
        return jsonify(fail(getattr(error, "code", "MASTER_REQUEST_FAILED"), message, status)), status

    def write(operation: Callable[..., dict[str, Any]], resource: str, record_id: int | None = None, *, created: bool = False) -> tuple[Response, int] | Response:
        try:
            csrf()
            payload = json_object(); current_user = user()
            def perform() -> tuple[dict[str, Any], int]:
                result = operation(current_user, resource, payload) if record_id is None else operation(current_user, resource, record_id, payload)
                return ok({"record": result}), 201 if created else 200
            body, status = execute_idempotent(settings, user_id=int(current_user["id"]), action_code=request.path, key=request.headers.get("Idempotency-Key"), payload=payload, operation=perform)
            return jsonify(body), status
        except (CsrfError, AuthServiceError, DomainError) as error:
            return error_response(error)
        except pymysql.IntegrityError as error:
            if error.args and error.args[0] == 1452:
                return error_response(DomainError("MASTER_RELATION_NOT_FOUND", "所属区域或分组不存在，请从已核验选项中选择", 400))
            raise

    @blueprint.get("/<resource>")
    def list_records(resource: str) -> tuple[Response, int] | Response:
        try:
            page, page_size = pagination(code="MASTER_PAGE_INVALID")
            result = service.list_records(user(), resource, page=page, page_size=page_size, status=request.args.get("status") or None, search=request.args.get("search") or None)
            return jsonify(ok(result))
        except (AuthServiceError, DomainError) as error:
            return error_response(error)
        except (TypeError, ValueError):
            return error_response(DomainError("MASTER_PAGE_INVALID", "分页参数无效", 400))

    @blueprint.get("/<resource>/<int:record_id>")
    def get_record(resource: str, record_id: int) -> tuple[Response, int] | Response:
        try:
            return jsonify(ok({"record": service.get(user(), resource, record_id)}))
        except (AuthServiceError, DomainError) as error:
            return error_response(error)

    @blueprint.post("/<resource>")
    def create_record(resource: str) -> tuple[Response, int] | Response:
        return write(service.create, resource, created=True)

    @blueprint.patch("/<resource>/<int:record_id>")
    def update_record(resource: str, record_id: int) -> tuple[Response, int] | Response:
        return write(service.update, resource, record_id)

    @blueprint.post("/<resource>/<int:record_id>/submit")
    def submit_record(resource: str, record_id: int) -> tuple[Response, int] | Response:
        return write(service.submit, resource, record_id)

    @blueprint.post("/<resource>/<int:record_id>/verify")
    def verify_record(resource: str, record_id: int) -> tuple[Response, int] | Response:
        return write(service.verify, resource, record_id)

    @blueprint.post("/ponds/<int:pond_id>/status-changes")
    def request_pond_status_change(pond_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            result = service.request_pond_status_change(user(), pond_id, json_object())
            return jsonify(ok({"status_change": result}, message="塘口状态变更已提交核验")), 201
        except (CsrfError, AuthServiceError, DomainError) as error:
            return error_response(error)

    @blueprint.post("/<resource>/<int:record_id>/archive")
    def archive_record(resource: str, record_id: int) -> tuple[Response, int] | Response:
        return write(service.archive, resource, record_id)

    @blueprint.post("/ponds/<int:pond_id>/status-changes/<int:request_id>/verify")
    def verify_pond_status_change(pond_id: int, request_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            return jsonify(ok(service.verify_pond_status_change(user(), pond_id, request_id, json_object()), message="塘口状态变更已核验"))
        except (CsrfError, AuthServiceError, DomainError) as error:
            return error_response(error)

    @blueprint.delete("/<resource>/<int:record_id>")
    def delete_record(resource: str, record_id: int) -> tuple[Response, int] | Response:
        try:
            csrf()
            return jsonify(ok({"record": service.delete(user(), resource, record_id)}, message="未提交且无引用的草稿已删除"))
        except (CsrfError, AuthServiceError, DomainError) as error:
            return error_response(error)

    return blueprint
