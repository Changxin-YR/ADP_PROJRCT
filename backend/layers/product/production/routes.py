from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, Response, g, jsonify, request

from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.idempotency import execute_idempotent
from backend.layers.common.http.response import fail, ok
from backend.layers.common.http.request_helpers import json_object, pagination, require_csrf
from backend.layers.common.security.csrf import CsrfError
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError
from backend.layers.features.production.production_service import ProductionService


def create_production_blueprint(settings: Settings, auth_store: Any, production_store: Any) -> Blueprint:
    blueprint = Blueprint("production", __name__, url_prefix="/api/v1/production")
    auth = AuthService(auth_store, settings)
    service = ProductionService(production_store)

    def user() -> dict[str, Any]:
        return auth.current_user(request.cookies.get("adp_session"), request_id=getattr(g, "request_id", None))

    def csrf() -> None:
        require_csrf()

    def error(error: Exception) -> tuple[Response, int]:
        status = 403 if isinstance(error, CsrfError) else int(getattr(error, "status", 400))
        return jsonify(fail(getattr(error, "code", "PRODUCTION_REQUEST_FAILED"), getattr(error, "message", str(error)), status)), status

    def write(operation: Callable[..., dict[str, Any]], resource: str, record_id: int | None = None, *, created: bool = False) -> tuple[Response, int] | Response:
        try:
            csrf(); payload = json_object(); current_user = user()
            def perform() -> tuple[dict[str, Any], int]:
                row = operation(current_user, resource, payload) if record_id is None else operation(current_user, resource, record_id, payload)
                return ok({"record": row}), 201 if created else 200
            body, status = execute_idempotent(settings, user_id=int(current_user["id"]), action_code=request.path, key=request.headers.get("Idempotency-Key"), payload=payload, operation=perform)
            return jsonify(body), status
        except (CsrfError, AuthServiceError, DomainError) as exc:
            return error(exc)

    @blueprint.get("/<resource>")
    def records(resource: str) -> tuple[Response, int] | Response:
        try:
            page, page_size = pagination(code="PRODUCTION_PAGE_INVALID")
            result = service.list_records(user(), resource, page=page, page_size=page_size, status=request.args.get("status") or None, search=request.args.get("search") or None, pond_id=request.args.get("pond_id") or None, area_id=request.args.get("area_id") or None)
            return jsonify(ok(result))
        except (AuthServiceError, DomainError) as exc:
            return error(exc)
        except (TypeError, ValueError):
            return error(DomainError("PRODUCTION_PAGE_INVALID", "分页参数无效", 400))

    @blueprint.post("/<resource>")
    def create(resource: str) -> tuple[Response, int] | Response:
        return write(service.create, resource, created=True)

    @blueprint.get("/<resource>/<int:record_id>")
    def get_record(resource: str, record_id: int) -> tuple[Response, int] | Response:
        try:
            return jsonify(ok({"record": service.get(user(), resource, record_id)}))
        except (AuthServiceError, DomainError) as exc:
            return error(exc)

    @blueprint.patch("/<resource>/<int:record_id>")
    def update(resource: str, record_id: int) -> tuple[Response, int] | Response:
        return write(service.update, resource, record_id)

    @blueprint.post("/<resource>/<int:record_id>/corrections")
    def correct(resource: str, record_id: int) -> tuple[Response, int] | Response:
        return write(service.correct, resource, record_id, created=True)

    @blueprint.post("/<resource>/<int:record_id>/submit")
    def submit(resource: str, record_id: int) -> tuple[Response, int] | Response:
        return write(service.submit, resource, record_id)

    @blueprint.post("/<resource>/<int:record_id>/verify")
    def verify(resource: str, record_id: int) -> tuple[Response, int] | Response:
        return write(service.verify, resource, record_id)

    @blueprint.delete("/<resource>/<int:record_id>")
    def delete(resource: str, record_id: int) -> tuple[Response, int] | Response:
        try:
            csrf(); return jsonify(ok({"record": service.delete(user(), resource, record_id)}, message="未提交且无引用的草稿已删除"))
        except (CsrfError, AuthServiceError, DomainError) as exc:
            return error(exc)

    @blueprint.get("/batches/<int:batch_id>/reconciliation")
    def reconciliation(batch_id: int) -> tuple[Response, int] | Response:
        try:
            return jsonify(ok(service.reconcile(user(), batch_id)))
        except (AuthServiceError, DomainError) as exc:
            return error(exc)

    return blueprint
