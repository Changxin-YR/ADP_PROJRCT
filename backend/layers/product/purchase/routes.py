from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, Response, g, jsonify, request

from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.http.response import fail, ok
from backend.layers.common.http.request_helpers import json_object, pagination, require_csrf
from backend.layers.common.security.csrf import CsrfError
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError
from backend.layers.features.purchase.purchase_service import PurchaseService


def create_purchase_blueprint(settings: Settings, auth_store: Any, purchase_store: Any) -> Blueprint:
    blueprint = Blueprint("purchase", __name__, url_prefix="/api/v1/purchase")
    auth = AuthService(auth_store, settings)
    service = PurchaseService(purchase_store)

    def user() -> dict[str, Any]:
        return auth.current_user(request.cookies.get("adp_session"), request_id=getattr(g, "request_id", None))

    def error(exc: Exception) -> tuple[Response, int]:
        status = 403 if isinstance(exc, CsrfError) else int(getattr(exc, "status", 400))
        return jsonify(fail(getattr(exc, "code", "PURCHASE_REQUEST_FAILED"), getattr(exc, "message", str(exc)), status)), status

    def write(operation: Callable[..., dict[str, Any]], record_id: int | None = None, *, created: bool = False) -> tuple[Response, int] | Response:
        try:
            require_csrf()
            payload = json_object()
            row = operation(user(), payload) if record_id is None else operation(user(), record_id, payload)
            response = jsonify(ok({"record": row})); response.status_code = 201 if created else 200
            return response
        except (CsrfError, AuthServiceError, DomainError) as exc:
            return error(exc)

    def listing(operation: Callable[..., dict[str, Any]]) -> tuple[Response, int] | Response:
        try:
            page, page_size = pagination(code="PURCHASE_PAGE_INVALID")
            return jsonify(ok(operation(user(), page=page, page_size=page_size, status=request.args.get("status") or None, search=request.args.get("search") or None)))
        except (AuthServiceError, DomainError) as exc:
            return error(exc)
        except (TypeError, ValueError):
            return error(DomainError("PURCHASE_PAGE_INVALID", "分页参数无效", 400))

    @blueprint.get("/orders")
    def orders() -> tuple[Response, int] | Response: return listing(service.list_orders)

    @blueprint.post("/orders")
    def create_order() -> tuple[Response, int] | Response: return write(service.create_order, created=True)

    @blueprint.patch("/orders/<int:record_id>")
    def update_order(record_id: int) -> tuple[Response, int] | Response: return write(service.update_order, record_id)

    @blueprint.post("/orders/<int:record_id>/submit")
    def submit_order(record_id: int) -> tuple[Response, int] | Response: return write(service.submit_order, record_id)

    @blueprint.post("/orders/<int:record_id>/approve")
    def approve_order(record_id: int) -> tuple[Response, int] | Response: return write(service.approve_order, record_id)

    @blueprint.post("/orders/<int:record_id>/cancel")
    def cancel_order(record_id: int) -> tuple[Response, int] | Response: return write(service.cancel_order, record_id)

    @blueprint.delete("/orders/<int:record_id>")
    def delete_order(record_id: int) -> tuple[Response, int] | Response:
        try:
            require_csrf()
            return jsonify(ok({"record": service.delete_order(user(), record_id)}, message="采购草稿已删除"))
        except (CsrfError, AuthServiceError, DomainError) as exc:
            return error(exc)

    @blueprint.get("/payables")
    def payables() -> tuple[Response, int] | Response: return listing(service.list_payables)

    @blueprint.get("/payments")
    def payments() -> tuple[Response, int] | Response: return listing(service.list_payments)

    @blueprint.post("/payments")
    def create_payment() -> tuple[Response, int] | Response: return write(service.create_payment, created=True)

    @blueprint.patch("/payments/<int:record_id>")
    def update_payment(record_id: int) -> tuple[Response, int] | Response: return write(service.update_payment, record_id)

    @blueprint.post("/payments/<int:record_id>/submit")
    def submit_payment(record_id: int) -> tuple[Response, int] | Response: return write(service.submit_payment, record_id)

    @blueprint.post("/payments/<int:record_id>/verify")
    def verify_payment(record_id: int) -> tuple[Response, int] | Response: return write(service.verify_payment, record_id)

    @blueprint.post("/payments/<int:record_id>/cancel")
    def cancel_payment(record_id: int) -> tuple[Response, int] | Response: return write(service.cancel_payment, record_id)

    @blueprint.post("/payments/<int:record_id>/reverse")
    def reverse_payment(record_id: int) -> tuple[Response, int] | Response: return write(service.reverse_payment, record_id)

    @blueprint.delete("/payments/<int:record_id>")
    def delete_payment(record_id: int) -> tuple[Response, int] | Response:
        try:
            require_csrf()
            return jsonify(ok({"record": service.delete_payment(user(), record_id)}, message="付款草稿已删除"))
        except (CsrfError, AuthServiceError, DomainError) as exc:
            return error(exc)

    return blueprint
