from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, Response, g, jsonify, request

from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.http.response import fail, ok
from backend.layers.common.http.request_helpers import json_object, pagination, require_csrf
from backend.layers.common.security.csrf import CsrfError
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError
from backend.layers.features.warehouse.warehouse_service import WarehouseService


def create_warehouse_blueprint(settings: Settings, auth_store: Any, warehouse_store: Any) -> Blueprint:
    blueprint = Blueprint("warehouse", __name__, url_prefix="/api/v1/warehouse")
    auth = AuthService(auth_store, settings)
    service = WarehouseService(warehouse_store)

    def user() -> dict[str, Any]:
        return auth.current_user(request.cookies.get("adp_session"), request_id=getattr(g, "request_id", None))

    def error(exc: Exception) -> tuple[Response, int]:
        status = 403 if isinstance(exc, CsrfError) else int(getattr(exc, "status", 400))
        return jsonify(fail(getattr(exc, "code", "WAREHOUSE_REQUEST_FAILED"), getattr(exc, "message", str(exc)), status)), status

    def write(operation: Callable[..., dict[str, Any]], resource: str, record_id: int | None = None, *, created: bool = False) -> tuple[Response, int] | Response:
        try:
            require_csrf()
            payload = json_object()
            row = operation(user(), resource, payload) if record_id is None else operation(user(), resource, record_id, payload)
            response = jsonify(ok({"record": row})); response.status_code = 201 if created else 200
            return response
        except (CsrfError, AuthServiceError, DomainError) as exc:
            return error(exc)

    @blueprint.get("/<resource>")
    def records(resource: str) -> tuple[Response, int] | Response:
        try:
            if resource == "warehouses":
                return jsonify(ok({"items": service.warehouses(user(), include_disabled=request.args.get("include_disabled") == "1")}))
            page, page_size = pagination(code="WAREHOUSE_PAGE_INVALID")
            result = service.list_records(user(), resource, page=page, page_size=page_size, status=request.args.get("status") or None, search=request.args.get("search") or None)
            return jsonify(ok(result))
        except (AuthServiceError, DomainError) as exc:
            return error(exc)
        except (TypeError, ValueError):
            return error(DomainError("WAREHOUSE_PAGE_INVALID", "分页参数无效", 400))

    @blueprint.post("/<resource>")
    def create(resource: str) -> tuple[Response, int] | Response:
        if resource == "warehouses":
            try:
                require_csrf()
                return jsonify(ok({"warehouse": service.create_warehouse(user(), json_object())})), 201
            except (CsrfError, AuthServiceError, DomainError) as exc:
                return error(exc)
        return write(service.create, resource, created=True)

    @blueprint.get("/<resource>/<int:record_id>")
    def get_record(resource: str, record_id: int) -> tuple[Response, int] | Response:
        try:
            return jsonify(ok({"record": service.get(user(), resource, record_id)}))
        except (AuthServiceError, DomainError) as exc:
            return error(exc)

    @blueprint.patch("/<resource>/<int:record_id>")
    def update(resource: str, record_id: int) -> tuple[Response, int] | Response:
        if resource == "warehouses":
            try:
                require_csrf()
                return jsonify(ok({"warehouse": service.update_warehouse(user(), record_id, json_object())}))
            except (CsrfError, AuthServiceError, DomainError) as exc:
                return error(exc)
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

    @blueprint.post("/<resource>/<int:record_id>/dispatch")
    def dispatch(resource: str, record_id: int) -> tuple[Response, int] | Response:
        return write(service.dispatch, resource, record_id)

    @blueprint.post("/<resource>/<int:record_id>/receive")
    def receive(resource: str, record_id: int) -> tuple[Response, int] | Response:
        return write(service.receive, resource, record_id)

    @blueprint.post("/<resource>/<int:record_id>/cancel")
    def cancel_transfer(resource: str, record_id: int) -> tuple[Response, int] | Response:
        return write(service.cancel_transfer, resource, record_id)

    @blueprint.delete("/<resource>/<int:record_id>")
    def delete(resource: str, record_id: int) -> tuple[Response, int] | Response:
        try:
            require_csrf()
            return jsonify(ok({"record": service.delete(user(), resource, record_id)}, message="未提交且无引用的仓储草稿已删除"))
        except (CsrfError, AuthServiceError, DomainError) as exc:
            return error(exc)

    @blueprint.get("/ledger")
    def ledger() -> tuple[Response, int] | Response:
        try:
            page, page_size = pagination(default_page_size=50, code="WAREHOUSE_PAGE_INVALID")
            return jsonify(ok(service.ledger(user(), page=page, page_size=page_size)))
        except (AuthServiceError, DomainError) as exc:
            return error(exc)
        except (TypeError, ValueError):
            return error(DomainError("WAREHOUSE_PAGE_INVALID", "分页参数无效", 400))

    @blueprint.get("/alerts")
    def alerts() -> tuple[Response, int] | Response:
        try:
            return jsonify(ok({"items": service.alerts(user())}))
        except (AuthServiceError, DomainError) as exc:
            return error(exc)

    @blueprint.post("/alerts/<path:alert_key>/handle")
    def handle_alert(alert_key: str) -> tuple[Response, int] | Response:
        try:
            require_csrf()
            return jsonify(ok({"alert": service.handle_alert(user(), alert_key, json_object())}))
        except (CsrfError, AuthServiceError, DomainError) as exc:
            return error(exc)

    @blueprint.get("/warehouses")
    def warehouses() -> tuple[Response, int] | Response:
        try:
            return jsonify(ok({"items": service.warehouses(user(), include_disabled=request.args.get("include_disabled") == "1")}))
        except (AuthServiceError, DomainError) as exc:
            return error(exc)

    return blueprint
