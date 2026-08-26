from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, Response, g, jsonify, request, session

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.http.response import fail, ok
from backend.layers.common.http.request_helpers import pagination
from backend.layers.common.security.csrf import CsrfError, validate_csrf_token
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError
from backend.layers.features.cost.cost_enterprise_service import CostEnterpriseService


def register_cost_enterprise_routes(blueprint: Blueprint, auth: AuthService, service: CostEnterpriseService) -> None:
    def user() -> dict[str, Any]:
        return auth.current_user(request.cookies.get("adp_session"), request_id=getattr(g, "request_id", None))

    def error(exc: Exception) -> tuple[Response, int]:
        status = 403 if isinstance(exc, CsrfError) else int(getattr(exc, "status", 400))
        message = getattr(exc, "message", str(exc))
        return jsonify(fail(getattr(exc, "code", "COST_REQUEST_FAILED"), message, status)), status

    def listing(operation: Callable[..., dict[str, Any]]) -> tuple[Response, int] | Response:
        try:
            page, page_size = pagination(code="COST_PAGE_INVALID")
            return jsonify(ok(operation(
                user(), page=page, page_size=page_size,
                status=request.args.get("status") or None, search=request.args.get("search") or None,
            )))
        except (AuthServiceError, DomainError) as exc:
            return error(exc)

    def detail(operation: Callable[..., dict[str, Any]], record_id: int) -> tuple[Response, int] | Response:
        try:
            return jsonify(ok(operation(user(), record_id)))
        except (AuthServiceError, DomainError) as exc:
            return error(exc)

    def json_body() -> dict[str, Any]:
        if not request.is_json:
            raise DomainError("COST_PAYLOAD_INVALID", "请求内容必须是 JSON 对象", 400)
        try:
            payload = request.get_json()
        except Exception as exc:
            raise DomainError("COST_PAYLOAD_INVALID", "JSON 格式无效", 400) from exc
        if not isinstance(payload, dict):
            raise DomainError("COST_PAYLOAD_INVALID", "请求内容必须是 JSON 对象", 400)
        return payload

    def write(operation: Callable[..., dict[str, Any]], record_id: int | None = None, *, created: bool = False) -> tuple[Response, int] | Response:
        try:
            validate_csrf_token(request.headers.get("X-CSRF-Token"), session.get("csrf_token"))
            payload = json_body()
            result = operation(user(), payload) if record_id is None else operation(user(), record_id, payload)
            response = jsonify(ok(result)); response.status_code = 201 if created else 200
            return response
        except (CsrfError, AuthServiceError, DomainError) as exc:
            return error(exc)

    def remove(operation: Callable[..., dict[str, Any]], record_id: int) -> tuple[Response, int] | Response:
        try:
            validate_csrf_token(request.headers.get("X-CSRF-Token"), session.get("csrf_token"))
            return jsonify(ok(operation(user(), record_id)))
        except (CsrfError, AuthServiceError, DomainError) as exc:
            return error(exc)

    @blueprint.get("/expenses")
    def list_expenses() -> tuple[Response, int] | Response: return listing(service.list_expenses)

    @blueprint.get("/expenses/<int:record_id>")
    def expense(record_id: int) -> tuple[Response, int] | Response: return detail(service.get_expense, record_id)

    @blueprint.post("/expenses")
    def create_expense() -> tuple[Response, int] | Response: return write(service.create_expense, created=True)

    @blueprint.patch("/expenses/<int:record_id>")
    def update_expense(record_id: int) -> tuple[Response, int] | Response: return write(service.update_expense, record_id)

    @blueprint.post("/expenses/<int:record_id>/submit")
    def submit_expense(record_id: int) -> tuple[Response, int] | Response: return write(service.submit_expense, record_id)

    @blueprint.post("/expenses/<int:record_id>/verify")
    def verify_expense(record_id: int) -> tuple[Response, int] | Response: return write(service.verify_expense, record_id)

    @blueprint.post("/expenses/<int:record_id>/confirm")
    def confirm_expense(record_id: int) -> tuple[Response, int] | Response: return write(service.confirm_expense, record_id)

    @blueprint.post("/expenses/<int:record_id>/reverse")
    def reverse_expense(record_id: int) -> tuple[Response, int] | Response: return write(service.reverse_expense, record_id)

    @blueprint.delete("/expenses/<int:record_id>")
    def delete_expense(record_id: int) -> tuple[Response, int] | Response: return remove(service.delete_expense, record_id)

    @blueprint.get("/assets")
    def list_assets() -> tuple[Response, int] | Response: return listing(service.list_assets)

    @blueprint.get("/assets/<int:record_id>")
    def asset(record_id: int) -> tuple[Response, int] | Response: return detail(service.get_asset, record_id)

    @blueprint.post("/assets")
    def create_asset() -> tuple[Response, int] | Response: return write(service.create_asset, created=True)

    @blueprint.patch("/assets/<int:record_id>")
    def update_asset(record_id: int) -> tuple[Response, int] | Response: return write(service.update_asset, record_id)

    @blueprint.post("/assets/<int:record_id>/submit")
    def submit_asset(record_id: int) -> tuple[Response, int] | Response: return write(service.submit_asset, record_id)

    @blueprint.post("/assets/<int:record_id>/verify")
    def verify_asset(record_id: int) -> tuple[Response, int] | Response: return write(service.verify_asset, record_id)

    @blueprint.post("/assets/<int:record_id>/confirm")
    def confirm_asset(record_id: int) -> tuple[Response, int] | Response: return write(service.confirm_asset, record_id)

    @blueprint.post("/assets/<int:record_id>/depreciate")
    def depreciate_asset(record_id: int) -> tuple[Response, int] | Response: return write(service.depreciate_asset, record_id, created=True)

    @blueprint.delete("/assets/<int:record_id>")
    def delete_asset(record_id: int) -> tuple[Response, int] | Response: return remove(service.delete_asset, record_id)

    @blueprint.post("/allocations")
    def run_allocation() -> tuple[Response, int] | Response: return write(service.run_allocation, created=True)

    @blueprint.get("/settlements")
    def list_settlements() -> tuple[Response, int] | Response: return listing(service.list_settlements)

    @blueprint.get("/settlements/<int:record_id>")
    def settlement(record_id: int) -> tuple[Response, int] | Response: return detail(service.get_settlement, record_id)

    @blueprint.post("/settlements")
    def create_settlement() -> tuple[Response, int] | Response: return write(service.create_settlement, created=True)

    @blueprint.patch("/settlements/<int:record_id>")
    def update_settlement(record_id: int) -> tuple[Response, int] | Response: return write(service.update_settlement, record_id)

    @blueprint.delete("/settlements/<int:record_id>")
    def delete_settlement(record_id: int) -> tuple[Response, int] | Response: return remove(service.delete_settlement, record_id)

    @blueprint.post("/settlements/<int:record_id>/submit")
    def submit_settlement(record_id: int) -> tuple[Response, int] | Response: return write(service.submit_settlement, record_id)

    @blueprint.post("/settlements/<int:record_id>/verify")
    def verify_settlement(record_id: int) -> tuple[Response, int] | Response: return write(service.verify_settlement, record_id)

    @blueprint.post("/settlements/<int:record_id>/confirm")
    def confirm_settlement(record_id: int) -> tuple[Response, int] | Response: return write(service.confirm_settlement, record_id)

    @blueprint.post("/settlements/<int:record_id>/reverse")
    def reverse_settlement(record_id: int) -> tuple[Response, int] | Response: return write(service.reverse_settlement, record_id)

    @blueprint.get("/reports/net")
    def net_report() -> tuple[Response, int] | Response:
        try:
            return jsonify(ok(service.net_report(user(), request.args)))
        except (AuthServiceError, DomainError) as exc:
            return error(exc)
