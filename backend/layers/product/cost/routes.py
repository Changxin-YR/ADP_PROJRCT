from __future__ import annotations

from datetime import date
from typing import Any

from flask import Blueprint, Response, g, jsonify, request, session

from backend.config.settings import Settings
from backend.layers.common.http.response import fail, ok
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.http.request_helpers import pagination
from backend.layers.common.security.csrf import CsrfError, validate_csrf_token
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError
from backend.layers.features.cost.cost_service import CostService, CostServiceError
from backend.layers.features.cost.cost_enterprise_service import CostEnterpriseService
from backend.layers.product.cost.enterprise_routes import register_cost_enterprise_routes


def create_cost_blueprint(settings: Settings, auth_store: Any, cost_store: Any) -> Blueprint:
    blueprint = Blueprint("cost", __name__, url_prefix="/api/v1/cost")
    auth_service = AuthService(auth_store, settings)
    service = CostService(cost_store)
    enterprise_service = CostEnterpriseService(cost_store)

    def current_user() -> dict[str, Any]:
        return auth_service.current_user(request.cookies.get("adp_session"))

    def parse_date(name: str, default: date | None = None) -> date:
        raw = request.args.get(name)
        if not raw and default is not None:
            return default
        try:
            return date.fromisoformat(str(raw))
        except ValueError as error:
            raise CostServiceError("COST_DATE_INVALID", f"{name} 日期格式无效", 400) from error

    def error_response(error: Exception, fallback_code: str = "COST_REQUEST_FAILED", fallback_status: int = 400) -> tuple[Response, int]:
        status = 403 if isinstance(error, CsrfError) else int(getattr(error, "status", fallback_status))
        message = getattr(error, "message", str(error))
        return jsonify(fail(getattr(error, "code", fallback_code), message, status)), status

    def json_body() -> dict[str, Any]:
        if not request.is_json:
            raise DomainError("COST_PAYLOAD_INVALID", "请求内容必须是 JSON 对象", 400)
        try:
            payload = request.get_json()
        except Exception as error:
            raise DomainError("COST_PAYLOAD_INVALID", "JSON 格式无效", 400) from error
        if not isinstance(payload, dict):
            raise DomainError("COST_PAYLOAD_INVALID", "请求内容必须是 JSON 对象", 400)
        return payload

    @blueprint.get("/structure")
    def structure() -> tuple[Response, int] | Response:
        try:
            period_start = parse_date("period_start")
            period_end = parse_date("period_end")
            if period_start > period_end:
                raise CostServiceError("COST_PERIOD_INVALID", "开始日期不能晚于结束日期", 400)
            return jsonify(ok(service.structure(current_user(), period_start=period_start, period_end=period_end)))
        except (AuthServiceError, CostServiceError) as error:
            return error_response(error)

    @blueprint.get("/entries")
    def entries() -> tuple[Response, int] | Response:
        try:
            category_code = str(request.args.get("category_code", "")).strip()
            if not category_code:
                raise CostServiceError("COST_CATEGORY_REQUIRED", "请选择成本分类", 400)
            period_start = parse_date("period_start")
            period_end = parse_date("period_end")
            if period_start > period_end:
                raise CostServiceError("COST_PERIOD_INVALID", "开始日期不能晚于结束日期", 400)
            page, page_size = pagination(code="COST_PAGE_INVALID")
            result = service.entries(
                current_user(),
                category_code=category_code,
                period_start=period_start,
                period_end=period_end,
                page=page,
                page_size=page_size,
                status=str(request.args.get("status", "confirmed")),
            )
            return jsonify(ok(result))
        except (AuthServiceError, CostServiceError, DomainError) as error:
            return error_response(error)

    @blueprint.get("/allocation-rules")
    def allocation_rules() -> tuple[Response, int] | Response:
        try:
            mode = str(request.args.get("mode", "effective")).strip()
            if mode == "latest":
                result = service.latest_rules(current_user())
            elif mode == "effective":
                result = service.rules(current_user(), effective_at=parse_date("effective_at", date.today()))
            else:
                raise CostServiceError("COST_RULE_MODE_INVALID", "规则查询模式无效", 400)
            return jsonify(ok(result))
        except (AuthServiceError, CostServiceError) as error:
            return error_response(error)

    @blueprint.post("/entries")
    def create_entry() -> tuple[Response, int] | Response:
        try:
            validate_csrf_token(request.headers.get("X-CSRF-Token"), session.get("csrf_token"))
            result = enterprise_service.create_expense(current_user(), json_body())
            response = jsonify(ok({"entry": result}, message="成本草稿已保存"))
            response.status_code = 201
            return response
        except (CsrfError, AuthServiceError, CostServiceError, DomainError) as error:
            return error_response(error)

    @blueprint.patch("/entries/<int:entry_id>")
    def update_entry(entry_id: int) -> tuple[Response, int] | Response:
        try:
            validate_csrf_token(request.headers.get("X-CSRF-Token"), session.get("csrf_token"))
            result = enterprise_service.update_expense(current_user(), entry_id, json_body())
            return jsonify(ok({"entry": result}, message="成本草稿已更新"))
        except (CsrfError, AuthServiceError, CostServiceError, DomainError) as error:
            return error_response(error)

    @blueprint.post("/entries/<int:entry_id>/submit")
    def submit_entry(entry_id: int) -> tuple[Response, int] | Response:
        try:
            validate_csrf_token(request.headers.get("X-CSRF-Token"), session.get("csrf_token"))
            result = enterprise_service.submit_expense(current_user(), entry_id, json_body())
            return jsonify(ok({"entry": result}, message="成本已提交核验"))
        except (CsrfError, AuthServiceError, CostServiceError, DomainError) as error:
            return error_response(error)

    @blueprint.post("/entries/<int:entry_id>/verify")
    def verify_entry(entry_id: int) -> tuple[Response, int] | Response:
        try:
            validate_csrf_token(request.headers.get("X-CSRF-Token"), session.get("csrf_token"))
            result = enterprise_service.verify_expense(current_user(), entry_id, json_body())
            return jsonify(ok({"entry": result}, message="成本已完成核验，等待最终确认"))
        except (CsrfError, AuthServiceError, CostServiceError, DomainError) as error:
            return error_response(error)

    @blueprint.post("/entries/<int:entry_id>/confirm")
    def confirm_entry(entry_id: int) -> tuple[Response, int] | Response:
        try:
            validate_csrf_token(request.headers.get("X-CSRF-Token"), session.get("csrf_token"))
            result = enterprise_service.confirm_expense(current_user(), entry_id, json_body())
            return jsonify(ok({"entry": result}, message="成本核验已完成，记录进入只读状态"))
        except (CsrfError, AuthServiceError, CostServiceError, DomainError) as error:
            return error_response(error)

    @blueprint.delete("/entries/<int:entry_id>")
    def delete_draft(entry_id: int) -> tuple[Response, int] | Response:
        try:
            validate_csrf_token(request.headers.get("X-CSRF-Token"), session.get("csrf_token"))
            result = enterprise_service.delete_expense(current_user(), entry_id)
            return jsonify(ok({"entry": result}, message="未正式录入的成本草稿已删除"))
        except (CsrfError, AuthServiceError, CostServiceError, DomainError) as error:
            return error_response(error)

    @blueprint.post("/entries/<int:entry_id>/reverse")
    def reverse_entry(entry_id: int) -> tuple[Response, int] | Response:
        try:
            validate_csrf_token(request.headers.get("X-CSRF-Token"), session.get("csrf_token"))
            payload = json_body()
            result = enterprise_service.reverse_expense(current_user(), entry_id, payload)
            return jsonify(ok({"entry": result}, message="已生成冲销记录，原核验记录保持不变"))
        except (CsrfError, AuthServiceError, CostServiceError, DomainError) as error:
            return error_response(error)

    @blueprint.put("/allocation-rules")
    def save_allocation_rules() -> tuple[Response, int] | Response:
        try:
            validate_csrf_token(request.headers.get("X-CSRF-Token"), session.get("csrf_token"))
            result = service.save_rules(
                current_user(),
                json_body(),
                ip_address=request.remote_addr or "unknown",
            )
            return jsonify(ok(result, message="分摊规则版本已保存"))
        except (CsrfError, AuthServiceError, CostServiceError) as error:
            return error_response(error)
        except ValueError as error:
            if str(error) == "RULE_EFFECTIVE_DATE_CONFLICT":
                return error_response(CostServiceError("COST_RULE_VERSION_CONFLICT", "该生效日期已有规则版本", 409))
            if str(error) == "RULE_CATEGORY_SET_MISMATCH":
                return error_response(CostServiceError("COST_RULES_INCOMPLETE", "分摊规则必须完整覆盖全部启用成本类别", 400))
            return error_response(CostServiceError("COST_RULE_SAVE_FAILED", "分摊规则保存失败", 400))

    register_cost_enterprise_routes(blueprint, auth_service, enterprise_service, settings)
    return blueprint
