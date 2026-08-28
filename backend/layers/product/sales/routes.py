from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, Response, g, jsonify, request

from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.governance.idempotency import execute_idempotent
from backend.layers.common.http.response import fail, ok
from backend.layers.common.http.request_helpers import json_object, pagination, require_csrf
from backend.layers.common.security.csrf import CsrfError
from backend.layers.common.security.session import request_session_token
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError
from backend.layers.features.sales.sales_service import SalesService


def create_sales_blueprint(settings: Settings, auth_store: Any, sales_store: Any) -> Blueprint:
    blueprint = Blueprint("sales", __name__, url_prefix="/api/v1/sales")
    auth, service = AuthService(auth_store, settings), SalesService(sales_store)

    def user() -> dict[str, Any]:
        return auth.current_user(request_session_token(request), request_id=getattr(g, "request_id", None))

    def error(exc: Exception) -> tuple[Response, int]:
        status = 403 if isinstance(exc, CsrfError) else int(getattr(exc, "status", 400))
        return jsonify(fail(getattr(exc, "code", "SALES_REQUEST_FAILED"), getattr(exc, "message", str(exc)), status)), status

    def write(operation: Callable[..., dict[str, Any]], record_id: int | None = None, *, created: bool = False) -> tuple[Response, int] | Response:
        try:
            require_csrf(); payload = json_object(); current_user = user()
            def perform() -> tuple[dict[str, Any], int]:
                row = operation(current_user, payload) if record_id is None else operation(current_user, record_id, payload)
                return ok({"record": row}), 201 if created else 200
            body, status = execute_idempotent(settings, user_id=int(current_user["id"]), action_code=request.path, key=request.headers.get("Idempotency-Key"), payload=payload, operation=perform)
            return jsonify(body), status
        except (CsrfError, AuthServiceError, DomainError) as exc: return error(exc)

    def listing(operation: Callable[..., dict[str, Any]]) -> tuple[Response, int] | Response:
        try:
            page, page_size = pagination(code="SALES_PAGE_INVALID")
            return jsonify(ok(operation(user(), page=page, page_size=page_size, status=request.args.get("status") or None, search=request.args.get("search") or None, sort_by=request.args.get("sort_by") or None, sort_dir=request.args.get("sort_dir") or None)))
        except (AuthServiceError, DomainError) as exc: return error(exc)
        except (TypeError, ValueError): return error(DomainError("SALES_PAGE_INVALID", "分页参数无效", 400))

    def remove(operation: Callable[..., dict[str, Any]], record_id: int, message: str) -> tuple[Response, int] | Response:
        try:
            require_csrf(); return jsonify(ok({"record": operation(user(), record_id)}, message=message))
        except (CsrfError, AuthServiceError, DomainError) as exc: return error(exc)

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
    def delete_order(record_id: int) -> tuple[Response, int] | Response: return remove(service.delete_order, record_id, "销售草稿已删除")

    @blueprint.get("/deliveries")
    def deliveries() -> tuple[Response, int] | Response: return listing(service.list_deliveries)

    @blueprint.post("/deliveries")
    def create_delivery() -> tuple[Response, int] | Response: return write(service.create_delivery, created=True)

    @blueprint.patch("/deliveries/<int:record_id>")
    def update_delivery(record_id: int) -> tuple[Response, int] | Response: return write(service.update_delivery, record_id)

    @blueprint.post("/deliveries/<int:record_id>/submit")
    def submit_delivery(record_id: int) -> tuple[Response, int] | Response: return write(service.submit_delivery, record_id)

    @blueprint.post("/deliveries/<int:record_id>/verify")
    def verify_delivery(record_id: int) -> tuple[Response, int] | Response: return write(service.verify_delivery, record_id)

    @blueprint.post("/deliveries/<int:record_id>/correct")
    def correct_delivery(record_id: int) -> tuple[Response, int] | Response: return write(service.correct_delivery, record_id, created=True)

    @blueprint.post("/deliveries/<int:record_id>/cancel")
    def cancel_delivery(record_id: int) -> tuple[Response, int] | Response: return write(service.cancel_delivery, record_id)

    @blueprint.delete("/deliveries/<int:record_id>")
    def delete_delivery(record_id: int) -> tuple[Response, int] | Response: return remove(service.delete_delivery, record_id, "交付草稿已删除")

    @blueprint.get("/returns")
    def returns() -> tuple[Response, int] | Response: return listing(service.list_returns)

    @blueprint.post("/returns")
    def create_return() -> tuple[Response, int] | Response: return write(service.create_return, created=True)

    @blueprint.post("/returns/<int:record_id>/submit")
    def submit_return(record_id: int) -> tuple[Response, int] | Response: return write(service.submit_return, record_id)

    @blueprint.post("/returns/<int:record_id>/verify")
    def verify_return(record_id: int) -> tuple[Response, int] | Response: return write(service.verify_return, record_id)

    @blueprint.post("/returns/<int:record_id>/cancel")
    def cancel_return(record_id: int) -> tuple[Response, int] | Response: return write(service.cancel_return, record_id)

    @blueprint.delete("/returns/<int:record_id>")
    def delete_return(record_id: int) -> tuple[Response, int] | Response: return remove(service.delete_return, record_id, "销售退货草稿已删除")

    @blueprint.get("/receivables")
    def receivables() -> tuple[Response, int] | Response: return listing(service.list_receivables)

    @blueprint.get("/receipts")
    def receipts() -> tuple[Response, int] | Response: return listing(service.list_receipts)

    @blueprint.post("/receipts")
    def create_receipt() -> tuple[Response, int] | Response: return write(service.create_receipt, created=True)

    @blueprint.patch("/receipts/<int:record_id>")
    def update_receipt(record_id: int) -> tuple[Response, int] | Response: return write(service.update_receipt, record_id)

    @blueprint.post("/receipts/<int:record_id>/submit")
    def submit_receipt(record_id: int) -> tuple[Response, int] | Response: return write(service.submit_receipt, record_id)

    @blueprint.post("/receipts/<int:record_id>/verify")
    def verify_receipt(record_id: int) -> tuple[Response, int] | Response: return write(service.verify_receipt, record_id)

    @blueprint.post("/receipts/<int:record_id>/cancel")
    def cancel_receipt(record_id: int) -> tuple[Response, int] | Response: return write(service.cancel_receipt, record_id)

    @blueprint.post("/receipts/<int:record_id>/reverse")
    def reverse_receipt(record_id: int) -> tuple[Response, int] | Response: return write(service.reverse_receipt, record_id)

    @blueprint.delete("/receipts/<int:record_id>")
    def delete_receipt(record_id: int) -> tuple[Response, int] | Response: return remove(service.delete_receipt, record_id, "收款草稿已删除")

    return blueprint
