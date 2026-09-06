from __future__ import annotations

from typing import Any
from uuid import uuid4

from flask import Blueprint, Response, g, jsonify, request

from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.http.request_helpers import json_object, require_csrf
from backend.layers.common.http.response import fail, ok
from backend.layers.common.security.csrf import CsrfError
from backend.layers.common.security.session import hash_session_token, request_session_token
from backend.layers.features.auth.auth_contracts import AuthServiceError
from backend.layers.features.auth.auth_service import AuthService
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError


def create_agent_blueprint(settings: Settings, auth_store: Any, gateway: Any) -> Blueprint:
    """Expose the authenticated boundary used by the Harness sidecar and Vue panel."""
    blueprint = Blueprint("agent", __name__, url_prefix="/api/v1/agent")
    auth = AuthService(auth_store, settings)

    def current_user() -> dict[str, Any]:
        session_token = request_session_token(request)
        user = auth.current_user(session_token, request_id=getattr(g, "request_id", None))
        if session_token:
            # Keep the confirmation bound to this session without exposing the raw token.
            user["_session_hash"] = hash_session_token(session_token)
        return user

    def error_response(error: Exception, fallback: str = "AGENT_REQUEST_FAILED") -> tuple[Response, int]:
        status = 403 if isinstance(error, CsrfError) else int(getattr(error, "status", 400))
        message = getattr(error, "message", str(error))
        return jsonify(fail(getattr(error, "code", fallback), message, status, data=getattr(error, "data", None))), status

    def conversation_id(payload: dict[str, Any]) -> str:
        value = payload.get("conversation_id")
        if value is None:
            return uuid4().hex
        if not isinstance(value, str) or not value.strip() or len(value) > 64:
            raise AgentGatewayError("VALIDATION_ERROR", "conversation_id 必须是 1-64 个字符", 400)
        return value.strip()

    @blueprint.post("/turn")
    def turn() -> tuple[Response, int] | Response:
        try:
            user = current_user()
            require_csrf()
            payload = json_object()
            message = payload.get("message")
            if not isinstance(message, str) or not message.strip():
                raise AgentGatewayError("VALIDATION_ERROR", "请输入要执行的指令", 400)
            if len(message.strip()) > 4000:
                raise AgentGatewayError("VALIDATION_ERROR", "指令长度不能超过 4000 个字符", 400)
            runner = getattr(gateway, "run_turn", None)
            if not callable(runner):
                raise AgentGatewayError("AGENT_UNAVAILABLE", "智能体服务暂时不可用，请稍后重试", 503)
            result = runner(
                user,
                message.strip(),
                conversation_id=conversation_id(payload),
                request_id=str(getattr(g, "request_id", "")),
            )
            return jsonify(ok(result))
        except (CsrfError, AuthServiceError, AgentGatewayError, DomainError) as error:
            return error_response(error)
        except (TypeError, ValueError) as error:
            return error_response(AgentGatewayError("VALIDATION_ERROR", "请求参数无效", 400))

    @blueprint.post("/confirm")
    def confirm() -> tuple[Response, int] | Response:
        try:
            user = current_user()
            require_csrf()
            payload = json_object()
            token = payload.get("token", "")
            if not isinstance(token, str):
                raise AgentGatewayError("VALIDATION_ERROR", "确认令牌必须是字符串", 400)
            result = gateway.confirm(user, token, request_id=str(getattr(g, "request_id", "")))
            return jsonify(ok(result))
        except (CsrfError, AuthServiceError, AgentGatewayError, DomainError) as error:
            return error_response(error)
        except (TypeError, ValueError):
            return error_response(AgentGatewayError("VALIDATION_ERROR", "请求参数无效", 400))

    return blueprint
