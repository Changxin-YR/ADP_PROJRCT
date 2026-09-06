from __future__ import annotations

import re
import secrets
import time
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from flask import Blueprint, Response, current_app, g, jsonify, request

from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.http.request_helpers import json_object, require_csrf
from backend.layers.common.http.response import fail, ok
from backend.layers.common.security.csrf import CsrfError
from backend.layers.common.security.session import hash_session_token, request_session_token
from backend.layers.features.auth.auth_contracts import AuthServiceError
from backend.layers.features.auth.auth_service import AuthService
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError
from backend.layers.features.agent.agent_confirmation_store import MySqlAgentConfirmationStore
from backend.layers.features.agent.agent_gateway_service import AgentGatewayService
from backend.layers.features.agent.agent_tool_registry import AgentTool, build_registry
from backend.layers.features.agent.harness_sidecar import HarnessSidecar


_PATH_PARAMETER = re.compile(r"\{([^}]+)\}")
_AGENT_CONTEXTS: dict[str, tuple[str, float]] = {}


def _issue_context(session_token: str) -> str:
    token = secrets.token_urlsafe(32)
    _AGENT_CONTEXTS[token] = (session_token, time.time() + 90)
    return token


def _context_session_token() -> str | None:
    token = request.headers.get("X-Agent-Context", "").strip()
    if not token:
        return None
    record = _AGENT_CONTEXTS.get(token)
    if record is None:
        return None
    session_token, expires_at = record
    if expires_at <= time.time():
        _AGENT_CONTEXTS.pop(token, None)
        return None
    return session_token


def _dispatch_fixed_tool(tool: AgentTool, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Dispatch only to the path fixed in the checked-in agent registry."""
    payload = arguments.get("payload") if isinstance(arguments.get("payload"), dict) else dict(arguments)
    path = tool.path_template
    path_params = set(_PATH_PARAMETER.findall(path))
    for name in path_params:
        value = arguments.get(name, payload.get(name))
        if value is None:
            raise AgentGatewayError("VALIDATION_ERROR", f"缺少路径参数 {name}", 400)
        path = path.replace("{" + name + "}", quote(str(value), safe=""))
    body = dict(payload)
    for name in path_params:
        body.pop(name, None)
    query = body if tool.method == "GET" else {}
    if tool.method == "GET":
        body = {}
    token = context.get("session_token")
    if not token:
        raise AgentGatewayError("UNAUTHENTICATED", "当前会话不能用于业务调用", 401)
    headers = {"Authorization": f"Bearer {token}", "X-Request-ID": str(context.get("request_id") or "")}
    if context.get("idempotency_key"):
        headers["Idempotency-Key"] = str(context["idempotency_key"])
    response = current_app.test_client().open(path, method=tool.method, query_string=query, json=None if tool.method == "GET" else body, headers=headers)
    result = response.get_json(silent=True)
    if response.status_code >= 400:
        if isinstance(result, dict):
            raise AgentGatewayError(str(result.get("code") or "BUSINESS_ERROR"), str(result.get("message") or "业务操作未完成"), response.status_code, result.get("data"))
        raise AgentGatewayError("BUSINESS_ERROR", "业务操作未完成", response.status_code)
    if isinstance(result, dict):
        return result.get("data") if "data" in result else result
    return {"status": response.status_code}


def create_agent_blueprint(settings: Settings, auth_store: Any, gateway: Any | None = None, sidecar: Any | None = None) -> Blueprint:
    """Expose the authenticated boundary used by the Harness sidecar and Vue panel."""
    blueprint = Blueprint("agent", __name__, url_prefix="/api/v1/agent")
    auth = AuthService(auth_store, settings)
    if gateway is None:
        gateway = AgentGatewayService(settings, registry=build_registry(lambda tool: lambda arguments, context: _dispatch_fixed_tool(tool, arguments, context)), confirmations=MySqlAgentConfirmationStore())
    sidecar = sidecar or HarnessSidecar(settings)

    def current_user() -> dict[str, Any]:
        session_token = request_session_token(request) or _context_session_token()
        user = auth.current_user(session_token, request_id=getattr(g, "request_id", None))
        if session_token:
            # Keep the confirmation bound to this session without exposing the raw token.
            user["_session_hash"] = hash_session_token(session_token)
            user["_session_token"] = session_token
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
            if callable(runner):
                safe_user = {key: value for key, value in user.items() if key != "_session_token"}
                result = runner(safe_user, message.strip(), conversation_id=conversation_id(payload), request_id=str(getattr(g, "request_id", "")))
            elif sidecar is not None:
                result = sidecar.run(
                    message.strip(),
                    context={
                        "conversation_id": conversation_id(payload),
                        "request_id": str(getattr(g, "request_id", "")),
                        "gateway_url": request.host_url.rstrip("/") + "api/v1/agent",
                        "context_token": _issue_context(str(request_session_token(request) or "")),
                    },
                )
            else:
                operation = str(payload.get("operation") or payload.get("tool_name") or "").strip()
                arguments = payload.get("arguments")
                if not operation or not isinstance(arguments, dict):
                    raise AgentGatewayError("AGENT_UNAVAILABLE", "智能体服务暂时不可用，请稍后重试", 503)
                result = gateway.prepare_tool(user, operation, arguments, conversation_id=conversation_id(payload), request_id=str(getattr(g, "request_id", "")))
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

    def operation_request(payload: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
        operation = str(payload.get("operation") or payload.get("tool_name") or "").strip()
        arguments = payload.get("arguments")
        if not operation or not isinstance(arguments, dict):
            raise AgentGatewayError("VALIDATION_ERROR", "请提供 operation 和对象类型 arguments", 400)
        return arguments, operation, conversation_id(payload)

    @blueprint.post("/query")
    def query() -> tuple[Response, int] | Response:
        try:
            if not request.headers.get("X-Agent-Context"):
                require_csrf()
            user = current_user(); arguments, operation, conversation = operation_request(json_object())
            result = gateway.prepare_tool(user, operation, arguments, conversation_id=conversation, request_id=str(getattr(g, "request_id", "")))
            if result.get("kind") != "success":
                raise AgentGatewayError("TOOL_RISK_INVALID", "查询工具未按只读策略注册", 409)
            return jsonify(ok(result))
        except (CsrfError, AuthServiceError, AgentGatewayError, TypeError, ValueError) as error:
            return error_response(error)

    @blueprint.post("/prepare")
    def prepare() -> tuple[Response, int] | Response:
        try:
            if not request.headers.get("X-Agent-Context"):
                require_csrf()
            user = current_user(); arguments, operation, conversation = operation_request(json_object())
            return jsonify(ok(gateway.prepare_tool(user, operation, arguments, conversation_id=conversation, request_id=str(getattr(g, "request_id", "")))))
        except (CsrfError, AuthServiceError, AgentGatewayError, TypeError, ValueError) as error:
            return error_response(error)

    return blueprint
